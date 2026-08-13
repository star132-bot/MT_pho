# MT Presence Production Deployment

## Purpose

This runbook promotes one reviewed Git tag to a single Linux host without copying local secrets or editing the active release in place. PostgreSQL and object storage remain authoritative in Supabase. Nginx terminates TLS and proxies only to the loopback Web process. The image scanner runs as a separate, more privileged Unix identity.

This is a future production procedure, not a record of an existing production deployment. The current project deployment boundary is development until every gate below is completed and an approved release is activated.

Do not use the server's root password in scripts, command arguments, repository files, shell history, or service environment files. Establish an SSH key before routine deployment and disable password login only after key access is verified in a second session.

## Release gates

A production release is blocked until all of the following are true:

- The requested product scope is accepted at `1440x900`, `1024x768`, and `390x844`.
- The release gate, security boundary tests, and browser smoke tests pass; development-only database rollback tests pass on development or an isolated staging/restored clone, never on the production primary.
- The Git worktree is clean and the selected commit has an exact release tag.
- A current database backup exists and its SHA-256 manifest is stored separately.
- Restore has been rehearsed against a disposable database, never directly against production.
- The exact public domain is configured in `MT_PUBLIC_BASE_URL` and in the Supabase Auth redirect allowlist.
- HTTPS certificate issuance succeeds before secure authentication cookies are enabled.
- Supabase Confirm Email is enabled; a domain-authenticated custom SMTP sender and first-party verification/recovery templates pass real external-mailbox delivery, expiry, one-time-use, and resend tests.
- When Google or Apple sign-in is enabled, each provider is configured in Supabase Auth and its provider console uses the Supabase callback URL shown by the provider panel. Supabase allows the exact `https://<domain>/auth/oauth/callback` application return URL, and a real account for each enabled provider passes sign-in, cancellation, first-account creation, repeat sign-in, sign-out, and Admin MFA acceptance. Account Settings identity linking and unlinking must also be verified without removing the final sign-in method.
- Web and scanner secrets are separated as described below.
- An external uptime check watches `/healthz`; an authenticated operational check watches `/readyz` from a trusted location.

## Host layout

```text
/opt/mt-presence/
  current -> releases/<release-id>
  previous -> releases/<release-id>
  releases/
/etc/mt-presence/
  web.env
  scanner.env
  database.env       # used only by an operator during migrations/backups
/var/lib/mt-presence/
/var/lib/mt-presence-scanner/
```

Create separate locked service accounts:

```bash
useradd --system --home /var/lib/mt-presence --shell /usr/sbin/nologin mtpresence
useradd --system --home /var/lib/mt-presence-scanner --shell /usr/sbin/nologin mtpresence-scanner
install -d -o mtpresence -g mtpresence -m 0750 /var/lib/mt-presence
install -d -o mtpresence-scanner -g mtpresence-scanner -m 0700 /var/lib/mt-presence-scanner
install -d -o root -g root -m 0755 /opt/mt-presence/releases
install -d -o root -g root -m 0750 /etc/mt-presence
```

The host needs Python 3.11+, Nginx, PostgreSQL client tools, Certbot or an equivalent ACME client, ClamAV with current signatures, and a dedicated scanner virtual environment installed from `requirements-scanner.txt` with `--require-hashes`.

## Secret boundary

`/etc/mt-presence/web.env`, mode `0640`, owner `root:mtpresence`:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `MT_RUNTIME_ENVIRONMENT=production`
- `MT_COOKIE_SECURE=1`
- `MT_TRUST_PROXY=1`
- `MT_MAX_REQUEST_THREADS=32`
- `MT_PUBLIC_BASE_URL=https://<domain>`
- `MT_AUTH_EMAIL_RATE_LIMIT_PER_HOUR=6`
- bounded inquiry rate configuration

It must not contain `PGPASSWORD`, `SUPABASE_SECRET_KEY`, or `SUPABASE_SERVICE_ROLE_KEY`.

Google OAuth Client ID/Secret and Apple Service ID/Key are stored only in **Supabase Dashboard > Authentication > Sign In / Providers** under their respective providers. Each provider console's authorized redirect URI is the Supabase callback (`https://<project-ref>.supabase.co/auth/v1/callback`), not the MT Presence callback. The exact MT Presence callback (`https://<domain>/auth/oauth/callback`) belongs in **Supabase Authentication > URL Configuration > Redirect URLs**. Do not place any provider credential in `web.env`, source control, browser storage, screenshots, or support messages.

`/etc/mt-presence/scanner.env`, mode `0640`, owner `root:mtpresence-scanner`, contains only the scanner runtime values and its isolated Supabase secret. It must define `MT_SCANNER_ID`, `MT_SCANNER_CLAMAV_COMMAND` (normally `clamdscan --stream --no-summary`), and a writable `MT_SCANNER_TEMP_DIR` below `/var/lib/mt-presence-scanner`; `MT_SCANNER_WORKER_ID` is not a supported variable. The hardened Scanner unit creates a mount namespace through `PrivateDevices`, `PrivateTmp`, and `ProtectSystem`; production therefore streams file contents to the resident daemon. Do not configure `clamdscan --fdpass`: clamd cannot validate a file descriptor passed across that namespace boundary. Standalone `clamscan` remains accepted for operators that intentionally provision enough memory, but it reloads signatures for every asset and is unsuitable for the default low-memory deployment. Development may still use `clamdscan --fdpass` when it runs without that systemd isolation.

`/etc/mt-presence/database.env`, mode `0600`, owner `root:root`, contains PostgreSQL deployment/backup credentials. No systemd Web or scanner unit reads this file.

## Authentication email templates

In Supabase Dashboard, open **Authentication > Emails > Templates > Reset Password**. The recovery template must render `{{ .Token }}` as the one-time recovery code. MT Presence currently validates the provider's eight-digit code, then creates a restricted recovery session that can only reach `/auth/reset-password` until the password is changed.

Do not make `{{ .ConfirmationURL }}` the primary recovery action. Mail clients and security scanners can prefetch a clickable confirmation link before the user opens it, consuming a one-time link and producing an invalid-or-expired page. The legacy link callback remains supported for compatibility, but production acceptance must exercise the code path from an external mailbox. Never place the OTP, token hash, or confirmation URL in application logs, analytics, or support screenshots.

## Database migration and backup

Create a backup before applying migrations:

```bash
set -a
source /etc/mt-presence/database.env
set +a
MT_BACKUP_DIR=/var/backups/mt-presence bash scripts/backup_production_database.sh
bash scripts/verify_production_backup.sh /var/backups/mt-presence/<backup.dump>
```

Before changing production, restore that verified backup into an access-restricted disposable staging or recovery clone with dedicated non-production credentials. Apply the exact candidate migrations to the clone without replaying the baseline:

```bash
set -a
source /secure/path/acceptance-clone.env
set +a
MT_DEPLOY_ENVIRONMENT=staging \
MT_APPLY_PHASE1_BASELINE=no \
bash scripts/deploy_supabase_phase1.sh
```

Run the rollback-only database acceptance suite only against this fixture-safe clone or development. The Python runners require `MT_TEST_ENVIRONMENT=development` and reject `MT_ALLOW_PRODUCTION=yes`; raw SQL acceptance files have the same operational restriction even where they cannot enforce it themselves. Confirm fixture absence afterward. Never source `/etc/mt-presence/database.env` for these tests, point test `PG*` values at the production primary, or treat transaction rollback as permission to test production.

```bash
MT_TEST_ENVIRONMENT=development bash scripts/database_acceptance_gate.sh
```

Only after clone migration and acceptance pass should an operator migrate the production database. For an existing production database, never reapply the non-idempotent baseline:

```bash
set -a
source /etc/mt-presence/database.env
set +a
MT_DEPLOY_ENVIRONMENT=production \
MT_ALLOW_PRODUCTION=yes \
MT_APPLY_PHASE1_BASELINE=no \
bash scripts/deploy_supabase_phase1.sh
```

After the production migration, use read-only catalog/schema inspection and the HTTPS smoke check below. Do not run fixture-writing database acceptance against production. Any approved signed-in production smoke uses dedicated disposable test identities, never customer identities.

Object storage is not contained in a PostgreSQL dump. Before go-live, configure a separate encrypted export or provider-supported recovery policy for original and derivative Storage buckets, document its retention, and rehearse restoring a disposable object plus its database metadata.

## Encrypted offsite database and Storage backup

The offsite batch is a second recovery copy, not a database replica and not a failover application host. It includes one verified PostgreSQL custom-format dump plus every object currently recorded in the allowlisted private buckets `image-originals`, `image-display`, `image-thumbnails`, and `profile-avatars`. The source queries the Storage inventory before and after download and discards the whole batch if bucket, key, size, or `updated_at` changes during the export. This prevents a database dump from being presented as matching a visibly different object set.

The receiving host must use a dedicated filesystem boundary and account. It must not receive `database.env`, `scanner.env`, Supabase credentials, the Web release, or plaintext backup data. Generate a dedicated source-host SSH key and constrain its public key on the receiving host to the source IP and append-only `rrsync` command:

```text
from="<source-ip>",restrict,command="/usr/bin/rrsync -wo -no-del -munge /srv/mt-presence-backup" ssh-ed25519 <dedicated-public-key>
```

Create `/srv/mt-presence-backup` as `root:mtpresence-backup` mode `0750`; `rrsync` needs to open this boundary for its per-user lock. Create its `incoming` child as mode `0700`, owned by the unprivileged `mtpresence-backup` account. Create the sibling `vault` and `.staging` directories as root-only mode `0700`; the receive account must not have traversal access to either directory. Keep its login shell only because OpenSSH runs the forced command through that shell; the key cannot request a TTY, forwarding, arbitrary command, read, delete, or follow useful symlinks. Keep normal administrative SSH access on a different reviewed key.

Create a dedicated GnuPG recovery key in a temporary root-only keyring and transfer **only its armored public key** to the source host. Import that public key into `/var/lib/mt-presence-offsite/gnupg`, record its full fingerprint in `/etc/mt-presence/offsite-backup.env`, and keep both paths root-only. Move the private recovery material into a separate offline/keychain recovery authority and remove it from both servers after the first decryption rehearsal. The receiving account cannot access the private key. Do not put recovery material in Git, a shell command, a screenshot, or either server's long-lived filesystem.

On the approved macOS recovery workstation, use the chunked helper rather than passing a long private key to `security -w`; the interactive Keychain CLI may silently truncate long values. The helper reads the key on stdin, writes 96-character versioned chunks, and verifies a separate byte-count/SHA-256 manifest before any export. Store the passphrase in a different Keychain item and never redirect helper `export` output to an ordinary local file:

```bash
gpg --homedir <temporary-root-only-gnupg-home> \
  --batch --yes --pinentry-mode loopback \
  --passphrase-file <temporary-root-only-passphrase-file> \
  --export-secret-keys <full-fingerprint> \
  | python3 scripts/macos_offsite_recovery_keychain.py store \
      --fingerprint <full-fingerprint>

python3 scripts/macos_offsite_recovery_keychain.py audit \
  --fingerprint <full-fingerprint>
```

For an approved recovery, stream the verified export directly through SSH into a new root-only temporary recovery directory. Import it into a new temporary GnuPG home, verify the full fingerprint, decrypt one selected vault batch, and remove all temporary material after the exercise. Keep a second hardware-backed or encrypted-offline custody copy; the workstation login Keychain alone is not sufficient escrow.

Install the source scripts under `/usr/local/libexec/mt-presence-offsite`, then install and enable the source service and timer:

```bash
install -d -o root -g root -m 0755 /usr/local/libexec/mt-presence-offsite
install -o root -g root -m 0755 scripts/create_offsite_backup.sh scripts/backup_production_database.sh scripts/verify_production_backup.sh /usr/local/libexec/mt-presence-offsite/
install -o root -g root -m 0755 scripts/export_production_storage.py /usr/local/libexec/mt-presence-offsite/
install -o root -g root -m 0644 deploy/mt-presence-offsite-backup.service deploy/mt-presence-offsite-backup.timer /etc/systemd/system/
install -o root -g root -m 0600 deploy/offsite-backup-environment.example /etc/mt-presence/offsite-backup.env
systemctl daemon-reload
systemctl enable --now mt-presence-offsite-backup.timer
```

The source service is the only process that reads both `/etc/mt-presence/database.env` and `/etc/mt-presence/scanner.env`. It runs as root with `ProtectSystem=strict`, gives libpq a dedicated `HOME=/var/lib/mt-presence-offsite` instead of exposing `/root`, writes only below `/var/backups/mt-presence-offsite` and `/var/lib/mt-presence-offsite`, uses a pinned target host key, stores no credential in command arguments, and gives backup work low CPU/IO priority. Each successful run leaves a local encrypted `.tar.gpg` plus its checksum and transfers the same pair to `incoming/`; plaintext staging is removed on exit.

Install `scripts/verify_offsite_ciphertexts.sh` and the two target verification units on the receiving host. The daily hardened root verifier accepts only timestamped mode-`0600` pairs, copies each complete pair into a root-only staging directory, verifies its checksum, and atomically renames the directory into the root-only vault before deleting the receive copy. Its systemd sandbox retains only `CAP_DAC_OVERRIDE`, which is required to read and remove files in the receiver-owned mode-`0700` incoming directory; it has no network access and cannot gain new privileges. A compromised source key therefore cannot read, overwrite, or delete any promoted recovery point. The same job rechecks every vault checksum, rejects unexpected entries, fails when the newest batch is older than 36 hours, and fails below the configured free-space floor. Wire systemd failure to the operations alert channel; a failed timer without an alert is not a backup system.

Run the first source service manually and require all of these before relying on the schedule:

```bash
systemctl start mt-presence-offsite-backup.service
systemctl status mt-presence-offsite-backup.service --no-pager
systemctl start mt-presence-offsite-verify.service
systemctl status mt-presence-offsite-verify.service --no-pager
```

For a recovery rehearsal, choose one root-only vault batch, verify its ciphertext checksum on the receiving host, decrypt it in a root-only temporary directory with the offline recovery key, extract it without following links, run `sha256sum --check FILES.sha256`, run `scripts/verify_production_backup.sh` against the dump, and run `scripts/export_production_storage.py verify` against the included inventory/object tree/manifest. Restore the database into a disposable isolated PostgreSQL project and restore one disposable object under a non-production bucket before declaring the rehearsal complete. Never restore over production and never use the target host's existing application database as the rehearsal destination.

The first cryptographic/content rehearsal is recorded in `docs/operations/offsite-recovery-rehearsal-2026-08-13.md`. It proves ciphertext decryption, archive safety, every file hash, Storage object integrity, and PostgreSQL catalog readability. It does **not** replace the outstanding full restore into a disposable Supabase-compatible project.

Do not automatically delete offsite batches until an approved retention policy and monitoring threshold exist. With append-only transfer, cleanup is an explicit receiving-host operation. Start with at least 30 daily recovery points, review growth monthly, and preserve any legal-hold or incident batch independently of routine retention.

## Build and transfer

Run the release gate locally, commit the accepted tree, and create an exact release tag. The builder refuses dirty or untagged releases:

```bash
bash scripts/release_gate.sh
git tag -a v1.1.0 -m "MT Presence v1.1.0"
MT_RELEASE_APPROVED=yes bash scripts/build_production_release.sh v1.1.0
```

Transfer the archive, checksum, and the two reviewed release-tool files through SSH. Keep `manage_production_release.py` beside `production_release_contract.py`; the shared contract prevents runtime preflight and archive installation from using different release manifests. Do not transfer `.env`, `.env.worker`, `.git`, browser profiles, test screenshots, or local SQLite data.

On the server, compare the checksum file through a trusted channel, then install without activating:

```bash
python3 /tmp/mt-presence-release-tools/manage_production_release.py \
  --root /opt/mt-presence \
  install \
  --archive /tmp/mt-presence-v1.1.0.tar.gz \
  --sha256 <verified-sha256> \
  --release-id v1.1.0
```

The installer rejects path traversal, links, devices, named pipes, missing application files, embedded environment files, duplicate release IDs, and checksum mismatches.

## Services and TLS

Install the templates:

```bash
install -o root -g root -m 0644 deploy/mt-presence.service /etc/systemd/system/mt-presence.service
install -o root -g root -m 0644 deploy/mt-presence-scanner.service /etc/systemd/system/mt-presence-scanner.service
install -o root -g root -m 0644 deploy/mt-presence-healthcheck.service /etc/systemd/system/mt-presence-healthcheck.service
install -o root -g root -m 0644 deploy/mt-presence-healthcheck.timer /etc/systemd/system/mt-presence-healthcheck.timer
install -o root -g root -m 0644 deploy/nginx-proxy.conf /etc/nginx/snippets/mt-presence-proxy.conf
```

Replace every `__DOMAIN__` marker in `deploy/nginx-mt-presence.conf`, install the result in Nginx's enabled HTTP context, issue the certificate, and run `nginx -t` before reload. The access log format records the path but not query data, protecting verification and recovery links.

Activate the installed release atomically:

```bash
python3 /tmp/mt-presence-release-tools/manage_production_release.py --root /opt/mt-presence activate --release-id v1.1.0
systemctl daemon-reload
systemctl restart mt-presence mt-presence-scanner
systemctl enable --now mt-presence-healthcheck.timer
systemctl reload nginx
```

Both services run without root privileges, without Linux capabilities, with a read-only operating system view and separate writable directories. If either runtime preflight fails, systemd refuses to start that process.

## Verification

Run the read-only automated smoke check through the public HTTPS origin:

```bash
python3 scripts/verify_production.py --base-url https://<domain>
```

The verifier checks public boundaries through HTTPS and checks the protected `/readyz` provider probe through `http://127.0.0.1:8131` by default. Run it on the application host; do not expose `/readyz` anonymously through Nginx.

After an explicitly approved activation, complete these signed-in checks with disposable production-test identities. These checks do not include the rollback-only database fixture suite:

1. Register, verify, sign in, sign out, recover, and complete Admin MFA.
2. Upload one non-sensitive test image; verify scanner completion, readiness, submit, review, publish, public delivery, takedown, and restore.
3. Submit one guest inquiry and one authenticated inquiry. Verify recipient notification, unread/read behavior, Inbox isolation, reply versioning, and truthful guest delivery status.
4. Suspend and reactivate a disposable User. Grant and revoke Reviewer with a disposable Super Admin session.
5. Verify the audit ledger records the inquiry reply and governance actions without exposing email, auth subject, raw states, Storage coordinates, tokens, or IP addresses.
6. Verify Home, Works, creator profile, Contact, Notifications, Inbox, and Admin Audit at desktop and mobile widths.
7. Confirm Nginx and systemd logs contain request IDs and paths but no query strings, cookies, tokens, inquiry bodies, or passwords.

## Rollback

Application rollback is an atomic symlink swap and does not modify the database:

```bash
MT_ALLOW_ROLLBACK=yes python3 /tmp/manage_production_release.py --root /opt/mt-presence rollback
systemctl restart mt-presence mt-presence-scanner
python3 /opt/mt-presence/current/scripts/verify_production.py --base-url https://<domain>
```

Database rollback is not an automatic down migration. Stop writes, preserve the failed database, and restore the verified pre-migration dump into a new recovery database or project. Point the application to the recovered provider only after integrity and Storage references pass acceptance. Record the incident and every operator action in the release log.

## Production observation

For the first hour after activation, watch Nginx 4xx/5xx rate, Web and scanner restarts, `/readyz`, scanner queue age, failed inquiry creates, failed replies, and audit failure events. Keep the previous release installed until the observation window and backup verification both pass.
