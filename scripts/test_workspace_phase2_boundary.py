#!/usr/bin/env python3
"""Secret-free HTTP integration test for Phase 2A Workspace boundaries."""

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
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MEMBER_ID = "20000000-0000-4000-8000-000000000001"
ADMIN_ID = "20000000-0000-4000-8000-000000000002"
FOLDER_ID = "30000000-0000-4000-8000-000000000001"
CUSTOM_FOLDER_ID = "30000000-0000-4000-8000-000000000002"
UPLOAD_ID = "40000000-0000-4000-8000-000000000001"
CANCEL_UPLOAD_ID = "40000000-0000-4000-8000-000000000002"
IMAGE_ID = "50000000-0000-4000-8000-000000000001"
VERSION_ID = "60000000-0000-4000-8000-000000000001"
SUBMISSION_ID = "80000000-0000-4000-8000-000000000001"
SUBMIT_IDEMPOTENCY_KEY = "90000000-0000-4000-8000-000000000001"
INCOMPLETE_IDEMPOTENCY_KEY = "90000000-0000-4000-8000-000000000002"
SCAN_PENDING_IDEMPOTENCY_KEY = "90000000-0000-4000-8000-000000000003"
STALE_IDEMPOTENCY_KEY = "90000000-0000-4000-8000-000000000004"
SUBMITTED_AT = "2026-07-16T08:00:00Z"
SUBMISSION_POLICY_VERSION = "workspace-review-v1"


def access_token(user_id: str, aal: str = "aal1") -> str:
    now = int(time.time())
    claims = {
        "sub": user_id,
        "aal": aal,
        "amr": [{"method": "password"}],
        "session_id": str(uuid.uuid5(uuid.NAMESPACE_URL, user_id)),
        "iat": now - 60,
        "exp": now + 3600,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


MEMBER_TOKEN = access_token(MEMBER_ID)
ADMIN_TOKEN = access_token(ADMIN_ID)


def draft_payload(
    title: str = "Server Draft",
    version_patch: dict | None = None,
    lock_version: int = 1,
    *,
    processing_status: str = "ready",
    workflow_status: str = "draft",
    locked_at: str | None = None,
    scan_statuses: dict[str, str] | None = None,
    folder_id: str = CUSTOM_FOLDER_ID,
    deleted_at: str | None = None,
) -> dict:
    version = {
        "id": VERSION_ID,
        "version_number": 1,
        "title": title,
        "caption": "Quiet weather.",
        "description": "",
        "alt_text": "",
        "tags": ["weather"],
        "content_category": "concrete",
        "captured_at": None,
        "location_name": None,
        "copyright_holder": None,
        "copyright_year": None,
        "contains_recognizable_people": None,
        "model_release_status": None,
        "property_release_status": None,
        "rights_declared": False,
        "ai_disclosure": None,
        "sensitive_content_disclosure": None,
        "created_at": "2026-07-15T00:00:00Z",
        "locked_at": locked_at,
    }
    version.update(version_patch or {})
    return {
        "id": IMAGE_ID,
        "folder_id": folder_id,
        "processing_status": processing_status,
        "workflow_status": workflow_status,
        "publication_status": "never_published",
        "original_filename": "field.jpg",
        "original_width": 2400,
        "original_height": 1600,
        "checksum_sha256": "a" * 64,
        "lock_version": lock_version,
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
        "deleted_at": deleted_at,
        "version": version,
        "assets": [
            {
                "id": f"70000000-0000-4000-8000-00000000000{index}",
                "kind": kind,
                "storage_bucket": bucket,
                "storage_key": f"{MEMBER_ID}/{IMAGE_ID}/{kind}.jpg",
                "mime_type": "image/jpeg",
                "byte_size": size,
                "width": width,
                "height": height,
                "checksum_sha256": character * 64,
                "scan_status": (scan_statuses or {}).get(kind, "pending"),
            }
            for index, (kind, bucket, size, width, height, character) in enumerate((
                ("original", "image-originals", 900000, 2400, 1600, "a"),
                ("display", "image-display", 400000, 1800, 1200, "b"),
                ("thumbnail", "image-thumbnails", 50000, 480, 320, "c"),
            ), start=1)
        ],
    }


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    rpc_calls: list[tuple[str, dict]] = []
    storage_calls: list[str] = []
    storage_delete_calls: list[tuple[str, dict]] = []
    draft_version_patch: dict = {}
    draft_lock_version = 1
    draft_processing_status = "ready"
    draft_workflow_status = "draft"
    draft_locked_at: str | None = None
    draft_deleted_at: str | None = None
    draft_folder_id = CUSTOM_FOLDER_ID
    restore_folder_missing = False
    restore_delay_seconds = 0.0
    asset_scan_statuses: dict[str, str] = {
        "original": "pending",
        "display": "pending",
        "thumbnail": "pending",
    }
    submissions: list[dict] = []
    submission_snapshot: dict | None = None
    submission_results_by_key: dict[str, dict] = {}

    @classmethod
    def reset_draft_state(cls) -> None:
        cls.draft_version_patch = {}
        cls.draft_lock_version = 1
        cls.draft_processing_status = "ready"
        cls.draft_workflow_status = "draft"
        cls.draft_locked_at = None
        cls.draft_deleted_at = None
        cls.draft_folder_id = CUSTOM_FOLDER_ID
        cls.restore_folder_missing = False
        cls.restore_delay_seconds = 0.0
        cls.asset_scan_statuses = {
            "original": "pending",
            "display": "pending",
            "thumbnail": "pending",
        }
        cls.submissions = []
        cls.submission_snapshot = None
        cls.submission_results_by_key = {}

    @classmethod
    def current_draft(cls) -> dict:
        return draft_payload(
            title=cls.draft_version_patch.get("title", "Server Draft"),
            version_patch=cls.draft_version_patch,
            lock_version=cls.draft_lock_version,
            processing_status=cls.draft_processing_status,
            workflow_status=cls.draft_workflow_status,
            locked_at=cls.draft_locked_at,
            scan_statuses=cls.asset_scan_statuses,
            folder_id=cls.draft_folder_id,
            deleted_at=cls.draft_deleted_at,
        )

    @classmethod
    def submission_readiness(cls) -> dict:
        draft = cls.current_draft()
        version = draft["version"]
        field_errors = {}
        required_fields = {
            "title": "Title is required.",
            "alt_text": "Alt text is required.",
            "content_category": "Content category is required.",
            "copyright_holder": "Copyright holder is required.",
            "copyright_year": "Copyright year is required.",
            "contains_recognizable_people": "Choose whether recognizable people appear.",
            "property_release_status": "Property release status is required.",
            "ai_disclosure": "AI disclosure is required.",
            "sensitive_content_disclosure": "Sensitive content disclosure is required.",
        }
        for field, message in required_fields.items():
            value = version.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                field_errors[field] = message
        if version.get("rights_declared") is not True:
            field_errors["rights_declared"] = "Confirm that you control the required rights."
        if version.get("contains_recognizable_people") is True and not version.get("model_release_status"):
            field_errors["model_release_status"] = "Model release status is required."

        assets = draft["assets"]
        asset_kinds = {asset.get("kind") for asset in assets}
        assets_complete = asset_kinds == {"original", "display", "thumbnail"} and len(assets) == 3
        scan_states = {asset.get("scan_status") for asset in assets}
        scans_clean = assets_complete and scan_states == {"clean"}
        scans_pending = assets_complete and scan_states <= {"clean", "pending"} and "pending" in scan_states
        workflow_editable = draft["workflow_status"] in {"draft", "changes_requested"} and not version.get("locked_at")

        work_detail_fields = {"title", "alt_text", "content_category"}
        work_detail_errors = work_detail_fields & field_errors.keys()
        rights_errors = set(field_errors) - work_detail_fields
        assets_ready = draft["processing_status"] == "ready" and assets_complete
        checks = [
            {
                "code": "work_details",
                "label": "Work details",
                "state": "pass" if not work_detail_errors else "fail",
                "message": "Work details are complete." if not work_detail_errors else "Complete the required work details.",
            },
            {
                "code": "rights_disclosures",
                "label": "Rights and disclosures",
                "state": "pass" if not rights_errors else "fail",
                "message": "Rights and disclosures are complete." if not rights_errors else "Complete the required rights and disclosures.",
            },
            {
                "code": "image_assets",
                "label": "Image assets",
                "state": "pass" if assets_ready else ("pending" if draft["processing_status"] != "ready" else "fail"),
                "message": "All required assets are available." if assets_ready else ("Image processing is still running." if draft["processing_status"] != "ready" else "Required image assets are missing."),
            },
            {
                "code": "security_scan",
                "label": "Security scan",
                "state": "pass" if scans_clean else ("pending" if scans_pending else "fail"),
                "message": "Security scans are complete." if scans_clean else ("Security scans are still running." if scans_pending else "An image asset did not pass its security scan."),
            },
            {
                "code": "submission_state",
                "label": "Submission state",
                "state": "pass" if workflow_editable else "fail",
                "message": "This Draft can be submitted." if workflow_editable else "This image is no longer an editable Draft.",
            },
        ]
        blocker_count = sum(check["state"] != "pass" for check in checks)
        has_failure = any(check["state"] == "fail" for check in checks)
        return {
            "image_id": IMAGE_ID,
            "lock_version": cls.draft_lock_version,
            "workflow_status": cls.draft_workflow_status,
            "status": "ready" if blocker_count == 0 else ("blocked" if has_failure else "pending"),
            "ready": blocker_count == 0,
            "blocker_count": blocker_count,
            "checks": checks,
            "field_errors": field_errors,
        }

    @classmethod
    def provider_readiness(cls) -> dict:
        readiness = copy.deepcopy(cls.submission_readiness())
        readiness["storage_key"] = f"{MEMBER_ID}/{IMAGE_ID}/original.jpg"
        readiness["scan_result_code"] = "internal-malware-signature"
        readiness["internal_note"] = "provider-only readiness context"
        for check in readiness["checks"]:
            check["internal_debug"] = "do-not-return"
        return readiness

    def log_message(self, _format, *_args) -> None:
        return

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
        authorization = self.headers.get("Authorization")
        if self.path == "/auth/v1/user" and authorization in {f"Bearer {MEMBER_TOKEN}", f"Bearer {ADMIN_TOKEN}"}:
            is_admin = authorization == f"Bearer {ADMIN_TOKEN}"
            self.send_json(HTTPStatus.OK, {
                "id": ADMIN_ID if is_admin else MEMBER_ID,
                "email": "admin@example.test" if is_admin else "member@example.test",
                "email_confirmed_at": "2026-07-15T00:00:00Z",
                "factors": [],
            })
            return
        if self.path.startswith("/rest/v1/user_profiles?") and authorization in {f"Bearer {MEMBER_TOKEN}", f"Bearer {ADMIN_TOKEN}"}:
            self.send_json(HTTPStatus.OK, [{
                "display_name": "Workspace Member",
                "avatar_url": None,
                "bio": "",
                "website_url": None,
                "country_code": "CN",
                "preferred_locale": "en",
                "timezone": "Asia/Shanghai",
                "copyright_name": "Workspace Member",
                "default_license_preference": "all-rights-reserved",
            }])
            return
        if self.path.startswith("/storage/v1/object/sign/"):
            body = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        authorization = self.headers.get("Authorization")
        if self.path == "/auth/v1/token?grant_type=password":
            body = self.body()
            is_admin = body.get("email") == "admin@example.test"
            expected_password = "Admin-password-2026!" if is_admin else "Member-password-2026!"
            if body.get("password") != expected_password:
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid credentials"})
                return
            user_id = ADMIN_ID if is_admin else MEMBER_ID
            token = ADMIN_TOKEN if is_admin else MEMBER_TOKEN
            self.send_json(HTTPStatus.OK, {
                "access_token": token,
                "refresh_token": f"refresh-{user_id}",
                "expires_in": 3600,
                "user": {
                    "id": user_id,
                    "email": body.get("email"),
                    "email_confirmed_at": "2026-07-15T00:00:00Z",
                },
            })
            return
        if self.path == "/rest/v1/rpc/current_authorization":
            if authorization == f"Bearer {MEMBER_TOKEN}":
                self.send_json(HTTPStatus.OK, {"user_id": MEMBER_ID, "account_status": "active", "roles": ["user"], "aal": "aal1"})
                return
            if authorization == f"Bearer {ADMIN_TOKEN}":
                self.send_json(HTTPStatus.OK, {"user_id": ADMIN_ID, "account_status": "active", "roles": ["admin"], "aal": "aal1"})
                return
            self.send_json(HTTPStatus.UNAUTHORIZED, {})
            return
        if self.path.startswith("/rest/v1/rpc/"):
            name = self.path.rsplit("/", 1)[-1]
            body = self.body()
            type(self).rpc_calls.append((name, body))
            if authorization != f"Bearer {MEMBER_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            if name == "workspace_get_submit_readiness":
                self.send_json(HTTPStatus.OK, {
                    "readiness": type(self).provider_readiness(),
                    "provider_debug": "do-not-return",
                })
                return
            if name == "workspace_submit_draft_versioned":
                idempotency_key = body.get("idempotency_key")
                replay = type(self).submission_results_by_key.get(idempotency_key)
                if replay is not None:
                    self.send_json(HTTPStatus.OK, copy.deepcopy(replay))
                    return
                if body.get("expected_version") != type(self).draft_lock_version:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_VERSION_CONFLICT",
                        "message": "A newer version of this Draft is available. Reload before submitting.",
                    }})
                    return
                if type(self).draft_workflow_status not in {"draft", "changes_requested"} or type(self).draft_locked_at:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_LOCKED",
                        "message": "Submitted or reviewed images cannot be changed as Drafts.",
                    }})
                    return
                readiness = type(self).submission_readiness()
                if not readiness["ready"]:
                    provider_details = type(self).provider_readiness()
                    provider_details["owner_user_id"] = MEMBER_ID
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_NOT_READY",
                        "message": "This Draft is not ready to submit.",
                        "field_errors": readiness["field_errors"],
                        "details": provider_details,
                        "storage_key": f"{MEMBER_ID}/{IMAGE_ID}/original.jpg",
                        "internal_note": "provider-only submission details",
                    }})
                    return

                type(self).submission_snapshot = copy.deepcopy(type(self).current_draft()["version"])
                type(self).draft_locked_at = SUBMITTED_AT
                type(self).draft_workflow_status = "submitted"
                type(self).draft_lock_version += 1
                submission = {
                    "id": SUBMISSION_ID,
                    "image_id": IMAGE_ID,
                    "image_version_id": VERSION_ID,
                    "status": "submitted",
                    "policy_version": SUBMISSION_POLICY_VERSION,
                    "submitted_at": SUBMITTED_AT,
                }
                type(self).submissions.append(copy.deepcopy(submission))
                provider_result = {
                    "submitted": True,
                    "submission": {
                        **submission,
                        "submitted_by_user_id": MEMBER_ID,
                        "internal_note": "provider-only review context",
                    },
                    "image": {
                        "id": IMAGE_ID,
                        "workflow_status": type(self).draft_workflow_status,
                        "lock_version": type(self).draft_lock_version,
                        "checksum_sha256": "a" * 64,
                    },
                    "assets": type(self).current_draft()["assets"],
                    "snapshot": copy.deepcopy(type(self).submission_snapshot),
                    "refresh_token": f"refresh-{MEMBER_ID}",
                }
                type(self).submission_results_by_key[idempotency_key] = copy.deepcopy(provider_result)
                self.send_json(HTTPStatus.OK, provider_result)
                return
            patch = body.get("patch", {})
            update_title = patch["title"] if "title" in patch else "Server Draft"
            updated_version = {key: value for key, value in patch.items() if key != "folder_id"}
            if name == "workspace_update_draft_versioned":
                if body.get("expected_version") != type(self).draft_lock_version:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_VERSION_CONFLICT",
                        "message": "A newer version of this Draft is available. Reload before saving.",
                    }})
                    return
                if type(self).draft_workflow_status not in {"draft", "changes_requested"} or type(self).draft_locked_at:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_LOCKED",
                        "message": "Submitted or reviewed images cannot be edited as Drafts.",
                    }})
                    return
                type(self).draft_version_patch.update(updated_version)
                type(self).draft_lock_version += 1
            if name == "workspace_trash_draft_versioned":
                if body.get("expected_version") != type(self).draft_lock_version:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_VERSION_CONFLICT",
                        "message": "A newer version of this Draft is available. Reload before moving it to Trash.",
                    }})
                    return
                if type(self).draft_workflow_status not in {"draft", "changes_requested"} or type(self).draft_locked_at:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_LOCKED",
                        "message": "Submitted or reviewed images cannot be moved to Trash.",
                    }})
                    return
                if type(self).draft_deleted_at is not None:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_NOT_FOUND",
                        "message": "The Draft is unavailable or cannot be moved to Trash.",
                    }})
                    return
                type(self).draft_deleted_at = "2026-07-22T03:00:00Z"
                type(self).draft_lock_version += 1
            if name == "workspace_restore_draft":
                if type(self).restore_delay_seconds:
                    time.sleep(type(self).restore_delay_seconds)
                if type(self).draft_deleted_at is None:
                    self.send_json(HTTPStatus.OK, {"error": {
                        "code": "DRAFT_NOT_FOUND",
                        "message": "The Draft is unavailable or cannot be restored.",
                    }})
                    return
                if type(self).restore_folder_missing:
                    type(self).draft_folder_id = FOLDER_ID
                type(self).draft_deleted_at = None
                type(self).draft_lock_version += 1
                self.send_json(HTTPStatus.OK, {"draft": type(self).current_draft()})
                return
            persisted_version = dict(type(self).draft_version_patch)
            persisted_version.setdefault("title", update_title)
            updated_draft = draft_payload(
                persisted_version.get("title", update_title),
                persisted_version,
                type(self).draft_lock_version,
                folder_id=type(self).draft_folder_id,
                deleted_at=type(self).draft_deleted_at,
            )
            if "folder_id" in patch:
                type(self).draft_folder_id = patch["folder_id"]
                updated_draft["folder_id"] = patch["folder_id"]
            intent_upload_id = (
                CANCEL_UPLOAD_ID
                if body.get("intent", {}).get("original_filename") == "cancel.jpg"
                else UPLOAD_ID
            )
            responses = {
                "workspace_list_folders": {"folders": [
                    {"id": FOLDER_ID, "name": "Inbox", "is_system": True, "image_count": 0},
                    {"id": CUSTOM_FOLDER_ID, "name": "Field Work", "is_system": False, "image_count": 1},
                ]},
                "workspace_create_folder": {"folder": {"id": CUSTOM_FOLDER_ID, "name": body.get("folder_name"), "is_system": False, "image_count": 0}},
                "workspace_rename_folder": {"folder": {"id": CUSTOM_FOLDER_ID, "name": body.get("folder_name"), "is_system": False, "image_count": 0}},
                "workspace_delete_folder": {"deleted": True, "folder_id": CUSTOM_FOLDER_ID, "moved_image_count": 1},
                "workspace_restore_folder": {"folder": {"id": CUSTOM_FOLDER_ID, "name": "Field Work", "is_system": False, "image_count": 0}},
                "workspace_create_upload_intent": {
                    "upload_id": intent_upload_id,
                    "image_id": IMAGE_ID,
                    "folder_id": CUSTOM_FOLDER_ID,
                    "expires_at": "2026-07-15T02:00:00Z",
                    "assets": draft_payload()["assets"],
                },
                "workspace_complete_upload": {"draft": draft_payload()},
                "workspace_cancel_upload_intent": {
                    "canceled": True,
                    "upload_id": body.get("upload_id"),
                    "cleanup_status": "pending",
                    "assets": draft_payload()["assets"],
                },
                "workspace_finish_upload_cleanup": {
                    "upload_id": body.get("upload_id"),
                    "cleanup_status": "complete" if body.get("cleanup_succeeded") else "failed",
                },
                "workspace_list_drafts": {
                    "images": [type(self).current_draft()]
                    if type(self).draft_workflow_status in {"draft", "changes_requested"}
                    and type(self).draft_deleted_at is None
                    else []
                },
                "workspace_list_trashed_drafts": {
                    "images": [type(self).current_draft()]
                    if type(self).draft_workflow_status in {"draft", "changes_requested"}
                    and type(self).draft_deleted_at is not None
                    else []
                },
                "workspace_update_draft_versioned": {"draft": updated_draft},
                "workspace_trash_draft": {"trashed": True, "image_id": IMAGE_ID},
                "workspace_trash_draft_versioned": {"trashed": True, "image_id": IMAGE_ID},
            }
            self.send_json(HTTPStatus.OK, responses.get(name, {"error": {"code": "UNKNOWN", "message": "unknown RPC"}}))
            return
        if self.path.startswith("/storage/v1/object/upload/sign/"):
            self.body()
            type(self).storage_calls.append(self.path)
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"url": f"{suffix}?token=signed-upload-token"})
            return
        if self.path.startswith("/storage/v1/object/sign/"):
            self.body()
            type(self).storage_calls.append(self.path)
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=signed-read-token"})
            return
        if self.path.startswith("/storage/v1/bucket/") and self.path.endswith("/delete"):
            body = self.body()
            type(self).storage_delete_calls.append((self.path, body))
            self.send_json(HTTPStatus.OK, [{"name": key} for key in body.get("prefixes", [])])
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


def request(
    opener,
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    origin: str | None = None,
    method: str | None = None,
    include_csrf: bool = True,
):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if origin:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
        csrf = next((cookie.value for cookie in opener.cookie_jar if cookie.name.endswith("mt_csrf_token")), "")
        if csrf and include_csrf:
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
            result = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else {}
            return response.status, result, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        result = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else {}
        return error.code, result, error.headers


def sign_in(opener, base_url: str, email: str, password: str) -> dict:
    status, csrf, _ = request(opener, base_url, "/api/auth/csrf")
    if status != HTTPStatus.OK or not csrf.get("csrf_token"):
        raise RuntimeError("Could not initialize CSRF")
    status, result, _ = request(
        opener,
        base_url,
        "/api/auth/sign-in",
        payload={"email": email, "password": password},
        origin=base_url,
    )
    if status != HTTPStatus.OK:
        raise RuntimeError("Could not establish test session")
    return result


def valid_intent() -> dict:
    return {
        "folder_id": CUSTOM_FOLDER_ID,
        "original_filename": "field.jpg",
        "original_width": 2400,
        "original_height": 1600,
        "checksum_sha256": "a" * 64,
        "assets": [
            {key: value for key, value in asset.items() if key in {"kind", "mime_type", "byte_size", "width", "height", "checksum_sha256"}}
            for asset in draft_payload()["assets"]
        ],
    }


def complete_submission_metadata() -> dict:
    return {
        "title": "Ready for Review",
        "alt_text": "A quiet field beneath a pale sky.",
        "content_category": "concrete",
        "copyright_holder": "MT Presence",
        "copyright_year": 2026,
        "contains_recognizable_people": False,
        "model_release_status": "not_applicable",
        "property_release_status": "not_applicable",
        "rights_declared": True,
        "ai_disclosure": "none",
        "sensitive_content_disclosure": "none",
    }


def assert_safe_readiness(payload: dict, *, status: str, ready: bool) -> dict:
    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        raise RuntimeError("Submission readiness response was missing its stable payload")
    if set(readiness) != {
        "image_id",
        "lock_version",
        "workflow_status",
        "status",
        "ready",
        "blocker_count",
        "checks",
        "field_errors",
    }:
        raise RuntimeError("Submission readiness response exposed an unstable or internal field")
    if readiness.get("image_id") != IMAGE_ID or readiness.get("status") != status or readiness.get("ready") is not ready:
        raise RuntimeError("Submission readiness response reported the wrong state")
    checks = readiness.get("checks")
    if not isinstance(checks, list) or [check.get("code") for check in checks] != [
        "work_details",
        "rights_disclosures",
        "image_assets",
        "security_scan",
        "submission_state",
    ]:
        raise RuntimeError("Submission readiness checks were incomplete or reordered")
    for check in checks:
        if set(check) != {"code", "label", "state", "message"}:
            raise RuntimeError("Submission readiness check exposed provider-only details")
        if check.get("state") not in {"pass", "pending", "fail"} or not check.get("label") or not check.get("message"):
            raise RuntimeError("Submission readiness check had an invalid public state")
    if readiness.get("blocker_count") != sum(check["state"] != "pass" for check in checks):
        raise RuntimeError("Submission readiness blocker count did not match its checks")
    if not isinstance(readiness.get("field_errors"), dict):
        raise RuntimeError("Submission readiness field errors were not stable")
    serialized = json.dumps(payload, sort_keys=True)
    forbidden = {
        "storage_key",
        "scan_result_code",
        "internal_note",
        "internal_debug",
        "provider_debug",
        "owner_user_id",
        MEMBER_ID,
    }
    if any(value in serialized for value in forbidden):
        raise RuntimeError("Submission readiness response leaked provider-only details")
    return readiness


def assert_safe_submit_response(payload: dict) -> None:
    if set(payload) != {"submitted", "submission", "image"} or payload.get("submitted") is not True:
        raise RuntimeError("Submit response did not use the strict public allowlist")
    submission = payload.get("submission")
    image = payload.get("image")
    if not isinstance(submission, dict) or set(submission) != {
        "id",
        "image_id",
        "image_version_id",
        "status",
        "policy_version",
        "submitted_at",
    }:
        raise RuntimeError("Submit response exposed an unstable submission shape")
    if not isinstance(image, dict) or set(image) != {"id", "workflow_status", "lock_version"}:
        raise RuntimeError("Submit response exposed an unstable image shape")
    if (
        submission.get("id") != SUBMISSION_ID
        or submission.get("image_id") != IMAGE_ID
        or submission.get("image_version_id") != VERSION_ID
        or submission.get("status") != "submitted"
        or image != {"id": IMAGE_ID, "workflow_status": "submitted", "lock_version": 3}
    ):
        raise RuntimeError("Submit response did not describe the locked submitted version")
    serialized = json.dumps(payload, sort_keys=True)
    forbidden = {
        "assets",
        "storage_key",
        "checksum_sha256",
        "submitted_by_user_id",
        "internal_note",
        "snapshot",
        "refresh_token",
        "signed_url",
        MEMBER_TOKEN,
        MEMBER_ID,
    }
    if any(value in serialized for value in forbidden):
        raise RuntimeError("Submit response leaked provider-only data or session secrets")


def main() -> None:
    FakeSupabaseHandler.rpc_calls = []
    FakeSupabaseHandler.storage_calls = []
    FakeSupabaseHandler.storage_delete_calls = []
    FakeSupabaseHandler.reset_draft_state()
    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{fake_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")
    with tempfile.TemporaryDirectory(prefix="mt-workspace-boundary-") as temp_name:
        handler = partial(app.MTRequestHandler, directory=temp_name)
        app_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
        app_thread.start()
        base_url = f"http://127.0.0.1:{app_server.server_address[1]}"
        anonymous = CookieOpener()
        member = CookieOpener()
        admin = CookieOpener()
        try:
            status, _, _ = request(anonymous, base_url, "/api/folders")
            if status != HTTPStatus.UNAUTHORIZED:
                raise RuntimeError("Anonymous request reached Folder RPC")

            sign_in(member, base_url, "member@example.test", "Member-password-2026!")
            status, result, _ = request(member, base_url, "/api/folders")
            if status != HTTPStatus.OK or result.get("folders", [])[0].get("name") != "Inbox":
                raise RuntimeError("Member could not hydrate server Folders")

            before = len(FakeSupabaseHandler.rpc_calls)
            status, result, _ = request(member, base_url, "/api/folders", payload={"name": "\n"}, origin=base_url)
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or len(FakeSupabaseHandler.rpc_calls) != before:
                raise RuntimeError("Invalid Folder input reached the provider RPC")

            status, result, _ = request(member, base_url, "/api/folders", payload={"name": "Field Work"}, origin=base_url)
            if status != HTTPStatus.CREATED or result.get("folder", {}).get("name") != "Field Work":
                raise RuntimeError("Folder create boundary failed")
            status, result, _ = request(
                member,
                base_url,
                f"/api/folders/{CUSTOM_FOLDER_ID}",
                payload={"name": "Field Notes"},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.OK or result.get("folder", {}).get("name") != "Field Notes":
                raise RuntimeError("Folder rename boundary failed")

            status, _, _ = request(member, base_url, "/api/uploads/intents", payload={"assets": []}, origin=base_url)
            if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise RuntimeError("Incomplete upload intent was accepted")
            status, result, _ = request(member, base_url, "/api/uploads/intents", payload=valid_intent(), origin=base_url)
            if status != HTTPStatus.CREATED or len(result.get("assets", [])) != 3:
                raise RuntimeError("Signed upload intent was not created")
            if any("signed_url" not in asset or "mt_access_token" in asset["signed_url"] for asset in result["assets"]):
                raise RuntimeError("Signed upload response was missing destinations or exposed a session token")

            status, result, _ = request(
                member,
                base_url,
                f"/api/uploads/{UPLOAD_ID}/complete",
                payload={"draft": {"title": "Server Draft", "content_category": "concrete", "tags": ["weather"]}},
                origin=base_url,
            )
            if status != HTTPStatus.CREATED or not result.get("draft", {}).get("assets", [])[0].get("signed_url"):
                raise RuntimeError("Upload completion did not return a private server Draft")

            cancel_intent = valid_intent()
            cancel_intent["original_filename"] = "cancel.jpg"
            status, result, _ = request(member, base_url, "/api/uploads/intents", payload=cancel_intent, origin=base_url)
            if status != HTTPStatus.CREATED or result.get("upload_id") != CANCEL_UPLOAD_ID:
                raise RuntimeError("Cancelable upload intent was not created")
            status, _, _ = request(
                member,
                base_url,
                f"/api/uploads/{CANCEL_UPLOAD_ID}",
                payload={"confirmation": "delete-now"},
                origin=base_url,
                method="DELETE",
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise RuntimeError("Upload cancellation accepted an invalid confirmation")
            status, result, _ = request(
                member,
                base_url,
                f"/api/uploads/{CANCEL_UPLOAD_ID}",
                payload={"confirmation": "cancel-upload"},
                origin=base_url,
                method="DELETE",
            )
            if (
                status != HTTPStatus.OK
                or result.get("canceled") is not True
                or result.get("cleanup_status") != "complete"
                or "assets" in result
            ):
                raise RuntimeError("Upload cancellation did not complete through the safe response boundary")
            if len(FakeSupabaseHandler.storage_delete_calls) != 3:
                raise RuntimeError("Upload cancellation did not clean all three private buckets")
            deleted_paths = [
                path
                for _, body in FakeSupabaseHandler.storage_delete_calls
                for path in body.get("prefixes", [])
            ]
            if len(deleted_paths) != 3 or any(not path.startswith(f"{MEMBER_ID}/") for path in deleted_paths):
                raise RuntimeError("Upload cancellation attempted to delete a non-owner Storage path")

            status, result, _ = request(member, base_url, "/api/images?workflow_status=draft")
            if status != HTTPStatus.OK or result.get("images", [])[0].get("publication_status") != "never_published":
                raise RuntimeError("Draft hydration did not remain non-public")
            if result.get("images", [])[0].get("lock_version") != 1:
                raise RuntimeError("Draft hydration did not expose its optimistic lock version")

            status, _, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 1, "draft": {"publication_status": "published"}},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise RuntimeError("Draft patch accepted a system publication field")
            status, _, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"draft": {"title": "Missing version"}},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise RuntimeError("Draft patch accepted metadata without an expected version")
            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={
                    "expected_version": 1,
                    "draft": {"title": "Updated Draft", "folder_id": CUSTOM_FOLDER_ID},
                },
                origin=base_url,
                method="PATCH",
            )
            if (
                status != HTTPStatus.OK
                or result.get("draft", {}).get("version", {}).get("title") != "Updated Draft"
                or result.get("draft", {}).get("lock_version") != 2
                or "assets" in result.get("draft", {})
            ):
                raise RuntimeError("Draft update boundary failed")
            compliance_patch = {
                "alt_text": "A quiet field beneath a pale sky.",
                "location_name": "Northern Field",
                "copyright_holder": "MT Presence",
                "copyright_year": 2026,
                "contains_recognizable_people": True,
                "model_release_status": "available",
                "property_release_status": "not_applicable",
                "rights_declared": True,
                "ai_disclosure": "none",
                "sensitive_content_disclosure": "none",
            }
            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 2, "draft": compliance_patch},
                origin=base_url,
                method="PATCH",
            )
            saved_version = result.get("draft", {}).get("version", {})
            if (
                status != HTTPStatus.OK
                or result.get("draft", {}).get("lock_version") != 3
                or any(saved_version.get(key) != value for key, value in compliance_patch.items())
            ):
                raise RuntimeError("Draft compliance metadata did not round-trip through the owner boundary")
            status, _, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 2, "draft": {"title": "Stale overwrite"}},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.CONFLICT:
                raise RuntimeError("Draft optimistic concurrency accepted a stale expected version")
            for invalid_patch in (
                {"copyright_year": 999},
                {"contains_recognizable_people": "yes"},
                {"model_release_status": "uploaded"},
                {"ai_disclosure": "unknown"},
                {"sensitive_content_disclosure": "unspecified"},
                {"rights_declared": "true"},
            ):
                status, _, _ = request(
                    member,
                    base_url,
                    f"/api/images/{IMAGE_ID}/draft",
                    payload={"expected_version": 3, "draft": invalid_patch},
                    origin=base_url,
                    method="PATCH",
                )
                if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                    raise RuntimeError(f"Draft compliance boundary accepted invalid metadata: {invalid_patch}")
            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 3, "draft": {"title": ""}},
                origin=base_url,
                method="PATCH",
            )
            if (
                status != HTTPStatus.OK
                or result.get("draft", {}).get("version", {}).get("title") != ""
                or result.get("draft", {}).get("lock_version") != 4
            ):
                raise RuntimeError("Incomplete Draft title was replaced by a display fallback")

            status, _, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}",
                payload={"confirmation": "delete-now", "expected_version": 4},
                origin=base_url,
                method="DELETE",
            )
            if status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise RuntimeError("Draft Trash action accepted an invalid confirmation")
            status, _, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}",
                payload={"confirmation": "move-to-trash", "expected_version": 3},
                origin=base_url,
                method="DELETE",
            )
            if status != HTTPStatus.CONFLICT:
                raise RuntimeError("Draft Trash accepted a stale expected version")
            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}",
                payload={"confirmation": "move-to-trash", "expected_version": 4},
                origin=base_url,
                method="DELETE",
            )
            if status != HTTPStatus.OK or result.get("trashed") is not True:
                raise RuntimeError("Draft Trash boundary failed")

            status, result, _ = request(member, base_url, "/api/images?workflow_status=draft")
            if status != HTTPStatus.OK or result.get("images") != []:
                raise RuntimeError("Trashed Draft remained visible in the active Draft list")
            status, result, _ = request(member, base_url, "/api/images?workflow_status=trashed")
            trashed = result.get("images", [])
            if (
                status != HTTPStatus.OK
                or len(trashed) != 1
                or trashed[0].get("id") != IMAGE_ID
                or not trashed[0].get("deleted_at")
                or trashed[0].get("lock_version") != 5
            ):
                raise RuntimeError("Owner Trash list did not return the soft-deleted Draft DTO")

            for invalid_query in (
                "/api/images?workflow_status=",
                "/api/images?workflow_status=trashed&workflow_status=draft",
                "/api/images?workflow_status=trashed&owner_id=other",
            ):
                status, result, _ = request(member, base_url, invalid_query)
                if status != HTTPStatus.UNPROCESSABLE_ENTITY or result.get("error", {}).get("code") != "IMAGE_FILTER_INVALID":
                    raise RuntimeError(f"Draft list accepted invalid query parameters: {invalid_query}")

            restore_path = f"/api/images/{IMAGE_ID}/restore"
            status, result, _ = request(
                member,
                base_url,
                restore_path,
                payload={},
                origin=base_url,
                include_csrf=False,
            )
            if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "CSRF_REJECTED":
                raise RuntimeError("Draft Restore accepted a request without CSRF")

            restore_rpc_count = len([
                call for call in FakeSupabaseHandler.rpc_calls
                if call[0] == "workspace_restore_draft"
            ])
            status, result, _ = request(
                member,
                base_url,
                restore_path,
                payload={"expected_version": 5},
                origin=base_url,
            )
            if (
                status != HTTPStatus.UNPROCESSABLE_ENTITY
                or result.get("error", {}).get("code") != "DRAFT_RESTORE_INVALID"
                or len([call for call in FakeSupabaseHandler.rpc_calls if call[0] == "workspace_restore_draft"]) != restore_rpc_count
            ):
                raise RuntimeError("Draft Restore accepted or forwarded unsupported request fields")

            FakeSupabaseHandler.restore_folder_missing = True
            status, result, _ = request(member, base_url, restore_path, payload={}, origin=base_url)
            restored = result.get("draft", {})
            if (
                status != HTTPStatus.OK
                or restored.get("id") != IMAGE_ID
                or restored.get("folder_id") != FOLDER_ID
                or restored.get("deleted_at") is not None
                or restored.get("lock_version") != 6
            ):
                raise RuntimeError("Draft Restore did not recover into the active Inbox")
            status, result, _ = request(member, base_url, restore_path, payload={}, origin=base_url)
            if status != HTTPStatus.NOT_FOUND or result.get("error", {}).get("code") != "DRAFT_NOT_FOUND":
                raise RuntimeError("Repeated Draft Restore did not report the stale Trash state")
            if FakeSupabaseHandler.draft_lock_version != 6:
                raise RuntimeError("Repeated Draft Restore changed the restored Draft version")
            status, result, _ = request(member, base_url, "/api/images?workflow_status=trashed")
            if status != HTTPStatus.OK or result.get("images") != []:
                raise RuntimeError("Restored Draft remained visible in Trash")
            status, result, _ = request(member, base_url, "/api/images?workflow_status=draft")
            active_drafts = result.get("images", [])
            if status != HTTPStatus.OK or len(active_drafts) != 1 or active_drafts[0].get("folder_id") != FOLDER_ID:
                raise RuntimeError("Restored Draft did not return to the active Draft list")

            FakeSupabaseHandler.reset_draft_state()
            submit_path = f"/api/images/{IMAGE_ID}/submit"
            submit_payload = {
                "confirmation": "submit-for-review",
                "expected_version": 1,
                "idempotency_key": INCOMPLETE_IDEMPOTENCY_KEY,
            }
            submit_rpc_count = len([
                call for call in FakeSupabaseHandler.rpc_calls
                if call[0] == "workspace_submit_draft_versioned"
            ])
            status, result, _ = request(
                member,
                base_url,
                submit_path,
                payload=submit_payload,
                origin=base_url,
                include_csrf=False,
            )
            if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "CSRF_REJECTED":
                raise RuntimeError("Draft Submit accepted a request without its CSRF token")
            if len([
                call for call in FakeSupabaseHandler.rpc_calls
                if call[0] == "workspace_submit_draft_versioned"
            ]) != submit_rpc_count:
                raise RuntimeError("CSRF-rejected Draft Submit reached the provider RPC")

            status, result, _ = request(member, base_url, f"/api/images/{IMAGE_ID}/readiness")
            if status != HTTPStatus.OK:
                raise RuntimeError("Incomplete Draft readiness could not be loaded")
            readiness = assert_safe_readiness(result, status="blocked", ready=False)
            if "alt_text" not in readiness["field_errors"] or readiness["blocker_count"] < 2:
                raise RuntimeError("Incomplete Draft readiness did not identify its metadata blockers")

            status, result, _ = request(
                member,
                base_url,
                submit_path,
                payload=submit_payload,
                origin=base_url,
            )
            error = result.get("error", {})
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error.get("code") != "DRAFT_NOT_READY":
                raise RuntimeError("Incomplete Draft was not blocked at the Submit boundary")
            if set(error) != {"code", "message", "request_id", "field_errors", "details"}:
                raise RuntimeError("Draft not-ready error exposed an unstable provider error shape")
            error_readiness = assert_safe_readiness({"readiness": error.get("details")}, status="blocked", ready=False)
            if error.get("field_errors") != error_readiness["field_errors"]:
                raise RuntimeError("Draft not-ready error did not preserve safe field guidance")
            if FakeSupabaseHandler.submissions or FakeSupabaseHandler.draft_lock_version != 1:
                raise RuntimeError("Rejected incomplete Submit changed provider state")

            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 1, "draft": complete_submission_metadata()},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.OK or result.get("draft", {}).get("lock_version") != 2:
                raise RuntimeError("Submission-ready metadata could not be saved")

            status, result, _ = request(member, base_url, f"/api/images/{IMAGE_ID}/readiness")
            if status != HTTPStatus.OK:
                raise RuntimeError("Scan-pending Draft readiness could not be loaded")
            readiness = assert_safe_readiness(result, status="pending", ready=False)
            check_states = {check["code"]: check["state"] for check in readiness["checks"]}
            if readiness["field_errors"] or check_states.get("security_scan") != "pending" or readiness["blocker_count"] != 1:
                raise RuntimeError("Metadata-complete Draft did not isolate its pending scan blocker")

            scan_pending_payload = {
                "confirmation": "submit-for-review",
                "expected_version": 2,
                "idempotency_key": SCAN_PENDING_IDEMPOTENCY_KEY,
            }
            status, result, _ = request(
                member,
                base_url,
                submit_path,
                payload=scan_pending_payload,
                origin=base_url,
            )
            error = result.get("error", {})
            if status != HTTPStatus.UNPROCESSABLE_ENTITY or error.get("code") != "DRAFT_NOT_READY":
                raise RuntimeError("Scan-pending Draft was accepted for review")
            assert_safe_readiness({"readiness": error.get("details")}, status="pending", ready=False)
            if FakeSupabaseHandler.submissions or FakeSupabaseHandler.draft_lock_version != 2:
                raise RuntimeError("Rejected scan-pending Submit changed provider state")

            FakeSupabaseHandler.asset_scan_statuses = {
                "original": "clean",
                "display": "clean",
                "thumbnail": "clean",
            }
            status, result, _ = request(member, base_url, f"/api/images/{IMAGE_ID}/readiness")
            if status != HTTPStatus.OK:
                raise RuntimeError("Ready Draft readiness could not be loaded")
            readiness = assert_safe_readiness(result, status="ready", ready=True)
            if readiness["blocker_count"] != 0 or readiness["field_errors"]:
                raise RuntimeError("Ready Draft retained a submission blocker")

            status, result, _ = request(
                member,
                base_url,
                submit_path,
                payload={
                    "confirmation": "submit-for-review",
                    "expected_version": 1,
                    "idempotency_key": STALE_IDEMPOTENCY_KEY,
                },
                origin=base_url,
            )
            if status != HTTPStatus.CONFLICT or result.get("error", {}).get("code") != "DRAFT_VERSION_CONFLICT":
                raise RuntimeError("Draft Submit accepted a stale expected version")
            if FakeSupabaseHandler.submissions or FakeSupabaseHandler.submission_snapshot is not None:
                raise RuntimeError("Stale Draft Submit created a review snapshot")

            ready_submit_payload = {
                "confirmation": "submit-for-review",
                "expected_version": 2,
                "idempotency_key": SUBMIT_IDEMPOTENCY_KEY,
            }
            status, result, _ = request(
                member,
                base_url,
                submit_path,
                payload=ready_submit_payload,
                origin=base_url,
            )
            if status != HTTPStatus.CREATED:
                raise RuntimeError("Ready Draft could not be submitted")
            assert_safe_submit_response(result)
            if (
                FakeSupabaseHandler.draft_workflow_status != "submitted"
                or FakeSupabaseHandler.draft_lock_version != 3
                or FakeSupabaseHandler.draft_locked_at != SUBMITTED_AT
                or len(FakeSupabaseHandler.submissions) != 1
            ):
                raise RuntimeError("Successful Draft Submit did not atomically lock the workflow")
            snapshot = copy.deepcopy(FakeSupabaseHandler.submission_snapshot)
            if not snapshot or snapshot.get("id") != VERSION_ID or snapshot.get("locked_at") is not None:
                raise RuntimeError("Successful Draft Submit did not capture the immutable edited version")

            status, replay_result, _ = request(
                member,
                base_url,
                submit_path,
                payload=ready_submit_payload,
                origin=base_url,
            )
            if status != HTTPStatus.CREATED or replay_result != result:
                raise RuntimeError("Draft Submit idempotency retry did not return the original success")
            if len(FakeSupabaseHandler.submissions) != 1 or FakeSupabaseHandler.draft_lock_version != 3:
                raise RuntimeError("Draft Submit idempotency retry duplicated provider state")

            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}/draft",
                payload={"expected_version": 3, "draft": {"title": "Forbidden submitted edit"}},
                origin=base_url,
                method="PATCH",
            )
            if status != HTTPStatus.LOCKED or result.get("error", {}).get("code") != "DRAFT_LOCKED":
                raise RuntimeError("Submitted image remained editable as a Draft")
            status, result, _ = request(
                member,
                base_url,
                f"/api/images/{IMAGE_ID}",
                payload={"confirmation": "move-to-trash", "expected_version": 3},
                origin=base_url,
                method="DELETE",
            )
            if status != HTTPStatus.LOCKED or result.get("error", {}).get("code") != "DRAFT_LOCKED":
                raise RuntimeError("Submitted image could still be moved directly to Trash")
            if FakeSupabaseHandler.submission_snapshot != snapshot or len(FakeSupabaseHandler.submissions) != 1:
                raise RuntimeError("A rejected submitted-image mutation changed the immutable snapshot")

            status, result, _ = request(member, base_url, "/api/images?workflow_status=draft")
            if status != HTTPStatus.OK or result.get("images") != []:
                raise RuntimeError("Submitted image remained visible in the Draft list")

            sign_in(admin, base_url, "admin@example.test", "Admin-password-2026!")
            status, result, _ = request(admin, base_url, "/api/folders")
            if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "MFA_REQUIRED":
                raise RuntimeError("Admin AAL1 reached Phase 2 Workspace RPCs")

            if len([path for path in FakeSupabaseHandler.storage_calls if "/upload/sign/" in path]) != 6:
                raise RuntimeError("Each upload intent did not create exactly three signed destinations")

            print("workspace_folders_owner_boundary=yes")
            print("workspace_upload_intent_validation=yes")
            print("workspace_signed_upload_destinations=yes")
            print("workspace_upload_cancel_cleanup=yes")
            print("workspace_private_draft_hydration=yes")
            print("workspace_incomplete_draft_title=yes")
            print("workspace_draft_compliance_metadata=yes")
            print("workspace_draft_optimistic_concurrency=yes")
            print("workspace_draft_system_fields_rejected=yes")
            print("workspace_draft_trash_confirmation=yes")
            print("workspace_trash_list_restore=yes")
            print("workspace_restore_folder_fallback=yes")
            print("workspace_submit_readiness=yes")
            print("workspace_submit_csrf_boundary=yes")
            print("workspace_submit_optimistic_concurrency=yes")
            print("workspace_submit_idempotency=yes")
            print("workspace_submission_snapshot_locked=yes")
            print("workspace_submit_response_allowlist=yes")
            print("workspace_admin_aal1_denied=yes")
            print("workspace_session_tokens_exposed=no")
        finally:
            app_server.shutdown()
            app_server.server_close()
    fake_server.shutdown()
    fake_server.server_close()


if __name__ == "__main__":
    main()
