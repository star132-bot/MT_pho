# Offsite recovery rehearsal - 2026-08-13

This is an evidence record, not a claim that MT Presence has completed an application-level disaster recovery exercise. It contains no credential, private key, recovery passphrase, signed URL, database row, or Storage object name.

## Recovery point

- Batch: `mt-presence-offsite-20260813T022433Z`
- Backup format: `mt-presence-offsite-v1`
- PostgreSQL artifact: one custom-format dump, 962,173 bytes
- Storage artifact: 165 objects, 44,042,883 bytes
- Storage buckets represented: `image-originals`, `image-display`, `image-thumbnails`, and `profile-avatars`
- Receiving-vault free space after promotion: 69 percent

## Passed checks

1. The source created and catalog-verified the PostgreSQL dump before packaging it.
2. Storage inventory was identical before and after export; all 165 downloaded objects matched their declared sizes and generated SHA-256 values.
3. The source encrypted the complete batch to the dedicated recovery public key before transfer. No plaintext batch was transferred.
4. The source-IP-bound write-only account placed the ciphertext pair in `incoming`; the target verifier checked owner, mode, filename, SHA-256, freshness, and disk floor before atomically promoting it to the root-only vault.
5. The receiver account could not traverse or read the promoted vault batch.
6. The recovery private key was reassembled from versioned macOS Keychain chunks, matched its manifest byte count and SHA-256, imported into a new root-only temporary GnuPG home, and decrypted the real vault ciphertext.
7. The decrypted tar contained 345 regular-file/directory entries and no link, device, socket, FIFO, absolute path, or parent traversal entry.
8. `FILES.sha256` validated every extracted file. The Storage verifier independently recomputed all 165 object hashes and 44,042,883 bytes.
9. An isolated, no-network, read-only PostgreSQL client container read the decrypted dump catalog: 132 table entries, 174 function entries, eight schemas, and the expected Supabase extension dependencies.
10. All target-host private-key copies, passphrase files, decrypted tar files, database dumps, and extracted Storage objects created by the rehearsal were removed. The source retains only the recovery public key; the target retains only ciphertext and its checksum.

## Intentionally not performed

The dump came from Supabase PostgreSQL 17 and depends on managed components including `supabase_vault`, `pgcrypto`, `pg_stat_statements`, and `uuid-ossp`. The receiving host only has a standard PostgreSQL 18 image and also runs an unrelated production workload. The rehearsal therefore did not restore into that host's existing database and did not upload an object into a production bucket.

Before application-level disaster recovery can be declared complete, provision an isolated disposable Supabase-compatible project, restore this dump there, restore one object under a disposable non-production bucket, and verify the database/Storage relationship through the application. Never run that exercise against MT Presence production or the receiving host's unrelated database.

## Custody state

- GPG recovery fingerprint: `866D9EF69E08A2782B7E06956A2CA8750146D18F`
- The encrypted private key is held in versioned, chunked macOS login-Keychain items managed by `scripts/macos_offsite_recovery_keychain.py`.
- The recovery passphrase is a separate Keychain item and is not stored in Git or on either server.
- The current Keychain private-key manifest records 28 chunks and 1,950 decoded bytes. Its integrity is checked before every export.
- A second offline/hardware-backed custody copy remains an operations requirement; one workstation Keychain is not a complete key-escrow policy.
