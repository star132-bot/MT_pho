#!/usr/bin/env python3
"""Secret-free HTTP integration test for the protected user Dashboard."""

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
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
USER_ID = "81000000-0000-4000-8000-000000000001"
IMAGE_ID = "82000000-0000-4000-8000-000000000001"
ASSET_ID = "83000000-0000-4000-8000-000000000001"
SUBMISSION_ID = "84000000-0000-4000-8000-000000000001"
COVER_IMAGE_ID = "82000000-0000-4000-8000-000000000002"
COVER_ASSET_ID = "83000000-0000-4000-8000-000000000002"
AVATAR_UPLOAD_IDS = (
    "86000000-0000-4000-8000-000000000001",
    "86000000-0000-4000-8000-000000000002",
    "86000000-0000-4000-8000-000000000003",
)
AVATAR_JPEG = b"\xff\xd8mt-avatar-boundary\xff\xd9"


def fake_access_token() -> str:
    now = int(time.time())
    claims = {
        "aal": "aal1",
        "amr": [{"method": "password"}],
        "session_id": "85000000-0000-4000-8000-000000000001",
        "iat": now - 10,
        "exp": now + 3600,
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


ACCESS_TOKEN = fake_access_token()


def dashboard_image() -> dict:
    return {
        "id": IMAGE_ID,
        "title": "Quiet Field",
        "original_filename": "quiet-field.jpg",
        "processing_status": "ready",
        "workflow_status": "draft",
        "publication_status": "never_published",
        "updated_at": "2026-07-22T02:15:00Z",
        "owner_user_id": USER_ID,
        "thumbnail_asset": {
            "id": ASSET_ID,
            "kind": "thumbnail",
            "storage_bucket": "image-thumbnails",
            "storage_key": f"{USER_ID}/{IMAGE_ID}/thumbnail.jpg",
            "mime_type": "image/jpeg",
            "byte_size": 48120,
            "width": 640,
            "height": 426,
            "scan_status": "clean",
            "scan_policy_version": "mt-asset-scan-2026-07-v1",
            "scan_result_code": "clean",
            "provider_debug": "must-not-leak",
        },
    }


def dashboard_payload() -> dict:
    image = dashboard_image()
    return {
        "status_counts": {
            "drafts": 1,
            "submitted": 2,
            "changes_requested": 1,
            "published": 3,
            "unpublished": 1,
            "internal_total": 99,
        },
        "needs_attention": [{
            "type": "changes_requested",
            "image_id": IMAGE_ID,
            "title": "Quiet Field",
            "message": "A reviewer requested updates before this work can continue.",
            "updated_at": "2026-07-22T02:10:00Z",
            "workspace_path": "/workspace/images",
            "reviewer_id": "private-provider-field",
        }],
        "recent_images": [copy.deepcopy(image)],
        "drafts": [copy.deepcopy(image)],
        "review_activity": [{
            "submission_id": SUBMISSION_ID,
            "image_id": IMAGE_ID,
            "title": "Quiet Field",
            "status": "escalated",
            "decision": "quarantine",
            "submitted_at": "2026-07-21T01:00:00Z",
            "review_started_at": "2026-07-21T01:10:00Z",
            "completed_at": None,
            "occurred_at": "2026-07-21T01:20:00Z",
            "internal_note": "must-not-leak",
        }],
        "storage_usage": {
            "used_bytes": 1357000,
            "asset_count": 3,
            "image_count": 1,
            "quota_bytes": None,
            "bucket_breakdown": {"image-originals": 1},
        },
        "capabilities": {
            "storage_quota": {"available": False, "reason": "not_configured", "internal": True},
            "public_portfolio": {"available": False, "reason": "public_delivery_not_connected"},
        },
        "generated_at": "2026-07-22T02:30:00Z",
        "provider_debug": "must-not-leak",
    }


def profile_payload() -> dict:
    return {
        "display_name": "Dashboard Member",
        "avatar_url": None,
        "bio": "Photographs shaped by weather and distance.",
        "website_url": "https://example.test",
        "country_code": "CN",
        "preferred_locale": "en",
        "timezone": "Asia/Shanghai",
        "copyright_name": "Dashboard Member",
        "default_license_preference": "all-rights-reserved",
        "professional_headline": "Photographer and visual artist",
        "company": "North Window Studio",
        "city": "Shanghai",
        "availability_status": "open",
        "instagram_url": "https://www.instagram.com/dashboard.member",
        "linkedin_url": "https://www.linkedin.com/in/dashboard-member",
        "avatar_storage_bucket": None,
        "avatar_storage_key": None,
        "avatar_mime_type": None,
        "avatar_byte_size": None,
        "avatar_width": None,
        "avatar_height": None,
        "avatar_updated_at": None,
    }


def profile_avatar_asset(upload_id: str, byte_size: int | None = None) -> dict:
    return {
        "storage_bucket": "profile-avatars",
        "storage_key": f"{USER_ID}/{upload_id}/avatar.jpg",
        "mime_type": "image/jpeg",
        "byte_size": byte_size if byte_size is not None else len(AVATAR_JPEG),
        "width": 512,
        "height": 512,
    }


def stored_profile_avatar(profile: dict) -> dict | None:
    if not profile.get("avatar_storage_key"):
        return None
    return {
        "storage_bucket": profile.get("avatar_storage_bucket"),
        "storage_key": profile.get("avatar_storage_key"),
        "mime_type": profile.get("avatar_mime_type"),
        "byte_size": profile.get("avatar_byte_size"),
        "width": profile.get("avatar_width"),
        "height": profile.get("avatar_height"),
    }


def profile_cover_asset(
    *,
    asset_id: str = COVER_ASSET_ID,
    image_id: str = COVER_IMAGE_ID,
    kind: str = "display",
    storage_key: str | None = None,
) -> dict:
    bucket = "image-display" if kind == "display" else "image-thumbnails"
    return {
        "id": asset_id,
        "image_id": image_id,
        "title": "Blue Hour",
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": storage_key or f"{USER_ID}/{image_id}/{kind}.jpg",
        "mime_type": "image/jpeg",
        "width": 2400 if kind == "display" else 640,
        "height": 960 if kind == "display" else 426,
        "scan_status": "clean",
        "scan_result_code": "clean",
        "scan_policy_version": "mt-asset-scan-2026-07-v1",
        "owner_user_id": USER_ID,
        "provider_debug": "must-not-leak",
    }


def profile_cover_payload() -> dict:
    selected = profile_cover_asset()
    thumbnail = profile_cover_asset(
        asset_id=ASSET_ID,
        image_id=IMAGE_ID,
        kind="thumbnail",
    )
    return {
        "cover_asset": copy.deepcopy(selected),
        "candidates": [copy.deepcopy(selected), thumbnail],
        "provider_debug": "must-not-leak",
    }


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    dashboard = dashboard_payload()
    profile = profile_payload()
    profile_cover = profile_cover_payload()
    rpc_calls: list[str] = []
    storage_calls: list[str] = []
    profile_update_calls: list[dict] = []
    cover_update_calls: list[dict] = []
    avatar_intent_ids: list[str] = list(AVATAR_UPLOAD_IDS)
    avatar_intents: dict[str, dict] = {}
    avatar_create_calls: list[dict] = []
    avatar_complete_calls: list[dict] = []
    avatar_cancel_calls: list[dict] = []
    avatar_remove_calls: list[dict] = []
    avatar_upload_calls: list[str] = []
    avatar_storage_delete_calls: list[str] = []
    fail_next_storage_signatures = 0
    logout_calls = 0

    def log_message(self, _format, *_args) -> None:
        return

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if not self.path.startswith("/storage/v1/object/upload/sign/profile-avatars/"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, x-upsert")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:
        authorization = self.headers.get("Authorization")
        parsed = urlparse(self.path)
        avatar_read_prefix = "/storage/v1/object/sign/profile-avatars/"
        if parsed.path.startswith(avatar_read_prefix) and parsed.query == "token=profile-avatar-read":
            storage_key = parsed.path.removeprefix(avatar_read_prefix)
            upload = next((
                intent
                for intent in type(self).avatar_intents.values()
                if intent.get("storage_key") == storage_key
            ), None)
            uploaded_bytes = upload.get("uploaded_bytes") if isinstance(upload, dict) else None
            if not isinstance(uploaded_bytes, bytes) or upload.get("status") != "completed":
                self.send_json(HTTPStatus.NOT_FOUND, {})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(uploaded_bytes)))
            self.end_headers()
            self.wfile.write(uploaded_bytes)
            return
        if self.path == "/auth/v1/user" and authorization == f"Bearer {ACCESS_TOKEN}":
            self.send_json(HTTPStatus.OK, {
                "id": USER_ID,
                "email": "dashboard@example.test",
                "email_confirmed_at": "2026-07-20T00:00:00Z",
                "factors": [],
            })
            return
        if urlparse(self.path).path == "/rest/v1/user_profiles" and authorization == f"Bearer {ACCESS_TOKEN}":
            self.send_json(HTTPStatus.OK, [copy.deepcopy(type(self).profile)])
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        prefix = "/storage/v1/object/upload/sign/profile-avatars/"
        if not parsed.path.startswith(prefix) or parsed.query != "token=profile-avatar-upload":
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        storage_key = parsed.path.removeprefix(prefix)
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        content_type = self.headers.get_content_type()
        uploaded_bytes = body
        if content_type == "multipart/form-data":
            boundary = self.headers.get_boundary()
            uploaded_bytes = b""
            if boundary:
                marker = f"--{boundary}".encode()
                for part in body.split(marker):
                    headers, separator, payload = part.partition(b"\r\n\r\n")
                    if (
                        separator
                        and b'filename="avatar.jpg"' in headers
                        and b"Content-Type: image/jpeg" in headers
                    ):
                        uploaded_bytes = payload[:-2] if payload.endswith(b"\r\n") else payload
                        break
        upload = next((
            intent
            for intent in type(self).avatar_intents.values()
            if intent.get("storage_key") == storage_key
        ), None)
        if (
            upload is None
            or upload.get("status") != "issued"
            or content_type not in {"image/jpeg", "multipart/form-data"}
            or len(uploaded_bytes) != upload.get("byte_size")
        ):
            self.send_json(HTTPStatus.BAD_REQUEST, {})
            return
        upload["uploaded"] = True
        upload["uploaded_bytes"] = uploaded_bytes
        type(self).avatar_upload_calls.append(storage_key)
        self.send_json(HTTPStatus.OK, {"Key": storage_key})

    def do_POST(self) -> None:
        authorization = self.headers.get("Authorization")
        if self.path == "/auth/v1/token?grant_type=password":
            body = self.body()
            if body != {"email": "dashboard@example.test", "password": "Dashboard-password-2026!"}:
                self.send_json(HTTPStatus.BAD_REQUEST, {"message": "invalid credentials"})
                return
            self.send_json(HTTPStatus.OK, {
                "access_token": ACCESS_TOKEN,
                "refresh_token": "dashboard-refresh-token",
                "expires_in": 3600,
                "user": {
                    "id": USER_ID,
                    "email": "dashboard@example.test",
                    "email_confirmed_at": "2026-07-20T00:00:00Z",
                },
            })
            return
        if self.path == "/auth/v1/logout?scope=local":
            self.body()
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            type(self).logout_calls += 1
            self.send_json(HTTPStatus.OK, {})
            return
        if self.path == "/rest/v1/rpc/current_authorization":
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            self.send_json(HTTPStatus.OK, {
                "user_id": USER_ID,
                "account_status": "active",
                "roles": ["user"],
                "aal": "aal1",
            })
            return
        if self.path == "/rest/v1/rpc/get_my_dashboard":
            self.body()
            type(self).rpc_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            self.send_json(HTTPStatus.OK, copy.deepcopy(type(self).dashboard))
            return
        if self.path == "/rest/v1/rpc/get_my_notification_unread_count":
            self.body()
            type(self).rpc_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            self.send_json(HTTPStatus.OK, {"unread_count": 0})
            return
        if self.path == "/rest/v1/rpc/update_my_profile":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).profile_update_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            patch = body.get("profile_patch") if isinstance(body, dict) else None
            if not isinstance(patch, dict):
                self.send_json(HTTPStatus.BAD_REQUEST, {})
                return
            type(self).profile = {**type(self).profile, **patch}
            self.send_json(HTTPStatus.OK, copy.deepcopy(type(self).profile))
            return
        if self.path == "/rest/v1/rpc/create_my_profile_avatar_upload":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).avatar_create_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            if not type(self).avatar_intent_ids:
                self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {})
                return
            upload_id = type(self).avatar_intent_ids.pop(0)
            intent = {
                "upload_id": upload_id,
                **profile_avatar_asset(upload_id, body.get("avatar_byte_size")),
                "expires_at": "2026-07-23T11:30:00Z",
                "superseded_uploads": [],
                "status": "issued",
                "uploaded": False,
            }
            type(self).avatar_intents[upload_id] = intent
            self.send_json(HTTPStatus.OK, {
                key: copy.deepcopy(value)
                for key, value in intent.items()
                if key not in {"status", "uploaded"}
            })
            return
        if self.path == "/rest/v1/rpc/complete_my_profile_avatar_upload":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).avatar_complete_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            upload = type(self).avatar_intents.get(body.get("upload_id"))
            if not upload or upload.get("status") != "issued" or upload.get("uploaded") is not True:
                self.send_json(HTTPStatus.OK, {
                    "error": {
                        "code": "PROFILE_AVATAR_UPLOAD_INCOMPLETE",
                        "message": "The profile photo upload is incomplete.",
                    }
                })
                return
            previous = stored_profile_avatar(type(self).profile)
            avatar = {
                key: upload[key]
                for key in ("storage_bucket", "storage_key", "mime_type", "byte_size", "width", "height")
            }
            type(self).profile.update({
                "avatar_url": None,
                "avatar_storage_bucket": avatar["storage_bucket"],
                "avatar_storage_key": avatar["storage_key"],
                "avatar_mime_type": avatar["mime_type"],
                "avatar_byte_size": avatar["byte_size"],
                "avatar_width": avatar["width"],
                "avatar_height": avatar["height"],
                "avatar_updated_at": "2026-07-23T11:00:00Z",
            })
            upload["status"] = "completed"
            self.send_json(HTTPStatus.OK, {
                "avatar": avatar,
                "previous_avatar": previous,
                "replayed": False,
            })
            return
        if self.path == "/rest/v1/rpc/cancel_my_profile_avatar_upload":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).avatar_cancel_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            upload = type(self).avatar_intents.get(body.get("upload_id"))
            if not upload or upload.get("status") != "issued":
                self.send_json(HTTPStatus.OK, {
                    "error": {
                        "code": "PROFILE_AVATAR_UPLOAD_NOT_FOUND",
                        "message": "The profile photo upload is unavailable.",
                    }
                })
                return
            upload["status"] = "canceled"
            self.send_json(HTTPStatus.OK, {
                "canceled": True,
                "status": "canceled",
                "upload": {
                    "upload_id": upload["upload_id"],
                    "storage_bucket": upload["storage_bucket"],
                    "storage_key": upload["storage_key"],
                },
            })
            return
        if self.path == "/rest/v1/rpc/remove_my_profile_avatar":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).avatar_remove_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            previous = stored_profile_avatar(type(self).profile)
            canceled_uploads = []
            for upload in type(self).avatar_intents.values():
                if upload.get("status") != "issued":
                    continue
                upload["status"] = "canceled"
                canceled_uploads.append({
                    "upload_id": upload["upload_id"],
                    "storage_bucket": upload["storage_bucket"],
                    "storage_key": upload["storage_key"],
                })
            type(self).profile.update({
                "avatar_url": None,
                "avatar_storage_bucket": None,
                "avatar_storage_key": None,
                "avatar_mime_type": None,
                "avatar_byte_size": None,
                "avatar_width": None,
                "avatar_height": None,
                "avatar_updated_at": None,
            })
            self.send_json(HTTPStatus.OK, {
                "removed": previous is not None,
                "previous_avatar": previous,
                "canceled_uploads": canceled_uploads,
            })
            return
        if self.path == "/rest/v1/rpc/get_my_profile_cover":
            self.body()
            type(self).rpc_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            self.send_json(HTTPStatus.OK, copy.deepcopy(type(self).profile_cover))
            return
        if self.path == "/rest/v1/rpc/set_my_profile_cover":
            body = self.body()
            type(self).rpc_calls.append(self.path)
            type(self).cover_update_calls.append(copy.deepcopy(body))
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            target_asset_id = body.get("target_asset_id")
            if target_asset_id is None:
                type(self).profile_cover["cover_asset"] = None
                self.send_json(HTTPStatus.OK, {"cover_asset": None, "saved": True})
                return
            selected = next((
                candidate
                for candidate in type(self).profile_cover.get("candidates", [])
                if candidate.get("id") == target_asset_id
            ), None)
            if selected is None:
                self.send_json(HTTPStatus.OK, {
                    "error": {
                        "code": "PROFILE_COVER_NOT_AVAILABLE",
                        "message": "Choose one of your current scanner-approved image assets.",
                    }
                })
                return
            type(self).profile_cover["cover_asset"] = copy.deepcopy(selected)
            self.send_json(HTTPStatus.OK, {"cover_asset": copy.deepcopy(selected), "saved": True})
            return
        if self.path.startswith("/storage/v1/object/upload/sign/profile-avatars/"):
            self.body()
            type(self).storage_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"url": f"{suffix}?token=profile-avatar-upload"})
            return
        if self.path.startswith("/storage/v1/object/sign/profile-avatars/"):
            self.body()
            type(self).storage_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=profile-avatar-read"})
            return
        if self.path == "/storage/v1/bucket/profile-avatars/delete":
            body = self.body()
            type(self).storage_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            prefixes = body.get("prefixes") if isinstance(body, dict) else None
            if not isinstance(prefixes, list) or any(not isinstance(key, str) for key in prefixes):
                self.send_json(HTTPStatus.BAD_REQUEST, {})
                return
            type(self).avatar_storage_delete_calls.extend(prefixes)
            self.send_json(HTTPStatus.OK, {"message": "Successfully deleted"})
            return
        if (
            self.path.startswith("/storage/v1/object/sign/image-thumbnails/")
            or self.path.startswith("/storage/v1/object/sign/image-display/")
        ):
            self.body()
            type(self).storage_calls.append(self.path)
            if authorization != f"Bearer {ACCESS_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            if type(self).fail_next_storage_signatures > 0:
                type(self).fail_next_storage_signatures -= 1
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {})
                return
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=private-signed-read"})
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
    include_csrf: bool = True,
    method: str | None = None,
):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
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
            value = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else raw.decode()
            return response.status, value, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        value = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else raw.decode()
        return error.code, value, error.headers


def upload_signed_avatar(signed_url: str) -> int:
    upload = urllib.request.Request(
        signed_url,
        data=AVATAR_JPEG,
        headers={"Content-Type": "image/jpeg"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(upload, timeout=10) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


def sign_in(opener, base_url: str) -> None:
    status, csrf, _ = request(opener, base_url, "/api/auth/csrf")
    if status != HTTPStatus.OK or not csrf.get("csrf_token"):
        raise RuntimeError("Dashboard test could not initialize CSRF")
    status, result, _ = request(
        opener,
        base_url,
        "/api/auth/sign-in",
        payload={"email": "dashboard@example.test", "password": "Dashboard-password-2026!"},
        origin=base_url,
    )
    if status != HTTPStatus.OK or result.get("next_action") != "workspace":
        raise RuntimeError("Dashboard test could not establish a member session")


def assert_private_fields_absent(payload: dict) -> None:
    serialized = json.dumps(payload)
    for forbidden in ("storage_bucket", "storage_key", "provider_debug", "internal_note", "owner_user_id", "reviewer_id"):
        if forbidden in serialized:
            raise RuntimeError(f"Dashboard response leaked provider-only field: {forbidden}")


def main() -> None:
    FakeSupabaseHandler.dashboard = dashboard_payload()
    FakeSupabaseHandler.profile = profile_payload()
    FakeSupabaseHandler.profile_cover = profile_cover_payload()
    FakeSupabaseHandler.rpc_calls = []
    FakeSupabaseHandler.storage_calls = []
    FakeSupabaseHandler.profile_update_calls = []
    FakeSupabaseHandler.cover_update_calls = []
    FakeSupabaseHandler.avatar_intent_ids = list(AVATAR_UPLOAD_IDS)
    FakeSupabaseHandler.avatar_intents = {}
    FakeSupabaseHandler.avatar_create_calls = []
    FakeSupabaseHandler.avatar_complete_calls = []
    FakeSupabaseHandler.avatar_cancel_calls = []
    FakeSupabaseHandler.avatar_remove_calls = []
    FakeSupabaseHandler.avatar_upload_calls = []
    FakeSupabaseHandler.avatar_storage_delete_calls = []
    FakeSupabaseHandler.fail_next_storage_signatures = 0
    FakeSupabaseHandler.logout_calls = 0
    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{fake_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "dashboard-test-key"
    os.environ["MT_PUBLIC_BASE_URL"] = ""
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")
    handler = partial(app.MTRequestHandler, directory=str(ROOT))
    app_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    base_url = f"http://127.0.0.1:{app_server.server_address[1]}"

    try:
        avatar_request = {
            "mime_type": "image/jpeg",
            "byte_size": len(AVATAR_JPEG),
            "width": 512,
            "height": 512,
        }
        anonymous = CookieOpener()
        status, _, headers = request(anonymous, base_url, "/dashboard")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/auth/sign-in?next=%2Fdashboard":
            raise RuntimeError("Anonymous Dashboard route did not preserve the canonical return path")
        status, _, headers = request(anonymous, base_url, "/dashboard.html")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/dashboard":
            raise RuntimeError("Direct Dashboard HTML route did not canonicalize")
        status, result, _ = request(anonymous, base_url, "/api/dashboard")
        if status != HTTPStatus.UNAUTHORIZED or result.get("error", {}).get("code") != "AUTH_REQUIRED":
            raise RuntimeError("Anonymous Dashboard API request was not rejected")
        status, result, _ = request(anonymous, base_url, "/api/me/profile/cover")
        if status != HTTPStatus.UNAUTHORIZED or result.get("error", {}).get("code") != "AUTH_REQUIRED":
            raise RuntimeError("Anonymous profile cover request was not rejected")
        status, csrf, _ = request(anonymous, base_url, "/api/auth/csrf")
        if status != HTTPStatus.OK or not csrf.get("csrf_token"):
            raise RuntimeError("Anonymous avatar test could not initialize CSRF")
        status, result, _ = request(
            anonymous,
            base_url,
            "/api/me/profile/avatar/intents",
            payload=avatar_request,
            origin=base_url,
        )
        if (
            status != HTTPStatus.UNAUTHORIZED
            or result.get("error", {}).get("code") != "AUTH_REQUIRED"
            or FakeSupabaseHandler.avatar_create_calls
        ):
            raise RuntimeError("Anonymous profile avatar intent was not rejected before provider access")

        member = CookieOpener()
        sign_in(member, base_url)
        status, _, headers = request(member, base_url, "/workspace")
        if status != HTTPStatus.SEE_OTHER or headers.get("Location") != "/dashboard":
            raise RuntimeError("Legacy Workspace root did not canonicalize to Dashboard")
        status, page, _ = request(member, base_url, "/dashboard")
        if (
            status != HTTPStatus.OK
            or 'data-dashboard-status-grid' not in page
            or 'src="/account-menu.js' not in page
            or 'data-dashboard-cover-open' not in page
            or 'href="/settings/account#profile">Edit profile</a>' not in page
        ):
            raise RuntimeError("Protected Dashboard page did not serve its complete UI shell")

        status, profile, _ = request(member, base_url, "/api/me/profile")
        creator = profile.get("profile", {})
        if (
            status != HTTPStatus.OK
            or creator.get("display_name") != "Dashboard Member"
            or creator.get("professional_headline") != "Photographer and visual artist"
            or creator.get("availability_status") != "open"
            or creator.get("instagram_url") != "https://www.instagram.com/dashboard.member"
        ):
            raise RuntimeError("Dashboard profile endpoint did not return the signed-in identity")

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile",
            payload={"linkedin_url": "https://example.test/not-linkedin"},
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.UNPROCESSABLE_ENTITY
            or result.get("error", {}).get("code") != "PROFILE_VALIDATION_FAILED"
            or FakeSupabaseHandler.profile_update_calls
        ):
            raise RuntimeError("Creator profile accepted a social URL outside its official HTTPS host")

        creator_patch = {
            "professional_headline": "Editorial photographer",
            "company": "Field Notes Studio",
            "city": "Hangzhou",
            "availability_status": "limited",
            "instagram_url": "https://Instagram.com/Field.Notes",
            "linkedin_url": "https://WWW.LinkedIn.com/in/field-notes",
        }
        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile",
            payload=creator_patch,
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.OK
            or result.get("saved") is not True
            or result.get("profile", {}).get("availability_status") != "limited"
            or result.get("profile", {}).get("instagram_url") != "https://Instagram.com/Field.Notes"
            or FakeSupabaseHandler.profile_update_calls != [{"profile_patch": creator_patch}]
        ):
            raise RuntimeError("Creator profile fields were not normalized and persisted through the strict RPC")

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/avatar/intents",
            payload=avatar_request,
            origin=base_url,
            include_csrf=False,
        )
        if (
            status != HTTPStatus.FORBIDDEN
            or result.get("error", {}).get("code") != "CSRF_REJECTED"
            or FakeSupabaseHandler.avatar_create_calls
        ):
            raise RuntimeError("Profile avatar intent reached the provider without CSRF protection")

        status, intent_payload, _ = request(
            member,
            base_url,
            "/api/me/profile/avatar/intents",
            payload=avatar_request,
            origin=base_url,
        )
        upload = intent_payload.get("upload") or {}
        first_upload_id = AVATAR_UPLOAD_IDS[0]
        first_storage_key = profile_avatar_asset(first_upload_id)["storage_key"]
        signed_upload = urlparse(upload.get("signed_url") or "")
        expected_create_call = {
            "avatar_mime_type": "image/jpeg",
            "avatar_byte_size": len(AVATAR_JPEG),
            "avatar_width": 512,
            "avatar_height": 512,
        }
        if (
            status != HTTPStatus.CREATED
            or set(upload) != {
                "id", "signed_url", "mime_type", "byte_size", "width", "height", "expires_at",
            }
            or upload.get("id") != first_upload_id
            or signed_upload.path != f"/storage/v1/object/upload/sign/profile-avatars/{first_storage_key}"
            or signed_upload.query != "token=profile-avatar-upload"
            or FakeSupabaseHandler.avatar_create_calls != [expected_create_call]
        ):
            raise RuntimeError("Profile avatar intent did not return its strict owner-bound signed upload DTO")
        assert_private_fields_absent(intent_payload)

        if upload_signed_avatar(upload["signed_url"]) != HTTPStatus.OK:
            raise RuntimeError("Profile avatar signed upload URL did not accept the prepared JPEG")
        if FakeSupabaseHandler.avatar_upload_calls != [first_storage_key]:
            raise RuntimeError("Profile avatar upload was not isolated to the current account path")

        status, completed, _ = request(
            member,
            base_url,
            f"/api/me/profile/avatar/intents/{first_upload_id}/complete",
            payload={"confirmation": "complete-profile-avatar"},
            origin=base_url,
        )
        completed_profile = completed.get("profile") or {}
        signed_read = urlparse(completed_profile.get("avatar_url") or "")
        if (
            status != HTTPStatus.OK
            or completed.get("saved") is not True
            or signed_read.path != f"/storage/v1/object/sign/profile-avatars/{first_storage_key}"
            or signed_read.query != "token=profile-avatar-read"
            or FakeSupabaseHandler.avatar_complete_calls != [{"upload_id": first_upload_id}]
        ):
            raise RuntimeError("Completed profile avatar was not exposed through an owner-bound signed read URL")
        assert_private_fields_absent(completed)

        status, signed_profile_payload, _ = request(member, base_url, "/api/me/profile")
        signed_profile = signed_profile_payload.get("profile") or {}
        if (
            status != HTTPStatus.OK
            or urlparse(signed_profile.get("avatar_url") or "").path
            != f"/storage/v1/object/sign/profile-avatars/{first_storage_key}"
        ):
            raise RuntimeError("Profile reload did not preserve the signed stable avatar")
        assert_private_fields_absent(signed_profile_payload)

        status, cancel_intent_payload, _ = request(
            member,
            base_url,
            "/api/me/profile/avatar/intents",
            payload=avatar_request,
            origin=base_url,
        )
        second_upload_id = AVATAR_UPLOAD_IDS[1]
        second_storage_key = profile_avatar_asset(second_upload_id)["storage_key"]
        if status != HTTPStatus.CREATED or cancel_intent_payload.get("upload", {}).get("id") != second_upload_id:
            raise RuntimeError("Profile avatar cancellation fixture could not create an upload intent")
        assert_private_fields_absent(cancel_intent_payload)

        status, canceled, _ = request(
            member,
            base_url,
            f"/api/me/profile/avatar/intents/{second_upload_id}",
            payload={"confirmation": "cancel-profile-avatar"},
            origin=base_url,
            method="DELETE",
        )
        if (
            status != HTTPStatus.OK
            or canceled != {"canceled": True}
            or FakeSupabaseHandler.avatar_cancel_calls != [{"upload_id": second_upload_id}]
            or FakeSupabaseHandler.avatar_storage_delete_calls != [second_storage_key]
        ):
            raise RuntimeError("Canceled profile avatar intent did not clean up its storage object")
        assert_private_fields_absent(canceled)

        status, pending_intent_payload, _ = request(
            member,
            base_url,
            "/api/me/profile/avatar/intents",
            payload=avatar_request,
            origin=base_url,
        )
        third_upload_id = AVATAR_UPLOAD_IDS[2]
        third_storage_key = profile_avatar_asset(third_upload_id)["storage_key"]
        if status != HTTPStatus.CREATED or pending_intent_payload.get("upload", {}).get("id") != third_upload_id:
            raise RuntimeError("Profile avatar removal fixture could not create its pending intent")
        assert_private_fields_absent(pending_intent_payload)

        status, removed, _ = request(
            member,
            base_url,
            "/api/me/profile/avatar",
            payload={"confirmation": "remove-profile-avatar"},
            origin=base_url,
            method="DELETE",
        )
        removed_profile = removed.get("profile") or {}
        expected_cleanup = [second_storage_key, first_storage_key, third_storage_key]
        if (
            status != HTTPStatus.OK
            or removed.get("removed") is not True
            or removed_profile.get("avatar_url") is not None
            or FakeSupabaseHandler.avatar_remove_calls != [{}]
            or sorted(FakeSupabaseHandler.avatar_storage_delete_calls) != sorted(expected_cleanup)
            or len(FakeSupabaseHandler.avatar_storage_delete_calls) != len(expected_cleanup)
            or any(not key.startswith(f"{USER_ID}/") for key in FakeSupabaseHandler.avatar_storage_delete_calls)
        ):
            raise RuntimeError("Profile avatar removal did not clear the active and pending owner storage objects")
        assert_private_fields_absent(removed)

        status, fallback_profile_payload, _ = request(member, base_url, "/api/me/profile")
        if status != HTTPStatus.OK or fallback_profile_payload.get("profile", {}).get("avatar_url") is not None:
            raise RuntimeError("Removed profile avatar remained visible through the profile endpoint")
        assert_private_fields_absent(fallback_profile_payload)
        status, fallback_page, _ = request(member, base_url, "/dashboard")
        if (
            status != HTTPStatus.OK
            or '"initials":"DM"' not in fallback_page
            or '<span data-account-menu-initials aria-hidden="true">DM</span>' not in fallback_page
            or "data-account-menu-image />" in fallback_page
        ):
            raise RuntimeError("Profile avatar removal did not return the header to its first-frame initials fallback")

        FakeSupabaseHandler.storage_calls = []

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": COVER_ASSET_ID},
            origin=base_url,
            include_csrf=False,
            method="PATCH",
        )
        if (
            status != HTTPStatus.FORBIDDEN
            or result.get("error", {}).get("code") != "CSRF_REJECTED"
            or FakeSupabaseHandler.cover_update_calls
        ):
            raise RuntimeError("Profile cover update reached the provider without CSRF protection")

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": "not-an-asset-id"},
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.UNPROCESSABLE_ENTITY
            or result.get("error", {}).get("code") != "PROFILE_COVER_VALIDATION_FAILED"
            or FakeSupabaseHandler.cover_update_calls
        ):
            raise RuntimeError("Profile cover accepted an invalid asset identifier")

        status, cover_payload, _ = request(member, base_url, "/api/me/profile/cover")
        cover = cover_payload.get("cover") or {}
        candidates = cover_payload.get("candidates") or []
        cover_keys = {
            "id", "image_id", "title", "kind", "mime_type",
            "width", "height", "signed_url", "expires_in",
        }
        if (
            status != HTTPStatus.OK
            or set(cover) != cover_keys
            or len(candidates) != 2
            or any(set(candidate) != cover_keys for candidate in candidates)
            or cover.get("id") != COVER_ASSET_ID
            or not cover.get("signed_url")
            or len(FakeSupabaseHandler.storage_calls) != 2
        ):
            raise RuntimeError("Profile cover endpoint did not project and sign its stable private DTO")
        assert_private_fields_absent(cover_payload)

        wrong_owner_cover = profile_cover_payload()
        wrong_owner_cover["cover_asset"]["storage_key"] = (
            f"00000000-0000-4000-8000-000000000099/{COVER_IMAGE_ID}/display.jpg"
        )
        FakeSupabaseHandler.profile_cover = wrong_owner_cover
        status, result, _ = request(member, base_url, "/api/me/profile/cover")
        if (
            status != HTTPStatus.BAD_GATEWAY
            or result.get("error", {}).get("code") != "PROFILE_COVER_ASSET_UNAVAILABLE"
        ):
            raise RuntimeError("Profile cover attempted to sign an asset outside the account prefix")

        mismatched_bucket_cover = profile_cover_payload()
        mismatched_bucket_cover["cover_asset"]["storage_bucket"] = "image-thumbnails"
        FakeSupabaseHandler.profile_cover = mismatched_bucket_cover
        status, result, _ = request(member, base_url, "/api/me/profile/cover")
        if (
            status != HTTPStatus.BAD_GATEWAY
            or result.get("error", {}).get("code") != "PROFILE_COVER_PROVIDER_FAILED"
        ):
            raise RuntimeError("Profile cover accepted a provider bucket that did not match its asset kind")
        FakeSupabaseHandler.profile_cover = profile_cover_payload()

        unavailable_asset_id = "83000000-0000-4000-8000-000000000099"
        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": unavailable_asset_id},
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.UNPROCESSABLE_ENTITY
            or result.get("error", {}).get("code") != "PROFILE_COVER_NOT_AVAILABLE"
        ):
            raise RuntimeError("Profile cover accepted an unavailable or cross-owner asset")

        FakeSupabaseHandler.fail_next_storage_signatures = 1
        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": ASSET_ID},
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.OK
            or result != {"cover": None, "saved": True}
            or FakeSupabaseHandler.profile_cover.get("cover_asset", {}).get("id") != ASSET_ID
        ):
            raise RuntimeError("Profile cover misreported a committed save after preview signing failed")

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": COVER_ASSET_ID},
            origin=base_url,
            method="PATCH",
        )
        if (
            status != HTTPStatus.OK
            or result.get("saved") is not True
            or set(result.get("cover") or {}) != cover_keys
            or result.get("cover", {}).get("id") != COVER_ASSET_ID
        ):
            raise RuntimeError("Profile cover could not select an approved owner asset")

        status, result, _ = request(
            member,
            base_url,
            "/api/me/profile/cover",
            payload={"asset_id": None},
            origin=base_url,
            method="PATCH",
        )
        if status != HTTPStatus.OK or result != {"cover": None, "saved": True}:
            raise RuntimeError("Profile cover could not be cleared")

        FakeSupabaseHandler.rpc_calls = []
        FakeSupabaseHandler.storage_calls = []
        status, payload, _ = request(member, base_url, "/api/dashboard")
        if status != HTTPStatus.OK:
            raise RuntimeError(f"Dashboard aggregate endpoint failed with {status}")
        expected_keys = {
            "status_counts", "needs_attention", "recent_images", "drafts",
            "review_activity", "storage_usage", "capabilities", "generated_at",
        }
        if set(payload) != expected_keys or payload["status_counts"]["drafts"] != 1:
            raise RuntimeError("Dashboard endpoint did not project the stable aggregate DTO")
        if payload["review_activity"][0].get("decision") != "quarantine":
            raise RuntimeError("Dashboard rejected a valid review activity decision")
        recent = payload["recent_images"][0]
        if set(recent) != {
            "id", "title", "original_filename", "processing_status", "workflow_status",
            "publication_status", "updated_at", "thumbnail",
        } or not recent.get("thumbnail", {}).get("signed_url"):
            raise RuntimeError("Dashboard image preview was not projected and signed")
        if len(FakeSupabaseHandler.rpc_calls) != 1 or len(FakeSupabaseHandler.storage_calls) != 1:
            raise RuntimeError("Dashboard did not use one aggregate RPC and one cached thumbnail signature")
        assert_private_fields_absent(payload)

        invalid = dashboard_payload()
        invalid["status_counts"]["drafts"] = -1
        FakeSupabaseHandler.dashboard = invalid
        status, result, _ = request(member, base_url, "/api/dashboard")
        if status != HTTPStatus.BAD_GATEWAY or result.get("error", {}).get("code") != "DASHBOARD_PROVIDER_FAILED":
            raise RuntimeError("Dashboard accepted an invalid provider aggregate")

        wrong_owner = dashboard_payload()
        for section in ("recent_images", "drafts"):
            wrong_owner[section][0]["thumbnail_asset"]["storage_key"] = f"00000000-0000-4000-8000-000000000099/{IMAGE_ID}/thumbnail.jpg"
        FakeSupabaseHandler.dashboard = wrong_owner
        status, result, _ = request(member, base_url, "/api/dashboard")
        if status != HTTPStatus.BAD_GATEWAY or result.get("error", {}).get("code") != "DASHBOARD_ASSET_UNAVAILABLE":
            raise RuntimeError("Dashboard attempted to sign a provider asset outside the account prefix")

        status, result, _ = request(
            member,
            base_url,
            "/api/auth/sign-out",
            payload={},
            origin=base_url,
            include_csrf=False,
        )
        if status != HTTPStatus.FORBIDDEN or result.get("error", {}).get("code") != "CSRF_REJECTED":
            raise RuntimeError("Account sign out accepted a request without the CSRF header")
        if FakeSupabaseHandler.logout_calls:
            raise RuntimeError("CSRF-rejected sign out reached the provider")
        status, result, _ = request(
            member,
            base_url,
            "/api/auth/sign-out",
            payload={},
            origin=base_url,
        )
        if status != HTTPStatus.OK or result.get("signed_out") is not True or FakeSupabaseHandler.logout_calls != 1:
            raise RuntimeError("CSRF-protected account sign out did not revoke the provider session")
        status, result, _ = request(member, base_url, "/api/dashboard")
        if status != HTTPStatus.UNAUTHORIZED or result.get("error", {}).get("code") != "AUTH_REQUIRED":
            raise RuntimeError("Account sign out did not clear the Dashboard session cookies")

        print("User Dashboard HTTP boundary checks passed.")
    finally:
        app_server.shutdown()
        app_server.server_close()
        app_thread.join(timeout=5)
        fake_server.shutdown()
        fake_server.server_close()
        fake_thread.join(timeout=5)


if __name__ == "__main__":
    main()
