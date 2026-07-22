#!/usr/bin/env python3
"""Development-only, two-session concurrency acceptance for Review Queue RPCs.

The test commits fixed disposable fixtures so independent PostgreSQL sessions can
race on the same rows. A process-held advisory lock prevents overlapping test
runs, and cleanup runs both before setup and in ``finally`` so an interrupted
run is recoverable on the next invocation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
RUN_LOCK = 77001700
START_GATE = 77001701
DECISION_GATE = 77001702
REPLAY_GATE = 77001703

OWNER_ID = "00000000-0000-4000-8000-00000000f401"
REVIEWER_A_ID = "00000000-0000-4000-8000-00000000f402"
REVIEWER_B_ID = "00000000-0000-4000-8000-00000000f403"
USER_IDS = (OWNER_ID, REVIEWER_A_ID, REVIEWER_B_ID)

IMAGE_IDS = (
    "00000000-0000-4000-8000-00000000f411",
    "00000000-0000-4000-8000-00000000f412",
    "00000000-0000-4000-8000-00000000f413",
)
VERSION_IDS = (
    "00000000-0000-4000-8000-00000000f421",
    "00000000-0000-4000-8000-00000000f422",
    "00000000-0000-4000-8000-00000000f423",
)
SUBMISSION_IDS = (
    "00000000-0000-4000-8000-00000000f431",
    "00000000-0000-4000-8000-00000000f432",
    "00000000-0000-4000-8000-00000000f433",
)

CHECKLIST = {
    "file_integrity": True,
    "rights": True,
    "privacy": True,
    "minors": True,
    "sensitive_content": True,
    "hate_illegal": True,
    "property_release": True,
    "third_party_ip": True,
    "ai_disclosure": True,
    "public_metadata": True,
}


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def require_development_environment() -> None:
    if os.environ.get("MT_TEST_ENVIRONMENT") != "development":
        raise RuntimeError(
            "Refusing committed concurrency fixtures without MT_TEST_ENVIRONMENT=development"
        )
    if os.environ.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError("Refusing Review concurrency fixtures while production approval is enabled")
    missing = [
        name
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required database environment variables: {', '.join(missing)}")


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required for the Review concurrency test")


def psql_command() -> list[str]:
    return [psql_binary(), "--no-psqlrc", "--quiet", "--no-align", "--tuples-only"]


def run_sql(command: str, *, timeout: float = 30.0) -> str:
    completed = subprocess.run(
        psql_command(),
        input=command,
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("Review concurrency database operation failed")
    return completed.stdout.strip()


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def cleanup_sql() -> str:
    users = sql_values(USER_IDS)
    images = sql_values(IMAGE_IDS)
    submissions = sql_values(SUBMISSION_IDS)
    return f"""
begin;
set local lock_timeout = '10s';
alter table public.audit_logs disable trigger audit_logs_append_only;
alter table public.review_decisions disable trigger review_decisions_append_only;
alter table public.review_submissions disable trigger review_submissions_snapshot_immutable;
alter table public.image_versions disable trigger image_versions_locked_immutable;
delete from public.audit_logs
where target_type = 'review_submission' and target_id in ({submissions});
delete from public.notifications
where payload ->> 'submission_id' in ({submissions});
delete from public.review_decisions where submission_id in ({submissions});
delete from public.review_submissions where id in ({submissions});
update public.images set current_version_id = null where id in ({images});
delete from public.image_versions where image_id in ({images});
delete from public.images where id in ({images});
delete from public.folders where owner_user_id in ({users});
delete from public.user_roles where user_id in ({users});
delete from public.user_profiles where user_id in ({users});
delete from public.users where id in ({users});
alter table public.image_versions enable trigger image_versions_locked_immutable;
alter table public.review_submissions enable trigger review_submissions_snapshot_immutable;
alter table public.review_decisions enable trigger review_decisions_append_only;
alter table public.audit_logs enable trigger audit_logs_append_only;
commit;
"""


def setup_sql() -> str:
    return f"""
begin;
set local lock_timeout = '10s';
insert into public.users (id, auth_subject, email, email_verified_at, account_status) values
  ('{OWNER_ID}', '{OWNER_ID}', 'phase3-race-owner@example.test', now(), 'active'),
  ('{REVIEWER_A_ID}', '{REVIEWER_A_ID}', 'phase3-race-reviewer-a@example.test', now(), 'active'),
  ('{REVIEWER_B_ID}', '{REVIEWER_B_ID}', 'phase3-race-reviewer-b@example.test', now(), 'active');
insert into public.user_profiles (user_id, display_name) values
  ('{OWNER_ID}', 'Phase 3 Race Owner'),
  ('{REVIEWER_A_ID}', 'Phase 3 Race Reviewer A'),
  ('{REVIEWER_B_ID}', 'Phase 3 Race Reviewer B');
insert into public.user_roles (user_id, role, reason) values
  ('{OWNER_ID}', 'user', 'phase3 concurrency test'),
  ('{REVIEWER_A_ID}', 'user', 'phase3 concurrency test'),
  ('{REVIEWER_A_ID}', 'reviewer', 'phase3 concurrency test'),
  ('{REVIEWER_B_ID}', 'user', 'phase3 concurrency test'),
  ('{REVIEWER_B_ID}', 'reviewer', 'phase3 concurrency test');
insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('00000000-0000-4000-8000-00000000f471', '{OWNER_ID}', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f472', '{REVIEWER_A_ID}', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f473', '{REVIEWER_B_ID}', 'Inbox', 0, true);
insert into public.images (
  id, owner_user_id, folder_id, processing_status, workflow_status,
  publication_status, original_filename, original_width, original_height,
  checksum_sha256, version
) values
  ('{IMAGE_IDS[0]}', '{OWNER_ID}', '00000000-0000-4000-8000-00000000f471',
   'ready', 'submitted', 'never_published', 'phase3-start-race.jpg', 1600, 1200,
   repeat('a', 64), 1),
  ('{IMAGE_IDS[1]}', '{OWNER_ID}', '00000000-0000-4000-8000-00000000f471',
   'ready', 'in_review', 'never_published', 'phase3-decision-race.jpg', 1600, 1200,
   repeat('b', 64), 2),
  ('{IMAGE_IDS[2]}', '{OWNER_ID}', '00000000-0000-4000-8000-00000000f471',
   'ready', 'in_review', 'never_published', 'phase3-replay-race.jpg', 1600, 1200,
   repeat('c', 64), 2);
insert into public.image_versions (
  id, image_id, version_number, title, alt_text, content_category,
  copyright_holder, copyright_year, contains_recognizable_people,
  model_release_status, property_release_status, rights_declared,
  ai_disclosure, sensitive_content_disclosure, created_by_user_id, locked_at
) values
  ('{VERSION_IDS[0]}', '{IMAGE_IDS[0]}', 1, 'Start race', 'Start race fixture.', 'concrete',
   'Phase 3 Race Owner', 2026, false, 'not_applicable', 'not_applicable', true,
   'none', 'none', '{OWNER_ID}', now()),
  ('{VERSION_IDS[1]}', '{IMAGE_IDS[1]}', 1, 'Decision race', 'Decision race fixture.', 'concrete',
   'Phase 3 Race Owner', 2026, false, 'not_applicable', 'not_applicable', true,
   'none', 'none', '{OWNER_ID}', now()),
  ('{VERSION_IDS[2]}', '{IMAGE_IDS[2]}', 1, 'Replay race', 'Replay race fixture.', 'concrete',
   'Phase 3 Race Owner', 2026, false, 'not_applicable', 'not_applicable', true,
   'none', 'none', '{OWNER_ID}', now());
update public.images set current_version_id = case id
  when '{IMAGE_IDS[0]}' then '{VERSION_IDS[0]}'::uuid
  when '{IMAGE_IDS[1]}' then '{VERSION_IDS[1]}'::uuid
  else '{VERSION_IDS[2]}'::uuid
end
where id in ({sql_values(IMAGE_IDS)});
insert into public.review_submissions (
  id, image_id, image_version_id, submitted_by_user_id, idempotency_key,
  status, assigned_reviewer_id, policy_version, lock_version,
  readiness_snapshot, asset_snapshot, review_started_at
) values
  ('{SUBMISSION_IDS[0]}', '{IMAGE_IDS[0]}', '{VERSION_IDS[0]}', '{OWNER_ID}',
   '00000000-0000-4000-8000-00000000f451', 'submitted', null,
   'mt-review-2026-07-v1', 1, '{{"ready":true,"checks":[{{}},{{}},{{}},{{}},{{}}]}}',
   '[{{}},{{}},{{}}]', null),
  ('{SUBMISSION_IDS[1]}', '{IMAGE_IDS[1]}', '{VERSION_IDS[1]}', '{OWNER_ID}',
   '00000000-0000-4000-8000-00000000f452', 'in_review', '{REVIEWER_A_ID}',
   'mt-review-2026-07-v1', 2, '{{"ready":true,"checks":[{{}},{{}},{{}},{{}},{{}}]}}',
   '[{{}},{{}},{{}}]', now()),
  ('{SUBMISSION_IDS[2]}', '{IMAGE_IDS[2]}', '{VERSION_IDS[2]}', '{OWNER_ID}',
   '00000000-0000-4000-8000-00000000f453', 'in_review', '{REVIEWER_A_ID}',
   'mt-review-2026-07-v1', 2, '{{"ready":true,"checks":[{{}},{{}},{{}},{{}},{{}}]}}',
   '[{{}},{{}},{{}}]', now());
commit;
"""


def claims_sql(actor_id: str) -> str:
    claims = json.dumps(
        {
            "sub": actor_id,
            "role": "authenticated",
            "aal": "aal1",
            "amr": [{"method": "password"}],
        },
        separators=(",", ":"),
    ).replace("'", "''")
    return f"do $$ begin perform set_config('request.jwt.claims', '{claims}', true); end $$;"


def decision_call(submission_id: str, request_key: str) -> str:
    checklist = json.dumps(CHECKLIST, separators=(",", ":"))
    return (
        "public.review_decide_submission("
        f"'{submission_id}', 2, 'reject', '[\"content_policy\"]'::jsonb, "
        "'Rejected by the concurrency acceptance.', 'Concurrency test.', "
        f"'{checklist}'::jsonb, '{request_key}')"
    )


def race_sql(label: str, actor_id: str, gate: int, call: str) -> str:
    return f"""
begin;
set local statement_timeout = '20s';
{claims_sql(actor_id)}
set local role authenticated;
select 'READY:{label}:' || pg_backend_pid();
select pg_advisory_lock_shared({gate});
select pg_advisory_unlock_shared({gate});
select 'RESULT:' || ({call})::text;
commit;
"""


def wait_for_prefix(stream: TextIO, prefix: str, timeout: float = 10.0) -> str:
    selector = selectors.DefaultSelector()
    selector.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ready = selector.select(max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            line = stream.readline()
            if not line:
                break
            value = line.strip()
            if value.startswith(prefix):
                return value
    finally:
        selector.close()
    raise RuntimeError(f"Timed out waiting for Review concurrency marker: {prefix}")


class Controller:
    def __init__(self) -> None:
        self.process = subprocess.Popen(
            psql_command(),
            cwd=ROOT,
            env=os.environ.copy(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Could not open the Review concurrency controller session")

    def send(self, command: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(command.rstrip() + "\n")
        self.process.stdin.flush()

    def wait(self, prefix: str) -> str:
        assert self.process.stdout is not None
        return wait_for_prefix(self.process.stdout, prefix)

    def close(self) -> None:
        if self.process.poll() is None and self.process.stdin is not None:
            try:
                self.send("select pg_advisory_unlock_all();")
                self.send("\\q")
                self.process.stdin.close()
                self.process.stdin = None
                self.process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)


def acquire_run_lock(controller: Controller) -> None:
    controller.send(
        f"select case when pg_try_advisory_lock({RUN_LOCK}) "
        "then 'RUN_LOCKED' else 'RUN_BUSY' end;"
    )
    marker = controller.wait("RUN_")
    if marker != "RUN_LOCKED":
        raise RuntimeError("Another Review concurrency test is already running")


def run_race(controller: Controller, gate: int, racers: list[tuple[str, str]]) -> tuple[list[int], list[dict]]:
    controller.send(f"select pg_advisory_lock({gate}); select 'GATE_READY:{gate}';")
    controller.wait(f"GATE_READY:{gate}")
    processes: list[subprocess.Popen[str]] = []
    backend_ids: list[int] = []
    results: list[dict] = []
    gate_released = False
    try:
        for label, command in racers:
            process = subprocess.Popen(
                psql_command(),
                cwd=ROOT,
                env=os.environ.copy(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Could not open a Review race session")
            process.stdin.write(command)
            process.stdin.flush()
            processes.append(process)

        for (label, _), process in zip(racers, processes, strict=True):
            assert process.stdout is not None
            marker = wait_for_prefix(process.stdout, f"READY:{label}:")
            backend_ids.append(int(marker.rsplit(":", 1)[1]))

        if len(set(backend_ids)) != len(backend_ids):
            raise RuntimeError("Review race did not use distinct PostgreSQL backends")

        controller.send(f"select pg_advisory_unlock({gate}); select 'GATE_RELEASED:{gate}';")
        controller.wait(f"GATE_RELEASED:{gate}")
        gate_released = True

        for process in processes:
            if process.stdin is not None:
                process.stdin.close()
                process.stdin = None
            output, _ = process.communicate(timeout=25)
            if process.returncode:
                raise RuntimeError("A Review race session failed")
            result_line = next(
                (line.strip() for line in output.splitlines() if line.strip().startswith("RESULT:")),
                "",
            )
            if not result_line:
                raise RuntimeError("A Review race session returned no result")
            results.append(json.loads(result_line.removeprefix("RESULT:")))
    finally:
        if not gate_released:
            try:
                controller.send(f"select pg_advisory_unlock({gate});")
            except (BrokenPipeError, OSError):
                pass
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return backend_ids, results


def error_code(result: dict) -> str:
    error = result.get("error")
    return str(error.get("code") or "") if isinstance(error, dict) else ""


def assert_start_race(results: list[dict]) -> None:
    successes = [result for result in results if result.get("submission", {}).get("status") == "in_review"]
    conflicts = [result for result in results if error_code(result) == "REVIEW_VERSION_CONFLICT"]
    if len(successes) != 1 or len(conflicts) != 1:
        raise RuntimeError("Atomic Start/claim race did not produce one winner and one CAS conflict")
    winner = successes[0]["submission"]
    if winner.get("assigned_reviewer_id") not in {REVIEWER_A_ID, REVIEWER_B_ID}:
        raise RuntimeError("Atomic Start/claim race assigned an unexpected reviewer")
    if winner.get("lock_version") != 2:
        raise RuntimeError("Atomic Start/claim race returned the wrong lock version")
    state = json.loads(run_sql(f"""
select json_build_object(
  'submission_status', s.status,
  'assigned_reviewer_id', s.assigned_reviewer_id,
  'submission_lock_version', s.lock_version,
  'workflow_status', i.workflow_status,
  'image_lock_version', i.version,
  'notifications', (select count(*) from public.notifications n where n.payload ->> 'submission_id' = s.id::text and n.type = 'image_review_started'),
  'audits', (select count(*) from public.audit_logs a where a.target_id = s.id::text and a.action = 'review.start')
)::text
from public.review_submissions s join public.images i on i.id = s.image_id
where s.id = '{SUBMISSION_IDS[0]}';
"""))
    expected = {
        "submission_status": "in_review",
        "assigned_reviewer_id": winner["assigned_reviewer_id"],
        "submission_lock_version": 2,
        "workflow_status": "in_review",
        "image_lock_version": 2,
        "notifications": 1,
        "audits": 1,
    }
    if state != expected:
        raise RuntimeError("Atomic Start/claim race committed inconsistent state or duplicate side effects")


def assert_decision_cas_race(results: list[dict]) -> None:
    successes = [result for result in results if result.get("submission", {}).get("status") == "rejected"]
    conflicts = [result for result in results if error_code(result) == "REVIEW_VERSION_CONFLICT"]
    if len(successes) != 1 or len(conflicts) != 1:
        raise RuntimeError("Decision CAS race did not produce one winner and one version conflict")
    state = json.loads(run_sql(f"""
select json_build_object(
  'submission_status', s.status,
  'submission_lock_version', s.lock_version,
  'workflow_status', i.workflow_status,
  'image_lock_version', i.version,
  'decisions', (select count(*) from public.review_decisions d where d.submission_id = s.id),
  'notifications', (select count(*) from public.notifications n where n.payload ->> 'submission_id' = s.id::text and n.type = 'image_rejected'),
  'audits', (select count(*) from public.audit_logs a where a.target_id = s.id::text and a.action = 'review.reject')
)::text
from public.review_submissions s join public.images i on i.id = s.image_id
where s.id = '{SUBMISSION_IDS[1]}';
"""))
    expected = {
        "submission_status": "rejected",
        "submission_lock_version": 3,
        "workflow_status": "rejected",
        "image_lock_version": 3,
        "decisions": 1,
        "notifications": 1,
        "audits": 1,
    }
    if state != expected:
        raise RuntimeError("Decision CAS race committed inconsistent state or duplicate side effects")


def assert_replay_race(results: list[dict]) -> None:
    if len(results) != 2 or results[0] != results[1]:
        raise RuntimeError("Concurrent same-key decision replay did not return one stable result")
    if results[0].get("submission", {}).get("status") != "rejected":
        raise RuntimeError("Concurrent same-key decision replay did not return the committed decision")
    state = json.loads(run_sql(f"""
select json_build_object(
  'submission_status', s.status,
  'submission_lock_version', s.lock_version,
  'decisions', (select count(*) from public.review_decisions d where d.submission_id = s.id),
  'distinct_keys', (select count(distinct d.idempotency_key) from public.review_decisions d where d.submission_id = s.id),
  'notifications', (select count(*) from public.notifications n where n.payload ->> 'submission_id' = s.id::text and n.type = 'image_rejected'),
  'audits', (select count(*) from public.audit_logs a where a.target_id = s.id::text and a.action = 'review.reject')
)::text
from public.review_submissions s
where s.id = '{SUBMISSION_IDS[2]}';
"""))
    expected = {
        "submission_status": "rejected",
        "submission_lock_version": 3,
        "decisions": 1,
        "distinct_keys": 1,
        "notifications": 1,
        "audits": 1,
    }
    if state != expected:
        raise RuntimeError("Concurrent same-key replay created duplicate decision side effects")


def assert_cleaned() -> None:
    counts = run_sql(f"""
select
  (select count(*) from public.users where id in ({sql_values(USER_IDS)})) +
  (select count(*) from public.images where id in ({sql_values(IMAGE_IDS)})) +
  (select count(*) from public.review_submissions where id in ({sql_values(SUBMISSION_IDS)}));
""")
    if counts != "0":
        raise RuntimeError("Review concurrency fixtures remain after cleanup")


def main() -> None:
    load_dotenv()
    require_development_environment()
    controller = Controller()
    acquired = False
    all_backend_ids: list[int] = []
    try:
        acquire_run_lock(controller)
        acquired = True
        run_sql(cleanup_sql())
        run_sql(setup_sql())

        start_backends, start_results = run_race(
            controller,
            START_GATE,
            [
                (
                    "start-a",
                    race_sql(
                        "start-a",
                        REVIEWER_A_ID,
                        START_GATE,
                        f"public.review_start_submission('{SUBMISSION_IDS[0]}', 1)",
                    ),
                ),
                (
                    "start-b",
                    race_sql(
                        "start-b",
                        REVIEWER_B_ID,
                        START_GATE,
                        f"public.review_start_submission('{SUBMISSION_IDS[0]}', 1)",
                    ),
                ),
            ],
        )
        all_backend_ids.extend(start_backends)
        assert_start_race(start_results)

        decision_backends, decision_results = run_race(
            controller,
            DECISION_GATE,
            [
                (
                    "decision-a",
                    race_sql(
                        "decision-a",
                        REVIEWER_A_ID,
                        DECISION_GATE,
                        decision_call(
                            SUBMISSION_IDS[1],
                            "00000000-0000-4000-8000-00000000f461",
                        ),
                    ),
                ),
                (
                    "decision-b",
                    race_sql(
                        "decision-b",
                        REVIEWER_A_ID,
                        DECISION_GATE,
                        decision_call(
                            SUBMISSION_IDS[1],
                            "00000000-0000-4000-8000-00000000f462",
                        ),
                    ),
                ),
            ],
        )
        all_backend_ids.extend(decision_backends)
        assert_decision_cas_race(decision_results)

        replay_key = "00000000-0000-4000-8000-00000000f463"
        replay_backends, replay_results = run_race(
            controller,
            REPLAY_GATE,
            [
                (
                    "replay-a",
                    race_sql(
                        "replay-a",
                        REVIEWER_A_ID,
                        REPLAY_GATE,
                        decision_call(SUBMISSION_IDS[2], replay_key),
                    ),
                ),
                (
                    "replay-b",
                    race_sql(
                        "replay-b",
                        REVIEWER_A_ID,
                        REPLAY_GATE,
                        decision_call(SUBMISSION_IDS[2], replay_key),
                    ),
                ),
            ],
        )
        all_backend_ids.extend(replay_backends)
        assert_replay_race(replay_results)
        if len(all_backend_ids) != 6:
            raise RuntimeError("Review concurrency test did not complete all six database sessions")
    finally:
        if acquired:
            try:
                run_sql(cleanup_sql())
            finally:
                controller.close()
        else:
            controller.close()

    assert_cleaned()
    print("review_concurrency_start_claim_race=yes")
    print("review_concurrency_decision_cas_race=yes")
    print("review_concurrency_same_key_replay=yes")
    print("review_concurrency_distinct_backends=yes")
    print("review_concurrency_fixtures_cleaned=yes")


if __name__ == "__main__":
    main()
