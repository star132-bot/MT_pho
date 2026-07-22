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
        "avatar_url": "https://provider.example/private-avatar.jpg",
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        authorization = self.headers.get("Authorization")
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
            or 'href="/settings/account#profile">Edit personal information</a>' not in page
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
