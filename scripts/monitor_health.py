#!/usr/bin/env python3
"""Bounded health probes with durable incident transitions and FIFO alert retries.

Delivery is at least once: event_id remains stable if the process stops after
the remote channel accepts a notification but before local acknowledgement.
No application credentials, response bodies or probe URLs enter notifications.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import notify_offsite_failure as alerts


def probe(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlsplit(url)
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and loopback)) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise alerts.AlertError("probe_url_invalid")
    if parsed.path not in {"/healthz", "/readyz"} or (parsed.path == "/readyz" and not loopback):
        raise alerts.AlertError("probe_boundary_invalid")
    expected = {"status": "ok"} if parsed.path == "/healthz" else {"status": "ready", "dependencies": {"supabase": "available"}}
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "mt-presence-health-monitor/1"})
    opener = urllib.request.build_opener(alerts.RejectRedirects())
    try:
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                return False, "http_status"
            raw = response.read(4097)
            if len(raw) > 4096:
                return False, "response_too_large"
            if json.loads(raw) != expected:
                return False, "response_contract"
    except alerts.AlertError:
        return False, "redirect_rejected"
    except urllib.error.HTTPError:
        return False, "http_status"
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "network_error"
    except (ValueError, UnicodeError):
        return False, "invalid_json"
    return True, "healthy"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state(path: Path) -> dict:
    if path.is_symlink():
        raise alerts.AlertError("monitor_state_invalid_preserved")
    if not path.exists():
        return {"version": 1, "checks": {}, "pending": []}
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError()
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["version"] != 1 or not isinstance(state["checks"], dict) or not isinstance(state["pending"], list):
            raise ValueError()
        if len(state["pending"]) > 4096:
            raise ValueError()
        for name, entry in state["checks"].items():
            alerts.safe_unit(name)
            for counter in ("failures", "successes"):
                if type(entry[counter]) is not int or not 0 <= entry[counter] <= 100:
                    raise ValueError()
            if entry["incident"] is not None and not isinstance(entry["incident"], str):
                raise ValueError()
            if entry["incident"] is not None and not isinstance(entry.get("started_at"), str):
                raise ValueError()
        for event in state["pending"]:
            if not isinstance(event, dict):
                raise ValueError()
            for field in ("event_id", "unit", "incident_id", "started_at", "occurred_at", "host", "reason"):
                if not isinstance(event.get(field), str) or not event[field] or len(event[field]) > 256:
                    raise ValueError()
            alerts.safe_unit(event["unit"])
            alerts.safe_label(event["host"])
            if event.get("source") != "health-monitor" or type(event.get("test")) is not bool:
                raise ValueError()
            if event["event_kind"] not in {"failure", "recovery"} or len(event["event_id"]) != 64 or any(c not in "0123456789abcdef" for c in event["event_id"]):
                raise ValueError()
        return state
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise alerts.AlertError("monitor_state_invalid_preserved") from error


def transition(state: dict, check_id: str, healthy: bool, reason: str, failure_threshold: int, recovery_threshold: int, test: bool) -> None:
    entry = state["checks"].setdefault(check_id, {"failures": 0, "successes": 0, "incident": None})
    entry["failures"] = 0 if healthy else min(100, entry["failures"] + 1)
    entry["successes"] = min(100, entry["successes"] + 1) if healthy else 0
    kind = None
    if not healthy and entry["incident"] is None and entry["failures"] >= failure_threshold:
        entry["incident"] = secrets.token_hex(16)
        entry["started_at"] = timestamp()
        kind = "failure"
    elif healthy and entry["incident"] is not None and entry["successes"] >= recovery_threshold:
        kind = "recovery"
    if kind:
        if len(state["pending"]) >= 4096:
            raise alerts.AlertError("monitor_pending_capacity_reached")
        event = {
            "event_id": hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
            "event_kind": kind, "unit": check_id, "incident_id": entry["incident"],
            "started_at": entry["started_at"], "occurred_at": timestamp(),
            "host": alerts.safe_label(alerts.env("MT_OFFSITE_ALERT_HOST_LABEL", "MT Presence")),
            "source": "health-monitor", "severity": "critical" if kind == "failure" else "info",
            "reason": reason, "test": test,
        }
        state["pending"].append(event)
        if kind == "recovery":
            entry["incident"] = None
            entry.pop("started_at", None)


def deliver(event: dict) -> dict:
    body = json.dumps(event, ensure_ascii=True, indent=2, sort_keys=True)
    channels, errors = [], []
    for name, sender, key in (("smtp", alerts.send_smtp, "MT_OFFSITE_ALERT_SMTP_HOST"), ("webhook", alerts.send_webhook, "MT_OFFSITE_ALERT_WEBHOOK_URL")):
        if not alerts.env(key):
            continue
        try:
            sender(event, body)
            channels.append(name)
        except alerts.AlertError as error:
            errors.append(str(error))
    return {"status": "delivered" if channels else "failed", "channels": channels, "errors": errors or ([] if channels else ["no_channel_configured"])}


def flush_pending(root: Path, state: dict, state_path: Path) -> int:
    # Bounded batch: retries continue on the next timer without starving probes.
    for event in list(state["pending"][:8]):
        spool = alerts.write_spool(root / "events", event)
        delivery = deliver(event)
        alerts.update_spool(spool, {**event, "delivery": delivery})
        if delivery["status"] != "delivered":
            print("health_monitor_delivery=pending", file=sys.stderr)
            break
        state["pending"].pop(0)
        alerts.update_spool(state_path, state)
        print(f"health_monitor_notification={event['event_kind']} event_id={event['event_id']}")
    return 1 if state["pending"] else 0


def drain(state_dir: Path) -> int:
    root = Path(state_dir)
    if root.is_symlink() or not (root / "state.json").is_file():
        raise alerts.AlertError("monitor_directory_invalid")
    os.chmod(root, 0o700)
    lock_path = root / ".monitor.lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(root / "state.json")
        os.chmod(root / "state.json", 0o600)
        return flush_pending(root, state, root / "state.json")


def check(check_id: str, url: str, state_dir: Path, failure_threshold: int = 2, recovery_threshold: int = 2, test: bool = False, record_only: bool = False) -> int:
    check_id = alerts.safe_unit(check_id)
    if not 1 <= failure_threshold <= 100 or not 1 <= recovery_threshold <= 100:
        raise alerts.AlertError("monitor_threshold_invalid")
    root = Path(state_dir)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise alerts.AlertError("monitor_directory_invalid")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock_path = root / ".monitor.lock"
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = root / "state.json"
        state = load_state(state_path)
        started = time.monotonic()
        healthy, reason = probe(url)
        probe_ms = int((time.monotonic() - started) * 1000)
        transition(state, check_id, healthy, reason, failure_threshold, recovery_threshold, test)
        alerts.update_spool(state_path, state)
        if not record_only:
            flush_pending(root, state, state_path)
        print(f"health_monitor_check={check_id} result={reason} probe_ms={probe_ms} pending={len(state['pending'])}")
        return 0 if healthy and (record_only or not state["pending"]) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-id")
    parser.add_argument("--url")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--record-only", action="store_true", help="Queue transitions without sending; external runner must persist before draining")
    modes.add_argument("--deliver-only", action="store_true", help="Retry queued notifications without probing")
    parser.add_argument("--state-dir", default="/var/lib/mt-presence-health-monitor")
    parser.add_argument("--failure-threshold", type=int, default=2)
    parser.add_argument("--recovery-threshold", type=int, default=2)
    parser.add_argument("--test", action="store_true", help="Label isolated rehearsal notifications; does not bypass probes")
    args = parser.parse_args()
    if not args.deliver_only and (not args.check_id or not args.url):
        parser.error("--check-id and --url are required for probes")
    try:
        if args.deliver_only:
            return drain(Path(args.state_dir))
        return check(args.check_id, args.url, Path(args.state_dir), args.failure_threshold, args.recovery_threshold, args.test, args.record_only)
    except alerts.AlertError as error:
        print(f"health_monitor_failed={error}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("health_monitor_failed=configuration_or_state_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
