# MT Presence

MT Presence is a fine art photography portfolio and image-workflow prototype. Version `v1.0.0` started as a static first version; the current workspace combines the public gallery, a legacy SQLite Review prototype, and a Supabase-backed account and private Draft workspace.

## Current Version

- Version: `1.0.0`
- Release label: `v1.0.0`
- Status: public frontend, server-managed Supabase Auth/Account, and Phase 2A-2F private Workspace slices
- Database: Phase 0/1 plus the Phase 2A-2F Workspace migrations form the development boundary; public Works and the legacy Review Center still read SQLite while the Supabase Review Queue/Publish path remains the next slice

## Features

- Sticky homepage hero transition from abstract black-and-white scenery to concrete color scenery.
- Infinite horizontal selected works gallery.
- Four-moment image-led Statement section, placed after Selected Works, with one image per text passage and a final Enter Works call to action.
- Works Archive page with read-only local SQLite API data when `data/archive.db` exists, with local photography sample fallback.
- Works Archive work viewer with full-screen enlarged images, fit/actual-size zoom, catalog-style metadata, keyboard navigation, and grouped visual tags.
- Internal Works Viewer Editor for importing works; maintaining the viewer title, series, notes, metadata, visibility, sort order, and grouped tags; and editing homepage hero images/text in the IndexedDB transition layer.
- Upload flow that reads original image dimensions, checksum, and basic EXIF in the browser.
- Local multi-version image asset generation for uploads: original, display, thumbnail, and square slices.
- Automatic ratio classification: `1:1`, `4:3`, `4:5`, `2:3`, `3:2`, `16:9`, `Panorama`.
- Abstract and Concrete filters.
- Arrange mode for ordering Works Archive items, with drag controls, Earlier/Later buttons, and local order persistence.
- Browser-local Lightbox for saving works and carrying a selection into a structured inquiry.
- About page for the artist practice and availability.
- Protected Upload Studio with server-authoritative Supabase Folders and Drafts, a two-worker upload queue, per-item Cancel/Retry/Remove controls, owner-scoped signed uploads to three private Storage buckets, canceled-object cleanup, 900 ms debounced Draft autosave, version-conflict recovery, five-check submission readiness, idempotent Submit for Review, soft-delete Trash actions, and read-only IndexedDB offline cache.
- Independent trusted asset scanner with restricted leased jobs, private Storage streaming, SHA-256/magic/MIME checks, ClamAV malware detection, isolated Pillow full decoding, bounded retries, append-only scan events, and fail-closed current-policy readiness updates.
- Contact Artist page linked from the homepage and Works Archive page.
- Supabase Register/Verify/Sign In/Sign Out/Forgot/Reset flow with HttpOnly session cookies, CSRF protection, owner isolation, and Admin MFA guards.
- Protected Account Settings for profile/authorship preferences, verified account state, current-session description, and provider-supported bulk session revocation.
- Local SQLite archive seed, Archive read/write metadata API, and automated validation workflow for checking image metadata, assets, grouped tags, collections, and Archive view output before backend integration.

## Run Locally

The Web application has no package install step. The independent trusted scanner targets Python 3.11, installs a hash-locked Pillow dependency, and requires a healthy ClamAV installation.

Use the local static server:

```bash
python3 server.py --port 8131
```

Then open:

```text
http://127.0.0.1:8131/
```

Works Archive:

```text
http://127.0.0.1:8131/works.html
```

Lightbox and About:

```text
http://127.0.0.1:8131/lightbox.html
http://127.0.0.1:8131/about.html
```

Internal Works Viewer Editor:

```text
http://127.0.0.1:8131/manage.html
```

Personal Upload Studio:

```text
http://127.0.0.1:8131/workspace/images
```

Authentication foundation:

```text
http://127.0.0.1:8131/auth/sign-in
http://127.0.0.1:8131/auth/register
http://127.0.0.1:8131/auth/forgot-password
http://127.0.0.1:8131/auth/reset-password
```

Protected account settings:

```text
http://127.0.0.1:8131/settings/account
```

Copy `.env.example` values into your local environment before starting the server. Set `MT_PUBLIC_BASE_URL` to the exact browser origin and add `/auth/verify-email` plus `/auth/reset-password` to the Supabase Auth redirect allowlist. The auth routes use Supabase Auth through the server, keep access/refresh tokens in `HttpOnly` cookies, require a same-origin CSRF token for mutations, and never use browser storage for credentials. `/workspace/images` is protected, direct `/upload-studio.html` requests canonicalize to it, and Admin/Super Admin sessions require AAL2 before opening or mutating the Workspace.

For a fresh development database, apply the Phase 0/1 baseline and all incremental migrations:

```bash
bash scripts/deploy_supabase_phase1.sh
```

For an existing Phase 1 database, skip the non-idempotent baseline and apply only the ordered incremental migrations:

```bash
MT_APPLY_PHASE1_BASELINE=no bash scripts/deploy_supabase_phase1.sh
```

Run the trusted scanner in its own environment; never source scanner secrets into `server.py`:

```bash
python3 -m venv .venv-scanner
.venv-scanner/bin/python -m pip install --require-hashes -r requirements-scanner.txt
set -a
source .env.worker
set +a
.venv-scanner/bin/python workers/image_scanner.py --once
```

`SUPABASE_SECRET_KEY` is preferred; a legacy `SUPABASE_SERVICE_ROLE_KEY` remains supported. Both are broadly privileged server credentials and must remain isolated even though this worker implementation calls only the three scanner RPCs. ClamAV must be installed, running, and using current signatures. Missing credentials, unavailable ClamAV, provider errors, expired leases, and decode uncertainty never produce `clean`.

The Phase 2F code and database boundary are deployed to development, but no persistent development worker is active until an isolated scanner secret and ClamAV runtime are provisioned. The existing three assets therefore remain truthfully `pending` with three `queued` jobs; no development fallback marks them clean.

Seed the local archive database:

```bash
python3 scripts/seed_local_archive_db.py
```

This creates `data/archive.db` with local sample image metadata, asset rows, grouped tags, taggings, and an `archive-featured` collection. Local `.db` files are ignored by Git.

When `data/archive.db` exists, `server.py` exposes the published archive rows at:

```text
http://127.0.0.1:8131/api/archive/images
```

`works.html` reads this endpoint first and falls back to the local sample data if the database or API is unavailable.

An authenticated Admin with completed MFA can also sync existing seeded works back into the local SQLite database:

```text
PATCH http://127.0.0.1:8131/api/archive/images/{id}
```

This metadata write path updates existing `images`, `image_tags`, and `image_taggings` rows only.

Phase 2A-2F uploads, Draft editing, readiness, trusted scanning, and submission use the protected Workspace boundary:

```text
GET|POST               /api/folders
PATCH|DELETE           /api/folders/{id}
POST                   /api/uploads/intents
DELETE                 /api/uploads/{id}
POST                   /api/uploads/{id}/complete
GET                    /api/images
GET                    /api/images/{id}/readiness
PATCH                  /api/images/{id}/draft
POST                   /api/images/{id}/submit
DELETE                 /api/images/{id}
```

The browser prepares `original`, `display`, and `thumbnail` assets, processes at most two tasks concurrently, requests owner-namespaced signed destinations, uploads directly to private Supabase Storage, and completes one server Draft transaction. A task may be canceled while queued or in flight, retried without losing its local preview, or removed after failure/cancellation. Server cancellation records the terminal state and removes any partial objects through the Storage API.

The Draft editor autosaves core copy, Alt Text, copyright, release, rights, AI, and sensitive-content disclosures after a 900 ms debounce while retaining the explicit Save command. The UI reports Saving, Saved, Error, and Conflict states. Each Draft response exposes a `lock_version`; Draft PATCH and Trash requests must send it as `expected_version`. The database compares the expected and current image versions atomically. A stale write returns HTTP 409, keeps the local form intact, stops autosave, and exposes `Reload Server Draft` so the author can deliberately replace local edits with current server data. A successful PATCH returns canonical Draft metadata without `assets` and does not perform a second signed-read step after committing the write. Folders and Draft metadata are authoritative in PostgreSQL. IndexedDB remains only a read-only offline cache; reconnect before changing data.

`database/migrations/20260716_workspace_draft_versioning.sql` adds the versioned Draft update and Trash RPCs, revokes authenticated execution from their old unversioned counterparts, and grants the versioned RPCs to authenticated users only. Moving Drafts to Inbox while deleting a Folder also increments each affected image version, so an open editor cannot overwrite that server-side move with a stale Folder value. `database/migrations/20260716_workspace_folder_integrity.sql` serializes Folder deletion with image and upload-intent Folder assignment, redirects an upload that finishes against a concurrently deleted Folder to the owner's active Inbox, and restores a trashed Draft to Inbox when its former Folder no longer exists.

Phase 2E adds server-authoritative readiness for Work details, Rights & disclosures, Image assets, Security scan, and Submission state. `POST /api/images/{id}/submit` requires the current `expected_version`, a valid UUID `idempotency_key`, and explicit `submit-for-review` confirmation. One transaction locks the selected image version, creates immutable review/readiness/asset snapshots, advances the image to `submitted`, writes the user notification and audit event, and makes same-key retries return the first result. Direct authenticated mutation of submission rows is revoked, and an owner cannot directly delete a Storage object after it has been registered in `image_assets`.

The Upload Studio polls only pending readiness, requires a confirmation before Submit, disables mutations while submitting, and removes a successfully submitted item from the Draft list. Uploaded assets are created with `scan_status=pending`; the independent Phase 2F worker is the only application runtime that claims scan jobs and moves them to `clean`, `flagged`, or `failed`. All three assets must be `clean` under the current scan policy before readiness becomes Ready. There is no user-level quota/capacity policy in this slice.

The legacy Archive endpoints and `manage.html` remain the existing Admin+AAL2 SQLite Review/public prototype. Submitted Supabase records do not yet appear in that Review Center or public Works; the Supabase Review Queue and review decisions are the next vertical slice.

Drafts are moved to Trash through:

```text
DELETE http://127.0.0.1:8131/api/images/{id}
```

This is a soft delete and uses the same `expected_version` compare-and-swap contract as Draft PATCH. Submitted images are locked and cannot be moved directly to Trash. The restore RPC/API boundary exists, while the Trash browser view, quota policy, Supabase Review Queue, and Publish decisions remain later slices.

Validate the local archive database workflow:

```bash
python3 scripts/validate_local_archive_db.py
```

This creates a temporary SQLite database, runs the seed process, and checks table/view presence, foreign keys, counts, multi-version assets, tag JSON, ratio categories, and local asset paths.

Contact page:

```text
http://127.0.0.1:8131/contact.html
```

The contact form opens the visitor's email app with a prepared draft. There is no local message inbox or message database.

## Project Files

- `index.html`: homepage; reads editable hero and Statement content from local homepage settings when available.
- `works.html`: public Works Archive page.
- `about.html`: public artist practice and availability page.
- `lightbox.html`: browser-local visitor selection and inquiry handoff.
- `public-archive.js`: shared public archive loading and Lightbox storage migration.
- `upload-studio.html`: protected `/workspace/images` document for personal image import, folder assignment, grouped work/accessibility/rights metadata editing, five-check readiness, confirmed Submit for Review, and moving editable Drafts to Trash.
- `account-settings.html` / `account-settings.js`: protected `/settings/account` profile, authorship preferences, account-security summary, current-session view, dirty state, and bulk session revocation UI.
- `manage.html`: Review Center for Works metadata, approval, visibility, and homepage content editing.
- `styles.css`: site styling and responsive layout.
- `script.js`: homepage navigation scroll state, editable homepage settings hydration, and Statement section activation.
- `archive-data.js`: shared Works Archive base sample data used by public Works and the internal editor.
- `archive-upload.js`: shared browser-side work import pipeline for dimensions, EXIF, checksum, display/thumbnail, and square slice records.
- `archive.js`: public Works Archive API loading, local sample fallback, URL filters, work viewer, Lightbox/inquiry actions, published-record reading, and IndexedDB fallback.
- `lightbox.js`: Lightbox rendering, remove/clear actions, and Contact handoff.
- `upload-studio.js`: server-authoritative Folder/Draft flow, bounded upload workers, task Cancel/Retry/Remove, signed private Storage uploads, compliance metadata normalization, serialized autosave, optimistic-concurrency recovery, readiness polling, UUID-idempotent submission, versioned Trash, and read-only IndexedDB offline cache.
- `manage.js`: legacy Review Center metadata editor, local SQLite metadata sync, homepage settings editor, editable-field-only dirty signatures, grouped tag editing, and IndexedDB save/revert fallback; it does not consume Supabase `review_submissions` yet.
- `contact.html`: Contact Artist page and inquiry form.
- `contact.js`: structured inquiry validation, Work/Series/Lightbox context, mail draft generation, and toast feedback.
- `server.py`: local static server; Supabase Auth/Profile/Session boundary with HttpOnly sessions and CSRF protection; protected Workspace Folder/Draft/readiness/submission/signed-upload APIs; strict readiness/submission response projection; public published Archive reads plus Admin+AAL2 legacy Archive mutations backed by `data/archive.db`.
- `database/local_archive_schema.sql`: SQLite schema for local Works Archive database verification.
- `scripts/seed_local_archive_db.py`: seeds `data/archive.db` from `archive-data.js`.
- `scripts/validate_local_archive_db.py`: validates the local SQLite archive workflow in a temporary database.
- `scripts/test_auth_security_boundary.py`: secret-free local integration test for CSRF, account recovery, profile read/write, session revocation, Workspace/Account route guards, Admin MFA, and private legacy originals.
- `scripts/test_workspace_phase2_boundary.py`: secret-free fake-provider integration test for Folder/upload/Draft boundaries plus readiness states, CSRF, stale Submit, idempotent success, immutable submitted state, response allowlists, and Admin AAL1 denial.
- `scripts/validate_workspace_phase2.py`: static contract validator for the Phase 2A-2E schema, migrations, API routes, resilient browser queue, Draft autosave/conflict, readiness/Submit state machine, RPC permissions, and CI wiring.
- `workers/scan_adapters.py` / `workers/image_scanner.py`: scanner-only provider, private Storage and ClamAV adapters plus the single-job/continuous polling CLI; redirects are rejected, subprocess environments are scrubbed, operation budgets must fit the lease, and no scanner secret enters the Web process.
- `workers/image_probe.py`: credential-free isolated Pillow subprocess for allowlisted full decode, EXIF-oriented dimensions, multi-frame rejection, decompression-bomb handling, and OS resource limits where supported.
- `requirements-scanner.txt` / `.env.worker.example`: pinned scanner dependency and secret-isolated runtime configuration contract.
- `scripts/validate_workspace_asset_scanner.py`: static Phase 2F schema, lease, RPC, fail-closed worker, dependency and logging contract validation.
- `scripts/test_workspace_asset_scanner.py`: secret-free loopback integration test for current/legacy key headers, clean/failed/flagged/retry branches and sensitive-log exclusion.
- `scripts/test_workspace_asset_scanner_database.sql`: development-only transactional scanner state-machine test for disjoint claims, token/idempotency, retry, lease reclaim, and attempt exhaustion; it always rolls back.
- `scripts/test_supabase_deploy_script.py`: fake-`psql` deployment regression for fresh-baseline, existing-database migration order, and invalid-mode fail-closed behavior.
- `.github/workflows/database.yml`: GitHub Actions workflow that runs the database validation command.
- `docs/README.md`: documentation index and maintenance rules.
- `docs/product/user-upload-admin-spec.md`: authoritative target specification for users, Upload Workspace, and Admin Platform.
- `docs/operations/upload-testing.md`: manual test and troubleshooting guide for upload/database integration.
- `assets/`: local visual assets used by the site.
- `docs/architecture/database-design.md`: current SQLite and deferred production database design notes.
- `database/schema.sql`: deferred PostgreSQL/Supabase schema.
- `database/product_schema.sql`: Phase 0 production target schema for users, ownership, folders, independent image states, immutable versions/reviews, takedowns, notifications, and append-only audit records.
- `database/supabase_phase1_auth_rls.sql`: Phase 1 Supabase baseline for `auth.users` business-user synchronization, owner-scoped RLS, strict owner-only profile RPC, reviewer/admin policies, Admin AAL2 enforcement, public Works isolation, and private Storage namespaces.
- `database/migrations/`: ordered, transaction-wrapped patches for existing environments, including Admin hardening, strict Account Settings, Phase 2A private Draft/Folders/Storage, Phase 2B cancellation/cleanup, Phase 2C compliance metadata, Phase 2D optimistic versioning/Folder integrity, Phase 2E authoritative readiness/submission snapshots, and Phase 2F trusted leased asset scanning.
- `scripts/validate_product_phase0.py`: validates the Phase 0 schema contract and confirms public navigation no longer exposes Series/Collections.
- `auth.html` / `auth.js`: Phase 1 Register and Sign In UI with field validation, verification/suspended-provider error boundaries, loading feedback, and no browser token storage.
- `scripts/validate_auth_foundation.py`: checks Phase 1 Auth/Account routes, secure Cookie/CSRF contracts, Profile/Session clients, deployment mode, accessibility hooks, and browser-storage prohibition.
- `scripts/validate_supabase_phase1_rls.py`: checks private-table RLS plus ownership, strict Profile RPC, role, MFA, public publication, and Storage policies.
- `scripts/deploy_supabase_phase1.sh`: validates and applies a fresh Phase 0/1 baseline or migration-only updates using `PG*` environment variables and an explicit production safety gate.
- `scripts/test_supabase_phase1_isolation.py`: signs in two disposable verified development users and performs non-mutating PostgREST checks proving user/profile/role row isolation.
- `docs/architecture/provider-decisions.md`: authentication, session, authorization, and object-storage boundaries plus development deployment evidence.
- `docs/architecture/project-map.md`: maintained feature and file responsibility map.
- `docs/design/design-system.md`: visual, component, responsive, and interaction rules.
- `docs/design/image-sources.md`: temporary image sources and production replacement rules.

## Notes

The current images are design-stage placeholders. They should be replaced with final MT works or properly licensed production assets before a formal public launch.
