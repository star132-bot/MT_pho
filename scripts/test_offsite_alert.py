#!/usr/bin/env python3
"""Network-free acceptance for the offsite failure notifier."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTIFIER = ROOT / "scripts" / "notify_offsite_failure.py"
SECRET = "fixture-hmac-secret-never-log"
LEAK = "fixture-password-never-log"


class WebhookHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict[str, str], bytes]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.requests.append((self.path, dict(self.headers), body))
        if self.path == "/redirect":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/accepted")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def log_message(self, format_string: str, *args) -> None:
        return


def run(
    environment: dict[str, str],
    unit: str = "mt-presence-offsite-backup.service",
    *,
    test: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = [sys.executable, str(NOTIFIER), unit]
    if test:
        arguments.append("--test")
    return subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def load_events(spool: Path) -> list[dict[str, object]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in spool.glob("[0-9a-f]*.json")]


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="mt-offsite-alert-test-") as temporary:
            root = Path(temporary)
            spool = root / "spool"
            base = {
                **os.environ,
                "MT_OFFSITE_ALERT_HOST_LABEL": "fixture-backup-host",
                "MT_OFFSITE_ALERT_SPOOL_DIR": str(spool),
                "MT_OFFSITE_ALERT_MIN_INTERVAL_SECONDS": "900",
                "MT_OFFSITE_ALERT_ALLOW_HTTP_LOOPBACK": "1",
                "MT_OFFSITE_ALERT_WEBHOOK_SECRET": SECRET,
                "MT_OFFSITE_ALERT_SMTP_PASSWORD": LEAK,
            }

            no_channel = run(base)
            if no_channel.returncode != 1 or "no_channel_configured" not in no_channel.stderr:
                raise AssertionError("missing alert channel did not fail while retaining the spool event")
            failed = load_events(spool)
            if len(failed) != 1 or failed[0].get("delivery", {}).get("status") != "failed":
                raise AssertionError("failed delivery was not recorded durably")

            accepted_environment = {
                **base,
                "MT_OFFSITE_ALERT_WEBHOOK_URL": f"http://127.0.0.1:{server.server_port}/accepted",
            }
            delivered = run(accepted_environment)
            if delivered.returncode != 0 or "offsite_alert_delivered=webhook" not in delivered.stdout:
                raise AssertionError(f"webhook alert failed: {delivered.stderr}")
            if len(WebhookHandler.requests) != 1:
                raise AssertionError("webhook did not receive exactly one alert")
            _, raw_headers, body = WebhookHandler.requests[0]
            headers = {name.lower(): value for name, value in raw_headers.items()}
            timestamp = headers.get("x-mt-presence-timestamp", "")
            expected = hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
            if headers.get("x-mt-presence-signature") != f"sha256={expected}":
                raise AssertionError("webhook HMAC signature is invalid")
            event = json.loads(body)["event"]
            if event.get("unit") != "mt-presence-offsite-backup.service" or event.get("severity") != "critical" or event.get("test"):
                raise AssertionError("webhook event contract drifted")

            tested = run(accepted_environment, test=True)
            if tested.returncode != 0 or len(WebhookHandler.requests) != 2:
                raise AssertionError("manual channel test did not bypass incident deduplication")
            test_event = json.loads(WebhookHandler.requests[-1][2])["event"]
            if test_event.get("severity") != "info" or not test_event.get("test"):
                raise AssertionError("manual channel test was presented as a real incident")

            suppressed = run(accepted_environment)
            if suppressed.returncode != 0 or "offsite_alert_suppressed=" not in suppressed.stdout:
                raise AssertionError("duplicate successful alert was not rate limited")
            if len(WebhookHandler.requests) != 2:
                raise AssertionError("suppressed alert still reached the webhook")

            redirect_environment = {
                **base,
                "MT_OFFSITE_ALERT_MIN_INTERVAL_SECONDS": "0",
                "MT_OFFSITE_ALERT_WEBHOOK_URL": f"http://127.0.0.1:{server.server_port}/redirect",
            }
            redirected = run(redirect_environment, "mt-presence-offsite-verify.service")
            if redirected.returncode != 1 or "webhook_redirect_rejected" not in redirected.stderr:
                raise AssertionError("webhook redirect was not rejected")

            unsafe = run(base, "../../unsafe")
            if unsafe.returncode != 1 or "invalid_unit" not in unsafe.stderr:
                raise AssertionError("unsafe systemd unit label was accepted")

            combined = "\n".join([no_channel.stdout, no_channel.stderr, delivered.stdout, delivered.stderr, redirected.stdout, redirected.stderr])
            serialized = "\n".join(path.read_text(encoding="utf-8") for path in spool.glob("*.json"))
            for secret in (SECRET, LEAK):
                if secret in combined or secret in serialized:
                    raise AssertionError("alert material leaked to output or spool")
            if any((path.stat().st_mode & 0o777) != 0o600 for path in spool.glob("*.json")):
                raise AssertionError("alert spool event mode is not 0600")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("Offsite alert acceptance passed (audit, HMAC, dedupe, redirect rejection).")


if __name__ == "__main__":
    main()
