# Offsite recovery rehearsal - 2026-09-17

This record contains no credential, private key, recovery passphrase, signed URL, database row, or Storage object name.

## Result

The production offsite backup and application-level recovery rehearsal passed.

- The source created a PostgreSQL custom-format dump and exported 165 allowlisted Storage objects totaling 44,042,883 bytes.
- The source encrypted the batch before transfer. The receiver verified the ciphertext checksum and atomically promoted one mode-`0600`, root-owned batch into the root-only vault.
- The recovery workstation reconstructed the private key from the macOS Keychain, verified the receiver checksum, decrypted the batch in a mode-`0700` temporary directory, rejected unsafe archive paths, and verified every entry in `FILES.sha256`.
- The Storage inventory, object tree, and JSONL manifest verified 165 objects and 44,042,883 bytes.
- The database dump checksum, catalog, ownership entries, and ACL entries passed verification.
- The dump restored atomically into a guarded, loopback-only disposable Supabase database with source-equivalent roles. Evidence included 3 application schemas, 59 tables, 123 public functions, 32 RLS tables, 30 policies, 260 relevant ACL rows, 270 Auth users, 270 application users, 55 images, and 165 Storage object rows.
- The recovered database was attached only to the disposable local Supabase stack. Auth, REST, Storage, Realtime, metadata, and gateway services reached healthy state.
- One backed-up object whose original metadata existed in the recovered database was uploaded to a private `recovery-rehearsal` bucket, downloaded through the local Storage API, and matched by byte count and SHA-256. After that focused proof, all 165 objects were restored and verified so the recovered Works application could render its complete asset set.
- The five rollback-only database acceptance groups passed against a data-free schema clone of the recovered database with the required bucket definitions; every fixed fixture was confirmed absent after the tests.
- The local gateway, PostgreSQL, and mail-capture ports were rebound from all interfaces to `127.0.0.1`; loopback access and application readiness passed while the workstation LAN address could no longer reach the recovery gateway.
- Production was never used as a restore target. The receiver retained ciphertext only, and the source retained its encrypted local copy.

## Findings fixed during the rehearsal

- The recovery runner now recreates an empty `public` schema after clearing the disposable target. Supabase dumps assume that schema already exists and do not necessarily contain `CREATE SCHEMA public`.
- The disposable target must provide source-equivalent Supabase roles. Preserving object ownership is required for Auth and Storage migrations; flattening all ownership to one restore role is not an application-valid recovery.
- A newer local Realtime container requires an empty `_realtime` schema when restoring a backup created by an environment that used the legacy `realtime` schema. This compatibility schema was added only to the disposable recovery environment.

## Operations state

- Production backup timer: enabled and active.
- Receiver verification timer: enabled and active.
- Latest source backup service result: success.
- Latest receiver verification service result: success.
- Production and receiver SSH: public-key authentication required; root password and keyboard-interactive login disabled.
