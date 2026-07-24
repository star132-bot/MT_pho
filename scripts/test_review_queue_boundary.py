#!/usr/bin/env python3
"""Secret-free HTTP integration coverage for the Review Queue boundary."""

from __future__ import annotations

import base64
import copy
import http.client
import http.cookiejar
import importlib
import json
import os
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fake_access_token(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


USER_ID = "10000000-0000-4000-8000-000000000001"
RECOVERY_ID = "10000000-0000-4000-8000-000000000002"
REVIEWER_A_ID = "10000000-0000-4000-8000-000000000003"
REVIEWER_B_ID = "10000000-0000-4000-8000-000000000004"
ADMIN_AAL1_ID = "10000000-0000-4000-8000-000000000005"
ADMIN_AAL2_ID = "10000000-0000-4000-8000-000000000006"
OWNER_ID = "10000000-0000-4000-8000-000000000007"

SUBMISSION_PUBLIC = "20000000-0000-4000-8000-000000000001"
SUBMISSION_A = "20000000-0000-4000-8000-000000000002"
SUBMISSION_B = "20000000-0000-4000-8000-000000000003"
SUBMISSION_DONE = "20000000-0000-4000-8000-000000000004"
IMAGE_ID = "30000000-0000-4000-8000-000000000001"
VERSION_ID = "40000000-0000-4000-8000-000000000001"
DECISION_ID = "50000000-0000-4000-8000-000000000001"


def token(user_id: str, *, aal: str = "aal1", method: str = "password") -> str:
    return fake_access_token({"sub": user_id, "aal": aal, "amr": [{"method": method}]})


USER_TOKEN = token(USER_ID)
RECOVERY_TOKEN = token(RECOVERY_ID, method="recovery")
REVIEWER_A_TOKEN = token(REVIEWER_A_ID)
REVIEWER_B_TOKEN = token(REVIEWER_B_ID)
ADMIN_AAL1_TOKEN = token(ADMIN_AAL1_ID)
ADMIN_AAL2_TOKEN = token(ADMIN_AAL2_ID, aal="aal2", method="totp")

AUTHORIZATIONS = {
    USER_TOKEN: {"user_id": USER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"},
    RECOVERY_TOKEN: {"user_id": RECOVERY_ID, "account_status": "active", "roles": ["reviewer"], "aal": "aal1"},
    REVIEWER_A_TOKEN: {"user_id": REVIEWER_A_ID, "account_status": "active", "roles": ["user", "reviewer"], "aal": "aal1"},
    REVIEWER_B_TOKEN: {"user_id": REVIEWER_B_ID, "account_status": "active", "roles": ["reviewer"], "aal": "aal1"},
    ADMIN_AAL1_TOKEN: {"user_id": ADMIN_AAL1_ID, "account_status": "active", "roles": ["reviewer", "admin"], "aal": "aal1"},
    ADMIN_AAL2_TOKEN: {"user_id": ADMIN_AAL2_ID, "account_status": "active", "roles": ["user", "admin"], "aal": "aal2"},
}


def review_roles(access_token: str) -> list[str]:
    return [role for role in AUTHORIZATIONS[access_token]["roles"] if role in {"reviewer", "admin", "super_admin"}]


def person(user_id: str | None) -> dict | None:
    return {"id": user_id, "display_name": f"Reviewer {user_id[-1]}"} if user_id else None


def asset(kind: str, suffix: str) -> dict:
    buckets = {"original": "image-originals", "display": "image-display", "thumbnail": "image-thumbnails"}
    return {
        "id": f"60000000-0000-4000-8000-00000000000{suffix}",
        "kind": kind,
        "storage_bucket": buckets[kind],
        "storage_key": f"{OWNER_ID}/{IMAGE_ID}/{kind}.jpg",
        "mime_type": "image/jpeg",
        "byte_size": 2048,
        "width": 1600,
        "height": 1200,
        "checksum_sha256": "a" * 64,
        "scan_status": "clean",
        "scan_result_code": "clean",
        "scan_policy_version": "mt-asset-scan-2026-07-v1",
        "provider_secret": "must-not-leak",
    }


def summary(submission_id: str, status: str, assigned_id: str | None) -> dict:
    return {
        "id": submission_id,
        "status": status,
        "lock_version": 2,
        "submitted_at": "2026-07-20T00:00:00Z",
        "review_started_at": "2026-07-20T00:05:00Z" if assigned_id else None,
        "completed_at": "2026-07-20T01:00:00Z" if status == "approved" else None,
        "policy_version": "review-v1",
        "assigned_reviewer": person(assigned_id),
        "owner": {"id": OWNER_ID, "display_name": "MT Owner", "email": "private@example.test"},
        "image": {
            "id": IMAGE_ID,
            "title": "Quiet Weather",
            "original_filename": "quiet-weather.jpg",
            "content_category": "concrete",
            "publication_status": "never_published",
            "rights": {
                "declared": True,
                "recognizable_people": False,
                "model_release_status": "not_required",
                "property_release_status": "not_required",
            },
            "thumbnail_asset": asset("thumbnail", "3"),
            "private_source": "must-not-leak",
        },
    }


def detail(access_token: str, submission_id: str, status: str, assigned_id: str | None) -> dict:
    checks = [
        {"code": code, "state": "pass", "message": "Verified."}
        for code in ("work_details", "rights_disclosures", "image_assets", "security_scan", "submission_state")
    ]
    return {
        "actor": {"id": AUTHORIZATIONS[access_token]["user_id"], "roles": review_roles(access_token), "email": "private@example.test"},
        "submission": {
            "id": submission_id,
            "status": status,
            "lock_version": 2,
            "policy_version": "review-v1",
            "submitted_at": "2026-07-20T00:00:00Z",
            "review_started_at": "2026-07-20T00:05:00Z" if assigned_id else None,
            "completed_at": None,
            "assigned_reviewer": person(assigned_id),
            "readiness_snapshot": {
                "image_id": IMAGE_ID,
                "lock_version": 1,
                "workflow_status": "submitted",
                "checks": checks,
                "field_errors": {},
            },
        },
        "owner": {
            "id": OWNER_ID,
            "display_name": "MT Owner",
            "account_status": "active",
            "created_at": "2026-07-01T00:00:00Z",
            "email": "private@example.test",
        },
        "image": {
            "id": IMAGE_ID,
            "workflow_status": "in_review" if status == "in_review" else "approved",
            "publication_status": "never_published",
            "processing_status": "ready",
            "published_at": None,
            "original_filename": "quiet-weather.jpg",
            "original_width": 1600,
            "original_height": 1200,
            "version": {
                "id": VERSION_ID,
                "version_number": 1,
                "title": "Quiet Weather",
                "caption": "After the storm.",
                "description": "A study of weather and distance.",
                "alt_text": "Clouds above a valley.",
                "tags": ["weather", "valley"],
                "content_category": "concrete",
                "captured_at": "2026-06-01T08:00:00Z",
                "location_name": "North valley",
                "public_exif": {"camera": "MT Camera", "gps": "must-not-leak"},
                "copyright_holder": "MT Owner",
                "copyright_year": 2026,
                "contains_recognizable_people": False,
                "model_release_status": "not_required",
                "property_release_status": "not_required",
                "rights_declared": True,
                "ai_disclosure": "none",
                "sensitive_content_disclosure": "none",
            },
        },
        "assets": [asset("original", "1"), asset("display", "2"), asset("thumbnail", "3")],
        "decisions": [],
        "service_role_secret": "must-not-leak",
    }


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    review_calls: list[tuple[str, dict, str]] = []
    storage_sign_calls = 0
    inject_cross_reviewer_list = False
    inject_self_owned_list = False
    inject_stale_scan_list = False
    inject_self_owned_detail = False
    inject_stale_scan_detail = False
    next_review_status: int | None = None
    next_review_error_code: str | None = None
    next_decision_result: dict | None = None
    decision_results: dict[str, dict] = {}
    decision_payloads: dict[str, dict] = {}
    decision_writes = 0

    def log_message(self, _format, *_args) -> None:
        return

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def access_token(self) -> str:
        return self.headers.get("Authorization", "").removeprefix("Bearer ")

    def do_GET(self) -> None:
        access_token = self.access_token()
        if self.path == "/auth/v1/user" and access_token in AUTHORIZATIONS:
            user_id = AUTHORIZATIONS[access_token]["user_id"]
            self.send_json(HTTPStatus.OK, {
                "id": user_id,
                "email": f"{user_id[-1]}@example.test",
                "email_confirmed_at": "2026-07-01T00:00:00Z",
                "factors": [],
            })
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        access_token = self.access_token()
        if self.path == "/rest/v1/rpc/current_authorization":
            authorization = AUTHORIZATIONS.get(access_token)
            self.send_json(HTTPStatus.OK if authorization else HTTPStatus.UNAUTHORIZED, authorization or {})
            return
        if self.path.startswith("/storage/v1/object/sign/"):
            self.body()
            type(self).storage_sign_calls += 1
            signed_path = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"/{signed_path.lstrip('/')}?token=fake"})
            return
        if not self.path.startswith("/rest/v1/rpc/review_"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return

        body = self.body()
        type(self).review_calls.append((self.path, copy.deepcopy(body), access_token))
        if type(self).next_review_status is not None:
            status = type(self).next_review_status
            type(self).next_review_status = None
            self.send_json(status, {"message": "provider detail must not escape"})
            return
        if type(self).next_review_error_code is not None:
            code = type(self).next_review_error_code
            type(self).next_review_error_code = None
            self.send_json(HTTPStatus.OK, {"error": {
                "code": code,
                "message": "A submission cannot be reviewed by its owner.",
            }})
            return
        if access_token not in AUTHORIZATIONS:
            self.send_json(HTTPStatus.UNAUTHORIZED, {})
            return

        actor = {"id": AUTHORIZATIONS[access_token]["user_id"], "roles": review_roles(access_token)}
        if self.path == "/rest/v1/rpc/review_list_submissions":
            status_filter = body.get("status_filter")
            if access_token == REVIEWER_A_TOKEN:
                scoped_items = [summary(SUBMISSION_PUBLIC, "submitted", None), summary(SUBMISSION_A, "in_review", REVIEWER_A_ID)]
                if type(self).inject_cross_reviewer_list:
                    scoped_items.append(summary(SUBMISSION_B, "in_review", REVIEWER_B_ID))
            elif access_token == REVIEWER_B_TOKEN:
                scoped_items = [summary(SUBMISSION_PUBLIC, "submitted", None), summary(SUBMISSION_B, "in_review", REVIEWER_B_ID)]
            else:
                scoped_items = [
                    summary(SUBMISSION_PUBLIC, "submitted", None),
                    summary(SUBMISSION_A, "in_review", REVIEWER_A_ID),
                    summary(SUBMISSION_B, "in_review", REVIEWER_B_ID),
                    summary(SUBMISSION_DONE, "approved", REVIEWER_A_ID),
                ]
            if type(self).inject_self_owned_list and scoped_items:
                scoped_items[0]["owner"]["id"] = AUTHORIZATIONS[access_token]["user_id"]
            if type(self).inject_stale_scan_list and scoped_items:
                scoped_items[0]["image"]["thumbnail_asset"]["scan_policy_version"] = "stale-policy-v0"
            open_statuses = {"submitted", "in_review", "escalated"}
            completed_statuses = {"changes_requested", "rejected", "approved", "withdrawn"}
            counts = {
                "open": sum(item["status"] in open_statuses for item in scoped_items),
                "submitted": sum(item["status"] == "submitted" for item in scoped_items),
                "in_review": sum(item["status"] == "in_review" for item in scoped_items),
                "completed": sum(item["status"] in completed_statuses for item in scoped_items),
            }
            if status_filter == "open":
                items = [item for item in scoped_items if item["status"] in open_statuses]
            elif status_filter == "completed":
                items = [item for item in scoped_items if item["status"] in completed_statuses]
            elif status_filter in {"all", None}:
                items = scoped_items
            else:
                items = [item for item in scoped_items if item["status"] == status_filter]
            result = {
                "actor": actor,
                "items": items,
                "counts": counts,
                "pagination": {"offset": body.get("page_offset", 0), "limit": body.get("page_size", 30), "total": len(items), "has_more": False},
            }
            self.send_json(HTTPStatus.OK, result)
            return
        if self.path == "/rest/v1/rpc/review_get_submission":
            submission_id = body.get("submission_id")
            assignments = {
                SUBMISSION_PUBLIC: ("submitted", None),
                SUBMISSION_A: ("in_review", REVIEWER_A_ID),
                SUBMISSION_B: ("in_review", REVIEWER_B_ID),
                SUBMISSION_DONE: ("approved", REVIEWER_A_ID),
            }
            status, assigned_id = assignments.get(submission_id, ("in_review", REVIEWER_A_ID))
            result = detail(access_token, submission_id, status, assigned_id)
            if type(self).inject_self_owned_detail:
                result["owner"]["id"] = AUTHORIZATIONS[access_token]["user_id"]
            if type(self).inject_stale_scan_detail:
                result["assets"][0]["scan_policy_version"] = "stale-policy-v0"
            self.send_json(HTTPStatus.OK, result)
            return
        if self.path == "/rest/v1/rpc/review_assign_submission":
            self.send_json(HTTPStatus.OK, {"submission": {
                "id": body.get("submission_id"), "status": "submitted", "lock_version": 2,
                "assigned_reviewer_id": AUTHORIZATIONS[access_token]["user_id"],
            }})
            return
        if self.path == "/rest/v1/rpc/review_start_submission":
            if body.get("expected_lock_version") == 999:
                self.send_json(HTTPStatus.OK, {"error": {"code": "REVIEW_VERSION_CONFLICT", "message": "Reload."}})
                return
            self.send_json(HTTPStatus.OK, {"submission": {
                "id": body.get("submission_id"), "status": "in_review", "lock_version": 3,
                "assigned_reviewer_id": AUTHORIZATIONS[access_token]["user_id"],
                "review_started_at": "2026-07-20T00:05:00Z",
            }})
            return
        if self.path == "/rest/v1/rpc/review_decide_submission":
            if type(self).next_decision_result is not None:
                result = type(self).next_decision_result
                type(self).next_decision_result = None
                self.send_json(HTTPStatus.OK, result)
                return
            key = body.get("idempotency_key")
            if key in type(self).decision_results:
                if type(self).decision_payloads.get(key) != body:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "REVIEW_IDEMPOTENCY_CONFLICT",
                        "message": "This decision key was already used with different review data.",
                    }})
                    return
                self.send_json(HTTPStatus.OK, type(self).decision_results[key])
                return
            decision = body.get("decision")
            status_by_decision = {
                "request_changes": "changes_requested",
                "reject": "rejected",
                "approve": "approved",
                "approve_and_publish": "approved",
            }
            result_status = status_by_decision.get(decision, "approved")
            result = {
                "submission": {"id": body.get("submission_id"), "status": result_status, "lock_version": 4, "completed_at": "2026-07-20T01:00:00Z"},
                "decision": {"id": DECISION_ID, "decision": decision, "created_at": "2026-07-20T01:00:00Z"},
                "image": {
                    "id": IMAGE_ID,
                    "workflow_status": result_status,
                    "publication_status": "published" if decision == "approve_and_publish" else "never_published",
                    "published_at": "2026-07-20T01:00:00Z" if decision == "approve_and_publish" else None,
                },
            }
            type(self).decision_results[key] = copy.deepcopy(result)
            type(self).decision_payloads[key] = copy.deepcopy(body)
            type(self).decision_writes += 1
            self.send_json(HTTPStatus.OK, result)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {})


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        return None


class CookieOpener:
    def __init__(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            RejectRedirects(),
        )

    def open(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._opener.open(*args, **kwargs)

    def set_cookie(self, name: str, value: str) -> None:
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain="127.0.0.1", domain_specified=False, domain_initial_dot=False,
            path="/", path_specified=True, secure=False, expires=None, discard=True,
            comment=None, comment_url=None, rest={"HttpOnly": None}, rfc2109=False,
        ))


def request(
    opener: CookieOpener,
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    origin: str | None = None,
    method: str | None = None,
) -> tuple[int, dict, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "MT review boundary test"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        csrf = next((cookie.value for cookie in opener.cookie_jar if cookie.name.endswith("mt_csrf_token")), "")
        if csrf:
            headers["X-CSRF-Token"] = csrf
    req = urllib.request.Request(f"{base_url}{path}", data=body, headers=headers, method=method or ("POST" if body is not None else "GET"))
    try:
        with opener.open(req, timeout=10) as response:
            raw = response.read()
            parsed = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        parsed = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else {}
        return error.code, parsed, error.headers


def raw_head(base_url: str, target: str) -> tuple[int, dict[str, str]]:
    """Send the literal origin-form target, including characters URL clients strip."""
    parsed = urlparse(base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    try:
        connection.putrequest("HEAD", target)
        connection.putheader("Accept", "*/*")
        connection.putheader("User-Agent", "MT review boundary raw HEAD")
        connection.endheaders()
        response = connection.getresponse()
        response.read()
        return response.status, {key: value for key, value in response.getheaders()}
    finally:
        connection.close()


def session(base_url: str, access_token: str, *, csrf: bool = True) -> CookieOpener:
    opener = CookieOpener()
    opener.set_cookie("mt_access_token", access_token)
    if csrf:
        status, result, _ = request(opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Could not initialize CSRF for a test session")
    return opener


def error_code(result: dict) -> str:
    return str(result.get("error", {}).get("code") or "")


def has_no_store(headers: object) -> bool:
    value = headers.get("Cache-Control", "")
    directives = {part.strip().split("=", 1)[0].lower() for part in value.split(",")}
    return "no-store" in directives


def decision_body(key: str, decision: str = "approve") -> dict:
    return {
        "confirmation": f"review-{decision.replace('_', '-')}",
        "expected_version": 3,
        "idempotency_key": key,
        "reason_codes": ["policy_complete"],
        "user_message": "The submitted work satisfies the review policy.",
        "internal_note": "",
        "checklist_result": {
            code: True for code in (
                "file_integrity", "rights", "privacy", "minors", "sensitive_content",
                "hate_illegal", "property_release", "third_party_ip", "ai_disclosure", "public_metadata",
            )
        },
    }


def main() -> None:
    temp_site = tempfile.TemporaryDirectory(prefix="mt-review-boundary-")
    temp_root = Path(temp_site.name)
    (temp_root / "admin-reviews.html").write_text((ROOT / "admin-reviews.html").read_text())
    (temp_root / "admin-reviews.js").write_text((ROOT / "admin-reviews.js").read_text())
    (temp_root / ".env").write_text("static-secret-canary")
    (temp_root / ".git").mkdir()
    (temp_root / ".git" / "config").write_text("static-git-canary")
    (temp_root / "data").mkdir()
    (temp_root / "data" / "archive.db").write_text("static-database-canary")
    private_derivative = temp_root / "assets" / "uploads" / "private" / "display-private.jpg"
    private_derivative.parent.mkdir(parents=True)
    private_derivative.write_bytes(b"static-private-asset-canary")

    FakeSupabaseHandler.review_calls = []
    FakeSupabaseHandler.storage_sign_calls = 0
    FakeSupabaseHandler.inject_cross_reviewer_list = False
    FakeSupabaseHandler.inject_self_owned_list = False
    FakeSupabaseHandler.inject_stale_scan_list = False
    FakeSupabaseHandler.inject_self_owned_detail = False
    FakeSupabaseHandler.inject_stale_scan_detail = False
    FakeSupabaseHandler.next_review_status = None
    FakeSupabaseHandler.next_review_error_code = None
    FakeSupabaseHandler.next_decision_result = None
    FakeSupabaseHandler.decision_results = {}
    FakeSupabaseHandler.decision_payloads = {}
    FakeSupabaseHandler.decision_writes = 0
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_PUBLIC_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")

    class CapturingAppHandler(app.MTRequestHandler):
        captured_logs: list[str] = []

        def log_message(self, format_string: str, *args) -> None:
            type(self).captured_logs.append(format_string % args)

    application = ThreadingHTTPServer(("127.0.0.1", 0), partial(CapturingAppHandler, directory=str(temp_root)))
    threading.Thread(target=application.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{application.server_address[1]}"

    try:
        anonymous = CookieOpener()
        status, _, headers = request(anonymous, base_url, f"/admin/reviews/{SUBMISSION_A}")
        expected_next = f"/auth/sign-in?next=%2Fadmin%2Freviews%2F{SUBMISSION_A}"
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != expected_next:
            raise RuntimeError("Canonical Review Detail did not preserve the anonymous next route")
        for alias in ("/%61dmin-reviews.html", "/admin%2dreviews.html", "//admin-reviews.html"):
            status, _, headers = request(anonymous, base_url, alias)
            if (
                status != HTTPStatus.SEE_OTHER
                or headers.get("Location") != "/admin/reviews"
                or not has_no_store(headers)
            ):
                raise RuntimeError("A normalized Review HTML alias bypassed the protected canonical route")
        for private_alias, canary in (
            ("/%2eenv", "static-secret-canary"),
            ("/%2egit/config", "static-git-canary"),
            ("/d%61ta/archive.db", "static-database-canary"),
            ("/assets/upl%6fads/private/display-private.jpg", "static-private-asset-canary"),
        ):
            status, result, _ = request(anonymous, base_url, private_alias)
            if status != HTTPStatus.NOT_FOUND or canary in json.dumps(result):
                raise RuntimeError("An encoded private static path bypassed the deny-by-default boundary")
            head_status, _, head_headers = request(anonymous, base_url, private_alias, method="HEAD")
            if head_status != HTTPStatus.NOT_FOUND or not has_no_store(head_headers):
                raise RuntimeError("HEAD exposed private static-path metadata")
        for protected_head_path in (
            "/admin/reviews",
            "/admin-reviews.html",
            "/admin-reviews.js",
            "/api/admin/review-submissions",
            "/assets/uploads/private/display-private.jpg",
        ):
            status, _, headers = request(anonymous, base_url, protected_head_path, method="HEAD")
            if status != HTTPStatus.NOT_FOUND or not has_no_store(headers):
                raise RuntimeError("HEAD bypassed an authenticated or private route")
        raw_status, raw_headers = raw_head(base_url, "/data#ignored/archive.db")
        if raw_status != HTTPStatus.NOT_FOUND or not has_no_store(raw_headers):
            raise RuntimeError("A literal fragment-like HEAD target bypassed private-path normalization")

        member = session(base_url, USER_TOKEN)
        status, result, _ = request(member, base_url, "/api/admin/review-submissions")
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "REVIEWER_REQUIRED":
            raise RuntimeError("A normal user reached the Review Queue API")

        recovery = session(base_url, RECOVERY_TOKEN)
        status, result, _ = request(recovery, base_url, "/api/admin/review-submissions")
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "RECOVERY_SESSION_RESTRICTED":
            raise RuntimeError("A recovery session reached Review Queue data")
        status, _, headers = request(recovery, base_url, "/admin/reviews")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("A recovery session opened the Review Queue page")

        admin_aal1 = session(base_url, ADMIN_AAL1_TOKEN)
        status, _, headers = request(admin_aal1, base_url, f"/admin/reviews/{SUBMISSION_A}")
        expected_mfa = f"/auth/mfa?next=%2Fadmin%2Freviews%2F{SUBMISSION_A}"
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != expected_mfa:
            raise RuntimeError("Admin AAL1 Review Detail did not preserve its MFA next route")
        status, result, _ = request(admin_aal1, base_url, "/api/admin/review-submissions")
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "MFA_REQUIRED":
            raise RuntimeError("Admin AAL1 reached Review Queue data")

        reviewer = session(base_url, REVIEWER_A_TOKEN)
        status, _, headers = request(reviewer, base_url, "/admin/reviews")
        if status != HTTPStatus.OK or not has_no_store(headers):
            raise RuntimeError("Reviewer page was unavailable or cacheable")
        status, _, headers = request(reviewer, base_url, "/admin-reviews.js")
        if status != HTTPStatus.OK or not has_no_store(headers):
            raise RuntimeError("Review client script was cacheable")
        status, _, headers = request(reviewer, base_url, "/admin%2dreviews.js")
        if status != HTTPStatus.OK or not has_no_store(headers):
            raise RuntimeError("A normalized Review client alias bypassed no-store")

        status, result, _ = request(reviewer, base_url, "/api/admin/review-submissions?status=open&assignment=all")
        if status != HTTPStatus.OK or len(result.get("items", [])) != 2:
            raise RuntimeError("Reviewer-safe queue items were not returned")
        if any("thumbnail_asset" in item.get("image", {}) for item in result["items"]):
            raise RuntimeError("Review list leaked the provider asset shape")
        if any(set(item.get("image", {}).get("thumbnail", {})).intersection({"storage_bucket", "storage_key", "provider_secret"}) for item in result["items"]):
            raise RuntimeError("Review list leaked private Storage coordinates")
        if any("email" in item.get("owner", {}) for item in result["items"]):
            raise RuntimeError("Review list leaked owner email")
        status, result, _ = request(reviewer, base_url, "/api/admin/review-submissions?status=completed&assignment=all")
        if status != HTTPStatus.OK or result.get("items") != [] or result.get("counts", {}).get("completed") != 0:
            raise RuntimeError("Reviewer completed aggregates were not scoped to the reviewer boundary")

        for injection in ("inject_self_owned_list", "inject_stale_scan_list"):
            setattr(FakeSupabaseHandler, injection, True)
            signs_before = FakeSupabaseHandler.storage_sign_calls
            status, result, _ = request(reviewer, base_url, "/api/admin/review-submissions")
            setattr(FakeSupabaseHandler, injection, False)
            if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "REVIEW_PROVIDER_FAILED":
                raise RuntimeError(f"Unsafe provider list mutation {injection} did not fail closed")
            if FakeSupabaseHandler.storage_sign_calls != signs_before:
                raise RuntimeError(f"Unsafe provider list mutation {injection} was signed before validation")

        FakeSupabaseHandler.inject_cross_reviewer_list = True
        signs_before = FakeSupabaseHandler.storage_sign_calls
        status, result, _ = request(reviewer, base_url, "/api/admin/review-submissions")
        FakeSupabaseHandler.inject_cross_reviewer_list = False
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "REVIEW_PROVIDER_FAILED":
            raise RuntimeError("Cross-reviewer list data did not fail closed")
        if FakeSupabaseHandler.storage_sign_calls != signs_before:
            raise RuntimeError("Cross-reviewer list data was signed before authorization validation")

        signs_before = FakeSupabaseHandler.storage_sign_calls
        status, result, _ = request(reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}")
        if status != HTTPStatus.OK or len(result.get("assets", [])) != 3:
            raise RuntimeError("Assigned reviewer could not load Review Detail")
        if FakeSupabaseHandler.storage_sign_calls != signs_before + 3:
            raise RuntimeError("Assigned reviewer did not retain all three Review Detail assets")
        if any(set(item).intersection({"storage_bucket", "storage_key", "provider_secret"}) for item in result["assets"]):
            raise RuntimeError("Review Detail leaked private Storage coordinates")
        if "gps" in result.get("image", {}).get("version", {}).get("public_exif", {}):
            raise RuntimeError("Review Detail leaked non-public EXIF")
        for injection in ("inject_self_owned_detail", "inject_stale_scan_detail"):
            setattr(FakeSupabaseHandler, injection, True)
            signs_before = FakeSupabaseHandler.storage_sign_calls
            status, result, _ = request(reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}")
            setattr(FakeSupabaseHandler, injection, False)
            if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "REVIEW_PROVIDER_FAILED":
                raise RuntimeError(f"Unsafe provider detail mutation {injection} did not fail closed")
            if FakeSupabaseHandler.storage_sign_calls != signs_before:
                raise RuntimeError(f"Unsafe provider detail mutation {injection} was signed before validation")
        signs_before = FakeSupabaseHandler.storage_sign_calls
        status, result, _ = request(reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_B}")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "REVIEW_PROVIDER_FAILED":
            raise RuntimeError("Cross-reviewer Review Detail did not fail closed")
        if FakeSupabaseHandler.storage_sign_calls != signs_before:
            raise RuntimeError("Cross-reviewer assets were signed before authorization validation")

        admin = session(base_url, ADMIN_AAL2_TOKEN)
        status, result, _ = request(admin, base_url, "/api/admin/review-submissions?status=completed&assignment=all")
        if status != HTTPStatus.OK or [item.get("id") for item in result.get("items", [])] != [SUBMISSION_DONE]:
            raise RuntimeError("Completed queue filter was not forwarded through the stable API")
        if FakeSupabaseHandler.review_calls[-1][1].get("status_filter") != "completed":
            raise RuntimeError("Completed filter changed before reaching the provider RPC")
        signs_before = FakeSupabaseHandler.storage_sign_calls
        status, result, _ = request(admin, base_url, f"/api/admin/review-submissions/{SUBMISSION_DONE}")
        if status != HTTPStatus.OK or {asset.get("kind") for asset in result.get("assets", [])} != {"display", "thumbnail"}:
            raise RuntimeError("Admin AAL2 did not receive the derivative-only Review Detail")
        if FakeSupabaseHandler.storage_sign_calls != signs_before + 2:
            raise RuntimeError("Admin AAL2 attempted to sign the Review Detail original")

        no_csrf = session(base_url, REVIEWER_A_TOKEN, csrf=False)
        calls_before = len(FakeSupabaseHandler.review_calls)
        status, result, _ = request(
            no_csrf, base_url, f"/api/admin/review-submissions/{SUBMISSION_PUBLIC}/assign",
            payload={"confirmation": "assign-to-me", "expected_version": 1}, origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "CSRF_REJECTED":
            raise RuntimeError("Review mutation accepted a missing CSRF token")
        if len(FakeSupabaseHandler.review_calls) != calls_before:
            raise RuntimeError("CSRF-rejected Review mutation reached the provider")

        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_PUBLIC}/assign",
            payload={"confirmation": "assign-to-me", "expected_version": 1}, origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("submission", {}).get("assigned_reviewer_id") != REVIEWER_A_ID:
            raise RuntimeError("Atomic Assign to Me did not return its strict DTO")
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_PUBLIC}/start",
            payload={"confirmation": "start-review", "expected_version": 2}, origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("submission", {}).get("status") != "in_review":
            raise RuntimeError("Start Review did not return its strict DTO")
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_PUBLIC}/start",
            payload={"confirmation": "start-review", "expected_version": 999}, origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(result) != "REVIEW_VERSION_CONFLICT":
            raise RuntimeError("Stale Start Review did not preserve its CAS error")

        for endpoint, payload in (
            ("assign", {"confirmation": "assign-to-me", "expected_version": 2}),
            ("start", {"confirmation": "start-review", "expected_version": 2}),
            ("approve", decision_body("70000000-0000-4000-8000-000000000009")),
        ):
            FakeSupabaseHandler.next_review_error_code = "REVIEW_SELF_REVIEW_FORBIDDEN"
            status, result, _ = request(
                reviewer,
                base_url,
                f"/api/admin/review-submissions/{SUBMISSION_A}/{endpoint}",
                payload=payload,
                origin=base_url,
            )
            if status != HTTPStatus.FORBIDDEN or error_code(result) != "REVIEW_SELF_REVIEW_FORBIDDEN":
                raise RuntimeError(f"Self-review error mapping was unstable for {endpoint}")

        calls_before = len(FakeSupabaseHandler.review_calls)
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}/approve",
            payload={**decision_body("70000000-0000-4000-8000-000000000001"), "unexpected": True}, origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(result) != "REVIEW_DECISION_INVALID":
            raise RuntimeError("Decision accepted an unexpected request field")
        if len(FakeSupabaseHandler.review_calls) != calls_before:
            raise RuntimeError("Invalid Decision input reached the provider")

        for invalid_reasons in (["missing_rights"], ["policy_complete", "policy_complete"]):
            calls_before = len(FakeSupabaseHandler.review_calls)
            invalid_payload = decision_body("70000000-0000-4000-8000-000000000008")
            invalid_payload["reason_codes"] = invalid_reasons
            status, result, _ = request(
                reviewer,
                base_url,
                f"/api/admin/review-submissions/{SUBMISSION_A}/approve",
                payload=invalid_payload,
                origin=base_url,
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(result) != "REVIEW_DECISION_INVALID":
                raise RuntimeError("Decision accepted a duplicate or action-incompatible reason code")
            if len(FakeSupabaseHandler.review_calls) != calls_before:
                raise RuntimeError("Invalid Decision reason codes reached the provider")

        idempotency_key = "70000000-0000-4000-8000-000000000002"
        payload = decision_body(idempotency_key)
        for _ in range(2):
            status, result, _ = request(
                reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}/approve",
                payload=payload, origin=base_url,
            )
            if status != HTTPStatus.OK or result.get("decision", {}).get("id") != DECISION_ID:
                raise RuntimeError("Idempotent Review Decision replay was not stable")
        if FakeSupabaseHandler.decision_writes != 1:
            raise RuntimeError("Review Decision replay duplicated provider state")
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}/approve",
            payload={**payload, "user_message": "A different message must not reuse the same key."}, origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(result) != "REVIEW_IDEMPOTENCY_CONFLICT":
            raise RuntimeError("Same-key different-payload Review Decision was not rejected")
        if FakeSupabaseHandler.decision_writes != 1:
            raise RuntimeError("Idempotency conflict duplicated provider state")

        FakeSupabaseHandler.next_decision_result = {
            "submission": {"id": SUBMISSION_A, "status": "changes_requested", "lock_version": 4},
            "decision": {"id": DECISION_ID, "decision": "approve", "created_at": "2026-07-20T01:00:00Z"},
            "image": {"id": IMAGE_ID, "workflow_status": "approved", "publication_status": "never_published"},
        }
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}/approve",
            payload=decision_body("70000000-0000-4000-8000-000000000005"), origin=base_url,
        )
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "REVIEW_PROVIDER_FAILED":
            raise RuntimeError("Semantically inconsistent Decision DTO did not fail closed")

        provider_calls_before = len(FakeSupabaseHandler.review_calls)
        status, result, _ = request(
            reviewer, base_url, f"/api/admin/review-submissions/{SUBMISSION_A}/approve-and-publish",
            payload=decision_body("70000000-0000-4000-8000-000000000003", "approve_and_publish"), origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "REVIEW_PUBLISH_ADMIN_REQUIRED":
            raise RuntimeError("Reviewer Publish was not rejected")
        if len(FakeSupabaseHandler.review_calls) != provider_calls_before:
            raise RuntimeError("Reviewer Publish reached the provider before its Admin check")

        status, result, _ = request(
            admin, base_url, f"/api/admin/review-submissions/{SUBMISSION_DONE}/approve-and-publish",
            payload=decision_body("70000000-0000-4000-8000-000000000004", "approve_and_publish"), origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("image", {}).get("publication_status") != "published":
            raise RuntimeError("Admin AAL2 could not Approve and Publish")

        for provider_status, expected_status, expected_code in (
            (HTTPStatus.UNAUTHORIZED, HTTPStatus.UNAUTHORIZED, "AUTH_REQUIRED"),
            (HTTPStatus.FORBIDDEN, HTTPStatus.FORBIDDEN, "REVIEW_ACCESS_REVOKED"),
            (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, "REVIEW_PROVIDER_UNAVAILABLE"),
        ):
            FakeSupabaseHandler.next_review_status = provider_status
            status, result, _ = request(admin, base_url, "/api/admin/review-submissions?status=completed")
            if status != expected_status or error_code(result) != expected_code:
                raise RuntimeError(f"Provider {provider_status} did not map to stable Review error semantics")
            if "provider detail must not escape" in json.dumps(result):
                raise RuntimeError("A provider error detail escaped the stable Review error boundary")

        captured_logs = "\n".join(CapturingAppHandler.captured_logs)
        forbidden_log_values = (
            USER_TOKEN,
            REVIEWER_A_TOKEN,
            ADMIN_AAL2_TOKEN,
            f"{OWNER_ID}/{IMAGE_ID}/original.jpg",
            "token=fake",
            "provider detail must not escape",
            "The submitted work satisfies the review policy.",
        )
        if any(value and value in captured_logs for value in forbidden_log_values):
            raise RuntimeError("Review access logs exposed a credential, private asset, or decision payload")

        print("review_route_role_mfa_recovery_guards=yes")
        print("review_canonical_detail_next=yes")
        print("review_protected_assets_no_store=yes")
        print("reviewer_scope_fail_closed=yes")
        print("review_dto_allowlists=yes")
        print("review_completed_filter=yes")
        print("review_csrf_boundary=yes")
        print("review_assignment_and_cas=yes")
        print("review_decision_idempotency=yes")
        print("review_publish_admin_preflight=yes")
        print("review_provider_error_mapping=yes")
        print("secrets_logged=no")
    finally:
        application.shutdown()
        application.server_close()
        provider.shutdown()
        provider.server_close()
        temp_site.cleanup()


if __name__ == "__main__":
    main()
