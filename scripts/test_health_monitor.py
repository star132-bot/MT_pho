#!/usr/bin/env python3
"""Isolated health monitor acceptance: loopback HTTP and mocked SMTP only."""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import smtplib
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import monitor_health as monitor
import rehearse_health_notifications as rehearsal


SECRET = "fixture-monitor-hmac-never-log"
PRIVATE_DETAIL = "fixture-private-smtp-detail-never-log"


class FixtureHandler(BaseHTTPRequestHandler):
    responses: dict[str, tuple[int, bytes]] = {}
    probes: list[str] = []
    notifications: list[tuple[int, dict[str, str], bytes]] = []
    webhook_status = HTTPStatus.NO_CONTENT

    def log_message(self, _format, *_args) -> None:
        return

    def do_GET(self) -> None:
        type(self).probes.append(self.path)
        status, body = type(self).responses.get(self.path, (HTTPStatus.NOT_FOUND, b""))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if 300 <= status < 400:
            self.send_header("Location", "/redirected-healthz")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        status = type(self).webhook_status
        type(self).notifications.append((status, dict(self.headers), body))
        self.send_response(status)
        if 300 <= status < 400:
            self.send_header("Location", "/redirected-webhook")
        self.send_header("Content-Length", "0")
        self.end_headers()


class HealthMonitorAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        temporary = self.context.enter_context(tempfile.TemporaryDirectory(prefix="mt-health-monitor-test-"))
        self.state_dir = Path(temporary) / "state"
        self.output = io.StringIO()
        self.context.enter_context(redirect_stdout(self.output))
        self.context.enter_context(redirect_stderr(self.output))
        # Never inherit a real alert recipient, credential, webhook or proxy.
        self.context.enter_context(mock.patch.dict(os.environ, {
            "MT_OFFSITE_ALERT_HOST_LABEL": "fixture-health-observer",
            "MT_OFFSITE_ALERT_WEBHOOK_URL": f"{self.origin}/webhook",
            "MT_OFFSITE_ALERT_WEBHOOK_SECRET": SECRET,
            "MT_OFFSITE_ALERT_ALLOW_HTTP_LOOPBACK": "1",
        }, clear=True))
        for transport in ("SMTP_SSL", "SMTP"):
            self.context.enter_context(mock.patch.object(
                monitor.alerts.smtplib,
                transport,
                side_effect=AssertionError("Real SMTP is forbidden in acceptance tests"),
            ))
        FixtureHandler.probes = []
        FixtureHandler.notifications = []
        FixtureHandler.webhook_status = HTTPStatus.NO_CONTENT
        FixtureHandler.responses = {
            "/healthz": (HTTPStatus.OK, b'{"status":"ok"}'),
            "/readyz": (HTTPStatus.OK, b'{"status":"ready","dependencies":{"supabase":"available"}}'),
            "/redirected-healthz": (HTTPStatus.OK, b'{"status":"ok"}'),
        }

    def tearDown(self) -> None:
        for material in (SECRET, PRIVATE_DETAIL, self.origin):
            self.assertNotIn(material, self.output.getvalue())

    def state(self) -> dict:
        return json.loads((self.state_dir / "state.json").read_text(encoding="utf-8"))

    def run_check(self, healthy: bool, check_id: str = "public-healthz", *, test: bool = True, record_only: bool = False) -> int:
        with mock.patch.object(monitor, "probe", return_value=(healthy, "healthy" if healthy else "network_error")):
            return monitor.check(check_id, f"{self.origin}/healthz", self.state_dir, test=test, record_only=record_only)

    def delivered_events(self) -> list[dict]:
        return [json.loads(body)["event"] for status, _, body in FixtureHandler.notifications if 200 <= status < 300]

    def test_probe_success_and_readyz_contract(self) -> None:
        self.assertEqual(monitor.probe(f"{self.origin}/healthz"), (True, "healthy"))
        self.assertEqual(monitor.probe(f"{self.origin}/readyz"), (True, "healthy"))
        for body in (
            b'{"status":"ok"}',
            b'{"status":"ready","dependencies":{"supabase":"unavailable"}}',
            b'{"status":"ready"}',
        ):
            with self.subTest(body=body):
                FixtureHandler.responses["/readyz"] = (HTTPStatus.OK, body)
                self.assertFalse(monitor.probe(f"{self.origin}/readyz")[0])

    def test_probe_rejects_false_success_and_oversized_body(self) -> None:
        for status, body in (
            (HTTPStatus.SERVICE_UNAVAILABLE, b'{"status":"ok"}'),
            (HTTPStatus.ACCEPTED, b'{"status":"ok"}'),
            (HTTPStatus.OK, b"<html>Sign in</html>"),
            (HTTPStatus.OK, b'{"status":"unavailable"}'),
            (HTTPStatus.OK, b'{"status":"ok","private_detail":"unexpected"}'),
            (HTTPStatus.OK, b"\xff"),
            (HTTPStatus.OK, b" " * 4097),
        ):
            with self.subTest(status=status, body_length=len(body)):
                FixtureHandler.responses["/healthz"] = (status, body)
                healthy, reason = monitor.probe(f"{self.origin}/healthz")
                self.assertFalse(healthy)
                self.assertTrue(reason)

    def test_probe_redirect_never_follows(self) -> None:
        FixtureHandler.responses["/healthz"] = (HTTPStatus.FOUND, b"")
        self.assertEqual(monitor.probe(f"{self.origin}/healthz"), (False, "redirect_rejected"))
        self.assertEqual(FixtureHandler.probes, ["/healthz"])

    def test_probe_rejects_untrusted_boundaries_before_network(self) -> None:
        for url in (
            "http://example.test/healthz",
            "https://example.test/readyz",
            "https://example.test/api/me",
            "https://fixture-user:fixture-password@example.test/healthz",
            "https://example.test/healthz?token=fixture-token",
            "https://example.test/healthz#fragment",
        ):
            with self.subTest(url=url), mock.patch.object(monitor.urllib.request, "build_opener") as opener:
                with self.assertRaises(monitor.alerts.AlertError):
                    monitor.probe(url)
                opener.assert_not_called()

    def test_probe_timeout_is_bounded_and_redacted(self) -> None:
        for failure in (TimeoutError(PRIVATE_DETAIL), urllib.error.URLError(PRIVATE_DETAIL)):
            with self.subTest(failure_type=type(failure).__name__):
                opener = mock.Mock()
                opener.open.side_effect = failure
                with mock.patch.object(monitor.urllib.request, "build_opener", return_value=opener):
                    self.assertEqual(monitor.probe("https://example.test/healthz"), (False, "network_error"))
                timeout = opener.open.call_args.kwargs["timeout"]
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 10)

    def test_incident_threshold_deduplication_and_recovery(self) -> None:
        self.assertEqual(self.run_check(True), 0)
        self.assertEqual(FixtureHandler.notifications, [])
        self.assertEqual(self.run_check(False), 1)
        self.assertEqual(FixtureHandler.notifications, [])
        self.assertEqual(self.run_check(False), 1)
        incident = self.state()["checks"]["public-healthz"]["incident"]
        self.assertTrue(incident)
        self.assertEqual([event["event_kind"] for event in self.delivered_events()], ["failure"])
        self.assertEqual(self.run_check(False), 1)
        self.assertEqual(len(self.delivered_events()), 1)
        self.assertEqual(self.state()["checks"]["public-healthz"]["incident"], incident)
        self.assertEqual(self.run_check(True), 0)
        self.assertEqual(len(self.delivered_events()), 1)
        self.assertEqual(self.run_check(True), 0)
        events = self.delivered_events()
        self.assertEqual([event["event_kind"] for event in events], ["failure", "recovery"])
        self.assertEqual({event["incident_id"] for event in events}, {incident})
        self.assertEqual(len({event["event_id"] for event in events}), 2)
        self.assertTrue(all(event["test"] and event["source"] == "health-monitor" for event in events))
        self.assertIsNone(self.state()["checks"]["public-healthz"]["incident"])
        self.assertEqual(self.run_check(True), 0)
        self.assertEqual(len(self.delivered_events()), 2)
        self.assertEqual(self.state()["pending"], [])

    def test_flapping_resets_consecutive_counts(self) -> None:
        for healthy in (False, True, False):
            self.run_check(healthy)
        self.assertEqual(FixtureHandler.notifications, [])
        self.assertEqual(self.state()["checks"]["public-healthz"]["failures"], 1)
        self.run_check(False)
        for healthy in (True, False, True):
            self.run_check(healthy)
        self.assertEqual(len(self.delivered_events()), 1)
        self.assertEqual(self.state()["checks"]["public-healthz"]["successes"], 1)
        self.run_check(True)
        self.assertEqual([event["event_kind"] for event in self.delivered_events()], ["failure", "recovery"])

    def test_failed_delivery_survives_recovery_and_retries_fifo(self) -> None:
        FixtureHandler.webhook_status = HTTPStatus.SERVICE_UNAVAILABLE
        self.run_check(False)
        self.run_check(False)
        failure = dict(self.state()["pending"][0])
        self.assertEqual(self.run_check(False), 1)
        self.assertEqual(self.state()["pending"], [failure])
        self.assertEqual(self.run_check(True), 1)
        self.assertEqual(self.run_check(True), 1)
        pending = self.state()["pending"]
        self.assertEqual([event["event_kind"] for event in pending], ["failure", "recovery"])
        self.assertEqual(pending[0], failure)
        self.assertEqual(pending[0]["incident_id"], pending[1]["incident_id"])
        self.assertIsNone(self.state()["checks"]["public-healthz"]["incident"])
        self.assertTrue(all(json.loads(body)["event"]["event_kind"] == "failure" for _, _, body in FixtureHandler.notifications))
        FixtureHandler.webhook_status = HTTPStatus.NO_CONTENT
        self.assertEqual(self.run_check(True), 0)
        self.assertEqual([event["event_id"] for event in self.delivered_events()], [event["event_id"] for event in pending])
        self.assertEqual(self.state()["pending"], [])
        audits = [json.loads(path.read_text()) for path in (self.state_dir / "events").glob("*.json")]
        self.assertEqual(len(audits), 2)
        self.assertTrue(all(event["delivery"]["status"] == "delivered" for event in audits))

    def test_record_only_checkpoint_restores_and_drains_same_events(self) -> None:
        with mock.patch.object(monitor, "deliver", side_effect=AssertionError("Recording must never deliver")):
            for healthy in (False, False, True, True):
                self.run_check(healthy, record_only=True)
        self.assertEqual(FixtureHandler.notifications, [])
        self.assertFalse((self.state_dir / "events").exists())
        checkpoint = (self.state_dir / "state.json").read_bytes()
        pending = json.loads(checkpoint)["pending"]
        self.assertEqual([event["event_kind"] for event in pending], ["failure", "recovery"])
        self.assertEqual(pending[0]["incident_id"], pending[1]["incident_id"])

        # A fresh runner receives only the durable queued checkpoint.
        restored_dir = self.state_dir.parent / "restored-runner"
        restored_dir.mkdir()
        restored_path = restored_dir / "state.json"
        restored_path.write_bytes(checkpoint)
        with mock.patch.object(monitor, "probe", side_effect=AssertionError("Draining must never probe")):
            self.assertEqual(monitor.drain(restored_dir), 0)
            self.assertEqual(monitor.drain(restored_dir), 0)
        self.assertEqual(self.delivered_events(), pending)
        self.assertEqual(json.loads(restored_path.read_text())["pending"], [])
        self.assertEqual((self.state_dir / "state.json").read_bytes(), checkpoint)
        for event in pending:
            audit = json.loads((restored_dir / "events" / f"{event['event_id']}.json").read_text())
            self.assertEqual(audit["event_id"], event["event_id"])
            self.assertEqual(audit["delivery"]["status"], "delivered")

    def test_recorded_checkpoint_failed_drain_retries_fifo_with_stable_ids(self) -> None:
        for healthy in (False, False, True, True):
            self.run_check(healthy, record_only=True)
        checkpoint = self.state()
        pending = checkpoint["pending"]
        self.assertEqual(FixtureHandler.notifications, [])
        FixtureHandler.webhook_status = HTTPStatus.SERVICE_UNAVAILABLE
        with mock.patch.object(monitor, "probe", side_effect=AssertionError("Retries must never probe")):
            for attempt_count in (1, 2):
                self.assertEqual(monitor.drain(self.state_dir), 1)
                self.assertEqual(self.state(), checkpoint)
                self.assertEqual(len(FixtureHandler.notifications), attempt_count)
                attempted = [json.loads(body)["event"] for _, _, body in FixtureHandler.notifications]
                self.assertEqual(attempted, [pending[0]] * attempt_count)
            FixtureHandler.webhook_status = HTTPStatus.NO_CONTENT
            self.assertEqual(monitor.drain(self.state_dir), 0)
        self.assertEqual(self.delivered_events(), pending)
        self.assertEqual(self.state()["pending"], [])
        for event in pending:
            audit = json.loads((self.state_dir / "events" / f"{event['event_id']}.json").read_text())
            self.assertEqual(audit["delivery"]["status"], "delivered")

    def test_rehearsal_record_only_and_resume_keep_pending_event_ids(self) -> None:
        with mock.patch.object(sys, "argv", ["rehearse_health_notifications.py", "--record-only", "--state-dir", str(self.state_dir)]):
            with mock.patch.object(monitor, "deliver", side_effect=AssertionError("Rehearsal recording must never deliver")):
                self.assertEqual(rehearsal.main(), 0)
        checkpoint = self.state()
        pending = checkpoint["pending"]
        self.assertEqual([event["event_kind"] for event in pending], ["failure", "recovery"])
        self.assertTrue(all(event["test"] for event in pending))
        self.assertEqual(pending[0]["incident_id"], pending[1]["incident_id"])
        self.assertEqual(FixtureHandler.notifications, [])
        FixtureHandler.webhook_status = HTTPStatus.SERVICE_UNAVAILABLE
        with mock.patch.object(sys, "argv", ["rehearse_health_notifications.py", "--resume", "--state-dir", str(self.state_dir)]):
            with mock.patch.object(rehearsal, "ThreadingHTTPServer", side_effect=AssertionError("Resume must never regenerate fixtures")):
                with mock.patch.object(monitor, "probe", side_effect=AssertionError("Resume must never probe")):
                    self.assertEqual(rehearsal.main(), 1)
                    self.assertEqual(self.state(), checkpoint)
                    attempted = [json.loads(body)["event"] for _, _, body in FixtureHandler.notifications]
                    self.assertEqual(attempted, [pending[0]])
                    FixtureHandler.webhook_status = HTTPStatus.NO_CONTENT
                    self.assertEqual(rehearsal.main(), 0)
                    self.assertEqual(rehearsal.main(), 0)
        self.assertEqual(self.delivered_events(), pending)
        self.assertEqual(self.state()["pending"], [])

    def test_checks_are_independent(self) -> None:
        for check_id in ("public-healthz", "provider-readyz"):
            self.run_check(False, check_id)
            self.run_check(False, check_id)
        opened = self.state()["checks"]
        self.assertNotEqual(opened["public-healthz"]["incident"], opened["provider-readyz"]["incident"])
        self.run_check(True, "public-healthz")
        self.run_check(True, "public-healthz")
        checks = self.state()["checks"]
        self.assertIsNone(checks["public-healthz"]["incident"])
        self.assertEqual(checks["provider-readyz"]["incident"], opened["provider-readyz"]["incident"])
        self.assertEqual([(event["unit"], event["event_kind"]) for event in self.delivered_events()], [
            ("public-healthz", "failure"), ("provider-readyz", "failure"), ("public-healthz", "recovery"),
        ])

    def test_state_and_audit_permissions_and_webhook_signature(self) -> None:
        self.run_check(False)
        self.run_check(False)
        self.assertEqual(self.state_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.state_dir / ".monitor.lock").stat().st_mode & 0o777, 0o600)
        for path in self.state_dir.rglob("*.json"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            serialized = path.read_text()
            for private in (SECRET, self.origin):
                self.assertNotIn(private, serialized)
        _, raw_headers, body = FixtureHandler.notifications[0]
        headers = {name.lower(): value for name, value in raw_headers.items()}
        timestamp = headers["x-mt-presence-timestamp"]
        expected = hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["x-mt-presence-signature"], f"sha256={expected}")

    def test_invalid_state_is_preserved_without_probe_or_notification(self) -> None:
        invalid_states = [
            b'{"version":',
            json.dumps({"version": 1, "checks": [], "pending": []}).encode(),
            json.dumps({"version": 1, "checks": {"public-healthz": {
                "failures": 2, "successes": 0, "incident": "a" * 32,
            }}, "pending": []}).encode(),
            json.dumps({"version": 1, "checks": {}, "pending": [{
                "event_kind": "failure", "event_id": "b" * 64,
            }]}).encode(),
        ]
        self.state_dir.mkdir()
        state_path = self.state_dir / "state.json"
        for case_number, raw in enumerate(invalid_states):
            with self.subTest(case_number=case_number):
                state_path.write_bytes(raw)
                with mock.patch.object(monitor, "probe") as probe:
                    with self.assertRaises(monitor.alerts.AlertError):
                        monitor.check("public-healthz", f"{self.origin}/healthz", self.state_dir, test=True)
                    probe.assert_not_called()
                self.assertEqual(state_path.read_bytes(), raw)
                self.assertEqual(FixtureHandler.notifications, [])

    def smtp_environment(self) -> None:
        os.environ.update({
            "MT_OFFSITE_ALERT_SMTP_HOST": "fixture-smtp.invalid",
            "MT_OFFSITE_ALERT_SMTP_PORT": "465",
            "MT_OFFSITE_ALERT_SMTP_SECURITY": "ssl",
            "MT_OFFSITE_ALERT_SMTP_USERNAME": "fixture-user",
            "MT_OFFSITE_ALERT_SMTP_PASSWORD": PRIVATE_DETAIL,
            "MT_OFFSITE_ALERT_FROM": "fixture-sender@example.test",
            "MT_OFFSITE_ALERT_RECIPIENT": "fixture-recipient@example.test",
        })

    def test_smtp_authentication_error_is_redacted_and_webhook_still_delivers(self) -> None:
        self.smtp_environment()
        smtp = mock.MagicMock()
        smtp.__enter__.return_value = smtp
        smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, PRIVATE_DETAIL.encode())
        with mock.patch.object(monitor.alerts.smtplib, "SMTP_SSL", return_value=smtp):
            self.run_check(False)
            self.run_check(False)
        smtp.login.assert_called_once()
        smtp.send_message.assert_not_called()
        self.assertEqual(len(self.delivered_events()), 1)
        self.assertEqual(self.state()["pending"], [])
        audit = json.loads(next((self.state_dir / "events").glob("*.json")).read_text())
        self.assertEqual(audit["delivery"], {
            "status": "delivered", "channels": ["webhook"], "errors": ["smtp_delivery_failed"],
        })
        self.assertNotIn(PRIVATE_DETAIL, json.dumps(audit))

    def test_webhook_redirect_remains_pending_without_following(self) -> None:
        FixtureHandler.webhook_status = HTTPStatus.FOUND
        self.run_check(False)
        self.assertEqual(self.run_check(False), 1)
        self.assertEqual(len(FixtureHandler.notifications), 1)
        self.assertEqual(len(self.state()["pending"]), 1)
        audit = json.loads(next((self.state_dir / "events").glob("*.json")).read_text())
        self.assertEqual(audit["delivery"]["errors"], ["webhook_redirect_rejected"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
