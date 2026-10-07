#!/usr/bin/env python3
"""Send a redacted offsite-job failure alert with a durable local audit record.

The notifier is intentionally independent from the application.  It can use a
root-only SMTP configuration and/or an HTTPS webhook, but never accepts
credentials on the command line and never includes service output in the
notification body.  A local spool record is written before any network call so
an operator can audit a failed delivery attempt.
"""

from __future__ import annotations

import argparse
import email.message
import email.utils
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SPOOL = "/var/lib/mt-presence-offsite-alerts"
MAX_WEBHOOK_RESPONSE = 1024


class AlertError(RuntimeError):
    """A stable, redacted alert failure."""


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise AlertError("webhook_redirect_rejected")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def positive_int(name: str, default: int, maximum: int) -> int:
    raw = env(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise AlertError(f"invalid_integer:{name}") from error
    if value < 0 or value > maximum:
        raise AlertError(f"invalid_integer:{name}")
    return value


def safe_unit(raw: str) -> str:
    value = raw.strip()
    if not value or len(value) > 256 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@._:-" for char in value):
        raise AlertError("invalid_unit")
    return value


def safe_label(raw: str) -> str:
    value = raw.strip()
    if not value or len(value) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AlertError("invalid_host_label")
    return value


def parse_mailbox(raw: str, name: str) -> str:
    value = raw.strip()
    parsed = email.utils.parseaddr(value)
    if parsed[1] != value or not parsed[1] or any(char in value for char in "\r\n"):
        raise AlertError(f"invalid_mailbox:{name}")
    return value


def spool_path(root: Path, event_id: str) -> Path:
    if not event_id or len(event_id) != 64:
        raise AlertError("invalid_event_id")
    return root / f"{event_id}.json"


def write_spool(root: Path, payload: dict[str, object]) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    event_id = str(payload["event_id"])
    destination = spool_path(root, event_id)
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return destination
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    return destination


def delivery_state_path(root: Path, unit: str) -> Path:
    return root / f".{hashlib.sha256(unit.encode('utf-8')).hexdigest()}.last"


def should_suppress(root: Path, unit: str, now: int, interval: int) -> bool:
    if interval == 0:
        return False
    state = delivery_state_path(root, unit)
    try:
        previous = int(state.read_text(encoding="ascii"))
    except (FileNotFoundError, ValueError):
        previous = 0
    return previous > 0 and now - previous < interval


def mark_delivered(root: Path, unit: str, now: int) -> None:
    state = delivery_state_path(root, unit)
    temporary = state.with_name(f".{state.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(str(now), encoding="ascii")
    os.chmod(temporary, 0o600)
    os.replace(temporary, state)


def update_spool(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    with temporary.open("xb") as output:
        os.chmod(temporary, 0o600)
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def send_smtp(payload: dict[str, object], body: str) -> None:
    host = env("MT_OFFSITE_ALERT_SMTP_HOST")
    port = positive_int("MT_OFFSITE_ALERT_SMTP_PORT", 465, 65535)
    security = env("MT_OFFSITE_ALERT_SMTP_SECURITY", "ssl").lower()
    username = env("MT_OFFSITE_ALERT_SMTP_USERNAME")
    password = env("MT_OFFSITE_ALERT_SMTP_PASSWORD")
    sender = parse_mailbox(env("MT_OFFSITE_ALERT_FROM"), "from")
    recipient = parse_mailbox(env("MT_OFFSITE_ALERT_RECIPIENT"), "recipient")
    if not host or not username or not password:
        raise AlertError("smtp_not_configured")
    if any(char in host for char in "\r\n"):
        raise AlertError("smtp_host_invalid")
    message = email.message.EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    subject = "Offsite alert channel test" if payload.get("test") else "Offsite job failed"
    message["Subject"] = f"[MT Presence] {subject}: {payload['unit']}"
    message.set_content(body)
    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as connection:
            connection.login(username, password)
            connection.send_message(message)
    elif security == "starttls":
        with smtplib.SMTP(host, port, timeout=15) as connection:
            connection.ehlo()
            connection.starttls(context=context)
            connection.ehlo()
            connection.login(username, password)
            connection.send_message(message)
    else:
        raise AlertError("smtp_security_invalid")


def send_webhook(payload: dict[str, object], body: str) -> None:
    raw_url = env("MT_OFFSITE_ALERT_WEBHOOK_URL")
    if not raw_url:
        raise AlertError("webhook_not_configured")
    parsed = urllib.parse.urlparse(raw_url)
    allow_loopback = env("MT_OFFSITE_ALERT_ALLOW_HTTP_LOOPBACK") == "1"
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (
        (parsed.scheme != "https" and not (allow_loopback and parsed.scheme == "http" and loopback))
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise AlertError("webhook_url_invalid")
    encoded = json.dumps({"text": body, "event": payload}, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    secret = env("MT_OFFSITE_ALERT_WEBHOOK_SECRET")
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + encoded, hashlib.sha256).hexdigest() if secret else ""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "mt-presence-offsite-alert/1",
        "X-MT-Presence-Timestamp": timestamp,
    }
    if signature:
        headers["X-MT-Presence-Signature"] = f"sha256={signature}"
    request = urllib.request.Request(raw_url, data=encoded, headers=headers, method="POST")
    opener = urllib.request.build_opener(RejectRedirects(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=15) as response:
            response.read(MAX_WEBHOOK_RESPONSE)
            if response.status < 200 or response.status >= 300:
                raise AlertError(f"webhook_http_status:{response.status}")
    except AlertError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise AlertError("webhook_delivery_failed") from error


def build_payload(unit: str, *, test: bool) -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    host = safe_label(env("MT_OFFSITE_ALERT_HOST_LABEL", socket.gethostname()))
    invocation = env("INVOCATION_ID")
    event_material = f"{host}\0{unit}\0{now}\0{invocation}".encode("utf-8")
    event_id = hashlib.sha256(event_material).hexdigest()
    return {
        "event_id": event_id,
        "occurred_at": now,
        "host": host,
        "unit": unit,
        "invocation_id": invocation or None,
        "severity": "info" if test else "critical",
        "source": "manual-alert-test" if test else "systemd-offsite-backup",
        "test": test,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("unit")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    try:
        unit = safe_unit(args.unit)
        root = Path(env("MT_OFFSITE_ALERT_SPOOL_DIR", DEFAULT_SPOOL))
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise AlertError("spool_directory_invalid")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        lock_path = root / ".notify.lock"
        with lock_path.open("a+", encoding="ascii") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            payload = build_payload(unit, test=args.test)
            spool = write_spool(root, payload)
            interval = 0 if args.test else positive_int("MT_OFFSITE_ALERT_MIN_INTERVAL_SECONDS", 900, 86400)
            suppressed = should_suppress(root, unit, int(time.time()), interval)
            if suppressed:
                payload["delivery"] = {"status": "suppressed", "channels": [], "errors": []}
                update_spool(spool, payload)
                print(f"offsite_alert_suppressed={unit}")
                return 0
            body = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
            deliveries: list[str] = []
            failures: list[str] = []
            for name, sender in (("smtp", send_smtp), ("webhook", send_webhook)):
                configured = bool(env("MT_OFFSITE_ALERT_SMTP_HOST")) if name == "smtp" else bool(env("MT_OFFSITE_ALERT_WEBHOOK_URL"))
                if not configured:
                    continue
                try:
                    sender(payload, body)
                    deliveries.append(name)
                except AlertError as error:
                    failures.append(str(error))
            if not deliveries:
                payload["delivery"] = {"status": "failed", "channels": [], "errors": failures or ["no_channel_configured"]}
                update_spool(spool, payload)
                print(f"offsite_alert_spooled={spool}", file=sys.stderr)
                if failures:
                    print("offsite_alert_delivery_failed=" + ",".join(failures), file=sys.stderr)
                else:
                    print("offsite_alert_no_channel_configured", file=sys.stderr)
                return 1
            mark_delivered(root, unit, int(time.time()))
            payload["delivery"] = {"status": "delivered", "channels": deliveries, "errors": failures}
            update_spool(spool, payload)
            print("offsite_alert_delivered=" + ",".join(deliveries))
            if failures:
                print("offsite_alert_partial_failure=" + ",".join(failures), file=sys.stderr)
            return 0
    except (AlertError, OSError, ValueError) as error:
        print(f"offsite_alert_failed={error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
