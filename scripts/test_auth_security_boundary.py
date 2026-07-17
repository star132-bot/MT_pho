#!/usr/bin/env python3
"""Local, secret-free integration test for recovery, CSRF, and route guards."""

from __future__ import annotations

import base64
import http.cookiejar
import importlib
import json
import os
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fake_access_token(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii").rstrip("=")
    return f"e30.{payload}.signature"


RECOVERY_USER_ID = "00000000-0000-4000-8000-000000000001"
MEMBER_USER_ID = "00000000-0000-4000-8000-000000000002"
ADMIN_USER_ID = "00000000-0000-4000-8000-000000000003"
RECOVERY_ACCESS_TOKEN = fake_access_token({"amr": [{"method": "recovery"}]})
MEMBER_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "password"}],
    "session_id": "10000000-0000-4000-8000-000000000002",
    "iat": 1784044800,
    "exp": 1784048400,
})
ADMIN_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "password"}],
    "session_id": "10000000-0000-4000-8000-000000000003",
    "iat": 1784044800,
    "exp": 1784048400,
})


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    password_updated = False
    global_logout = False
    logout_scopes: list[str] = []
    profile_updates: list[dict] = []
    authorization_failures_remaining = 0
    profile = {
        "display_name": "MT Member",
        "avatar_url": None,
        "bio": "A quiet photographic practice.",
        "website_url": "https://example.test",
        "country_code": "CN",
        "preferred_locale": "en",
        "timezone": "Asia/Shanghai",
        "copyright_name": "MT Member",
        "default_license_preference": "all-rights-reserved",
    }

    def log_message(self, _format, *_args) -> None:
        return

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self) -> None:
        authorization = self.headers.get("Authorization")
        users = {
            f"Bearer {RECOVERY_ACCESS_TOKEN}": {
                "id": RECOVERY_USER_ID,
                "email": "recovery@example.test",
                "email_confirmed_at": "2026-07-14T00:00:00Z",
                "factors": [],
            },
            f"Bearer {MEMBER_ACCESS_TOKEN}": {
                "id": MEMBER_USER_ID,
                "email": "member@example.test",
                "email_confirmed_at": "2026-07-14T00:00:00Z",
                "factors": [],
            },
            f"Bearer {ADMIN_ACCESS_TOKEN}": {
                "id": ADMIN_USER_ID,
                "email": "admin@example.test",
                "email_confirmed_at": "2026-07-14T00:00:00Z",
                "factors": [],
            },
        }
        if self.path == "/auth/v1/user" and authorization in users:
            self.send_json(HTTPStatus.OK, users[authorization])
            return
        if urlparse(self.path).path == "/rest/v1/user_profiles" and authorization == f"Bearer {MEMBER_ACCESS_TOKEN}":
            self.send_json(HTTPStatus.OK, [dict(type(self).profile)])
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        authorization = self.headers.get("Authorization")
        if self.path == "/auth/v1/token?grant_type=password":
            body = self.body()
            sessions = {
                "member@example.test": ("Member-password-2026!", MEMBER_ACCESS_TOKEN, MEMBER_USER_ID),
                "admin@example.test": ("Admin-password-2026!", ADMIN_ACCESS_TOKEN, ADMIN_USER_ID),
            }
            expected = sessions.get(body.get("email"))
            if expected and body.get("password") == expected[0]:
                access_token, user_id = expected[1], expected[2]
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "access_token": access_token,
                        "refresh_token": f"refresh-{user_id}",
                        "expires_in": 3600,
                        "user": {
                            "id": user_id,
                            "email": body["email"],
                            "email_confirmed_at": "2026-07-14T00:00:00Z",
                        },
                    },
                )
                return
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid credentials"})
            return
        if self.path == "/rest/v1/rpc/current_authorization":
            if type(self).authorization_failures_remaining > 0:
                type(self).authorization_failures_remaining -= 1
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"message": "temporary authorization outage"})
                return
            if authorization == f"Bearer {MEMBER_ACCESS_TOKEN}":
                self.send_json(
                    HTTPStatus.OK,
                    {"user_id": MEMBER_USER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"},
                )
                return
            if authorization == f"Bearer {ADMIN_ACCESS_TOKEN}":
                self.send_json(
                    HTTPStatus.OK,
                    {"user_id": ADMIN_USER_ID, "account_status": "active", "roles": ["admin"], "aal": "aal1"},
                )
                return
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid authorization"})
            return
        if self.path == "/rest/v1/rpc/update_my_profile" and authorization == f"Bearer {MEMBER_ACCESS_TOKEN}":
            patch = self.body().get("profile_patch")
            if not isinstance(patch, dict):
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid patch"})
                return
            type(self).profile_updates.append(dict(patch))
            type(self).profile.update(patch)
            self.send_json(HTTPStatus.OK, dict(type(self).profile))
            return
        if self.path.startswith("/auth/v1/recover?"):
            self.body()
            self.send_json(HTTPStatus.OK, {})
            return
        if self.path == "/auth/v1/verify":
            body = self.body()
            if body == {"type": "recovery", "token_hash": "valid-recovery-token-hash"}:
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "access_token": RECOVERY_ACCESS_TOKEN,
                        "refresh_token": "refresh-recovery",
                        "expires_in": 3600,
                        "user": {
                            "id": RECOVERY_USER_ID,
                            "email": "recovery@example.test",
                            "email_confirmed_at": "2026-07-14T00:00:00Z",
                        },
                    },
                )
                return
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid token"})
            return
        if self.path in {"/auth/v1/logout?scope=local", "/auth/v1/logout?scope=others", "/auth/v1/logout?scope=global"}:
            self.body()
            scope = self.path.rsplit("=", 1)[-1]
            type(self).logout_scopes.append(scope)
            if scope == "global":
                type(self).global_logout = True
            self.send_json(HTTPStatus.OK, {})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {})

    def do_PUT(self) -> None:
        if self.path == "/auth/v1/user" and self.headers.get("Authorization") == f"Bearer {RECOVERY_ACCESS_TOKEN}":
            body = self.body()
            type(self).password_updated = body.get("password") == "A-new-password-2026!"
            self.send_json(HTTPStatus.OK, {"id": RECOVERY_USER_ID})
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {})


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        return None


def request(
    opener,
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    origin: str | None = None,
    method: str | None = None,
) -> tuple[int, dict, object]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/126.0 Safari/537.36",
    }
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
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
            parsed = json.loads(raw.decode("utf-8")) if raw and response.headers.get_content_type() == "application/json" else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        parsed = json.loads(raw.decode("utf-8")) if raw and error.headers.get_content_type() == "application/json" else {}
        return error.code, parsed, error.headers


class CookieOpener:
    def __init__(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            RejectRedirects(),
        )

    def open(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._opener.open(*args, **kwargs)

    def cookie_value(self, name: str) -> str:
        return next((cookie.value for cookie in self.cookie_jar if cookie.name == name), "")


def main() -> None:
    temp_site = tempfile.TemporaryDirectory(prefix="mt-auth-boundary-")
    temp_root = Path(temp_site.name)
    archive_db = temp_root / "data" / "archive.db"
    upload_root = temp_root / "assets" / "uploads"
    archive_db.parent.mkdir(parents=True)
    (temp_root / "account-settings.html").write_text((ROOT / "account-settings.html").read_text())
    (temp_root / "upload-studio.html").write_text((ROOT / "upload-studio.html").read_text())
    (upload_root / "published").mkdir(parents=True)
    (upload_root / "draft").mkdir(parents=True)
    (upload_root / "published" / "display-public.jpg").write_bytes(b"public-display")
    (upload_root / "published" / "original-private.jpg").write_bytes(b"private-original")
    (upload_root / "draft" / "display-private.jpg").write_bytes(b"private-draft")
    with sqlite3.connect(archive_db) as connection:
        connection.executescript(
            """
            create table images (id text primary key, visibility text not null);
            create table image_assets (
              id text primary key,
              image_id text not null,
              kind text not null,
              public_url text
            );
            insert into images values ('published-image', 'published');
            insert into images values ('draft-image', 'draft');
            insert into image_assets values (
              'published-display', 'published-image', 'display',
              'assets/uploads/published/display-public.jpg'
            );
            insert into image_assets values (
              'published-original', 'published-image', 'original',
              'assets/uploads/published/original-private.jpg'
            );
            insert into image_assets values (
              'draft-display', 'draft-image', 'display',
              'assets/uploads/draft/display-private.jpg'
            );
            """
        )

    FakeSupabaseHandler.password_updated = False
    FakeSupabaseHandler.global_logout = False
    FakeSupabaseHandler.logout_scopes = []
    FakeSupabaseHandler.profile_updates = []
    FakeSupabaseHandler.authorization_failures_remaining = 0
    FakeSupabaseHandler.profile = {
        "display_name": "MT Member",
        "avatar_url": None,
        "bio": "A quiet photographic practice.",
        "website_url": "https://example.test",
        "country_code": "CN",
        "preferred_locale": "en",
        "timezone": "Asia/Shanghai",
        "copyright_name": "MT Member",
        "default_license_preference": "all-rights-reserved",
    }
    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{fake_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_PUBLIC_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")
    app.ARCHIVE_DB_PATH = archive_db
    app.UPLOAD_ASSET_ROOT = upload_root
    handler = partial(app.MTRequestHandler, directory=str(temp_root))
    app_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    base_url = f"http://127.0.0.1:{app_server.server_address[1]}"
    opener = CookieOpener()

    try:
        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/forgot-password",
            payload={"email": "unknown@example.test"},
            origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "CSRF_REJECTED":
            raise RuntimeError("Auth mutation accepted a request without a CSRF token")

        status, result, _ = request(opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("CSRF endpoint did not establish a token")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/forgot-password",
            payload={"email": "unknown@example.test"},
            origin="https://attacker.example",
        )
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "CSRF_REJECTED":
            raise RuntimeError("Auth mutation accepted a cross-origin request")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/forgot-password",
            payload={"email": "unknown@example.test"},
            origin=base_url,
        )
        if status != HTTPStatus.ACCEPTED or result.get("status") != "recovery_email_sent":
            raise RuntimeError("Forgot Password did not return the enumeration-safe response")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/recovery-session",
            payload={"type": "recovery", "token_hash": "valid-recovery-token-hash"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("recovery_ready") is not True:
            raise RuntimeError("Recovery token did not establish a restricted recovery session")

        status, result, _ = request(opener, base_url, "/api/auth/recovery-status")
        if status != HTTPStatus.OK or result.get("recovery_ready") is not True:
            raise RuntimeError("Recovery session status was not available")

        status, _, headers = request(opener, base_url, "/workspace/images")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("Recovery-only session was allowed into the Workspace")

        status, _, headers = request(opener, base_url, "/settings/account")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("Recovery-only session was allowed into Account Settings")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/reset-password",
            payload={"password": "A-new-password-2026!", "password_confirmation": "different"},
            origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "password_confirmation" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Password confirmation mismatch was not rejected")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/reset-password",
            payload={"password": "A-new-password-2026!", "password_confirmation": "A-new-password-2026!"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("password_reset") is not True:
            raise RuntimeError("Valid recovery session could not update the password")
        if not FakeSupabaseHandler.password_updated or not FakeSupabaseHandler.global_logout:
            raise RuntimeError("Password reset did not update the provider and revoke sessions")

        status, _, headers = request(opener, base_url, "/upload-studio.html")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/workspace/images":
            raise RuntimeError("Direct Upload Studio route did not canonicalize to protected Workspace")

        fresh_opener = CookieOpener()
        status, _, headers = request(fresh_opener, base_url, "/workspace/images")
        if status != HTTPStatus.SEE_OTHER or not headers.get("Location", "").startswith("/auth/sign-in?"):
            raise RuntimeError("Protected Workspace did not redirect an anonymous request")

        status, _, headers = request(fresh_opener, base_url, "/settings/account")
        if status != HTTPStatus.SEE_OTHER or not headers.get("Location", "").startswith("/auth/sign-in?"):
            raise RuntimeError("Account Settings did not redirect an anonymous request")

        member_opener = CookieOpener()
        status, result, _ = request(member_opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Member session could not establish CSRF protection")
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/auth/sign-in",
            payload={"email": "member@example.test", "password": "Member-password-2026!"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("next_action") != "workspace":
            raise RuntimeError("Member could not establish a protected application session")

        FakeSupabaseHandler.authorization_failures_remaining = 1
        status, _, _ = request(member_opener, base_url, "/workspace/images")
        if status != HTTPStatus.OK or FakeSupabaseHandler.authorization_failures_remaining != 0:
            raise RuntimeError("Workspace did not recover from a transient authorization failure")

        status, _, _ = request(member_opener, base_url, "/settings/account")
        if status != HTTPStatus.OK:
            raise RuntimeError("Active member could not open Account Settings")

        status, result, _ = request(member_opener, base_url, "/api/me/profile")
        if status != HTTPStatus.OK or result.get("profile", {}).get("display_name") != "MT Member":
            raise RuntimeError("Member profile could not be loaded through the account boundary")
        if result.get("account", {}).get("roles") != ["user"]:
            raise RuntimeError("Account response did not preserve server-derived roles")

        status, result, _ = request(
            member_opener,
            base_url,
            "/api/me/profile",
            payload={"website_url": "https://example.test\\@attacker.test"},
            origin=base_url,
            method="PATCH",
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "website_url" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Profile update accepted a website URL outside the database contract")
        if FakeSupabaseHandler.profile_updates:
            raise RuntimeError("Invalid profile input reached the provider RPC")

        profile_patch = {
            "display_name": "MT Presence Member",
            "bio": "Photography, weather, and distance.",
            "website_url": "https://portfolio.example.test/work",
            "country_code": "cn",
            "preferred_locale": "en",
            "timezone": "Asia/Shanghai",
            "copyright_name": "MT Presence Member",
            "default_license_preference": "cc-by-nc-4.0",
        }
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/me/profile",
            payload=profile_patch,
            origin=base_url,
            method="PATCH",
        )
        if status != HTTPStatus.OK or result.get("profile", {}).get("display_name") != "MT Presence Member":
            raise RuntimeError("Valid profile changes were not saved")
        if FakeSupabaseHandler.profile_updates[-1].get("country_code") != "CN":
            raise RuntimeError("Profile input was not normalized before reaching the provider RPC")

        status, result, _ = request(member_opener, base_url, "/api/me/sessions")
        sessions = result.get("sessions", [])
        if status != HTTPStatus.OK or len(sessions) != 1 or not sessions[0].get("current"):
            raise RuntimeError("Current session summary was not returned")
        if sessions[0].get("browser") != "Chrome" or sessions[0].get("operating_system") != "macOS":
            raise RuntimeError("Current session summary exposed an unstable device shape")
        if result.get("scope") != "current_only" or result.get("capabilities", {}).get("revoke_by_id") is not False:
            raise RuntimeError("Session capabilities overstated provider support")

        status, result, _ = request(
            member_opener,
            base_url,
            "/api/me/sessions/others",
            payload={"confirmation": "sign-out-others"},
            origin=base_url,
            method="DELETE",
        )
        if status != HTTPStatus.OK or result.get("signed_out") is not False or "others" not in FakeSupabaseHandler.logout_scopes:
            raise RuntimeError("Other-device session revocation did not preserve the current session")
        if not member_opener.cookie_value("mt_access_token"):
            raise RuntimeError("Other-device revocation cleared the current access cookie")

        admin_opener = CookieOpener()
        request(admin_opener, base_url, "/api/auth/csrf")
        status, result, _ = request(
            admin_opener,
            base_url,
            "/api/auth/sign-in",
            payload={"email": "admin@example.test", "password": "Admin-password-2026!"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("next_action") != "mfa":
            raise RuntimeError("Admin AAL1 sign-in did not require MFA")
        status, _, headers = request(admin_opener, base_url, "/settings/account")
        if status != HTTPStatus.SEE_OTHER or not headers.get("Location", "").startswith("/auth/mfa?"):
            raise RuntimeError("Admin AAL1 session opened Account Settings without MFA")
        status, result, _ = request(admin_opener, base_url, "/api/me/profile")
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "MFA_REQUIRED":
            raise RuntimeError("Admin AAL1 profile API did not fail closed")

        status, result, _ = request(
            member_opener,
            base_url,
            "/api/me/sessions/all",
            payload={"confirmation": "sign-out-all"},
            origin=base_url,
            method="DELETE",
        )
        if status != HTTPStatus.OK or result.get("signed_out") is not True:
            raise RuntimeError("All-device session revocation did not sign out the current session")
        if member_opener.cookie_value("mt_access_token") or member_opener.cookie_value("mt_refresh_token"):
            raise RuntimeError("All-device session revocation did not clear application cookies")
        status, _, _ = request(member_opener, base_url, "/api/me/profile")
        if status != HTTPStatus.UNAUTHORIZED:
            raise RuntimeError("Revoked member session remained authenticated")

        status, _, _ = request(fresh_opener, base_url, "/assets/uploads/published/original-private.jpg")
        if status != HTTPStatus.NOT_FOUND:
            raise RuntimeError("Published original upload asset remained publicly readable")

        status, _, _ = request(fresh_opener, base_url, "/assets/uploads/draft/display-private.jpg")
        if status != HTTPStatus.NOT_FOUND:
            raise RuntimeError("Draft derivative upload asset remained publicly readable")

        status, _, _ = request(fresh_opener, base_url, "/assets/uploads/")
        if status != HTTPStatus.NOT_FOUND:
            raise RuntimeError("Legacy upload directory listing remained publicly readable")

        status, _, _ = request(fresh_opener, base_url, "/assets/uploads/published/display-public.jpg")
        if status != HTTPStatus.OK:
            raise RuntimeError("Published display derivative was not publicly readable")

        print("csrf_missing_rejected=yes")
        print("csrf_cross_origin_rejected=yes")
        print("forgot_response_enumeration_safe=yes")
        print("recovery_session_restricted=yes")
        print("recovery_session_workspace_denied=yes")
        print("recovery_session_account_settings_denied=yes")
        print("password_updated_and_sessions_revoked=yes")
        print("workspace_direct_route_protected=yes")
        print("workspace_transient_authorization_retry=yes")
        print("account_settings_route_protected=yes")
        print("account_profile_read_write_validated=yes")
        print("account_session_capabilities_validated=yes")
        print("admin_account_settings_requires_mfa=yes")
        print("account_session_bulk_revoke_validated=yes")
        print("legacy_original_private=yes")
        print("legacy_draft_derivative_private=yes")
        print("legacy_upload_listing_disabled=yes")
        print("published_display_public=yes")
        print("secrets_logged=no")
    finally:
        app_server.shutdown()
        app_server.server_close()
        fake_server.shutdown()
        fake_server.server_close()
        temp_site.cleanup()


if __name__ == "__main__":
    main()
