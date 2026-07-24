#!/usr/bin/env python3
"""Secret-free HTTP acceptance for Admin Works governance."""

from __future__ import annotations

import base64
import copy
import http.cookiejar
import importlib
import json
import os
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PUBLISHABLE_KEY = "admin-works-test-publishable-key"
USER_ID = "10000000-0000-4000-8000-000000000071"
REVIEWER_ID = "10000000-0000-4000-8000-000000000072"
ADMIN_AAL1_ID = "10000000-0000-4000-8000-000000000073"
ADMIN_ID = "10000000-0000-4000-8000-000000000074"
SUPER_ADMIN_ID = "10000000-0000-4000-8000-000000000075"
RECOVERY_ADMIN_ID = "10000000-0000-4000-8000-000000000076"
INACTIVE_ADMIN_ID = "10000000-0000-4000-8000-000000000077"
OWNER_ID = "10000000-0000-4000-8000-000000000078"
IMAGE_ID = "20000000-0000-4000-8000-000000000071"
OTHER_IMAGE_ID = "20000000-0000-4000-8000-000000000072"
VERSION_ID = "30000000-0000-4000-8000-000000000071"
DISPLAY_ASSET_ID = "40000000-0000-4000-8000-000000000071"
THUMBNAIL_ASSET_ID = "40000000-0000-4000-8000-000000000072"
ORIGINAL_ASSET_ID = "40000000-0000-4000-8000-000000000073"
ACTION_ID = "50000000-0000-4000-8000-000000000071"
TAKEDOWN_ID = "60000000-0000-4000-8000-000000000071"
OTHER_TAKEDOWN_ID = "60000000-0000-4000-8000-000000000072"
CREATOR_SLUG = "field-notes"
GOVERNANCE_POLICY_VERSION = "mt-admin-governance-2026-07-v1"

PRIVATE_CANARIES = (
    "private-storage-key-canary",
    "private-original-canary",
    "private-internal-note-canary",
    "private-provider-detail-canary",
    "private-audit-canary",
)


def fake_access_token(user_id: str, *, aal: str = "aal1", method: str = "password") -> str:
    claims = {"sub": user_id, "aal": aal, "amr": [{"method": method}]}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


USER_TOKEN = fake_access_token(USER_ID)
REVIEWER_TOKEN = fake_access_token(REVIEWER_ID)
ADMIN_AAL1_TOKEN = fake_access_token(ADMIN_AAL1_ID)
ADMIN_TOKEN = fake_access_token(ADMIN_ID, aal="aal2", method="totp")
SUPER_ADMIN_TOKEN = fake_access_token(SUPER_ADMIN_ID, aal="aal2", method="totp")
RECOVERY_ADMIN_TOKEN = fake_access_token(RECOVERY_ADMIN_ID, aal="aal2", method="recovery")
INACTIVE_ADMIN_TOKEN = fake_access_token(INACTIVE_ADMIN_ID, aal="aal2", method="totp")

AUTHORIZATIONS = {
    USER_TOKEN: {"user_id": USER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"},
    REVIEWER_TOKEN: {"user_id": REVIEWER_ID, "account_status": "active", "roles": ["reviewer"], "aal": "aal1"},
    ADMIN_AAL1_TOKEN: {"user_id": ADMIN_AAL1_ID, "account_status": "active", "roles": ["reviewer", "admin"], "aal": "aal1"},
    ADMIN_TOKEN: {"user_id": ADMIN_ID, "account_status": "active", "roles": ["user", "admin"], "aal": "aal2"},
    SUPER_ADMIN_TOKEN: {"user_id": SUPER_ADMIN_ID, "account_status": "active", "roles": ["super_admin"], "aal": "aal2"},
    RECOVERY_ADMIN_TOKEN: {"user_id": RECOVERY_ADMIN_ID, "account_status": "active", "roles": ["admin"], "aal": "aal2"},
    INACTIVE_ADMIN_TOKEN: {"user_id": INACTIVE_ADMIN_ID, "account_status": "suspended", "roles": ["admin"], "aal": "aal2"},
}


def actor(access_token: str) -> dict:
    authorization = AUTHORIZATIONS[access_token]
    return {
        "id": authorization["user_id"],
        "roles": authorization["roles"],
        "can_govern_images": True,
        "capabilities": {"can_takedown": True, "can_restore": True},
        "provider_private": "private-provider-detail-canary",
    }


def derivative_asset(kind: str, scan_status: str = "clean") -> dict:
    if kind == "display":
        asset_id, bucket, width, height = DISPLAY_ASSET_ID, "image-display", 1800, 1200
    elif kind == "thumbnail":
        asset_id, bucket, width, height = THUMBNAIL_ASSET_ID, "image-thumbnails", 600, 400
    else:
        asset_id, bucket, width, height = ORIGINAL_ASSET_ID, "image-originals", 6000, 4000
    suffix = "private-original-canary" if kind == "original" else f"{kind}.jpg"
    scan_result_code = {
        "clean": "clean",
        "pending": "pending",
        "flagged": "policy_flagged",
        "failed": "scanner_failed",
    }[scan_status]
    return {
        "id": asset_id,
        "image_id": IMAGE_ID,
        "owner_user_id": OWNER_ID,
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": f"{OWNER_ID}/{IMAGE_ID}/{suffix}",
        "mime_type": "image/jpeg",
        "byte_size": 2048,
        "width": width,
        "height": height,
        "checksum_sha256": "a" * 64,
        "scan_status": scan_status,
        "scan_result_code": scan_result_code,
        "scan_completed_at": None if scan_status == "pending" else "2026-07-22T04:00:00Z",
        "scan_policy_version": "mt-asset-scan-2026-07-v1",
        "storage_visibility": "private" if kind == "original" else "public",
        "deleted_at": None,
        "created_at": "2026-07-20T00:00:00Z",
        "provider_private": "private-storage-key-canary",
    }


def work_summary(publication_status: str = "published") -> dict:
    return {
        "id": IMAGE_ID,
        "version": 7,
        "title": "Quiet Weather",
        "original_filename": "quiet-weather.jpg",
        "original_width": 1800,
        "original_height": 1200,
        "processing_status": "ready",
        "workflow_status": "approved",
        "publication_status": publication_status,
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-23T01:00:00Z",
        "published_at": "2026-07-22T06:00:00Z" if publication_status == "published" else None,
        "unpublished_at": "2026-07-23T01:00:00Z" if publication_status != "published" else None,
        "owner": {
            "id": OWNER_ID,
            "email": "owner@example.test",
            "display_name": "Field Notes",
            "account_status": "active",
        },
        "asset_summary": {
            "count": 3,
            "clean_count": 3,
            "flagged_count": 0,
            "failed_count": 0,
            "pending_count": 0,
        },
        "thumbnail_asset": derivative_asset("thumbnail"),
        "latest_review": {
            "submission_id": "31000000-0000-4000-8000-000000000071",
            "image_id": IMAGE_ID,
            "image_version_id": VERSION_ID,
            "status": "approved",
            "assigned_reviewer_id": REVIEWER_ID,
            "submitted_at": "2026-07-22T05:00:00Z",
            "completed_at": "2026-07-22T06:00:00Z",
            "decision": "approve_and_publish",
            "decision_at": "2026-07-22T06:00:00Z",
        },
        "latest_governance_action": None,
        "internal_note": "private-internal-note-canary",
        "provider_private": "private-provider-detail-canary",
    }


def work_detail(publication_status: str = "published") -> dict:
    return {
        **work_summary(publication_status),
        "current_version": {
            "id": VERSION_ID,
            "image_id": IMAGE_ID,
            "version_number": 3,
            "title": "Quiet Weather",
            "caption": "A clearing after rain.",
            "description": "A study of distance and low cloud.",
            "alt_text": "Low cloud above a green valley.",
            "tags": ["weather", "valley"],
            "content_category": "concrete",
            "captured_at": "2026-06-01T08:00:00Z",
            "location_name": "North valley",
            "gps_visibility": "approximate",
            "public_exif": {"camera": "MT Camera", "gps": "private-provider-detail-canary"},
            "copyright_holder": "Field Notes",
            "copyright_year": 2026,
            "contains_recognizable_people": False,
            "model_release_status": "not_applicable",
            "property_release_status": "not_applicable",
            "rights_declared": True,
            "ai_disclosure": "none",
            "sensitive_content_disclosure": "none",
            "locked_at": "2026-07-22T05:00:00Z",
            "created_at": "2026-07-20T00:00:00Z",
        },
        "original_asset": derivative_asset("original"),
        "display_asset": derivative_asset("display"),
        "thumbnail_asset": derivative_asset("thumbnail"),
        "versions": [{"id": VERSION_ID, "image_id": IMAGE_ID, "version_number": 3, "title": "Quiet Weather", "created_by_user_id": OWNER_ID, "created_at": "2026-07-20T00:00:00Z", "locked_at": "2026-07-22T05:00:00Z"}],
        "review_submissions": [{
            "id": "31000000-0000-4000-8000-000000000071",
            "image_id": IMAGE_ID,
            "image_version_id": VERSION_ID,
            "image_version_image_id": IMAGE_ID,
            "status": "approved",
            "assigned_reviewer_id": REVIEWER_ID,
            "policy_version": "review-v1",
            "lock_version": 2,
            "submitted_at": "2026-07-22T05:00:00Z",
            "review_started_at": "2026-07-22T05:15:00Z",
            "completed_at": "2026-07-22T06:00:00Z",
            "decisions": [{
                "id": "32000000-0000-4000-8000-000000000071",
                "submission_id": "31000000-0000-4000-8000-000000000071",
                "reviewer_id": REVIEWER_ID,
                "decision": "approve_and_publish",
                "reason_codes": ["policy_complete"],
                "user_message": "Approved for publication.",
                "policy_version": "review-v1",
                "created_at": "2026-07-22T06:00:00Z",
                "internal_note": "private-internal-note-canary",
            }],
        }],
        "takedowns": [],
        "governance_actions": [],
        "audit_timeline": [{
            "id": "33000000-0000-4000-8000-000000000071",
            "target_type": "image",
            "target_id": IMAGE_ID,
            "actor_user_id": ADMIN_ID,
            "actor_role": "admin",
            "action": "review.approve_and_publish",
            "request_id": "34000000-0000-4000-8000-000000000071",
            "reason_code": "policy_complete",
            "policy_version": "review-v1",
            "result": "success",
            "created_at": "2026-07-22T06:00:00Z",
            "before_state": "private-audit-canary",
        }],
    }


def public_work() -> dict:
    display = derivative_asset("display")
    thumbnail = derivative_asset("thumbnail")
    for value in (display, thumbnail):
        value.pop("owner_user_id", None)
        value.pop("byte_size", None)
        value.pop("scan_status", None)
        value.pop("scan_result_code", None)
        value.pop("scan_policy_version", None)
        value.pop("provider_private", None)
    return {
        "id": IMAGE_ID,
        "title": "Quiet Weather",
        "caption": "A clearing after rain.",
        "description": "A study of distance and low cloud.",
        "alt_text": "Low cloud above a green valley.",
        "tags": ["weather", "valley"],
        "content_category": "concrete",
        "captured_at": "2026-06-01T08:00:00Z",
        "location_name": "North valley",
        "public_exif": {"camera": "MT Camera"},
        "published_at": "2026-07-22T06:00:00Z",
        "width": 1800,
        "height": 1200,
        "ratio_code": "three_to_two",
        "ratio_label": "3:2",
        "creator": {"slug": CREATOR_SLUG, "display_name": "Field Notes"},
        "display_asset": display,
        "thumbnail_asset": thumbnail,
    }


def public_creator() -> dict:
    work = public_work()
    return {
        "slug": CREATOR_SLUG,
        "display_name": "Field Notes",
        "professional_headline": "Editorial photographer",
        "company": None,
        "city": "Hangzhou",
        "country_code": "CN",
        "bio": "Photographs about weather and place.",
        "website_url": None,
        "availability_status": "limited",
        "instagram_url": None,
        "linkedin_url": None,
        "avatar_url": None,
        "cover_asset": copy.deepcopy(work["display_asset"]),
        "works": [work],
        "work_count": 1,
    }


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    published = True
    admin_calls: list[tuple[str, dict, str]] = []
    public_calls: list[tuple[str, dict, str]] = []
    storage_calls: list[tuple[str, dict, str]] = []
    mutation_payloads: dict[str, dict] = {}
    mutation_results: dict[str, dict] = {}
    mutation_writes = 0
    next_admin_status: int | None = None
    next_admin_error: str | None = None
    unsafe_asset = False
    non_ready_item = False
    derivative_scan_status: str | None = None
    next_storage_url_drift = False
    next_admin_read_drift: str | None = None
    next_mutation_drift: str | None = None

    def log_message(self, _format, *_args) -> None:
        return

    def access_token(self) -> str:
        return self.headers.get("Authorization", "").removeprefix("Bearer ")

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        access_token = self.access_token()
        if self.path == "/auth/v1/user" and access_token in AUTHORIZATIONS:
            user_id = AUTHORIZATIONS[access_token]["user_id"]
            self.send_json(HTTPStatus.OK, {
                "id": user_id,
                "email": f"{user_id[-1]}@example.test",
                "email_confirmed_at": "2026-07-20T00:00:00Z",
                "factors": [],
            })
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        access_token = self.access_token()
        body = self.body()
        if self.path == "/rest/v1/rpc/current_authorization":
            authorization = AUTHORIZATIONS.get(access_token)
            self.send_json(HTTPStatus.OK if authorization else HTTPStatus.UNAUTHORIZED, authorization or {})
            return

        if self.path.startswith("/storage/v1/object/sign/"):
            type(self).storage_calls.append((self.path, copy.deepcopy(body), access_token))
            if type(self).next_storage_url_drift:
                type(self).next_storage_url_drift = False
                self.send_json(HTTPStatus.OK, {
                    "signedURL": f"/object/sign/image-originals/{OWNER_ID}/{OTHER_IMAGE_ID}/original.jpg?token=drift",
                })
                return
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=admin-works-signed"})
            return

        if self.path in {
            "/rest/v1/rpc/get_public_works",
            "/rest/v1/rpc/get_public_creator",
            "/rest/v1/rpc/get_public_creator_avatar",
        }:
            type(self).public_calls.append((self.path, copy.deepcopy(body), access_token))
            if access_token != PUBLISHABLE_KEY:
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            if self.path.endswith("get_public_works"):
                payload = {"items": [public_work()], "count": 1} if type(self).published else {"items": [], "count": 0}
            elif self.path.endswith("get_public_creator_avatar"):
                payload = {}
            else:
                payload = public_creator() if type(self).published else {}
            self.send_json(HTTPStatus.OK, payload)
            return

        if not self.path.startswith("/rest/v1/rpc/admin_"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return

        type(self).admin_calls.append((self.path, copy.deepcopy(body), access_token))
        if type(self).next_admin_status is not None:
            status = type(self).next_admin_status
            type(self).next_admin_status = None
            self.send_json(status, {"message": "private-provider-detail-canary"})
            return
        if type(self).next_admin_error is not None:
            code = type(self).next_admin_error
            type(self).next_admin_error = None
            self.send_json(HTTPStatus.OK, {"error": {"code": code, "message": "Stable provider error."}})
            return
        if access_token not in {ADMIN_TOKEN, SUPER_ADMIN_TOKEN}:
            self.send_json(HTTPStatus.FORBIDDEN, {})
            return

        if self.path == "/rest/v1/rpc/admin_list_images":
            item = work_summary("published" if type(self).published else "quarantined")
            if type(self).next_admin_read_drift == "list_latest_action_image_id":
                item["latest_governance_action"] = {
                    "id": ACTION_ID,
                    "image_id": OTHER_IMAGE_ID,
                    "actor_user_id": ADMIN_ID,
                    "actor_role": "admin",
                    "action": "unpublish",
                    "reason_code": "privacy",
                    "policy_version": GOVERNANCE_POLICY_VERSION,
                    "created_at": "2026-07-23T02:00:00Z",
                }
                type(self).next_admin_read_drift = None
            elif type(self).next_admin_read_drift == "list_latest_review_image_id":
                item["latest_review"]["image_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            if type(self).unsafe_asset:
                item["thumbnail_asset"] = derivative_asset("original")
            elif type(self).derivative_scan_status:
                item["thumbnail_asset"] = derivative_asset("thumbnail", type(self).derivative_scan_status)
            if type(self).non_ready_item:
                item["processing_status"] = "pending"
                item["original_width"] = None
                item["original_height"] = None
            status_filter = body.get("status_filter", "all")
            matches_status = status_filter == "all" or item["publication_status"] == status_filter
            total = int(matches_status)
            offset = body.get("page_offset", 0)
            result = {
                "actor": actor(access_token),
                "items": [item] if matches_status and offset == 0 else [],
                "counts": {
                    "all": 1,
                    "never_published": 0,
                    "published": int(type(self).published),
                    "unpublished": 0,
                    "quarantined": int(not type(self).published),
                    "archived": 0,
                    "deleted": 0,
                },
                "pagination": {
                    "total": total,
                    "limit": body.get("page_size", 30),
                    "offset": offset,
                    "has_more": False,
                },
                "provider_private": "private-provider-detail-canary",
            }
            self.send_json(HTTPStatus.OK, result)
            return

        if self.path == "/rest/v1/rpc/admin_get_image":
            work = work_detail("published" if type(self).published else "quarantined")
            drift = type(self).next_admin_read_drift
            if drift == "detail_action_image_id":
                work["governance_actions"] = [{
                    "id": ACTION_ID,
                    "image_id": OTHER_IMAGE_ID,
                    "actor_user_id": ADMIN_ID,
                    "actor_role": "admin",
                    "action": "unpublish",
                    "reason_code": "privacy",
                    "policy_version": GOVERNANCE_POLICY_VERSION,
                    "created_at": "2026-07-23T02:00:00Z",
                }]
                type(self).next_admin_read_drift = None
            elif drift == "detail_current_version_image_id":
                work["current_version"]["image_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_version_image_id":
                work["versions"][0]["image_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_submission_image_id":
                work["review_submissions"][0]["image_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_submission_version_image_id":
                work["review_submissions"][0]["image_version_image_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_decision_submission_id":
                work["review_submissions"][0]["decisions"][0]["submission_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_latest_review_submission_id":
                work["latest_review"]["submission_id"] = "31000000-0000-4000-8000-000000000072"
                type(self).next_admin_read_drift = None
            elif drift == "detail_audit_target_id":
                work["audit_timeline"][0]["target_id"] = OTHER_IMAGE_ID
                type(self).next_admin_read_drift = None
            elif drift == "detail_audit_target_type":
                work["audit_timeline"][0]["target_type"] = "user"
                type(self).next_admin_read_drift = None
            if type(self).unsafe_asset:
                work["display_asset"] = derivative_asset("thumbnail")
            elif type(self).derivative_scan_status:
                work["display_asset"] = derivative_asset("display", type(self).derivative_scan_status)
                work["thumbnail_asset"] = derivative_asset("thumbnail", type(self).derivative_scan_status)
            result = {
                "actor": actor(access_token),
                "work": work,
                "provider_private": "private-provider-detail-canary",
            }
            self.send_json(HTTPStatus.OK, result)
            return

        if self.path == "/rest/v1/rpc/admin_govern_image":
            key = str(body.get("idempotency_key") or "")
            if key in type(self).mutation_results:
                if type(self).mutation_payloads[key] != body:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT",
                        "message": "This key was already used with different governance data.",
                    }})
                    return
                replay = copy.deepcopy(type(self).mutation_results[key])
                replay["replayed"] = True
                self.send_json(HTTPStatus.OK, replay)
                return
            expected_version = body.get("target_expected_version", body.get("expected_version"))
            if expected_version == 999:
                self.send_json(HTTPStatus.OK, {"error": {"code": "ADMIN_IMAGE_VERSION_CONFLICT", "message": "Reload."}})
                return
            action_code = body.get("action_code", body.get("action"))
            if action_code == "restore":
                type(self).published = True
                publication_status = "published"
            else:
                type(self).published = False
                publication_status = "quarantined" if action_code == "takedown" else "unpublished"
            reason = body.get("submitted_reason_code", body.get("reason_code"))
            actor_role = "super_admin" if "super_admin" in AUTHORIZATIONS[access_token]["roles"] else "admin"
            result = {
                "actor": actor(access_token),
                "action": {
                    "id": ACTION_ID,
                    "image_id": IMAGE_ID,
                    "actor_user_id": AUTHORIZATIONS[access_token]["user_id"],
                    "actor_role": actor_role,
                    "action": action_code,
                    "reason_code": reason,
                    "user_message": body.get("submitted_user_message", body.get("public_message")),
                    "expected_image_version": int(expected_version or 7),
                    "policy_version": GOVERNANCE_POLICY_VERSION,
                    "created_at": "2026-07-23T02:00:00Z",
                    "takedown_case_id": TAKEDOWN_ID,
                    "internal_note": "private-internal-note-canary",
                },
                "work": {
                    **work_summary(publication_status),
                    "version": int(expected_version or 7) + 1,
                    "latest_governance_action": {
                        "id": ACTION_ID,
                        "image_id": IMAGE_ID,
                        "action": action_code,
                        "reason_code": reason,
                        "actor_user_id": AUTHORIZATIONS[access_token]["user_id"],
                        "actor_role": actor_role,
                        "policy_version": GOVERNANCE_POLICY_VERSION,
                        "created_at": "2026-07-23T02:00:00Z",
                    },
                },
                "takedown": {
                    "id": TAKEDOWN_ID,
                    "image_id": IMAGE_ID,
                    "status": "restored" if action_code == "restore" else "open",
                    "reason_code": reason,
                    "public_message": body.get("submitted_user_message", body.get("public_message")),
                    "assigned_admin_id": AUTHORIZATIONS[access_token]["user_id"],
                    "legal_hold": False,
                    "created_at": "2026-07-23T02:00:00Z",
                    "internal_note": "private-internal-note-canary",
                },
                "replayed": False,
                "notification": {"payload": "private-internal-note-canary"},
                "audit": {"before_state": "private-audit-canary"},
            }
            drift = type(self).next_mutation_drift
            type(self).next_mutation_drift = None
            if drift == "reason_code":
                result["action"]["reason_code"] = "privacy"
            elif drift == "user_message":
                result["action"]["user_message"] = "A different public message."
            elif drift == "expected_image_version":
                result["action"]["expected_image_version"] = int(expected_version or 7) + 1
            elif drift == "actor_user_id":
                result["action"]["actor_user_id"] = SUPER_ADMIN_ID
            elif drift == "action_image_id":
                result["action"]["image_id"] = OTHER_IMAGE_ID
            elif drift == "latest_actor_user_id":
                result["work"]["latest_governance_action"]["actor_user_id"] = SUPER_ADMIN_ID
            elif drift == "latest_action":
                result["work"]["latest_governance_action"]["action"] = "restore"
            elif drift == "latest_reason_code":
                result["work"]["latest_governance_action"]["reason_code"] = "privacy"
            elif drift == "takedown_image_id":
                result["takedown"]["image_id"] = OTHER_IMAGE_ID
            elif drift == "takedown_case_id":
                result["action"]["takedown_case_id"] = OTHER_TAKEDOWN_ID
            type(self).mutation_payloads[key] = copy.deepcopy(body)
            type(self).mutation_results[key] = copy.deepcopy(result)
            type(self).mutation_writes += 1
            self.send_json(HTTPStatus.OK, result)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {})


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        return None


class CookieOpener:
    def __init__(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            RejectRedirects(),
        )

    def open(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._opener.open(*args, **kwargs)

    def set_cookie(self, name: str, value: str) -> None:
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain="127.0.0.1", domain_specified=False, domain_initial_dot=False,
            path="/", path_specified=True, secure=False, expires=None, discard=True,
            comment=None, comment_url=None, rest={"HttpOnly": None}, rfc2109=False,
        ))


def request(
    opener: CookieOpener,
    base_url: str,
    path: str,
    *,
    payload: object | None = None,
    origin: str | None = None,
    method: str | None = None,
    content_type: str = "application/json",
) -> tuple[int, dict, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "MT Admin Works boundary test"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = content_type
        csrf = next((cookie.value for cookie in opener.cookie_jar if cookie.name.endswith("mt_csrf_token")), "")
        if csrf:
            headers["X-CSRF-Token"] = csrf
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with opener.open(req, timeout=10) as response:
            raw = response.read()
            parsed = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        parsed = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else {}
        return error.code, parsed, error.headers


def session(base_url: str, access_token: str, *, csrf: bool = True) -> CookieOpener:
    opener = CookieOpener()
    opener.set_cookie("mt_access_token", access_token)
    if csrf:
        status, result, _ = request(opener, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not result.get("csrf_token"):
            raise RuntimeError("Could not initialize CSRF for an Admin Works test session")
    return opener


def error_code(result: dict) -> str:
    return str(result.get("error", {}).get("code") or "")


def mutation_body(key: str, action: str, *, expected_version: int = 7, reason_code: str | None = None) -> dict:
    reasons = {"takedown": "copyright", "restore": "appeal_upheld"}
    return {
        "expected_version": expected_version,
        "idempotency_key": key,
        "reason_code": reason_code or reasons[action],
        "public_message": "This work was removed under the published policy.",
        "internal_note": "Operations reference 2026-07-23.",
    }


def assert_no_sensitive(payload: object, label: str) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    if any(canary in serialized for canary in PRIVATE_CANARIES):
        raise RuntimeError(f"{label} leaked a private provider value")
    lowered = serialized.lower()
    for forbidden_key in ('"storage_bucket"', '"storage_key"', '"internal_note"'):
        if forbidden_key in lowered:
            raise RuntimeError(f"{label} leaked forbidden field {forbidden_key}")
    if '"kind": "original"' in lowered or "image-originals" in lowered:
        raise RuntimeError(f"{label} exposed an original asset")


def assert_work_owner_allowlist(work: object, label: str) -> None:
    owner = work.get("owner") if isinstance(work, dict) else None
    expected_keys = {"display_name", "email", "account_status"}
    if not isinstance(owner, dict) or set(owner) != expected_keys:
        raise RuntimeError(f"{label} owner DTO escaped its exact allowlist: {owner}")


def assert_latest_review_allowlist(work: object, label: str) -> None:
    latest_review = work.get("latest_review") if isinstance(work, dict) else None
    expected_keys = {
        "submission_id",
        "status",
        "decision",
        "submitted_at",
        "completed_at",
        "decision_at",
        "assigned_reviewer_id",
    }
    if not isinstance(latest_review, dict) or set(latest_review) != expected_keys:
        raise RuntimeError(f"{label} latest-review DTO escaped its exact allowlist: {latest_review}")


def assert_denied_without_provider(
    opener: CookieOpener,
    base_url: str,
    expected_status: int,
    expected_code: str,
    label: str,
) -> None:
    before = len(FakeSupabaseHandler.admin_calls)
    status, result, _ = request(opener, base_url, "/api/admin/works")
    if status != expected_status or error_code(result) != expected_code:
        raise RuntimeError(f"{label} did not fail closed: {status} {result}")
    if len(FakeSupabaseHandler.admin_calls) != before:
        raise RuntimeError(f"{label} reached the Admin Works provider")


def main() -> None:
    temp_site = tempfile.TemporaryDirectory(prefix="mt-admin-works-boundary-")
    temp_root = Path(temp_site.name)
    for name in ("admin-works.html", "admin-works.js"):
        (temp_root / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")

    FakeSupabaseHandler.published = True
    FakeSupabaseHandler.admin_calls = []
    FakeSupabaseHandler.public_calls = []
    FakeSupabaseHandler.storage_calls = []
    FakeSupabaseHandler.mutation_payloads = {}
    FakeSupabaseHandler.mutation_results = {}
    FakeSupabaseHandler.mutation_writes = 0
    FakeSupabaseHandler.next_admin_status = None
    FakeSupabaseHandler.next_admin_error = None
    FakeSupabaseHandler.unsafe_asset = False
    FakeSupabaseHandler.non_ready_item = False
    FakeSupabaseHandler.derivative_scan_status = None
    FakeSupabaseHandler.next_storage_url_drift = False
    FakeSupabaseHandler.next_admin_read_drift = None
    FakeSupabaseHandler.next_mutation_drift = None
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = PUBLISHABLE_KEY
    os.environ["MT_PUBLIC_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")

    class CapturingAppHandler(app.MTRequestHandler):
        captured_logs: list[str] = []

        def log_message(self, format_string: str, *args) -> None:
            type(self).captured_logs.append(format_string % args)

    application = ThreadingHTTPServer(("127.0.0.1", 0), partial(CapturingAppHandler, directory=str(temp_root)))
    threading.Thread(target=application.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{application.server_address[1]}"

    try:
        anonymous = CookieOpener()
        status, _, headers = request(anonymous, base_url, "/admin/works")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/sign-in?next=%2Fadmin%2Fworks":
            raise RuntimeError("Anonymous Admin Works page did not preserve its canonical next route")
        status, result, _ = request(anonymous, base_url, "/api/admin/works")
        if status != HTTPStatus.UNAUTHORIZED or error_code(result) != "AUTH_REQUIRED":
            raise RuntimeError("Anonymous caller reached Admin Works data")
        status, _, headers = request(anonymous, base_url, "/api/admin/works", method="HEAD")
        if status != HTTPStatus.NOT_FOUND or headers.get("Cache-Control") != "no-store":
            raise RuntimeError("HEAD disclosed the protected Admin Works API")

        member = session(base_url, USER_TOKEN)
        reviewer = session(base_url, REVIEWER_TOKEN)
        admin_aal1 = session(base_url, ADMIN_AAL1_TOKEN)
        recovery = session(base_url, RECOVERY_ADMIN_TOKEN)
        inactive = session(base_url, INACTIVE_ADMIN_TOKEN)
        assert_denied_without_provider(member, base_url, HTTPStatus.FORBIDDEN, "ADMIN_REQUIRED", "Ordinary user")
        assert_denied_without_provider(reviewer, base_url, HTTPStatus.FORBIDDEN, "ADMIN_REQUIRED", "Reviewer")
        assert_denied_without_provider(admin_aal1, base_url, HTTPStatus.FORBIDDEN, "MFA_REQUIRED", "Admin AAL1")
        assert_denied_without_provider(recovery, base_url, HTTPStatus.FORBIDDEN, "RECOVERY_SESSION_RESTRICTED", "Recovery Admin")
        assert_denied_without_provider(inactive, base_url, HTTPStatus.FORBIDDEN, "ACCOUNT_RESTRICTED", "Inactive Admin")

        status, _, headers = request(recovery, base_url, "/admin/works")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/reset-password":
            raise RuntimeError("Recovery Admin opened the Admin Works page")
        status, _, headers = request(admin_aal1, base_url, "/admin/works")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/mfa?next=%2Fadmin%2Fworks":
            raise RuntimeError("Admin AAL1 page did not preserve its MFA next route")

        admin = session(base_url, ADMIN_TOKEN)
        super_admin = session(base_url, SUPER_ADMIN_TOKEN)
        for opener, label in ((admin, "Admin"), (super_admin, "Super Admin")):
            page_status, _, page_headers = request(opener, base_url, "/admin/works")
            if page_status != HTTPStatus.OK or "no-store" not in (page_headers.get("Cache-Control") or ""):
                raise RuntimeError(f"{label} could not open the protected Admin Works page")
            status, result, headers = request(opener, base_url, "/api/admin/works")
            if status != HTTPStatus.OK or set(result) != {"actor", "items", "counts", "pagination"}:
                raise RuntimeError(f"{label} could not load the strict Admin Works list")
            if headers.get("Cache-Control") != "no-store":
                raise RuntimeError("Admin Works list was cacheable")
            assert_no_sensitive(result, f"{label} list")
            if len(result.get("items", [])) != 1 or not result["items"][0].get("thumbnail", {}).get("signed_url"):
                raise RuntimeError("Admin Works list did not return its signed current thumbnail")
            assert_work_owner_allowlist(result["items"][0], f"{label} list")
            assert_latest_review_allowlist(result["items"][0], f"{label} list")

        FakeSupabaseHandler.non_ready_item = True
        status, pending_result, _ = request(admin, base_url, "/api/admin/works")
        FakeSupabaseHandler.non_ready_item = False
        pending_item = (pending_result.get("items") or [{}])[0]
        if (
            status != HTTPStatus.OK
            or pending_item.get("processing_status") != "pending"
            or pending_item.get("original_width") is not None
            or pending_item.get("original_height") is not None
        ):
            raise RuntimeError("A non-ready Admin Work with unknown dimensions was rejected")

        filtered_path = "/api/admin/works?q=Quiet&status=published&sort=updated_desc&limit=20&offset=40"
        status, result, _ = request(admin, base_url, filtered_path)
        if status != HTTPStatus.OK:
            raise RuntimeError("Admin Works filters were rejected")
        provider_payload = FakeSupabaseHandler.admin_calls[-1][1]
        expected_filters = {
            "search_query": "Quiet",
            "status_filter": "published",
            "sort_code": "updated_desc",
            "page_size": 20,
            "page_offset": 40,
        }
        if any(provider_payload.get(key) != value for key, value in expected_filters.items()):
            raise RuntimeError(f"Admin Works filters changed before the RPC: {provider_payload}")
        if result.get("pagination", {}).get("limit") != 20 or result.get("pagination", {}).get("offset") != 40:
            raise RuntimeError("Admin Works pagination DTO drifted")

        for invalid_path in (
            "/api/admin/works?status=unknown",
            "/api/admin/works?sort=drop_table",
            "/api/admin/works?limit=0",
            "/api/admin/works?offset=-1",
            "/api/admin/works?q=" + ("x" * 201),
        ):
            before = len(FakeSupabaseHandler.admin_calls)
            status, result, _ = request(admin, base_url, invalid_path)
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(result) != "ADMIN_FILTER_INVALID":
                raise RuntimeError(f"Invalid Admin Works filter did not fail closed: {invalid_path}")
            if len(FakeSupabaseHandler.admin_calls) != before:
                raise RuntimeError("Invalid Admin Works filter reached the provider")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        FakeSupabaseHandler.next_admin_read_drift = "list_latest_action_image_id"
        status, result, _ = request(admin, base_url, "/api/admin/works")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
            raise RuntimeError("Cross-image latest governance action did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Cross-image latest governance action reached preview signing")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        FakeSupabaseHandler.next_admin_read_drift = "list_latest_review_image_id"
        status, result, _ = request(admin, base_url, "/api/admin/works")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
            raise RuntimeError("Cross-image latest review did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Cross-image latest review reached preview signing")

        FakeSupabaseHandler.next_storage_url_drift = True
        status, result, _ = request(admin, base_url, "/api/admin/works")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_ASSET_UNAVAILABLE":
            raise RuntimeError("Admin Works accepted a signed URL for another Storage object")
        assert_no_sensitive(result, "Admin Works signed URL path drift")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        FakeSupabaseHandler.unsafe_asset = True
        status, result, _ = request(admin, base_url, "/api/admin/works")
        FakeSupabaseHandler.unsafe_asset = False
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
            raise RuntimeError("Unsafe Admin Works thumbnail descriptor did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Unsafe Admin Works thumbnail was signed before validation")

        for scan_status in ("pending", "flagged", "failed"):
            FakeSupabaseHandler.derivative_scan_status = scan_status
            signs_before = len(FakeSupabaseHandler.storage_calls)
            status, scan_list, _ = request(admin, base_url, "/api/admin/works")
            scan_item = (scan_list.get("items") or [{}])[0]
            if status != HTTPStatus.OK or scan_item.get("thumbnail", "missing") is not None:
                raise RuntimeError(f"Admin Works list did not suppress a {scan_status} thumbnail preview")
            status, scan_detail, _ = request(admin, base_url, f"/api/admin/works/{IMAGE_ID}")
            scan_work = scan_detail.get("work") or {}
            if (
                status != HTTPStatus.OK
                or scan_work.get("display", "missing") is not None
                or scan_work.get("thumbnail", "missing") is not None
            ):
                raise RuntimeError(f"Admin Work Detail did not suppress {scan_status} derivative previews")
            if len(FakeSupabaseHandler.storage_calls) != signs_before:
                raise RuntimeError(f"Admin Works signed a {scan_status} derivative")
            assert_no_sensitive(scan_list, f"Admin Works {scan_status} list")
            assert_no_sensitive(scan_detail, f"Admin Works {scan_status} detail")
        FakeSupabaseHandler.derivative_scan_status = None

        signs_before = len(FakeSupabaseHandler.storage_calls)
        FakeSupabaseHandler.unsafe_asset = True
        status, result, _ = request(admin, base_url, f"/api/admin/works/{IMAGE_ID}")
        FakeSupabaseHandler.unsafe_asset = False
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
            raise RuntimeError("Cross-kind Admin Work Detail derivative did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Cross-kind Admin Work Detail derivative was signed before validation")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        FakeSupabaseHandler.next_admin_read_drift = "detail_action_image_id"
        status, result, _ = request(admin, base_url, f"/api/admin/works/{IMAGE_ID}")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
            raise RuntimeError("Cross-image governance history action did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Cross-image governance history action reached preview signing")

        detail_relationship_drifts = (
            ("detail_current_version_image_id", "current version"),
            ("detail_version_image_id", "version history"),
            ("detail_submission_image_id", "review submission"),
            ("detail_submission_version_image_id", "review submission version"),
            ("detail_decision_submission_id", "review decision"),
            ("detail_latest_review_submission_id", "latest review"),
            ("detail_audit_target_id", "audit target"),
            ("detail_audit_target_type", "audit target type"),
        )
        for drift, label in detail_relationship_drifts:
            signs_before = len(FakeSupabaseHandler.storage_calls)
            FakeSupabaseHandler.next_admin_read_drift = drift
            status, result, _ = request(admin, base_url, f"/api/admin/works/{IMAGE_ID}")
            if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "ADMIN_WORKS_PROVIDER_FAILED":
                raise RuntimeError(f"Cross-record {label} did not fail closed")
            if len(FakeSupabaseHandler.storage_calls) != signs_before:
                raise RuntimeError(f"Cross-record {label} reached preview signing")

        status, result, _ = request(admin, base_url, f"/api/admin/works/{IMAGE_ID}")
        if status != HTTPStatus.OK or set(result) != {"actor", "work"}:
            raise RuntimeError("Admin Work Detail did not return its strict envelope")
        assert_no_sensitive(result, "Admin Work Detail")
        work = result.get("work", {})
        assert_work_owner_allowlist(work, "Admin Work Detail")
        assert_latest_review_allowlist(work, "Admin Work Detail")
        if not work.get("display", {}).get("signed_url") or not work.get("thumbnail", {}).get("signed_url"):
            raise RuntimeError("Admin Work Detail did not sign the clean display/thumbnail pair")
        recent_sign_paths = [path for path, _, _ in FakeSupabaseHandler.storage_calls[-2:]]
        if any("original" in unquote(path).lower() for path in recent_sign_paths):
            raise RuntimeError("Admin Work Detail signed an original asset")

        no_csrf = session(base_url, ADMIN_TOKEN, csrf=False)
        calls_before = len(FakeSupabaseHandler.admin_calls)
        status, result, _ = request(
            no_csrf,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/takedown",
            payload=mutation_body("70000000-0000-4000-8000-000000000071", "takedown"),
            origin=base_url,
        )
        if status != HTTPStatus.FORBIDDEN or error_code(result) != "CSRF_REJECTED":
            raise RuntimeError("Admin Works mutation accepted a missing CSRF token")
        if len(FakeSupabaseHandler.admin_calls) != calls_before:
            raise RuntimeError("CSRF-rejected Admin Works mutation reached the provider")

        status, result, _ = request(
            admin,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/takedown",
            payload=mutation_body("70000000-0000-4000-8000-000000000072", "takedown"),
            origin=base_url,
            content_type="text/plain",
        )
        if status != HTTPStatus.UNSUPPORTED_MEDIA_TYPE or error_code(result) != "CONTENT_TYPE_INVALID":
            raise RuntimeError("Admin Works mutation accepted a non-JSON content type")

        invalid_mutations = (
            {**mutation_body("bad-key", "takedown")},
            {**mutation_body("70000000-0000-4000-8000-000000000073", "takedown"), "unexpected": True},
            {**mutation_body("70000000-0000-4000-8000-000000000074", "takedown"), "reason_code": "appeal_upheld"},
            {**mutation_body("70000000-0000-4000-8000-000000000075", "takedown"), "expected_version": 0},
        )
        for invalid in invalid_mutations:
            before = len(FakeSupabaseHandler.admin_calls)
            status, result, _ = request(
                admin, base_url, f"/api/admin/works/{IMAGE_ID}/takedown", payload=invalid, origin=base_url,
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error_code(result) != "ADMIN_GOVERNANCE_VALIDATION_FAILED":
                raise RuntimeError("Invalid Admin Works mutation did not fail closed")
            if len(FakeSupabaseHandler.admin_calls) != before:
                raise RuntimeError("Invalid Admin Works mutation reached the provider")

        mutation_drifts = (
            "reason_code",
            "user_message",
            "expected_image_version",
            "actor_user_id",
            "action_image_id",
            "latest_actor_user_id",
            "latest_action",
            "latest_reason_code",
            "takedown_image_id",
            "takedown_case_id",
        )
        for index, drift in enumerate(mutation_drifts, start=79):
            FakeSupabaseHandler.next_mutation_drift = drift
            signs_before = len(FakeSupabaseHandler.storage_calls)
            status, drifted, _ = request(
                admin,
                base_url,
                f"/api/admin/works/{IMAGE_ID}/takedown",
                payload=mutation_body(f"70000000-0000-4000-8000-{index:012d}", "takedown"),
                origin=base_url,
            )
            if status != HTTPStatus.BAD_GATEWAY or error_code(drifted) != "ADMIN_WORKS_PROVIDER_FAILED":
                raise RuntimeError(f"Admin Works accepted provider mutation drift: {drift}")
            if len(FakeSupabaseHandler.storage_calls) != signs_before:
                raise RuntimeError(f"Admin Works signed a thumbnail before rejecting provider drift: {drift}")
            assert_no_sensitive(drifted, f"Admin Works provider mutation drift ({drift})")
            FakeSupabaseHandler.published = True

        FakeSupabaseHandler.mutation_payloads = {}
        FakeSupabaseHandler.mutation_results = {}
        FakeSupabaseHandler.mutation_writes = 0

        takedown_key = "70000000-0000-4000-8000-000000000076"
        takedown_payload = mutation_body(takedown_key, "takedown")
        status, result, _ = request(
            admin, base_url, f"/api/admin/works/{IMAGE_ID}/takedown", payload=takedown_payload, origin=base_url,
        )
        if (
            status != HTTPStatus.OK
            or set(result) != {"actor", "action", "replayed", "work", "takedown"}
            or result.get("work", {}).get("publication_status") != "quarantined"
            or result.get("action", {}).get("reason_code") != "copyright"
        ):
            raise RuntimeError(f"Admin Takedown result drifted: {result}")
        assert_no_sensitive(result, "Admin Takedown result")
        assert_work_owner_allowlist(result.get("work"), "Admin Takedown result")
        assert_latest_review_allowlist(result.get("work"), "Admin Takedown result")
        if FakeSupabaseHandler.mutation_writes != 1:
            raise RuntimeError("Admin Takedown did not produce exactly one governance write")

        status, works_result, _ = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.OK or works_result.get("items") != [] or works_result.get("count") != 0:
            raise RuntimeError("Takedown did not immediately remove the work from anonymous Works")
        status, creator_result, _ = request(anonymous, base_url, f"/api/public/creators/{CREATOR_SLUG}")
        if status != HTTPStatus.NOT_FOUND or error_code(creator_result) != "PUBLIC_CREATOR_NOT_FOUND":
            raise RuntimeError("Takedown did not immediately remove the anonymous creator profile")

        status, replay, _ = request(
            admin, base_url, f"/api/admin/works/{IMAGE_ID}/takedown", payload=takedown_payload, origin=base_url,
        )
        if status != HTTPStatus.OK or replay.get("action", {}).get("id") != result.get("action", {}).get("id") or replay.get("replayed") is not True:
            raise RuntimeError("Same-key Admin Takedown did not replay its stable result")
        assert_work_owner_allowlist(replay.get("work"), "Admin Takedown replay")
        assert_latest_review_allowlist(replay.get("work"), "Admin Takedown replay")
        if FakeSupabaseHandler.mutation_writes != 1:
            raise RuntimeError("Same-key Admin Takedown wrote a duplicate audit/notification result")

        status, conflict, _ = request(
            admin,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/takedown",
            payload={**takedown_payload, "reason_code": "privacy"},
            origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(conflict) != "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT":
            raise RuntimeError("Same-key different-payload Takedown did not conflict")

        status, conflict, _ = request(
            admin,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/takedown",
            payload={**takedown_payload, "expected_version": 8},
            origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(conflict) != "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT":
            raise RuntimeError("Same-key changed-version Takedown did not conflict")

        status, conflict, _ = request(
            admin,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/restore",
            payload=mutation_body("70000000-0000-4000-8000-000000000077", "restore", expected_version=999),
            origin=base_url,
        )
        if status != HTTPStatus.CONFLICT or error_code(conflict) != "ADMIN_IMAGE_VERSION_CONFLICT":
            raise RuntimeError("Stale Admin Restore did not preserve its CAS error")

        status, restored, _ = request(
            admin,
            base_url,
            f"/api/admin/works/{IMAGE_ID}/restore",
            payload=mutation_body("70000000-0000-4000-8000-000000000078", "restore", expected_version=8),
            origin=base_url,
        )
        if status != HTTPStatus.OK or restored.get("work", {}).get("publication_status") != "published":
            raise RuntimeError("Admin Restore did not return the published stable result")
        assert_no_sensitive(restored, "Admin Restore result")
        assert_work_owner_allowlist(restored.get("work"), "Admin Restore result")
        assert_latest_review_allowlist(restored.get("work"), "Admin Restore result")
        status, works_result, _ = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.OK or works_result.get("count") != 1 or len(works_result.get("items", [])) != 1:
            raise RuntimeError("Restore did not return the work to anonymous Works")
        status, creator_result, _ = request(anonymous, base_url, f"/api/public/creators/{CREATOR_SLUG}")
        if status != HTTPStatus.OK or creator_result.get("creator", {}).get("slug") != CREATOR_SLUG:
            raise RuntimeError("Restore did not return the creator profile to anonymous delivery")

        for provider_status, expected_status, expected_code in (
            (HTTPStatus.UNAUTHORIZED, HTTPStatus.UNAUTHORIZED, "AUTH_REQUIRED"),
            (HTTPStatus.FORBIDDEN, HTTPStatus.FORBIDDEN, "ADMIN_WORKS_ACCESS_REVOKED"),
            (HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY, "ADMIN_WORKS_PROVIDER_UNAVAILABLE"),
        ):
            FakeSupabaseHandler.next_admin_status = provider_status
            status, provider_error, _ = request(admin, base_url, "/api/admin/works")
            if status != expected_status or error_code(provider_error) != expected_code:
                raise RuntimeError(f"Provider {provider_status} did not map to stable Admin Works semantics")
            assert_no_sensitive(provider_error, "Admin Works provider error")

        captured_logs = "\n".join(CapturingAppHandler.captured_logs)
        forbidden_logs = (*PRIVATE_CANARIES, ADMIN_TOKEN, SUPER_ADMIN_TOKEN, RECOVERY_ADMIN_TOKEN)
        if any(value in captured_logs for value in forbidden_logs):
            raise RuntimeError("Admin Works logs exposed credentials or private governance data")

        print("admin_works_route_guards=yes")
        print("admin_works_role_mfa_recovery_inactive=yes")
        print("admin_works_list_detail_allowlist=yes")
        print("admin_works_filters_pagination=yes")
        print("admin_works_pending_dimensions=yes")
        print("admin_works_derivative_preview_suppression=yes")
        print("admin_works_governance_cas_idempotency=yes")
        print("admin_works_provider_drift_fail_closed=yes")
        print("admin_works_governance_cross_record_binding=yes")
        print("admin_works_signed_url_path_binding=yes")
        print("admin_works_relationship_integrity=yes")
        print("admin_works_public_takedown_restore=yes")
        print("admin_works_provider_error_mapping=yes")
        print("admin_works_sensitive_fields_exposed=no")
    finally:
        application.shutdown()
        application.server_close()
        provider.shutdown()
        provider.server_close()
        temp_site.cleanup()


if __name__ == "__main__":
    main()
