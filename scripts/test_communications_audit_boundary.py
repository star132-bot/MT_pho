#!/usr/bin/env python3
"""Secret-free Communications, Audit, and public-static boundary checks."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


USER_ID = "10000000-0000-4000-8000-000000000001"
OTHER_ID = "10000000-0000-4000-8000-000000000002"
CONVERSATION_ID = "20000000-0000-4000-8000-000000000001"
MESSAGE_ID = "30000000-0000-4000-8000-000000000001"
WORK_ID = "40000000-0000-4000-8000-000000000001"
NOTIFICATION_ID = "50000000-0000-4000-8000-000000000001"
AUDIT_ID = "60000000-0000-4000-8000-000000000001"
EXPORT_ID = "70000000-0000-4000-8000-000000000001"
STAMP = "2026-07-23T08:00:00Z"


def pagination(limit: int, key: str) -> dict:
    return {"limit": limit, "has_more": False, "next_cursor": None}


def notification() -> dict:
    return {
        "id": NOTIFICATION_ID,
        "type": "conversation_reply_received",
        "message": "Recorded reply.",
        "href": f"/inbox/{CONVERSATION_ID}",
        "read_at": None,
        "created_at": STAMP,
    }


def conversation_message() -> dict:
    return {
        "id": MESSAGE_ID,
        "sender_kind": "member",
        "sender_role": "sender",
        "sender_display_name": "Sender",
        "body": "A recorded message.",
        "delivery_status": "recorded",
        "created_at": STAMP,
    }


def conversation_summary() -> dict:
    return {
        "id": CONVERSATION_ID,
        "participant_role": "recipient",
        "public_reference": "INQ-ABCDEF123456",
        "status": "open",
        "version": 2,
        "inquiry_type": "editorial",
        "organization": "Publication",
        "project_use": "Editorial image licensing",
        "timeline": None,
        "budget_range": None,
        "sender": {"kind": "member", "display_name": "Sender", "email": "sender@example.test"},
        "recipient": {"display_name": "Creator"},
        "works": [{
            "id": WORK_ID,
            "title": "Quiet Weather",
            "position": 1,
        }],
        "work_count": 1,
        "unread_count": 1,
        "last_message": conversation_message(),
        "last_message_at": STAMP,
        "created_at": STAMP,
        "updated_at": STAMP,
    }


def audit_item() -> dict:
    return {
        "id": AUDIT_ID,
        "target_type": "conversation",
        "target_id": CONVERSATION_ID,
        "actor": {"id": USER_ID, "display_name": "Administrator", "role": "admin"},
        "action": "conversation.status_closed",
        "request_id": "request:123",
        "reason_code": "user_request",
        "result": "success",
        "policy_version": "mt-communications-2026-07-v1",
        "created_at": STAMP,
    }


def assert_no_private(value: object, label: str) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for forbidden in (
        "recipient_user_id", "viewer_user_id", "initiator_user_id", "owner_user_id",
        "sender@example.test", "private-ip", "before_state", "refresh_token", "payload",
    ):
        if forbidden in serialized:
            raise RuntimeError(f"{label} leaked {forbidden}")


def main() -> None:
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "database/migrations/20260723_d_communications_audit.sql").read_text(encoding="utf-8")

    raw_notifications = {
        "items": [notification()],
        "unread_count": 1,
        "pagination": pagination(30, "created_at"),
    }
    cleaned_notifications = server.clean_notification_list_result(raw_notifications, USER_ID, 30)
    if not cleaned_notifications or set(cleaned_notifications["items"][0]) != {
        "id", "type", "title", "message", "read_at", "created_at", "href",
    }:
        raise RuntimeError("Notification projection is not fixed")
    if cleaned_notifications["items"][0]["href"] != f"/inbox/{CONVERSATION_ID}":
        raise RuntimeError("Notification href was not server-derived")
    assert_no_private(cleaned_notifications, "Notifications")
    malicious = copy.deepcopy(raw_notifications)
    malicious["items"][0]["href"] = "https://evil.example/private"
    if server.clean_notification_list_result(malicious, USER_ID, 30) is not None:
        raise RuntimeError("Provider notification href was trusted")

    raw_list = {
        "items": [conversation_summary()],
        "pagination": pagination(30, "last_message_at"),
    }
    cleaned_list = server.clean_conversation_list_result(raw_list, USER_ID, 30)
    if not cleaned_list or cleaned_list["items"][0]["unread_count"] != 1:
        raise RuntimeError("Inbox list projection failed")
    assert_no_private(cleaned_list, "Inbox list")

    raw_detail = {
        "conversation": conversation_summary(),
        "participants": [
            {"participant_role": "recipient", "display_name": "Creator", "email": "creator@example.test", "last_read_message_id": None, "last_read_at": None, "joined_at": STAMP},
            {"participant_role": "sender", "display_name": "Sender", "email": "sender@example.test", "last_read_message_id": MESSAGE_ID, "last_read_at": STAMP, "joined_at": STAMP},
        ],
        "messages": [conversation_message()],
        "pagination": pagination(100, "created_at"),
    }
    cleaned_detail = server.clean_conversation_detail_result(raw_detail, USER_ID, CONVERSATION_ID, 100)
    if not cleaned_detail or cleaned_detail["participants"][1]["email"] != "sender@example.test":
        raise RuntimeError("Participant detail email contract failed")
    invalid_detail = copy.deepcopy(raw_detail)
    invalid_detail["messages"][0]["sender_role"] = "admin"
    if server.clean_conversation_detail_result(invalid_detail, USER_ID, CONVERSATION_ID, 100) is not None:
        raise RuntimeError("Non-participant message role passed")
    if "and participant.user_id = actor_id" not in migration_source or "and viewer.user_id = $2" not in migration_source:
        raise RuntimeError("Database participant isolation predicate is missing")

    status_result = server.clean_conversation_status_result({
        "conversation_id": CONVERSATION_ID,
        "status": "closed",
        "conversation_version": 3,
        "delivery": {"record_status": "recorded", "provider_status": "not_required", "provider_action_required": False},
        "replayed": False,
    }, CONVERSATION_ID, "closed", 2)
    if not status_result or status_result["conversation_version"] != 3:
        raise RuntimeError("Conversation status CAS projection failed")

    guest_inquiry = server.clean_project_inquiry_result({
        "reference": "INQ-ABCDEF123456", "status": "received", "created_at": STAMP,
        "replayed": False, "selected_work_count": 1,
    }, None)
    if not guest_inquiry or set(guest_inquiry) != {"reference", "status", "created_at", "replayed", "selected_work_count"}:
        raise RuntimeError("Guest inquiry provider projection failed")
    guest_browser = {"reference": guest_inquiry["reference"], "status": guest_inquiry["status"]}
    if set(guest_browser) != {"reference", "status"}:
        raise RuntimeError("Guest inquiry leaked identifiers")

    roles = {"user", "admin"}
    raw_audit = {
        "actor": {"id": USER_ID, "roles": sorted(roles)},
        "items": [audit_item()],
        "pagination": pagination(50, "created_at"),
    }
    cleaned_audit = server.clean_admin_audit_list_result(raw_audit, USER_ID, roles, 50)
    if not cleaned_audit or "email" in json.dumps(cleaned_audit):
        raise RuntimeError("Audit list projection failed")
    raw_export = {
        "actor": {"id": USER_ID, "roles": sorted(roles)},
        "export": {"id": EXPORT_ID, "reason_code": "compliance_request", "created_at": STAMP, "replayed": False},
        "items": [audit_item()], "count": 1, "truncated": False, "replayed": False,
    }
    cleaned_export = server.clean_admin_audit_export_result(raw_export, USER_ID, roles, "compliance_request")
    if not cleaned_export or set(cleaned_export) != {"items", "count", "truncated", "replayed"}:
        raise RuntimeError("Audit export projection failed")
    assert_no_private(cleaned_export, "Audit export")

    public_paths = ("/index.html", "/styles.css", "/script.js")
    blocked_paths = (
        "/server.py", "/database/product_schema.sql", "/scripts/test_admin_users_boundary.py",
        "/deploy/web-environment.example", "/docs/product/user-upload-admin-spec.md", "/.git/config",
        "/.env", "/requirements-scanner.txt", "/README.md",
    )
    if not all(server.is_public_static_path(path) for path in public_paths):
        raise RuntimeError("Runtime public allowlist rejected a required file")
    if server.is_public_static_path("/assets/art/metadata.json"):
        raise RuntimeError("Non-image art metadata was public")
    for path in blocked_paths:
        if server.is_public_static_path(server.canonical_url_path(path)):
            raise RuntimeError(f"Sensitive static path was public: {path}")
    encoded = "/%64atabase/product_schema.sql"
    if server.is_public_static_path(server.canonical_url_path(encoded)):
        raise RuntimeError("Percent-encoded sensitive alias was public")
    if not all(server.is_private_static_path(path) for path in (
        "/.env", "/data/archive.db", f"/assets/uploads/{WORK_ID}/original-source.jpg",
    )):
        raise RuntimeError("Legacy private static classification regressed")

    required_source = (
        '"/workspace/notifications"', '"/api/admin/audit-logs"', '"/api/admin/audit-logs/export"',
        'def handle_inbox_status', 'def handle_admin_audit_export', 'def handle_health_get',
        'def handle_readiness_get', 'class BoundedThreadingHTTPServer', 'TRUST_REVERSE_PROXY',
        'MT_INQUIRY_RATE_LIMIT_PER_HOUR', 'set(body) != {"status", "expected_version", "idempotency_key"}',
    )
    if any(marker not in source for marker in required_source):
        raise RuntimeError("A required communications/audit boundary marker is missing")
    if "<script id=\"mt-header-identity\"" in source or not server.HEADER_IDENTITY_BOOTSTRAP_MARKER.startswith("<template"):
        raise RuntimeError("Header identity bootstrap is not CSP-safe template markup")
    if not 1 <= server.INQUIRY_EMAIL_RATE_LIMIT <= 100:
        raise RuntimeError("Inquiry email rate limit is not bounded")
    invalid_env = dict(os.environ, MT_INQUIRY_RATE_LIMIT_PER_HOUR="invalid")
    invalid_limit = subprocess.check_output(
        [sys.executable, "-c", "import server; print(server.INQUIRY_EMAIL_RATE_LIMIT)"],
        cwd=ROOT,
        env=invalid_env,
        text=True,
    ).strip()
    if invalid_limit != "5":
        raise RuntimeError("Invalid inquiry rate environment did not fail closed to the default")

    print("communications_notification_allowlist=yes")
    print("communications_notification_href_provider_trusted=no")
    print("communications_participant_isolation=yes")
    print("communications_email_list_exposed=no")
    print("communications_email_detail_only=yes")
    print("communications_status_cas_contract=yes")
    print("inquiry_guest_ids_exposed=no")
    print("admin_audit_allowlist_export=yes")
    print("public_static_sensitive_files_exposed=no")
    print("header_identity_inline_script=no")
    print("production_health_proxy_threads_routes=yes")


if __name__ == "__main__":
    main()
