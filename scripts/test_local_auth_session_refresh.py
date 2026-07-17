#!/usr/bin/env python3
"""Live, secret-safe regression test for the local Auth session boundary."""

from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("MT_TEST_BASE_URL", "http://127.0.0.1:8134").rstrip("/")


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        return None


def local_request(opener, path: str, *, payload: dict | None = None) -> tuple[int, object, list[str]]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "Origin": BASE_URL}
    if body is not None:
        headers["Content-Type"] = "application/json"
        csrf_token = next(
            (
                cookie.value
                for handler in opener.handlers
                for cookie in getattr(handler, "cookiejar", [])
                if cookie.name.endswith("mt_csrf_token")
            ),
            "",
        )
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8")) if raw and response.headers.get_content_type() == "application/json" else None
            return response.status, result, response.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as error:
        error.read()
        raise RuntimeError(f"Local Auth {path} failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Local Auth {path} is unavailable") from error


def revoke_test_session(jar: http.cookiejar.CookieJar) -> None:
    access_token = next((cookie.value for cookie in jar if cookie.name == "mt_access_token"), "")
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not access_token or not url or not key:
        return
    request = urllib.request.Request(
        f"{url}/auth/v1/logout?scope=local",
        data=b"{}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        # Cleanup is best effort; never leak the provider response or token.
        pass


def main() -> None:
    load_dotenv()
    email = required("MT_DEV_ADMIN_EMAIL")
    password = required("MT_DEV_ADMIN_PASSWORD")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), RejectRedirects())
    try:
        csrf_status, csrf_result, _ = local_request(opener, "/api/auth/csrf")
        if csrf_status != 200 or not isinstance(csrf_result, dict) or not csrf_result.get("csrf_token"):
            raise RuntimeError("Local Auth CSRF boundary did not initialize")

        sign_in_status, result, _ = local_request(
            opener,
            "/api/auth/sign-in",
            payload={"email": email, "password": password},
        )
        if sign_in_status != 200 or not isinstance(result, dict) or result.get("next_action") != "mfa":
            raise RuntimeError("Local Admin sign-in did not establish the expected AAL1 session")

        access_cookie = next((cookie for cookie in jar if cookie.name == "mt_access_token"), None)
        refresh_cookie = next((cookie for cookie in jar if cookie.name == "mt_refresh_token"), None)
        if access_cookie is None or refresh_cookie is None:
            raise RuntimeError("Local sign-in did not set both HttpOnly session cookies")
        access_cookie.value = "invalid-access-token"

        me_status, _, rotated_headers = local_request(opener, "/api/me")
        rotated_names = {
            header.split("=", 1)[0].strip()
            for header in rotated_headers
            if "=" in header
        }
        if me_status != 200 or not {"mt_access_token", "mt_refresh_token"}.issubset(rotated_names):
            raise RuntimeError("Refresh-token rotation did not return both replacement cookies")

        mfa_status, _, _ = local_request(opener, "/auth/mfa?next=/workspace")
        if mfa_status != 200:
            raise RuntimeError("The refreshed session did not reach the protected MFA route")

        print("sign_in_status=200")
        print("session_refresh_status=200")
        print("rotated_session_cookies=2")
        print("protected_mfa_status=200")
        print("secrets_logged=no")
    finally:
        revoke_test_session(jar)


if __name__ == "__main__":
    main()
