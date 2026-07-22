#!/usr/bin/env python3
"""Development-only real-browser acceptance for the Phase 3 Review Queue.

The test intentionally commits short-lived fixtures so three independent
agent-browser sessions can exercise the real Supabase Auth, PostgREST, and
private Storage boundaries through ``server.py``.  A process-held advisory
lock prevents overlapping runs.  Fixed object paths and fixture UUIDs make an
interrupted run recoverable by the next invocation.

Stdout contains only stable yes/no markers.  Provider bodies, browser output,
credentials, tokens, TOTP material, private keys, and Storage keys are never
printed.  Every cleanup action is attempted independently in ``finally``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import time
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
WEB_ENV_PATH = ROOT / ".env"
WORKER_ENV_PATH = ROOT / ".env.worker"
JPEG_PATH = ROOT / "assets" / "uploads" / "upload-1783242881490-0" / "thumbnail-pexels-cmonphotography-1809701-2.jpg"

RUN_LOCK = 77001800
OWNER_ID = "00000000-0000-4000-8000-00000000f501"
FOLDER_ID = "00000000-0000-4000-8000-00000000f571"
IMAGE_IDS = (
    "00000000-0000-4000-8000-00000000f511",
    "00000000-0000-4000-8000-00000000f512",
)
VERSION_IDS = (
    "00000000-0000-4000-8000-00000000f521",
    "00000000-0000-4000-8000-00000000f522",
)
SUBMISSION_IDS = (
    "00000000-0000-4000-8000-00000000f531",
    "00000000-0000-4000-8000-00000000f532",
)
ASSET_IDS = (
    "00000000-0000-4000-8000-00000000f541",
    "00000000-0000-4000-8000-00000000f542",
    "00000000-0000-4000-8000-00000000f543",
    "00000000-0000-4000-8000-00000000f544",
    "00000000-0000-4000-8000-00000000f545",
    "00000000-0000-4000-8000-00000000f546",
)
SUBMIT_KEYS = (
    "00000000-0000-4000-8000-00000000f551",
    "00000000-0000-4000-8000-00000000f552",
)

REVIEWER_EMAILS = (
    "mt-phase3-browser-reviewer-a@example.com",
    "mt-phase3-browser-reviewer-b@example.com",
)
OWNER_EMAIL = "mt-phase3-browser-owner@example.test"
SESSION_NAMES = (
    "mt-phase3-browser-reviewer-a",
    "mt-phase3-browser-reviewer-b",
    "mt-phase3-browser-admin",
)
SCAN_POLICY = "mt-asset-scan-2026-07-v1"
REVIEW_POLICY = "mt-review-2026-07-v1"
ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
AGENT_BROWSER_VERSION = re.compile(r"^agent-browser 0\.13\.[0-9]+(?:[-+].*)?$")

ASSET_ROWS = (
    (ASSET_IDS[0], IMAGE_IDS[0], "original", "image-originals"),
    (ASSET_IDS[1], IMAGE_IDS[0], "display", "image-display"),
    (ASSET_IDS[2], IMAGE_IDS[0], "thumbnail", "image-thumbnails"),
    (ASSET_IDS[3], IMAGE_IDS[1], "original", "image-originals"),
    (ASSET_IDS[4], IMAGE_IDS[1], "display", "image-display"),
    (ASSET_IDS[5], IMAGE_IDS[1], "thumbnail", "image-thumbnails"),
)


def storage_key(image_id: str, kind: str) -> str:
    return f"{OWNER_ID}/phase3-browser/{image_id}/{kind}.jpg"


STORAGE_OBJECTS = tuple(
    (bucket, storage_key(image_id, kind))
    for _, image_id, kind, bucket in ASSET_ROWS
)

MARKER_ORDER = (
    "review_browser_environment_guard",
    "review_browser_reviewer_claim",
    "review_browser_second_reviewer_denied",
    "review_browser_request_changes",
    "review_browser_admin_aal2_approve",
    "review_browser_private_images_loaded",
    "review_browser_responsive_contract",
    "review_browser_focus_dialog_contract",
    "review_browser_console_clean",
    "review_browser_sessions_closed",
    "review_browser_state_persisted",
    "review_browser_fixtures_cleaned",
    "review_browser_acceptance",
    "credentials_logged",
)


class AcceptanceError(RuntimeError):
    """A deliberately non-sensitive acceptance failure."""


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


SERVICE_OPENER = urllib.request.build_opener(RejectRedirectHandler())


def read_assignments(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not ASSIGNMENT_PATTERN.fullmatch(name):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def configuration() -> dict[str, str]:
    values: dict[str, str] = {}
    values.update(read_assignments(WEB_ENV_PATH))
    values.update(read_assignments(WORKER_ENV_PATH))
    values.update({name: value for name, value in os.environ.items() if value})
    return values


def required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise AcceptanceError("configuration_missing")
    return value


def require_development(values: Mapping[str, str]) -> None:
    if not WEB_ENV_PATH.is_file() or not WORKER_ENV_PATH.is_file():
        raise AcceptanceError("environment_files_missing")
    if stat.S_IMODE(WEB_ENV_PATH.stat().st_mode) & 0o077:
        raise AcceptanceError("web_environment_not_private")
    if stat.S_IMODE(WORKER_ENV_PATH.stat().st_mode) != 0o600:
        raise AcceptanceError("worker_environment_not_private")
    web_values = read_assignments(WEB_ENV_PATH)
    worker_values = read_assignments(WORKER_ENV_PATH)
    web_url = web_values.get("SUPABASE_URL", "").strip().rstrip("/")
    worker_url = worker_values.get("SUPABASE_URL", "").strip().rstrip("/")
    configured_url = values.get("SUPABASE_URL", "").strip().rstrip("/")
    if not web_url or not worker_url or web_url != worker_url or configured_url != web_url:
        raise AcceptanceError("environment_project_mismatch")
    if values.get("MT_TEST_ENVIRONMENT") != "development":
        raise AcceptanceError("development_confirmation_required")
    if values.get("MT_ALLOW_PRODUCTION") == "yes":
        raise AcceptanceError("production_approval_present")
    url = urllib.parse.urlparse(required(values, "SUPABASE_URL").rstrip("/"))
    local_http = url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
    if (
        (url.scheme != "https" and not local_http)
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise AcceptanceError("supabase_url_invalid")
    for name in (
        "SUPABASE_PUBLISHABLE_KEY",
        "PGHOST",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "MT_DEV_ADMIN_EMAIL",
        "MT_DEV_ADMIN_PASSWORD",
    ):
        required(values, name)
    service_secret(values)
    if not JPEG_PATH.is_file():
        raise AcceptanceError("jpeg_fixture_missing")


def service_secret(values: Mapping[str, str]) -> str:
    value = (
        values.get("SUPABASE_SECRET_KEY", "").strip()
        or values.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not value or value.startswith("sb_publishable_"):
        raise AcceptanceError("service_secret_missing")
    return value


def service_headers(secret: str) -> dict[str, str]:
    headers = {"apikey": secret, "Accept": "application/json"}
    if not secret.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def request(
    url: str,
    *,
    method: str,
    headers: Mapping[str, str],
    payload: dict[str, Any] | None = None,
    body: bytes | None = None,
    expected: set[int],
    timeout: float = 30.0,
) -> dict[str, Any]:
    request_headers = dict(headers)
    data = body
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    provider_request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with SERVICE_OPENER.open(provider_request, timeout=timeout) as response:
            raw = response.read()
            if response.status not in expected:
                raise AcceptanceError("provider_status_invalid")
    except urllib.error.HTTPError as error:
        error.read()
        if error.code in expected:
            return {}
        raise AcceptanceError("provider_request_failed") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise AcceptanceError("provider_unavailable") from error
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AcceptanceError("provider_response_invalid") from error
    return parsed if isinstance(parsed, dict) else {"items": parsed}


def auth_admin_create(
    base_url: str,
    secret: str,
    email: str,
    password: str,
    display_name: str,
) -> str:
    result = request(
        f"{base_url}/auth/v1/admin/users",
        method="POST",
        headers=service_headers(secret),
        payload={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"display_name": display_name},
            "app_metadata": {"mt_fixture": "phase3-browser"},
        },
        expected={200, 201},
    )
    try:
        user = result.get("user") if isinstance(result.get("user"), dict) else result
        user_id = str(uuid.UUID(str(user["id"])))
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise AcceptanceError("auth_fixture_invalid") from error
    return user_id


def auth_admin_delete(base_url: str, secret: str, user_id: str) -> None:
    normalized = str(uuid.UUID(user_id))
    request(
        f"{base_url}/auth/v1/admin/users/{normalized}?should_soft_delete=false",
        method="DELETE",
        headers=service_headers(secret),
        expected={200, 204, 404},
    )


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.is_file():
        return str(fallback)
    raise AcceptanceError("psql_missing")


def database_environment(values: Mapping[str, str]) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "MT_DEV_ADMIN_EMAIL",
        "MT_DEV_ADMIN_PASSWORD",
    ):
        environment.pop(name, None)
    for name in (
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSSLMODE",
        "PGSSLROOTCERT",
    ):
        if values.get(name):
            environment[name] = values[name]
    environment.setdefault("PGCONNECT_TIMEOUT", "10")
    return environment


def psql_command() -> list[str]:
    return [
        psql_binary(),
        "--no-psqlrc",
        "--set",
        "ON_ERROR_STOP=1",
        "--quiet",
        "--no-align",
        "--tuples-only",
    ]


def run_sql(command: str, values: Mapping[str, str], *, timeout: float = 40.0) -> str:
    completed = subprocess.run(
        psql_command(),
        input=command,
        cwd=ROOT,
        env=database_environment(values),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        raise AcceptanceError("database_operation_failed")
    return completed.stdout.strip()


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{sql_literal(value)}'" for value in values)


def sql_storage_pairs() -> str:
    return ", ".join(
        f"('{sql_literal(bucket)}', '{sql_literal(key)}')"
        for bucket, key in STORAGE_OBJECTS
    )


class AdvisoryLock:
    def __init__(self, values: Mapping[str, str]):
        self.process = subprocess.Popen(
            psql_command(),
            cwd=ROOT,
            env=database_environment(values),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise AcceptanceError("database_lock_unavailable")

    def acquire(self) -> None:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(
            f"select case when pg_try_advisory_lock({RUN_LOCK}) then 'yes' else 'no' end;\n"
        )
        self.process.stdin.flush()
        if self.process.stdout.readline().strip() != "yes":
            raise AcceptanceError("database_lock_busy")

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        if self.process.stdin is not None:
            try:
                self.process.stdin.write("select pg_advisory_unlock_all();\n\\q\n")
                self.process.stdin.flush()
                self.process.stdin.close()
                self.process.stdin = None
                self.process.wait(timeout=5)
                return
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                pass
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def cleanup_sql() -> str:
    images = sql_values(IMAGE_IDS)
    submissions = sql_values(SUBMISSION_IDS)
    assets = sql_values(ASSET_IDS)
    reviewer_emails = sql_values(REVIEWER_EMAILS)
    return f"""
begin;
set local lock_timeout = '10s';
alter table public.audit_logs disable trigger audit_logs_append_only;
alter table public.review_decisions disable trigger review_decisions_append_only;
alter table public.review_submissions disable trigger review_submissions_snapshot_immutable;
alter table public.image_versions disable trigger image_versions_locked_immutable;
alter table public.asset_scan_jobs disable trigger asset_scan_jobs_terminal_immutable;
alter table public.asset_scan_events disable trigger asset_scan_events_append_only;
delete from public.audit_logs
where target_type = 'review_submission' and target_id in ({submissions});
delete from public.notifications
where payload ->> 'submission_id' in ({submissions})
   or payload ->> 'image_id' in ({images});
delete from public.review_decisions where submission_id in ({submissions});
delete from public.review_submissions where id in ({submissions}) or image_id in ({images});
delete from public.asset_scan_events where asset_id in ({assets});
delete from public.asset_scan_jobs where asset_id in ({assets});
delete from public.image_assets where id in ({assets}) or image_id in ({images});
update public.images set current_version_id = null where id in ({images});
delete from public.image_versions where image_id in ({images});
delete from public.images where id in ({images});
delete from public.folders
where owner_user_id = '{OWNER_ID}'::uuid
   or owner_user_id in (
     select id from public.users where lower(email) in ({reviewer_emails})
   );
delete from public.user_roles
where user_id = '{OWNER_ID}'::uuid
   or user_id in (
     select id from public.users where lower(email) in ({reviewer_emails})
   );
delete from public.user_profiles
where user_id = '{OWNER_ID}'::uuid
   or user_id in (
     select id from public.users where lower(email) in ({reviewer_emails})
   );
delete from public.users
where id = '{OWNER_ID}'::uuid or lower(email) in ({reviewer_emails});
alter table public.asset_scan_events enable trigger asset_scan_events_append_only;
alter table public.asset_scan_jobs enable trigger asset_scan_jobs_terminal_immutable;
alter table public.image_versions enable trigger image_versions_locked_immutable;
alter table public.review_submissions enable trigger review_submissions_snapshot_immutable;
alter table public.review_decisions enable trigger review_decisions_append_only;
alter table public.audit_logs enable trigger audit_logs_append_only;
commit;
"""


def fixture_auth_ids(values: Mapping[str, str]) -> list[str]:
    emails = sql_values(REVIEWER_EMAILS)
    raw = run_sql(
        f"select id::text from auth.users where lower(email) in ({emails}) order by id;",
        values,
    )
    result: list[str] = []
    for line in raw.splitlines():
        if line.strip():
            result.append(str(uuid.UUID(line.strip())))
    return result


def remove_storage_objects(base_url: str, secret: str) -> None:
    grouped: dict[str, list[str]] = {}
    for bucket, key in STORAGE_OBJECTS:
        grouped.setdefault(bucket, []).append(key)
    for bucket, keys in grouped.items():
        request(
            f"{base_url}/storage/v1/object/{urllib.parse.quote(bucket, safe='')}",
            method="DELETE",
            headers=service_headers(secret),
            payload={"prefixes": keys},
            expected={200, 204, 404},
        )


def delete_fixture_auth_users(
    values: Mapping[str, str],
    base_url: str,
    secret: str,
    known_ids: set[str],
) -> None:
    candidates = set(known_ids)
    try:
        candidates.update(fixture_auth_ids(values))
    except AcceptanceError:
        if not candidates:
            raise
    failures = False
    for user_id in sorted(candidates):
        try:
            auth_admin_delete(base_url, secret, user_id)
        except (AcceptanceError, ValueError):
            failures = True
    if failures:
        raise AcceptanceError("auth_cleanup_failed")


def cleanup_verification(values: Mapping[str, str]) -> bool:
    reviewer_emails = sql_values(REVIEWER_EMAILS)
    images = sql_values(IMAGE_IDS)
    submissions = sql_values(SUBMISSION_IDS)
    assets = sql_values(ASSET_IDS)
    raw = run_sql(
        f"""
select json_build_object(
  'auth_users', (select count(*) from auth.users where lower(email) in ({reviewer_emails})),
  'public_users', (select count(*) from public.users where id = '{OWNER_ID}'::uuid or lower(email) in ({reviewer_emails})),
  'images', (select count(*) from public.images where id in ({images})),
  'submissions', (select count(*) from public.review_submissions where id in ({submissions}) or image_id in ({images})),
  'assets', (select count(*) from public.image_assets where id in ({assets}) or image_id in ({images})),
  'scan_jobs', (select count(*) from public.asset_scan_jobs where asset_id in ({assets})),
  'scan_events', (select count(*) from public.asset_scan_events where asset_id in ({assets})),
  'storage_objects', (select count(*) from storage.objects where (bucket_id, name) in ({sql_storage_pairs()}))
)::text;
""",
        values,
    )
    try:
        counts = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(counts, dict) and counts and all(value == 0 for value in counts.values())


def preclean(values: Mapping[str, str], base_url: str, secret: str) -> None:
    remove_storage_objects(base_url, secret)
    delete_fixture_auth_users(values, base_url, secret, set())
    run_sql(cleanup_sql(), values)
    if not cleanup_verification(values):
        raise AcceptanceError("preclean_incomplete")


def upload_storage_objects(base_url: str, secret: str, data: bytes) -> None:
    for bucket, key in STORAGE_OBJECTS:
        headers = service_headers(secret)
        headers.update(
            {
                "Content-Type": "image/jpeg",
                "Cache-Control": "no-store",
                "x-upsert": "false",
            }
        )
        encoded_key = urllib.parse.quote(key, safe="/")
        request(
            f"{base_url}/storage/v1/object/{urllib.parse.quote(bucket, safe='')}/{encoded_key}",
            method="POST",
            headers=headers,
            body=data,
            expected={200, 201},
        )


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise AcceptanceError("jpeg_fixture_invalid")
    offset = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in start_of_frame and length >= 7:
            height = int.from_bytes(data[offset + 3:offset + 5], "big")
            width = int.from_bytes(data[offset + 5:offset + 7], "big")
            if width > 0 and height > 0:
                return width, height
        offset += length
    raise AcceptanceError("jpeg_dimensions_missing")


def readiness_snapshot(image_id: str) -> str:
    checks = [
        ("work_details", "Work details are complete."),
        ("rights_disclosures", "Rights and disclosures are complete."),
        ("image_assets", "All required image assets are present."),
        ("security_scan", "All image assets passed the current scan policy."),
        ("submission_state", "The image is ready for review."),
    ]
    value = {
        "image_id": image_id,
        "lock_version": 1,
        "workflow_status": "submitted",
        "status": "ready",
        "ready": True,
        "blocker_count": 0,
        "field_errors": {},
        "checks": [
            {"code": code, "label": code, "state": "pass", "message": message}
            for code, message in checks
        ],
    }
    return json.dumps(value, separators=(",", ":"))


def setup_fixtures(
    values: Mapping[str, str],
    reviewer_a_id: str,
    reviewer_b_id: str,
    *,
    byte_size: int,
    checksum: str,
    width: int,
    height: int,
) -> None:
    reviewer_a_id = str(uuid.UUID(reviewer_a_id))
    reviewer_b_id = str(uuid.UUID(reviewer_b_id))
    asset_value_rows = []
    for asset_id, image_id, kind, _bucket in ASSET_ROWS:
        asset_value_rows.append(
            "(" + ", ".join(
                (
                    f"'{asset_id}'",
                    f"'{image_id}'",
                    f"'{OWNER_ID}'",
                    f"'{kind}'",
                    f"'{sql_literal(storage_key(image_id, kind))}'",
                    "'image/jpeg'",
                    str(byte_size),
                    str(width),
                    str(height),
                    f"'{checksum}'",
                    "'private'",
                )
            ) + ")"
        )
    asset_rows_sql = ",\n  ".join(asset_value_rows)
    readiness_one = sql_literal(readiness_snapshot(IMAGE_IDS[0]))
    readiness_two = sql_literal(readiness_snapshot(IMAGE_IDS[1]))
    run_sql(
        f"""
begin;
set local lock_timeout = '10s';
insert into public.user_roles (user_id, role, assigned_by, reason) values
  ('{reviewer_a_id}', 'reviewer', null, 'Disposable Phase 3 browser acceptance'),
  ('{reviewer_b_id}', 'reviewer', null, 'Disposable Phase 3 browser acceptance')
on conflict (user_id, role) do update set reason = excluded.reason;
delete from public.user_roles
where user_id in ('{reviewer_a_id}'::uuid, '{reviewer_b_id}'::uuid)
  and role in ('admin'::public.role_code, 'super_admin'::public.role_code);
update public.user_profiles set display_name = case user_id
  when '{reviewer_a_id}'::uuid then 'Phase 3 Browser Reviewer A'
  else 'Phase 3 Browser Reviewer B'
end
where user_id in ('{reviewer_a_id}'::uuid, '{reviewer_b_id}'::uuid);
insert into public.users (id, auth_subject, email, email_verified_at, account_status) values
  ('{OWNER_ID}', '{OWNER_ID}', '{OWNER_EMAIL}', now(), 'active');
insert into public.user_profiles (user_id, display_name) values
  ('{OWNER_ID}', 'Phase 3 Browser Owner');
insert into public.user_roles (user_id, role, reason) values
  ('{OWNER_ID}', 'user', 'Disposable Phase 3 browser acceptance');
insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('{FOLDER_ID}', '{OWNER_ID}', 'Inbox', 0, true);
update storage.objects set owner_id = '{OWNER_ID}'
where (bucket_id, name) in ({sql_storage_pairs()});
insert into public.images (
  id, owner_user_id, folder_id, processing_status, workflow_status,
  publication_status, original_filename, original_width, original_height,
  checksum_sha256, version
) values
  ('{IMAGE_IDS[0]}', '{OWNER_ID}', '{FOLDER_ID}', 'ready', 'submitted',
   'never_published', 'phase3-browser-request-changes.jpg', {width}, {height}, '{checksum}', 1),
  ('{IMAGE_IDS[1]}', '{OWNER_ID}', '{FOLDER_ID}', 'ready', 'submitted',
   'never_published', 'phase3-browser-admin-approve.jpg', {width}, {height}, '{checksum}', 1);
insert into public.image_versions (
  id, image_id, version_number, title, caption, description, alt_text, tags,
  content_category, public_exif, copyright_holder, copyright_year,
  contains_recognizable_people, model_release_status, property_release_status,
  rights_declared, ai_disclosure, sensitive_content_disclosure,
  created_by_user_id, locked_at
) values
  ('{VERSION_IDS[0]}', '{IMAGE_IDS[0]}', 1, 'Browser Request Changes Fixture',
   'A reversible Review Queue browser fixture.', 'Reviewer A must request changes.',
   'A quiet mountain landscape held in low cloud.', '["phase3","browser"]',
   'concrete', '{{"camera":"Acceptance fixture"}}', 'Phase 3 Browser Owner', 2026,
   false, 'not_applicable', 'not_applicable', true, 'none', 'none', '{OWNER_ID}', now()),
  ('{VERSION_IDS[1]}', '{IMAGE_IDS[1]}', 1, 'Browser Admin Approval Fixture',
   'A reversible Review Queue browser fixture.', 'The development Admin must approve this submission.',
   'A quiet mountain landscape held in low cloud.', '["phase3","browser"]',
   'concrete', '{{"camera":"Acceptance fixture"}}', 'Phase 3 Browser Owner', 2026,
   false, 'not_applicable', 'not_applicable', true, 'none', 'none', '{OWNER_ID}', now());
update public.images set current_version_id = case id
  when '{IMAGE_IDS[0]}'::uuid then '{VERSION_IDS[0]}'::uuid
  else '{VERSION_IDS[1]}'::uuid
end
where id in ({sql_values(IMAGE_IDS)});
insert into public.image_assets (
  id, image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
  width, height, checksum_sha256, storage_visibility
) values
  {asset_rows_sql};
update public.image_assets set
  scan_status = 'clean', scan_result_code = 'clean', scan_completed_at = now(),
  scan_policy_version = '{SCAN_POLICY}'
where id in ({sql_values(ASSET_IDS)});
update public.asset_scan_jobs set
  status = 'clean', attempt_count = 1, scanner_version = 'phase3-browser-fixture',
  engine_name = 'fixture', engine_version = '1', result_code = 'clean',
  result_details = '{{"fixture":true}}'::jsonb, completed_at = now()
where asset_id in ({sql_values(ASSET_IDS)});
insert into public.asset_scan_events (
  job_id, asset_id, attempt_number, event_type, worker_id, result_code, details
)
select id, asset_id, 1, 'clean', 'phase3-browser-fixture', 'clean',
       '{{"fixture":true}}'::jsonb
from public.asset_scan_jobs where asset_id in ({sql_values(ASSET_IDS)});
insert into public.review_submissions (
  id, image_id, image_version_id, submitted_by_user_id, idempotency_key,
  status, assigned_reviewer_id, policy_version, lock_version,
  readiness_snapshot, asset_snapshot
)
select '{SUBMISSION_IDS[0]}', '{IMAGE_IDS[0]}', '{VERSION_IDS[0]}', '{OWNER_ID}',
       '{SUBMIT_KEYS[0]}', 'submitted', null, '{REVIEW_POLICY}', 1,
       '{readiness_one}'::jsonb,
       (select jsonb_agg(jsonb_build_object(
          'id', a.id, 'kind', a.kind, 'mime_type', a.mime_type,
          'byte_size', a.byte_size, 'width', a.width, 'height', a.height,
          'checksum_sha256', a.checksum_sha256, 'scan_status', a.scan_status,
          'scan_policy_version', a.scan_policy_version
        ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
        from public.image_assets a where a.image_id = '{IMAGE_IDS[0]}')
union all
select '{SUBMISSION_IDS[1]}', '{IMAGE_IDS[1]}', '{VERSION_IDS[1]}', '{OWNER_ID}',
       '{SUBMIT_KEYS[1]}', 'submitted', null, '{REVIEW_POLICY}', 1,
       '{readiness_two}'::jsonb,
       (select jsonb_agg(jsonb_build_object(
          'id', a.id, 'kind', a.kind, 'mime_type', a.mime_type,
          'byte_size', a.byte_size, 'width', a.width, 'height', a.height,
          'checksum_sha256', a.checksum_sha256, 'scan_status', a.scan_status,
          'scan_policy_version', a.scan_policy_version
        ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
        from public.image_assets a where a.image_id = '{IMAGE_IDS[1]}');
commit;
""",
        values,
        timeout=60,
    )
    verified = run_sql(
        f"""
select json_build_object(
  'submitted', (select count(*) from public.review_submissions where id in ({sql_values(SUBMISSION_IDS)}) and status = 'submitted'),
  'assets', (select count(*) from public.image_assets where id in ({sql_values(ASSET_IDS)}) and scan_status = 'clean' and scan_policy_version = '{SCAN_POLICY}'),
  'objects', (select count(*) from storage.objects where (bucket_id, name) in ({sql_storage_pairs()}) and owner_id = '{OWNER_ID}'),
  'pure_reviewers', (select count(*) from public.users u where u.id in ('{reviewer_a_id}'::uuid, '{reviewer_b_id}'::uuid) and exists (select 1 from public.user_roles r where r.user_id=u.id and r.role='reviewer') and not exists (select 1 from public.user_roles r where r.user_id=u.id and r.role in ('admin','super_admin'))),
  'non_self', (select count(*) from public.review_submissions where id in ({sql_values(SUBMISSION_IDS)}) and submitted_by_user_id not in ('{reviewer_a_id}'::uuid, '{reviewer_b_id}'::uuid))
)::text;
""",
        values,
    )
    try:
        state = json.loads(verified)
    except json.JSONDecodeError as error:
        raise AcceptanceError("fixture_verification_invalid") from error
    expected = {"submitted": 2, "assets": 6, "objects": 6, "pure_reviewers": 2, "non_self": 2}
    if state != expected:
        raise AcceptanceError("fixture_verification_failed")


def admin_factor(values: Mapping[str, str]) -> tuple[str, str, str]:
    email = required(values, "MT_DEV_ADMIN_EMAIL").lower()
    raw = run_sql(
        "select json_build_object("
        "'id', au.id, 'factor_id', min(mf.id::text), 'secret', min(mf.secret), "
        "'factor_count', count(*)"
        ")::text "
        "from auth.users au "
        "join public.users u on u.id=au.id "
        "join auth.mfa_factors mf on mf.user_id=au.id "
        f"where lower(au.email)=lower('{sql_literal(email)}') "
        "and au.email_confirmed_at is not null and u.account_status='active' "
        "and exists (select 1 from public.user_roles ur where ur.user_id=au.id and ur.role in ('admin','super_admin')) "
        "and mf.status::text='verified' and mf.factor_type::text='totp' "
        "group by au.id;",
        values,
    )
    try:
        result = json.loads(raw)
        admin_id = str(uuid.UUID(str(result["id"])))
        factor_id = str(uuid.UUID(str(result["factor_id"])))
        secret = str(result["secret"])
        factor_count = int(result["factor_count"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as error:
        raise AcceptanceError("admin_factor_invalid") from error
    if factor_count != 1 or not secret or not factor_id:
        raise AcceptanceError("admin_factor_ambiguous")
    return admin_id, factor_id, secret


def totp(secret: str, at: int | None = None) -> str:
    normalized = secret.strip().replace(" ", "").upper().rstrip("=")
    try:
        key = base64.b32decode(normalized + "=" * (-len(normalized) % 8))
    except (ValueError, TypeError) as error:
        raise AcceptanceError("admin_factor_secret_invalid") from error
    counter = int((at or int(time.time())) / 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def server_environment(values: Mapping[str, str], base_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("MT_SCANNER_") or name.startswith("PG"):
            environment.pop(name, None)
    for name in (
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "MT_DEV_ADMIN_EMAIL",
        "MT_DEV_ADMIN_PASSWORD",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "SUPABASE_URL": required(values, "SUPABASE_URL").rstrip("/"),
            "SUPABASE_PUBLISHABLE_KEY": required(values, "SUPABASE_PUBLISHABLE_KEY"),
            "MT_COOKIE_SECURE": "0",
            "MT_PUBLIC_BASE_URL": base_url,
        }
    )
    return environment


def start_server(values: Mapping[str, str]) -> tuple[subprocess.Popen[bytes], str]:
    port = reserve_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [shutil.which("python3") or "python3", "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=server_environment(values, base_url),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AcceptanceError("loopback_server_failed")
        try:
            with opener.open(f"{base_url}/auth/sign-in", timeout=1) as response:
                if response.status == 200:
                    return process, base_url
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    raise AcceptanceError("loopback_server_timeout")


def stop_server(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class Browser:
    def __init__(self, config_path: Path):
        binary = shutil.which("agent-browser")
        if not binary:
            raise AcceptanceError("agent_browser_missing")
        environment = os.environ.copy()
        for name in tuple(environment):
            if (
                name.startswith("SUPABASE_")
                or name.startswith("PG")
                or name.startswith("MT_DEV_ADMIN_")
                or name.startswith("MT_SCANNER_")
            ):
                environment.pop(name, None)
        for name in tuple(environment):
            if name.startswith("AGENT_BROWSER_"):
                environment.pop(name, None)
        version = subprocess.run(
            [binary, "--version"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if version.returncode or not AGENT_BROWSER_VERSION.fullmatch(version.stdout.strip()):
            raise AcceptanceError("agent_browser_version_invalid")
        self.binary = binary
        self.config_path = config_path
        self.opened_sessions: set[str] = set()
        self.environment = environment

    def command(
        self,
        session: str,
        *arguments: str,
        stdin: str | None = None,
        json_output: bool = False,
        timeout: float = 35.0,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            self.binary,
            "--session",
            session,
            "--config",
            str(self.config_path),
        ]
        if json_output:
            command.append("--json")
        command.extend(arguments)
        completed = subprocess.run(
            command,
            input=stdin,
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if check and completed.returncode:
            raise AcceptanceError("browser_command_failed")
        if completed.returncode == 0 and arguments and arguments[0] == "open":
            self.opened_sessions.add(session)
        return completed

    def json_command(self, session: str, *arguments: str, stdin: str | None = None) -> dict[str, Any]:
        completed = self.command(
            session,
            *arguments,
            stdin=stdin,
            json_output=True,
        )
        payload: dict[str, Any] | None = None
        for line in reversed(completed.stdout.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break
        if payload is None or payload.get("success") is False:
            raise AcceptanceError("browser_response_invalid")
        return payload

    def condition(self, session: str, expression: str) -> bool:
        script = f"(() => (({expression}) ? 'MT_ACCEPT_YES' : 'MT_ACCEPT_NO'))()"
        try:
            payload = self.json_command(session, "eval", "--stdin", stdin=script)
        except AcceptanceError:
            return False
        return "MT_ACCEPT_YES" in json.dumps(payload, separators=(",", ":"))

    def assert_condition(self, session: str, expression: str) -> None:
        if not self.condition(session, expression):
            raise AcceptanceError("browser_assertion_failed")

    def wait_condition(self, session: str, expression: str, *, timeout: float = 25.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.condition(session, expression):
                return
            time.sleep(0.25)
        raise AcceptanceError("browser_wait_timeout")

    def close(self, session: str) -> bool:
        try:
            completed = self.command(session, "close", timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        closed = completed.returncode == 0
        if closed:
            self.opened_sessions.discard(session)
        return closed

    def sign_out(self, session: str) -> bool:
        script = """
(async () => {
  const csrfResponse = await fetch('/api/auth/csrf', {
    credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}
  });
  const csrf = await csrfResponse.json().catch(() => ({}));
  if (!csrfResponse.ok || !csrf.csrf_token) return 'MT_ACCEPT_NO';
  const response = await fetch('/api/auth/sign-out', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token},
    body: '{}'
  });
  return response.ok ? 'MT_ACCEPT_YES' : 'MT_ACCEPT_NO';
})()
"""
        try:
            payload = self.json_command(session, "eval", "--stdin", stdin=script)
        except Exception:
            return False
        return "MT_ACCEPT_YES" in json.dumps(payload, separators=(",", ":"))


def fill_secret_form(browser: Browser, session: str, fields: Mapping[str, str]) -> None:
    # Feed secrets only over stdin; native setters/events still exercise the
    # real form while keeping values out of argv and agent-browser output.
    serialized = json.dumps(dict(fields), separators=(",", ":"))
    script = f"""
(() => {{
  const values = {serialized};
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  for (const [selector, value] of Object.entries(values)) {{
    const input = document.querySelector(selector);
    if (!(input instanceof HTMLInputElement)) return 'MT_ACCEPT_NO';
    setter.call(input, value);
    input.dispatchEvent(new Event('input', {{bubbles: true}}));
    input.dispatchEvent(new Event('change', {{bubbles: true}}));
  }}
  return 'MT_ACCEPT_YES';
}})()
"""
    payload = browser.json_command(session, "eval", "--stdin", stdin=script)
    if "MT_ACCEPT_YES" not in json.dumps(payload, separators=(",", ":")):
        raise AcceptanceError("browser_secret_fill_failed")


def login_reviewer(
    browser: Browser,
    session: str,
    base_url: str,
    email: str,
    password: str,
    next_path: str,
) -> None:
    encoded_next = urllib.parse.quote(next_path, safe="")
    browser.command(session, "open", f"{base_url}/auth/sign-in?next={encoded_next}")
    browser.wait_condition(session, "document.querySelector('#auth-email') !== null")
    fill_secret_form(
        browser,
        session,
        {"#auth-email": email, "#auth-password": password},
    )
    browser.command(session, "click", "[data-auth-submit]")
    browser.wait_condition(session, "location.pathname.startsWith('/admin/reviews')", timeout=30)


def login_admin_aal2(
    browser: Browser,
    session: str,
    base_url: str,
    email: str,
    password: str,
    factor_secret: str,
    next_path: str,
) -> None:
    encoded_next = urllib.parse.quote(next_path, safe="")
    browser.command(session, "open", f"{base_url}/auth/sign-in?next={encoded_next}")
    browser.wait_condition(session, "document.querySelector('#auth-email') !== null")
    fill_secret_form(
        browser,
        session,
        {"#auth-email": email, "#auth-password": password},
    )
    browser.command(session, "click", "[data-auth-submit]")
    browser.wait_condition(session, "location.pathname === '/auth/mfa'", timeout=30)
    browser.wait_condition(
        session,
        "document.querySelector('[data-mfa-form]')?.hidden === false && document.querySelector('[name=code]') !== null",
        timeout=30,
    )
    browser.wait_condition(
        session,
        "document.activeElement === document.querySelector('[name=code]')",
    )
    remaining = 30 - (time.time() % 30)
    if remaining < 10:
        time.sleep(remaining + 0.5)
    fill_secret_form(browser, session, {"[name=code]": totp(factor_secret)})
    browser.command(session, "click", "[data-mfa-submit]")
    browser.wait_condition(session, "location.pathname.startsWith('/admin/reviews')", timeout=35)


def no_horizontal_overflow(browser: Browser, session: str) -> None:
    browser.assert_condition(
        session,
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1",
    )


def responsive_check(browser: Browser, session: str) -> None:
    browser.command(session, "set", "viewport", "1440", "900")
    no_horizontal_overflow(browser, session)
    browser.command(session, "set", "viewport", "390", "844")
    browser.command(session, "wait", "200")
    no_horizontal_overflow(browser, session)
    browser.command(session, "set", "viewport", "1440", "900")


def private_image_check(browser: Browser, session: str, supabase_url: str) -> None:
    origin = urllib.parse.urlparse(supabase_url).netloc
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-image]')?.complete === true && "
        "document.querySelector('[data-review-image]')?.naturalWidth > 0",
        timeout=30,
    )
    browser.wait_condition(
        session,
        "Array.from(document.images).filter((image) => image.getAttribute('src')).every((image) => image.complete && image.naturalWidth > 0)",
        timeout=30,
    )
    browser.assert_condition(
        session,
        f"new URL(document.querySelector('[data-review-image]').src).host === {json.dumps(origin)} && "
        "document.querySelectorAll('[data-asset-kind]').length === 3",
    )


def structured_items(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    data: Any = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
        if not data:
            return []
    if isinstance(data, str) and data.lower().startswith("no "):
        return []
    return None


def browser_diagnostics_clean(
    browser: Browser,
    session: str,
    *,
    allow_expected_404: bool = False,
) -> None:
    page_errors = structured_items(
        browser.json_command(session, "errors"),
        ("errors", "items"),
    )
    if page_errors is None or page_errors:
        raise AcceptanceError("browser_page_error")
    messages = structured_items(
        browser.json_command(session, "console"),
        ("messages", "entries", "items"),
    )
    if messages is None:
        raise AcceptanceError("browser_console_response_invalid")
    error_messages = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        level = str(message.get("type") or message.get("level") or "").lower()
        if level in {"error", "assert"}:
            error_messages.append(str(message.get("text") or message.get("message") or ""))
    if allow_expected_404:
        error_messages = [message for message in error_messages if "404" not in message]
    if error_messages:
        raise AcceptanceError("browser_console_error")


def clear_browser_diagnostics(browser: Browser, session: str) -> None:
    browser.command(session, "console", "--clear")
    browser.command(session, "errors", "--clear")


def complete_checklist(browser: Browser, session: str) -> None:
    names = (
        "file_integrity",
        "rights",
        "privacy",
        "minors",
        "sensitive_content",
        "hate_illegal",
        "property_release",
        "third_party_ip",
        "ai_disclosure",
        "public_metadata",
    )
    for name in names:
        browser.command(session, "check", f"[data-review-checklist] [name={name}]")


def exercise_dialog_focus(browser: Browser, session: str) -> None:
    browser.command(session, "click", "[data-review-decision-submit]")
    browser.wait_condition(session, "document.querySelector('[data-review-dialog]')?.open === true")
    browser.wait_condition(
        session,
        "document.activeElement === document.querySelector('[data-review-dialog-cancel]')",
    )
    browser.command(session, "press", "Escape")
    browser.wait_condition(session, "document.querySelector('[data-review-dialog]')?.open !== true")
    browser.wait_condition(
        session,
        "document.activeElement === document.querySelector('[data-review-decision-submit]')",
    )


def confirm_decision(browser: Browser, session: str) -> None:
    browser.command(session, "click", "[data-review-decision-submit]")
    browser.wait_condition(session, "document.querySelector('[data-review-dialog]')?.open === true")
    browser.command(session, "click", "[data-review-dialog-confirm]")


def click_dialog_action(browser: Browser, session: str, action: str) -> None:
    browser.command(session, "click", f"[data-review-action={action}]")
    browser.wait_condition(session, "document.querySelector('[data-review-dialog]')?.open === true")
    browser.command(session, "click", "[data-review-dialog-confirm]")


def wait_database(values: Mapping[str, str], command: str, expected: str, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run_sql(command, values) == expected:
            return
        time.sleep(0.3)
    raise AcceptanceError("database_state_timeout")


def reviewer_a_claim(
    browser: Browser,
    values: Mapping[str, str],
    base_url: str,
    reviewer_id: str,
    email: str,
    password: str,
) -> tuple[bool, bool, bool, bool, bool]:
    session = SESSION_NAMES[0]
    login_reviewer(browser, session, base_url, email, password, f"/admin/reviews/{SUBMISSION_IDS[0]}")
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-detail-retry]')?.dataset.action === 'start-selected'",
        timeout=30,
    )
    browser.command(session, "click", "[data-review-detail-retry]")
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-status]')?.textContent.trim() === 'In review' && "
        "document.querySelector('[data-review-detail]')?.hidden === false",
        timeout=35,
    )
    browser.wait_condition(
        session,
        "document.activeElement === document.querySelector('[data-review-title]')",
    )
    wait_database(
        values,
        f"select status::text || '|' || assigned_reviewer_id::text from public.review_submissions where id='{SUBMISSION_IDS[0]}';",
        f"in_review|{reviewer_id}",
    )
    private_image_check(browser, session, required(values, "SUPABASE_URL"))
    responsive_check(browser, session)
    browser_diagnostics_clean(browser, session)
    clear_browser_diagnostics(browser, session)
    return True, True, True, True, True


def reviewer_a_request_changes(
    browser: Browser,
    values: Mapping[str, str],
) -> tuple[bool, bool, bool]:
    session = SESSION_NAMES[0]
    browser.command(session, "select", "[data-review-decision]", "request_changes")
    browser.command(session, "select", "[data-review-reason]", "missing_metadata")
    browser.command(
        session,
        "fill",
        "[data-review-decision-form] textarea[name=user_message]",
        "Please update the submitted metadata before resubmitting.",
    )
    browser.command(
        session,
        "fill",
        "[data-review-decision-form] textarea[name=internal_note]",
        "Phase 3 browser acceptance request changes.",
    )
    complete_checklist(browser, session)
    exercise_dialog_focus(browser, session)
    confirm_decision(browser, session)
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-detail-state-title]')?.textContent.trim() === 'Decision recorded'",
        timeout=35,
    )
    wait_database(
        values,
        f"select s.status::text || '|' || i.workflow_status::text || '|' || count(d.id)::text from public.review_submissions s join public.images i on i.id=s.image_id left join public.review_decisions d on d.submission_id=s.id where s.id='{SUBMISSION_IDS[0]}' group by s.status,i.workflow_status;",
        "changes_requested|changes_requested|1",
    )
    browser_diagnostics_clean(browser, session)
    return True, True, True


def reviewer_b_denial(
    browser: Browser,
    base_url: str,
    email: str,
    password: str,
) -> tuple[bool, bool]:
    session = SESSION_NAMES[1]
    login_reviewer(browser, session, base_url, email, password, "/admin/reviews")
    browser.wait_condition(session, "document.querySelector('[data-review-queue]')?.getAttribute('aria-busy') === 'false'", timeout=30)
    browser_diagnostics_clean(browser, session)
    clear_browser_diagnostics(browser, session)
    browser.command(session, "open", f"{base_url}/admin/reviews/{SUBMISSION_IDS[0]}")
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-detail-state-title]')?.textContent.trim() === 'Submission unavailable'",
        timeout=30,
    )
    browser.assert_condition(
        session,
        f"!document.querySelector('[data-review-submission=\"{SUBMISSION_IDS[0]}\"]') && "
        "document.querySelector('[data-review-detail]')?.hidden === true && "
        "!document.querySelector('[data-review-image]')?.getAttribute('src')",
    )
    fetch_script = f"""
(async () => {{
  const response = await fetch('/api/admin/review-submissions/{SUBMISSION_IDS[0]}', {{credentials:'same-origin', cache:'no-store'}});
  return response.status === 404 ? 'MT_ACCEPT_YES' : 'MT_ACCEPT_NO';
}})()
"""
    payload = browser.json_command(session, "eval", "--stdin", stdin=fetch_script)
    if "MT_ACCEPT_YES" not in json.dumps(payload, separators=(",", ":")):
        raise AcceptanceError("reviewer_denial_failed")
    responsive_check(browser, session)
    browser_diagnostics_clean(browser, session, allow_expected_404=True)
    return True, True


def admin_acceptance(
    browser: Browser,
    values: Mapping[str, str],
    base_url: str,
    admin_id: str,
    factor_secret: str,
) -> tuple[bool, bool, bool, bool]:
    session = SESSION_NAMES[2]
    login_admin_aal2(
        browser,
        session,
        base_url,
        required(values, "MT_DEV_ADMIN_EMAIL"),
        required(values, "MT_DEV_ADMIN_PASSWORD"),
        factor_secret,
        f"/admin/reviews/{SUBMISSION_IDS[1]}",
    )
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-detail]')?.hidden === false && "
        "document.querySelector('[data-review-status]')?.textContent.trim() === 'Waiting'",
        timeout=35,
    )
    private_image_check(browser, session, required(values, "SUPABASE_URL"))
    responsive_check(browser, session)
    click_dialog_action(browser, session, "assign")
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-action=start]') !== null",
        timeout=30,
    )
    click_dialog_action(browser, session, "start")
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-decision-form]')?.hidden === false && "
        "document.querySelector('[data-review-status]')?.textContent.trim() === 'In review'",
        timeout=35,
    )
    browser.command(session, "select", "[data-review-decision]", "approve")
    browser.command(session, "select", "[data-review-reason]", "policy_complete")
    browser.command(
        session,
        "fill",
        "[data-review-decision-form] textarea[name=user_message]",
        "Approved after completing the Phase 3 policy review.",
    )
    browser.command(
        session,
        "fill",
        "[data-review-decision-form] textarea[name=internal_note]",
        "Phase 3 browser acceptance approval.",
    )
    complete_checklist(browser, session)
    confirm_decision(browser, session)
    browser.wait_condition(
        session,
        "document.querySelector('[data-review-status]')?.textContent.trim() === 'Approved'",
        timeout=35,
    )
    wait_database(
        values,
        f"select s.status::text || '|' || i.workflow_status::text || '|' || d.decision::text || '|' || d.reviewer_id::text from public.review_submissions s join public.images i on i.id=s.image_id join public.review_decisions d on d.submission_id=s.id where s.id='{SUBMISSION_IDS[1]}';",
        f"approved|approved|approve|{admin_id}",
    )
    browser_diagnostics_clean(browser, session)
    return True, True, True, True


def cleanup_everything(
    *,
    browser: Browser | None,
    server: subprocess.Popen[bytes] | None,
    values: Mapping[str, str] | None,
    base_url: str,
    secret: str,
    reviewer_ids: set[str],
) -> tuple[bool, bool]:
    sessions_closed = browser is not None
    if browser is not None:
        for session in tuple(browser.opened_sessions):
            if not browser.sign_out(session):
                sessions_closed = False
        for session in SESSION_NAMES:
            try:
                closed = browser.close(session)
            except Exception:
                closed = False
            if not closed:
                sessions_closed = False
    try:
        stop_server(server)
    except Exception:
        pass

    cleanup_ok = values is not None and bool(base_url and secret)
    if values is None or not base_url or not secret:
        return sessions_closed, False
    for operation in (
        lambda: remove_storage_objects(base_url, secret),
        lambda: delete_fixture_auth_users(values, base_url, secret, reviewer_ids),
        lambda: run_sql(cleanup_sql(), values),
    ):
        try:
            operation()
        except Exception:
            cleanup_ok = False
    try:
        cleanup_ok = cleanup_verification(values) and cleanup_ok
    except Exception:
        cleanup_ok = False
    return sessions_closed, cleanup_ok


def main() -> int:
    markers = {name: False for name in MARKER_ORDER}
    markers["review_browser_state_persisted"] = False
    markers["credentials_logged"] = False
    values: dict[str, str] | None = None
    base_url = ""
    secret = ""
    lock: AdvisoryLock | None = None
    lock_acquired = False
    browser: Browser | None = None
    server: subprocess.Popen[bytes] | None = None
    reviewer_ids: set[str] = set()
    acceptance_ok = False

    with tempfile.TemporaryDirectory(prefix="mt-phase3-browser-") as temporary_directory:
        config_path = Path(temporary_directory) / "agent-browser.json"
        config_path.write_text('{"headed":false}\n', encoding="utf-8")
        try:
            values = configuration()
            require_development(values)
            markers["review_browser_environment_guard"] = True
            base_url = required(values, "SUPABASE_URL").rstrip("/")
            secret = service_secret(values)
            lock = AdvisoryLock(values)
            lock.acquire()
            lock_acquired = True
            browser = Browser(config_path)
            preclosed = [browser.close(session) for session in SESSION_NAMES]
            if not all(preclosed):
                raise AcceptanceError("browser_session_preclean_failed")
            preclean(values, base_url, secret)

            admin_id, _factor_id, factor_secret = admin_factor(values)
            jpeg = JPEG_PATH.read_bytes()
            width, height = jpeg_dimensions(jpeg)
            checksum = hashlib.sha256(jpeg).hexdigest()
            reviewer_passwords = (
                f"Mt!{secrets.token_urlsafe(28)}7a",
                f"Mt!{secrets.token_urlsafe(28)}8b",
            )
            reviewer_a_id = auth_admin_create(
                base_url,
                secret,
                REVIEWER_EMAILS[0],
                reviewer_passwords[0],
                "Phase 3 Browser Reviewer A",
            )
            reviewer_ids.add(reviewer_a_id)
            reviewer_b_id = auth_admin_create(
                base_url,
                secret,
                REVIEWER_EMAILS[1],
                reviewer_passwords[1],
                "Phase 3 Browser Reviewer B",
            )
            reviewer_ids.add(reviewer_b_id)
            if len(reviewer_ids) != 2 or admin_id in reviewer_ids or OWNER_ID in reviewer_ids:
                raise AcceptanceError("reviewer_identity_collision")

            upload_storage_objects(base_url, secret, jpeg)
            setup_fixtures(
                values,
                reviewer_a_id,
                reviewer_b_id,
                byte_size=len(jpeg),
                checksum=checksum,
                width=width,
                height=height,
            )
            server, loopback_url = start_server(values)

            reviewer_claim, image_a, responsive_a, claim_focus, claim_clean = reviewer_a_claim(
                browser,
                values,
                loopback_url,
                reviewer_a_id,
                REVIEWER_EMAILS[0],
                reviewer_passwords[0],
            )
            markers["review_browser_reviewer_claim"] = reviewer_claim
            denied, clean_b = reviewer_b_denial(
                browser,
                loopback_url,
                REVIEWER_EMAILS[1],
                reviewer_passwords[1],
            )
            markers["review_browser_second_reviewer_denied"] = denied
            request_changes, dialog_focus, decision_clean = reviewer_a_request_changes(
                browser,
                values,
            )
            markers["review_browser_request_changes"] = request_changes
            admin_approve, image_admin, responsive_admin, clean_admin = admin_acceptance(
                browser,
                values,
                loopback_url,
                admin_id,
                factor_secret,
            )
            markers["review_browser_admin_aal2_approve"] = admin_approve
            markers["review_browser_private_images_loaded"] = image_a and image_admin
            markers["review_browser_responsive_contract"] = responsive_a and responsive_admin
            markers["review_browser_focus_dialog_contract"] = claim_focus and dialog_focus
            markers["review_browser_console_clean"] = claim_clean and clean_b and decision_clean and clean_admin
            acceptance_ok = all(
                markers[name]
                for name in (
                    "review_browser_environment_guard",
                    "review_browser_reviewer_claim",
                    "review_browser_second_reviewer_denied",
                    "review_browser_request_changes",
                    "review_browser_admin_aal2_approve",
                    "review_browser_private_images_loaded",
                    "review_browser_responsive_contract",
                    "review_browser_focus_dialog_contract",
                    "review_browser_console_clean",
                )
            )
        except (
            AcceptanceError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ):
            acceptance_ok = False
        finally:
            try:
                sessions_closed, fixtures_cleaned = cleanup_everything(
                    browser=browser,
                    server=server,
                    values=values if lock_acquired else None,
                    base_url=base_url if lock_acquired else "",
                    secret=secret if lock_acquired else "",
                    reviewer_ids=reviewer_ids,
                )
                markers["review_browser_sessions_closed"] = sessions_closed
                markers["review_browser_fixtures_cleaned"] = fixtures_cleaned
            finally:
                if lock is not None:
                    lock.close()

    markers["review_browser_acceptance"] = (
        acceptance_ok
        and markers["review_browser_sessions_closed"]
        and markers["review_browser_fixtures_cleaned"]
        and not markers["review_browser_state_persisted"]
        and not markers["credentials_logged"]
    )
    for name in MARKER_ORDER:
        print(f"{name}={'yes' if markers[name] else 'no'}")
    return 0 if markers["review_browser_acceptance"] else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except (Exception, KeyboardInterrupt):
        for marker_name in MARKER_ORDER:
            print(f"{marker_name}=no")
        exit_code = 1
    raise SystemExit(exit_code)
