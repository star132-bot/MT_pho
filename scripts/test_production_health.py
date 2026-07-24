#!/usr/bin/env python3
"""Secret-free production health/readiness boundary coverage."""

from __future__ import annotations

import importlib
import json
import os
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    ready = True
    calls = 0

    def log_message(self, _format, *_args) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/rest/v1/rpc/get_public_works":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or "0")
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        if payload != {"target_creator_slug": None, "page_limit": 1, "page_offset": 0}:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        if not type(self).ready:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
            return
        body = json.dumps({"items": [], "count": 0}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def request(base_url: str, path: str, *, method: str = "GET") -> tuple[int, dict, dict[str, str], bytes]:
    raw_request = urllib.request.Request(f"{base_url}{path}", method=method)
    try:
        with urllib.request.urlopen(raw_request, timeout=4) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}, dict(response.headers), raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw.decode("utf-8")) if raw else {}, dict(error.headers), raw


def main() -> None:
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    start_server(provider)
    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "health-test-publishable-key"

    import server as server_module

    server_module = importlib.reload(server_module)
    app = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(server_module.MTRequestHandler, directory=str(ROOT)),
    )
    start_server(app)
    base_url = f"http://127.0.0.1:{app.server_address[1]}"
    try:
        status, payload, headers, _ = request(base_url, "/healthz")
        if status != HTTPStatus.OK or payload != {"status": "ok"} or FakeSupabaseHandler.calls:
            raise RuntimeError("Liveness was not a provider-independent minimal response")
        if "no-store" not in headers.get("Cache-Control", ""):
            raise RuntimeError("Liveness was cacheable")

        status, payload, headers, raw = request(base_url, "/healthz", method="HEAD")
        if status != HTTPStatus.OK or payload or raw or FakeSupabaseHandler.calls:
            raise RuntimeError("Liveness HEAD executed work or returned a body")
        if "no-store" not in headers.get("Cache-Control", ""):
            raise RuntimeError("Liveness HEAD was cacheable")

        status, payload, headers, _ = request(base_url, "/readyz")
        expected = {"status": "ready", "dependencies": {"supabase": "available"}}
        if status != HTTPStatus.OK or payload != expected or FakeSupabaseHandler.calls != 1:
            raise RuntimeError("Readiness did not perform the bounded Supabase probe")
        if "no-store" not in headers.get("Cache-Control", ""):
            raise RuntimeError("Readiness was cacheable")

        FakeSupabaseHandler.ready = False
        status, payload, _, _ = request(base_url, "/readyz")
        expected = {"status": "unavailable", "dependencies": {"supabase": "unavailable"}}
        if status != HTTPStatus.SERVICE_UNAVAILABLE or payload != expected or FakeSupabaseHandler.calls != 2:
            raise RuntimeError("Readiness failure leaked diagnostics or returned the wrong status")

        serialized = json.dumps(payload)
        for forbidden in ("SUPABASE_URL", "publishable", "health-test", "provider", "version", "key"):
            if forbidden in serialized:
                raise RuntimeError(f"Readiness leaked {forbidden}")
    finally:
        app.shutdown()
        app.server_close()
        provider.shutdown()
        provider.server_close()

    print("healthz_minimal_provider_independent=yes")
    print("healthz_head_no_body=yes")
    print("readyz_supabase_probe=yes")
    print("readyz_failure_minimal_503=yes")
    print("health_readiness_cacheable=no")


if __name__ == "__main__":
    main()
