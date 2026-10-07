# Release Observation 2026-10-07: v1.6.1

## Release scope

- Git tag: `v1.6.1`
- Release type: documentation and release-contract closure
- Runtime baseline: `v1.6.0` (`8fffca6dff25bfff11bb023137112a8e8827ff8a`)
- Host: `mtdo.cn` production host
- Previous release retained for rollback: `v1.6.0`

This release records the reviewed worktree ownership, the production observation
and the remaining external acceptance gates. It contains no database migration
and no runtime behavior change beyond the already activated `v1.6.0` release.

## Local release evidence

- The worktree was reviewed for ownership before commit. Ignored environments,
  credentials, local databases, uploads, browser profiles and generated output
  were excluded from the release set.
- `git diff --check` passed.
- `bash scripts/release_gate.sh` passed, including syntax, static contracts,
  boundary tests, production-tool tests, backup/alert/recovery contracts and
  patch integrity.
- The release builder created a clean exact-tag archive and checksum.

## Production evidence

- `v1.6.1` was installed and activated at
  `/opt/mt-presence/releases/v1.6.1` on `mtdo.cn`.
- `v1.6.0` remains installed as the previous release for atomic rollback.
- Web, Scanner and the local readiness timer are active. `GET
  http://127.0.0.1:8131/readyz` returned HTTP 200 with Supabase available.
- Nginx configuration test and reload passed.
- `scripts/verify_production.py --base-url https://mtdo.cn` passed liveness,
  readiness, public shell/security headers, authoritative Works, private-path,
  protected-route and CSRF checks.
- The earlier passive observation remains in
  `release-observation-2026-10-07.md`: 2,404 recent requests measured p50
  0.002s, p95 0.007s, p99 0.4214s and maximum 7.954s. This is not a capacity
  test.

## External acceptance gates

These are still open because they require external accounts, infrastructure or
source material that is not present in the repository:

1. SMTP needs an operator-controlled mailbox test covering registration,
   verification, resend, expiry, one-time-use and password recovery. SMTP
   credential authentication passed; mailbox delivery was not claimed.
2. Google OAuth needs a real operator-controlled account test covering consent,
   cancellation, repeat login, logout, MFA and identity linking. Apple remains
   intentionally hidden and disabled until its provider credentials and real
   account flow are configured.
3. Capacity requires an isolated staging/recovery target, agreed traffic,
   concurrency, dataset and p95/p99 thresholds. Production passive logs cannot
   establish capacity.
4. Continuous monitoring requires an external `/healthz` and trusted `/readyz`
   alert path with recovery delivery evidence. The local readiness timer passed.
5. The configured offsite receiver at `8.160.170.69:22` timed out during the
   latest backup. The receiving host verify unit is not installed on the
   application host, so offsite backup and restore acceptance remain open.
6. `assets/art/` AI images and `assets/archive/` Picsum samples remain
   temporary. Final author works or written authorization with provenance,
   license/consent and per-file SHA-256 records are required before formal
   publication.

## Rollback

The application rollback remains an atomic symlink swap to the previous release:

```bash
MT_ALLOW_ROLLBACK=yes python3 /tmp/manage_production_release.py \
  --root /opt/mt-presence rollback
```

After rollback, restart Web/Scanner and rerun the same host-side smoke check.
