# Admin Review Queue Testing

## Scope

The Phase 3 Review Queue slice connects protected reviewer tooling to Supabase `review_submissions` without reusing the legacy SQLite `manage.html` workflow.

Included:

- protected `/admin/reviews` and `/admin/reviews/{submissionId}` routes;
- status and assignment filters with bounded pagination;
- queue counts, compact submission summaries, and signed thumbnail previews;
- atomic reviewer claim/start, optimistic `lock_version` checks, and immutable review decisions;
- Request Changes, Reject, and Approve UI for Reviewer;
- Admin/Super Admin+AAL2-only browser and database/API boundary for `approve_and_publish`;
- signed, short-lived access to submitted private assets;
- notifications and append-only audit evidence.

The browser exposes Approve and publish only to Admin/Super Admin sessions at AAL2. That action is connected to the strict Supabase public DTO and derivative delivery; Reviewer Approve remains unpublished, and the production public path never falls back to the legacy SQLite archive.

## Authorization Matrix

| Identity | Queue list | Submission detail/assets | Decision |
| --- | --- | --- | --- |
| Anonymous / normal user | Denied | Denied | Denied |
| Recovery session | Denied | Denied | Denied |
| Pure Reviewer | Unassigned waiting items and their own open assignments, excluding their submissions | Own open non-self assignment only | Request Changes, Reject, or Approve on own active non-self assignment; no publish |
| Admin or Super Admin at AAL1 | Denied | Denied | Denied |
| Admin or Super Admin at AAL2 | Full queue/history, including read-only visibility of own submissions | Full authorized review history | Supported Admin actions including Approve and publish, but never self-review |

Role stacking must not let an Admin who also has `reviewer` bypass AAL2. Self-review is denied in assignment, start, and decision RPCs for every role; a future override would require a separate, explicitly audited policy action.

## Local Contract Tests

Run the focused checks before browser testing:

```bash
python3 scripts/validate_review_queue_phase3.py
python3 scripts/test_review_queue_boundary.py
python3 -m py_compile scripts/test_review_queue_concurrency.py
node --check admin-reviews.js
python3 scripts/test_supabase_deploy_script.py
```

The validator checks the SQL/RLS/RPC, page/client/API, project-map, and CI contracts. It is a static contract check and cannot prove that PostgreSQL can parse or compile the migration; a real development-database apply remains mandatory. The secret-free HTTP test uses a loopback fake provider and must not print access tokens, private Storage keys, signed URLs, user messages, or internal notes.

## Development Deployment

Apply the ordered migration to an existing development database only after local checks pass:

```bash
MT_APPLY_PHASE1_BASELINE=no \
MT_DEPLOY_ENVIRONMENT=development \
bash scripts/deploy_supabase_phase1.sh
```

Do not run the production mode without the existing explicit release confirmation. The migration must remain transaction-wrapped and safe to replay through the ordered deployment script.

After deployment, run the rollback-only database acceptance with development `PG*` variables loaded:

```bash
psql --set ON_ERROR_STOP=1 --file scripts/test_review_queue_database.sql
```

The script uses fixed development-only UUIDs under an advisory transaction lock, restores the scanner trigger before completion, and always ends with `ROLLBACK`. It must print `review_database_fixtures_rolled_back=yes`.

Then run the committed-fixture two-session acceptance. This test requires an explicit development confirmation, holds a process-level advisory lock to prevent overlapping runs, synchronizes each pair of PostgreSQL backends behind a shared gate, and cleans fixed fixture identities before and after the run:

```bash
MT_TEST_ENVIRONMENT=development python3 scripts/test_review_queue_concurrency.py
```

It must print all five `review_concurrency_*=yes` markers, including `review_concurrency_distinct_backends=yes` and `review_concurrency_fixtures_cleaned=yes`. Never set `MT_TEST_ENVIRONMENT=development` for a production database.

## Real Browser Acceptance

Secret-free fake-provider acceptance passed on 2026-07-20 at `1440 x 1000` and `390 x 844`: signed images rendered, mobile document width matched the viewport, missing fields/checklist restored useful focus, the confirmation dialog focused Cancel and restored its opener on Escape, and the browser reported no console/page errors.

The real disposable Reviewer/Admin multi-identity acceptance passed on 2026-07-22. It is development-only, creates disposable Auth/database fixtures, holds an advisory run lock, and removes its sessions and fixtures before reporting success:

```bash
MT_TEST_ENVIRONMENT=development python3 scripts/test_review_queue_browser.py
```

The successful run verified:

- Reviewer A atomically claimed an unassigned non-self submission before private detail access;
- Reviewer B was denied cross-assignment detail and could not overwrite Reviewer A;
- Reviewer A completed Request Changes against the immutable submitted version;
- an Admin at AAL2 completed Approve without bypassing the self-review boundary;
- `display`, `original`, and `thumbnail` private variants loaded from the signed provider origin;
- desktop/mobile responsive bounds, checklist error focus, confirmation-dialog focus restoration, and console/page errors stayed clean;
- every browser session closed and all disposable users, submissions, assets, decisions, notifications, audit rows, and Storage objects were cleaned;
- `review_browser_state_persisted=no`, `credentials_logged=no`, `review_browser_failure_stage=none`, and `review_browser_acceptance=yes`.

Never run this fixture workflow against production. A passing result requires both `review_browser_sessions_closed=yes` and `review_browser_fixtures_cleaned=yes`; a functional assertion alone is insufficient.

## Database Acceptance Before Release

The rollback-only development test passed on 2026-07-20. It covers:

- User, Reviewer, Admin AAL1, Admin AAL2, and stacked-role direct table/RPC/Storage access;
- self-review rejection for assignment, start, approval, and future publish actions;
- clean/current scan-policy revocation at Queue Detail and Storage object access;
- same-key/same-payload idempotency and same-key/different-payload conflict;
- stable same-payload replay after a later Admin Publish changes live state;
- exact audit `before_state` / `after_state` values;
- terminal-state and stale-version rejection;
- Storage access revocation after a Reviewer assignment leaves the open-review state.

The two-session development concurrency test passed on 2026-07-20. It used six independent `psql` sessions across three synchronized races and verified that each competing pair had distinct PostgreSQL backend PIDs:

- two disposable Reviewer identities racing the same atomic Start/claim produce one winner and one version conflict;
- two decision requests with different keys at the same expected version produce one decision and one CAS conflict;
- two same-key/same-payload decisions return the same immutable result with exactly one decision, notification, and audit row;
- all committed fixture users, images, submissions, decisions, notifications, and audit rows are removed afterward.

The database, concurrency, fake-provider, and real disposable multi-identity browser gates are complete. Never run any fixture test against production, and always verify the rollback and cleanup markers. Public derivative delivery, Supabase-backed Works, the public creator profile, and browser-exposed Admin+AAL2 Approve and publish are now covered by the separate public-delivery gate.

## Explicit Non-goals

- Escalate, Quarantine, Withdraw, appeal, and legal-hold workflows;
- risk/date/category/release filters beyond the first status/assignment queue slice;
- bulk assignment or bulk approval;
- production notification delivery and scheduled SLA monitoring.
