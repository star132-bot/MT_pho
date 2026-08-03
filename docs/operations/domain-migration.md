# MT Presence Domain Migration Runbook

This runbook records the production domain migration from `mtcijian.lat` to the following canonical structure:

- Primary site: `https://mtdo.cn`
- HTTPS alias: `https://mt6666.cn`, permanently redirected to the primary site
- Retired domain: `https://mtcijian.lat`, temporarily retained as an HTTPS redirect
- Origin server: `45.76.228.175`

Do not place passwords, provider keys, Supabase secrets, or private certificate material in this document or in shell history.

## 1. Understand the Layers

A domain migration changes several independent layers. Updating only one is not enough:

1. Registrar: owns the domain and controls which authoritative DNS servers are delegated.
2. Authoritative DNS: publishes the A/AAAA/CNAME records used by the internet.
3. TLS certificate: proves that the server may serve each HTTPS hostname.
4. Nginx: routes the primary, alias, and retired hostnames.
5. Application environment: generates trusted first-party callback URLs from `MT_PUBLIC_BASE_URL`.
6. Supabase Auth: allowlists email verification and password recovery redirects.

The registrar can be Alibaba Cloud while the authoritative DNS remains Cloudflare. Always inspect NS records instead of assuming the registrar also serves DNS.

## 2. Choose One Canonical Domain

Use one hostname as the canonical application origin:

```text
https://mtdo.cn
```

Redirect other hostnames to it with HTTP `301`. This keeps cookies, Auth callbacks, canonical URLs, and search indexing on one origin. Do not operate two independent authenticated origins unless the application has explicitly been designed for cross-origin sessions.

## 3. Prepare and Verify DNS

Create the following records at the active authoritative DNS provider:

```text
Type  Host  Value
A     @     45.76.228.175
```

For a `www` hostname, use either another A record or a CNAME to the apex. Do not create an AAAA record unless the server really accepts public IPv6 traffic.

Query specific public resolvers:

```bash
dig @8.8.8.8 +short A mtdo.cn
dig @1.1.1.1 +short A mtdo.cn
dig @223.5.5.5 +short A mtdo.cn

dig @8.8.8.8 +short A mt6666.cn
dig @1.1.1.1 +short A mt6666.cn
dig @223.5.5.5 +short A mt6666.cn
```

All results must become:

```text
45.76.228.175
```

Inspect the authoritative DNS delegation:

```bash
dig @8.8.8.8 +short NS mtdo.cn
dig @8.8.8.8 +short NS mt6666.cn
```

If `mt6666.cn` still lists Cloudflare nameservers but Cloudflare access is unavailable, prepare the A record in Alibaba Cloud DNS first, copy the two nameservers assigned by Alibaba Cloud, then change the domain's DNS servers under Alibaba Cloud Domain Console. Never copy nameservers from another domain without checking the assigned values.

DNS caches can temporarily disagree. For example:

```bash
dig @8.8.8.8 +short A mt6666.cn
dig +short A mt6666.cn
```

The first command asks Google DNS explicitly. The second uses the machine's configured recursive resolver. A stale result from the second command is normally a cache-propagation issue; inspect its remaining TTL with:

```bash
dig mt6666.cn A +noall +answer
```

## 4. Back Up the Server Configuration

Connect to the server and create timestamped backups:

```bash
ssh root@45.76.228.175

stamp=$(date +%Y%m%d-%H%M%S)
cp -a /etc/nginx/sites-available/mt-presence-v1.1.2 \
  /etc/nginx/sites-available/mt-presence-v1.1.2.before-domain-$stamp
cp -a /etc/mt-presence/web.env \
  /etc/mt-presence/web.env.before-domain-$stamp
```

The enabled site is a symlink:

```text
/etc/nginx/sites-enabled/mt-cijian
  -> /etc/nginx/sites-available/mt-presence-v1.1.2
```

Edit the target file, not the release files under `/opt/mt-presence/current`.

## 5. Expose the ACME HTTP Challenge

Before referencing a new certificate path, configure the port 80 server for the new domains:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name mtdo.cn mt6666.cn mtcijian.lat www.mtcijian.lat;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }

    location / {
        return 301 https://mtdo.cn$request_uri;
    }
}
```

Validate before reload:

```bash
mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
nginx -t
systemctl reload nginx
```

Do not change the existing HTTPS certificate paths until the new certificate exists.

## 6. Issue or Expand the Certificate

Issue one certificate containing both new domains:

```bash
certbot certonly --webroot \
  -w /var/www/letsencrypt \
  --cert-name mtdo.cn \
  -d mtdo.cn \
  -d mt6666.cn
```

If `mtdo.cn` was issued first without the alias, expand the existing certificate non-interactively:

```bash
certbot certonly --webroot \
  -w /var/www/letsencrypt \
  --cert-name mtdo.cn \
  -d mtdo.cn \
  -d mt6666.cn \
  --expand \
  --non-interactive
```

Verify the exact certificate domains and paths:

```bash
certbot certificates
```

Expected certificate paths:

```text
/etc/letsencrypt/live/mtdo.cn/fullchain.pem
/etc/letsencrypt/live/mtdo.cn/privkey.pem
```

## 7. Configure Canonical HTTPS Routing

Use three HTTPS server blocks:

1. `mtdo.cn`: retains the complete production proxy, rate limits, security headers, upload size, logs, and application locations.
2. `mt6666.cn`: uses the new dual-domain certificate and returns `301` to `mtdo.cn$request_uri`.
3. `mtcijian.lat` and `www.mtcijian.lat`: use the still-valid old certificate and return `301` to the new primary while old bookmarks are retired.

The alias block is:

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name mt6666.cn;

    ssl_certificate /etc/letsencrypt/live/mtdo.cn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mtdo.cn/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    return 301 https://mtdo.cn$request_uri;
}
```

In the existing application HTTPS block, change only the hostname and certificate paths:

```nginx
server_name mtdo.cn;
ssl_certificate /etc/letsencrypt/live/mtdo.cn/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/mtdo.cn/privkey.pem;
```

Keep the original security headers, rate limits, `client_max_body_size`, logs, `/api/inquiries`, proxy snippet, and catch-all application proxy.

Validate and reload:

```bash
nginx -t
systemctl reload nginx
```

## 8. Update the Application Origin

Edit:

```text
/etc/mt-presence/web.env
```

Set:

```env
MT_PUBLIC_BASE_URL=https://mtdo.cn
```

Restart and wait for readiness:

```bash
systemctl restart mt-presence.service
systemctl is-active nginx mt-presence.service mt-presence-scanner.service
curl -fsS http://127.0.0.1:8131/healthz
curl -fsS http://127.0.0.1:8131/readyz
```

The first request immediately after restart can fail while the process begins listening. Check `systemctl status` and retry after a few seconds before treating it as a deployment failure.

## 9. Update Supabase Auth

In Supabase Dashboard, open `Authentication -> URL Configuration` and set:

```text
Site URL
https://mtdo.cn
```

Allow these redirects:

```text
https://mtdo.cn/auth/verify-email
https://mtdo.cn/auth/reset-password
```

The redirect-only alias does not need to become a second application origin. Existing cookies are scoped to the old domain and do not migrate; users must sign in again on `mtdo.cn`.

## 10. Production Verification

Verify the primary site:

```bash
curl -I https://mtdo.cn
python3 /opt/mt-presence/current/scripts/verify_production.py \
  --base-url https://mtdo.cn
```

Verify the alias preserves paths and query parameters:

```bash
curl -I 'https://mt6666.cn/works.html?ratio=square'
curl -L -I 'https://mt6666.cn/works.html?ratio=square'
```

Expected behavior:

```text
mt6666.cn -> 301 -> https://mtdo.cn/works.html?ratio=square -> 200
```

Verify automatic certificate renewal:

```bash
certbot renew --dry-run
```

If public DNS is still cached incorrectly, test the server's Nginx routing independently:

```bash
curl --resolve mt6666.cn:443:127.0.0.1 \
  -I https://mt6666.cn/works.html
```

## 11. Rollback

If Nginx validation fails, do not reload. Restore the timestamped site file and test again:

```bash
cp -a /etc/nginx/sites-available/mt-presence-v1.1.2.before-domain-<timestamp> \
  /etc/nginx/sites-available/mt-presence-v1.1.2
nginx -t
systemctl reload nginx
```

Restore the previous application environment only when intentionally rolling back the public origin:

```bash
cp -a /etc/mt-presence/web.env.before-domain-<timestamp> \
  /etc/mt-presence/web.env
systemctl restart mt-presence.service
```

After rollback, restore the matching Supabase Auth Site URL and redirect allowlist. DNS, TLS, Nginx, application origin, and Auth callbacks must always describe the same active public origin.
