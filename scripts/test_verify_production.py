#!/usr/bin/env python3
"""Network-free acceptance for the read-only production verifier."""

from __future__ import annotations

import argparse
import importlib.util
import json
from http import HTTPStatus
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("verify_production.py")
SPEC = importlib.util.spec_from_file_location("mt_verify_production", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("production verifier module is unavailable")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

PUBLIC_ORIGIN = "https://portfolio.example.com"
READINESS_ORIGIN = "http://127.0.0.1:8131"


def encoded(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def fixture_request(calls: list[tuple[str, str]], base_url: str, path: str):
    calls.append((base_url, path))
    if path == "/healthz":
        return HTTPStatus.OK, {}, encoded({"status": "ok"})
    if path == "/readyz":
        return HTTPStatus.OK, {}, encoded({"status": "ready", "dependencies": {"supabase": "available"}})
    if path == "/":
        return HTTPStatus.OK, {
            "Strict-Transport-Security": "max-age=31536000",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Request-ID": "fixture-request",
        }, b"<title>MT Presence</title>"
    if path == "/api/archive/images?limit=1":
        return HTTPStatus.OK, {}, encoded({"source": "supabase", "items": [{"id": "public-work"}]})
    if path in VERIFIER.PRIVATE_STATIC_PATHS:
        return HTTPStatus.NOT_FOUND, {}, b"Not found"
    if path in ("/dashboard", "/workspace/notifications", "/inbox", "/admin/audit", "/admin/users"):
        return HTTPStatus.SEE_OTHER, {"Location": "/auth/sign-in?next=protected"}, b""
    if path == "/api/auth/csrf":
        return HTTPStatus.OK, {
            "Set-Cookie": "__Host-mt_csrf_token=fixture; Secure; HttpOnly; SameSite=Strict",
        }, encoded({"csrf_token": "fixture-token"})
    raise AssertionError(f"unexpected verifier request: {base_url}{path}")


def main() -> None:
    calls: list[tuple[str, str]] = []
    args = argparse.Namespace(
        base_url=PUBLIC_ORIGIN,
        readiness_url=READINESS_ORIGIN,
        allow_http_loopback=False,
    )
    with mock.patch.object(
        VERIFIER,
        "request",
        side_effect=lambda base_url, path: fixture_request(calls, base_url, path),
    ):
        VERIFIER.verify(args)
    if (READINESS_ORIGIN, "/readyz") not in calls or (PUBLIC_ORIGIN, "/readyz") in calls:
        raise AssertionError("readiness was not isolated to the loopback origin")

    unsafe_args = argparse.Namespace(
        base_url=PUBLIC_ORIGIN,
        readiness_url="https://portfolio.example.com",
        allow_http_loopback=False,
    )
    try:
        VERIFIER.verify(unsafe_args)
    except SystemExit as error:
        if error.code != 1:
            raise
    else:
        raise AssertionError("production verifier accepted a non-loopback readiness URL")

    print("Production verifier acceptance passed (public HTTPS + protected loopback readiness).")


if __name__ == "__main__":
    main()
