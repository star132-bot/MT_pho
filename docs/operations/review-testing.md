# Admin Review Queue Testing

## Scope

The Phase 3 Review Queue slice connects protected reviewer tooling to Supabase `review_submissions` without reusing the legacy SQLite `manage.html` workflow.

Included:

- protected `/admin/reviews` and `/admin/reviews/{submissionId}` routes;
- status and assignment filters with bounded pagination;
- queue counts, compact submission summaries, and signed thumbnail previews;
- atomic reviewer claim/start, optimistic `lock_version` checks, and immutable review decisions;
- Request Changes, Reject, and Approve UI;
- Admin+AAL2-only database/API boundary for `approve_and_publish`;
- signed, short-lived access to submitted private assets;
- notifications and append-only audit evidence.

The browser does **not** expose Approve and Publish yet. The public Works page still reads the legacy SQLite archive, so enabling that action before Supabase public DTO and derivative delivery are connected would create a false publication promise.

## Authorization Matrix

| Identity | Queue list | Submission detail/assets | Decision |
| --- | --- | --- | --- |
| Anonymous / normal user | Denied | Denied | Denied |
| Recovery session | Denied | Denied | Denied |
| Pure Reviewer | Unassigned waiting items and their own open assignments, excluding their submissions | Own open non-self assignment only | Own active non-self assignment only |
| Admin or Super Admin at AAL1 | Denied | Denied | Denied |
| Admin or Super Admin at AAL2 | Full queue/history, including read-only visibility of own submissions | Full authorized review history | Supported Admin actions, but never self-review |

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

## Manual Browser Acceptance

Secret-free fake-provider acceptance passed on 2026-07-20 at `1440 x 1000` and `390 x 844`: signed images rendered, mobile document width matched the viewport, missing fields/checklist restored useful focus, the confirmation dialog focused Cancel and restored its opener on Escape, and the browser reported no console/page errors. Real disposable Reviewer/Admin sessions remain required before release.

1. Start the current server and sign in with a disposable Reviewer or Admin test identity.
2. Open `/admin/reviews`.
3. Verify loading, empty, error, queue, and detail states without horizontal overflow at `1440 × 900` and `390 × 844`.
4. As a pure Reviewer, open an unassigned waiting item and confirm the start request claims it atomically before private detail assets load.
5. Open the same submission in a second reviewer session; the second actor must not receive the detail or overwrite the assignment.
6. Submit a stale `expected_version`; the UI must preserve the decision form and offer a reload path.
7. Retry the same decision key with the same payload; it must return the original complete result and create one decision, notification, and audit event.
8. Reuse that key with a different payload; it must return an idempotency conflict.
9. Confirm Request Changes creates a new editable version while preserving the immutable submitted version.
10. Confirm the dialog restores focus to its trigger, errors are announced, and controls remain disabled during an in-flight mutation.

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

The remaining Phase 3 release gate is real disposable Reviewer/Admin browser acceptance. Never run either database fixture test against production, and always verify the rollback and cleanup markers.

## Explicit Non-goals

- public Works data-source migration and public derivative delivery;
- browser-exposed Approve and Publish;
- Escalate, Quarantine, Withdraw, appeal, and legal-hold workflows;
- risk/date/category/release filters beyond the first status/assignment queue slice;
- bulk assignment or bulk approval;
- production notification delivery and scheduled SLA monitoring.
