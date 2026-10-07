# Release Observation 2026-10-07

## Activated release

- Git tag: `v1.6.0`
- Commit: `8fffca6dff25bfff11bb023137112a8e8827ff8a`
- Archive: `mt-presence-v1.6.0.tar.gz`
- Archive SHA-256: `dda25228fb27212fca2198d4fcc87720e6bef7ad583d831e4c688aa4e76e9c45`
- Host: `mtdo.cn` production host (`vultr`, resolved on the observation date as `198.18.0.166`)
- Active release after activation: `/opt/mt-presence/releases/v1.6.0`
- Previous release retained for rollback: `/opt/mt-presence/releases/v1.5.0`

## Pre-activation evidence

- A new PostgreSQL custom dump was created on the production host at
  `/var/backups/mt-presence-pre-release-20261007/mt-presence-20261007T143857Z.dump`.
- The dump passed checksum, catalog, and ACL verification. Its SHA-256 is
  recorded on the host and is not copied into this document.
- The release archive checksum passed before installation. The installer
  rejected no paths or forbidden environment files.
- Web and Scanner production preflight passed with the production environment.
- The release was installed before activation; `v1.5.0` remained the previous
  symlink throughout activation.

## Host-side activation and smoke

- `mt-presence` and `mt-presence-scanner`: active after restart.
- `mt-presence-healthcheck.timer`: active.
- `mt-presence-offsite-backup.timer`: active, but its last service run failed
  while connecting to the configured receiving host on TCP/22.
- `GET http://127.0.0.1:8131/readyz`: HTTP 200 with
  `{"status":"ready","dependencies":{"supabase":"available"}}`.
- `nginx -t`: passed; Nginx reload completed.
- `python3 /opt/mt-presence/current/scripts/verify_production.py --base-url
  https://mtdo.cn`: passed liveness, readiness, public shell/security headers,
  authoritative Works, private-path, protected-route, and CSRF checks.
- Public HTML now references `script.js?v=20261002-public-recovery` and
  `styles.css?v=20261002-public-recovery`; the motion control is present.
- Production auth configuration explicitly enables Google. Apple is hidden in
  the auth and account-linking UI and direct Apple starts return the unavailable
  flow until the provider is configured.

## Observation sample

The Nginx access log contained 2,404 recent requests at observation time. The
recorded `request_time` sample was:

| Statistic | Value |
| --- | ---: |
| p50 | 0.002 s |
| p95 | 0.007 s |
| p99 | 0.4214 s |
| maximum | 7.954 s |

This is a passive production observation, not a capacity test or a Web Vitals
measurement. Disk usage was 56%; the Scanner was continuously reporting idle;
no Web 4xx/5xx entries appeared in the last one-hour journal sample.

## External acceptance status

- SMTP credentials on the production host authenticated successfully against
  the configured QQ SMTP service. No test message was sent from this release
  observation, so mailbox receipt, templates, OTP expiry, resend, and reset
  flows remain unverified.
- Google OAuth reached the Google authorization page through Supabase. A real
  disposable account sign-in, cancellation, repeat sign-in, sign-out, MFA, and
  identity linking flow still requires an operator-controlled account.
- Apple OAuth is intentionally disabled until its Supabase provider setup and
  real account test exist.
- The repository has no safe production load harness. A staging or isolated
  target, traffic target, dataset, and pass threshold are required before a
  p95/capacity result can be called complete.
- The local health timer and offsite failure alert contract are installed, but
  the offsite receiving host was unreachable during this observation and the
  receiver-side verify timer is not installed on the application host. The
  failed backup remains an active operations blocker.
- `assets/art/` AI images and `assets/archive/` Picsum samples remain clearly
  labelled temporary. Final author material or written authorization with
  provenance, license/consent, and per-file SHA-256 records is still required.

## Rollback reference

The previous release remains installed at `/opt/mt-presence/releases/v1.5.0`.
The documented rollback command is:

```bash
MT_ALLOW_ROLLBACK=yes python3 /tmp/manage_production_release.py \
  --root /opt/mt-presence rollback
```

Rollback must be followed by Web/Scanner restart and the same host-side smoke
check. Database changes were not part of `v1.6.0`.
