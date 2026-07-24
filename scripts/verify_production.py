#!/usr/bin/env python3
"""Read-only production smoke checks for the public and protected boundaries."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from urllib.parse import urljoin, urlparse


SENSITIVE_WORK_FIELDS = {
    "owner_user_id",
    "auth_subject",
    "storage_bucket",
    "storage_path",
    "checksum_sha256",
    "internal_note",
    "original_url",
}

PRIVATE_STATIC_PATHS = (
    "/database/product_schema.sql",
    "/scripts/production_preflight.py",
    "/deploy/nginx-mt-presence.conf",
    "/docs/operations/production-deployment.md",
    "/.git/config",
    "/%64atabase/product_schema.sql",
    "/scripts%2fproduction_preflight.py",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def fail(message: str) -> None:
    print(f"production verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def request(base_url: str, path: str) -> tuple[int, dict[str, str], bytes]:
    target = urljoin(f"{base_url}/", path.lstrip("/"))
    outgoing = urllib.request.Request(target, headers={"Accept": "application/json", "User-Agent": "mt-production-verifier/1"})
    try:
        response = OPENER.open(outgoing, timeout=15)
        with response:
            return response.status, dict(response.headers.items()), response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read(2 * 1024 * 1024)
    except (urllib.error.URLError, TimeoutError) as error:
        fail(f"{path} could not be reached: {error.reason if hasattr(error, 'reason') else error}")


def json_body(body: bytes, path: str) -> dict:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail(f"{path} did not return valid JSON")
    if not isinstance(payload, dict):
        fail(f"{path} returned an unexpected JSON shape")
    return payload


def header(headers: dict[str, str], name: str) -> str:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), "")


def validate_origin(value: str, label: str, *, allow_http_loopback: bool, require_loopback: bool = False) -> str:
    origin = value.rstrip("/")
    parsed = urlparse(origin)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme != "https" and not (allow_http_loopback and parsed.scheme == "http" and loopback))
        or (require_loopback and not loopback)
    ):
        suffix = "; only an explicit loopback HTTP origin is allowed" if allow_http_loopback else ""
        fail(f"{label} must be a credential-free HTTPS origin{suffix}")
    return origin


def verify(args: argparse.Namespace) -> None:
    base_url = validate_origin(
        args.base_url,
        "base URL",
        allow_http_loopback=args.allow_http_loopback,
    )
    readiness_url = validate_origin(
        args.readiness_url,
        "readiness URL",
        allow_http_loopback=True,
        require_loopback=True,
    )

    status, _, body = request(base_url, "/healthz")
    if status != HTTPStatus.OK or json_body(body, "/healthz").get("status") != "ok":
        fail("health endpoint is not healthy")
    print("[ok] liveness")

    status, _, body = request(readiness_url, "/readyz")
    readiness = json_body(body, "/readyz")
    if status != HTTPStatus.OK or readiness.get("status") != "ready":
        fail("readiness endpoint is not ready")
    if readiness.get("dependencies") != {"supabase": "available"}:
        fail("readiness dependency contract is unexpected")
    print("[ok] provider readiness")

    status, headers, body = request(base_url, "/")
    if status != HTTPStatus.OK or b"MT Presence" not in body:
        fail("public home is unavailable")
    if not args.allow_http_loopback:
        required_headers = {
            "Strict-Transport-Security": "max-age=",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Request-ID": "",
        }
        for name, expected in required_headers.items():
            value = header(headers, name)
            if not value or (expected and expected not in value):
                fail(f"public response is missing secure {name}")
    print("[ok] public shell and security headers")

    status, _, body = request(base_url, "/api/archive/images?limit=1")
    archive = json_body(body, "/api/archive/images")
    if status != HTTPStatus.OK or archive.get("source") in {"local-sqlite", "sample", "indexeddb"}:
        fail("public Works is not using the authoritative provider")
    for item in archive.get("items") or []:
        leaked = SENSITIVE_WORK_FIELDS.intersection(item)
        if leaked:
            fail(f"public Works leaked sensitive fields: {', '.join(sorted(leaked))}")
    print("[ok] authoritative public Works boundary")

    for path in PRIVATE_STATIC_PATHS:
        status, _, body = request(base_url, path)
        if status != HTTPStatus.NOT_FOUND or b"create table" in body.lower() or b"production_preflight" in body:
            fail(f"private repository path is publicly readable: {path}")
    print("[ok] private repository paths are not publicly served")

    for path in ("/dashboard", "/workspace/notifications", "/inbox", "/admin/audit", "/admin/users"):
        status, headers, _ = request(base_url, path)
        location = header(headers, "Location")
        if status != HTTPStatus.SEE_OTHER or not location.startswith("/auth/sign-in"):
            fail(f"anonymous protected route did not redirect safely: {path}")
    print("[ok] anonymous protected-route boundary")

    status, headers, body = request(base_url, "/api/auth/csrf")
    csrf = json_body(body, "/api/auth/csrf")
    set_cookie = header(headers, "Set-Cookie")
    if status != HTTPStatus.OK or not csrf.get("csrf_token"):
        fail("CSRF bootstrap is unavailable")
    if not args.allow_http_loopback and not all(marker in set_cookie for marker in ("Secure", "HttpOnly", "SameSite=Strict")):
        fail("production CSRF cookie attributes are incomplete")
    print("[ok] CSRF cookie boundary")

    print("Production read-only smoke verification passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an MT Presence production deployment.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--readiness-url",
        default="http://127.0.0.1:8131",
        help="loopback Web origin used for the protected provider-readiness probe",
    )
    parser.add_argument("--allow-http-loopback", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    verify(parse_args())
