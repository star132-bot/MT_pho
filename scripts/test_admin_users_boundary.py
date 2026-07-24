#!/usr/bin/env python3
"""Secret-free HTTP acceptance for Admin Users governance."""

from __future__ import annotations

import base64
import copy
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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PUBLISHABLE_KEY = "admin-users-test-publishable-key"
MEMBER_ID = "10000000-0000-4000-8000-000000000081"
REVIEWER_ID = "10000000-0000-4000-8000-000000000082"
ADMIN_AAL1_ID = "10000000-0000-4000-8000-000000000083"
ADMIN_ID = "10000000-0000-4000-8000-000000000084"
SUPER_ADMIN_ID = "10000000-0000-4000-8000-000000000085"
RECOVERY_ADMIN_ID = "10000000-0000-4000-8000-000000000086"
INACTIVE_ADMIN_ID = "10000000-0000-4000-8000-000000000087"
TARGET_ID = "20000000-0000-4000-8000-000000000081"
OTHER_USER_ID = "20000000-0000-4000-8000-000000000082"
IMAGE_ID = "30000000-0000-4000-8000-000000000081"
ACTION_ID = "40000000-0000-4000-8000-000000000081"
AUDIT_ID = "50000000-0000-4000-8000-000000000081"
POLICY_VERSION = "mt-admin-user-governance-2026-07-v1"

PRIVATE_CANARIES = (
    "private-auth-subject-canary",
    "private-avatar-locator-canary",
    "private-profile-bio-canary",
    "private-social-url-canary",
    "private-original-filename-canary",
    "private-audit-before-state-canary",
    "private-session-token-canary",
    "private-ip-address-canary",
    "private-provider-debug-canary",
)


def fake_access_token(user_id: str, *, aal: str = "aal1", method: str = "password") -> str:
    claims = {"sub": user_id, "aal": aal, "amr": [{"method": method}]}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


MEMBER_TOKEN = fake_access_token(MEMBER_ID)
REVIEWER_TOKEN = fake_access_token(REVIEWER_ID)
ADMIN_AAL1_TOKEN = fake_access_token(ADMIN_AAL1_ID)
ADMIN_TOKEN = fake_access_token(ADMIN_ID, aal="aal2", method="totp")
SUPER_ADMIN_TOKEN = fake_access_token(SUPER_ADMIN_ID, aal="aal2", method="totp")
RECOVERY_ADMIN_TOKEN = fake_access_token(RECOVERY_ADMIN_ID, aal="aal2", method="recovery")
INACTIVE_ADMIN_TOKEN = fake_access_token(INACTIVE_ADMIN_ID, aal="aal2", method="totp")

AUTHORIZATIONS = {
    MEMBER_TOKEN: {"user_id": MEMBER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"},
    REVIEWER_TOKEN: {"user_id": REVIEWER_ID, "account_status": "active", "roles": ["user", "reviewer"], "aal": "aal1"},
    ADMIN_AAL1_TOKEN: {"user_id": ADMIN_AAL1_ID, "account_status": "active", "roles": ["user", "admin"], "aal": "aal1"},
    ADMIN_TOKEN: {"user_id": ADMIN_ID, "account_status": "active", "roles": ["user", "admin"], "aal": "aal2"},
    SUPER_ADMIN_TOKEN: {"user_id": SUPER_ADMIN_ID, "account_status": "active", "roles": ["user", "super_admin"], "aal": "aal2"},
    RECOVERY_ADMIN_TOKEN: {"user_id": RECOVERY_ADMIN_ID, "account_status": "active", "roles": ["user", "admin"], "aal": "aal2"},
    INACTIVE_ADMIN_TOKEN: {"user_id": INACTIVE_ADMIN_ID, "account_status": "suspended", "roles": ["user", "admin"], "aal": "aal2"},
}


def actor(access_token: str) -> dict:
    authorization = AUTHORIZATIONS[access_token]
    return {
        "id": authorization["user_id"],
        "roles": authorization["roles"],
        "can_manage_users": True,
        "can_manage_roles": "super_admin" in authorization["roles"],
        "provider_debug": "private-provider-debug-canary",
    }


def user_summary(state: dict) -> dict:
    return {
        "id": TARGET_ID,
        "auth_subject": "private-auth-subject-canary",
        "email": "creator@example.test",
        "email_verified_at": "2026-07-20T00:00:00Z",
        "account_status": state["account_status"],
        "version": state["version"],
        "is_system_identity": False,
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-23T04:00:00Z",
        "last_active_at": "2026-07-23T03:00:00Z",
        "roles": list(state["roles"]),
        "profile": {
            "user_id": TARGET_ID,
            "display_name": "Field Notes",
            "avatar_url": "private-avatar-locator-canary",
            "professional_headline": "Documentary photographer",
            "company": "Field Office",
            "country_code": "US",
            "city": "Portland",
            "availability_status": "open",
            "bio": "private-profile-bio-canary",
            "website_url": "private-social-url-canary",
        },
        "mfa_status": "unavailable",
        "sessions": {
            "status": "provider_managed",
            "active_count": None,
            "provider_action_required": True,
            "refresh_token": "private-session-token-canary",
        },
        "image_counts": {
            "total": 4,
            "draft": 1,
            "submitted": 0,
            "in_review": 1,
            "changes_requested": 0,
            "rejected": 0,
            "approved": 2,
            "published": 1,
            "unpublished": 1,
            "quarantined": 0,
            "processing_failed": 0,
        },
        "storage": {"used_bytes": 4096, "quota_bytes": None, "quota_status": "unavailable"},
        "takedown_case_count": 1,
        "provider_debug": "private-provider-debug-canary",
    }


def governance_action(
    access_token: str,
    state: dict,
    *,
    action_code: str = "revoke_sessions",
    target_role: str | None = None,
    reason_code: str = "access_review",
    expected_version: int | None = None,
) -> dict:
    return {
        "id": ACTION_ID,
        "target_user_id": TARGET_ID,
        "action": action_code,
        "target_role": target_role,
        "reason_code": reason_code,
        "actor_user_id": AUTHORIZATIONS[access_token]["user_id"],
        "actor_role": "super_admin" if "super_admin" in AUTHORIZATIONS[access_token]["roles"] else "admin",
        "expected_user_version": expected_version if expected_version is not None else state["version"],
        "provider_action_required": action_code == "revoke_sessions",
        "policy_version": POLICY_VERSION,
        "created_at": "2026-07-23T05:00:00Z",
        "internal_note": "private-provider-debug-canary",
    }


def user_detail(access_token: str, state: dict) -> dict:
    summary = user_summary(state)
    summary["profile"].update({
        "instagram_url": "private-social-url-canary",
        "linkedin_url": "private-social-url-canary",
        "preferred_locale": "en",
        "timezone": "UTC",
        "copyright_name": "Private copyright value",
        "default_license_preference": "all-rights-reserved",
    })
    summary.update({
        "recent_images": [{
            "id": IMAGE_ID,
            "owner_user_id": TARGET_ID,
            "original_filename": "private-original-filename-canary",
            "processing_status": "ready",
            "workflow_status": "approved",
            "publication_status": "published",
            "version": 3,
            "created_at": "2026-07-20T00:00:00Z",
            "updated_at": "2026-07-22T00:00:00Z",
            "published_at": "2026-07-22T00:00:00Z",
        }],
        "governance_actions": [governance_action(access_token, state)],
        "audit_timeline": [{
            "id": AUDIT_ID,
            "target_type": "user",
            "target_id": TARGET_ID,
            "target_user_id": TARGET_ID,
            "actor_user_id": ADMIN_ID,
            "actor_role": "admin",
            "action": "admin.user.revoke_sessions_requested",
            "reason_code": "access_review",
            "result": "success",
            "policy_version": POLICY_VERSION,
            "created_at": "2026-07-23T05:00:00Z",
            "request_id": "private-provider-debug-canary",
            "before_state": "private-audit-before-state-canary",
            "ip_address": "private-ip-address-canary",
        }],
    })
    return summary


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    state = {"account_status": "active", "version": 3, "roles": ["user"]}
    admin_calls: list[tuple[str, dict, str]] = []
    mutation_payloads: dict[str, dict] = {}
    mutation_results: dict[str, dict] = {}
    mutation_writes = 0
    next_status: int | None = None
    next_error: str | None = None
    next_drift: str | None = None

    def log_message(self, _format, *_args) -> None:
        return

    def access_token(self) -> str:
        return self.headers.get("Authorization", "").removeprefix("Bearer ")

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        access_token = self.access_token()
        if self.path == "/auth/v1/user" and access_token in AUTHORIZATIONS:
            user_id = AUTHORIZATIONS[access_token]["user_id"]
            self.send_json(HTTPStatus.OK, {
                "id": user_id,
                "email": f"{user_id[-1]}@example.test",
                "email_confirmed_at": "2026-07-20T00:00:00Z",
                "factors": [],
            })
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        access_token = self.access_token()
        body = self.body()
        if self.path == "/rest/v1/rpc/current_authorization":
            authorization = AUTHORIZATIONS.get(access_token)
            self.send_json(HTTPStatus.OK if authorization else HTTPStatus.UNAUTHORIZED, authorization or {})
            return
        if not self.path.startswith("/rest/v1/rpc/admin_"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        type(self).admin_calls.append((self.path, copy.deepcopy(body), access_token))
        if type(self).next_status is not None:
            status = type(self).next_status
            type(self).next_status = None
            self.send_json(status, {"message": "private-provider-debug-canary"})
            return
        if type(self).next_error is not None:
            code = type(self).next_error
            type(self).next_error = None
            self.send_json(HTTPStatus.OK, {"error": {"code": code, "message": "private-provider-debug-canary"}})
            return
        if access_token not in {ADMIN_TOKEN, SUPER_ADMIN_TOKEN}:
            self.send_json(HTTPStatus.FORBIDDEN, {})
            return
        if self.path == "/rest/v1/rpc/admin_list_users":
            item = user_summary(type(self).state)
            drift = type(self).next_drift
            type(self).next_drift = None
            if drift == "list_profile_user":
                item["profile"]["user_id"] = OTHER_USER_ID
            elif drift == "list_mfa_claim":
                item["mfa_status"] = "enrolled"
            elif drift == "list_session_claim":
                item["sessions"]["active_count"] = 4
            matches_status = body.get("status_filter") in {"all", item["account_status"]}
            matches_role = body.get("role_filter") in {"all", *item["roles"]}
            matches = matches_status and matches_role and body.get("page_offset", 0) == 0
            statuses = {
                "all": 1,
                "pending_verification": 0,
                "active": int(type(self).state["account_status"] == "active"),
                "suspended": int(type(self).state["account_status"] == "suspended"),
                "banned": 0,
                "deletion_requested": 0,
                "deleted": 0,
            }
            roles = {role: int(role in type(self).state["roles"]) for role in ("user", "reviewer", "admin", "super_admin")}
            self.send_json(HTTPStatus.OK, {
                "actor": actor(access_token),
                "items": [item] if matches else [],
                "counts": {"statuses": statuses, "roles": roles},
                "pagination": {
                    "limit": body.get("page_size", 30),
                    "offset": body.get("page_offset", 0),
                    "total": int(matches_status and matches_role),
                    "has_more": False,
                },
                "provider_debug": "private-provider-debug-canary",
            })
            return
        if self.path == "/rest/v1/rpc/admin_get_user":
            detail = user_detail(access_token, type(self).state)
            drift = type(self).next_drift
            type(self).next_drift = None
            if drift == "detail_user":
                detail["id"] = OTHER_USER_ID
            elif drift == "detail_profile_user":
                detail["profile"]["user_id"] = OTHER_USER_ID
            elif drift == "detail_image_owner":
                detail["recent_images"][0]["owner_user_id"] = OTHER_USER_ID
            elif drift == "detail_action_target":
                detail["governance_actions"][0]["target_user_id"] = OTHER_USER_ID
            elif drift == "detail_audit_target":
                detail["audit_timeline"][0]["target_id"] = OTHER_USER_ID
            elif drift == "detail_audit_relationship":
                detail["audit_timeline"][0]["target_user_id"] = OTHER_USER_ID
            self.send_json(HTTPStatus.OK, {"actor": actor(access_token), "user": detail})
            return
        if self.path == "/rest/v1/rpc/admin_govern_user":
            key = str(body.get("idempotency_key") or "")
            existing = type(self).mutation_results.get(key)
            if existing is not None:
                if type(self).mutation_payloads[key] != body:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "ADMIN_USER_IDEMPOTENCY_CONFLICT",
                        "message": "private-provider-debug-canary",
                    }})
                    return
                replay = copy.deepcopy(existing)
                replay["replayed"] = True
                self.send_json(HTTPStatus.OK, replay)
                return
            if body.get("target_user_id") != TARGET_ID:
                self.send_json(HTTPStatus.OK, {"error": {"code": "ADMIN_USER_NOT_FOUND", "message": "not found"}})
                return
            if body.get("expected_version") != type(self).state["version"]:
                self.send_json(HTTPStatus.OK, {"error": {
                    "code": "ADMIN_USER_VERSION_CONFLICT",
                    "message": "private-provider-debug-canary",
                }})
                return
            action_code = body.get("action")
            target_role = body.get("target_role")
            reason_code = body.get("reason_code")
            drift = type(self).next_drift
            type(self).next_drift = None
            if drift:
                hypothetical = copy.deepcopy(type(self).state)
                hypothetical["version"] += 1
                result = {
                    "actor": actor(access_token),
                    "action": governance_action(
                        access_token,
                        type(self).state,
                        action_code=action_code,
                        target_role=target_role,
                        reason_code=reason_code,
                        expected_version=type(self).state["version"],
                    ),
                    "user": user_summary(hypothetical),
                    "replayed": False,
                }
                if drift == "mutation_target":
                    result["action"]["target_user_id"] = OTHER_USER_ID
                elif drift == "mutation_actor":
                    result["action"]["actor_user_id"] = OTHER_USER_ID
                elif drift == "mutation_user":
                    result["user"]["id"] = OTHER_USER_ID
                elif drift == "mutation_reason":
                    result["action"]["reason_code"] = "other"
                elif drift == "mutation_provider_flag":
                    result["action"]["provider_action_required"] = not result["action"]["provider_action_required"]
                self.send_json(HTTPStatus.OK, result)
                return
            before_version = type(self).state["version"]
            if action_code == "suspend":
                type(self).state["account_status"] = "suspended"
            elif action_code == "reactivate":
                type(self).state["account_status"] = "active"
            elif action_code == "grant_role":
                type(self).state["roles"].append(target_role)
                type(self).state["roles"] = sorted(set(type(self).state["roles"]))
            elif action_code == "revoke_role":
                type(self).state["roles"] = [role for role in type(self).state["roles"] if role != target_role]
            type(self).state["version"] += 1
            result = {
                "actor": actor(access_token),
                "action": governance_action(
                    access_token,
                    type(self).state,
                    action_code=action_code,
                    target_role=target_role,
                    reason_code=reason_code,
                    expected_version=before_version,
                ),
                "user": user_summary(type(self).state),
                "replayed": False,
                "provider_debug": "private-provider-debug-canary",
            }
            type(self).mutation_payloads[key] = copy.deepcopy(body)
            type(self).mutation_results[key] = copy.deepcopy(result)
            type(self).mutation_writes += 1
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
    payload: object | None = None,
    origin: str | None = None,
    method: str | None = None,
    content_type: str = "application/json",
) -> tuple[int, dict, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "MT Admin Users boundary test"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = content_type
        csrf = next((cookie.value for cookie in opener.cookie_jar if cookie.name.endswith("mt_csrf_token")), "")
        if csrf:
            headers["X-CSRF-Token"] = csrf
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with opener.open(req, timeout=10) as response:
            raw = response.read()
            parsed = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        parsed = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else {}
        return error.code, parsed, error.headers


def session(base_url: str, access_token: str, *, csrf: bool = True) -> CookieOpener:
    opener = CookieOpener()
    opener.set_cookie("mt_access_token", access_token)
    if csrf:
        status, result, _ = request(opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Could not initialize CSRF for an Admin Users test session")
    return opener


def error_code(result: dict) -> str:
    return str(result.get("error", {}).get("code") or "")


def mutation_body(key: str, action: str, *, expected_version: int, target_role: str | None = None) -> dict:
    reasons = {
        "suspend": "security_review",
        "reactivate": "investigation_cleared",
        "grant_role": "operational_need",
        "revoke_role": "access_review",
        "revoke_sessions": "suspected_compromise",
    }
    body = {
        "action": action,
        "reason_code": reasons[action],
        "expected_version": expected_version,
        "idempotency_key": key,
    }
    if target_role is not None:
        body["target_role"] = target_role
    return body


def assert_no_sensitive(payload: object, label: str) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    if any(canary in serialized for canary in PRIVATE_CANARIES):
        raise RuntimeError(f"{label} leaked a private provider value")
    lowered = serialized.lower()
    for forbidden in (
        '"auth_subject"', '"avatar_url"', '"bio"', '"website_url"',
        '"recent_images"', '"original_filename"', '"before_state"',
        '"after_state"', '"ip_address"', '"refresh_token"',
    ):
        if forbidden in lowered:
            raise RuntimeError(f"{label} leaked forbidden field {forbidden}")


def assert_user_allowlist(user: object, label: str, *, detail: bool = False) -> None:
    expected = {
        "id", "email", "email_verified", "email_verified_at", "account_status", "version",
        "is_system_identity", "roles", "profile", "mfa_status", "sessions", "image_counts",
        "storage", "takedown_case_count", "created_at", "updated_at", "last_active_at",
        "is_self", "permissions",
    }
    if detail:
        expected.update({"governance_actions", "audit_timeline"})
    if not isinstance(user, dict) or set(user) != expected:
        raise RuntimeError(f"{label} user DTO escaped its exact allowlist: {user}")
    if set(user["profile"]) != {
        "display_name", "professional_headline", "company", "city", "country_code", "availability_status",
    }:
        raise RuntimeError(f"{label} profile DTO escaped its exact allowlist")
    if user.get("mfa_status") != "unavailable":
        raise RuntimeError(f"{label} fabricated MFA state")
    sessions = user.get("sessions") or {}
    if sessions != {"status": "provider_managed", "active_count": None, "provider_action_required": True}:
        raise RuntimeError(f"{label} fabricated provider session state")
    if detail:
        action_keys = {
            "id", "action", "target_role", "reason_code", "actor_role",
            "expected_user_version", "provider_action_required", "policy_version", "created_at",
        }
        audit_keys = {"id", "action", "reason_code", "actor_role", "policy_version", "result", "created_at"}
        if any(set(action) != action_keys for action in user["governance_actions"]):
            raise RuntimeError(f"{label} governance action escaped its exact allowlist")
        if any(set(entry) != audit_keys for entry in user["audit_timeline"]):
            raise RuntimeError(f"{label} audit entry escaped its exact allowlist")


def assert_denied_without_provider(
    opener: CookieOpener,
    base_url: str,
    expected_status: int,
    expected_code: str,
    label: str,
) -> None:
    before = len(FakeSupabaseHandler.admin_calls)
    status, result, _ = request(opener, base_url, "/api/admin/users")
    if status != expected_status or error_code(result) != expected_code:
        raise RuntimeError(f"{label} did not fail closed: {status} {result}")
    if len(FakeSupabaseHandler.admin_calls) != before:
        raise RuntimeError(f"{label} reached the Admin Users provider")


def main() -> None:
    temp_site = tempfile.TemporaryDirectory(prefix="mt-admin-users-boundary-")
    temp_root = Path(temp_site.name)
    (temp_root / "admin-users.html").write_text(
        (ROOT / "admin-users.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    FakeSupabaseHandler.state = {"account_status": "active", "version": 3, "roles": ["user"]}
    FakeSupabaseHandler.admin_calls = []
    FakeSupabaseHandler.mutation_payloads = {}
    FakeSupabaseHandler.mutation_results = {}
    FakeSupabaseHandler.mutation_writes = 0
    FakeSupabaseHandler.next_status = None
    FakeSupabaseHandler.next_error = None
    FakeSupabaseHandler.next_drift = None
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = PUBLISHABLE_KEY
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
        status, _, headers = request(anonymous, base_url, "/admin/users")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/sign-in?next=%2Fadmin%2Fusers":
            raise RuntimeError("Anonymous Admin Users page did not preserve its canonical next route")
        status, result, _ = request(anonymous, base_url, "/api/admin/users")
        if status != HTTPStatus.UNAUTHORIZED or error_code(result) != "AUTH_REQUIRED":
            raise RuntimeError("Anonymous caller reached Admin Users data")
        status, _, headers = request(anonymous, base_url, "/api/admin/users", method="HEAD")
        if status != HTTPStatus.NOT_FOUND or headers.get("Cache-Control") != "no-store":
            raise RuntimeError("HEAD disclosed the protected Admin Users API")

        member = session(base_url, MEMBER_TOKEN)
        reviewer = session(base_url, REVIEWER_TOKEN)
        admin_aal1 = session(base_url, ADMIN_AAL1_TOKEN)
        recovery = session(base_url, RECOVERY_ADMIN_TOKEN)
        inactive = session(base_url, INACTIVE_ADMIN_TOKEN)
        admin = session(base_url, ADMIN_TOKEN)
        super_admin = session(base_url, SUPER_ADMIN_TOKEN)
        assert_denied_without_provider(member, base_url, HTTPStatus.FORBIDDEN, "ADMIN_REQUIRED", "Member")
        assert_denied_without_provider(reviewer, base_url, HTTPStatus.FORBIDDEN, "ADMIN_REQUIRED", "Reviewer")
        assert_denied_without_provider(admin_aal1, base_url, HTTPStatus.FORBIDDEN, "MFA_REQUIRED", "Admin AAL1")
        assert_denied_without_provider(recovery, base_url, HTTPStatus.FORBIDDEN, "RECOVERY_SESSION_RESTRICTED", "Recovery Admin")
        assert_denied_without_provider(inactive, base_url, HTTPStatus.FORBIDDEN, "ACCOUNT_RESTRICTED", "Inactive Admin")

        status, _, headers = request(admin_aal1, base_url, "/admin/users")
        if status != HTTPStatus.SEE_OTHER or not str(headers.get("Location", "")).startswith("/auth/mfa?"):
            raise RuntimeError("Admin AAL1 page did not redirect to MFA")
        status, _, _ = request(admin, base_url, "/admin/users")
        if status != HTTPStatus.OK:
            raise RuntimeError("Admin AAL2 could not open Admin Users")
        status, _, _ = request(super_admin, base_url, f"/admin/users/{TARGET_ID}")
        if status != HTTPStatus.OK:
            raise RuntimeError("Super Admin could not open a deep-linked User Detail")
        status, _, headers = request(admin, base_url, "/admin-users.html")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/admin/users":
            raise RuntimeError("Legacy Admin Users page did not redirect to the canonical route")

        status, result, _ = request(
            admin,
            base_url,
            "/api/admin/users?status=active&role=user&sort=last_login_desc&q=Field&limit=30&offset=0",
        )
        if status != HTTPStatus.OK or set(result) != {"actor", "items", "counts", "pagination"}:
            raise RuntimeError(f"Admin Users list envelope drifted: {result}")
        if len(result.get("items", [])) != 1:
            raise RuntimeError("Valid Admin Users filters did not return the target user")
        assert_user_allowlist(result["items"][0], "Admin Users list")
        assert_no_sensitive(result, "Admin Users list")
        actor_result = result.get("actor") or {}
        if set(actor_result) != {"id", "roles", "permissions"} or actor_result.get("permissions", {}).get("can_manage_roles") is not False:
            raise RuntimeError("Admin Users actor capabilities were not fail-closed")
        last_call = FakeSupabaseHandler.admin_calls[-1]
        expected_list_payload = {
            "status_filter": "active",
            "role_filter": "user",
            "search_query": "Field",
            "sort_code": "last_login_desc",
            "page_size": 30,
            "page_offset": 0,
        }
        if last_call[0] != "/rest/v1/rpc/admin_list_users" or last_call[1] != expected_list_payload:
            raise RuntimeError(f"Admin Users list provider payload drifted: {last_call}")

        for invalid_query in (
            "?status=active&status=suspended",
            "?status=invalid",
            "?role=owner",
            "?sort=unsafe",
            "?limit=101",
            "?offset=-1",
            "?unexpected=1",
        ):
            before = len(FakeSupabaseHandler.admin_calls)
            status, invalid, _ = request(admin, base_url, f"/api/admin/users{invalid_query}")
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(invalid) != "ADMIN_USER_FILTER_INVALID":
                raise RuntimeError(f"Invalid Admin Users query did not fail closed: {invalid_query}")
            if len(FakeSupabaseHandler.admin_calls) != before:
                raise RuntimeError("Invalid Admin Users query reached the provider")

        for drift in ("list_profile_user", "list_mfa_claim", "list_session_claim"):
            FakeSupabaseHandler.next_drift = drift
            status, drifted, _ = request(admin, base_url, "/api/admin/users")
            if status != HTTPStatus.BAD_GATEWAY or error_code(drifted) != "ADMIN_USERS_PROVIDER_FAILED":
                raise RuntimeError(f"Admin Users accepted list provider drift: {drift}")
            assert_no_sensitive(drifted, f"Admin Users list drift {drift}")

        status, result, _ = request(admin, base_url, f"/api/admin/users/{TARGET_ID}")
        if status != HTTPStatus.OK or set(result) != {"actor", "user"}:
            raise RuntimeError(f"Admin User Detail envelope drifted: {result}")
        assert_user_allowlist(result.get("user"), "Admin User Detail", detail=True)
        assert_no_sensitive(result, "Admin User Detail")
        if result["user"]["permissions"] != {
            "can_manage_status": True,
            "can_manage_roles": False,
            "can_revoke_sessions": True,
        }:
            raise RuntimeError("Admin User Detail permissions did not respect target privilege")

        for drift in (
            "detail_user",
            "detail_profile_user",
            "detail_image_owner",
            "detail_action_target",
            "detail_audit_target",
            "detail_audit_relationship",
        ):
            FakeSupabaseHandler.next_drift = drift
            status, drifted, _ = request(admin, base_url, f"/api/admin/users/{TARGET_ID}")
            if status != HTTPStatus.BAD_GATEWAY or error_code(drifted) != "ADMIN_USERS_PROVIDER_FAILED":
                raise RuntimeError(f"Admin Users accepted detail cross-record drift: {drift}")
            assert_no_sensitive(drifted, f"Admin Users detail drift {drift}")

        no_csrf = session(base_url, ADMIN_TOKEN, csrf=False)
        body = mutation_body("60000000-0000-4000-8000-000000000081", "suspend", expected_version=3)
        calls_before = len(FakeSupabaseHandler.admin_calls)
        status, result, _ = request(
            no_csrf, base_url, f"/api/admin/users/{TARGET_ID}/status", payload=body, origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "CSRF_REJECTED":
            raise RuntimeError("Admin Users mutation accepted a missing CSRF token")
        if len(FakeSupabaseHandler.admin_calls) != calls_before:
            raise RuntimeError("CSRF-rejected Admin Users mutation reached the provider")
        status, result, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/status",
            payload=body,
            origin="http://evil.example",
        )
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "CSRF_REJECTED":
            raise RuntimeError("Admin Users mutation accepted a cross-origin request")
        status, result, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/status",
            payload=body,
            origin=base_url,
            content_type="text/plain",
        )
        if status != HTTPStatus.UNSUPPORTED_MEDIA_TYPE or error_code(result) != "CONTENT_TYPE_INVALID":
            raise RuntimeError("Admin Users mutation accepted non-JSON content")

        invalid_bodies = (
            {**body, "unexpected": True},
            {**body, "target_role": None},
            {**body, "action": "grant_role"},
            {**body, "reason_code": "appeal_upheld"},
            {**body, "expected_version": 0},
            {**body, "idempotency_key": "not-a-uuid"},
        )
        for invalid_body in invalid_bodies:
            before = len(FakeSupabaseHandler.admin_calls)
            status, invalid, _ = request(
                admin,
                base_url,
                f"/api/admin/users/{TARGET_ID}/status",
                payload=invalid_body,
                origin=base_url,
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(invalid) != "ADMIN_USER_VALIDATION_FAILED":
                raise RuntimeError("Invalid Admin Users mutation did not fail closed")
            if len(FakeSupabaseHandler.admin_calls) != before:
                raise RuntimeError("Invalid Admin Users mutation reached the provider")

        before = len(FakeSupabaseHandler.admin_calls)
        status, denied, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{ADMIN_ID}/status",
            payload=body,
            origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(denied) != "ADMIN_USER_SELF_ACTION_FORBIDDEN":
            raise RuntimeError("Admin Users self-governance was not blocked by the server")
        if len(FakeSupabaseHandler.admin_calls) != before:
            raise RuntimeError("Self-governance reached the Admin Users provider")

        admin_role_body = mutation_body(
            "60000000-0000-4000-8000-000000000082",
            "grant_role",
            expected_version=3,
            target_role="reviewer",
        )
        before = len(FakeSupabaseHandler.admin_calls)
        status, denied, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/roles",
            payload=admin_role_body,
            origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(denied) != "ADMIN_USER_ROLE_FORBIDDEN":
            raise RuntimeError("Admin role mutation was not restricted to Super Admin")
        if len(FakeSupabaseHandler.admin_calls) != before:
            raise RuntimeError("Admin role mutation reached the provider")

        for index, drift in enumerate(
            ("mutation_target", "mutation_actor", "mutation_user", "mutation_reason", "mutation_provider_flag"),
            start=90,
        ):
            FakeSupabaseHandler.next_drift = drift
            drift_body = mutation_body(
                f"60000000-0000-4000-8000-{index:012d}",
                "revoke_sessions",
                expected_version=3,
            )
            status, drifted, _ = request(
                super_admin,
                base_url,
                f"/api/admin/users/{TARGET_ID}/revoke-sessions",
                payload=drift_body,
                origin=base_url,
            )
            if status != HTTPStatus.BAD_GATEWAY or error_code(drifted) != "ADMIN_USERS_PROVIDER_FAILED":
                raise RuntimeError(f"Admin Users accepted mutation provider drift: {drift}")
            assert_no_sensitive(drifted, f"Admin Users mutation drift {drift}")

        grant_key = "60000000-0000-4000-8000-000000000101"
        grant_body = mutation_body(grant_key, "grant_role", expected_version=3, target_role="reviewer")
        status, granted, _ = request(
            super_admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/roles",
            payload=grant_body,
            origin=base_url,
        )
        if status != HTTPStatus.OK or "reviewer" not in granted.get("user", {}).get("roles", []):
            raise RuntimeError(f"Super Admin role grant failed: {granted}")
        assert_user_allowlist(granted.get("user"), "Admin User role grant")
        assert_no_sensitive(granted, "Admin User role grant")
        status, replayed, _ = request(
            super_admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/roles",
            payload=grant_body,
            origin=base_url,
        )
        if status != HTTPStatus.OK or replayed.get("replayed") is not True or FakeSupabaseHandler.mutation_writes != 1:
            raise RuntimeError("Admin User same-key replay wrote a duplicate result")
        status, conflict, _ = request(
            super_admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/roles",
            payload={**grant_body, "reason_code": "other"},
            origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(conflict) != "ADMIN_USER_IDEMPOTENCY_CONFLICT":
            raise RuntimeError("Admin User same-key different payload did not conflict")
        stale_body = mutation_body(
            "60000000-0000-4000-8000-000000000102",
            "revoke_sessions",
            expected_version=3,
        )
        status, stale, _ = request(
            super_admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/revoke-sessions",
            payload=stale_body,
            origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(stale) != "ADMIN_USER_VERSION_CONFLICT":
            raise RuntimeError("Admin User stale mutation did not preserve CAS semantics")

        session_body = mutation_body(
            "60000000-0000-4000-8000-000000000103",
            "revoke_sessions",
            expected_version=4,
        )
        status, requested, _ = request(
            super_admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/revoke-sessions",
            payload=session_body,
            origin=base_url,
        )
        if (
            status != HTTPStatus.ACCEPTED
            or requested.get("action", {}).get("provider_action_required") is not True
            or requested.get("user", {}).get("version") != 5
        ):
            raise RuntimeError(f"Session revoke request was falsely represented: {requested}")
        assert_no_sensitive(requested, "Admin User session revoke request")

        suspend_body = mutation_body(
            "60000000-0000-4000-8000-000000000104",
            "suspend",
            expected_version=5,
        )
        status, suspended, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/status",
            payload=suspend_body,
            origin=base_url,
        )
        if status != HTTPStatus.OK or suspended.get("user", {}).get("account_status") != "suspended":
            raise RuntimeError("Admin User suspend did not return the stable suspended state")
        reactivate_body = mutation_body(
            "60000000-0000-4000-8000-000000000105",
            "reactivate",
            expected_version=6,
        )
        status, reactivated, _ = request(
            admin,
            base_url,
            f"/api/admin/users/{TARGET_ID}/status",
            payload=reactivate_body,
            origin=base_url,
        )
        if status != HTTPStatus.OK or reactivated.get("user", {}).get("account_status") != "active":
            raise RuntimeError("Admin User reactivate did not return the stable active state")

        for provider_status, expected_status, expected_code in (
            (HTTPStatus.UNAUTHORIZED, HTTPStatus.UNAUTHORIZED, "AUTH_REQUIRED"),
            (HTTPStatus.FORBIDDEN, HTTPStatus.FORBIDDEN, "ADMIN_USERS_ACCESS_REVOKED"),
            (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, "ADMIN_USERS_PROVIDER_UNAVAILABLE"),
        ):
            FakeSupabaseHandler.next_status = provider_status
            status, provider_error, _ = request(admin, base_url, "/api/admin/users")
            if status != expected_status or error_code(provider_error) != expected_code:
                raise RuntimeError(f"Provider {provider_status} did not map to stable Admin Users semantics")
            assert_no_sensitive(provider_error, "Admin Users provider error")
        FakeSupabaseHandler.next_error = "ADMIN_USER_SYSTEM_IDENTITY"
        status, controlled, _ = request(admin, base_url, f"/api/admin/users/{TARGET_ID}")
        if status != HTTPStatus.FORBIDDEN or error_code(controlled) != "ADMIN_USER_SYSTEM_IDENTITY":
            raise RuntimeError("Admin Users did not preserve a supported provider error")
        assert_no_sensitive(controlled, "Admin Users controlled provider error")

        captured_logs = "\n".join(CapturingAppHandler.captured_logs)
        forbidden_logs = (*PRIVATE_CANARIES, ADMIN_TOKEN, SUPER_ADMIN_TOKEN, RECOVERY_ADMIN_TOKEN)
        if any(value in captured_logs for value in forbidden_logs):
            raise RuntimeError("Admin Users logs exposed credentials or private governance data")

        print("admin_users_route_guards=yes")
        print("admin_users_role_mfa_recovery_inactive=yes")
        print("admin_users_list_detail_allowlist=yes")
        print("admin_users_filters_pagination=yes")
        print("admin_users_mfa_session_truthfulness=yes")
        print("admin_users_csrf_strict_body=yes")
        print("admin_users_super_admin_role_boundary=yes")
        print("admin_users_cas_idempotency=yes")
        print("admin_users_provider_drift_fail_closed=yes")
        print("admin_users_cross_record_binding=yes")
        print("admin_users_session_revoke_provider_action=yes")
        print("admin_users_provider_error_mapping=yes")
        print("admin_users_sensitive_fields_exposed=no")
    finally:
        application.shutdown()
        application.server_close()
        provider.shutdown()
        provider.server_close()
        temp_site.cleanup()


if __name__ == "__main__":
    main()
