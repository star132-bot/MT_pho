#!/usr/bin/env python3
"""Send TEST failure/recovery alerts using an isolated loopback probe."""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import monitor_health


class Fixture(BaseHTTPRequestHandler):
    healthy = False

    def do_GET(self):
        body = b'{"status":"ok"}' if self.healthy else b'{"status":"unavailable"}'
        self.send_response(200 if self.healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--record-only", action="store_true")
    modes.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(args.state_dir)
    if args.resume:
        return monitor_health.drain(root)
    if (root / "state.json").exists():
        parser.error("Use a fresh rehearsal state directory")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/healthz"
    try:
        for healthy in (False, False, True, True):
            Fixture.healthy = healthy
            monitor_health.check("isolated-notification-rehearsal", url, root, test=True, record_only=args.record_only)
        if args.record_only:
            print("health_rehearsal=queued_failure_and_recovery")
            return 0
        state = monitor_health.load_state(root / "state.json")
        events = [json.loads(p.read_text()) for p in (root / "events").glob("*.json")]
        if state["pending"] or {e["event_kind"] for e in events if e.get("delivery", {}).get("status") == "delivered"} != {"failure", "recovery"}:
            print("health_rehearsal=delivery_pending")
            return 1
        print("health_rehearsal=channel_accepted_failure_and_recovery")
        print("health_rehearsal=recipient_confirmation_required")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
