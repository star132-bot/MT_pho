# MT Presence

MT Presence is a fine art photography portfolio and image-workflow prototype. Version `v1.0.0` started as a static first version; the current workspace combines the public gallery, a legacy SQLite Review prototype, and a Supabase-backed account and private Draft workspace.

## Current Version

- Version: `1.0.0`
- Release label: `v1.0.0`
- Status: public frontend, server-managed Supabase Auth/Account, protected creator workspace, Review/public delivery, Admin Works/Users, project inquiries, Notifications/Inbox, protected Audit Ledger, and production-deployment tooling. This repository is a production candidate; it does not record an active production deployment.
- Database: Phase 0/1 through Phase 4B are deployed to development. The Phase 5 communications/audit migration and its development-only rollback acceptance remain gates before production promotion. Public Works and creator profiles read strict published-only Supabase DTOs; the SQLite Archive remains development/legacy tooling rather than the production authority.

## Features

- One reusable 64px GlobalHeader across Home, Works, About, Lightbox, Contact, Review, Dashboard, creator profiles, Privacy, and the direct Collections compatibility route. Desktop keeps the MT Presence brand, a centered 500px work search, Home/Works/About/Lightbox/Contact/Review, the stable account identity, and the account menu in one quiet line; mobile collapses search and public navigation without introducing a left rail.
- Unified responsive footer system: Home, Works, About, Contact, and Lightbox use a restrained charcoal Public Footer with real inquiry and account destinations, while Dashboard, Upload Studio, Account Settings, and Review Queue use a compact in-flow Workspace Footer. Protected account links fail closed unless the account is explicitly active, and Review additionally requires the matching role.
- Full-width, regular-flow homepage hero with no left rail, transitioning from abstract black-and-white scenery to concrete color scenery and revealing the start of Selected Works in the first viewport.
- Infinite horizontal selected works gallery.
- Four-moment image-led Statement section, placed after Selected Works, with one image per text passage and a final Enter Works call to action.
- Compact Works Archive page with read-only local SQLite preview data when explicitly enabled, global-header search, underlined Type/Ratio text filters directly below the header, no title/metrics hero, and responsive five/four/three/two/one-column natural-ratio masonry. Ratio filters expose the underlying `1:1`, `4:3`, `4:5`, `2:3`, `3:2`, `16:9`, and panorama groups without collapsing results into a narrow left column.
- Works Archive work viewer with full-screen enlarged images, fit/actual-size zoom, catalog-style metadata, keyboard navigation, and grouped visual tags.
- Standalone work detail route with a 55/45 image-and-record layout, previous/next navigation, synchronized Lightbox save state, inquiry/download actions, metadata, tags, and related works.
- Internal Works Viewer Editor for importing works; maintaining the viewer title, series, notes, metadata, visibility, sort order, and grouped tags; and editing homepage hero images/text in the IndexedDB transition layer.
- Upload flow that reads original image dimensions, checksum, and basic EXIF in the browser.
- Local multi-version image asset generation for uploads: original, display, thumbnail, and square slices.
- Automatic ratio classification: `1:1`, `4:3`, `4:5`, `2:3`, `3:2`, `16:9`, `Panorama`.
- Abstract and Concrete filters.
- Arrange mode for ordering Works Archive items, with drag controls, Earlier/Later buttons, and local order persistence.
- Browser-local Lightbox with persistent saved works plus an explicit session-scoped Inquiry Selection, three-column desktop gallery, visible selection summary, sorting, and selected-ID-only Contact handoff.
- About page with an image-led editorial spread, published creator profile hydration when available, truthful fallback content, and a linear practice fact strip.
- Protected Upload Studio with server-authoritative Supabase Folders and Drafts, a two-worker upload queue, per-item Cancel/Retry/Remove controls, owner-scoped signed uploads to three private Storage buckets, canceled-object cleanup, 900 ms debounced Draft autosave, version-conflict recovery, five-check submission readiness, idempotent Submit for Review, soft-delete Trash/Restore views, and read-only IndexedDB offline cache.
- Independent trusted asset scanner with restricted leased jobs, private Storage streaming, SHA-256/magic/MIME checks, ClamAV malware detection, isolated Pillow full decoding, bounded retries, append-only scan events, and fail-closed current-policy readiness updates.
- Contact Artist submits a persisted, idempotent project inquiry with optional selected published works, abuse controls, a visitor reference, and a privacy notice.
- Protected Notifications and Inbox workspaces provide unread state, cursor pagination, recipient-isolated conversations, versioned replies, Close/Reopen controls, and truthful manual-email fallback when no outbound provider is configured.
- Supabase Register/Verify/Sign In/Sign Out/Forgot/Reset flow with HttpOnly session cookies, CSRF protection, owner isolation, and Admin MFA guards.
- Protected Account Settings with a real owner-scoped profile-photo upload/remove flow, five creator-profile groups and ten editable identity/work/location/about/link fields, plus authorship preferences, verified account state, current-session description, and provider-supported bulk session revocation. Source photos are center-cropped and re-encoded in the browser; only a private 512x512 JPEG is uploaded.
- Full-width protected personal profile at `/dashboard`, led by an editable horizontal photography cover, overlapping avatar, restrained identity/actions and thin-line profile facts rather than colored dashboard blocks. Overview/My works remain backed by the real server aggregate for work status, Changes Requested/processing attention, recent signed private previews, review activity, storage usage, editable Drafts, and truthful quota/public-portfolio capability states.
- Signed-in headers reserve a fixed avatar container before paint. A server-rendered, secret-free identity bootstrap provides initials, and the shared controller crossfades a decoded avatar without changing header geometry; a failed image keeps the initials fallback. The avatar and adjacent three-dot control open the same keyboard-accessible account menu, while Review remains a permission-aware top-level destination. The menu contains only Dashboard, Workspace, Account Settings, and CSRF-protected Sign out.
- Protected Supabase Admin Review Queue with scoped Reviewer claims, Admin+AAL2 history access, image-first submitted-version inspection, checklist decisions, optimistic concurrency, idempotent mutation keys, private signed assets, and immutable decision/audit evidence. Reviewer exposes Request Changes, Reject, and Approve; Admin/Super Admin at AAL2 can additionally Approve and publish into the strict public Works and creator-profile boundary. A separate Super Admin+AAL2 self-publish action is limited to an owned, untouched, unassigned Submitted work and writes dedicated immutable audit evidence.
- Protected Admin Works governance at `/admin/works` with all-work status counts, search, sort, bounded pagination, deep-linked evidence inspection, derivative-only previews, and Admin/Super Admin+AAL2 Takedown/Restore controls backed by CAS, idempotency, creator notification, active takedown cases, and append-only success/failure audit history.
- Protected Admin User administration at `/admin/users` with account-state counts, search, role filters, sorting, bounded pagination, deep-linked identity/security/history inspection, Admin suspend/reactivate controls, Super Admin-only Reviewer/Admin role management, and audited session-revocation requests. Self/system/privileged-target and final-active-Super-Admin guards are enforced in PostgreSQL; MFA, active-session counts, and quota remain explicitly unavailable when the identity provider is not authoritative through this Web process.
- Protected Admin Audit Ledger at `/admin/audit` with safe list/detail projections, actor/request/date filters, cursor pagination, and an audited bounded CSV export that excludes raw private state and direct identifiers.
- The repository includes production operations for fail-closed runtime preflight, bounded request threads, explicit public static-file allowlisting, Nginx TLS/security/rate-limit templates, split Web/scanner/database credentials, immutable checksummed releases, atomic activation/rollback, health/readiness probes, database backup verification, and a single local/CI release gate. These artifacts are readiness tooling, not evidence of production activation.
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

Protected user Dashboard:

```text
http://127.0.0.1:8131/dashboard
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

Protected Supabase Review Queue:

```text
http://127.0.0.1:8131/admin/reviews
http://127.0.0.1:8131/admin/reviews/{submissionId}
```

Protected Admin Works governance:

```text
http://127.0.0.1:8131/admin/works
http://127.0.0.1:8131/admin/works/{imageId}
```

Protected Admin User administration:

```text
http://127.0.0.1:8131/admin/users
http://127.0.0.1:8131/admin/users/{userId}
```

Copy `.env.example` values into your local environment before starting the server. Set `MT_PUBLIC_BASE_URL` to the exact browser origin and add `/auth/verify-email` plus `/auth/reset-password` to the Supabase Auth redirect allowlist. The auth routes use Supabase Auth through the server, keep access/refresh tokens in `HttpOnly` cookies, require a same-origin CSRF token for mutations, and never use browser storage for credentials. `/dashboard` and `/workspace/images` are protected, `/workspace` canonicalizes to Dashboard, direct `/upload-studio.html` requests canonicalize to Upload Studio, and Admin/Super Admin sessions require AAL2 before opening these account surfaces.

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
python3 scripts/configure_development_scanner.py
set -a
source .env.worker
set +a
.venv-scanner/bin/python workers/image_scanner.py --once
```

The configurator reads the project URL from `.env`, accepts a current secret through a hidden prompt (or either supported credential from the process environment), verifies ClamAV with a real empty-file scan, preserves a stable worker ID, and atomically writes only the Git-ignored `.env.worker` with mode `0600`. It never accepts the secret as a command argument. `SUPABASE_SECRET_KEY` is preferred; a legacy `SUPABASE_SERVICE_ROLE_KEY` remains supported. Both are broadly privileged server credentials and must remain isolated even though this worker implementation calls only the three scanner RPCs. ClamAV must be installed with current signatures; `clamdscan` also requires a running ClamD. Missing credentials, unavailable ClamAV, provider errors, expired leases, and decode uncertainty never produce `clean`.

The Phase 2F code and database boundary are deployed to development, and the isolated development worker can run with the provisioned `.env.worker` and ClamAV runtime. Worker process state is operational rather than repository state, so verify it directly before relying on queued-job consumption. A production-persistent worker, monitoring, and alerting remain unfinished; no fallback may mark an asset `clean`.

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

The Dashboard reads one owner-scoped server aggregate and never walks all image rows in the browser:

```text
GET                    /api/dashboard
GET                    /api/me/profile
GET|PATCH              /api/me/profile/cover
```

`database/migrations/20260722_user_dashboard.sql` installs authenticated-only `get_my_dashboard()`. `database/migrations/20260722_z_creator_profile.sql` extends the owner profile and exposes authenticated-only cover read/update RPCs. The cover chooser accepts only a current, ready, non-deleted image owned by the signed-in user and a current-policy scanner-clean display/thumbnail derivative; it remains usable after publication changes a derivative from private to public. `database/migrations/20260722_public_delivery.sql` adds the stable opaque creator slug, published-only Works/creator/status RPCs, and anonymous read policy for exact clean public display/thumbnail objects. The Web server projects fixed browser allowlists and replaces explicit Storage fields with short-lived signed URLs; originals, owner identifiers, review evidence, and private EXIF are never returned by the MT Web API. The provider locator inside the signed URL or anonymous delivery RPC is not an anonymity boundary; see `docs/operations/public-delivery-testing.md`.

The browser prepares `original`, `display`, and `thumbnail` assets, processes at most two tasks concurrently, requests owner-namespaced signed destinations, uploads directly to private Supabase Storage, and completes one server Draft transaction. A task may be canceled while queued or in flight, retried without losing its local preview, or removed after failure/cancellation. Server cancellation records the terminal state and removes any partial objects through the Storage API.

The Draft editor autosaves core copy, Alt Text, copyright, release, rights, AI, and sensitive-content disclosures after a 900 ms debounce while retaining the explicit Save command. The UI reports Saving, Saved, Error, and Conflict states. Each Draft response exposes a `lock_version`; Draft PATCH and Trash requests must send it as `expected_version`. The database compares the expected and current image versions atomically. A stale write returns HTTP 409, keeps the local form intact, stops autosave, and exposes `Reload Server Draft` so the author can deliberately replace local edits with current server data. A successful PATCH returns canonical Draft metadata without `assets` and does not perform a second signed-read step after committing the write. Folders and Draft metadata are authoritative in PostgreSQL. IndexedDB remains only a read-only offline cache; reconnect before changing data.

`database/migrations/20260716_workspace_draft_versioning.sql` adds the versioned Draft update and Trash RPCs, revokes authenticated execution from their old unversioned counterparts, and grants the versioned RPCs to authenticated users only. Moving Drafts to Inbox while deleting a Folder also increments each affected image version, so an open editor cannot overwrite that server-side move with a stale Folder value. `database/migrations/20260716_workspace_folder_integrity.sql` serializes Folder deletion with image and upload-intent Folder assignment, redirects an upload that finishes against a concurrently deleted Folder to the owner's active Inbox, and restores a trashed Draft to Inbox when its former Folder no longer exists.

Phase 2E adds server-authoritative readiness for Work details, Rights & disclosures, Image assets, Security scan, and Submission state. `POST /api/images/{id}/submit` requires the current `expected_version`, a valid UUID `idempotency_key`, and explicit `submit-for-review` confirmation. One transaction locks the selected image version, creates immutable review/readiness/asset snapshots, advances the image to `submitted`, writes the user notification and audit event, and makes same-key retries return the first result. Direct authenticated mutation of submission rows is revoked, and an owner cannot directly delete a Storage object after it has been registered in `image_assets`.

The Upload Studio polls only pending readiness, requires a confirmation before Submit, disables mutations while submitting, and removes a successfully submitted item from the Draft list. Uploaded assets are created with `scan_status=pending`; the independent Phase 2F worker is the only application runtime that claims scan jobs and moves them to `clean`, `flagged`, or `failed`. All three assets must be `clean` under the current scan policy before readiness becomes Ready. There is no user-level quota/capacity policy in this slice.

The protected `/admin/reviews` workspace reads Supabase submission snapshots through the dedicated Review Queue API. A pure Reviewer can see non-self waiting work and their own open non-self assignments, but private detail assets require an atomic claim/start and a current clean scan. Normal assignment, start, and decision RPCs forbid self-review for every role. Admin and Super Admin sessions require AAL2 and can inspect the full authorized history. Mutations use CSRF, current `lock_version`, and UUID idempotency keys. Reviewers can Request Changes, Reject, or Approve. Admin/Super Admin+AAL2 additionally see Approve and publish on non-self work. The dedicated `review_super_admin_self_publish` path is the only owner exception: Super Admin+AAL2, untouched/unassigned Submitted state, complete checklist, current readiness/version and three current-policy-clean assets are all required, and `review.super_admin_self_publish` is audited. Publication atomically makes only clean display/thumbnail derivatives visible through public Works and the creator profile. Legacy non-public Archive mutation endpoints remain Admin+AAL2-only SQLite tooling and are not a production public fallback.

```text
GET    /api/admin/review-submissions?status=&assignment=&limit=&offset=
GET    /api/admin/review-submissions/{submissionId}
POST   /api/admin/review-submissions/{submissionId}/assign
POST   /api/admin/review-submissions/{submissionId}/start
POST   /api/admin/review-submissions/{submissionId}/{request-changes|reject|approve|approve-and-publish}
```

The protected `/admin/works` workspace is the publication inventory after review. Its browser DTO never includes owner UUIDs, originals, Storage coordinates, checksums, private EXIF, internal notes, or provider diagnostics. Preview signing is limited to the exact current-policy-clean display/thumbnail object. Takedown and Restore require active Admin/Super Admin+AAL2, same-origin CSRF, current version, a UUID idempotency key, a controlled reason, and a creator-facing message; all side effects are one database transaction and every accepted or controlled-failure attempt is auditable.

```text
GET    /api/admin/works?status=&q=&sort=&limit=&offset=
GET    /api/admin/works/{imageId}
POST   /api/admin/works/{imageId}/{takedown|restore}
```

The protected `/admin/users` workspace reads a strict account-governance DTO. Status and session-intent controls require active Admin/Super Admin+AAL2; role changes additionally require Super Admin. Session revocation returns HTTP `202` with `provider_action_required=true`: it records the required provider operation and never claims that Supabase Auth sessions have already closed.

```text
GET    /api/admin/users?status=&role=&q=&sort=&limit=&offset=
GET    /api/admin/users/{userId}
POST   /api/admin/users/{userId}/status
POST   /api/admin/users/{userId}/roles
POST   /api/admin/users/{userId}/revoke-sessions
```

Drafts are listed, moved to Trash, and restored through:

```text
GET    http://127.0.0.1:8131/api/images?workflow_status=trashed
DELETE http://127.0.0.1:8131/api/images/{id}
POST   http://127.0.0.1:8131/api/images/{id}/restore
```

Trash is a soft delete and uses the same `expected_version` compare-and-swap contract as Draft PATCH. Submitted images are locked and cannot be moved directly to Trash. The read-only Trash view exposes only Restore; a successful restore returns the Draft to its original active Folder or falls back to Inbox when that Folder was deleted. Quota policy remains a later slice; published-only public delivery and end-to-end Works/creator visibility are connected.

Run the development-only, rollback-only Dashboard/Trash/creator-profile database acceptance with isolated development `PG*` variables loaded:

```bash
MT_TEST_ENVIRONMENT=development python3 scripts/test_user_dashboard_database.py
```

Never point rollback-only fixture tests at the production primary. Before production promotion, run them against development or a disposable staging/restored clone using dedicated non-production credentials, then use only read-only checks against production.

The rollback-only test now requires twelve success markers. `dashboard_image_json(uuid)`, `require_creator_profile_user()`, and `creator_profile_cover_asset_json(uuid,uuid)` remain owner-only helpers; `get_my_dashboard()`, `workspace_list_trashed_drafts()`, `update_my_profile(jsonb)`, `get_my_profile_cover()`, and `set_my_profile_cover(uuid)` are executable only by `postgres` and `authenticated`. The test covers aggregate/state filtering, extended profile normalization, official-host social URLs, owner-isolated current-clean cover eligibility, bucket-kind mismatch rejection, inactive/recovery/AAL guards, rollback, and an independent fixture-absence check.

Validate the local archive database workflow:

```bash
python3 scripts/validate_local_archive_db.py
```

This creates a temporary SQLite database, runs the seed process, and checks table/view presence, foreign keys, counts, multi-version assets, tag JSON, ratio categories, and local asset paths.

Contact page:

```text
http://127.0.0.1:8131/contact.html
```

The contact form records the inquiry through `POST /api/inquiries` and returns an opaque reference. Signed-in recipients manage isolated conversations in `/inbox`; account updates are available at `/workspace/notifications`. Guest replies remain truthful: without a configured outbound provider the Inbox offers a manual email action and never claims that mail was sent.

## Project Files

- `index.html`: homepage; reads editable hero and Statement content from local homepage settings when available.
- `works.html`: compact public Works Archive shell with GlobalHeader, directly adjacent Type/Ratio filters, no visible title/count hero, responsive natural-ratio masonry, and the existing viewer/actions.
- `work.html` / `work-detail.js`: standalone public work record; loads the same published-only archive DTO, renders previous/next, metadata, tags and related works, and shares Lightbox/inquiry state without replacing the existing full-screen Viewer.
- `about.html` / `about.js`: public artist practice and availability spread using the unified header, published creator profile hydration, stable fallback copy, and no public rail.
- `lightbox.html`: browser-local saved-work collection with a separate session Inquiry Selection, visible selection summary, sorting, and selected-ID-only Contact handoff.
- `public-archive.js`: shared public archive loading, persistent Lightbox migration, and session-scoped Inquiry Selection storage.
- `public-navigation.js`: mobile controller for the shared public/Profile header; synchronizes menu visibility, `aria-expanded`, `aria-hidden`, `inert`, ArrowDown/Escape focus behavior, outside closing, and breakpoint changes without owning authentication.
- `global-header.js`: reusable header renderer and global work-search controller; owns the shared brand/search/public-navigation structure, active-route state, responsive search expansion, debounced Works filtering, safe cross-page suggestions, keyboard submission/Escape behavior, and Lightbox count synchronization without duplicating identity requests.
- `site-footer.js`: shared Public/Workspace footer renderer with dynamic year, current-route state, real inquiry destinations, and permission-aware account links driven by the existing account-loaded event without a duplicate identity request.
- `dashboard.html` / `dashboard.js`: full-width protected `/dashboard` personal profile with editable horizontal cover, overlapping avatar, quiet identity/facts sidebar, Overview/My works tabs, aggregate Dashboard DTO consumption, and complete loading/empty/error/permission states.
- `account-menu.js`: single public/internal Header Identity controller; hydrates the server bootstrap, keeps Sign In and the fixed-size avatar mutually exclusive, decodes avatar images before crossfade, synchronizes the avatar and three-dot menu triggers, renders the stable identity summary, owns keyboard/focus behavior, and performs CSRF-protected sign out.
- `upload-studio.html`: protected `/workspace/images` document for personal image import, folder assignment, grouped work/accessibility/rights metadata editing, five-check readiness, confirmed Submit for Review, and read-only Trash/Restore views.
- `account-settings.html` / `account-settings.js`: protected `/settings/account` editor with ten creator fields grouped into Identity, Work, Location, About, and Links, plus authorship preferences, account-security summary, current-session view, dirty state, and bulk session revocation UI.
- `admin-reviews.html` / `admin-reviews.js`: protected `/admin/reviews` queue/detail workspace with status/assignment filters, atomic Reviewer start, submitted-version evidence, review checklist, conflict recovery, Reviewer decisions, Admin/Super Admin+AAL2 Approve and publish, and the constrained Super Admin self-publish confirmation flow.
- `admin-works.html` / `admin-works.js`: protected `/admin/works` publication inventory/detail workspace with status counts, search/sort/pagination, mobile single-view navigation, governance history, conflict recovery, and confirmed Takedown/Restore.
- `admin-users.html` / `admin-users.js`: protected `/admin/users` account directory/detail workspace with status metrics, search/role/sort/pagination, mobile single-view navigation, strict capability states, conflict recovery, and confirmed status/role/session-intent controls.
- `creator.html` / `creator.js`: public `/creators/{public_slug}` profile with published cover, identity, availability, external links, and responsive Works masonry linking into Viewer deep links.
- `manage.html`: Review Center for Works metadata, approval, visibility, and homepage content editing.
- `styles.css`: site styling and responsive layout, including the 64px quiet editorial GlobalHeader, 500x40 pill search, compact account popover, Public/Workspace footer variants, zero public rail reservation, compact Works filters/masonry, and mobile overflow protections.
- `script.js`: homepage navigation scroll state, editable homepage settings hydration, and Statement section activation.
- `archive-data.js`: shared Works Archive base sample data used by public Works and the internal editor.
- `archive-upload.js`: shared browser-side work import pipeline for dimensions, EXIF, checksum, display/thumbnail, and square slice records.
- `archive.js`: public Works Archive DTO loading, URL filters, work viewer, creator links, Lightbox/inquiry actions, and environment-aware fallback; favorite changes patch the original card/viewer/count nodes and never rebuild the Gallery.
- `lightbox.js`: persistent saved-work rendering, node-local Inquiry Selection controls, remove/confirmed Remove all actions, and selected-ID-only Contact handoff.
- `upload-studio.js`: server-authoritative Folder/Draft/Trash flow, bounded upload workers, task Cancel/Retry/Remove, signed private Storage uploads, compliance metadata normalization, serialized autosave, optimistic-concurrency recovery, readiness polling, UUID-idempotent submission, versioned Trash/Restore states, and read-only IndexedDB offline cache.
- `database/migrations/20260722_workspace_trash_restore.sql`: authenticated owner-scoped trashed-Draft read model used by the Upload Studio Trash view.
- `scripts/test_workspace_phase2_boundary.py` / `scripts/test_workspace_trash_browser.py`: secret-free API boundary plus 1440px/390px Trash/Restore browser acceptance and screenshots.
- `manage.js`: legacy Review Center metadata editor, local SQLite metadata sync, homepage settings editor, editable-field-only dirty signatures, grouped tag editing, and IndexedDB save/revert fallback; it does not consume Supabase `review_submissions` yet.
- `contact.html`: Contact Artist page and inquiry form using the unified header and no public rail.
- `contact.js`: structured inquiry validation, Work/Series/explicit Inquiry Selection context, per-item context removal, CSRF retry, UUID idempotency, and persisted inquiry success/error states.
- `notifications.html` / `notifications.js`: protected account notification center with strict safe DTOs, unread/read-all commands, local filtering, object-cursor pagination, and internal-link validation.
- `inbox.html` / `inbox.js`: protected recipient conversation workspace with local search, status filtering, thread detail, read state, versioned reply and Close/Reopen mutations, conflict recovery, and manual guest-email fallback.
- `admin-audit.html` / `admin-audit.js` / `admin-audit.css`: Admin/Super Admin+AAL2 safe audit list/detail, advanced filters, mobile list/detail navigation, and reason-bound audited CSV export.
- `privacy.html` / `privacy.css`: public notice for account, artwork, inquiry, cookie, retention, and security-record handling.
- `server.py`: local Web/BFF server; explicit public static allowlist; Supabase Auth/Profile/Session boundary with HttpOnly sessions and CSRF; creator Workspace, Review, Admin Works/Users/Audit, Notifications/Inbox/inquiry APIs; health/readiness probes; strict DTO projections; and bounded production request concurrency.
- `database/migrations/20260723_d_communications_audit.sql`: transaction-wrapped project inquiry, conversation/message, notification, safe audit read/export, exact ACL/RLS, CAS/idempotency, rate-limit, append-only, and privacy boundary.
- `scripts/validate_communications_audit.py` / `scripts/test_communications_audit_boundary.py` / `scripts/test_communications_audit_database.py`: static, secret-free HTTP, and development-only rollback PostgreSQL acceptance for the communications and audit slice.
- `scripts/release_gate.sh`: one-command static, JavaScript, secret-free boundary, production-artifact, syntax, and patch-integrity release gate; credentialed database acceptance remains a non-production gate and browser acceptance remains an explicit subsequent gate.
- `deploy/` / `docs/operations/production-deployment.md`: hardened systemd/Nginx/environment templates and the backup, migration, immutable release, TLS, verification, rollback, and observation runbook.
- `database/migrations/20260722_user_dashboard.sql`: authenticated owner-scoped Dashboard read model with server-side counts, attention ordering, recent work/review activity, storage usage, and explicit capability flags.
- `database/migrations/20260722_z_creator_profile.sql`: transaction-wrapped protected creator-profile extension, strict field RPC, owner-scoped cover eligibility helpers, and authenticated-only cover read/update RPCs.
- `database/migrations/20260723_c_profile_avatar_upload.sql`: transaction-wrapped private profile-avatar bucket, owner-scoped upload intents, exact active-object metadata, complete/cancel/remove RPCs, and public-current-object read policy; signed URLs are never persisted.
- `database/migrations/20260722_public_delivery.sql`: transaction-wrapped published-only Works/creator/status RPCs, opaque stable public slug, strict active/current/clean projection, base-table public-read revocation, and derivative-only Storage policy.
- `scripts/validate_user_dashboard.py` / `scripts/test_user_dashboard_boundary.py`: static Dashboard/creator-profile contract plus secret-free loopback route/RPC/DTO/signing and cover mutation integration.
- `scripts/test_user_dashboard_database.py`: development-only, rollback-only PostgreSQL acceptance for Dashboard/Trash/creator-profile security metadata, exact ACLs, owner isolation, state filters, field validation, cover eligibility, identity guards, and fixture cleanup.
- `database/migrations/20260717_review_queue.sql`: transaction-wrapped Phase 3 Review Queue/RLS/Storage/RPC boundary for scoped list/detail, atomic assignment/start, versioned idempotent decisions, notifications, publication state, and append-only audit evidence.
- `database/migrations/20260729_super_admin_self_publish.sql`: transaction-wrapped, authenticated-only Super Admin+AAL2 owner self-publish RPC with untouched/unassigned Submitted, CAS, readiness, current-clean asset, derivative visibility, idempotency, notification, and dedicated audit gates.
- `scripts/validate_review_queue_phase3.py`: static Review Queue contract validator for SQL permissions, server/UI boundary, project documentation, and CI wiring.
- `scripts/test_review_queue_boundary.py`: secret-free fake-provider HTTP integration for identity/MFA/CSRF, queue/detail scopes, DTO allowlists, conflicts, idempotency, and Admin publish prechecks.
- `scripts/test_review_queue_database.sql`: development-only, rollback-only Review authorization/state test covering role stacking, self-review, direct RLS, current-scan Storage lifecycle, CAS, immutable replay snapshots across later Publish, notification, and audit evidence.
- `scripts/test_review_queue_concurrency.py`: development-only committed-fixture test that synchronizes independent PostgreSQL sessions for Start/claim, decision CAS, and same-key replay races, then removes all fixtures.
- `database/migrations/20260723_admin_works_governance.sql`: transaction-wrapped Admin Works list/detail/governance RPCs, exact derivative Storage policy, versioned idempotent Takedown/Restore, notification/takedown/audit transaction, immutable governance actions, and failure audit.
- `scripts/validate_admin_works.py` / `scripts/test_admin_works_boundary.py`: static and secret-free Fake Supabase HTTP contracts for Admin/AAL2, strict DTOs, exact signed paths, CSRF, conflicts, failure history, and cross-record rejection.
- `scripts/test_admin_works_database.py`: development-only rollback acceptance for function ACLs, role/AAL/recovery, Storage RLS, list/detail, versioned/idempotent governance, legal hold, restore asset gate, failure audit, append-only enforcement, and independent fixture absence.
- `database/migrations/20260723_b_admin_user_governance.sql`: transaction-wrapped Admin User read model and governance RPCs, versioned users, baseline-role repair, immutable actions, exact ACLs, global last-Super-Admin serialization, notifications, and success/failure audit.
- `scripts/validate_admin_users.py` / `scripts/test_admin_users_boundary.py`: static and secret-free Fake Supabase HTTP contracts for page/API guards, AAL2/recovery, strict DTO and relationship binding, CSRF, CAS/idempotency, provider drift, role scope, and truthful provider-managed session semantics.
- `scripts/test_admin_users_database.py`: development-only rollback acceptance for exact function/table ACLs, actor/AAL/recovery boundaries, list/detail, profile-less legacy users, status/role governance, CAS/idempotency, identity/Super Admin guards, provider session intent, immutable actions, audits, and fixture absence.
- `scripts/validate_public_delivery.py` / `scripts/test_public_delivery_boundary.py`: static and secret-free Fake Supabase acceptance for anonymous published Works/creator DTOs, Admin publish visibility, derivative signing, private-field exclusion, and authoritative empty/error handling.
- `scripts/test_public_delivery_database.py`: development-only rollback acceptance for public RPC/Storage ACLs, active/published/current/clean filters, original isolation, creator/cover/status projection, and fixture cleanup.
- `docs/operations/public-delivery-testing.md`: public delivery gate, development database procedure, required markers, and signed-URL revocation-window runbook.
- `database/local_archive_schema.sql`: SQLite schema for local Works Archive database verification.
- `scripts/seed_local_archive_db.py`: seeds `data/archive.db` from `archive-data.js`.
- `scripts/validate_local_archive_db.py`: validates the local SQLite archive workflow in a temporary database.
- `scripts/test_auth_security_boundary.py`: secret-free local integration test for CSRF, account recovery, profile read/write, session revocation, Workspace/Account route guards, Admin MFA, and private legacy originals.
- `scripts/test_workspace_phase2_boundary.py`: secret-free fake-provider integration test for Folder/upload/Draft boundaries plus readiness states, CSRF, stale Submit, idempotent success, immutable submitted state, response allowlists, and Admin AAL1 denial.
- `scripts/validate_workspace_phase2.py`: static contract validator for the Phase 2A-2E schema, migrations, API routes, resilient browser queue, Draft autosave/conflict, readiness/Submit state machine, RPC permissions, Works public shell/account-menu Workspace destination, and CI wiring.
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
- `database/migrations/`: ordered, transaction-wrapped patches for existing environments, including Admin hardening, strict Account Settings, private Draft/Folders/Storage, cancellation/cleanup, compliance metadata, optimistic versioning/Folder integrity, authoritative readiness/submission snapshots, trusted leased asset scanning, Review decisions, Dashboard/creator settings, published-only public delivery, Admin Works governance, and Admin User governance.
- `scripts/validate_product_phase0.py`: validates the Phase 0 schema contract and confirms public pages expose neither Series/Collections nor the retired public rail, and all load the unified public header/account/mobile-navigation contract.
- `scripts/validate_interaction_integrity.py`: enforces original-node Works favorites, explicit Inquiry Selection handoff, server-rendered Header Identity, and top-navigation Review contracts.
- `scripts/test_public_interaction_state.js`: dependency-free state regression for persistent Lightbox favorites, session Inquiry Selection, and automatic selection pruning.
- `scripts/test_header_identity_boundary.py`: verifies signed profile avatars are reissued through the authenticated Storage boundary and rejects origin or object-path substitution.
- `scripts/validate_profile_avatar.py`: enforces the private Storage, owner binding, strict browser DTO, image preparation, lifecycle API, shared Header Identity synchronization, accessibility, and reduced-motion contracts for profile photos.
- `scripts/test_profile_avatar_browser.py`: development-only real Supabase/Storage browser acceptance using a disposable member; verifies center-cropped upload, immediate Header Identity synchronization, refresh persistence, UI removal, session close, and complete fixture cleanup without logging credentials or signed object coordinates.
- `scripts/test_review_queue_browser.py`: development-only disposable Reviewer/Admin browser acceptance for claim isolation, Request Changes, Admin AAL2 Approve, exact Reviewer-versus-Admin private asset visibility, responsive/focus/console contracts, and complete session/Storage/database cleanup.
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
