#!/usr/bin/env python3
"""Local static server for MT Presence."""

from __future__ import annotations

import argparse
import base64
import hmac
import hashlib
import json
import os
import posixpath
import secrets
import shutil
import sqlite3
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from functools import partial
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parent
ARCHIVE_DB_PATH = ROOT / "data" / "archive.db"
UPLOAD_ASSET_ROOT = ROOT / "assets" / "uploads"
UPLOAD_ASSET_URL_PREFIX = "assets/uploads"
MAX_UPLOAD_BYTES = 96 * 1024 * 1024
SEED_ARTIST_ID = "artist-mt-presence"
ARCHIVE_RATIO_CODES = {
    "1:1": "one_to_one",
    "4:3": "four_to_three",
    "4:5": "four_to_five",
    "2:3": "two_to_three",
    "3:2": "three_to_two",
    "16:9": "sixteen_to_nine",
    "panorama": "panorama",
}
ARCHIVE_CONTENT_TYPES = {
    "abstract": "abstract",
    "concrete": "concrete",
}
ARCHIVE_DISPLAY_MODES = {
    "black_white": "black_white",
    "color": "color",
}
ARCHIVE_VISIBILITIES = {
    "draft": "draft",
    "private": "private",
    "published": "published",
    "archived": "archived",
}
ARCHIVE_ASSET_KINDS = {"original", "display", "thumbnail", "square_slice"}
ARCHIVE_ASSET_KIND_ORDER = {
    "original": 0,
    "display": 1,
    "thumbnail": 2,
    "square_slice": 3,
}
ARCHIVE_UPLOAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,96}$")
MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}
TAG_GROUP_SORT_ORDER = {
    "Subject": 10,
    "Place": 20,
    "Form / Ratio": 30,
    "Mood": 40,
    "Material / Surface": 50,
    "Palette / Tone": 60,
    "Series / Collection": 70,
}

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
COOKIE_SECURE = os.environ.get("MT_COOKIE_SECURE", "0") == "1"
PUBLIC_BASE_URL = os.environ.get("MT_PUBLIC_BASE_URL", "").rstrip("/")
ACCESS_COOKIE = "mt_access_token"
REFRESH_COOKIE = "mt_refresh_token"
CSRF_COOKIE = "__Host-mt_csrf_token" if COOKIE_SECURE else "mt_csrf_token"
RECOVERY_COOKIE = "__Host-mt_recovery_grant" if COOKIE_SECURE else "mt_recovery_grant"
CSRF_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,128}$")
RECOVERY_GRANT_TTL_SECONDS = 10 * 60
RECOVERY_GRANTS: dict[str, tuple[str, float]] = {}
RECOVERY_GRANTS_LOCK = threading.Lock()
PROFILE_FIELDS = (
    "display_name",
    "avatar_url",
    "bio",
    "website_url",
    "country_code",
    "preferred_locale",
    "timezone",
    "copyright_name",
    "default_license_preference",
    "professional_headline",
    "company",
    "city",
    "availability_status",
    "instagram_url",
    "linkedin_url",
)
PROFILE_EDITABLE_FIELDS = tuple(field for field in PROFILE_FIELDS if field != "avatar_url")
PROFILE_LOCALES = {"en"}
PROFILE_AVAILABILITY_STATUSES = {"unavailable", "open", "limited"}
PROFILE_SOCIAL_HOSTS = {
    "instagram_url": {"instagram.com", "www.instagram.com"},
    "linkedin_url": {"linkedin.com", "www.linkedin.com"},
}
PROFILE_LICENSES = {
    "all-rights-reserved",
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "cc-by-nc-4.0",
    "cc-by-nc-sa-4.0",
}
PROFILE_COVER_ASSET_KINDS = {"display", "thumbnail"}
PROFILE_COVER_ASSET_BUCKETS = {
    "display": "image-display",
    "thumbnail": "image-thumbnails",
}
PROFILE_COVER_SCAN_POLICY_VERSION = "mt-asset-scan-2026-07-v1"
PROFILE_COVER_MAX_CANDIDATES = 24
WORKSPACE_ASSET_KINDS = {"original", "display", "thumbnail"}
WORKSPACE_ASSET_LIMITS = {
    "original": 50 * 1024 * 1024,
    "display": 20 * 1024 * 1024,
    "thumbnail": 10 * 1024 * 1024,
}
WORKSPACE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
WORKSPACE_DRAFT_FIELDS = {
    "folder_id",
    "title",
    "caption",
    "description",
    "alt_text",
    "tags",
    "content_category",
    "captured_at",
    "location_name",
    "copyright_holder",
    "copyright_year",
    "contains_recognizable_people",
    "model_release_status",
    "property_release_status",
    "rights_declared",
    "ai_disclosure",
    "sensitive_content_disclosure",
}
WORKSPACE_DRAFT_CORE_FIELDS = WORKSPACE_DRAFT_FIELDS - {
    "copyright_holder",
    "copyright_year",
    "contains_recognizable_people",
    "model_release_status",
    "property_release_status",
    "rights_declared",
    "ai_disclosure",
    "sensitive_content_disclosure",
}
WORKSPACE_RELEASE_STATUSES = {"not_applicable", "available", "not_available", "pending"}
WORKSPACE_AI_DISCLOSURES = {"none", "ai_edited", "ai_generated"}
WORKSPACE_SENSITIVE_DISCLOSURES = {"none", "contains_sensitive_content"}
WORKSPACE_ERROR_STATUS = {
    "FOLDER_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "FOLDER_NAME_CONFLICT": HTTPStatus.CONFLICT,
    "FOLDER_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "FOLDER_NOT_EMPTY": HTTPStatus.CONFLICT,
    "FOLDER_RESTORE_CONFLICT": HTTPStatus.CONFLICT,
    "UPLOAD_INTENT_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "UPLOAD_ASSETS_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "UPLOAD_INTENT_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "UPLOAD_INTENT_EXPIRED": HTTPStatus.GONE,
    "UPLOAD_INTENT_NOT_CANCELABLE": HTTPStatus.CONFLICT,
    "UPLOAD_ASSETS_INCOMPLETE": HTTPStatus.CONFLICT,
    "UPLOAD_ALREADY_COMPLETED": HTTPStatus.CONFLICT,
    "DRAFT_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "DRAFT_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "DRAFT_LOCKED": HTTPStatus.LOCKED,
    "DRAFT_VERSION_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "DRAFT_VERSION_CONFLICT": HTTPStatus.CONFLICT,
    "DRAFT_NOT_READY": HTTPStatus.UNPROCESSABLE_ENTITY,
    "SUBMISSION_CONFIRMATION_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "SUBMISSION_VERSION_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "SUBMISSION_IDEMPOTENCY_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "SUBMISSION_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "SUBMISSION_ALREADY_OPEN": HTTPStatus.CONFLICT,
    "SUBMISSION_STATE_CONFLICT": HTTPStatus.CONFLICT,
}

WORKSPACE_READINESS_CHECKS = {
    "work_details": "Work details",
    "rights_disclosures": "Rights & disclosures",
    "image_assets": "Image assets",
    "security_scan": "Security scan",
    "submission_state": "Submission state",
}
WORKSPACE_READINESS_FIELD_KEYS = {
    "title",
    "alt_text",
    "content_category",
    "copyright_holder",
    "copyright_year",
    "contains_recognizable_people",
    "model_release_status",
    "property_release_status",
    "rights_declared",
    "ai_disclosure",
    "sensitive_content_disclosure",
    "processing_status",
    "image_assets",
    "security_scan",
    "submission_state",
}

DASHBOARD_PROCESSING_STATUSES = {"pending", "uploading", "processing", "ready", "failed", "canceled"}
DASHBOARD_WORKFLOW_STATUSES = {"draft", "submitted", "in_review", "changes_requested", "rejected", "approved"}
DASHBOARD_PUBLICATION_STATUSES = {"never_published", "published", "unpublished", "quarantined", "archived", "deleted"}
DASHBOARD_COUNT_KEYS = ("drafts", "submitted", "changes_requested", "published", "unpublished")
DASHBOARD_ATTENTION_TYPES = {"changes_requested", "processing_failed"}
DASHBOARD_REVIEW_DECISIONS = {
    "request_changes",
    "reject",
    "approve",
    "approve_and_publish",
    "escalate",
    "quarantine",
}

REVIEW_STATUSES = {
    "submitted",
    "in_review",
    "changes_requested",
    "rejected",
    "approved",
    "withdrawn",
    "escalated",
}
REVIEW_OPEN_STATUSES = {"submitted", "in_review", "escalated"}
REVIEW_FILTER_STATUSES = REVIEW_STATUSES.union({"open", "all", "completed"})
REVIEW_DECISIONS = {"request_changes", "reject", "approve", "approve_and_publish"}
REVIEW_ASSET_SCAN_POLICY_VERSION = "mt-asset-scan-2026-07-v1"
REVIEW_REASON_CODES = {
    "request_changes": {"missing_rights", "missing_metadata", "privacy_review", "release_required"},
    "reject": {"content_policy", "rights_unverified", "privacy_risk", "misleading_metadata"},
    "approve": {"policy_complete"},
    "approve_and_publish": {"policy_complete"},
}
REVIEW_CHECKLIST_CODES = {
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
}
REVIEW_REASON_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,79}$")
REVIEW_ERROR_STATUS = {
    "REVIEW_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "REVIEW_SUBMISSION_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "REVIEW_VERSION_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "REVIEW_VERSION_CONFLICT": HTTPStatus.CONFLICT,
    "REVIEW_ALREADY_ASSIGNED": HTTPStatus.CONFLICT,
    "REVIEW_ASSIGNMENT_REQUIRED": HTTPStatus.CONFLICT,
    "REVIEW_SELF_REVIEW_FORBIDDEN": HTTPStatus.FORBIDDEN,
    "REVIEW_STATE_CONFLICT": HTTPStatus.CONFLICT,
    "REVIEW_ASSETS_NOT_READY": HTTPStatus.CONFLICT,
    "REVIEW_ALREADY_PUBLISHED": HTTPStatus.CONFLICT,
    "REVIEW_DECISION_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "REVIEW_CHECKLIST_INCOMPLETE": HTTPStatus.UNPROCESSABLE_ENTITY,
    "REVIEW_IDEMPOTENCY_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "REVIEW_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "REVIEW_PUBLISH_ADMIN_REQUIRED": HTTPStatus.FORBIDDEN,
    "REVIEW_ACCESS_REVOKED": HTTPStatus.FORBIDDEN,
}


def canonical_url_path(value: str) -> str:
    """Match SimpleHTTPRequestHandler path normalization for protected aliases."""
    # Request targets are origin-form paths. urlparse("//file") treats `file`
    # as a host, while SimpleHTTPRequestHandler treats it as a path alias.
    decoded = unquote(value.split("?", 1)[0].split("#", 1)[0])
    return posixpath.normpath(f"/{decoded.lstrip('/')}")


def auth_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)


def auth_error(
    code: str,
    message: str,
    field_errors: dict | None = None,
    details: dict | None = None,
) -> dict:
    error = {"code": code, "message": message, "request_id": uuid.uuid4().hex}
    if field_errors:
        error["field_errors"] = field_errors
    if details:
        error["details"] = details
    return {"error": error}


def decode_jwt_payload(token: str) -> dict:
    """Decode provider-verified JWT claims without treating them as authorization."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def session_has_auth_method(session: dict, method: str) -> bool:
    claims = decode_jwt_payload(str(session.get("access_token") or ""))
    return any(
        isinstance(entry, dict) and entry.get("method") == method
        for entry in claims.get("amr") or []
    )


def create_recovery_grant(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with RECOVERY_GRANTS_LOCK:
        expired = [key for key, (_, deadline) in RECOVERY_GRANTS.items() if deadline <= now]
        for key in expired:
            RECOVERY_GRANTS.pop(key, None)
        RECOVERY_GRANTS[token] = (user_id, now + RECOVERY_GRANT_TTL_SECONDS)
    return token


def recovery_grant_is_valid(token: str, user_id: str) -> bool:
    if not token or not user_id:
        return False
    now = time.monotonic()
    with RECOVERY_GRANTS_LOCK:
        grant = RECOVERY_GRANTS.get(token)
        if not grant or grant[1] <= now:
            RECOVERY_GRANTS.pop(token, None)
            return False
        return hmac.compare_digest(grant[0], user_id)


def consume_recovery_grant(token: str) -> None:
    if not token:
        return
    with RECOVERY_GRANTS_LOCK:
        RECOVERY_GRANTS.pop(token, None)


def supabase_auth_request(
    path: str,
    payload: dict | None = None,
    access_token: str = "",
    *,
    method: str | None = None,
) -> tuple[int, dict]:
    if not auth_configured():
        return HTTPStatus.SERVICE_UNAVAILABLE, auth_error(
            "AUTH_NOT_CONFIGURED",
            "Authentication is not configured for this environment.",
        )
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw_body = response.read()
            return response.status, json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        return error.code, data
    except (urllib.error.URLError, TimeoutError):
        return HTTPStatus.BAD_GATEWAY, auth_error("AUTH_PROVIDER_UNAVAILABLE", "Authentication is temporarily unavailable.")


def supabase_rest_request(
    path: str,
    access_token: str,
    payload: dict | None = None,
    *,
    method: str = "POST",
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict | list]:
    if not auth_configured():
        return HTTPStatus.SERVICE_UNAVAILABLE, auth_error("AUTH_NOT_CONFIGURED", "Authentication is not configured for this environment.")
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw_body = response.read()
            return response.status, json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        return error.code, data
    except (urllib.error.URLError, TimeoutError):
        return HTTPStatus.BAD_GATEWAY, auth_error("AUTH_PROVIDER_UNAVAILABLE", "Authorization is temporarily unavailable.")


def supabase_storage_request(
    path: str,
    access_token: str,
    payload: dict | None = None,
    *,
    method: str = "POST",
) -> tuple[int, dict | list]:
    if not auth_configured():
        return HTTPStatus.SERVICE_UNAVAILABLE, auth_error(
            "AUTH_NOT_CONFIGURED",
            "Authentication is not configured for this environment.",
        )
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{SUPABASE_URL}/storage/v1/{path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw_body = response.read()
            return response.status, json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        return error.code, data
    except (urllib.error.URLError, TimeoutError):
        return HTTPStatus.BAD_GATEWAY, auth_error("STORAGE_PROVIDER_UNAVAILABLE", "Image storage is temporarily unavailable.")


def is_private_static_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    local_original = (
        len(parts) >= 3
        and parts[:2] == ["assets", "uploads"]
        and parts[-1].lower().startswith("original-")
    )
    return (
        any(part.startswith(".") for part in parts)
        or (bool(parts) and parts[0] in {"data", "tmp", "shots"})
        or local_original
    )


def legacy_upload_asset_access(path: str) -> tuple[str, str] | None:
    """Return (kind, visibility) for a registered legacy upload asset URL."""
    if not ARCHIVE_DB_PATH.exists():
        return None
    public_url = path.lstrip("/")
    try:
        with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
            row = connection.execute(
                """
                SELECT a.kind, i.visibility
                FROM image_assets AS a
                JOIN images AS i ON i.id = a.image_id
                WHERE a.public_url = ?
                LIMIT 1
                """,
                (public_url,),
            ).fetchone()
    except sqlite3.Error:
        return None
    return (str(row[0]), str(row[1])) if row else None


def parse_archive_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return fallback
    return parsed if parsed is not None else fallback


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value, max_length: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()).strip("-")
    return slug or fallback


def clean_identifier(value, field_name: str = "id") -> str:
    text = clean_text(value, 128)
    if not text or not ARCHIVE_UPLOAD_ID_PATTERN.match(text):
        raise ValueError(f"Invalid {field_name}.")
    return text


def clean_uuid(value, field_name: str) -> str:
    text = clean_text(value, 64)
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {field_name}.") from error


def clean_workspace_submit_readiness(value) -> dict | None:
    """Project provider readiness into the only shape safe for browser clients."""
    if not isinstance(value, dict):
        return None
    try:
        image_id = clean_uuid(value.get("image_id"), "image id")
    except ValueError:
        return None
    lock_version = value.get("lock_version")
    if isinstance(lock_version, bool) or not isinstance(lock_version, int) or lock_version < 1:
        return None
    workflow_status = clean_text(value.get("workflow_status"), 40)
    if workflow_status not in {"draft", "changes_requested", "submitted"}:
        return None

    raw_checks = value.get("checks")
    if not isinstance(raw_checks, list) or len(raw_checks) != len(WORKSPACE_READINESS_CHECKS):
        return None
    checks_by_code = {}
    for raw_check in raw_checks:
        if not isinstance(raw_check, dict):
            return None
        code = clean_text(raw_check.get("code"), 80)
        state = clean_text(raw_check.get("state"), 20)
        if code not in WORKSPACE_READINESS_CHECKS or code in checks_by_code or state not in {"pass", "pending", "fail"}:
            return None
        message = clean_text(raw_check.get("message"), 300)
        if not message:
            return None
        checks_by_code[code] = {
            "code": code,
            "label": WORKSPACE_READINESS_CHECKS[code],
            "state": state,
            "message": message,
        }
    if set(checks_by_code) != set(WORKSPACE_READINESS_CHECKS):
        return None
    checks = [checks_by_code[code] for code in WORKSPACE_READINESS_CHECKS]

    failed = sum(check["state"] == "fail" for check in checks)
    pending = sum(check["state"] == "pending" for check in checks)
    status = "blocked" if failed else "pending" if pending else "ready"
    field_errors = {}
    raw_field_errors = value.get("field_errors")
    if isinstance(raw_field_errors, dict):
        for key in sorted(WORKSPACE_READINESS_FIELD_KEYS.intersection(raw_field_errors)):
            message = clean_text(raw_field_errors.get(key), 300)
            if message:
                field_errors[key] = message
    return {
        "image_id": image_id,
        "lock_version": lock_version,
        "workflow_status": workflow_status,
        "status": status,
        "ready": status == "ready",
        "blocker_count": failed + pending,
        "checks": checks,
        "field_errors": field_errors,
    }


def clean_workspace_submission_result(value, expected_image_id: str) -> dict | None:
    """Allowlist a successful Submit response and reject inconsistent provider data."""
    if not isinstance(value, dict) or value.get("submitted") is not True:
        return None
    submission = value.get("submission")
    image = value.get("image")
    if not isinstance(submission, dict) or not isinstance(image, dict):
        return None
    try:
        submission_id = clean_uuid(submission.get("id"), "submission id")
        submission_image_id = clean_uuid(submission.get("image_id"), "submission image id")
        image_version_id = clean_uuid(submission.get("image_version_id"), "image version id")
        image_id = clean_uuid(image.get("id"), "image id")
    except ValueError:
        return None
    if submission_image_id != expected_image_id or image_id != expected_image_id:
        return None
    if clean_text(submission.get("status"), 40) != "submitted":
        return None
    if clean_text(image.get("workflow_status"), 40) != "submitted":
        return None
    policy_version = clean_text(submission.get("policy_version"), 80)
    submitted_at = clean_text(submission.get("submitted_at"), 80)
    lock_version = image.get("lock_version")
    if (
        not policy_version
        or not submitted_at
        or isinstance(lock_version, bool)
        or not isinstance(lock_version, int)
        or lock_version < 1
    ):
        return None
    return {
        "submitted": True,
        "submission": {
            "id": submission_id,
            "image_id": submission_image_id,
            "image_version_id": image_version_id,
            "status": "submitted",
            "policy_version": policy_version,
            "submitted_at": submitted_at,
        },
        "image": {
            "id": image_id,
            "workflow_status": "submitted",
            "lock_version": lock_version,
        },
    }


def clean_dashboard_image(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        image_id = clean_uuid(value.get("id"), "dashboard image id")
    except ValueError:
        return None
    processing_status = clean_text(value.get("processing_status"), 40)
    workflow_status = clean_text(value.get("workflow_status"), 40)
    publication_status = clean_text(value.get("publication_status"), 40)
    updated_at = clean_text(value.get("updated_at"), 80)
    if (
        processing_status not in DASHBOARD_PROCESSING_STATUSES
        or workflow_status not in DASHBOARD_WORKFLOW_STATUSES
        or publication_status not in DASHBOARD_PUBLICATION_STATUSES
        or not updated_at
    ):
        return None
    thumbnail = None
    if value.get("thumbnail_asset") is not None:
        thumbnail = clean_review_asset(value.get("thumbnail_asset"))
        if thumbnail is None or thumbnail.get("kind") != "thumbnail":
            return None
    return {
        "id": image_id,
        "title": clean_text(value.get("title"), 180) or "Untitled Work",
        "original_filename": clean_text(value.get("original_filename"), 512),
        "processing_status": processing_status,
        "workflow_status": workflow_status,
        "publication_status": publication_status,
        "updated_at": updated_at,
        "thumbnail_asset": thumbnail,
    }


def clean_dashboard_result(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    raw_counts = value.get("status_counts")
    if not isinstance(raw_counts, dict):
        return None
    counts = {}
    for key in DASHBOARD_COUNT_KEYS:
        count = raw_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        counts[key] = count

    images_by_section = {}
    for key, maximum in (("recent_images", 8), ("drafts", 12)):
        raw_images = value.get(key)
        if not isinstance(raw_images, list) or len(raw_images) > maximum:
            return None
        images = []
        for raw_image in raw_images:
            image = clean_dashboard_image(raw_image)
            if image is None:
                return None
            images.append(image)
        images_by_section[key] = images

    raw_attention = value.get("needs_attention")
    if not isinstance(raw_attention, list) or len(raw_attention) > 8:
        return None
    attention = []
    for raw_item in raw_attention:
        if not isinstance(raw_item, dict):
            return None
        try:
            image_id = clean_uuid(raw_item.get("image_id"), "attention image id")
        except ValueError:
            return None
        attention_type = clean_text(raw_item.get("type"), 40)
        message = clean_text(raw_item.get("message"), 300)
        updated_at = clean_text(raw_item.get("updated_at"), 80)
        if (
            attention_type not in DASHBOARD_ATTENTION_TYPES
            or not message
            or not updated_at
            or raw_item.get("workspace_path") != "/workspace/images"
        ):
            return None
        attention.append({
            "type": attention_type,
            "image_id": image_id,
            "title": clean_text(raw_item.get("title"), 180) or "Untitled Work",
            "message": message,
            "updated_at": updated_at,
            "workspace_path": "/workspace/images",
        })

    raw_activity = value.get("review_activity")
    if not isinstance(raw_activity, list) or len(raw_activity) > 10:
        return None
    activity = []
    for raw_item in raw_activity:
        if not isinstance(raw_item, dict):
            return None
        try:
            submission_id = clean_uuid(raw_item.get("submission_id"), "dashboard submission id")
            image_id = clean_uuid(raw_item.get("image_id"), "dashboard activity image id")
        except ValueError:
            return None
        status = clean_text(raw_item.get("status"), 40)
        decision = clean_text(raw_item.get("decision"), 40) or None
        occurred_at = clean_text(raw_item.get("occurred_at"), 80)
        if (
            status not in REVIEW_STATUSES
            or (decision is not None and decision not in DASHBOARD_REVIEW_DECISIONS)
            or not occurred_at
        ):
            return None
        activity.append({
            "submission_id": submission_id,
            "image_id": image_id,
            "title": clean_text(raw_item.get("title"), 180) or "Untitled Work",
            "status": status,
            "decision": decision,
            "submitted_at": clean_text(raw_item.get("submitted_at"), 80) or None,
            "review_started_at": clean_text(raw_item.get("review_started_at"), 80) or None,
            "completed_at": clean_text(raw_item.get("completed_at"), 80) or None,
            "occurred_at": occurred_at,
        })

    raw_storage = value.get("storage_usage")
    if not isinstance(raw_storage, dict) or raw_storage.get("quota_bytes") is not None:
        return None
    storage = {"quota_bytes": None}
    for key in ("used_bytes", "asset_count", "image_count"):
        number = raw_storage.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return None
        storage[key] = number

    raw_capabilities = value.get("capabilities")
    if not isinstance(raw_capabilities, dict):
        return None
    capabilities = {}
    expected_capabilities = {
        "storage_quota": "not_configured",
        "public_portfolio": "public_delivery_not_connected",
    }
    for key, reason in expected_capabilities.items():
        capability = raw_capabilities.get(key)
        if not isinstance(capability, dict) or capability.get("available") is not False or capability.get("reason") != reason:
            return None
        capabilities[key] = {"available": False, "reason": reason}

    generated_at = clean_text(value.get("generated_at"), 80)
    if not generated_at:
        return None
    return {
        "status_counts": counts,
        "needs_attention": attention,
        "recent_images": images_by_section["recent_images"],
        "drafts": images_by_section["drafts"],
        "review_activity": activity,
        "storage_usage": storage,
        "capabilities": capabilities,
        "generated_at": generated_at,
    }


def clean_profile_cover_asset(value) -> dict | None:
    """Validate the private provider descriptor before any Storage signing."""
    if not isinstance(value, dict):
        return None
    try:
        asset_id = clean_uuid(value.get("id"), "profile cover asset id")
        image_id = clean_uuid(value.get("image_id"), "profile cover image id")
    except ValueError:
        return None
    kind = clean_text(value.get("kind"), 32)
    bucket = clean_text(value.get("storage_bucket"), 80)
    storage_key = clean_text(value.get("storage_key"), 1024)
    mime_type = clean_text(value.get("mime_type"), 120).lower()
    width = value.get("width")
    height = value.get("height")
    if (
        kind not in PROFILE_COVER_ASSET_KINDS
        or bucket != PROFILE_COVER_ASSET_BUCKETS.get(kind)
        or not storage_key
        or mime_type not in WORKSPACE_IMAGE_MIME_TYPES
        or any(
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension < 1
            or dimension > 100_000
            for dimension in (width, height)
        )
        or value.get("scan_status") != "clean"
        or value.get("scan_result_code") != "clean"
        or value.get("scan_policy_version") != PROFILE_COVER_SCAN_POLICY_VERSION
    ):
        return None
    return {
        "id": asset_id,
        "image_id": image_id,
        "title": clean_text(value.get("title"), 180) or "Untitled Work",
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": storage_key,
        "mime_type": mime_type,
        "width": width,
        "height": height,
    }


def clean_profile_cover_result(value, *, include_candidates: bool) -> dict | None:
    if not isinstance(value, dict):
        return None
    cover = None
    if value.get("cover_asset") is not None:
        cover = clean_profile_cover_asset(value.get("cover_asset"))
        if cover is None:
            return None

    result = {"cover_asset": cover}
    if not include_candidates:
        if value.get("saved") is not True:
            return None
        result["saved"] = True
        return result

    raw_candidates = value.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) > PROFILE_COVER_MAX_CANDIDATES:
        return None
    candidates = []
    seen_ids = set()
    for raw_candidate in raw_candidates:
        candidate = clean_profile_cover_asset(raw_candidate)
        if candidate is None or candidate["id"] in seen_ids:
            return None
        seen_ids.add(candidate["id"])
        candidates.append(candidate)
    result["candidates"] = candidates
    return result


def clean_review_person(value, *, required: bool = True) -> dict | None:
    if value is None and not required:
        return None
    if not isinstance(value, dict):
        return None
    try:
        person_id = clean_uuid(value.get("id"), "person id")
    except ValueError:
        return None
    display_name = clean_text(value.get("display_name"), 120) or "Member"
    return {"id": person_id, "display_name": display_name}


def clean_review_principal(user: dict, authorization: dict) -> tuple[str, set[str]] | None:
    try:
        user_id = clean_uuid(user.get("id"), "review actor id")
        authorization_user_id = clean_uuid(authorization.get("user_id"), "authorization user id")
    except ValueError:
        return None
    raw_roles = authorization.get("roles")
    if user_id != authorization_user_id or not isinstance(raw_roles, list):
        return None
    roles = {
        clean_text(role, 40)
        for role in raw_roles
        if isinstance(role, str)
    }.intersection({"reviewer", "admin", "super_admin"})
    if not roles:
        return None
    return user_id, roles


def clean_review_actor(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        actor_id = clean_uuid(value.get("id"), "review actor id")
    except ValueError:
        return None
    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list):
        return None
    roles = sorted({clean_text(role, 40) for role in raw_roles}.intersection({"reviewer", "admin", "super_admin"}))
    if (
        not roles
        or (expected_actor_id and actor_id != expected_actor_id)
        or (expected_roles is not None and set(roles) != expected_roles)
    ):
        return None
    return {
        "id": actor_id,
        "roles": roles,
        "can_publish": bool(set(roles).intersection({"admin", "super_admin"})),
    }


def clean_review_asset(value) -> dict | None:
    """Keep private Storage coordinates server-side until a signed URL exists."""
    if not isinstance(value, dict):
        return None
    try:
        asset_id = clean_uuid(value.get("id"), "review asset id")
    except ValueError:
        return None
    kind = clean_text(value.get("kind"), 32)
    bucket = clean_text(value.get("storage_bucket"), 80)
    expected_bucket = {
        "original": "image-originals",
        "display": "image-display",
        "thumbnail": "image-thumbnails",
    }.get(kind)
    storage_key = clean_text(value.get("storage_key"), 1024)
    mime_type = clean_text(value.get("mime_type"), 120).lower()
    width = value.get("width")
    height = value.get("height")
    if (
        not expected_bucket
        or bucket != expected_bucket
        or not storage_key
        or any(ord(character) < 32 or ord(character) == 127 for character in storage_key)
        or mime_type not in WORKSPACE_IMAGE_MIME_TYPES
        or isinstance(width, bool)
        or not isinstance(width, int)
        or width < 1
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height < 1
    ):
        return None
    result = {
        "id": asset_id,
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": storage_key,
        "mime_type": mime_type,
        "width": width,
        "height": height,
    }
    byte_size = value.get("byte_size")
    if isinstance(byte_size, int) and not isinstance(byte_size, bool) and byte_size > 0:
        result["byte_size"] = byte_size
    checksum = clean_text(value.get("checksum_sha256"), 64).lower()
    if re.fullmatch(r"[0-9a-f]{64}", checksum):
        result["checksum_sha256"] = checksum
    scan_status = clean_text(value.get("scan_status"), 20)
    if scan_status in {"pending", "clean", "flagged", "failed"}:
        result["scan_status"] = scan_status
    for key, maximum in (("scan_result_code", 120), ("scan_policy_version", 120)):
        text = clean_text(value.get(key), maximum)
        if text:
            result[key] = text
    if (
        result.get("scan_status") != "clean"
        or result.get("scan_policy_version") != REVIEW_ASSET_SCAN_POLICY_VERSION
    ):
        return None
    return result


def clean_review_submission_summary(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        submission_id = clean_uuid(value.get("id"), "review submission id")
    except ValueError:
        return None
    status = clean_text(value.get("status"), 40)
    lock_version = value.get("lock_version")
    owner = clean_review_person(value.get("owner"))
    assigned = clean_review_person(value.get("assigned_reviewer"), required=False)
    image = value.get("image")
    if (
        status not in REVIEW_STATUSES
        or isinstance(lock_version, bool)
        or not isinstance(lock_version, int)
        or lock_version < 1
        or owner is None
        or not isinstance(image, dict)
    ):
        return None
    try:
        image_id = clean_uuid(image.get("id"), "review image id")
    except ValueError:
        return None
    rights = image.get("rights") if isinstance(image.get("rights"), dict) else {}
    thumbnail = None
    if image.get("thumbnail_asset") is not None:
        thumbnail = clean_review_asset(image.get("thumbnail_asset"))
        if thumbnail is None or thumbnail["kind"] != "thumbnail":
            return None
    publication_status = clean_text(image.get("publication_status"), 40)
    if publication_status not in {"never_published", "published", "unpublished", "quarantined", "archived", "deleted"}:
        return None
    return {
        "id": submission_id,
        "status": status,
        "lock_version": lock_version,
        "submitted_at": clean_text(value.get("submitted_at"), 80),
        "review_started_at": clean_text(value.get("review_started_at"), 80) or None,
        "completed_at": clean_text(value.get("completed_at"), 80) or None,
        "policy_version": clean_text(value.get("policy_version"), 120),
        "assigned_reviewer": assigned,
        "owner": owner,
        "image": {
            "id": image_id,
            "title": clean_text(image.get("title"), 180),
            "original_filename": clean_text(image.get("original_filename"), 512),
            "content_category": clean_text(image.get("content_category"), 80) or None,
            "publication_status": publication_status,
            "rights": {
                "declared": rights.get("declared") is True,
                "recognizable_people": rights.get("recognizable_people") if isinstance(rights.get("recognizable_people"), bool) else None,
                "model_release_status": clean_text(rights.get("model_release_status"), 40) or None,
                "property_release_status": clean_text(rights.get("property_release_status"), 40) or None,
            },
            "thumbnail_asset": thumbnail,
        },
    }


def clean_review_list_result(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_review_actor(
        value.get("actor"),
        expected_actor_id=expected_actor_id,
        expected_roles=expected_roles,
    )
    raw_items = value.get("items")
    raw_counts = value.get("counts")
    raw_pagination = value.get("pagination")
    if actor is None or not isinstance(raw_items, list) or len(raw_items) > 50:
        return None
    items = []
    for raw_item in raw_items:
        item = clean_review_submission_summary(raw_item)
        if item is None:
            return None
        items.append(item)
    privileged = bool(set(actor["roles"]).intersection({"admin", "super_admin"}))
    if not privileged:
        for item in items:
            if item["owner"]["id"] == actor["id"]:
                return None
            assigned = item.get("assigned_reviewer")
            is_public_waiting = item["status"] == "submitted" and assigned is None
            is_owned_open = (
                isinstance(assigned, dict)
                and assigned.get("id") == actor["id"]
                and item["status"] in REVIEW_OPEN_STATUSES
            )
            if not (is_public_waiting or is_owned_open):
                return None
    if not isinstance(raw_counts, dict) or not isinstance(raw_pagination, dict):
        return None
    counts = {}
    for key in ("open", "submitted", "in_review", "completed"):
        count = raw_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        counts[key] = count
    pagination = {}
    for key in ("offset", "limit", "total"):
        number = raw_pagination.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return None
        pagination[key] = number
    pagination["has_more"] = raw_pagination.get("has_more") is True
    return {"actor": actor, "items": items, "counts": counts, "pagination": pagination}


def review_item_matches_filters(item: dict, status_filter: str, assignment_filter: str, actor_id: str) -> bool:
    status = item.get("status")
    assigned_id = (item.get("assigned_reviewer") or {}).get("id")
    status_matches = (
        status_filter == "all"
        or status_filter == status
        or (status_filter == "open" and status in REVIEW_OPEN_STATUSES)
        or (
            status_filter == "completed"
            and status in {"changes_requested", "rejected", "approved", "withdrawn"}
        )
    )
    assignment_matches = (
        assignment_filter == "all"
        or (assignment_filter == "unassigned" and assigned_id is None)
        or (assignment_filter == "mine" and assigned_id == actor_id)
    )
    return status_matches and assignment_matches


def clean_review_detail_result(
    value,
    expected_submission_id: str,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_review_actor(
        value.get("actor"),
        expected_actor_id=expected_actor_id,
        expected_roles=expected_roles,
    )
    submission = value.get("submission")
    image = value.get("image")
    owner = value.get("owner")
    if actor is None or not isinstance(submission, dict) or not isinstance(image, dict) or not isinstance(owner, dict):
        return None
    try:
        submission_id = clean_uuid(submission.get("id"), "review submission id")
        owner_id = clean_uuid(owner.get("id"), "owner id")
        image_id = clean_uuid(image.get("id"), "image id")
    except ValueError:
        return None
    if submission_id != expected_submission_id:
        return None
    status = clean_text(submission.get("status"), 40)
    lock_version = submission.get("lock_version")
    assigned = clean_review_person(submission.get("assigned_reviewer"), required=False)
    version = image.get("version")
    if (
        status not in REVIEW_STATUSES
        or isinstance(lock_version, bool)
        or not isinstance(lock_version, int)
        or lock_version < 1
        or not isinstance(version, dict)
    ):
        return None
    privileged = bool(set(actor["roles"]).intersection({"admin", "super_admin"}))
    if not privileged and (
        owner_id == actor["id"]
        or assigned is None
        or assigned.get("id") != actor["id"]
        or status not in REVIEW_OPEN_STATUSES
    ):
        return None
    try:
        version_id = clean_uuid(version.get("id"), "image version id")
    except ValueError:
        return None
    version_number = version.get("version_number")
    if isinstance(version_number, bool) or not isinstance(version_number, int) or version_number < 1:
        return None

    raw_assets = value.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) != 3:
        return None
    assets = []
    for raw_asset in raw_assets:
        asset = clean_review_asset(raw_asset)
        if asset is None:
            return None
        assets.append(asset)
    if {asset["kind"] for asset in assets} != WORKSPACE_ASSET_KINDS:
        return None

    tags = version.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [clean_text(tag, 80) for tag in tags if isinstance(tag, str) and clean_text(tag, 80)][:40]
    public_exif = version.get("public_exif") if isinstance(version.get("public_exif"), dict) else {}
    public_exif = {
        key: public_exif[key]
        for key in ("camera", "lens", "exposure", "aperture", "iso", "focal_length")
        if key in public_exif and isinstance(public_exif[key], (str, int, float)) and not isinstance(public_exif[key], bool)
    }
    readiness = clean_workspace_submit_readiness(submission.get("readiness_snapshot"))
    if readiness is None or readiness["image_id"] != image_id:
        return None

    decisions = []
    raw_decisions = value.get("decisions")
    if not isinstance(raw_decisions, list):
        return None
    for raw_decision in raw_decisions:
        if not isinstance(raw_decision, dict):
            return None
        try:
            decision_id = clean_uuid(raw_decision.get("id"), "review decision id")
        except ValueError:
            return None
        decision_code = clean_text(raw_decision.get("decision"), 40)
        reviewer = clean_review_person(raw_decision.get("reviewer"))
        reason_codes = raw_decision.get("reason_codes")
        if decision_code not in REVIEW_DECISIONS.union({"escalate", "quarantine"}) or reviewer is None or not isinstance(reason_codes, list):
            return None
        internal_note = clean_text(raw_decision.get("internal_note"), 2000) or None
        if not privileged and reviewer["id"] != actor["id"] and internal_note is not None:
            return None
        decisions.append({
            "id": decision_id,
            "decision": decision_code,
            "reason_codes": [clean_text(code, 80) for code in reason_codes if isinstance(code, str)][:8],
            "user_message": clean_text(raw_decision.get("user_message"), 1000),
            "internal_note": internal_note,
            "policy_version": clean_text(raw_decision.get("policy_version"), 120),
            "created_at": clean_text(raw_decision.get("created_at"), 80),
            "reviewer": reviewer,
        })

    workflow_status = clean_text(image.get("workflow_status"), 40)
    publication_status = clean_text(image.get("publication_status"), 40)
    processing_status = clean_text(image.get("processing_status"), 40)
    if workflow_status not in {"submitted", "in_review", "changes_requested", "rejected", "approved"}:
        return None
    if publication_status not in {"never_published", "published", "unpublished", "quarantined", "archived", "deleted"}:
        return None
    if processing_status not in {"pending", "uploading", "processing", "ready", "failed", "canceled"}:
        return None
    return {
        "actor": actor,
        "submission": {
            "id": submission_id,
            "status": status,
            "lock_version": lock_version,
            "policy_version": clean_text(submission.get("policy_version"), 120),
            "submitted_at": clean_text(submission.get("submitted_at"), 80),
            "review_started_at": clean_text(submission.get("review_started_at"), 80) or None,
            "completed_at": clean_text(submission.get("completed_at"), 80) or None,
            "assigned_reviewer": assigned,
            "readiness": readiness,
        },
        "owner": {
            "id": owner_id,
            "display_name": clean_text(owner.get("display_name"), 120) or "Member",
            "account_status": clean_text(owner.get("account_status"), 40),
            "created_at": clean_text(owner.get("created_at"), 80),
        },
        "image": {
            "id": image_id,
            "workflow_status": workflow_status,
            "publication_status": publication_status,
            "processing_status": processing_status,
            "published_at": clean_text(image.get("published_at"), 80) or None,
            "original_filename": clean_text(image.get("original_filename"), 512),
            "original_width": image.get("original_width") if isinstance(image.get("original_width"), int) and not isinstance(image.get("original_width"), bool) else None,
            "original_height": image.get("original_height") if isinstance(image.get("original_height"), int) and not isinstance(image.get("original_height"), bool) else None,
            "version": {
                "id": version_id,
                "version_number": version_number,
                "title": clean_text(version.get("title"), 180),
                "caption": clean_text(version.get("caption"), 500),
                "description": clean_text(version.get("description"), 6000),
                "alt_text": clean_text(version.get("alt_text"), 500),
                "tags": tags,
                "content_category": clean_text(version.get("content_category"), 80) or None,
                "captured_at": clean_text(version.get("captured_at"), 80) or None,
                "location_name": clean_text(version.get("location_name"), 240) or None,
                "public_exif": public_exif,
                "copyright_holder": clean_text(version.get("copyright_holder"), 160) or None,
                "copyright_year": version.get("copyright_year") if isinstance(version.get("copyright_year"), int) and not isinstance(version.get("copyright_year"), bool) else None,
                "contains_recognizable_people": version.get("contains_recognizable_people") if isinstance(version.get("contains_recognizable_people"), bool) else None,
                "model_release_status": clean_text(version.get("model_release_status"), 40) or None,
                "property_release_status": clean_text(version.get("property_release_status"), 40) or None,
                "rights_declared": version.get("rights_declared") is True,
                "ai_disclosure": clean_text(version.get("ai_disclosure"), 40) or None,
                "sensitive_content_disclosure": clean_text(version.get("sensitive_content_disclosure"), 80) or None,
            },
        },
        "assets": assets,
        "decisions": decisions,
    }


def clean_review_mutation_result(value, expected_submission_id: str) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("submission"), dict):
        return None
    submission = value["submission"]
    try:
        submission_id = clean_uuid(submission.get("id"), "review submission id")
    except ValueError:
        return None
    status = clean_text(submission.get("status"), 40)
    lock_version = submission.get("lock_version")
    if (
        submission_id != expected_submission_id
        or status not in REVIEW_STATUSES
        or isinstance(lock_version, bool)
        or not isinstance(lock_version, int)
        or lock_version < 1
    ):
        return None
    result = {
        "submission": {
            "id": submission_id,
            "status": status,
            "lock_version": lock_version,
            "review_started_at": clean_text(submission.get("review_started_at"), 80) or None,
            "completed_at": clean_text(submission.get("completed_at"), 80) or None,
        }
    }
    assigned_id = submission.get("assigned_reviewer_id")
    if assigned_id:
        try:
            result["submission"]["assigned_reviewer_id"] = clean_uuid(assigned_id, "assigned reviewer id")
        except ValueError:
            return None
    decision = value.get("decision")
    if decision is not None:
        if not isinstance(decision, dict):
            return None
        try:
            decision_id = clean_uuid(decision.get("id"), "review decision id")
        except ValueError:
            return None
        decision_code = clean_text(decision.get("decision"), 40)
        if decision_code not in REVIEW_DECISIONS:
            return None
        result["decision"] = {
            "id": decision_id,
            "decision": decision_code,
            "created_at": clean_text(decision.get("created_at"), 80) or None,
        }
    image = value.get("image")
    if image is not None:
        if not isinstance(image, dict):
            return None
        try:
            image_id = clean_uuid(image.get("id"), "review image id")
        except ValueError:
            return None
        workflow_status = clean_text(image.get("workflow_status"), 40)
        publication_status = clean_text(image.get("publication_status"), 40)
        if workflow_status not in {"submitted", "in_review", "changes_requested", "rejected", "approved"}:
            return None
        if publication_status not in {"never_published", "published", "unpublished", "quarantined", "archived", "deleted"}:
            return None
        result["image"] = {
            "id": image_id,
            "workflow_status": workflow_status,
            "publication_status": publication_status,
            "published_at": clean_text(image.get("published_at"), 80) or None,
        }
    return result


def valid_profile_https_url(value: str, *, allowed_hosts: set[str] | None = None) -> bool:
    parsed = urlparse(value)
    try:
        port = parsed.port
        hostname = parsed.hostname or ""
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or parsed.username
        or parsed.password
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", parsed.netloc)
    ):
        return False
    if allowed_hosts is not None and (hostname.lower() not in allowed_hosts or port is not None):
        return False
    return True


def clean_profile_result(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    display_name = clean_text(value.get("display_name"), 120)
    if not display_name:
        return None

    profile = {
        "display_name": display_name,
        "avatar_url": clean_text(value.get("avatar_url"), 2048) or None,
    }
    for field, maximum in (
        ("bio", 1600),
        ("copyright_name", 160),
        ("professional_headline", 160),
        ("company", 160),
        ("city", 120),
    ):
        raw_value = value.get(field)
        if raw_value is not None and not isinstance(raw_value, str):
            return None
        normalized = clean_text(raw_value, maximum)
        if isinstance(raw_value, str) and len(raw_value.strip()) > maximum:
            return None
        profile[field] = normalized or None

    for field in ("website_url", "instagram_url", "linkedin_url"):
        raw_value = value.get(field)
        if raw_value is not None and not isinstance(raw_value, str):
            return None
        normalized = clean_text(raw_value, 2048)
        if isinstance(raw_value, str) and len(raw_value.strip()) > 2048:
            return None
        if normalized and not valid_profile_https_url(
            normalized,
            allowed_hosts=PROFILE_SOCIAL_HOSTS.get(field),
        ):
            return None
        profile[field] = normalized or None

    country_code = clean_text(value.get("country_code"), 2).upper()
    if country_code and not re.fullmatch(r"[A-Z]{2}", country_code):
        return None
    profile["country_code"] = country_code or None

    locale = clean_text(value.get("preferred_locale"), 35)
    timezone_name = clean_text(value.get("timezone"), 64)
    license_preference = clean_text(value.get("default_license_preference"), 64)
    availability = clean_text(value.get("availability_status"), 32) or "unavailable"
    if (
        locale not in PROFILE_LOCALES
        or not timezone_name
        or (license_preference and license_preference not in PROFILE_LICENSES)
        or availability not in PROFILE_AVAILABILITY_STATUSES
    ):
        return None
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    profile["preferred_locale"] = locale
    profile["timezone"] = timezone_name
    profile["default_license_preference"] = license_preference or None
    profile["availability_status"] = availability
    return {field: profile.get(field) for field in PROFILE_FIELDS}


def normalize_profile_update(body: dict) -> tuple[dict, dict]:
    """Return a PostgREST-safe profile patch and stable field errors."""
    updates: dict = {}
    field_errors: dict[str, str] = {}
    unknown = sorted(set(body) - set(PROFILE_EDITABLE_FIELDS))
    for field in unknown:
        field_errors[field] = "This field cannot be updated."

    def text_value(field: str, maximum: int, *, required: bool = False) -> str | None:
        if field not in body:
            return None
        value = body.get(field)
        if value is None and not required:
            return ""
        if not isinstance(value, str):
            field_errors[field] = "Enter text for this field."
            return None
        normalized = value.strip()
        if required and not normalized:
            field_errors[field] = "This field is required."
            return None
        if len(normalized) > maximum:
            field_errors[field] = f"Use {maximum} characters or fewer."
            return None
        return normalized

    display_name = text_value("display_name", 120, required=True)
    if "display_name" in body and display_name is not None:
        updates["display_name"] = display_name

    for field, maximum in (
        ("website_url", 2048),
        ("instagram_url", 2048),
        ("linkedin_url", 2048),
    ):
        value = text_value(field, maximum)
        if field not in body or value is None:
            continue
        allowed_hosts = PROFILE_SOCIAL_HOSTS.get(field)
        if value and not valid_profile_https_url(value, allowed_hosts=allowed_hosts):
            field_errors[field] = (
                f"Use an HTTPS {field.removesuffix('_url').title()} address."
                if allowed_hosts
                else "Use a complete HTTPS address."
            )
            continue
        updates[field] = value or None

    bio = text_value("bio", 1600)
    if "bio" in body and bio is not None:
        updates["bio"] = bio or None

    for field, maximum in (
        ("professional_headline", 160),
        ("company", 160),
        ("city", 120),
    ):
        value = text_value(field, maximum)
        if field in body and value is not None:
            updates[field] = value or None

    availability_status = text_value("availability_status", 32, required=True)
    if "availability_status" in body and availability_status is not None:
        if availability_status not in PROFILE_AVAILABILITY_STATUSES:
            field_errors["availability_status"] = "Choose an available work status."
        else:
            updates["availability_status"] = availability_status

    country_code = text_value("country_code", 2)
    if "country_code" in body and country_code is not None:
        if country_code and not re.fullmatch(r"[A-Za-z]{2}", country_code):
            field_errors["country_code"] = "Use a two-letter country code."
        else:
            updates["country_code"] = country_code.upper() or None

    preferred_locale = text_value("preferred_locale", 35, required=True)
    if "preferred_locale" in body and preferred_locale is not None:
        if preferred_locale not in PROFILE_LOCALES:
            field_errors["preferred_locale"] = "Choose one of the available languages."
        else:
            updates["preferred_locale"] = preferred_locale

    timezone_name = text_value("timezone", 64, required=True)
    if "timezone" in body and timezone_name is not None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            field_errors["timezone"] = "Choose a valid IANA timezone."
        else:
            updates["timezone"] = timezone_name

    copyright_name = text_value("copyright_name", 160)
    if "copyright_name" in body and copyright_name is not None:
        updates["copyright_name"] = copyright_name or None

    license_preference = text_value("default_license_preference", 64)
    if "default_license_preference" in body and license_preference is not None:
        if license_preference and license_preference not in PROFILE_LICENSES:
            field_errors["default_license_preference"] = "Choose one of the available license preferences."
        else:
            updates["default_license_preference"] = license_preference or None

    return updates, field_errors


def normalize_profile_cover_update(body: dict) -> tuple[str | None, dict]:
    field_errors: dict[str, str] = {}
    for field in sorted(set(body) - {"asset_id"}):
        field_errors[field] = "This field cannot be used for a profile cover."
    if "asset_id" not in body:
        field_errors["asset_id"] = "Choose a cover image or clear the current cover."
        return None, field_errors
    if body.get("asset_id") is None:
        return None, field_errors
    try:
        asset_id = clean_uuid(body.get("asset_id"), "profile cover asset id")
    except ValueError:
        field_errors["asset_id"] = "Choose an available cover image."
        return None, field_errors
    return asset_id, field_errors


def normalize_workspace_folder_name(value) -> tuple[str, dict]:
    if not isinstance(value, str):
        return "", {"name": "Enter a folder name."}
    name = value.strip()
    if not name or len(name) > 120 or any(ord(character) < 32 or ord(character) == 127 for character in name):
        return "", {"name": "Use a folder name between 1 and 120 characters."}
    return name, {}


def normalize_workspace_upload_intent(body: dict) -> tuple[dict, dict]:
    field_errors: dict[str, str] = {}
    allowed = {"folder_id", "original_filename", "original_width", "original_height", "checksum_sha256", "assets"}
    for field in sorted(set(body) - allowed):
        field_errors[field] = "This field cannot be used for an upload intent."

    folder_id = None
    if body.get("folder_id") is not None and body.get("folder_id") != "":
        try:
            folder_id = clean_uuid(body.get("folder_id"), "folder id")
        except ValueError:
            field_errors["folder_id"] = "Choose an available folder."

    original_filename = body.get("original_filename")
    if not isinstance(original_filename, str):
        field_errors["original_filename"] = "Original filename is required."
        original_filename = ""
    else:
        original_filename = original_filename.strip()
        if (
            not original_filename
            or len(original_filename) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in original_filename)
        ):
            field_errors["original_filename"] = "Original filename is invalid."

    dimensions: dict[str, int] = {}
    for field in ("original_width", "original_height"):
        value = body.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 100_000:
            field_errors[field] = "Image dimensions are invalid."
        else:
            dimensions[field] = value

    checksum = clean_text(body.get("checksum_sha256"), 64).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        field_errors["checksum_sha256"] = "Original checksum is invalid."

    raw_assets = body.get("assets")
    normalized_assets: list[dict] = []
    if not isinstance(raw_assets, list) or len(raw_assets) != 3:
        field_errors["assets"] = "Original, display, and thumbnail assets are required."
    else:
        seen_kinds: set[str] = set()
        for index, asset in enumerate(raw_assets):
            key = f"assets[{index}]"
            if not isinstance(asset, dict):
                field_errors[key] = "Asset metadata must be an object."
                continue
            kind = clean_text(asset.get("kind"), 32).lower()
            mime_type = clean_text(asset.get("mime_type"), 120).lower()
            byte_size = asset.get("byte_size")
            width = asset.get("width")
            height = asset.get("height")
            asset_checksum = clean_text(asset.get("checksum_sha256"), 64).lower()
            if kind not in WORKSPACE_ASSET_KINDS or kind in seen_kinds:
                field_errors[key] = "Asset kinds must be unique original, display, and thumbnail values."
                continue
            seen_kinds.add(kind)
            if mime_type not in WORKSPACE_IMAGE_MIME_TYPES:
                field_errors[key] = "Asset MIME type is not supported."
                continue
            if (
                not isinstance(byte_size, int)
                or isinstance(byte_size, bool)
                or byte_size < 1
                or byte_size > WORKSPACE_ASSET_LIMITS[kind]
            ):
                field_errors[key] = "Asset size exceeds the server limit."
                continue
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 100_000
                for value in (width, height)
            ):
                field_errors[key] = "Asset dimensions are invalid."
                continue
            if not re.fullmatch(r"[0-9a-f]{64}", asset_checksum):
                field_errors[key] = "Asset checksum is invalid."
                continue
            normalized_assets.append({
                "kind": kind,
                "mime_type": mime_type,
                "byte_size": byte_size,
                "width": width,
                "height": height,
                "checksum_sha256": asset_checksum,
            })
        if seen_kinds != WORKSPACE_ASSET_KINDS:
            field_errors["assets"] = "Original, display, and thumbnail assets are required."

    original_asset = next((asset for asset in normalized_assets if asset["kind"] == "original"), None)
    if original_asset and dimensions:
        if original_asset["width"] != dimensions.get("original_width") or original_asset["height"] != dimensions.get("original_height"):
            field_errors["assets"] = "Original asset dimensions must match the image metadata."
        if original_asset["checksum_sha256"] != checksum:
            field_errors["assets"] = "Original asset checksum must match the upload metadata."

    return {
        "folder_id": folder_id,
        "original_filename": original_filename,
        **dimensions,
        "checksum_sha256": checksum,
        "assets": normalized_assets,
    }, field_errors


def normalize_workspace_draft_patch(
    body: dict,
    *,
    allow_empty: bool = False,
    allow_compliance: bool = True,
) -> tuple[dict, dict]:
    updates: dict = {}
    field_errors: dict[str, str] = {}
    allowed_fields = WORKSPACE_DRAFT_FIELDS if allow_compliance else WORKSPACE_DRAFT_CORE_FIELDS
    for field in sorted(set(body) - allowed_fields):
        field_errors[field] = "This Draft field cannot be updated."

    if "folder_id" in body:
        try:
            updates["folder_id"] = clean_uuid(body.get("folder_id"), "folder id")
        except ValueError:
            field_errors["folder_id"] = "Choose an available folder."

    def text_field(name: str, maximum: int) -> None:
        if name not in body:
            return
        value = body.get(name)
        if not isinstance(value, str):
            field_errors[name] = "Enter text for this field."
            return
        normalized = value.strip()
        if len(normalized) > maximum:
            field_errors[name] = f"Use {maximum} characters or fewer."
            return
        updates[name] = normalized

    for field, maximum in (
        ("title", 180),
        ("caption", 500),
        ("description", 10_000),
        ("alt_text", 500),
        ("location_name", 500),
        ("copyright_holder", 160),
    ):
        text_field(field, maximum)

    if "tags" in body:
        tags = body.get("tags")
        if (
            not isinstance(tags, list)
            or len(tags) > 30
            or any(not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 64 for tag in tags)
        ):
            field_errors["tags"] = "Use at most 30 tags of 64 characters or fewer."
        else:
            updates["tags"] = unique_text_values(tags)

    if "content_category" in body:
        category = clean_text(body.get("content_category"), 64).lower()
        if category and category not in {"abstract", "concrete"}:
            field_errors["content_category"] = "Choose an available content category."
        else:
            updates["content_category"] = category or None

    if "captured_at" in body:
        captured_at = clean_text(body.get("captured_at"), 40)
        if captured_at:
            try:
                datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except ValueError:
                field_errors["captured_at"] = "Use a valid captured date."
            else:
                updates["captured_at"] = captured_at
        else:
            updates["captured_at"] = None

    if "copyright_year" in body:
        copyright_year = body.get("copyright_year")
        maximum_year = datetime.now(timezone.utc).year + 1
        if copyright_year is None:
            updates["copyright_year"] = None
        elif isinstance(copyright_year, bool) or not isinstance(copyright_year, int):
            field_errors["copyright_year"] = "Enter a valid copyright year."
        elif not 1000 <= copyright_year <= maximum_year:
            field_errors["copyright_year"] = f"Use a year from 1000 to {maximum_year}."
        else:
            updates["copyright_year"] = copyright_year

    if "contains_recognizable_people" in body:
        people_value = body.get("contains_recognizable_people")
        if people_value is not None and not isinstance(people_value, bool):
            field_errors["contains_recognizable_people"] = "Choose Yes, No, or Not set."
        else:
            updates["contains_recognizable_people"] = people_value

    if "rights_declared" in body:
        rights_value = body.get("rights_declared")
        if not isinstance(rights_value, bool):
            field_errors["rights_declared"] = "Confirm whether you control the required rights."
        else:
            updates["rights_declared"] = rights_value

    def enum_field(name: str, choices: set[str], message: str) -> None:
        if name not in body:
            return
        value = body.get(name)
        if value is None or value == "":
            updates[name] = None
            return
        if not isinstance(value, str) or value not in choices:
            field_errors[name] = message
            return
        updates[name] = value

    enum_field("model_release_status", WORKSPACE_RELEASE_STATUSES, "Choose an available model release status.")
    enum_field("property_release_status", WORKSPACE_RELEASE_STATUSES, "Choose an available property release status.")
    enum_field("ai_disclosure", WORKSPACE_AI_DISCLOSURES, "Choose an available AI disclosure.")
    enum_field(
        "sensitive_content_disclosure",
        WORKSPACE_SENSITIVE_DISCLOSURES,
        "Choose an available sensitive content disclosure.",
    )

    if not allow_empty and not updates and not field_errors:
        field_errors["draft"] = "Choose at least one Draft field to update."
    return updates, field_errors


def unique_text_values(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def user_agent_summary(user_agent: str) -> dict[str, str]:
    """Return intentionally coarse device data without exposing fingerprinting details."""
    value = clean_text(user_agent, 512)
    if "Edg/" in value:
        browser = "Edge"
    elif "OPR/" in value or "Opera/" in value:
        browser = "Opera"
    elif "Chrome/" in value or "CriOS/" in value:
        browser = "Chrome"
    elif "Firefox/" in value or "FxiOS/" in value:
        browser = "Firefox"
    elif "Safari/" in value:
        browser = "Safari"
    else:
        browser = "Unknown browser"

    if "iPhone" in value:
        device = "iPhone"
        operating_system = "iOS"
    elif "iPad" in value:
        device = "iPad"
        operating_system = "iPadOS"
    elif "Android" in value:
        device = "Android device"
        operating_system = "Android"
    elif "Macintosh" in value or "Mac OS X" in value:
        device = "Mac"
        operating_system = "macOS"
    elif "Windows" in value:
        device = "PC"
        operating_system = "Windows"
    elif "Linux" in value:
        device = "Computer"
        operating_system = "Linux"
    else:
        device = "Unknown device"
        operating_system = "Unknown system"
    return {"browser": browser, "device": device, "operating_system": operating_system}


def jwt_timestamp_iso(value) -> str | None:
    try:
        timestamp = int(value)
        return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def positive_int(value, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {field_name}.") from error
    if number <= 0:
        raise ValueError(f"Invalid {field_name}.")
    return number


def non_negative_int(value, field_name: str, fallback: int = 0) -> int:
    if value is None or value == "":
        return fallback
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {field_name}.") from error
    if number < 0:
        raise ValueError(f"Invalid {field_name}.")
    return number


def optional_json_object(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    text = clean_text(value)
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def optional_json_list(value, fallback=None):
    if fallback is None:
        fallback = []
    parsed = optional_json_object(value, fallback)
    return parsed if isinstance(parsed, list) else fallback


def mime_extension(mime_type: str, fallback: str = "jpg") -> str:
    return MIME_EXTENSIONS.get(clean_text(mime_type).lower(), fallback)


def safe_upload_filename(asset: dict, file_part: dict, index: int) -> str:
    kind = clean_text(asset.get("kind")) or "asset"
    raw_name = clean_text(asset.get("storage_path") or file_part.get("filename") or asset.get("id") or kind)
    raw_name = raw_name.replace("\\", "/").split("/")[-1]
    raw_stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", raw_name)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_stem).strip("-_").lower()
    if not stem:
        stem = f"{kind}-{index}"
    if not stem.startswith(kind):
        stem = f"{kind}-{stem}"
    extension = mime_extension(file_part.get("content_type") or asset.get("mime_type"))
    return f"{stem[:96]}.{extension}"


def normalize_archive_assets(value, image_id: str) -> list[dict]:
    if not isinstance(value, list):
        return []
    assets: list[dict] = []
    seen_ids: set[str] = set()
    for index, asset in enumerate(value):
        if not isinstance(asset, dict):
            continue
        kind = clean_text(asset.get("kind")).lower()
        if kind not in ARCHIVE_ASSET_KINDS:
            raise ValueError("Invalid asset kind.")
        asset_id = clean_identifier(asset.get("id") or f"{image_id}-{kind}-{index}", "asset id")
        if asset_id in seen_ids:
            raise ValueError("Duplicate asset id.")
        seen_ids.add(asset_id)
        assets.append(
            {
                "id": asset_id,
                "image_id": image_id,
                "kind": kind,
                "storage_bucket": clean_text(asset.get("storage_bucket"), 120) or "local-upload-assets",
                "storage_path": clean_text(asset.get("storage_path"), 512),
                "public_url": clean_text(asset.get("public_url"), 512) or None,
                "url_expires_at": clean_text(asset.get("url_expires_at"), 80) or None,
                "mime_type": clean_text(asset.get("mime_type"), 120) or "image/jpeg",
                "byte_size": non_negative_int(asset.get("byte_size"), "asset byte_size", 0) or None,
                "width": positive_int(asset.get("width"), "asset width"),
                "height": positive_int(asset.get("height"), "asset height"),
                "checksum_sha256": clean_text(asset.get("checksum_sha256"), 64) or None,
                "source_asset_id": clean_text(asset.get("source_asset_id"), 128) or None,
            }
        )
    return sorted(assets, key=lambda asset: ARCHIVE_ASSET_KIND_ORDER.get(asset["kind"], 99))


def normalize_archive_square_slices(value, image_id: str, asset_ids: set[str]) -> list[dict]:
    if not isinstance(value, list):
        return []
    slices: list[dict] = []
    seen_ids: set[str] = set()
    for index, slice_row in enumerate(value):
        if not isinstance(slice_row, dict):
            continue
        slice_id = clean_identifier(slice_row.get("id") or f"{image_id}-slice-{index}", "slice id")
        if slice_id in seen_ids:
            raise ValueError("Duplicate square slice id.")
        seen_ids.add(slice_id)
        asset_id = clean_identifier(slice_row.get("asset_id"), "square slice asset id")
        if asset_id not in asset_ids:
            raise ValueError("Square slice asset does not exist.")
        width = positive_int(slice_row.get("width"), "square slice width")
        height = positive_int(slice_row.get("height"), "square slice height")
        if width != height:
            raise ValueError("Square slice width and height must match.")
        slices.append(
            {
                "id": slice_id,
                "image_id": image_id,
                "asset_id": asset_id,
                "slice_index": non_negative_int(slice_row.get("slice_index"), "square slice index", index),
                "source_x": non_negative_int(slice_row.get("source_x"), "square slice source_x", 0),
                "source_y": non_negative_int(slice_row.get("source_y"), "square slice source_y", 0),
                "source_size": positive_int(slice_row.get("source_size"), "square slice source_size"),
                "width": width,
                "height": height,
            }
        )
    return slices


def archive_image_payload(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["tags"] = parse_archive_json(payload.get("tags"), [])
    payload["tag_groups"] = parse_archive_json(payload.get("tag_groups"), [])
    payload["square_slice_count"] = int(payload.get("square_slice_count") or 0)
    return payload


def single_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key) or []
    return values[0].strip() if values else default


def archive_query_filters(query: dict[str, list[str]]) -> tuple[list[str], list, int]:
    filters: list[str] = []
    params: list = []

    visibility = single_query_value(query, "visibility").lower()
    if not visibility:
        filters.append("visibility = ?")
        params.append("published")
    elif visibility != "all":
        if visibility not in ARCHIVE_VISIBILITIES:
            raise ValueError("Invalid visibility filter.")
        filters.append("visibility = ?")
        params.append(visibility)

    include_missing_assets = single_query_value(query, "include_missing_assets").lower()
    if include_missing_assets not in {"1", "true", "yes"}:
        filters.append("image_url IS NOT NULL")

    content_type = single_query_value(query, "type").lower()
    if content_type:
        if content_type not in ARCHIVE_CONTENT_TYPES:
            raise ValueError("Invalid type filter.")
        filters.append("content_type = ?")
        params.append(ARCHIVE_CONTENT_TYPES[content_type])

    ratio = single_query_value(query, "ratio")
    if ratio:
        ratio_key = ratio.lower()
        ratio_code = ARCHIVE_RATIO_CODES.get(ratio) or ARCHIVE_RATIO_CODES.get(ratio_key) or ratio_key
        if ratio_code not in set(ARCHIVE_RATIO_CODES.values()):
            raise ValueError("Invalid ratio filter.")
        filters.append("ratio_category_code = ?")
        params.append(ratio_code)

    raw_limit = single_query_value(query, "limit", "500")
    try:
        limit = int(raw_limit)
    except ValueError as error:
        raise ValueError("Invalid limit.") from error
    limit = max(1, min(limit, 1000))

    return filters, params, limit


def normalize_archive_update_payload(payload: dict) -> dict:
    content_type = clean_text(payload.get("content_type")).lower()
    if content_type not in ARCHIVE_CONTENT_TYPES:
        raise ValueError("Invalid content_type.")

    display_mode = clean_text(payload.get("display_mode")).lower()
    if display_mode not in ARCHIVE_DISPLAY_MODES:
        raise ValueError("Invalid display_mode.")

    if (content_type == "abstract" and display_mode != "black_white") or (content_type == "concrete" and display_mode != "color"):
        raise ValueError("content_type and display_mode do not match the archive schema rules.")

    visibility = clean_text(payload.get("visibility")).lower() or "draft"
    if visibility not in ARCHIVE_VISIBILITIES:
        raise ValueError("Invalid visibility.")

    title = clean_text(payload.get("title"), 180)
    if not title:
        raise ValueError("Title is required.")

    try:
        sort_order = int(payload.get("sort_order") or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid sort_order.") from error

    return {
        "title": title,
        "description": clean_text(payload.get("description"), 4000),
        "curatorial_note": clean_text(payload.get("curatorial_note"), 2400),
        "artist_statement": clean_text(payload.get("artist_statement"), 6000),
        "series": clean_text(payload.get("series"), 240),
        "captured_at": clean_text(payload.get("captured_at"), 64) or None,
        "content_type": content_type,
        "display_mode": display_mode,
        "visibility": visibility,
        "sort_order": sort_order,
        "tag_groups": normalize_tag_groups(payload.get("tag_groups")),
        "updated_at": now_iso(),
    }


def normalize_tag_groups(value) -> list[dict]:
    if not isinstance(value, list):
        return []

    groups: list[dict] = []
    seen_groups: set[str] = set()
    for group in value:
        if not isinstance(group, dict):
            continue
        label = clean_text(group.get("label") or group.get("group_name") or group.get("groupName"), 80)
        if not label:
            continue
        key = label.lower()
        if key in seen_groups:
            continue
        tags = []
        seen_tags: set[str] = set()
        raw_tags = group.get("tags") or []
        if not isinstance(raw_tags, list):
            continue
        for tag in raw_tags:
            text = clean_text(tag, 120)
            tag_key = text.lower()
            if text and tag_key not in seen_tags:
                tags.append(text)
                seen_tags.add(tag_key)
        if tags:
            groups.append({"label": label, "tags": tags})
            seen_groups.add(key)
    return groups


def replace_image_tags(connection: sqlite3.Connection, image_id: str, tag_groups: list[dict], timestamp: str) -> None:
    connection.execute("DELETE FROM image_taggings WHERE image_id = ?", (image_id,))

    tag_order = 0
    for group_index, group in enumerate(tag_groups):
        group_name = group["label"]
        group_sort = TAG_GROUP_SORT_ORDER.get(group_name, (group_index + 1) * 100)
        for tag_name in group["tags"]:
            tag_slug = slugify(tag_name, "tag")
            tag_id = f"tag-{slugify(group_name, 'group')}-{tag_slug}"
            connection.execute(
                """
                INSERT INTO image_tags (id, name, slug, group_name, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_name, slug) DO UPDATE SET
                  name = excluded.name,
                  sort_order = excluded.sort_order
                """,
                (tag_id, tag_name, tag_slug, group_name, group_sort, timestamp),
            )
            connection.execute(
                """
                INSERT INTO image_taggings (image_id, tag_id, sort_order, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (image_id, tag_id, tag_order, timestamp),
            )
            tag_order += 1


def write_upload_assets(
    connection: sqlite3.Connection,
    image_id: str,
    assets: list[dict],
    square_slices: list[dict],
    file_parts: dict[str, dict],
    timestamp: str,
) -> None:
    if not assets:
        raise ValueError("At least one upload asset is required.")

    upload_dir = UPLOAD_ASSET_ROOT / image_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    asset_ids = {asset["id"] for asset in assets}
    if not any(asset["kind"] == "original" for asset in assets):
        raise ValueError("An original upload asset is required.")

    for index, asset in enumerate(assets):
        file_part = file_parts.get(asset["id"])
        if file_part:
            file_body = file_part["body"]
            if not file_body:
                raise ValueError("Upload asset file is empty.")
            filename = safe_upload_filename(asset, file_part, index)
            asset_path = upload_dir / filename
            asset_path.write_bytes(file_body)
            checksum = hashlib.sha256(file_body).hexdigest()
            if asset["checksum_sha256"] and asset["checksum_sha256"] != checksum:
                raise ValueError("Upload asset checksum does not match.")
            asset["checksum_sha256"] = checksum
            asset["byte_size"] = len(file_body)
            asset["mime_type"] = file_part.get("content_type") or asset["mime_type"]
            asset["storage_bucket"] = "local-upload-assets"
            asset["storage_path"] = f"{image_id}/{filename}"
            asset["public_url"] = f"{UPLOAD_ASSET_URL_PREFIX}/{image_id}/{filename}"
        elif not asset["public_url"]:
            raise ValueError("Upload asset file is missing.")

        if asset["source_asset_id"] and asset["source_asset_id"] not in asset_ids:
            raise ValueError("Upload asset source_asset_id does not exist.")

        connection.execute(
            """
            INSERT INTO image_assets (
              id, image_id, kind, storage_bucket, storage_path, public_url, url_expires_at,
              mime_type, byte_size, width, height, checksum_sha256, source_asset_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset["id"],
                image_id,
                asset["kind"],
                asset["storage_bucket"],
                asset["storage_path"],
                asset["public_url"],
                asset["url_expires_at"],
                asset["mime_type"],
                asset["byte_size"],
                asset["width"],
                asset["height"],
                asset["checksum_sha256"],
                asset["source_asset_id"],
                timestamp,
            ),
        )

    for slice_row in square_slices:
        connection.execute(
            """
            INSERT INTO image_square_slices (
              id, image_id, asset_id, slice_index, source_x, source_y, source_size, width, height, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slice_row["id"],
                image_id,
                slice_row["asset_id"],
                slice_row["slice_index"],
                slice_row["source_x"],
                slice_row["source_y"],
                slice_row["source_size"],
                slice_row["width"],
                slice_row["height"],
                timestamp,
            ),
        )


class MTRequestHandler(SimpleHTTPRequestHandler):
    server_version = "MTPresenceServer/1.0"

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Never write password-recovery codes, token hashes, or other query data
        # into the default development access log.
        self.log_message(
            '"%s %s %s" %s %s',
            self.command,
            urlparse(self.path).path,
            self.request_version,
            str(code),
            str(size),
        )

    def do_HEAD(self) -> None:
        """Never let inherited static HEAD bypass private or authenticated routes."""
        canonical_path = canonical_url_path(self.path)
        protected_route = (
            canonical_path.startswith("/api/")
            or canonical_path.startswith("/admin/reviews")
            or canonical_path == "/assets/uploads"
            or canonical_path.startswith("/assets/uploads/")
            or canonical_path in {
                "/admin-reviews.html",
                "/admin-reviews.js",
                "/dashboard",
                "/dashboard.html",
                "/dashboard.js",
                "/settings/account",
                "/workspace",
                "/workspace/images",
            }
            or is_private_static_path(canonical_path)
        )
        if protected_route:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.path = canonical_path
        super().do_HEAD()

    def end_headers(self) -> None:
        for cookie in getattr(self, "_pending_response_cookies", []):
            self.send_header("Set-Cookie", cookie)
        self._pending_response_cookies = []
        if canonical_url_path(self.path) in {
            "/auth.html",
            "/auth.js",
            "/mfa.html",
            "/mfa.js",
            "/account-settings.html",
            "/account-settings.js",
            "/admin-reviews.html",
            "/admin-reviews.js",
            "/dashboard.html",
            "/dashboard.js",
            "/account-menu.js",
        }:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def request_cookies(self) -> SimpleCookie:
        cookies = SimpleCookie()
        cookies.load(self.headers.get("Cookie", ""))
        return cookies

    def cookie_value(self, name: str) -> str:
        morsel = self.request_cookies().get(name)
        return morsel.value if morsel else ""

    def request_origin(self) -> str:
        host = clean_text(self.headers.get("Host"), 255)
        if not host or not re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", host):
            return ""
        scheme = "https" if COOKIE_SECURE else "http"
        return f"{scheme}://{host}"

    def public_base_url(self) -> str:
        if PUBLIC_BASE_URL:
            parsed = urlparse(PUBLIC_BASE_URL)
            valid_scheme = parsed.scheme == "https" if COOKIE_SECURE else parsed.scheme in {"http", "https"}
            if (
                valid_scheme
                and parsed.netloc
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            ):
                return f"{parsed.scheme}://{parsed.netloc}"
            return ""

        # Local development may derive its loopback origin. Non-loopback
        # deployments must set MT_PUBLIC_BASE_URL to prevent Host injection in
        # verification and recovery emails.
        host = clean_text(self.headers.get("Host"), 255)
        if re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?", host):
            return self.request_origin()
        return ""

    def csrf_cookie_header(self, token: str) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return f"{CSRF_COOKIE}={token}; Path=/; Max-Age=3600; HttpOnly; SameSite=Strict{secure}"

    def clear_csrf_cookie_header(self) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return f"{CSRF_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}"

    def recovery_cookie_header(self, token: str) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return (
            f"{RECOVERY_COOKIE}={token}; Path=/; "
            f"Max-Age={RECOVERY_GRANT_TTL_SECONDS}; HttpOnly; SameSite=Strict{secure}"
        )

    def clear_recovery_cookie_header(self) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return f"{RECOVERY_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}"

    def handle_csrf_token(self) -> None:
        token = self.cookie_value(CSRF_COOKIE)
        if not CSRF_TOKEN_PATTERN.fullmatch(token):
            token = secrets.token_urlsafe(32)
        self.send_auth_json(HTTPStatus.OK, {"csrf_token": token}, [self.csrf_cookie_header(token)])

    def require_csrf(self, *, require_json: bool = True) -> bool:
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("CSRF_REJECTED", "The request origin could not be verified."))
            return False

        origin = clean_text(self.headers.get("Origin"), 512)
        expected_origin = self.request_origin()
        if not origin or not expected_origin or not hmac.compare_digest(origin, expected_origin):
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("CSRF_REJECTED", "The request origin could not be verified."))
            return False

        header_token = clean_text(self.headers.get("X-CSRF-Token"), 256)
        cookie_token = self.cookie_value(CSRF_COOKIE)
        if (
            not CSRF_TOKEN_PATTERN.fullmatch(header_token)
            or not CSRF_TOKEN_PATTERN.fullmatch(cookie_token)
            or not hmac.compare_digest(header_token, cookie_token)
        ):
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("CSRF_REJECTED", "The security token is missing or expired."))
            return False

        if require_json and not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, auth_error("CONTENT_TYPE_INVALID", "Use application/json for this request."))
            return False
        return True

    def session_cookie_headers(self, session: dict) -> list[str]:
        secure = "; Secure" if COOKIE_SECURE else ""
        access_age = max(60, int(session.get("expires_in") or 3600))
        refresh_age = 60 * 60 * 24 * 30
        return [
            f"{ACCESS_COOKIE}={session.get('access_token', '')}; Path=/; Max-Age={access_age}; HttpOnly; SameSite=Lax{secure}",
            f"{REFRESH_COOKIE}={session.get('refresh_token', '')}; Path=/; Max-Age={refresh_age}; HttpOnly; SameSite=Lax{secure}",
        ]

    def clear_session_cookie_headers(self) -> list[str]:
        secure = "; Secure" if COOKIE_SECURE else ""
        return [
            f"{ACCESS_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}",
            f"{REFRESH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}",
        ]

    def send_auth_json(self, status: HTTPStatus, payload: dict, cookies: list[str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookies is not None:
            # An explicit session (MFA verification/sign-out) must supersede any
            # access/refresh pair queued by current_auth_user().
            self._pending_response_cookies = []
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_current_user_error(self, status: int, payload: dict) -> None:
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            provider_error = payload if isinstance(payload, dict) and payload.get("error") else auth_error(
                "AUTH_PROVIDER_UNAVAILABLE",
                "Authentication is temporarily unavailable.",
            )
            self.send_auth_json(status, provider_error)
            return
        self.send_auth_json(HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue."))

    def current_auth_user(self) -> tuple[int, dict]:
        access_token = self.cookie_value(ACCESS_COOKIE)
        if access_token:
            status, user = supabase_auth_request("user", access_token=access_token)
            if status == HTTPStatus.OK:
                return status, user
            if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                return status, user
        refresh_token = self.cookie_value(REFRESH_COOKIE)
        if not refresh_token:
            return HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue.")
        status, session = supabase_auth_request("token?grant_type=refresh_token", {"refresh_token": refresh_token})
        if status != HTTPStatus.OK:
            if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                return status, session
            return HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue.")
        # Supabase rotates refresh tokens. Queue the replacement immediately so
        # every response path (including MFA/Admin errors) preserves the session.
        self._pending_response_cookies = self.session_cookie_headers(session)
        status, user = supabase_auth_request("user", access_token=session.get("access_token", ""))
        if status == HTTPStatus.OK:
            user["_refreshed_session"] = session
        return status, user

    def handle_auth_register(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        email = clean_text(body.get("email"), 320).lower()
        password = str(body.get("password") or "")
        display_name = clean_text(body.get("display_name"), 120)
        terms_accepted = body.get("terms_accepted") is True
        field_errors = {}
        if "@" not in email:
            field_errors["email"] = "Enter a valid email address."
        if len(password) < 10:
            field_errors["password"] = "Use at least 10 characters."
        if not display_name:
            field_errors["display_name"] = "Display name is required."
        if not terms_accepted:
            field_errors["terms_accepted"] = "Accept the Terms to continue."
        if field_errors:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUTH_VALIDATION_FAILED", "Check the highlighted fields.", field_errors))
            return
        public_base_url = self.public_base_url()
        if not public_base_url:
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                auth_error("AUTH_REDIRECT_NOT_CONFIGURED", "Email verification is not configured for this environment."),
            )
            return
        redirect_to = f"{public_base_url}/auth/verify-email"
        status, result = supabase_auth_request(f"signup?{urlencode({'redirect_to': redirect_to})}", {
            "email": email,
            "password": password,
            "data": {"display_name": display_name, "terms_policy_version": "2026-07", "terms_accepted_at": now_iso()},
        })
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_json(status, result)
            return
        if status not in {HTTPStatus.OK, HTTPStatus.CREATED}:
            self.send_json(HTTPStatus.BAD_REQUEST, auth_error("REGISTRATION_FAILED", "Unable to create this account. Check your details or try again later."))
            return
        user = result.get("user") or {}
        if result.get("access_token") and (user.get("email_confirmed_at") or user.get("confirmed_at")):
            self.send_json(HTTPStatus.CREATED, {"status": "account_ready", "message": "Account created. Sign in to continue."})
            return
        self.send_json(HTTPStatus.CREATED, {"status": "verification_required", "message": "Check your email to verify your account."})

    def handle_auth_forgot_password(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        email = clean_text(body.get("email"), 320).lower()
        if "@" not in email:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("AUTH_VALIDATION_FAILED", "Enter a valid email address.", {"email": "Enter a valid email address."}),
            )
            return
        public_base_url = self.public_base_url()
        if not public_base_url:
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                auth_error("AUTH_REDIRECT_NOT_CONFIGURED", "Password recovery is not configured for this environment."),
            )
            return
        redirect_to = f"{public_base_url}/auth/reset-password"
        status, result = supabase_auth_request(
            f"recover?{urlencode({'redirect_to': redirect_to})}",
            {"email": email},
        )
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_json(status, result)
            return
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            self.send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                auth_error("RECOVERY_RATE_LIMITED", "Please wait before requesting another reset link."),
            )
            return
        if status not in {HTTPStatus.OK, HTTPStatus.CREATED}:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("RECOVERY_REQUEST_FAILED", "Unable to send a reset link right now. Try again later."),
            )
            return
        self.send_json(
            HTTPStatus.ACCEPTED,
            {
                "status": "recovery_email_sent",
                "message": "If an account exists for this email, a reset link has been sent.",
            },
        )

    def handle_auth_callback_session(self, expected_type: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        callback_type = clean_text(body.get("type"), 32).lower()
        token_hash = clean_text(body.get("token_hash"), 2048)
        refresh_token = clean_text(body.get("refresh_token"), 4096)
        if callback_type != expected_type or not (token_hash or refresh_token):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("AUTH_CALLBACK_INVALID", "This verification link is invalid or has expired."),
            )
            return

        if token_hash:
            status, session = supabase_auth_request("verify", {"type": expected_type, "token_hash": token_hash})
        else:
            status, session = supabase_auth_request(
                "token?grant_type=refresh_token",
                {"refresh_token": refresh_token},
            )

        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_json(status, session)
            return
        if (
            status != HTTPStatus.OK
            or not session.get("access_token")
            or not session.get("refresh_token")
            or (expected_type == "recovery" and refresh_token and not session_has_auth_method(session, "recovery"))
        ):
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                auth_error("AUTH_CALLBACK_INVALID", "This verification link is invalid or has expired."),
            )
            return

        user = session.get("user") or {}
        if not user.get("id"):
            user_status, user = supabase_auth_request("user", access_token=session.get("access_token", ""))
            if user_status != HTTPStatus.OK:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    auth_error("AUTH_CALLBACK_INVALID", "This verification link is invalid or has expired."),
                )
                return
        if expected_type == "signup" and not (user.get("email_confirmed_at") or user.get("confirmed_at")):
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                auth_error("EMAIL_NOT_VERIFIED", "This verification link is invalid or has expired."),
            )
            return

        cookies = self.session_cookie_headers(session)
        payload = {"verified": True, "type": expected_type}
        if expected_type == "recovery":
            grant = create_recovery_grant(str(user.get("id")))
            cookies.append(self.recovery_cookie_header(grant))
            payload["recovery_ready"] = True
        else:
            consume_recovery_grant(self.cookie_value(RECOVERY_COOKIE))
            cookies.append(self.clear_recovery_cookie_header())
        self.send_auth_json(HTTPStatus.OK, payload, cookies)

    def handle_auth_recovery_status(self) -> None:
        status, user = self.current_auth_user()
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_current_user_error(status, user)
            return
        if status != HTTPStatus.OK:
            self.send_json(HTTPStatus.OK, {"recovery_ready": False})
            return
        if not recovery_grant_is_valid(self.cookie_value(RECOVERY_COOKIE), str(user.get("id") or "")):
            self.send_json(HTTPStatus.OK, {"recovery_ready": False})
            return
        self.send_auth_json(HTTPStatus.OK, {"recovery_ready": True})

    def handle_auth_verification_status(self) -> None:
        status, user = self.current_auth_user()
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_current_user_error(status, user)
            return
        if status != HTTPStatus.OK:
            self.send_json(HTTPStatus.OK, {"email_verified": False})
            return
        verified = bool(user.get("email_confirmed_at") or user.get("confirmed_at"))
        self.send_auth_json(HTTPStatus.OK, {"email_verified": verified})

    def handle_auth_reset_password(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        password = str(body.get("password") or "")
        password_confirmation = str(body.get("password_confirmation") or "")
        field_errors = {}
        if len(password) < 10:
            field_errors["password"] = "Use at least 10 characters."
        elif len(password) > 256:
            field_errors["password"] = "Password is too long."
        if password != password_confirmation:
            field_errors["password_confirmation"] = "Passwords do not match."
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("AUTH_VALIDATION_FAILED", "Check the highlighted fields.", field_errors),
            )
            return

        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return
        grant = self.cookie_value(RECOVERY_COOKIE)
        if not recovery_grant_is_valid(grant, str(user.get("id") or "")):
            self.send_json(
                HTTPStatus.UNAUTHORIZED,
                auth_error("RECOVERY_SESSION_REQUIRED", "Request a new password reset link to continue."),
            )
            return
        access_token = self.current_access_token(user)
        update_status, result = supabase_auth_request(
            "user",
            {"password": password},
            access_token,
            method="PUT",
        )
        if update_status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_json(update_status, result)
            return
        if update_status != HTTPStatus.OK:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "PASSWORD_UPDATE_FAILED",
                    "Choose a stronger password and try again.",
                    {"password": "Choose a stronger password and try again."},
                ),
            )
            return

        consume_recovery_grant(grant)
        supabase_auth_request("logout?scope=global", {}, access_token, method="POST")
        self.send_auth_json(
            HTTPStatus.OK,
            {"password_reset": True, "next_action": "sign-in", "message": "Password updated. Sign in with your new password."},
            [
                *self.clear_session_cookie_headers(),
                self.clear_recovery_cookie_header(),
                self.clear_csrf_cookie_header(),
            ],
        )

    def handle_auth_sign_in(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        email = clean_text(body.get("email"), 320).lower()
        password = str(body.get("password") or "")
        if not email or not password:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUTH_VALIDATION_FAILED", "Email and password are required."))
            return
        status, session = supabase_auth_request("token?grant_type=password", {"email": email, "password": password})
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
            self.send_json(status, session)
            return
        if status != HTTPStatus.OK or not session.get("access_token") or not session.get("refresh_token"):
            self.send_json(HTTPStatus.UNAUTHORIZED, auth_error("INVALID_CREDENTIALS", "Email or password is incorrect."))
            return
        user = session.get("user") or {}
        if not user.get("email_confirmed_at") and not user.get("confirmed_at"):
            supabase_auth_request("logout?scope=local", {}, session.get("access_token", ""), method="POST")
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("EMAIL_NOT_VERIFIED", "Verify your email before signing in."))
            return
        authz_status, authorization = supabase_rest_request("rpc/current_authorization", session.get("access_token", ""))
        if authz_status != HTTPStatus.OK:
            supabase_auth_request("logout?scope=local", {}, session.get("access_token", ""), method="POST")
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify account access. Try again."),
            )
            return
        if authorization.get("account_status") != "active":
            supabase_auth_request("logout?scope=local", {}, session.get("access_token", ""), method="POST")
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ACCOUNT_RESTRICTED", "This account cannot access the Workspace."),
            )
            return
        roles = set(authorization.get("roles") or [])
        next_action = "mfa" if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2" else "workspace"
        consume_recovery_grant(self.cookie_value(RECOVERY_COOKIE))
        self.send_auth_json(
            HTTPStatus.OK,
            {"user": {"id": user.get("id"), "email": user.get("email")}, "next_action": next_action},
            [*self.session_cookie_headers(session), self.clear_recovery_cookie_header()],
        )

    def handle_auth_sign_out(self) -> None:
        status, user = self.current_auth_user()
        if status == HTTPStatus.OK:
            supabase_auth_request("logout?scope=local", {}, self.current_access_token(user), method="POST")
        grant = self.cookie_value(RECOVERY_COOKIE)
        consume_recovery_grant(grant)
        self.send_auth_json(
            HTTPStatus.OK,
            {"signed_out": True},
            [
                *self.clear_session_cookie_headers(),
                self.clear_recovery_cookie_header(),
                self.clear_csrf_cookie_header(),
            ],
        )

    def handle_me(self) -> None:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return
        if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("RECOVERY_SESSION_RESTRICTED", "Finish resetting your password before accessing account data."),
            )
            return
        authz_status, authorization = self.current_authorization(user)
        if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify account access. Try again."),
            )
            return
        profile_status, profile = self.fetch_current_profile(user)
        if profile_status != HTTPStatus.OK:
            self.send_json(profile_status, profile)
            return
        session = user.get("_refreshed_session")
        self.send_auth_json(
            HTTPStatus.OK,
            self.account_payload(user, authorization, profile),
            self.session_cookie_headers(session) if session else None,
        )

    def current_authorization(self, user: dict) -> tuple[int, dict]:
        refreshed = user.get("_refreshed_session") or {}
        access_token = refreshed.get("access_token") or self.cookie_value(ACCESS_COOKIE)
        if not access_token:
            return HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue.")
        status, authorization = supabase_rest_request("rpc/current_authorization", access_token)
        if status in {
            HTTPStatus.REQUEST_TIMEOUT,
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
        }:
            return supabase_rest_request("rpc/current_authorization", access_token)
        return status, authorization

    def current_access_token(self, user: dict) -> str:
        refreshed = user.get("_refreshed_session") or {}
        return refreshed.get("access_token") or self.cookie_value(ACCESS_COOKIE)

    def require_account_session(self, *, require_admin_mfa: bool = True) -> tuple[dict | None, dict | None]:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return None, None
        access_token = self.current_access_token(user)
        if session_has_auth_method({"access_token": access_token}, "recovery"):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("RECOVERY_SESSION_RESTRICTED", "Finish resetting your password before opening account settings."),
            )
            return None, None
        authz_status, authorization = self.current_authorization(user)
        if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify account access. Try again."),
            )
            return None, None
        if authorization.get("account_status") != "active":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ACCOUNT_RESTRICTED", "This account cannot change profile or session settings."),
            )
            return None, authorization
        roles = set(authorization.get("roles") or [])
        if require_admin_mfa and roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("MFA_REQUIRED", "Complete multi-factor authentication before changing administrator settings."),
            )
            return None, authorization
        return user, authorization

    def fetch_current_profile(self, user: dict) -> tuple[int, dict]:
        user_id = clean_text(user.get("id"), 64)
        try:
            user_id = clean_uuid(user_id, "user id")
        except ValueError:
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile could not be loaded.")
        query = urlencode({"select": ",".join(PROFILE_FIELDS), "user_id": f"eq.{user_id}", "limit": "1"})
        status, result = supabase_rest_request(
            f"user_profiles?{query}",
            self.current_access_token(user),
            method="GET",
        )
        if status != HTTPStatus.OK or not isinstance(result, list) or len(result) != 1:
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile could not be loaded.")
        profile = result[0]
        profile = clean_profile_result(profile)
        if profile is None:
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile could not be loaded.")
        return HTTPStatus.OK, profile

    def account_payload(self, user: dict, authorization: dict, profile: dict) -> dict:
        email_verified_at = user.get("email_confirmed_at") or user.get("confirmed_at")
        account = {
            "id": user.get("id"),
            "email": user.get("email"),
            "email_verified": bool(email_verified_at),
            "email_verified_at": email_verified_at,
            "account_status": authorization.get("account_status"),
            "roles": authorization.get("roles") or [],
            "aal": authorization.get("aal") or "aal1",
        }
        return {
            "user": {
                "id": account["id"],
                "email": account["email"],
                "display_name": profile.get("display_name"),
            },
            "account": account,
            "profile": profile,
        }

    def handle_profile_get(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, profile = self.fetch_current_profile(user)
        if status != HTTPStatus.OK:
            self.send_json(status, profile)
            return
        self.send_auth_json(HTTPStatus.OK, self.account_payload(user, authorization, profile))

    def handle_profile_update(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        updates, field_errors = normalize_profile_update(body)
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_VALIDATION_FAILED", "Check the highlighted fields.", field_errors),
            )
            return
        if not updates:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_VALIDATION_FAILED", "Choose at least one profile field to update."),
            )
            return
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, result = supabase_rest_request(
            "rpc/update_my_profile",
            self.current_access_token(user),
            {"profile_patch": updates},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_UPDATE_FAILED", "Your profile could not be saved. Try again."),
            )
            return
        profile = clean_profile_result(result)
        if profile is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_UPDATE_FAILED", "Your profile could not be saved. Try again."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, {"profile": profile, "saved": True})

    def handle_profile_cover_get(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, result = supabase_rest_request(
            "rpc/get_my_profile_cover",
            self.current_access_token(user),
            {},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_COVER_PROVIDER_FAILED", "Profile cover options could not be loaded. Try again."),
            )
            return
        clean_result = clean_profile_cover_result(result, include_candidates=True)
        if clean_result is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_COVER_PROVIDER_FAILED", "Profile cover options could not be verified. Try again."),
            )
            return
        response = self.sign_profile_cover_result(user, clean_result, include_candidates=True)
        if response is not None:
            self.send_auth_json(HTTPStatus.OK, response)

    def handle_profile_cover_update(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        asset_id, field_errors = normalize_profile_cover_update(body)
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_COVER_VALIDATION_FAILED", "Choose an available cover image.", field_errors),
            )
            return
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, result = supabase_rest_request(
            "rpc/set_my_profile_cover",
            self.current_access_token(user),
            {"target_asset_id": asset_id},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_COVER_UPDATE_FAILED", "Your profile cover could not be saved. Try again."),
            )
            return
        provider_error = result.get("error")
        if isinstance(provider_error, dict):
            if provider_error.get("code") == "PROFILE_COVER_NOT_AVAILABLE":
                self.send_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    auth_error(
                        "PROFILE_COVER_NOT_AVAILABLE",
                        "Choose one of your current scanner-approved image assets.",
                        {"asset_id": "This image is no longer available as a profile cover."},
                    ),
                )
            else:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("PROFILE_COVER_UPDATE_FAILED", "Your profile cover could not be saved. Try again."),
                )
            return
        clean_result = clean_profile_cover_result(result, include_candidates=False)
        if clean_result is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_COVER_UPDATE_FAILED", "Your saved profile cover could not be verified. Try again."),
            )
            return
        response = self.sign_profile_cover_result(
            user,
            clean_result,
            include_candidates=False,
            send_error=False,
        )
        if response is None:
            # The RPC has already committed. Keep the response truthful when a
            # transient Storage signing failure prevents an immediate preview.
            self.send_auth_json(HTTPStatus.OK, {"cover": None, "saved": True})
            return
        response["saved"] = True
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_sessions_get(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        claims = decode_jwt_payload(self.current_access_token(user))
        session_id = clean_text(claims.get("session_id"), 64)
        try:
            session_id = clean_uuid(session_id, "session id")
        except ValueError:
            session_id = "current"
        methods = [
            clean_text(entry.get("method"), 32)
            for entry in claims.get("amr") or []
            if isinstance(entry, dict) and clean_text(entry.get("method"), 32)
        ]
        session = {
            "id": session_id,
            "current": True,
            **user_agent_summary(self.headers.get("User-Agent", "")),
            "aal": authorization.get("aal") or claims.get("aal") or "aal1",
            "auth_methods": methods,
            "authenticated_at": jwt_timestamp_iso(claims.get("iat")),
            "expires_at": jwt_timestamp_iso(claims.get("exp")),
            "observed_at": now_iso(),
            "approximate_location": None,
        }
        self.send_auth_json(
            HTTPStatus.OK,
            {
                "sessions": [session],
                "scope": "current_only",
                "capabilities": {
                    "list_all": False,
                    "revoke_by_id": False,
                    "sign_out_others": True,
                    "sign_out_all": True,
                },
            },
        )

    def handle_session_revoke(self, target: str) -> None:
        if target not in {"others", "all"}:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("SESSION_TARGET_UNSUPPORTED", "This provider cannot revoke an arbitrary session by identifier."),
            )
            return
        body = self.read_json_body()
        if body is None:
            return
        expected_confirmation = f"sign-out-{target}"
        if body.get("confirmation") != expected_confirmation:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("SESSION_CONFIRMATION_REQUIRED", "Confirm the session action before continuing."),
            )
            return
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, _ = supabase_auth_request(
            f"logout?scope={'global' if target == 'all' else 'others'}",
            {},
            self.current_access_token(user),
            method="POST",
        )
        if status not in {HTTPStatus.OK, HTTPStatus.NO_CONTENT}:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("SESSION_REVOCATION_FAILED", "Sessions could not be revoked. Try again."),
            )
            return
        if target == "others":
            self.send_auth_json(
                HTTPStatus.OK,
                {
                    "revoked": "others",
                    "signed_out": False,
                    "message": "Other devices can no longer refresh their sessions. Short-lived access may remain until it expires.",
                },
            )
            return
        consume_recovery_grant(self.cookie_value(RECOVERY_COOKIE))
        self.send_auth_json(
            HTTPStatus.OK,
            {"revoked": "all", "signed_out": True, "message": "All device sessions have been signed out."},
            [
                *self.clear_session_cookie_headers(),
                self.clear_recovery_cookie_header(),
                self.clear_csrf_cookie_header(),
            ],
        )

    def send_workspace_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "WORKSPACE_REQUEST_FAILED"
        message = clean_text(error.get("message"), 500) or "Unable to complete this Workspace request."
        field_errors = {}
        raw_field_errors = error.get("field_errors")
        if isinstance(raw_field_errors, dict):
            for raw_key, raw_message in raw_field_errors.items():
                key = clean_text(raw_key, 80)
                safe_message = clean_text(raw_message, 300)
                if re.fullmatch(r"[a-z][a-z0-9_]*", key) and safe_message:
                    field_errors[key] = safe_message
        details = None
        if code == "DRAFT_NOT_READY" and isinstance(error.get("details"), dict):
            raw_details = error["details"].get("readiness", error["details"])
            details = clean_workspace_submit_readiness(raw_details)
        self.send_json(
            WORKSPACE_ERROR_STATUS.get(code, HTTPStatus.BAD_REQUEST),
            auth_error(code, message, field_errors or None, details),
        )

    def workspace_rpc(self, name: str, payload: dict | None = None) -> tuple[dict | None, dict | None]:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return None, None
        status, result = supabase_rest_request(
            f"rpc/{name}",
            self.current_access_token(user),
            payload or {},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("WORKSPACE_PROVIDER_FAILED", "Workspace data could not be updated. Try again."),
            )
            return None, None
        if isinstance(result.get("error"), dict):
            self.send_workspace_error(result["error"])
            return None, None
        return user, result

    def send_review_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "REVIEW_REQUEST_FAILED"
        if code not in REVIEW_ERROR_STATUS:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review provider returned an unsupported error."),
            )
            return
        message = clean_text(error.get("message"), 500) or "Unable to complete this review request."
        self.send_json(REVIEW_ERROR_STATUS[code], auth_error(code, message))

    def send_review_provider_error(self, status: int) -> None:
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_auth_json(HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue."))
            return
        if status == HTTPStatus.FORBIDDEN:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error("REVIEW_ACCESS_REVOKED", "Review access is no longer available. Sign in again or contact an administrator."),
            )
            return
        if status in {
            HTTPStatus.REQUEST_TIMEOUT,
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
        }:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_UNAVAILABLE", "Review services are temporarily unavailable. Try again."),
            )
            return
        self.send_auth_json(
            HTTPStatus.BAD_GATEWAY,
            auth_error("REVIEW_PROVIDER_FAILED", "The review provider could not complete this request."),
        )

    def review_rpc(
        self,
        name: str,
        payload: dict | None = None,
        *,
        principal: tuple[dict, dict] | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        if principal is None:
            allowed, user, authorization = self.require_reviewer()
            if not allowed or not user or not authorization:
                return None, None, None
        else:
            user, authorization = principal
        status, result = supabase_rest_request(
            f"rpc/{name}",
            self.current_access_token(user),
            payload or {},
        )
        if status != HTTPStatus.OK:
            self.send_review_provider_error(status)
            return None, None, None
        if not isinstance(result, dict):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review provider response was invalid."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_review_error(result["error"])
            return None, None, None
        return user, authorization, result

    def sign_review_asset(self, user: dict, asset: dict) -> dict | None:
        bucket = asset.get("storage_bucket")
        storage_key = asset.get("storage_key")
        endpoint = f"object/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": 10 * 60},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if status != HTTPStatus.OK or not signed_url:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_ASSET_UNAVAILABLE", "A private review asset could not be loaded. Try again."),
            )
            return None
        safe_asset = {
            key: value
            for key, value in asset.items()
            if key not in {"storage_bucket", "storage_key"}
        }
        safe_asset["signed_url"] = signed_url
        safe_asset["expires_in"] = 10 * 60
        return safe_asset

    def sign_dashboard_asset(self, user: dict, asset: dict) -> dict | None:
        bucket = asset.get("storage_bucket")
        storage_key = asset.get("storage_key")
        try:
            expected_owner = clean_uuid(user.get("id"), "Dashboard asset owner id")
        except ValueError:
            expected_owner = ""
        if not expected_owner or not storage_key.startswith(f"{expected_owner}/"):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("DASHBOARD_ASSET_UNAVAILABLE", "A private Dashboard preview could not be loaded. Try again."),
            )
            return None
        endpoint = f"object/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": 10 * 60},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if status != HTTPStatus.OK or not signed_url:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("DASHBOARD_ASSET_UNAVAILABLE", "A private Dashboard preview could not be loaded. Try again."),
            )
            return None
        return {
            "id": asset["id"],
            "kind": "thumbnail",
            "mime_type": asset["mime_type"],
            "width": asset["width"],
            "height": asset["height"],
            "signed_url": signed_url,
            "expires_in": 10 * 60,
        }

    def sign_profile_cover_asset(
        self,
        user: dict,
        asset: dict,
        *,
        send_error: bool = True,
    ) -> dict | None:
        bucket = asset.get("storage_bucket")
        storage_key = asset.get("storage_key")
        try:
            expected_owner = clean_uuid(user.get("id"), "profile cover owner id")
        except ValueError:
            expected_owner = ""
        key_parts = storage_key.split("/") if isinstance(storage_key, str) else []
        if (
            not expected_owner
            or bucket != PROFILE_COVER_ASSET_BUCKETS.get(asset.get("kind"))
            or not key_parts
            or key_parts[0] != expected_owner
            or any(part in {"", ".", ".."} for part in key_parts)
        ):
            if send_error:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("PROFILE_COVER_ASSET_UNAVAILABLE", "A private profile cover could not be loaded. Try again."),
                )
            return None

        endpoint = f"object/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": 10 * 60},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if status != HTTPStatus.OK or not signed_url:
            if send_error:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("PROFILE_COVER_ASSET_UNAVAILABLE", "A private profile cover could not be loaded. Try again."),
                )
            return None
        return {
            "id": asset["id"],
            "image_id": asset["image_id"],
            "title": asset["title"],
            "kind": asset["kind"],
            "mime_type": asset["mime_type"],
            "width": asset["width"],
            "height": asset["height"],
            "signed_url": signed_url,
            "expires_in": 10 * 60,
        }

    def sign_profile_cover_result(
        self,
        user: dict,
        result: dict,
        *,
        include_candidates: bool,
        send_error: bool = True,
    ) -> dict | None:
        signed_by_id: dict[str, dict] = {}

        def signed_asset(asset: dict | None) -> dict | None:
            if asset is None:
                return None
            asset_id = asset["id"]
            if asset_id not in signed_by_id:
                signed = self.sign_profile_cover_asset(user, asset, send_error=send_error)
                if signed is None:
                    return None
                signed_by_id[asset_id] = signed
            return dict(signed_by_id[asset_id])

        cover = signed_asset(result.get("cover_asset"))
        if result.get("cover_asset") is not None and cover is None:
            return None
        response = {"cover": cover}
        if include_candidates:
            candidates = []
            for candidate in result.get("candidates") or []:
                signed = signed_asset(candidate)
                if signed is None:
                    return None
                candidates.append(signed)
            response["candidates"] = candidates
        return response

    def handle_review_submissions_get(self, parsed) -> None:
        query = parse_qs(parsed.query)
        status_filter = single_query_value(query, "status") or "open"
        assignment_filter = single_query_value(query, "assignment") or "all"
        try:
            page_size = int(single_query_value(query, "limit") or "30")
            page_offset = int(single_query_value(query, "offset") or "0")
        except ValueError:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_FILTER_INVALID", "Review pagination values must be integers."),
            )
            return
        if (
            status_filter not in REVIEW_FILTER_STATUSES
            or assignment_filter not in {"all", "unassigned", "mine"}
            or page_size < 1
            or page_size > 50
            or page_offset < 0
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_FILTER_INVALID", "Choose supported review filters."),
            )
            return
        user, authorization, result = self.review_rpc(
            "review_list_submissions",
            {
                "status_filter": status_filter,
                "assignment_filter": assignment_filter,
                "page_size": page_size,
                "page_offset": page_offset,
            },
        )
        if not user or authorization is None or result is None:
            return
        principal = clean_review_principal(user, authorization)
        response = clean_review_list_result(
            result,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if response is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review queue response was invalid."),
            )
            return
        if any(
            not review_item_matches_filters(item, status_filter, assignment_filter, response["actor"]["id"])
            for item in response["items"]
        ):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review queue filters were inconsistent."),
            )
            return
        expected_has_more = (
            response["pagination"]["offset"] + len(response["items"])
            < response["pagination"]["total"]
        )
        if response["pagination"]["has_more"] != expected_has_more:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review queue pagination was inconsistent."),
            )
            return
        if assignment_filter == "all":
            expected_total = {
                "open": response["counts"]["open"],
                "submitted": response["counts"]["submitted"],
                "in_review": response["counts"]["in_review"],
                "completed": response["counts"]["completed"],
                "all": response["counts"]["open"] + response["counts"]["completed"],
            }.get(status_filter)
            if expected_total is not None and response["pagination"]["total"] != expected_total:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("REVIEW_PROVIDER_FAILED", "The review queue counts were inconsistent."),
                )
                return
        for item in response["items"]:
            thumbnail = item["image"].pop("thumbnail_asset")
            if thumbnail and (
                thumbnail.get("scan_status") != "clean"
                or thumbnail.get("scan_policy_version") != REVIEW_ASSET_SCAN_POLICY_VERSION
            ):
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("REVIEW_PROVIDER_FAILED", "The review queue returned an unsafe preview asset."),
                )
                return
            item["image"]["thumbnail"] = self.sign_review_asset(user, thumbnail) if thumbnail else None
            if thumbnail and item["image"]["thumbnail"] is None:
                return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_review_submission_get(self, submission_id: str) -> None:
        try:
            submission_id = clean_uuid(submission_id, "review submission id")
        except ValueError:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable."),
            )
            return
        user, authorization, result = self.review_rpc("review_get_submission", {"submission_id": submission_id})
        if not user or authorization is None or result is None:
            return
        principal = clean_review_principal(user, authorization)
        response = clean_review_detail_result(
            result,
            submission_id,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if response is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review detail response was invalid."),
            )
            return
        if any(
            asset.get("scan_status") != "clean"
            or asset.get("scan_policy_version") != REVIEW_ASSET_SCAN_POLICY_VERSION
            for asset in response["assets"]
        ):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review detail returned an unsafe private asset."),
            )
            return
        signed_assets = []
        for asset in response["assets"]:
            signed = self.sign_review_asset(user, asset)
            if signed is None:
                return
            signed_assets.append(signed)
        response["assets"] = signed_assets
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_review_assignment(self, submission_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            submission_id = clean_uuid(submission_id, "review submission id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable."))
            return
        expected_version = body.get("expected_version")
        if (
            set(body) != {"confirmation", "expected_version"}
            or body.get("confirmation") != "assign-to-me"
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_VERSION_REQUIRED", "Confirm the current submission version before assigning it."),
            )
            return
        user, authorization, result = self.review_rpc(
            "review_assign_submission",
            {"submission_id": submission_id, "expected_lock_version": expected_version},
        )
        if not user or authorization is None or result is None:
            return
        response = clean_review_mutation_result(result, submission_id)
        principal = clean_review_principal(user, authorization)
        if (
            response is None
            or principal is None
            or response["submission"].get("assigned_reviewer_id") != principal[0]
            or response["submission"].get("status") != "submitted"
        ):
            self.send_json(HTTPStatus.BAD_GATEWAY, auth_error("REVIEW_PROVIDER_FAILED", "The assignment result was invalid."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_review_start(self, submission_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            submission_id = clean_uuid(submission_id, "review submission id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable."))
            return
        expected_version = body.get("expected_version")
        if (
            set(body) != {"confirmation", "expected_version"}
            or body.get("confirmation") != "start-review"
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_VERSION_REQUIRED", "Confirm the current submission version before starting review."),
            )
            return
        user, authorization, result = self.review_rpc(
            "review_start_submission",
            {"submission_id": submission_id, "expected_lock_version": expected_version},
        )
        if not user or authorization is None or result is None:
            return
        response = clean_review_mutation_result(result, submission_id)
        principal = clean_review_principal(user, authorization)
        if (
            response is None
            or principal is None
            or response["submission"].get("assigned_reviewer_id") != principal[0]
            or response["submission"].get("status") != "in_review"
        ):
            self.send_json(HTTPStatus.BAD_GATEWAY, auth_error("REVIEW_PROVIDER_FAILED", "The start-review result was invalid."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_review_decision(self, submission_id: str, action: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        decision = {
            "request-changes": "request_changes",
            "reject": "reject",
            "approve": "approve",
            "approve-and-publish": "approve_and_publish",
        }.get(action)
        try:
            submission_id = clean_uuid(submission_id, "review submission id")
        except ValueError:
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable."),
            )
            return
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "review idempotency key")
        except ValueError:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_IDEMPOTENCY_REQUIRED", "Use a valid decision request identifier."),
            )
            return
        expected_fields = {
            "confirmation",
            "expected_version",
            "idempotency_key",
            "reason_codes",
            "user_message",
            "internal_note",
            "checklist_result",
        }
        expected_version = body.get("expected_version")
        raw_reason_codes = body.get("reason_codes")
        user_message = body.get("user_message")
        internal_note = body.get("internal_note")
        checklist = body.get("checklist_result")
        reason_codes = []
        if isinstance(raw_reason_codes, list):
            reason_codes = [code.strip() for code in raw_reason_codes if isinstance(code, str)]
        valid_checklist = (
            isinstance(checklist, dict)
            and set(checklist) == REVIEW_CHECKLIST_CODES
            and all(value is True for value in checklist.values())
        )
        if (
            decision is None
            or set(body) != expected_fields
            or body.get("confirmation") != f"review-{action}"
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not isinstance(raw_reason_codes, list)
            or not 1 <= len(reason_codes) <= 8
            or len(reason_codes) != len(raw_reason_codes)
            or any(not 2 <= len(code) <= 80 or not REVIEW_REASON_CODE_PATTERN.fullmatch(code) for code in reason_codes)
            or len(set(reason_codes)) != len(reason_codes)
            or any(code not in REVIEW_REASON_CODES.get(decision or "", set()) for code in reason_codes)
            or not isinstance(user_message, str)
            or not 5 <= len(user_message.strip()) <= 1000
            or not isinstance(internal_note, str)
            or len(internal_note.strip()) > 2000
            or not valid_checklist
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("REVIEW_DECISION_INVALID", "Complete the checklist, reason, and decision message."),
            )
            return
        allowed, user, authorization = self.require_reviewer()
        if not allowed or not user or authorization is None:
            return
        roles = set(authorization.get("roles") or [])
        if decision == "approve_and_publish" and not roles.intersection({"admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("REVIEW_PUBLISH_ADMIN_REQUIRED", "Administrator approval is required to publish."),
            )
            return
        _, _, result = self.review_rpc(
            "review_decide_submission",
            {
                "submission_id": submission_id,
                "expected_lock_version": expected_version,
                "decision": decision,
                "reason_codes": reason_codes,
                "user_message": user_message.strip(),
                "internal_note": internal_note.strip(),
                "checklist_result": checklist,
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_review_mutation_result(result, submission_id)
        expected_status = {
            "request_changes": "changes_requested",
            "reject": "rejected",
            "approve": "approved",
            "approve_and_publish": "approved",
        }[decision]
        if (
            response is None
            or not isinstance(response.get("decision"), dict)
            or not isinstance(response.get("image"), dict)
            or response.get("decision", {}).get("decision") != decision
            or response.get("submission", {}).get("status") != expected_status
            or response.get("image", {}).get("workflow_status") != expected_status
            or (
                decision == "approve_and_publish"
                and response.get("image", {}).get("publication_status") != "published"
            )
        ):
            self.send_json(HTTPStatus.BAD_GATEWAY, auth_error("REVIEW_PROVIDER_FAILED", "The review decision result was invalid."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def absolute_storage_url(self, value: str) -> str:
        path = clean_text(value, 4096)
        if path.startswith("/"):
            return f"{SUPABASE_URL}/storage/v1{path}"
        parsed = urlparse(path)
        expected = urlparse(SUPABASE_URL)
        if parsed.scheme == "https" and parsed.netloc == expected.netloc:
            return path
        return ""

    def create_signed_upload_urls(self, user: dict, upload: dict) -> dict | None:
        signed_assets = []
        for asset in upload.get("assets") or []:
            if not isinstance(asset, dict):
                self.send_json(HTTPStatus.BAD_GATEWAY, auth_error("UPLOAD_INTENT_FAILED", "Upload destinations are invalid."))
                return None
            bucket = clean_text(asset.get("storage_bucket"), 80)
            storage_key = clean_text(asset.get("storage_key"), 1024)
            if bucket not in {"image-originals", "image-display", "image-thumbnails"} or not storage_key:
                self.send_json(HTTPStatus.BAD_GATEWAY, auth_error("UPLOAD_INTENT_FAILED", "Upload destinations are invalid."))
                return None
            endpoint = f"object/upload/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
            status, signed = supabase_storage_request(endpoint, self.current_access_token(user), {})
            signed_url = self.absolute_storage_url(signed.get("url", "")) if isinstance(signed, dict) else ""
            if status != HTTPStatus.OK or not signed_url:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("UPLOAD_INTENT_FAILED", "Secure upload destinations could not be created. Try again."),
                )
                return None
            signed_assets.append({**asset, "signed_url": signed_url})
        return {**upload, "assets": signed_assets}

    def remove_workspace_upload_objects(self, user: dict, assets: list) -> bool:
        expected_owner = clean_text(user.get("id"), 64)
        grouped: dict[str, list[str]] = {}
        for asset in assets:
            if not isinstance(asset, dict):
                return False
            bucket = clean_text(asset.get("storage_bucket"), 80)
            storage_key = clean_text(asset.get("storage_key"), 1024)
            if (
                bucket not in {"image-originals", "image-display", "image-thumbnails"}
                or not storage_key.startswith(f"{expected_owner}/")
            ):
                return False
            grouped.setdefault(bucket, []).append(storage_key)

        cleanup_succeeded = True
        for bucket, storage_keys in grouped.items():
            status, _ = supabase_storage_request(
                f"bucket/{quote(bucket, safe='')}/delete",
                self.current_access_token(user),
                {"prefixes": storage_keys},
            )
            if status != HTTPStatus.OK:
                cleanup_succeeded = False
        return cleanup_succeeded

    def handle_dashboard_get(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        status, result = supabase_rest_request(
            "rpc/get_my_dashboard",
            self.current_access_token(user),
            {},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("DASHBOARD_PROVIDER_FAILED", "Dashboard data could not be loaded. Try again."),
            )
            return
        response = clean_dashboard_result(result)
        if response is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("DASHBOARD_PROVIDER_FAILED", "Dashboard data could not be verified. Try again."),
            )
            return

        signed_assets = {}
        for section in ("recent_images", "drafts"):
            for image in response[section]:
                asset = image.pop("thumbnail_asset")
                if asset is None:
                    image["thumbnail"] = None
                    continue
                asset_id = asset["id"]
                if asset_id not in signed_assets:
                    signed_asset = self.sign_dashboard_asset(user, asset)
                    if signed_asset is None:
                        return
                    signed_assets[asset_id] = signed_asset
                image["thumbnail"] = dict(signed_assets[asset_id])
        self.send_auth_json(HTTPStatus.OK, response)

    def sign_workspace_draft(self, user: dict, draft: dict) -> dict | None:
        signed_assets = []
        for asset in draft.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            bucket = clean_text(asset.get("storage_bucket"), 80)
            storage_key = clean_text(asset.get("storage_key"), 1024)
            if bucket not in {"image-originals", "image-display", "image-thumbnails"} or not storage_key:
                continue
            endpoint = f"object/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
            status, signed = supabase_storage_request(
                endpoint,
                self.current_access_token(user),
                {"expiresIn": 10 * 60},
            )
            signed_value = ""
            if isinstance(signed, dict):
                signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
            signed_url = self.absolute_storage_url(signed_value)
            if status != HTTPStatus.OK or not signed_url:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("DRAFT_ASSET_UNAVAILABLE", "Private Draft previews could not be loaded. Try again."),
                )
                return None
            signed_assets.append({**asset, "signed_url": signed_url})
        return {**draft, "assets": signed_assets}

    def handle_workspace_folders_get(self) -> None:
        _, result = self.workspace_rpc("workspace_list_folders")
        if result is not None:
            self.send_auth_json(HTTPStatus.OK, result)

    def handle_workspace_folder_create(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        name, field_errors = normalize_workspace_folder_name(body.get("name"))
        if set(body) - {"name"}:
            field_errors["folder"] = "Only a folder name can be provided."
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("FOLDER_VALIDATION_FAILED", "Check the folder name.", field_errors),
            )
            return
        _, result = self.workspace_rpc("workspace_create_folder", {"folder_name": name})
        if result is not None:
            self.send_auth_json(HTTPStatus.CREATED, result)

    def handle_workspace_folder_rename(self, folder_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            folder_id = clean_uuid(folder_id, "folder id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("FOLDER_NOT_FOUND", "The folder is unavailable."))
            return
        name, field_errors = normalize_workspace_folder_name(body.get("name"))
        if set(body) - {"name"}:
            field_errors["folder"] = "Only a folder name can be provided."
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("FOLDER_VALIDATION_FAILED", "Check the folder name.", field_errors),
            )
            return
        _, result = self.workspace_rpc(
            "workspace_rename_folder",
            {"folder_id": folder_id, "folder_name": name},
        )
        if result is not None:
            self.send_auth_json(HTTPStatus.OK, result)

    def handle_workspace_folder_delete(self, folder_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            folder_id = clean_uuid(folder_id, "folder id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("FOLDER_NOT_FOUND", "The folder is unavailable."))
            return
        policy = clean_text(body.get("non_empty_policy"), 40) or "reject"
        if policy not in {"reject", "move_to_inbox"} or set(body) - {"non_empty_policy"}:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("FOLDER_VALIDATION_FAILED", "Choose how to handle images in this folder."),
            )
            return
        _, result = self.workspace_rpc(
            "workspace_delete_folder",
            {"folder_id": folder_id, "non_empty_policy": policy},
        )
        if result is not None:
            self.send_auth_json(HTTPStatus.OK, result)

    def handle_workspace_folder_restore(self, folder_id: str) -> None:
        try:
            folder_id = clean_uuid(folder_id, "folder id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("FOLDER_NOT_FOUND", "The folder is unavailable."))
            return
        _, result = self.workspace_rpc("workspace_restore_folder", {"folder_id": folder_id})
        if result is not None:
            self.send_auth_json(HTTPStatus.OK, result)

    def handle_workspace_upload_intent_create(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        intent, field_errors = normalize_workspace_upload_intent(body)
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("UPLOAD_INTENT_INVALID", "Check the upload metadata.", field_errors),
            )
            return
        user, result = self.workspace_rpc("workspace_create_upload_intent", {"intent": intent})
        if not user or result is None:
            return
        signed = self.create_signed_upload_urls(user, result)
        if signed is not None:
            self.send_auth_json(HTTPStatus.CREATED, signed)

    def handle_workspace_upload_complete(self, upload_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            upload_id = clean_uuid(upload_id, "upload id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("UPLOAD_INTENT_NOT_FOUND", "The upload intent is unavailable."))
            return
        if set(body) - {"draft"} or not isinstance(body.get("draft", {}), dict):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("DRAFT_VALIDATION_FAILED", "Draft metadata must be an object."),
            )
            return
        draft_patch, field_errors = normalize_workspace_draft_patch(
            body.get("draft", {}),
            allow_empty=True,
            allow_compliance=False,
        )
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("DRAFT_VALIDATION_FAILED", "Check the Draft metadata.", field_errors),
            )
            return
        user, result = self.workspace_rpc(
            "workspace_complete_upload",
            {"upload_id": upload_id, "draft": draft_patch},
        )
        if not user or result is None:
            return
        signed = self.sign_workspace_draft(user, result.get("draft") or {})
        if signed is not None:
            self.send_auth_json(HTTPStatus.CREATED, {"draft": signed})

    def handle_workspace_upload_cancel(self, upload_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            upload_id = clean_uuid(upload_id, "upload id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("UPLOAD_INTENT_NOT_FOUND", "The upload intent is unavailable."))
            return
        if body != {"confirmation": "cancel-upload"}:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("UPLOAD_CANCEL_CONFIRMATION_REQUIRED", "Confirm canceling this upload."),
            )
            return

        user, canceled = self.workspace_rpc("workspace_cancel_upload_intent", {"upload_id": upload_id})
        if not user or canceled is None:
            return
        if canceled.get("cleanup_status") == "complete":
            self.send_auth_json(HTTPStatus.OK, {
                "canceled": True,
                "upload_id": upload_id,
                "cleanup_status": "complete",
            })
            return

        cleanup_succeeded = self.remove_workspace_upload_objects(user, canceled.get("assets") or [])
        finalize_status, finalized = supabase_rest_request(
            "rpc/workspace_finish_upload_cleanup",
            self.current_access_token(user),
            {"upload_id": upload_id, "cleanup_succeeded": cleanup_succeeded},
        )
        finalized_status = finalized.get("cleanup_status") if isinstance(finalized, dict) else None
        cleanup_complete = cleanup_succeeded and finalize_status == HTTPStatus.OK and finalized_status == "complete"
        response = {
            "canceled": True,
            "upload_id": upload_id,
            "cleanup_status": "complete" if cleanup_complete else "failed",
        }
        if not cleanup_complete:
            response["message"] = "Upload canceled, but some temporary objects still require cleanup."
        self.send_auth_json(HTTPStatus.OK if cleanup_complete else HTTPStatus.ACCEPTED, response)

    def handle_workspace_images_get(self, parsed) -> None:
        query = parse_qs(parsed.query, keep_blank_values=True)
        workflow_values = query.get("workflow_status")
        if (
            set(query) - {"workflow_status"}
            or (workflow_values is not None and len(workflow_values) != 1)
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("IMAGE_FILTER_INVALID", "Choose one Draft or Trash image filter."),
            )
            return
        workflow_status = workflow_values[0].strip() if workflow_values is not None else "draft"
        rpc_name = {
            "draft": "workspace_list_drafts",
            "trashed": "workspace_list_trashed_drafts",
        }.get(workflow_status)
        if not rpc_name:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("IMAGE_FILTER_INVALID", "Choose Draft or Trash images."),
            )
            return
        user, result = self.workspace_rpc(rpc_name)
        if not user or result is None:
            return
        signed_images = []
        for draft in result.get("images") or []:
            if not isinstance(draft, dict):
                continue
            signed = self.sign_workspace_draft(user, draft)
            if signed is None:
                return
            signed_images.append(signed)
        self.send_auth_json(HTTPStatus.OK, {"images": signed_images})

    def handle_workspace_submit_readiness(self, image_id: str) -> None:
        try:
            image_id = clean_uuid(image_id, "image id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("DRAFT_NOT_FOUND", "The Draft is unavailable."))
            return
        _, result = self.workspace_rpc("workspace_get_submit_readiness", {"image_id": image_id})
        if result is None:
            return
        readiness = clean_workspace_submit_readiness(result.get("readiness"))
        if readiness is None or readiness["image_id"] != image_id:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("WORKSPACE_PROVIDER_FAILED", "Submission readiness could not be verified. Try again."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, {"readiness": readiness})

    def handle_workspace_draft_submit(self, image_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            image_id = clean_uuid(image_id, "image id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("DRAFT_NOT_FOUND", "The Draft is unavailable."))
            return
        expected_version = body.get("expected_version")
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "idempotency key")
        except ValueError:
            idempotency_key = ""
        if (
            set(body) != {"confirmation", "expected_version", "idempotency_key"}
            or body.get("confirmation") != "submit-for-review"
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not idempotency_key
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "SUBMISSION_CONFIRMATION_REQUIRED",
                    "Confirm the current Draft version before submitting it for review.",
                    {
                        "expected_version": "Use the current positive Draft version.",
                        "idempotency_key": "Use a valid request UUID.",
                    },
                ),
            )
            return
        _, result = self.workspace_rpc(
            "workspace_submit_draft_versioned",
            {
                "image_id": image_id,
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
            },
        )
        if result is None:
            return
        response = clean_workspace_submission_result(result, image_id)
        if response is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("WORKSPACE_PROVIDER_FAILED", "The submission result could not be verified. Try again."),
            )
            return
        self.send_auth_json(HTTPStatus.CREATED, response)

    def handle_workspace_draft_update(self, image_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            image_id = clean_uuid(image_id, "image id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("DRAFT_NOT_FOUND", "The Draft is unavailable."))
            return
        if set(body) != {"draft", "expected_version"} or not isinstance(body.get("draft"), dict):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "DRAFT_VALIDATION_FAILED",
                    "Draft updates require metadata and the version you edited.",
                    {"draft": "Send draft and expected_version only."},
                ),
            )
            return
        expected_version = body.get("expected_version")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "DRAFT_VERSION_REQUIRED",
                    "Reload this Draft before saving changes.",
                    {"expected_version": "Use the current positive Draft version."},
                ),
            )
            return
        patch, field_errors = normalize_workspace_draft_patch(body["draft"])
        if field_errors:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("DRAFT_VALIDATION_FAILED", "Check the Draft metadata.", field_errors),
            )
            return
        user, result = self.workspace_rpc(
            "workspace_update_draft_versioned",
            {"image_id": image_id, "patch": patch, "expected_version": expected_version},
        )
        if not user or result is None:
            return
        draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
        self.send_auth_json(
            HTTPStatus.OK,
            {"draft": {key: value for key, value in draft.items() if key != "assets"}, "saved": True},
        )

    def handle_workspace_draft_trash(self, image_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            image_id = clean_uuid(image_id, "image id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("DRAFT_NOT_FOUND", "The Draft is unavailable."))
            return
        expected_version = body.get("expected_version")
        if (
            set(body) != {"confirmation", "expected_version"}
            or body.get("confirmation") != "move-to-trash"
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "DRAFT_CONFIRMATION_REQUIRED",
                    "Confirm moving the current Draft version to Trash.",
                    {"expected_version": "Reload the Draft before moving it to Trash."},
                ),
            )
            return
        _, result = self.workspace_rpc(
            "workspace_trash_draft_versioned",
            {"image_id": image_id, "expected_version": expected_version},
        )
        if result is not None:
            self.send_auth_json(HTTPStatus.OK, result)

    def handle_workspace_draft_restore(self, image_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            image_id = clean_uuid(image_id, "image id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("DRAFT_NOT_FOUND", "The Draft is unavailable."))
            return
        if body:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("DRAFT_RESTORE_INVALID", "Restore does not accept request fields."),
            )
            return
        user, result = self.workspace_rpc("workspace_restore_draft", {"image_id": image_id})
        if not user or result is None:
            return
        signed = self.sign_workspace_draft(user, result.get("draft") or {})
        if signed is not None:
            self.send_auth_json(HTTPStatus.OK, {"draft": signed})

    def handle_mfa_factors(self) -> None:
        user, _ = self.require_account_session(require_admin_mfa=False)
        if not user:
            return
        all_factors = user.get("factors") or []
        factors = {
            "all": all_factors,
            "totp": [factor for factor in all_factors if factor.get("factor_type") == "totp"],
            "phone": [factor for factor in all_factors if factor.get("factor_type") == "phone"],
        }
        session = user.get("_refreshed_session")
        self.send_auth_json(HTTPStatus.OK, factors, self.session_cookie_headers(session) if session else None)

    def handle_mfa_enroll(self) -> None:
        user, _ = self.require_account_session(require_admin_mfa=False)
        if not user:
            return
        factors = user.get("factors") or []
        totp_factors = [
            factor
            for factor in factors
            if (factor.get("factor_type") or factor.get("type")) == "totp"
        ]
        if any(factor.get("status") == "verified" for factor in totp_factors):
            self.send_json(
                HTTPStatus.CONFLICT,
                auth_error("MFA_ALREADY_ENROLLED", "Use your existing authenticator to continue."),
            )
            return

        if any(factor.get("status") != "unverified" for factor in totp_factors):
            self.send_json(
                HTTPStatus.CONFLICT,
                auth_error("MFA_RESET_FAILED", "The authenticator state could not be verified safely."),
            )
            return

        access_token = self.current_access_token(user)
        for pending_factor in (factor for factor in totp_factors if factor.get("status") == "unverified"):
            try:
                factor_id = clean_uuid(pending_factor.get("id"), "factor id")
            except ValueError:
                self.send_json(
                    HTTPStatus.CONFLICT,
                    auth_error("MFA_RESET_FAILED", "The incomplete authenticator setup could not be reset."),
                )
                return
            reset_status, _ = supabase_auth_request(
                f"factors/{factor_id}",
                access_token=access_token,
                method="DELETE",
            )
            if reset_status not in {HTTPStatus.OK, HTTPStatus.NO_CONTENT, HTTPStatus.NOT_FOUND}:
                self.send_json(
                    HTTPStatus.CONFLICT,
                    auth_error("MFA_RESET_FAILED", "The incomplete authenticator setup could not be reset. Try again."),
                )
                return

        status, factor = supabase_auth_request(
            "factors",
            {"factor_type": "totp", "friendly_name": "MT Presence authenticator"},
            access_token,
        )
        if status not in {HTTPStatus.OK, HTTPStatus.CREATED}:
            self.send_json(HTTPStatus.BAD_REQUEST, auth_error("MFA_ENROLL_FAILED", "Unable to start authenticator setup."))
            return
        self.send_auth_json(HTTPStatus.CREATED, factor)

    def handle_mfa_challenge(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            factor_id = clean_uuid(body.get("factor_id"), "factor id")
        except ValueError as error:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("MFA_VALIDATION_FAILED", str(error)))
            return
        user, _ = self.require_account_session(require_admin_mfa=False)
        if not user:
            return
        status, challenge = supabase_auth_request(
            f"factors/{factor_id}/challenge", {}, self.current_access_token(user)
        )
        if status not in {HTTPStatus.OK, HTTPStatus.CREATED}:
            self.send_json(HTTPStatus.BAD_REQUEST, auth_error("MFA_CHALLENGE_FAILED", "Unable to start MFA verification."))
            return
        self.send_auth_json(HTTPStatus.OK, {"id": challenge.get("id")})

    def handle_mfa_verify(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        code = clean_text(body.get("code"), 6)
        try:
            factor_id = clean_uuid(body.get("factor_id"), "factor id")
            challenge_id = clean_uuid(body.get("challenge_id"), "challenge id")
        except ValueError as error:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("MFA_VALIDATION_FAILED", str(error)))
            return
        if not re.fullmatch(r"\d{6}", code):
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("MFA_VALIDATION_FAILED", "Enter the 6-digit code."))
            return
        user, _ = self.require_account_session(require_admin_mfa=False)
        if not user:
            return
        status, session = supabase_auth_request(
            f"factors/{factor_id}/verify",
            {"challenge_id": challenge_id, "code": code},
            self.current_access_token(user),
        )
        if status != HTTPStatus.OK or not session.get("access_token"):
            self.send_json(HTTPStatus.UNAUTHORIZED, auth_error("MFA_CODE_INVALID", "That code is invalid or expired. Try the current code."))
            return
        self.send_auth_json(
            HTTPStatus.OK,
            {"verified": True, "aal": "aal2"},
            self.session_cookie_headers(session),
        )

    def require_admin(self) -> tuple[bool, dict | None]:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return False, None
        status, authorization = self.current_authorization(user)
        if status != HTTPStatus.OK:
            self.send_json(status, authorization if "error" in authorization else auth_error("AUTHORIZATION_FAILED", "Unable to verify access."))
            return False, None
        if authorization.get("account_status") != "active":
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("ACCOUNT_RESTRICTED", "This account cannot access the Admin Platform."))
            return False, authorization
        roles = set(authorization.get("roles") or [])
        if not roles.intersection({"admin", "super_admin"}):
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("ADMIN_REQUIRED", "You do not have access to the Admin Platform."))
            return False, authorization
        if authorization.get("aal") != "aal2":
            self.send_json(HTTPStatus.FORBIDDEN, auth_error("MFA_REQUIRED", "Complete multi-factor authentication to continue."))
            return False, authorization
        return True, authorization

    def require_reviewer(self) -> tuple[bool, dict | None, dict | None]:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return False, None, None
        access_token = self.current_access_token(user)
        if session_has_auth_method({"access_token": access_token}, "recovery"):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("RECOVERY_SESSION_RESTRICTED", "Finish resetting your password before opening review tools."),
            )
            return False, user, None
        status, authorization = self.current_authorization(user)
        if status != HTTPStatus.OK or not isinstance(authorization, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify review access. Try again."),
            )
            return False, user, None
        if authorization.get("account_status") != "active":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ACCOUNT_RESTRICTED", "This account cannot access review tools."),
            )
            return False, user, authorization
        roles = set(authorization.get("roles") or [])
        if not roles.intersection({"reviewer", "admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("REVIEWER_REQUIRED", "You do not have access to the Review Queue."),
            )
            return False, user, authorization
        if clean_review_principal(user, authorization) is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify review identity. Try again."),
            )
            return False, user, None
        if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("MFA_REQUIRED", "Complete multi-factor authentication to continue."),
            )
            return False, user, authorization
        return True, user, authorization

    def serve_review_page(self, next_path: str = "/admin/reviews") -> None:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                self.send_current_user_error(status, user)
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/sign-in?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/auth/reset-password")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        authz_status, authorization = self.current_authorization(user)
        if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("AUTHORIZATION_FAILED", "Unable to verify review access. Try again."),
            )
            return
        roles = set(authorization.get("roles") or [])
        if authorization.get("account_status") != "active" or not roles.intersection({"reviewer", "admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("REVIEWER_REQUIRED", "You do not have access to the Review Queue."),
            )
            return
        if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/mfa?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.path = "/admin-reviews.html"
        super().do_GET()

    def has_admin_access_silently(self) -> bool:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            return False
        status, authorization = self.current_authorization(user)
        if status != HTTPStatus.OK or authorization.get("account_status") != "active":
            return False
        roles = set(authorization.get("roles") or [])
        return bool(roles.intersection({"admin", "super_admin"})) and authorization.get("aal") == "aal2"

    def read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length."})
            return None
        if length <= 0:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body is required."})
            return None
        if length > 128 * 1024:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Request body is too large."})
            return None
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON."})
            return None
        if not isinstance(body, dict):
            self.send_json(HTTPStatus.BAD_REQUEST, auth_error("JSON_OBJECT_REQUIRED", "Request body must be a JSON object."))
            return None
        return body

    def read_archive_create_body(self) -> tuple[dict, dict[str, dict]] | None:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length."})
                return None
            if length <= 0:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body is required."})
                return None
            if length > MAX_UPLOAD_BYTES:
                self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Upload request is too large."})
                return None

            raw_body = self.rfile.read(length)
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw_body
            )
            metadata = None
            files: dict[str, dict] = {}
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if name == "metadata":
                    try:
                        metadata = json.loads(payload.decode(part.get_content_charset() or "utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Upload metadata must be valid JSON."})
                        return None
                    continue
                if name.startswith("asset:"):
                    asset_id = name.removeprefix("asset:")
                    files[asset_id] = {
                        "filename": filename or asset_id,
                        "content_type": part.get_content_type(),
                        "body": payload,
                    }
            if not isinstance(metadata, dict):
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Upload metadata is required."})
                return None
            return metadata, files

        body = self.read_json_body()
        if body is None:
            return None
        return body, {}

    def handle_archive_images(self, parsed) -> None:
        if not ARCHIVE_DB_PATH.exists():
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "Local archive database is not available.",
                    "hint": "Run python3 scripts/seed_local_archive_db.py first.",
                },
            )
            return

        try:
            filters, params, limit = archive_query_filters(parse_qs(parsed.query))
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        where_clause = " AND ".join(filters) if filters else "1 = 1"
        sql = f"""
            SELECT *
            FROM archive_image_view
            WHERE {where_clause}
            ORDER BY sort_order ASC, uploaded_at DESC
            LIMIT ?
        """

        try:
            with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, [*params, limit]).fetchall()
        except sqlite3.Error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to read local archive database."})
            return

        items = [archive_image_payload(row) for row in rows]
        self.send_json(
            HTTPStatus.OK,
            {
                "items": items,
                "count": len(items),
                "source": "local-sqlite",
            },
        )

    def handle_archive_image_update(self, image_id: str) -> None:
        if not ARCHIVE_DB_PATH.exists():
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "Local archive database is not available.",
                    "hint": "Run python3 scripts/seed_local_archive_db.py first.",
                },
            )
            return

        body = self.read_json_body()
        if body is None:
            return
        try:
            payload = normalize_archive_update_payload(body)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        try:
            with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                existing = connection.execute("SELECT id FROM images WHERE id = ?", (image_id,)).fetchone()
                if not existing:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Archive image not found."})
                    return

                with connection:
                    connection.execute(
                        """
                        UPDATE images
                        SET
                          title = ?,
                          description = ?,
                          curatorial_note = ?,
                          artist_statement = ?,
                          series = ?,
                          captured_at = ?,
                          content_type = ?,
                          display_mode = ?,
                          visibility = ?,
                          sort_order = ?,
                          updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            payload["title"],
                            payload["description"],
                            payload["curatorial_note"],
                            payload["artist_statement"],
                            payload["series"],
                            payload["captured_at"],
                            payload["content_type"],
                            payload["display_mode"],
                            payload["visibility"],
                            payload["sort_order"],
                            payload["updated_at"],
                            image_id,
                        ),
                    )
                    replace_image_tags(connection, image_id, payload["tag_groups"], payload["updated_at"])

                row = connection.execute("SELECT * FROM archive_image_view WHERE id = ?", (image_id,)).fetchone()
        except sqlite3.Error as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to update local archive database."})
            return

        self.send_json(HTTPStatus.OK, {"item": archive_image_payload(row), "source": "local-sqlite"})

    def handle_archive_image_delete(self, image_id: str) -> None:
        if not ARCHIVE_DB_PATH.exists():
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "Local archive database is not available.",
                    "hint": "Run python3 scripts/seed_local_archive_db.py first.",
                },
            )
            return

        try:
            image_id = clean_identifier(image_id, "image id")
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        upload_dir = UPLOAD_ASSET_ROOT / image_id
        try:
            with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                existing = connection.execute("SELECT id, source_type FROM images WHERE id = ?", (image_id,)).fetchone()
                if not existing:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Archive image not found."})
                    return
                if existing["source_type"] != "upload":
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": "Only uploaded image records can be deleted from Upload Studio."})
                    return

                with connection:
                    connection.execute("DELETE FROM images WHERE id = ?", (image_id,))
        except sqlite3.Error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to delete local archive database record."})
            return

        warning = ""
        try:
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
        except OSError:
            warning = "Database record deleted, but local upload files could not be removed."

        payload = {"id": image_id, "deleted": True, "source": "local-sqlite"}
        if warning:
            payload["warning"] = warning
        self.send_json(HTTPStatus.OK, payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        canonical_path = canonical_url_path(self.path)
        if canonical_path == "/admin-reviews.html" and parsed.path != canonical_path:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/reviews")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if canonical_path == "/admin-reviews.js" and parsed.path != canonical_path:
            self.path = "/admin-reviews.js"
            super().do_GET()
            return
        # Route and protect the same normalized path that the static handler
        # will eventually translate. Encoded dotfiles/private directories and
        # encoded legacy upload paths must never fall through as public files.
        parsed = parsed._replace(path=canonical_path, netloc="")
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path in {"/admin/reviews", "/admin/reviews/"}:
            self.serve_review_page()
            return
        if len(parts) == 3 and parts[:2] == ["admin", "reviews"]:
            try:
                submission_id = clean_uuid(parts[2], "review submission id")
            except ValueError:
                self.send_json(
                    HTTPStatus.NOT_FOUND,
                    auth_error("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable."),
                )
                return
            self.serve_review_page(f"/admin/reviews/{submission_id}")
            return
        if parsed.path == "/admin-reviews.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/reviews")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path in {
            "/auth/sign-in",
            "/auth/register",
            "/auth/forgot-password",
            "/auth/reset-password",
            "/auth/verify-email",
        }:
            self.path = "/auth.html"
            super().do_GET()
            return
        if parsed.path == "/auth/mfa":
            status, user = self.current_auth_user()
            if status != HTTPStatus.OK:
                if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                    self.send_current_user_error(status, user)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/auth/sign-in?next=/workspace/images")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.path = "/mfa.html"
            super().do_GET()
            return
        if parsed.path == "/dashboard.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/dashboard")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/upload-studio.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/workspace/images")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/account-settings.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/settings/account")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path in {"/settings/account", "/settings/account/"}:
            status, user = self.current_auth_user()
            if status != HTTPStatus.OK:
                if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                    self.send_current_user_error(status, user)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", f"/auth/sign-in?{urlencode({'next': '/settings/account'})}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/auth/reset-password")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            authz_status, authorization = self.current_authorization(user)
            if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("AUTHORIZATION_FAILED", "Unable to verify account access. Try again."),
                )
                return
            if authorization.get("account_status") != "active":
                self.send_json(
                    HTTPStatus.FORBIDDEN,
                    auth_error("ACCOUNT_RESTRICTED", "This account cannot open account settings."),
                )
                return
            roles = set(authorization.get("roles") or [])
            if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", f"/auth/mfa?{urlencode({'next': '/settings/account'})}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.path = "/account-settings.html"
            super().do_GET()
            return
        if parsed.path in {
            "/dashboard",
            "/dashboard/",
            "/workspace",
            "/workspace/",
            "/workspace/images",
            "/workspace/images/",
        }:
            status, user = self.current_auth_user()
            if status != HTTPStatus.OK:
                if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_GATEWAY}:
                    self.send_current_user_error(status, user)
                    return
                self.send_response(HTTPStatus.SEE_OTHER)
                next_path = "/workspace/images" if parsed.path.startswith("/workspace/images") else "/dashboard"
                self.send_header("Location", f"/auth/sign-in?{urlencode({'next': next_path})}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/auth/reset-password")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            authz_status, authorization = self.current_authorization(user)
            if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("AUTHORIZATION_FAILED", "Unable to verify account access. Try again."),
                )
                return
            if authorization.get("account_status") != "active":
                self.send_json(HTTPStatus.FORBIDDEN, auth_error("ACCOUNT_RESTRICTED", "This account cannot access the Workspace."))
                return
            roles = set(authorization.get("roles") or [])
            if (
                parsed.path in {"/dashboard", "/dashboard/"}
                and roles.intersection({"admin", "super_admin"})
                and authorization.get("aal") != "aal2"
            ):
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", f"/auth/mfa?{urlencode({'next': '/dashboard'})}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if parsed.path in {"/workspace", "/workspace/"}:
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/dashboard")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if parsed.path in {"/dashboard", "/dashboard/"}:
                self.path = "/dashboard.html"
                super().do_GET()
                return
            self.path = "/upload-studio.html"
            super().do_GET()
            return
        if parsed.path == "/api/auth/csrf":
            self.handle_csrf_token()
            return
        if parsed.path == "/api/auth/recovery-status":
            self.handle_auth_recovery_status()
            return
        if parsed.path == "/api/auth/verification-status":
            self.handle_auth_verification_status()
            return
        if parsed.path == "/api/me":
            self.handle_me()
            return
        if parsed.path == "/api/me/profile":
            self.handle_profile_get()
            return
        if parsed.path == "/api/me/profile/cover":
            self.handle_profile_cover_get()
            return
        if parsed.path == "/api/me/sessions":
            self.handle_sessions_get()
            return
        if parsed.path == "/api/dashboard":
            self.handle_dashboard_get()
            return
        if parsed.path == "/api/folders":
            self.handle_workspace_folders_get()
            return
        if parsed.path == "/api/images":
            self.handle_workspace_images_get(parsed)
            return
        if len(parts) == 4 and parts[:2] == ["api", "images"] and parts[3] == "readiness":
            self.handle_workspace_submit_readiness(parts[2])
            return
        if parsed.path == "/api/auth/mfa/factors":
            self.handle_mfa_factors()
            return
        if parsed.path == "/api/admin/review-submissions":
            self.handle_review_submissions_get(parsed)
            return
        if len(parts) == 4 and parts[:3] == ["api", "admin", "review-submissions"]:
            self.handle_review_submission_get(parts[3])
            return
        if parsed.path == "/api/admin/access-check":
            allowed, authorization = self.require_admin()
            if allowed:
                self.send_auth_json(HTTPStatus.OK, {"allowed": True, "authorization": authorization})
            return
        if parsed.path == "/api/archive/images":
            visibility = single_query_value(parse_qs(parsed.query), "visibility").lower()
            if visibility not in {"", "published"}:
                allowed, _ = self.require_admin()
                if not allowed:
                    return
            self.handle_archive_images(parsed)
            return

        if canonical_path == "/assets/uploads" or canonical_path.startswith("/assets/uploads/"):
            asset_path = Path(self.translate_path(parsed.path))
            if parsed.path.endswith("/") or asset_path.is_dir():
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            access = legacy_upload_asset_access(parsed.path)
            is_public_derivative = bool(
                access
                and access[1] == "published"
                and access[0] in {"display", "thumbnail", "square_slice"}
            )
            if not is_public_derivative and not self.has_admin_access_silently():
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            self.path = parsed.path
            super().do_GET()
            return

        if parsed.path.startswith("/api/"):
            if parsed.path.startswith("/api/admin/"):
                allowed, _ = self.require_admin()
                if allowed:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "Admin API endpoint not found."})
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})
            return

        if is_private_static_path(canonical_path):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return

        super().do_GET()

    def handle_archive_image_create(self) -> None:
        if not ARCHIVE_DB_PATH.exists():
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "Local archive database is not available.",
                    "hint": "Run python3 scripts/seed_local_archive_db.py first.",
                },
            )
            return

        create_body = self.read_archive_create_body()
        if create_body is None:
            return
        body, file_parts = create_body

        try:
            image_id = clean_identifier(body.get("id"), "image id")
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        try:
            payload = normalize_archive_update_payload(body)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        # Validate required upload fields
        try:
            original_width = positive_int(body.get("original_width"), "original_width")
            original_height = positive_int(body.get("original_height"), "original_height")
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        ratio_category_code = clean_text(body.get("ratio_category_code"), 32)
        if ratio_category_code not in set(ARCHIVE_RATIO_CODES.values()):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid ratio_category_code."})
            return

        original_filename = clean_text(body.get("original_filename"), 512) or payload["title"]
        timestamp = now_iso()
        try:
            assets = normalize_archive_assets(body.get("assets"), image_id)
            square_slices = normalize_archive_square_slices(body.get("square_slices"), image_id, {asset["id"] for asset in assets})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        try:
            with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")

                # Check if image already exists
                existing = connection.execute("SELECT id FROM images WHERE id = ?", (image_id,)).fetchone()
                if existing:
                    self.send_json(HTTPStatus.CONFLICT, {"error": "Image with this id already exists."})
                    return

                with connection:
                    connection.execute(
                        """
                        INSERT INTO images (
                          id, artist_id, title, slug, description, curatorial_note, artist_statement,
                          series, source_type, visibility, original_filename, original_width, original_height,
                          original_aspect_ratio, ratio_category_code, display_ratio_override,
                          content_type, display_mode, ai_model, ai_confidence, ai_analysis, exif,
                          sort_order, captured_at, uploaded_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            image_id,
                            SEED_ARTIST_ID,
                            payload["title"],
                            slugify(payload["title"], image_id),
                            payload["description"],
                            payload["curatorial_note"],
                            payload["artist_statement"],
                            payload["series"],
                            "upload",
                            payload["visibility"],
                            original_filename,
                            original_width,
                            original_height,
                            original_width / original_height,
                            ratio_category_code,
                            None,
                            payload["content_type"],
                            payload["display_mode"],
                            None,
                            None,
                            "{}",
                            json.dumps(body.get("exif") or {}),
                            payload["sort_order"],
                            payload["captured_at"],
                            timestamp,
                            timestamp,
                            payload["updated_at"],
                        ),
                    )
                    replace_image_tags(connection, image_id, payload["tag_groups"], timestamp)
                    write_upload_assets(connection, image_id, assets, square_slices, file_parts, timestamp)

                row = connection.execute("SELECT * FROM archive_image_view WHERE id = ?", (image_id,)).fetchone()
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except sqlite3.Error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to create image in local archive database."})
            return

        self.send_json(HTTPStatus.CREATED, {"item": archive_image_payload(row), "source": "local-sqlite"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path.startswith("/api/auth/") and not self.require_csrf():
            return
        if parsed.path == "/api/auth/register":
            self.handle_auth_register()
            return
        if parsed.path == "/api/auth/sign-in":
            self.handle_auth_sign_in()
            return
        if parsed.path == "/api/auth/sign-out":
            self.handle_auth_sign_out()
            return
        if parsed.path == "/api/auth/forgot-password":
            self.handle_auth_forgot_password()
            return
        if parsed.path == "/api/auth/recovery-session":
            self.handle_auth_callback_session("recovery")
            return
        if parsed.path == "/api/auth/verify-email":
            self.handle_auth_callback_session("signup")
            return
        if parsed.path == "/api/auth/reset-password":
            self.handle_auth_reset_password()
            return
        if parsed.path == "/api/auth/mfa/enroll":
            self.handle_mfa_enroll()
            return
        if parsed.path == "/api/auth/mfa/challenge":
            self.handle_mfa_challenge()
            return
        if parsed.path == "/api/auth/mfa/verify":
            self.handle_mfa_verify()
            return
        if parsed.path == "/api/folders":
            if not self.require_csrf():
                return
            self.handle_workspace_folder_create()
            return
        if len(parts) == 4 and parts[:2] == ["api", "folders"] and parts[3] == "restore":
            if not self.require_csrf():
                return
            self.handle_workspace_folder_restore(parts[2])
            return
        if parsed.path == "/api/uploads/intents":
            if not self.require_csrf():
                return
            self.handle_workspace_upload_intent_create()
            return
        if len(parts) == 4 and parts[:2] == ["api", "uploads"] and parts[3] == "complete":
            if not self.require_csrf():
                return
            self.handle_workspace_upload_complete(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "images"] and parts[3] == "restore":
            if not self.require_csrf():
                return
            self.handle_workspace_draft_restore(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "images"] and parts[3] == "submit":
            if not self.require_csrf():
                return
            self.handle_workspace_draft_submit(parts[2])
            return
        if len(parts) == 5 and parts[:3] == ["api", "admin", "review-submissions"]:
            if not self.require_csrf():
                return
            submission_id = parts[3]
            action = parts[4]
            if action == "assign":
                self.handle_review_assignment(submission_id)
                return
            if action == "start":
                self.handle_review_start(submission_id)
                return
            if action in {"request-changes", "reject", "approve", "approve-and-publish"}:
                self.handle_review_decision(submission_id, action)
                return
        if parsed.path == "/api/archive/images":
            if not self.require_csrf(require_json=False):
                return
            allowed, _ = self.require_admin()
            if not allowed:
                return
            self.handle_archive_image_create()
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/api/me/profile":
            if not self.require_csrf():
                return
            self.handle_profile_update()
            return
        if parsed.path == "/api/me/profile/cover":
            if not self.require_csrf():
                return
            self.handle_profile_cover_update()
            return
        if len(parts) == 3 and parts[:2] == ["api", "folders"]:
            if not self.require_csrf():
                return
            self.handle_workspace_folder_rename(parts[2])
            return
        if len(parts) == 4 and parts[:2] == ["api", "images"] and parts[3] == "draft":
            if not self.require_csrf():
                return
            self.handle_workspace_draft_update(parts[2])
            return
        if len(parts) == 4 and parts[:3] == ["api", "archive", "images"]:
            if not self.require_csrf():
                return
            allowed, _ = self.require_admin()
            if not allowed:
                return
            self.handle_archive_image_update(parts[3])
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[:3] == ["api", "me", "sessions"]:
            if not self.require_csrf():
                return
            self.handle_session_revoke(parts[3])
            return
        if len(parts) == 3 and parts[:2] == ["api", "folders"]:
            if not self.require_csrf():
                return
            self.handle_workspace_folder_delete(parts[2])
            return
        if len(parts) == 3 and parts[:2] == ["api", "uploads"]:
            if not self.require_csrf():
                return
            self.handle_workspace_upload_cancel(parts[2])
            return
        if len(parts) == 3 and parts[:2] == ["api", "images"]:
            if not self.require_csrf():
                return
            self.handle_workspace_draft_trash(parts[2])
            return
        if len(parts) == 4 and parts[:3] == ["api", "archive", "images"]:
            if not self.require_csrf(require_json=False):
                return
            allowed, _ = self.require_admin()
            if not allowed:
                return
            self.handle_archive_image_delete(parts[3])
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MT Presence local static site.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8131)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = partial(MTRequestHandler, directory=str(ROOT))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    actual_port = server.server_address[1]
    print(f"Serving MT Presence at http://{args.host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
