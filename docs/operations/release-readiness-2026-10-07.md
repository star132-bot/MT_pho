# Release Readiness Review 2026-10-07

This record is the ownership review for the uncommitted work that was present in
the MT Presence checkout before the release was prepared. It keeps historical
operations work separate from the October public-site optimization while keeping
both sets in the same reviewed release line.

## Change ownership

| Group | Files | Disposition |
| --- | --- | --- |
| Public-site optimization, 2026-10-02 | HTML shells, `script.js`, public archive/lightbox/work scripts, `styles.css`, `server.py`, public delivery and browser tests | Included in the release. Covers layout stability, motion controls, authoritative API failures, timeout/retry behavior, storage failure recovery, and public browser evidence. |
| Backup and recovery hardening, 2026-08-13 | `deploy/mt-presence-offsite-*`, `deploy/offsite-*`, SSH hardening, backup/export/verification/alert scripts and their tests | Included in the release. The services remain separately installed on the source and receiving hosts. No credentials are included. |
| Recovery rehearsal, 2026-09-17 | `docs/operations/offsite-recovery-rehearsal-2026-09-17.md`, recovery runner and boundary test | Included in the release contract. The rehearsal targets an isolated recovery project and never the production primary. |
| Module and system specifications, 2026-09-29 | `docs/module-specs/`, `docs/operations/website-optimization-process.md`, architecture and operations updates | Included as product and operational documentation. The specifications describe implemented boundaries and explicitly mark external acceptance requirements. |
| Historical planning notes | `MT_Presence_Server_Production_Optimization_Prompt.md`, `MT_Presence_Weekly_Development_Report_2026-07-23_to_2026-07-29.md` | Included as historical project records; they do not provide production acceptance evidence. |

The review found no `.env`, `.env.worker`, database dump, ignored upload,
browser profile, or generated cache in the release set. The ignored local
Pexels derivatives and SQLite databases remain outside Git.

## Release evidence

- `bash scripts/release_gate.sh` passed before this review and is rerun after the
  release commit.
- `python3 scripts/test_public_browser.py` passed at 1440x900, 1024x768, and
  390x844 against an isolated loopback fixture.
- Database acceptance and recovery rehearsal evidence use development or
  disposable isolated targets. They never write fixtures to the production
  primary.
- The release builder requires both a clean worktree and an exact Git tag. The
  archive checksum is generated beside the archive.

## External acceptance status

The following require credentials or infrastructure outside this checkout and
must be recorded with an operator timestamp before they are called complete:

1. A real external mailbox must receive and consume registration, verification,
   resend, recovery, expiry, and one-time-use messages. The local QQ SMTP
   endpoint currently closes the TLS session before an SMTP banner, so no
   message was sent from this workstation.
2. Google OAuth starts through Supabase. Apple is deliberately disabled in the
   production example until its Supabase provider configuration and a real
   account flow are completed; the UI hides it and the server rejects it when
   it is not in `MT_ENABLED_OAUTH_PROVIDERS`.
3. Capacity and p95 measurements require a staging or isolated service with an
   agreed request rate, concurrency, dataset, and pass threshold. Local browser
   samples are not production capacity evidence.
4. An external `/healthz` monitor and a trusted `/readyz` monitor must have a
   tested alert and recovery delivery path. The repository contains the local
   health timer and offsite failure alert contract, but installing and testing
   the production timers requires host access.
5. The AI and Picsum files remain labelled as temporary visual samples. Final
   author material or written authorization, with per-file provenance and
   SHA-256 records, is required before they can be described as MT works.

## Current release decision

The code and documentation are ready to be committed and tagged. Production
activation remains conditional on the external acceptance items above and on a
successful host-side readiness/smoke check immediately after activation.
