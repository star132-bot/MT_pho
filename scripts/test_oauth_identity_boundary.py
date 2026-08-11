#!/usr/bin/env python3
"""Secret-free OAuth provider and linked-identity boundary test."""

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
import sys
import threading
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fake_access_token(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


MEMBER_ID = "00000000-0000-4000-8000-000000000002"
OTHER_ID = "00000000-0000-4000-8000-000000000099"
EMAIL_IDENTITY = "10000000-0000-4000-8000-000000000001"
GOOGLE_IDENTITY = "10000000-0000-4000-8000-000000000002"
APPLE_IDENTITY = "10000000-0000-4000-8000-000000000003"
MEMBER_TOKEN = fake_access_token({"sub": MEMBER_ID, "aal": "aal1"})
APPLE_TOKEN = fake_access_token({"sub": OTHER_ID, "aal": "aal1"})


def identity(identity_id: str, provider: str, email: str) -> dict:
    return {
        "id": identity_id,
        "provider": provider,
        "email": email,
        "identity_data": {"email": email},
        "created_at": "2026-08-01T00:00:00Z",
        "last_sign_in_at": "2026-08-06T00:00:00Z",
    }


class FakeIdentityHandler(BaseHTTPRequestHandler):
    identities = [identity(EMAIL_IDENTITY, "email", "member@example.test")]
    authorize_queries: list[dict] = []
    oauth_exchanges: list[dict] = []
    unlink_ids: list[str] = []
    provider_port = 0

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

    def user_payload(self, token: str) -> dict | None:
        if token == MEMBER_TOKEN:
            return {
                "id": MEMBER_ID,
                "email": "member@example.test",
                "email_confirmed_at": "2026-08-01T00:00:00Z",
                "app_metadata": {"provider": "email", "providers": ["email"]},
                "identities": [dict(item) for item in type(self).identities],
                "factors": [],
            }
        if token == APPLE_TOKEN:
            return {
                "id": OTHER_ID,
                "email": "apple.member@example.test",
                "email_confirmed_at": "2026-08-01T00:00:00Z",
                "app_metadata": {"provider": "apple", "providers": ["apple"]},
                "identities": [identity(APPLE_IDENTITY, "apple", "apple.member@example.test")],
                "factors": [],
            }
        return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if parsed.path == "/auth/v1/user":
            user = self.user_payload(token)
            if user:
                self.send_json(HTTPStatus.OK, user)
                return
        if parsed.path == "/auth/v1/user/identities/authorize" and token == MEMBER_TOKEN:
            query = parse_qs(parsed.query)
            type(self).authorize_queries.append(query)
            provider = query.get("provider", [""])[0]
            self.send_json(
                HTTPStatus.OK,
                {"url": f"http://127.0.0.1:{type(self).provider_port}/provider/{provider}?state=fake"},
            )
            return
        if parsed.path == "/rest/v1/user_profiles" and token == MEMBER_TOKEN:
            self.send_json(HTTPStatus.OK, [{
                "display_name": "MT Member", "avatar_url": None, "bio": "", "website_url": None,
                "country_code": "US", "preferred_locale": "en", "timezone": "UTC",
                "copyright_name": None, "default_license_preference": None,
                "professional_headline": None, "company": None, "city": None,
                "availability_status": "unavailable", "instagram_url": None, "linkedin_url": None,
            }])
            return
        if parsed.path == "/rest/v1/rpc/current_authorization" and token in {MEMBER_TOKEN, APPLE_TOKEN}:
            user_id = MEMBER_ID if token == MEMBER_TOKEN else OTHER_ID
            self.send_json(HTTPStatus.OK, {"user_id": user_id, "account_status": "active", "roles": ["user"], "aal": "aal1"})
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if parsed.path == "/rest/v1/rpc/current_authorization" and token in {MEMBER_TOKEN, APPLE_TOKEN}:
            user_id = MEMBER_ID if token == MEMBER_TOKEN else OTHER_ID
            self.send_json(HTTPStatus.OK, {"user_id": user_id, "account_status": "active", "roles": ["user"], "aal": "aal1"})
            return
        if parsed.path == "/auth/v1/token" and parse_qs(parsed.query).get("grant_type") == ["password"]:
            self.send_json(HTTPStatus.OK, {
                "access_token": MEMBER_TOKEN,
                "refresh_token": "refresh-member",
                "expires_in": 3600,
                "user": self.user_payload(MEMBER_TOKEN),
            })
            return
        if parsed.path == "/auth/v1/token" and parse_qs(parsed.query).get("grant_type") == ["pkce"]:
            body = self.body()
            type(self).oauth_exchanges.append(body)
            code = body.get("auth_code")
            if not body.get("code_verifier"):
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "missing verifier"})
                return
            if code == "valid-apple-code":
                self.send_json(HTTPStatus.OK, {
                    "access_token": APPLE_TOKEN, "refresh_token": "refresh-apple", "expires_in": 3600,
                    "provider_token": "must-not-reach-browser", "user": self.user_payload(APPLE_TOKEN),
                })
                return
            if code in {"valid-link-google", "valid-link-apple"}:
                provider = "google" if code.endswith("google") else "apple"
                identity_id = GOOGLE_IDENTITY if provider == "google" else APPLE_IDENTITY
                email = f"{provider}.linked@example.test"
                if not any(item["id"] == identity_id for item in type(self).identities):
                    type(self).identities.append(identity(identity_id, provider, email))
                self.send_json(HTTPStatus.OK, {
                    "access_token": MEMBER_TOKEN, "refresh_token": f"refresh-link-{provider}", "expires_in": 3600,
                    "user": self.user_payload(MEMBER_TOKEN),
                })
                return
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid code"})
            return
        if parsed.path.startswith("/auth/v1/logout"):
            self.body()
            self.send_json(HTTPStatus.OK, {})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if parsed.path.startswith("/auth/v1/user/identities/") and token == MEMBER_TOKEN:
            identity_id = parsed.path.rsplit("/", 1)[-1]
            type(self).unlink_ids.append(identity_id)
            if len(type(self).identities) <= 1:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"message": "single identity"})
                return
            before = len(type(self).identities)
            type(self).identities = [item for item in type(self).identities if item["id"] != identity_id]
            if len(type(self).identities) == before:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"message": "not found"})
                return
            self.send_json(HTTPStatus.OK, {})
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {})


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        return None


class CookieOpener:
    def __init__(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar), RejectRedirects())

    def open(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._opener.open(*args, **kwargs)

    def cookie_value(self, name: str) -> str:
        return next((cookie.value for cookie in self.cookie_jar if cookie.name == name), "")


def request(opener: CookieOpener, base_url: str, path: str, *, payload: dict | None = None, origin: str | None = None, method: str | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        csrf = opener.cookie_value("mt_csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf
    req = urllib.request.Request(f"{base_url}{path}", data=body, headers=headers, method=method or ("POST" if body else "GET"))
    try:
        with opener.open(req, timeout=10) as response:
            raw = response.read()
            result = json.loads(raw.decode()) if raw else {}
            return response.status, result, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        result = json.loads(raw.decode()) if raw else {}
        return error.code, result, error.headers


def main() -> None:
    FakeIdentityHandler.identities = [identity(EMAIL_IDENTITY, "email", "member@example.test")]
    FakeIdentityHandler.authorize_queries = []
    FakeIdentityHandler.oauth_exchanges = []
    FakeIdentityHandler.unlink_ids = []
    provider_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeIdentityHandler)
    FakeIdentityHandler.provider_port = provider_server.server_address[1]
    provider_thread = threading.Thread(target=provider_server.serve_forever, daemon=True)
    provider_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_COOKIE_SECURE"] = "0"
    os.environ["MT_RUNTIME_ENVIRONMENT"] = "development"
    os.environ.pop("MT_PUBLIC_BASE_URL", None)
    app = importlib.import_module("server")
    app.OAUTH_FLOWS.clear()
    app_server = ThreadingHTTPServer(("127.0.0.1", 0), partial(app.MTRequestHandler, directory=str(ROOT)))
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    base_url = f"http://127.0.0.1:{app_server.server_address[1]}"

    try:
        apple = CookieOpener()
        status, _, headers = request(apple, base_url, "/auth/oauth/apple?next=/works.html")
        if status != HTTPStatus.SEE_OTHER:
            raise RuntimeError("Apple OAuth did not start")
        start_url = urlparse(headers.get("Location", ""))
        if parse_qs(start_url.query).get("provider") != ["apple"]:
            raise RuntimeError("Apple OAuth provider was not selected")
        status, _, headers = request(apple, base_url, "/auth/oauth/callback?code=valid-apple-code")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/works.html":
            raise RuntimeError("Apple OAuth did not return to Works")
        if any(cookie.value == "must-not-reach-browser" for cookie in apple.cookie_jar):
            raise RuntimeError("Apple provider token leaked into cookies")

        member = CookieOpener()
        status, _, _ = request(member, base_url, "/api/auth/csrf")
        status, _, _ = request(member, base_url, "/api/auth/sign-in", payload={"email": "member@example.test", "password": "ignored"}, origin=base_url)
        if status != HTTPStatus.OK:
            raise RuntimeError("Member session could not be established")
        status, result, _ = request(member, base_url, "/api/me/identities")
        if status != HTTPStatus.OK or len(result.get("identities", [])) != 1:
            raise RuntimeError("Initial identity list was not projected")

        status, _, _ = request(member, base_url, "/api/me/identities/link", payload={"provider": "google"})
        if status != HTTPStatus.FORBIDDEN:
            raise RuntimeError("Identity link started without same-origin CSRF verification")

        status, result, _ = request(member, base_url, "/api/me/identities/link", payload={"provider": "google"}, origin=base_url)
        if status != HTTPStatus.OK or not result.get("redirect_url"):
            raise RuntimeError("Google identity link did not start")
        query = FakeIdentityHandler.authorize_queries[-1]
        if query.get("provider") != ["google"] or query.get("skip_http_redirect") != ["true"]:
            raise RuntimeError("Identity link authorize request was incomplete")
        status, _, headers = request(member, base_url, "/auth/oauth/callback?code=valid-link-google")
        if status != HTTPStatus.SEE_OTHER or "identity_status=linked" not in headers.get("Location", ""):
            raise RuntimeError("Linked OAuth callback did not return to account settings")
        verifier = FakeIdentityHandler.oauth_exchanges[-1].get("code_verifier", "")
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if expected_challenge != query.get("code_challenge", [""])[0]:
            raise RuntimeError("Linked OAuth PKCE verifier did not match its challenge")

        status, result, _ = request(member, base_url, "/api/me/identities")
        if status != HTTPStatus.OK or {item["provider"] for item in result.get("identities", [])} != {"email", "google"}:
            raise RuntimeError("Linked Google identity was not visible")

        google_id = next(item["id"] for item in result["identities"] if item["provider"] == "google")
        status, result, _ = request(member, base_url, f"/api/me/identities/{google_id}", payload={}, origin=base_url, method="DELETE")
        if status != HTTPStatus.OK or len(result.get("identities", [])) != 1:
            raise RuntimeError("Google identity could not be unlinked")
        status, _, _ = request(member, base_url, f"/api/me/identities/{EMAIL_IDENTITY}", payload={}, origin=base_url, method="DELETE")
        if status != HTTPStatus.CONFLICT:
            raise RuntimeError("Last identity could be removed")
        status, _, _ = request(member, base_url, "/api/me/identities/not-a-uuid", payload={}, origin=base_url, method="DELETE")
        if status != HTTPStatus.NOT_FOUND:
            raise RuntimeError("Invalid identity id was not rejected")

        print("apple_oauth_pkce_validated=yes")
        print("apple_provider_token_not_persisted=yes")
        print("identity_link_csrf_and_pkce_validated=yes")
        print("identity_linked_projection_validated=yes")
        print("identity_unlink_owner_and_last_guard_validated=yes")
    finally:
        app_server.shutdown()
        provider_server.shutdown()


if __name__ == "__main__":
    main()
