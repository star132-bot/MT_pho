#!/usr/bin/env python3
"""Secret-free HTTP integration for published Works and creator delivery."""

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
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PUBLISHABLE_KEY = "public-delivery-test-publishable-key"
OWNER_ID = "10000000-0000-4000-8000-000000000061"
ADMIN_ID = "10000000-0000-4000-8000-000000000062"
IMAGE_ID = "20000000-0000-4000-8000-000000000061"
SUBMISSION_ID = "30000000-0000-4000-8000-000000000061"
DECISION_ID = "40000000-0000-4000-8000-000000000061"
DISPLAY_ASSET_ID = "50000000-0000-4000-8000-000000000061"
THUMBNAIL_ASSET_ID = "50000000-0000-4000-8000-000000000062"
CREATOR_SLUG = "field-notes"
PRIVATE_CANARIES = (
    "private-owner@example.test",
    "provider-owner-canary",
    "private-storage-canary",
    "private-review-canary",
    "private-gps-canary",
)


def fake_access_token() -> str:
    claims = {
        "sub": ADMIN_ID,
        "aal": "aal2",
        "amr": [{"method": "password"}, {"method": "totp"}],
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.signature"


ADMIN_TOKEN = fake_access_token()


def derivative_asset(kind: str) -> dict:
    asset_id = DISPLAY_ASSET_ID if kind == "display" else THUMBNAIL_ASSET_ID
    bucket = "image-display" if kind == "display" else "image-thumbnails"
    width, height = ((1800, 1200) if kind == "display" else (600, 400))
    return {
        "id": asset_id,
        "image_id": IMAGE_ID,
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": f"{OWNER_ID}/{IMAGE_ID}/{kind}.jpg",
        "mime_type": "image/jpeg",
        "width": width,
        "height": height,
        "storage_debug": "private-storage-canary",
    }


def public_work() -> dict:
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
        "public_exif": {
            "camera": "MT Camera",
            "lens": "50mm",
            "gps": "private-gps-canary",
        },
        "published_at": "2026-07-22T06:00:00Z",
        "width": 1800,
        "height": 1200,
        "ratio_code": "three_to_two",
        "ratio_label": "3:2",
        "creator": {
            "slug": CREATOR_SLUG,
            "display_name": "Field Notes",
            "email": "private-owner@example.test",
            "owner_user_id": "provider-owner-canary",
        },
        "display_asset": derivative_asset("display"),
        "thumbnail_asset": derivative_asset("thumbnail"),
        "review": {"internal_note": "private-review-canary"},
    }


def public_creator() -> dict:
    work = public_work()
    return {
        "slug": CREATOR_SLUG,
        "display_name": "Field Notes",
        "professional_headline": "Editorial photographer",
        "company": "Field Notes Studio",
        "city": "Hangzhou",
        "country_code": "CN",
        "bio": "Photographs about weather, distance, and place.",
        "website_url": "https://example.test",
        "availability_status": "limited",
        "instagram_url": "https://www.instagram.com/field.notes",
        "linkedin_url": "https://www.linkedin.com/in/field-notes",
        "avatar_url": "https://example.test/avatar.jpg",
        "cover_asset": copy.deepcopy(work["display_asset"]),
        "works": [work],
        "work_count": 1,
        "email": "private-owner@example.test",
        "owner_user_id": "provider-owner-canary",
        "review_activity": [{"internal_note": "private-review-canary"}],
    }


class FakeSupabaseHandler(BaseHTTPRequestHandler):
    published = False
    public_mode = "normal"
    public_rpc_calls: list[tuple[str, dict, str]] = []
    review_calls: list[dict] = []
    storage_calls: list[tuple[str, dict, str]] = []

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
        authorization = self.headers.get("Authorization", "")
        if self.path == "/auth/v1/user" and authorization == f"Bearer {ADMIN_TOKEN}":
            self.send_json(HTTPStatus.OK, {
                "id": ADMIN_ID,
                "email": "admin@example.test",
                "email_confirmed_at": "2026-07-20T00:00:00Z",
                "factors": [{"factor_type": "totp", "status": "verified"}],
            })
            return
        self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid token"})

    def do_POST(self) -> None:
        authorization = self.headers.get("Authorization", "")
        body = self.body()

        if self.path == "/rest/v1/rpc/current_authorization":
            if authorization != f"Bearer {ADMIN_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            self.send_json(HTTPStatus.OK, {
                "user_id": ADMIN_ID,
                "account_status": "active",
                "roles": ["admin"],
                "aal": "aal2",
            })
            return

        if self.path == "/rest/v1/rpc/review_decide_submission":
            if authorization != f"Bearer {ADMIN_TOKEN}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            type(self).review_calls.append(copy.deepcopy(body))
            decision = body.get("decision")
            if decision == "approve_and_publish":
                type(self).published = True
            status = "approved" if decision in {"approve", "approve_and_publish"} else "in_review"
            self.send_json(HTTPStatus.OK, {
                "submission": {
                    "id": SUBMISSION_ID,
                    "status": status,
                    "lock_version": int(body.get("expected_lock_version") or 1) + 1,
                    "completed_at": "2026-07-22T06:00:00Z",
                },
                "decision": {
                    "id": DECISION_ID,
                    "decision": decision,
                    "created_at": "2026-07-22T06:00:00Z",
                },
                "image": {
                    "id": IMAGE_ID,
                    "workflow_status": status,
                    "publication_status": "published" if type(self).published else "never_published",
                    "current_version_id": "60000000-0000-4000-8000-000000000061",
                    "published_at": "2026-07-22T06:00:00Z" if type(self).published else None,
                },
            })
            return

        if self.path in {
            "/rest/v1/rpc/get_public_works",
            "/rest/v1/rpc/get_public_creator",
        }:
            type(self).public_rpc_calls.append((self.path, copy.deepcopy(body), authorization))
            if authorization != f"Bearer {PUBLISHABLE_KEY}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "public token required"})
                return
            if type(self).public_mode == "failure":
                self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"message": "private-provider-failure"})
                return

            if self.path.endswith("get_public_works"):
                if not type(self).published or type(self).public_mode == "empty":
                    self.send_json(HTTPStatus.OK, {"items": [], "count": 0})
                    return
                work = public_work()
                if type(self).public_mode == "unsafe":
                    work["display_asset"]["kind"] = "original"
                    work["display_asset"]["storage_bucket"] = "image-originals"
                self.send_json(HTTPStatus.OK, {"items": [work], "count": 1})
                return

            if not type(self).published or type(self).public_mode == "empty":
                self.send_json(HTTPStatus.OK, {})
                return
            creator = public_creator()
            if type(self).public_mode == "unsafe":
                creator["cover_asset"]["image_id"] = "20000000-0000-4000-8000-000000000099"
            self.send_json(HTTPStatus.OK, creator)
            return

        if self.path.startswith("/storage/v1/object/sign/"):
            type(self).storage_calls.append((self.path, copy.deepcopy(body), authorization))
            if authorization != f"Bearer {PUBLISHABLE_KEY}":
                self.send_json(HTTPStatus.UNAUTHORIZED, {})
                return
            suffix = self.path.removeprefix("/storage/v1")
            self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=public-signed-read"})
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
            urllib.request.ProxyHandler({}),
        )

    def open(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._opener.open(*args, **kwargs)

    def set_cookie(self, name: str, value: str) -> None:
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain="127.0.0.1",
            domain_specified=False,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=False,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None},
            rfc2109=False,
        ))


def request(
    opener: CookieOpener,
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
    origin: str | None = None,
) -> tuple[int, dict | str, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "MT public delivery boundary"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if origin:
        headers["Origin"] = origin
    csrf = next((cookie.value for cookie in opener.cookie_jar if cookie.name.endswith("mt_csrf_token")), "")
    if body is not None and csrf:
        headers["X-CSRF-Token"] = csrf
    provider_request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with opener.open(provider_request, timeout=10) as response:
            raw = response.read()
            value = json.loads(raw.decode()) if raw and response.headers.get_content_type() == "application/json" else raw.decode()
            return response.status, value, response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        value = json.loads(raw.decode()) if raw and error.headers.get_content_type() == "application/json" else raw.decode()
        return error.code, value, error.headers


def admin_session(base_url: str) -> CookieOpener:
    opener = CookieOpener()
    opener.set_cookie("mt_access_token", ADMIN_TOKEN)
    status, result, _ = request(opener, base_url, "/api/auth/csrf")
    if status != HTTPStatus.OK or not isinstance(result, dict) or not result.get("csrf_token"):
        raise RuntimeError("Public delivery boundary could not initialize Admin CSRF")
    return opener


def decision_body(key: str, decision: str) -> dict:
    return {
        "confirmation": f"review-{decision.replace('_', '-')}",
        "expected_version": 3 if decision == "approve" else 4,
        "idempotency_key": key,
        "reason_codes": ["policy_complete"],
        "user_message": "The submitted work satisfies the review policy.",
        "internal_note": "",
        "checklist_result": {
            code: True for code in (
                "file_integrity",
                "rights",
                "privacy",
                "minors",
                "sensitive_content",
                "hate_illegal",
                "property_release",
                "third_party_ip",
                "ai_disclosure",
                "public_metadata",
            )
        },
    }


def serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def assert_private_fields_absent(value: object) -> None:
    text = serialized(value)
    forbidden_tokens = (
        '"email"',
        '"owner_user_id"',
        '"storage_bucket"',
        '"storage_key"',
        '"review"',
        '"review_activity"',
        '"internal_note"',
        '"gps"',
        *PRIVATE_CANARIES,
    )
    found = [token for token in forbidden_tokens if token in text]
    if found:
        raise RuntimeError(f"Public delivery response leaked private fields: {', '.join(found)}")


def error_code(value: object) -> str:
    return str(value.get("error", {}).get("code") or "") if isinstance(value, dict) else ""


def creator_from(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    creator = value.get("creator")
    return creator if isinstance(creator, dict) else value


def signed_assets(value: object) -> list[dict]:
    found: list[dict] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            if isinstance(item.get("signed_url"), str):
                found.append(item)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def reset_fake() -> None:
    FakeSupabaseHandler.published = False
    FakeSupabaseHandler.public_mode = "normal"
    FakeSupabaseHandler.public_rpc_calls = []
    FakeSupabaseHandler.review_calls = []
    FakeSupabaseHandler.storage_calls = []


def main() -> None:
    reset_fake()
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()

    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = PUBLISHABLE_KEY
    os.environ["MT_PUBLIC_BASE_URL"] = ""
    os.environ["MT_COOKIE_SECURE"] = "0"
    app = importlib.import_module("server")
    application = ThreadingHTTPServer(("127.0.0.1", 0), partial(app.MTRequestHandler, directory=str(ROOT)))
    app_thread = threading.Thread(target=application.serve_forever, daemon=True)
    app_thread.start()
    base_url = f"http://127.0.0.1:{application.server_address[1]}"

    try:
        anonymous = CookieOpener()
        status, works, _ = request(anonymous, base_url, "/api/archive/images")
        if (
            status != HTTPStatus.OK
            or not isinstance(works, dict)
            or works.get("items") != []
            or works.get("count") != 0
            or works.get("source") == "local-sqlite"
            or "sample" in serialized(works).lower()
        ):
            raise RuntimeError("Pre-publish Works did not preserve the authoritative empty state")
        status, creator, _ = request(anonymous, base_url, f"/api/public/creators/{CREATOR_SLUG}")
        if status != HTTPStatus.NOT_FOUND or error_code(creator) != "PUBLIC_CREATOR_NOT_FOUND":
            raise RuntimeError("Pre-publish creator profile was publicly visible")
        if FakeSupabaseHandler.storage_calls:
            raise RuntimeError("Pre-publish public reads attempted Storage signing")

        admin = admin_session(base_url)
        status, result, _ = request(
            admin,
            base_url,
            f"/api/admin/review-submissions/{SUBMISSION_ID}/approve",
            payload=decision_body("70000000-0000-4000-8000-000000000061", "approve"),
            origin=base_url,
        )
        if status != HTTPStatus.OK or not isinstance(result, dict) or result.get("image", {}).get("publication_status") != "never_published":
            raise RuntimeError("Admin Approve did not preserve the unpublished state")
        status, works, _ = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.OK or not isinstance(works, dict) or works.get("items") != []:
            raise RuntimeError("Ordinary Approve leaked a work into the public archive")

        status, result, _ = request(
            admin,
            base_url,
            f"/api/admin/review-submissions/{SUBMISSION_ID}/approve-and-publish",
            payload=decision_body("70000000-0000-4000-8000-000000000062", "approve_and_publish"),
            origin=base_url,
        )
        if status != HTTPStatus.OK or not isinstance(result, dict) or result.get("image", {}).get("publication_status") != "published":
            raise RuntimeError("Admin AAL2 Approve and Publish failed")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        status, works, works_headers = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.OK or not isinstance(works, dict) or works.get("count") != 1:
            raise RuntimeError("Published work did not enter the anonymous Works response")
        items = works.get("items") or []
        if len(items) != 1 or items[0].get("id") != IMAGE_ID:
            raise RuntimeError("Published Works returned an unstable item projection")
        work_assets = signed_assets(items[0])
        if {asset.get("kind") for asset in work_assets} != {"display", "thumbnail"}:
            raise RuntimeError("Published Works did not sign exactly display and thumbnail derivatives")
        if any(not asset.get("signed_url") or not isinstance(asset.get("expires_in"), int) for asset in work_assets):
            raise RuntimeError("Published Works returned an invalid signed derivative DTO")
        assert_private_fields_absent(works)
        if len(FakeSupabaseHandler.storage_calls) - signs_before != 2:
            raise RuntimeError("Published Works did not perform exactly two derivative signatures")
        if works_headers.get("Cache-Control") != "no-store":
            raise RuntimeError("Signed public Works response was cacheable")

        signs_before = len(FakeSupabaseHandler.storage_calls)
        status, creator_response, creator_headers = request(
            anonymous,
            base_url,
            f"/api/public/creators/{CREATOR_SLUG}",
        )
        creator = creator_from(creator_response)
        if (
            status != HTTPStatus.OK
            or creator.get("slug") != CREATOR_SLUG
            or creator.get("display_name") != "Field Notes"
            or creator.get("work_count") != 1
            or len(creator.get("works") or []) != 1
        ):
            raise RuntimeError("Published creator did not enter the anonymous creator response")
        creator_assets = signed_assets(creator_response)
        if not creator_assets or any(asset.get("kind") not in {"display", "thumbnail"} for asset in creator_assets):
            raise RuntimeError("Creator response exposed a non-derivative or unsigned asset")
        assert_private_fields_absent(creator_response)
        if len(FakeSupabaseHandler.storage_calls) - signs_before > 3:
            raise RuntimeError("Creator response did not deduplicate repeated derivative signatures")
        if creator_headers.get("Cache-Control") != "no-store":
            raise RuntimeError("Signed public Creator response was cacheable")

        if not FakeSupabaseHandler.public_rpc_calls or any(
            authorization != f"Bearer {PUBLISHABLE_KEY}"
            for _, _, authorization in FakeSupabaseHandler.public_rpc_calls
        ):
            raise RuntimeError("Anonymous public RPCs did not use the publishable provider identity")
        if any(
            authorization != f"Bearer {PUBLISHABLE_KEY}"
            for _, _, authorization in FakeSupabaseHandler.storage_calls
        ):
            raise RuntimeError("Anonymous derivative signing reused a private account identity")
        if any("image-originals" in path or "/original" in unquote(path) for path, _, _ in FakeSupabaseHandler.storage_calls):
            raise RuntimeError("Public delivery signed an original asset")

        FakeSupabaseHandler.public_mode = "unsafe"
        signs_before = len(FakeSupabaseHandler.storage_calls)
        status, result, _ = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "PUBLIC_DELIVERY_PROVIDER_FAILED":
            raise RuntimeError("Unsafe public provider DTO did not fail closed")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Unsafe public provider DTO reached Storage signing")

        FakeSupabaseHandler.public_mode = "failure"
        signs_before = len(FakeSupabaseHandler.storage_calls)
        status, result, _ = request(anonymous, base_url, "/api/archive/images")
        if status != HTTPStatus.BAD_GATEWAY or error_code(result) != "PUBLIC_DELIVERY_PROVIDER_FAILED":
            raise RuntimeError("Public provider failure did not map to a stable fail-closed error")
        if "private-provider-failure" in serialized(result):
            raise RuntimeError("Public provider error details escaped the stable boundary")
        if len(FakeSupabaseHandler.storage_calls) != signs_before:
            raise RuntimeError("Failed public provider request reached Storage signing")

        FakeSupabaseHandler.public_mode = "empty"
        status, works, _ = request(anonymous, base_url, "/api/archive/images")
        if (
            status != HTTPStatus.OK
            or not isinstance(works, dict)
            or works.get("items") != []
            or works.get("count") != 0
            or "sample" in serialized(works).lower()
        ):
            raise RuntimeError("Authoritative empty public result fell back to sample content")

        print("public_delivery_anonymous_read=yes")
        print("public_delivery_approve_hidden=yes")
        print("public_delivery_publish_visible=yes")
        print("public_delivery_creator_projection=yes")
        print("public_delivery_derivative_signing=yes")
        print("public_delivery_original_exposed=no")
        print("public_delivery_private_fields_exposed=no")
        print("public_delivery_unsafe_provider_failed_closed=yes")
        print("public_delivery_provider_error_stable=yes")
        print("public_delivery_authoritative_empty=yes")
    finally:
        application.shutdown()
        application.server_close()
        app_thread.join(timeout=5)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)


if __name__ == "__main__":
    main()
