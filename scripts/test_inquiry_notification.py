#!/usr/bin/env python3
"""Network-free acceptance for the optional Contact inquiry email notification."""

from __future__ import annotations

import io
import json
import sys
import threading
import time
import urllib.request
import uuid
from contextlib import redirect_stderr
from functools import partial
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


SETTINGS = {
    "recipient": "photographer@example.com",
    "sender": "inquiries@example.com",
    "host": "smtp.example.com",
    "port": "465",
    "security": "ssl",
    "username": "inquiries@example.com",
    "password": "fixture-app-password-never-log",
}
VISITOR_EMAIL = "visitor@example.org"
CSRF_TOKEN = "a" * 43
VISITOR_MESSAGE = "We would like to license two prints for a hotel lobby."


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, username, password):
        if self.fail:
            raise server.smtplib.SMTPAuthenticationError(535, b"rejected")

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def rpc_result(replayed: bool) -> tuple[HTTPStatus, dict]:
    return HTTPStatus.OK, {
        "reference": "INQ-0123456789AB",
        "status": "received",
        "created_at": "2026-10-13T08:00:00Z",
        "replayed": replayed,
        "selected_work_count": 2,
    }


def post_inquiry(port: int, sender_name: str) -> int:
    body = json.dumps(
        {
            "sender_name": sender_name,
            "sender_email": VISITOR_EMAIL,
            "inquiry_type": "licensing",
            "organization": "Harbour Hotel",
            "project_use": "Lobby print licensing",
            "message": VISITOR_MESSAGE,
            "website": "",
            "work_ids": [],
            "idempotency_key": str(uuid.uuid4()),
        }
    ).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/inquiries",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-CSRF-Token": CSRF_TOKEN,
            "Cookie": f"{server.CSRF_COOKIE}={CSRF_TOKEN}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def wait_for_sent(count: int) -> None:
    deadline = time.monotonic() + 5
    while len(FakeSMTP.sent) < count and time.monotonic() < deadline:
        time.sleep(0.02)


def main() -> None:
    app_server = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.MTRequestHandler, directory=str(ROOT)))
    port = app_server.server_address[1]
    threading.Thread(target=app_server.serve_forever, daemon=True).start()
    try:
        with (
            mock.patch.object(server.smtplib, "SMTP_SSL", FakeSMTP),
            mock.patch.object(server, "consume_inquiry_rate_limit", return_value=True),
        ):
            # Disabled by default: inquiry is accepted and nothing is sent.
            with mock.patch.object(server, "supabase_rest_request", return_value=rpc_result(False)):
                status = post_inquiry(port, "Ada Visitor")
            if status != HTTPStatus.ACCEPTED or FakeSMTP.sent:
                raise RuntimeError(f"unconfigured notification changed inquiry behaviour: {status}")

            with mock.patch.dict(server.INQUIRY_NOTIFY_SETTINGS, SETTINGS):
                # A new inquiry sends one email; header injection in the name is neutralised.
                with mock.patch.object(server, "supabase_rest_request", return_value=rpc_result(False)):
                    status = post_inquiry(port, "Ada Visitor\r\nBcc: attacker@example.net")
                wait_for_sent(1)
                if status != HTTPStatus.ACCEPTED or len(FakeSMTP.sent) != 1:
                    raise RuntimeError("new inquiry did not produce exactly one notification")
                message = FakeSMTP.sent[0]
                if message["To"] != SETTINGS["recipient"] or message["Bcc"] is not None:
                    raise RuntimeError("notification recipients are wrong")
                if VISITOR_EMAIL not in message["Reply-To"] or "\n" in message["Subject"]:
                    raise RuntimeError("notification reply/subject headers are wrong")
                text = message.get_content()
                for expected in ("INQ-0123456789AB", VISITOR_EMAIL, VISITOR_MESSAGE, "Harbour Hotel", "Selected works: 2"):
                    if expected not in text:
                        raise RuntimeError(f"notification body is missing {expected!r}")

                # An idempotent replay must not email the photographer twice.
                with mock.patch.object(server, "supabase_rest_request", return_value=rpc_result(True)):
                    status = post_inquiry(port, "Ada Visitor")
                time.sleep(0.2)
                if status != HTTPStatus.ACCEPTED or len(FakeSMTP.sent) != 1:
                    raise RuntimeError("replayed inquiry sent a duplicate notification")

                # SMTP failure keeps the inquiry accepted and logs no visitor data or secret.
                FakeSMTP.fail = True
                captured = io.StringIO()
                with redirect_stderr(captured):
                    server.send_inquiry_notification(
                        {"reference": "INQ-0123456789AB", "sender_name": "Ada", "sender_email": VISITOR_EMAIL,
                         "inquiry_type": "licensing", "project_use": "x", "message": VISITOR_MESSAGE}
                    )
                log = captured.getvalue()
                if "result=failed" not in log or VISITOR_EMAIL in log or SETTINGS["password"] in log:
                    raise RuntimeError(f"failure log is unsafe or missing: {log!r}")
    finally:
        app_server.shutdown()
        app_server.server_close()

    print("Inquiry notification acceptance passed (disabled default, send, header injection, replay, failure log).")


if __name__ == "__main__":
    main()
