#!/usr/bin/env python3
"""Local, secret-free integration test for recovery, CSRF, and route guards."""

from __future__ import annotations

import base64
import hashlib
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
from urllib.parse import parse_qs, urlencode, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fake_access_token(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii").rstrip("=")
    return f"e30.{payload}.signature"


RECOVERY_USER_ID = "00000000-0000-4000-8000-000000000001"
MEMBER_USER_ID = "00000000-0000-4000-8000-000000000002"
ADMIN_USER_ID = "00000000-0000-4000-8000-000000000003"
SIGNUP_USER_ID = "00000000-0000-4000-8000-000000000004"
GOOGLE_USER_ID = "00000000-0000-4000-8000-000000000005"
MEMBER_MFA_FACTOR_ID = "20000000-0000-4000-8000-000000000001"
MEMBER_MFA_CHALLENGE_ID = "30000000-0000-4000-8000-000000000001"
RECOVERY_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "otp"}],
    "session_id": "10000000-0000-4000-8000-000000000001",
    "iat": 1784044800,
    "exp": 1784048400,
})
MEMBER_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "password"}],
    "session_id": "10000000-0000-4000-8000-000000000002",
    "iat": 1784044800,
    "exp": 1784048400,
})
MEMBER_AAL2_ACCESS_TOKEN = fake_access_token({
    "aal": "aal2",
    "amr": [{"method": "password"}, {"method": "totp"}],
    "session_id": "10000000-0000-4000-8000-000000000006",
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
SIGNUP_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "password"}],
    "session_id": "10000000-0000-4000-8000-000000000004",
    "iat": 1784044800,
    "exp": 1784048400,
})
GOOGLE_ACCESS_TOKEN = fake_access_token({
    "aal": "aal1",
    "amr": [{"method": "oauth", "provider": "google"}],
    "session_id": "10000000-0000-4000-8000-000000000005",
    "iat": 1784044800,
    "exp": 1784048400,
})


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    password_updated = False
    global_logout = False
    logout_scopes: list[str] = []
    profile_updates: list[dict] = []
    registrations: list[dict] = []
    verification_resends: list[dict] = []
    oauth_exchanges: list[dict] = []
    authorization_failures_remaining = 0
    member_mfa_state = "off"
    google_mfa_enabled = False
    email_response_override: tuple[int, dict] | None = None
    unverified_signin_error_field = "error_code"
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
    google_profile = {**profile, "display_name": "Google Member"}

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

    @classmethod
    def member_factors(cls) -> list[dict]:
        if cls.member_mfa_state == "off":
            return []
        return [{
            "id": MEMBER_MFA_FACTOR_ID,
            "factor_type": "totp",
            "status": "verified" if cls.member_mfa_state == "verified" else "unverified",
            "friendly_name": "MT Presence authenticator",
        }]

    @classmethod
    def google_factors(cls) -> list[dict]:
        if not cls.google_mfa_enabled:
            return []
        return [{
            "id": "20000000-0000-4000-8000-000000000005",
            "factor_type": "totp",
            "status": "verified",
            "friendly_name": "Google member authenticator",
        }]

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
                "factors": type(self).member_factors(),
            },
            f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}": {
                "id": MEMBER_USER_ID,
                "email": "member@example.test",
                "email_confirmed_at": "2026-07-14T00:00:00Z",
                "factors": type(self).member_factors(),
            },
            f"Bearer {ADMIN_ACCESS_TOKEN}": {
                "id": ADMIN_USER_ID,
                "email": "admin@example.test",
                "email_confirmed_at": "2026-07-14T00:00:00Z",
                "factors": [],
            },
            f"Bearer {SIGNUP_ACCESS_TOKEN}": {
                "id": SIGNUP_USER_ID,
                "email": "new.artist@example.test",
                "email_confirmed_at": "2026-08-03T00:00:00Z",
                "factors": [],
            },
            f"Bearer {GOOGLE_ACCESS_TOKEN}": {
                "id": GOOGLE_USER_ID,
                "email": "google.member@example.test",
                "email_confirmed_at": "2026-08-05T00:00:00Z",
                "app_metadata": {"provider": "google", "providers": ["google"]},
                "identities": [{
                    "id": "40000000-0000-4000-8000-000000000005",
                    "provider": "google",
                    "identity_data": {"email": "google.member@example.test"},
                }],
                "factors": type(self).google_factors(),
            },
        }
        if self.path == "/auth/v1/user" and authorization in users:
            self.send_json(HTTPStatus.OK, users[authorization])
            return
        if (
            urlparse(self.path).path == "/rest/v1/user_profiles"
            and authorization in {f"Bearer {MEMBER_ACCESS_TOKEN}", f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}"}
        ):
            self.send_json(HTTPStatus.OK, [dict(type(self).profile)])
            return
        if (
            urlparse(self.path).path == "/rest/v1/user_profiles"
            and authorization == f"Bearer {GOOGLE_ACCESS_TOKEN}"
            and parse_qs(urlparse(self.path).query).get("user_id") == [f"eq.{GOOGLE_USER_ID}"]
        ):
            self.send_json(HTTPStatus.OK, [dict(type(self).google_profile)])
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        authorization = self.headers.get("Authorization")
        parsed = urlparse(self.path)
        if parsed.path in {"/auth/v1/signup", "/auth/v1/resend", "/auth/v1/recover"}:
            override = type(self).email_response_override
            if override is not None:
                self.body()
                self.send_json(*override)
                return
        if parsed.path == "/auth/v1/signup":
            body = self.body()
            type(self).registrations.append(body)
            self.send_json(
                HTTPStatus.OK,
                {
                    "user": {
                        "id": SIGNUP_USER_ID,
                        "email": body.get("email"),
                        "email_confirmed_at": None,
                    },
                },
            )
            return
        if parsed.path == "/auth/v1/resend":
            body = self.body()
            type(self).verification_resends.append(body)
            # The application must not reveal whether this address exists.
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "identity not found"})
            return
        if self.path == "/auth/v1/token?grant_type=password":
            body = self.body()
            if body.get("email") == "unverified@example.test":
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {type(self).unverified_signin_error_field: "email_not_confirmed", "msg": "Email not confirmed"},
                )
                return
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
        if self.path == "/auth/v1/token?grant_type=pkce":
            body = self.body()
            type(self).oauth_exchanges.append(body)
            if body.get("auth_code") != "valid-google-code" or not body.get("code_verifier"):
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid authorization code"})
                return
            self.send_json(
                HTTPStatus.OK,
                {
                    "access_token": GOOGLE_ACCESS_TOKEN,
                    "refresh_token": "refresh-google-member",
                    "expires_in": 3600,
                    "provider_token": "must-not-reach-the-browser",
                    "user": {
                        "id": GOOGLE_USER_ID,
                        "email": "google.member@example.test",
                        "email_confirmed_at": "2026-08-05T00:00:00Z",
                        "app_metadata": {"provider": "google", "providers": ["google"]},
                    },
                },
            )
            return
        if parsed.path == "/auth/v1/factors" and authorization in {
            f"Bearer {MEMBER_ACCESS_TOKEN}",
            f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}",
        }:
            body = self.body()
            if body.get("factor_type") != "totp":
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "unsupported factor"})
                return
            type(self).member_mfa_state = "unverified"
            self.send_json(
                HTTPStatus.CREATED,
                {
                    "id": MEMBER_MFA_FACTOR_ID,
                    "factor_type": "totp",
                    "friendly_name": body.get("friendly_name"),
                    "totp": {
                        "qr_code": "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E",
                        "secret": "JBSWY3DPEHPK3PXP",
                    },
                },
            )
            return
        if parsed.path == f"/auth/v1/factors/{MEMBER_MFA_FACTOR_ID}/challenge" and authorization in {
            f"Bearer {MEMBER_ACCESS_TOKEN}",
            f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}",
        }:
            self.body()
            if type(self).member_mfa_state == "off":
                self.send_json(HTTPStatus.NOT_FOUND, {"message": "factor not found"})
                return
            self.send_json(HTTPStatus.OK, {"id": MEMBER_MFA_CHALLENGE_ID})
            return
        if parsed.path == f"/auth/v1/factors/{MEMBER_MFA_FACTOR_ID}/verify" and authorization in {
            f"Bearer {MEMBER_ACCESS_TOKEN}",
            f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}",
        }:
            body = self.body()
            if body != {"challenge_id": MEMBER_MFA_CHALLENGE_ID, "code": "123456"}:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid totp"})
                return
            type(self).member_mfa_state = "verified"
            self.send_json(
                HTTPStatus.OK,
                {
                    "access_token": MEMBER_AAL2_ACCESS_TOKEN,
                    "refresh_token": "refresh-member-aal2",
                    "expires_in": 3600,
                    "user": {
                        "id": MEMBER_USER_ID,
                        "email": "member@example.test",
                        "email_confirmed_at": "2026-07-14T00:00:00Z",
                        "factors": type(self).member_factors(),
                    },
                },
            )
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
            if authorization == f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}":
                self.send_json(
                    HTTPStatus.OK,
                    {"user_id": MEMBER_USER_ID, "account_status": "active", "roles": ["user"], "aal": "aal2"},
                )
                return
            if authorization == f"Bearer {ADMIN_ACCESS_TOKEN}":
                self.send_json(
                    HTTPStatus.OK,
                    {"user_id": ADMIN_USER_ID, "account_status": "active", "roles": ["admin"], "aal": "aal1"},
                )
                return
            if authorization == f"Bearer {GOOGLE_ACCESS_TOKEN}":
                self.send_json(
                    HTTPStatus.OK,
                    {"user_id": GOOGLE_USER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"},
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
            if body == {"type": "recovery", "email": "recovery@example.test", "token": "48273106"}:
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "access_token": RECOVERY_ACCESS_TOKEN,
                        "refresh_token": "refresh-recovery-code",
                        "expires_in": 3600,
                        "user": {
                            "id": RECOVERY_USER_ID,
                            "email": "recovery@example.test",
                            "email_confirmed_at": "2026-07-14T00:00:00Z",
                        },
                    },
                )
                return
            if body == {"type": "email", "email": "new.artist@example.test", "token": "48273106"}:
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "access_token": SIGNUP_ACCESS_TOKEN,
                        "refresh_token": "refresh-signup",
                        "expires_in": 3600,
                        "user": {
                            "id": SIGNUP_USER_ID,
                            "email": "new.artist@example.test",
                            "email_confirmed_at": "2026-08-04T00:00:00Z",
                        },
                    },
                )
                return
            if body == {"type": "signup", "token_hash": "valid-signup-token-hash"}:
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "access_token": SIGNUP_ACCESS_TOKEN,
                        "refresh_token": "refresh-signup",
                        "expires_in": 3600,
                        "user": {
                            "id": SIGNUP_USER_ID,
                            "email": "new.artist@example.test",
                            "email_confirmed_at": "2026-08-03T00:00:00Z",
                        },
                    },
                )
                return
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

    def do_DELETE(self) -> None:
        if (
            self.path == f"/auth/v1/factors/{MEMBER_MFA_FACTOR_ID}"
            and self.headers.get("Authorization") == f"Bearer {MEMBER_AAL2_ACCESS_TOKEN}"
        ):
            type(self).member_mfa_state = "off"
            self.send_json(HTTPStatus.OK, {})
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
    FakeSupabaseHandler.registrations = []
    FakeSupabaseHandler.verification_resends = []
    FakeSupabaseHandler.oauth_exchanges = []
    FakeSupabaseHandler.authorization_failures_remaining = 0
    FakeSupabaseHandler.member_mfa_state = "off"
    FakeSupabaseHandler.google_mfa_enabled = False
    FakeSupabaseHandler.email_response_override = None
    FakeSupabaseHandler.unverified_signin_error_field = "error_code"
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
    FakeSupabaseHandler.google_profile = {
        **FakeSupabaseHandler.profile,
        "display_name": "Google Member",
    }
    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{fake_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_PUBLIC_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["MT_COOKIE_SECURE"] = "0"
    os.environ["MT_RUNTIME_ENVIRONMENT"] = "test"
    os.environ["MT_ENABLED_OAUTH_PROVIDERS"] = "google"
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
        unsafe_destinations = [
            "/works.html\r\nX-Audit-Test: synthetic",
            "/works.html\x00",
            "/works.html%0d%0aX-Audit-Test:%20synthetic",
            "/works.html%250d%250aX-Audit-Test:%20synthetic",
            "/public/../auth/oauth/google",
            "/public/%2e%2e/auth/oauth/google",
            "/public/%252e%252e/auth/oauth/google",
            "/public/../api/me",
            "/%61uth/oauth/google",
            "/%2561uth/oauth/google",
            "/%2fexample.test/steal",
            "/%252fexample.test/steal",
            "/%5cexample.test/steal",
            "/%255cexample.test/steal",
            "//example.test/steal",
            "/api/me",
            "/auth/verify-email",
        ]
        for case_number, destination in enumerate(unsafe_destinations, start=1):
            if app.safe_auth_destination(destination) != "/works.html":
                raise RuntimeError(f"Unsafe authentication destination case {case_number} was accepted")
        safe_destination = "/workspace/images?filter=drafts#list"
        if app.safe_auth_destination(safe_destination) != safe_destination:
            raise RuntimeError("Safe internal authentication destination lost its query or fragment")

        oauth_opener = CookieOpener()
        status, _, headers = request(oauth_opener, base_url, "/auth/oauth/google?next=/workspace/images")
        if status != HTTPStatus.SEE_OTHER:
            raise RuntimeError("Google OAuth did not start with a redirect")
        authorize_url = urlparse(headers.get("Location", ""))
        authorize_query = parse_qs(authorize_url.query)
        if (
            authorize_url.path != "/auth/v1/authorize"
            or authorize_query.get("provider") != ["google"]
            or authorize_query.get("redirect_to") != ["http://127.0.0.1:9/auth/oauth/callback"]
            or authorize_query.get("code_challenge_method") != ["s256"]
            or not authorize_query.get("code_challenge", [""])[0]
        ):
            raise RuntimeError("Google OAuth authorization request was incomplete")
        if not oauth_opener.cookie_value("mt_oauth_state"):
            raise RuntimeError("Google OAuth did not establish an HttpOnly state cookie")

        status, _, headers = request(oauth_opener, base_url, "/auth/oauth/callback?code=valid-google-code")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/workspace/images":
            raise RuntimeError("Google OAuth callback did not return to the requested Workspace route")
        if not FakeSupabaseHandler.oauth_exchanges:
            raise RuntimeError("Google OAuth callback did not exchange the PKCE code")
        verifier = FakeSupabaseHandler.oauth_exchanges[-1].get("code_verifier", "")
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        if expected_challenge != authorize_query["code_challenge"][0]:
            raise RuntimeError("Google OAuth PKCE verifier did not match the original challenge")
        if oauth_opener.cookie_value("mt_access_token") != GOOGLE_ACCESS_TOKEN or not oauth_opener.cookie_value("mt_refresh_token"):
            raise RuntimeError("Google OAuth did not establish application session cookies")
        if any(cookie.name == "provider_token" or cookie.value == "must-not-reach-the-browser" for cookie in oauth_opener.cookie_jar):
            raise RuntimeError("Google provider credentials leaked into browser cookies")

        status, _, headers = request(oauth_opener, base_url, "/auth/oauth/callback?code=valid-google-code")
        replay_destination = urlparse(headers.get("Location", ""))
        if (
            status != HTTPStatus.SEE_OTHER
            or replay_destination.path != "/auth/sign-in"
            or parse_qs(replay_destination.query).get("oauth_error") != ["invalid"]
        ):
            raise RuntimeError("Google OAuth callback could be replayed")

        for login_attempt in range(2):
            status, result, _ = request(oauth_opener, base_url, "/api/me")
            if (
                status != HTTPStatus.OK
                or result.get("user", {}).get("id") != GOOGLE_USER_ID
                or result.get("profile", {}).get("display_name") != "Google Member"
                or result.get("account", {}).get("account_status") != "active"
                or {identity["provider"] for identity in result.get("account", {}).get("identities", [])} != {"google"}
            ):
                raise RuntimeError("Google OAuth session did not load its own active account and profile")
            for protected_path in ("/workspace/images", "/settings/account"):
                status, _, _ = request(oauth_opener, base_url, protected_path)
                if status != HTTPStatus.OK:
                    raise RuntimeError("Google OAuth session could not open its protected account pages")

            status, result, _ = request(oauth_opener, base_url, "/api/auth/csrf")
            if status != HTTPStatus.OK or not result.get("csrf_token"):
                raise RuntimeError("Google OAuth session could not initialize protected sign-out")
            previous_logouts = len(FakeSupabaseHandler.logout_scopes)
            status, result, _ = request(
                oauth_opener,
                base_url,
                "/api/auth/sign-out",
                payload={},
                origin=base_url,
            )
            if (
                status != HTTPStatus.OK
                or result.get("signed_out") is not True
                or oauth_opener.cookie_value("mt_access_token")
                or oauth_opener.cookie_value("mt_refresh_token")
                or FakeSupabaseHandler.logout_scopes[previous_logouts:] != ["local"]
            ):
                raise RuntimeError("Google OAuth sign-out did not revoke the provider session and clear cookies")
            status, _, _ = request(oauth_opener, base_url, "/api/me")
            if status != HTTPStatus.UNAUTHORIZED:
                raise RuntimeError("Signed-out Google OAuth account remained authenticated")
            for protected_path in ("/workspace/images", "/settings/account"):
                status, _, headers = request(oauth_opener, base_url, protected_path)
                destination = urlparse(headers.get("Location", ""))
                if (
                    status != HTTPStatus.SEE_OTHER
                    or destination.path != "/auth/sign-in"
                    or parse_qs(destination.query).get("next") != [protected_path]
                ):
                    raise RuntimeError("Signed-out Google account could still open a protected page")
            if login_attempt == 0:
                status, _, _ = request(oauth_opener, base_url, "/auth/oauth/google?next=/settings/account")
                if status != HTTPStatus.SEE_OTHER:
                    raise RuntimeError("Google OAuth could not start again after sign-out")
                status, _, headers = request(oauth_opener, base_url, "/auth/oauth/callback?code=valid-google-code")
                if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/settings/account":
                    raise RuntimeError("Repeated Google OAuth login lost its requested destination")

        cancelled_oauth = CookieOpener()
        request(cancelled_oauth, base_url, "/auth/oauth/google?next=/workspace/images")
        status, _, headers = request(cancelled_oauth, base_url, "/auth/oauth/callback?error=access_denied")
        cancelled_destination = urlparse(headers.get("Location", ""))
        cancelled_query = parse_qs(cancelled_destination.query)
        if (
            status != HTTPStatus.SEE_OTHER
            or cancelled_destination.path != "/auth/sign-in"
            or cancelled_query.get("oauth_error") != ["cancelled"]
            or cancelled_query.get("oauth_provider") != ["google"]
            or cancelled_query.get("next") != ["/workspace/images"]
            or cancelled_oauth.cookie_value("mt_oauth_state")
            or cancelled_oauth.cookie_value("mt_access_token")
        ):
            raise RuntimeError("Cancelled Google OAuth did not preserve a safe retry destination and clear its flow")

        unsafe_cancelled_oauth = CookieOpener()
        request(
            unsafe_cancelled_oauth,
            base_url,
            f"/auth/oauth/google?{urlencode({'next': '/public/%2e%2e/auth/oauth/google'})}",
        )
        status, _, headers = request(unsafe_cancelled_oauth, base_url, "/auth/oauth/callback?error=access_denied")
        if status != HTTPStatus.SEE_OTHER or parse_qs(urlparse(headers.get("Location", "")).query).get("next") != ["/works.html"]:
            raise RuntimeError("Cancelled Google OAuth retained an unsafe requested destination")

        external_next_opener = CookieOpener()
        status, _, _ = request(external_next_opener, base_url, "/auth/oauth/google?next=https://attacker.example/steal")
        if status != HTTPStatus.SEE_OTHER:
            raise RuntimeError("Google OAuth rejected a safe fallback start")
        status, _, headers = request(external_next_opener, base_url, "/auth/oauth/callback?code=valid-google-code")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/works.html":
            raise RuntimeError("Google OAuth accepted an external post-authentication destination")

        FakeSupabaseHandler.google_mfa_enabled = True
        oauth_mfa_opener = CookieOpener()
        status, _, _ = request(oauth_mfa_opener, base_url, "/auth/oauth/google?next=/workspace/images")
        if status != HTTPStatus.SEE_OTHER:
            raise RuntimeError("Google OAuth MFA test could not start")
        status, _, headers = request(oauth_mfa_opener, base_url, "/auth/oauth/callback?code=valid-google-code")
        mfa_destination = urlparse(headers.get("Location", ""))
        if (
            status != HTTPStatus.SEE_OTHER
            or mfa_destination.path != "/auth/mfa"
            or parse_qs(mfa_destination.query).get("next") != ["/workspace/images"]
        ):
            raise RuntimeError("Google OAuth bypassed an enabled authenticator factor")
        status, result, _ = request(oauth_mfa_opener, base_url, "/api/me")
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "MFA_REQUIRED":
            raise RuntimeError("Google OAuth AAL1 session did not fail closed behind MFA")
        FakeSupabaseHandler.google_mfa_enabled = False

        registration_opener = CookieOpener()
        status, result, _ = request(registration_opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Registration could not establish CSRF protection")

        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/register",
            payload={
                "display_name": "New Artist",
                "email": "new.artist@example.test",
                "password": "A-unique-registration-passphrase-2026!",
                "password_confirmation": "different-password",
                "terms_accepted": True,
            },
            origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "password_confirmation" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Registration accepted mismatched passwords")
        if FakeSupabaseHandler.registrations:
            raise RuntimeError("Invalid registration reached the identity provider")

        registration_payload = {
            "display_name": "New Artist",
            "email": "new.artist@example.test",
            "password": "A-unique-registration-passphrase-2026!",
            "password_confirmation": "A-unique-registration-passphrase-2026!",
            "terms_accepted": True,
        }
        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/register",
            payload=registration_payload,
            origin=base_url,
        )
        if status != HTTPStatus.CREATED or result.get("status") != "verification_required":
            raise RuntimeError("Valid email registration did not require verification")
        provider_registration = FakeSupabaseHandler.registrations[-1]
        metadata = provider_registration.get("data", {})
        if provider_registration.get("email") != "new.artist@example.test" or provider_registration.get("password") != registration_payload["password"]:
            raise RuntimeError("Registration credentials were not normalized for the identity provider")
        if metadata.get("display_name") != "New Artist" or metadata.get("terms_policy_version") != "2026-08-03" or not metadata.get("terms_accepted_at"):
            raise RuntimeError("Registration consent metadata was incomplete")

        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/resend-verification",
            payload={"email": "unregistered@example.test"},
            origin=base_url,
        )
        if status != HTTPStatus.ACCEPTED or result.get("status") != "verification_email_requested":
            raise RuntimeError("Verification resend revealed provider identity state")
        if FakeSupabaseHandler.verification_resends[-1] != {"type": "signup", "email": "unregistered@example.test"}:
            raise RuntimeError("Verification resend sent an unexpected provider payload")

        email_endpoints = {
            "/api/auth/register": "REGISTRATION_RATE_LIMITED",
            "/api/auth/resend-verification": "VERIFICATION_RATE_LIMITED",
            "/api/auth/forgot-password": "RECOVERY_RATE_LIMITED",
        }
        smtp_detail = "synthetic-smtp.internal: authentication failed for synthetic-sender@example.test"
        try:
            for endpoint_number, (endpoint, rate_code) in enumerate(email_endpoints.items()):
                for provider_status in (
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    HTTPStatus.BAD_GATEWAY,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    HTTPStatus.GATEWAY_TIMEOUT,
                ):
                    FakeSupabaseHandler.email_response_override = (
                        provider_status,
                        {"error_code": "unexpected_failure", "msg": smtp_detail},
                    )
                    email = f"mail-failure-{endpoint_number}-{provider_status}@example.test"
                    payload = {**registration_payload, "email": email} if endpoint.endswith("register") else {"email": email}
                    status, result, _ = request(
                        registration_opener,
                        base_url,
                        endpoint,
                        payload=payload,
                        origin=base_url,
                    )
                    expected_status = (
                        HTTPStatus.SERVICE_UNAVAILABLE
                        if provider_status == HTTPStatus.SERVICE_UNAVAILABLE
                        else HTTPStatus.BAD_GATEWAY
                    )
                    message = result.get("error", {}).get("message")
                    if (
                        status != expected_status
                        or result.get("error", {}).get("code") != "AUTH_EMAIL_UNAVAILABLE"
                        or not isinstance(message, str)
                        or not message
                        or "status" in result
                        or any(detail in json.dumps(result) for detail in (smtp_detail, "synthetic-smtp.internal", "synthetic-sender@example.test"))
                    ):
                        raise RuntimeError(f"Email endpoint {endpoint} did not safely report provider status {provider_status}")

                FakeSupabaseHandler.email_response_override = (
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error_code": "over_email_send_rate_limit", "msg": "Synthetic provider email rate limit"},
                )
                email = f"mail-rate-{endpoint_number}@example.test"
                payload = {**registration_payload, "email": email} if endpoint.endswith("register") else {"email": email}
                status, result, _ = request(
                    registration_opener,
                    base_url,
                    endpoint,
                    payload=payload,
                    origin=base_url,
                )
                if status != HTTPStatus.TOO_MANY_REQUESTS or result.get("error", {}).get("code") != rate_code:
                    raise RuntimeError(f"Email endpoint {endpoint} lost its provider rate-limit response")

            for provider_status, provider_code in (
                (HTTPStatus.BAD_REQUEST, "email_already_confirmed"),
                (HTTPStatus.NOT_FOUND, "user_not_found"),
                (HTTPStatus.UNPROCESSABLE_ENTITY, "identity_not_found"),
            ):
                FakeSupabaseHandler.email_response_override = (
                    provider_status,
                    {"error_code": provider_code, "msg": "Synthetic private identity detail"},
                )
                status, result, _ = request(
                    registration_opener,
                    base_url,
                    "/api/auth/resend-verification",
                    payload={"email": f"resend-private-{provider_status}@example.test"},
                    origin=base_url,
                )
                if (
                    status != HTTPStatus.ACCEPTED
                    or result.get("status") != "verification_email_requested"
                    or "Synthetic private identity detail" in json.dumps(result)
                    or provider_code in json.dumps(result)
                ):
                    raise RuntimeError("Verification resend exposed private provider identity state")
        finally:
            FakeSupabaseHandler.email_response_override = None

        unverified_signin = CookieOpener()
        request(unverified_signin, base_url, "/api/auth/csrf")
        try:
            for error_field in ("error_code", "code"):
                FakeSupabaseHandler.unverified_signin_error_field = error_field
                status, result, _ = request(
                    unverified_signin,
                    base_url,
                    "/api/auth/sign-in",
                    payload={"email": "unverified@example.test", "password": "Synthetic-unverified-password!"},
                    origin=base_url,
                )
                if (
                    status != HTTPStatus.FORBIDDEN
                    or result.get("error", {}).get("code") != "EMAIL_NOT_VERIFIED"
                    or unverified_signin.cookie_value("mt_access_token")
                    or unverified_signin.cookie_value("mt_refresh_token")
                ):
                    raise RuntimeError(f"Unverified email sign-in did not map provider {error_field} without creating a session")
        finally:
            FakeSupabaseHandler.unverified_signin_error_field = "error_code"

        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/verify-email-code",
            payload={"email": "new.artist@example.test", "verification_code": "12A456"},
            origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "verification_code" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Email verification accepted a malformed code")

        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/verify-email-code",
            payload={"email": "new.artist@example.test", "verification_code": "48273106"},
            origin=base_url,
        )
        if (
            status != HTTPStatus.OK
            or result.get("verified") is not True
            or result.get("type") != "email"
            or result.get("user", {}).get("email") != "new.artist@example.test"
        ):
            raise RuntimeError("Email verification code did not establish a session")
        if not registration_opener.cookie_value("mt_access_token") or not registration_opener.cookie_value("mt_refresh_token"):
            raise RuntimeError("Email verification code did not issue application cookies")

        status, result, _ = request(
            registration_opener,
            base_url,
            "/api/auth/verify-email",
            payload={"type": "signup", "token_hash": "valid-signup-token-hash"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("verified") is not True:
            raise RuntimeError("Signup verification token did not establish a session")
        if not registration_opener.cookie_value("mt_access_token") or not registration_opener.cookie_value("mt_refresh_token"):
            raise RuntimeError("Signup verification did not issue application cookies")
        status, result, _ = request(registration_opener, base_url, "/api/auth/verification-status")
        if status != HTTPStatus.OK or result.get("email_verified") is not True:
            raise RuntimeError("Verified registration status was not available")

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
        if status != HTTPStatus.ACCEPTED or result.get("status") != "recovery_code_sent":
            raise RuntimeError("Forgot Password did not return the enumeration-safe response")

        recovery_code_opener = CookieOpener()
        status, result, _ = request(recovery_code_opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Recovery code flow could not establish CSRF protection")
        status, result, _ = request(
            recovery_code_opener,
            base_url,
            "/api/auth/forgot-password",
            payload={"email": "recovery@example.test"},
            origin=base_url,
        )
        if status != HTTPStatus.ACCEPTED or result.get("status") != "recovery_code_sent":
            raise RuntimeError("Recovery code request was not accepted")
        status, result, _ = request(
            recovery_code_opener,
            base_url,
            "/api/auth/verify-recovery-code",
            payload={"email": "recovery@example.test", "recovery_code": "123"},
            origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "recovery_code" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Malformed recovery code was not rejected")
        status, result, _ = request(
            recovery_code_opener,
            base_url,
            "/api/auth/verify-recovery-code",
            payload={"email": "recovery@example.test", "recovery_code": "48273106"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("recovery_ready") is not True:
            raise RuntimeError("Valid recovery code did not establish a restricted recovery session")
        if not recovery_code_opener.cookie_value("mt_access_token") or not recovery_code_opener.cookie_value("mt_recovery_grant"):
            raise RuntimeError("Recovery code verification did not issue the required secure session cookies")

        status, result, _ = request(
            opener,
            base_url,
            "/api/auth/recovery-session",
            payload={"type": "recovery", "token_hash": "valid-recovery-token-hash"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("recovery_ready") is not True:
            raise RuntimeError("Recovery token did not establish a restricted recovery session")

        status, result, _ = request(recovery_code_opener, base_url, "/api/auth/recovery-status")
        if status != HTTPStatus.OK or result.get("recovery_ready") is not True:
            raise RuntimeError("Recovery session status was not available")

        status, _, headers = request(recovery_code_opener, base_url, "/workspace/images")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("Recovery-only session was allowed into the Workspace")

        status, _, headers = request(recovery_code_opener, base_url, "/settings/account")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("Recovery-only session was allowed into Account Settings")

        status, result, _ = request(
            recovery_code_opener,
            base_url,
            "/api/auth/reset-password",
            payload={"password": "A-new-password-2026!", "password_confirmation": "different"},
            origin=base_url,
        )
        if status != HTTPStatus.UNPROCESSABLE_ENTITY or "password_confirmation" not in result.get("error", {}).get("field_errors", {}):
            raise RuntimeError("Password confirmation mismatch was not rejected")

        status, result, _ = request(
            recovery_code_opener,
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

        status, result, _ = request(member_opener, base_url, "/api/auth/mfa/status")
        if status != HTTPStatus.OK or result.get("mfa", {}).get("enabled") is not False:
            raise RuntimeError("Member MFA status did not start disabled")
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/auth/mfa/enroll",
            payload={},
            origin=base_url,
        )
        if status != HTTPStatus.CREATED or result.get("id") != MEMBER_MFA_FACTOR_ID or not result.get("totp", {}).get("secret"):
            raise RuntimeError("Member could not start authenticator enrollment")
        status, result, _ = request(member_opener, base_url, "/api/auth/mfa/factors")
        pending = result.get("all", [])
        if status != HTTPStatus.OK or len(pending) != 1 or pending[0].get("status") != "unverified":
            raise RuntimeError("Pending authenticator enrollment was not projected safely")
        if "totp" in pending[0] or "secret" in pending[0]:
            raise RuntimeError("Authenticator enrollment secret leaked through the factor listing")
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/auth/mfa/challenge",
            payload={"factor_id": MEMBER_MFA_FACTOR_ID},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("id") != MEMBER_MFA_CHALLENGE_ID:
            raise RuntimeError("Member authenticator challenge could not start")
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/auth/mfa/verify",
            payload={
                "factor_id": MEMBER_MFA_FACTOR_ID,
                "challenge_id": MEMBER_MFA_CHALLENGE_ID,
                "code": "000000",
            },
            origin=base_url,
        )
        if status != HTTPStatus.UNAUTHORIZED or result.get("error", {}).get("code") != "MFA_CODE_INVALID":
            raise RuntimeError("Invalid authenticator code was not rejected")
        status, result, _ = request(
            member_opener,
            base_url,
            "/api/auth/mfa/verify",
            payload={
                "factor_id": MEMBER_MFA_FACTOR_ID,
                "challenge_id": MEMBER_MFA_CHALLENGE_ID,
                "code": "123456",
            },
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("aal") != "aal2":
            raise RuntimeError("Valid authenticator code did not establish AAL2")
        if member_opener.cookie_value("mt_access_token") != MEMBER_AAL2_ACCESS_TOKEN:
            raise RuntimeError("MFA verification did not rotate the application session")
        status, result, _ = request(member_opener, base_url, "/api/auth/mfa/status")
        member_mfa = result.get("mfa", {})
        if (
            status != HTTPStatus.OK
            or member_mfa.get("enabled") is not True
            or member_mfa.get("aal") != "aal2"
            or member_mfa.get("can_disable") is not True
        ):
            raise RuntimeError("Verified member authenticator status was incomplete")

        mfa_login_opener = CookieOpener()
        request(mfa_login_opener, base_url, "/api/auth/csrf")
        status, result, _ = request(
            mfa_login_opener,
            base_url,
            "/api/auth/sign-in",
            payload={"email": "member@example.test", "password": "Member-password-2026!"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("next_action") != "mfa":
            raise RuntimeError("Password sign-in bypassed an enabled member authenticator")
        status, _, headers = request(mfa_login_opener, base_url, "/workspace/images")
        mfa_route = urlparse(headers.get("Location", ""))
        if status != HTTPStatus.SEE_OTHER or mfa_route.path != "/auth/mfa":
            raise RuntimeError("Enabled member MFA did not guard the Workspace route")
        status, result, _ = request(mfa_login_opener, base_url, "/api/me/profile")
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "MFA_REQUIRED":
            raise RuntimeError("Enabled member MFA did not guard protected APIs")
        status, result, _ = request(
            mfa_login_opener,
            base_url,
            "/api/auth/mfa",
            payload={"confirmation": "disable-mfa"},
            origin=base_url,
            method="DELETE",
        )
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "MFA_REQUIRED":
            raise RuntimeError("AAL1 session could disable member MFA")
        status, result, _ = request(
            mfa_login_opener,
            base_url,
            "/api/auth/mfa/challenge",
            payload={"factor_id": MEMBER_MFA_FACTOR_ID},
            origin=base_url,
        )
        if status != HTTPStatus.OK:
            raise RuntimeError("Returning member could not challenge the saved authenticator")
        status, result, _ = request(
            mfa_login_opener,
            base_url,
            "/api/auth/mfa/verify",
            payload={
                "factor_id": MEMBER_MFA_FACTOR_ID,
                "challenge_id": result.get("id"),
                "code": "123456",
            },
            origin=base_url,
        )
        if status != HTTPStatus.OK or mfa_login_opener.cookie_value("mt_access_token") != MEMBER_AAL2_ACCESS_TOKEN:
            raise RuntimeError("Returning member could not complete authenticator verification")
        status, result, _ = request(
            mfa_login_opener,
            base_url,
            "/api/auth/mfa",
            payload={"confirmation": "disable-mfa"},
            origin=base_url,
            method="DELETE",
        )
        if (
            status != HTTPStatus.OK
            or result.get("disabled") is not True
            or result.get("other_sessions_revoked") is not True
            or result.get("mfa", {}).get("enabled") is not False
            or FakeSupabaseHandler.member_mfa_state != "off"
        ):
            raise RuntimeError("Verified member could not safely disable MFA")

        post_disable_opener = CookieOpener()
        request(post_disable_opener, base_url, "/api/auth/csrf")
        status, result, _ = request(
            post_disable_opener,
            base_url,
            "/api/auth/sign-in",
            payload={"email": "member@example.test", "password": "Member-password-2026!"},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("next_action") != "workspace":
            raise RuntimeError("Disabled member MFA continued to force authenticator verification")

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
        if status != HTTPStatus.NOT_FOUND:
            raise RuntimeError("Configured Supabase delivery leaked a legacy published derivative")

        print("csrf_missing_rejected=yes")
        print("google_oauth_pkce_validated=yes")
        print("google_oauth_account_profile_and_protected_pages=yes")
        print("google_oauth_signout_and_repeat_login=yes")
        print("google_oauth_cancelled_next_preserved=yes")
        print("google_oauth_replay_rejected=yes")
        print("google_oauth_external_next_rejected=yes")
        print("auth_destination_control_encoding_and_path_guards=yes")
        print("google_oauth_mfa_required=yes")
        print("google_provider_token_not_persisted=yes")
        print("email_registration_verification_required=yes")
        print("email_registration_consent_recorded=yes")
        print("verification_resend_enumeration_safe=yes")
        print("auth_email_provider_failures_safe=yes")
        print("auth_email_provider_rate_limits_preserved=yes")
        print("unverified_email_signin_recovery_available=yes")
        print("signup_verification_session_established=yes")
        print("csrf_cross_origin_rejected=yes")
        print("forgot_response_enumeration_safe=yes")
        print("recovery_code_format_rejected=yes")
        print("recovery_code_session_established=yes")
        print("recovery_session_restricted=yes")
        print("recovery_session_workspace_denied=yes")
        print("recovery_session_account_settings_denied=yes")
        print("password_updated_and_sessions_revoked=yes")
        print("workspace_direct_route_protected=yes")
        print("workspace_transient_authorization_retry=yes")
        print("account_settings_route_protected=yes")
        print("account_profile_read_write_validated=yes")
        print("account_session_capabilities_validated=yes")
        print("member_mfa_enrollment_verified=yes")
        print("member_mfa_password_guarded=yes")
        print("member_mfa_aal1_disable_rejected=yes")
        print("member_mfa_aal2_disable_validated=yes")
        print("admin_account_settings_requires_mfa=yes")
        print("account_session_bulk_revoke_validated=yes")
        print("legacy_original_private=yes")
        print("legacy_draft_derivative_private=yes")
        print("legacy_upload_listing_disabled=yes")
        print("configured_legacy_published_display_private=yes")
        print("secrets_logged=no")
    finally:
        app_server.shutdown()
        app_server.server_close()
        fake_server.shutdown()
        fake_server.server_close()
        temp_site.cleanup()


if __name__ == "__main__":
    main()
