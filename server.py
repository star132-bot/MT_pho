#!/usr/bin/env python3
"""Local static server for MT Presence."""

from __future__ import annotations

import argparse
import base64
import html
import hmac
import hashlib
import ipaddress
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
from datetime import datetime, timedelta, timezone
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
RUNTIME_ENVIRONMENT = os.environ.get("MT_RUNTIME_ENVIRONMENT", "development").strip().lower()
LOCAL_ARCHIVE_PREVIEW = os.environ.get("MT_LOCAL_ARCHIVE_PREVIEW", "0") == "1"
COOKIE_SECURE = os.environ.get("MT_COOKIE_SECURE", "0") == "1"
PUBLIC_BASE_URL = os.environ.get("MT_PUBLIC_BASE_URL", "").rstrip("/")
TRUST_REVERSE_PROXY = os.environ.get("MT_TRUST_PROXY", "0") == "1"
try:
    MAX_REQUEST_THREADS = int(os.environ.get("MT_MAX_REQUEST_THREADS", "32"))
except ValueError:
    MAX_REQUEST_THREADS = 32
MAX_REQUEST_THREADS = max(4, min(MAX_REQUEST_THREADS, 128))
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
PROFILE_AVATAR_STORAGE_FIELDS = (
    "avatar_storage_bucket",
    "avatar_storage_key",
    "avatar_mime_type",
    "avatar_byte_size",
    "avatar_width",
    "avatar_height",
    "avatar_updated_at",
)
PROFILE_AVATAR_BUCKET = "profile-avatars"
PROFILE_AVATAR_MIME_TYPE = "image/jpeg"
PROFILE_AVATAR_SIZE = 512
PROFILE_AVATAR_MAX_BYTES = 1024 * 1024
PROFILE_AVATAR_SIGNED_URL_TTL = 60 * 60
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
HEADER_IDENTITY_BOOTSTRAP_MARKER = (
    '<template id="mt-header-identity" data-header-identity>'
    '{"authenticated":false,"status":"pending"}</template>'
)
HEADER_IDENTITY_BOOTSTRAP_FALLBACK_MARKER = (
    '<template id="mt-header-identity">'
    '{"authenticated":false,"status":"pending"}</template>'
)
HEADER_IDENTITY_SLOT_MARKER = '<div class="header-identity-slot" data-header-identity-slot></div>'
HEADER_AVATAR_SIGNED_URL_TTL = PROFILE_AVATAR_SIGNED_URL_TTL
HEADER_IDENTITY_PUBLIC_PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/works.html": "works.html",
    "/work.html": "work.html",
    "/about.html": "about.html",
    "/contact.html": "contact.html",
    "/lightbox.html": "lightbox.html",
    "/collections.html": "collections.html",
    "/privacy.html": "privacy.html",
}
PUBLIC_CREATOR_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$")
PUBLIC_DELIVERY_ASSET_KINDS = {"display", "thumbnail"}
PUBLIC_DELIVERY_ASSET_BUCKETS = {
    "display": "image-display",
    "thumbnail": "image-thumbnails",
}
PUBLIC_DELIVERY_SIGNED_URL_TTL = 10 * 60
PUBLIC_DELIVERY_MAX_WORKS = 250
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
    "REVIEW_SELF_PUBLISH_FORBIDDEN": HTTPStatus.FORBIDDEN,
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

ADMIN_WORKS_PUBLICATION_STATUSES = {
    "never_published",
    "published",
    "unpublished",
    "quarantined",
    "archived",
    "deleted",
}
ADMIN_WORKS_FILTER_STATUSES = ADMIN_WORKS_PUBLICATION_STATUSES.union({"all"})
ADMIN_WORKS_SORT_CODES = {"updated_desc", "published_desc", "uploaded_desc", "title_asc"}
ADMIN_WORKS_ACTIONS = {"takedown", "restore"}
ADMIN_WORKS_TAKEDOWN_REASON_CODES = {
    "copyright",
    "privacy",
    "illegal_content",
    "policy_violation",
    "security",
    "user_request",
    "other",
}
ADMIN_WORKS_RESTORE_REASON_CODES = {
    "appeal_upheld",
    "investigation_cleared",
    "administrative_error",
    "other",
}
ADMIN_WORKS_REASON_CODES = ADMIN_WORKS_TAKEDOWN_REASON_CODES.union(ADMIN_WORKS_RESTORE_REASON_CODES)
ADMIN_WORKS_SCAN_POLICY_VERSION = "mt-asset-scan-2026-07-v1"
ADMIN_WORKS_GOVERNANCE_POLICY_VERSION = "mt-admin-governance-2026-07-v1"
ADMIN_WORKS_MAX_PAGE_SIZE = 50
ADMIN_WORKS_ERROR_STATUS = {
    "ADMIN_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_IMAGE_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "ADMIN_IMAGE_VERSION_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_GOVERNANCE_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_GOVERNANCE_STATE_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_GOVERNANCE_RESTORE_BLOCKED": HTTPStatus.CONFLICT,
}

ADMIN_USERS_ACCOUNT_STATUSES = {
    "pending_verification",
    "active",
    "suspended",
    "banned",
    "deletion_requested",
    "deleted",
}
ADMIN_USERS_FILTER_STATUSES = ADMIN_USERS_ACCOUNT_STATUSES.union({"all"})
ADMIN_USERS_ROLE_CODES = {"user", "reviewer", "admin", "super_admin"}
ADMIN_USERS_FILTER_ROLES = ADMIN_USERS_ROLE_CODES.union({"all"})
ADMIN_USERS_MUTABLE_ROLES = {"reviewer", "admin"}
ADMIN_USERS_SORT_CODES = {
    "updated_desc",
    "created_desc",
    "last_login_desc",
    "email_asc",
    "display_name_asc",
}
ADMIN_USERS_ACTIONS = {"suspend", "reactivate", "grant_role", "revoke_role", "revoke_sessions"}
ADMIN_USERS_AUDIT_ACTIONS = {
    "admin.user.suspend",
    "admin.user.reactivate",
    "admin.user.grant_role",
    "admin.user.revoke_role",
    "admin.user.revoke_sessions_requested",
    "admin.user.suspend_failed",
    "admin.user.reactivate_failed",
    "admin.user.grant_role_failed",
    "admin.user.revoke_role_failed",
    "admin.user.revoke_sessions_request_failed",
    "admin.user.governance_failed",
}
ADMIN_USERS_REASON_CODES = {
    "suspend": {"policy_violation", "security_review", "suspected_compromise", "other"},
    "reactivate": {"investigation_cleared", "appeal_upheld", "administrative_error", "other"},
    "grant_role": {"operational_need", "access_review", "staffing_change", "security_review", "other"},
    "revoke_role": {"operational_need", "access_review", "staffing_change", "security_review", "other"},
    "revoke_sessions": {"suspected_compromise", "access_review", "user_request", "other"},
}
ADMIN_USERS_ALL_REASON_CODES = set().union(*ADMIN_USERS_REASON_CODES.values())
ADMIN_USERS_MAX_PAGE_SIZE = 100
ADMIN_USERS_POLICY_VERSION = "mt-admin-user-governance-2026-07-v1"
ADMIN_USERS_ERROR_STATUS = {
    "ADMIN_USER_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_USER_SORT_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_USER_SEARCH_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_USER_PAGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_USER_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "ADMIN_USER_VERSION_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_USER_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "ADMIN_USER_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_USER_STATE_CONFLICT": HTTPStatus.CONFLICT,
    "ADMIN_USER_SELF_ACTION_FORBIDDEN": HTTPStatus.FORBIDDEN,
    "ADMIN_USER_SYSTEM_IDENTITY": HTTPStatus.FORBIDDEN,
    "ADMIN_USER_TARGET_FORBIDDEN": HTTPStatus.FORBIDDEN,
    "ADMIN_USER_ROLE_FORBIDDEN": HTTPStatus.FORBIDDEN,
    "ADMIN_USER_LAST_SUPER_ADMIN": HTTPStatus.CONFLICT,
}

COMMUNICATIONS_MAX_PAGE_SIZE = 100
COMMUNICATIONS_MESSAGE_MAX_PAGE_SIZE = 200
COMMUNICATIONS_CONVERSATION_STATUSES = {"all", "open", "replied", "closed"}
COMMUNICATIONS_INQUIRY_TYPES = {
    "exhibition",
    "editorial",
    "licensing",
    "print",
    "commission",
    "other",
}
COMMUNICATIONS_NOTIFICATION_PAYLOAD_FIELDS = {
    "image_id",
    "asset_id",
    "submission_id",
    "decision_id",
    "governance_action_id",
    "takedown_case_id",
    "user_governance_action_id",
    "conversation_id",
    "message_id",
    "action",
    "decision",
    "reason_code",
    "reason_codes",
    "status",
    "workflow_status",
    "publication_status",
    "account_status",
    "scan_status",
    "result_code",
    "target_role",
    "provider_action_required",
    "inquiry_type",
    "work_count",
    "message",
}
COMMUNICATIONS_ERROR_STATUS = {
    "NOTIFICATION_PAGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "NOTIFICATION_CURSOR_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "NOTIFICATION_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "INQUIRY_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "INQUIRY_WORKS_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "INQUIRY_WORK_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "INQUIRY_RECIPIENT_CONFLICT": HTTPStatus.CONFLICT,
    "INQUIRY_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "INQUIRY_RATE_LIMITED": HTTPStatus.TOO_MANY_REQUESTS,
    "INQUIRY_RECIPIENT_UNAVAILABLE": HTTPStatus.SERVICE_UNAVAILABLE,
    "INQUIRY_SELF_FORBIDDEN": HTTPStatus.FORBIDDEN,
    "INQUIRY_REJECTED": HTTPStatus.BAD_REQUEST,
    "COMMUNICATION_ACCOUNT_RESTRICTED": HTTPStatus.FORBIDDEN,
    "CONVERSATION_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_PAGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_CURSOR_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "CONVERSATION_VERSION_CONFLICT": HTTPStatus.CONFLICT,
    "CONVERSATION_STATE_CONFLICT": HTTPStatus.CONFLICT,
    "CONVERSATION_REPLY_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_MESSAGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
    "CONVERSATION_MESSAGE_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "CONVERSATION_READ_TARGET_INVALID": HTTPStatus.NOT_FOUND,
    "CONVERSATION_STATUS_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "CONVERSATION_STATUS_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
}
ADMIN_AUDIT_ERROR_STATUS = {
    "AUDIT_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_DATE_RANGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_PAGE_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_CURSOR_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_NOT_FOUND": HTTPStatus.NOT_FOUND,
    "AUDIT_EXPORT_LIMIT_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_EXPORT_REASON_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_EXPORT_IDEMPOTENCY_REQUIRED": HTTPStatus.UNPROCESSABLE_ENTITY,
    "AUDIT_EXPORT_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT,
}
INQUIRY_BODY_MAX_BYTES = 16 * 1024
INQUIRY_RATE_WINDOW_SECONDS = 60 * 60
try:
    INQUIRY_EMAIL_RATE_LIMIT = int(os.environ.get("MT_INQUIRY_RATE_LIMIT_PER_HOUR", "5"))
except ValueError:
    INQUIRY_EMAIL_RATE_LIMIT = 5
if not 1 <= INQUIRY_EMAIL_RATE_LIMIT <= 100:
    INQUIRY_EMAIL_RATE_LIMIT = 5
INQUIRY_RATE_LIMITS = {"ip": 10, "email": INQUIRY_EMAIL_RATE_LIMIT}
INQUIRY_RATE_MAX_BUCKETS = 4096
INQUIRY_RATE_SECRET = secrets.token_bytes(32)
INQUIRY_RATE_BUCKETS: dict[str, list[float]] = {}
INQUIRY_RATE_LOCK = threading.Lock()

PUBLIC_ROOT_STATIC_FILES = {
    "index.html", "works.html", "work.html", "about.html", "contact.html", "lightbox.html", "privacy.html",
    "creator.html", "collections.html", "auth.html", "mfa.html", "account-settings.html",
    "dashboard.html", "upload-studio.html", "notifications.html", "inbox.html", "admin-reviews.html",
    "admin-works.html", "admin-users.html", "admin-audit.html", "manage.html",
    "styles.css", "privacy.css", "admin-audit.css",
    "script.js", "global-header.js", "archive.js", "archive-data.js", "archive-upload.js", "public-archive.js",
    "work-detail.js", "about.js",
    "public-navigation.js", "series-data.js", "lightbox.js", "contact.js", "creator.js",
    "collections.js", "auth.js", "mfa.js", "account-menu.js", "account-settings.js",
    "dashboard.js", "upload-studio.js", "notifications.js", "inbox.js", "site-footer.js",
    "admin-reviews.js", "admin-works.js", "admin-users.js", "admin-audit.js", "manage.js",
}
PUBLIC_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


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


def is_public_static_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if any(part.startswith(".") for part in parts):
        return False
    if len(parts) == 1:
        return parts[0] in PUBLIC_ROOT_STATIC_FILES
    if len(parts) >= 3 and parts[:2] in (["assets", "art"], ["assets", "archive"]):
        try:
            candidate = (ROOT / path.lstrip("/")).resolve()
            candidate.relative_to(ROOT)
        except (OSError, ValueError):
            return False
        return not path.endswith("/") and candidate.is_file() and candidate.suffix.lower() in PUBLIC_IMAGE_EXTENSIONS
    return False


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


def clean_iso_timestamp(value, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > 80:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return value


def clean_optional_text(value, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > max_length or any(ord(character) < 32 for character in normalized):
        return None
    return normalized


def valid_email_address(value: str) -> bool:
    return bool(
        3 <= len(value) <= 180
        and value == value.lower()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)
    )


def inquiry_rate_digest(scope: str, value: str) -> str:
    return hmac.new(INQUIRY_RATE_SECRET, f"{scope}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def consume_inquiry_rate_limit(client_ip: str, sender_email: str) -> bool:
    """Consume both anonymous rate buckets without retaining plaintext identifiers."""
    now = time.monotonic()
    cutoff = now - INQUIRY_RATE_WINDOW_SECONDS
    keys = {
        scope: inquiry_rate_digest(scope, value)
        for scope, value in (("ip", client_ip), ("email", sender_email.lower()))
    }
    with INQUIRY_RATE_LOCK:
        for key in list(INQUIRY_RATE_BUCKETS):
            recent = [stamp for stamp in INQUIRY_RATE_BUCKETS[key] if stamp > cutoff]
            if recent:
                INQUIRY_RATE_BUCKETS[key] = recent
            else:
                INQUIRY_RATE_BUCKETS.pop(key, None)
        missing_bucket_count = sum(key not in INQUIRY_RATE_BUCKETS for key in keys.values())
        excess_bucket_count = max(0, len(INQUIRY_RATE_BUCKETS) + missing_bucket_count - INQUIRY_RATE_MAX_BUCKETS)
        if excess_bucket_count:
            oldest = sorted(INQUIRY_RATE_BUCKETS, key=lambda key: INQUIRY_RATE_BUCKETS[key][-1])
            for key in oldest[:excess_bucket_count]:
                INQUIRY_RATE_BUCKETS.pop(key, None)
        if any(len(INQUIRY_RATE_BUCKETS.get(keys[scope], [])) >= limit for scope, limit in INQUIRY_RATE_LIMITS.items()):
            return False
        for key in keys.values():
            INQUIRY_RATE_BUCKETS.setdefault(key, []).append(now)
    return True


def clean_cursor_pagination(value, expected_limit: int, cursor_time_key: str) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"limit", "has_more", "next_cursor"}:
        return None
    limit = value.get("limit")
    has_more = value.get("has_more")
    if isinstance(limit, bool) or limit != expected_limit or not isinstance(has_more, bool):
        return None
    raw_cursor = value.get("next_cursor")
    if not has_more:
        if raw_cursor is not None:
            return None
        return {"limit": limit, "has_more": False, "next_cursor": None}
    if not isinstance(raw_cursor, dict) or set(raw_cursor) != {cursor_time_key, "id"}:
        return None
    timestamp = clean_iso_timestamp(raw_cursor.get(cursor_time_key))
    try:
        cursor_id = clean_uuid(raw_cursor.get("id"), "cursor id")
    except ValueError:
        return None
    if timestamp is None:
        return None
    return {
        "limit": limit,
        "has_more": True,
        "next_cursor": {cursor_time_key: timestamp, "id": cursor_id},
    }


def clean_notification_payload(value) -> dict | None:
    if not isinstance(value, dict) or set(value) - COMMUNICATIONS_NOTIFICATION_PAYLOAD_FIELDS:
        return None
    cleaned = {}
    uuid_fields = {
        "image_id", "asset_id", "submission_id", "decision_id", "governance_action_id",
        "takedown_case_id", "user_governance_action_id", "conversation_id", "message_id",
    }
    text_fields = {
        "action", "decision", "reason_code", "status", "workflow_status", "publication_status",
        "account_status", "scan_status", "result_code", "target_role", "inquiry_type",
    }
    for key, raw_value in value.items():
        if key in uuid_fields:
            try:
                cleaned[key] = clean_uuid(raw_value, f"notification {key}")
            except ValueError:
                return None
        elif key in text_fields:
            if not isinstance(raw_value, str) or not raw_value or len(raw_value) > 120:
                return None
            cleaned[key] = raw_value
        elif key == "reason_codes":
            if not isinstance(raw_value, list) or len(raw_value) > 20:
                return None
            reason_codes = []
            for reason in raw_value:
                if not isinstance(reason, str) or not reason or len(reason) > 80:
                    return None
                reason_codes.append(reason)
            cleaned[key] = reason_codes
        elif key == "provider_action_required":
            if not isinstance(raw_value, bool):
                return None
            cleaned[key] = raw_value
        elif key == "work_count":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
                return None
            cleaned[key] = raw_value
        elif key == "message":
            if not isinstance(raw_value, str) or len(raw_value) > 1000:
                return None
            cleaned[key] = raw_value
    return cleaned


def clean_notification_message(value: str) -> str:
    without_controls = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return without_controls.strip()[:1000]


def notification_presentation(notification_type: str, payload: dict) -> tuple[str, str, str]:
    titles = {
        "image_submitted": "Work submitted",
        "image_review_started": "Review started",
        "image_changes_requested": "Changes requested",
        "image_rejected": "Work not approved",
        "image_approved": "Work approved",
        "image_published": "Work published",
        "asset_scan_blocked": "Asset review required",
        "assets_scan_complete": "Assets ready",
        "image_unpublished_by_admin": "Work unpublished",
        "image_taken_down": "Work taken down",
        "image_restored_by_admin": "Work restored",
        "account_suspended_by_admin": "Account suspended",
        "account_reactivated_by_admin": "Account reactivated",
        "role_granted_by_admin": "Account access updated",
        "role_revoked_by_admin": "Account access updated",
        "admin_session_revocation_requested": "Sessions revoked",
        "project_inquiry_received": "New project inquiry",
        "conversation_reply_received": "New conversation reply",
        "conversation_status_changed": "Conversation status changed",
    }
    messages = {
        "image_submitted": "Your work was recorded for review.",
        "image_review_started": "Review of your work has started.",
        "image_changes_requested": "Your reviewer requested changes.",
        "image_rejected": "Your work was not approved for publication.",
        "image_approved": "Your work passed review.",
        "image_published": "Your work is now public.",
        "asset_scan_blocked": "An uploaded asset requires attention.",
        "assets_scan_complete": "The required asset checks completed.",
        "image_unpublished_by_admin": "An administrator unpublished your work.",
        "image_taken_down": "An administrator removed your work from public view.",
        "image_restored_by_admin": "An administrator restored your work.",
        "account_suspended_by_admin": "Your account access changed.",
        "account_reactivated_by_admin": "Your account access was restored.",
        "role_granted_by_admin": "A role was added to your account.",
        "role_revoked_by_admin": "A role was removed from your account.",
        "admin_session_revocation_requested": "Your active sessions were revoked.",
        "project_inquiry_received": "A visitor recorded a project inquiry.",
        "conversation_reply_received": "A participant recorded a reply.",
        "conversation_status_changed": "The inquiry recipient changed the conversation status.",
    }
    title = titles.get(notification_type, "Account notification")
    message = clean_notification_message(payload.get("message", "")) or messages.get(
        notification_type,
        "There is an update in your account.",
    )
    image_id = payload.get("image_id")
    conversation_id = payload.get("conversation_id")
    if notification_type in {"project_inquiry_received", "conversation_reply_received", "conversation_status_changed"} and conversation_id:
        href = f"/inbox/{quote(conversation_id, safe='')}"
    elif image_id:
        href = f"/workspace/images?{urlencode({'image': image_id})}"
    elif notification_type.startswith(("account_", "role_", "admin_session_")):
        href = "/settings/account"
    else:
        href = "/workspace/notifications"
    return title, message, href


def clean_notification_href(value) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 512:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or canonical_url_path(value) != parsed.path:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.path in {"/settings/account", "/workspace/notifications"} and not parsed.query:
        return parsed.path
    if len(parts) == 2 and parts[0] == "inbox" and not parsed.query:
        try:
            return f"/inbox/{clean_uuid(parts[1], 'notification conversation id')}"
        except ValueError:
            return None
    if parsed.path == "/workspace/images":
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) == {"image"} and len(query["image"]) == 1:
            try:
                image_id = clean_uuid(query["image"][0], "notification image id")
            except ValueError:
                return None
            return f"/workspace/images?{urlencode({'image': image_id})}"
    return None


def clean_notification_item(value, expected_recipient_id: str = "") -> dict | None:
    expected_keys = {"id", "type", "message", "href", "read_at", "created_at"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    try:
        notification_id = clean_uuid(value.get("id"), "notification id")
    except ValueError:
        return None
    notification_type = value.get("type")
    raw_message = value.get("message")
    href = clean_notification_href(value.get("href"))
    read_at = clean_iso_timestamp(value.get("read_at"), nullable=True)
    created_at = clean_iso_timestamp(value.get("created_at"))
    if (
        not isinstance(notification_type, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,119}", notification_type)
        or (raw_message is not None and not isinstance(raw_message, str))
        or (isinstance(raw_message, str) and len(raw_message) > 1000)
        or href is None
        or (value.get("read_at") is not None and read_at is None)
        or created_at is None
    ):
        return None
    title, default_message, _ = notification_presentation(notification_type, {})
    message = clean_notification_message(raw_message) if isinstance(raw_message, str) else ""
    message = message or default_message
    return {
        "id": notification_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "read_at": read_at,
        "created_at": created_at,
        "href": href,
    }


def clean_notification_list_result(value, expected_recipient_id: str, expected_limit: int) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"items", "unread_count", "pagination"}:
        return None
    raw_items = value.get("items")
    unread_count = value.get("unread_count")
    pagination = clean_cursor_pagination(value.get("pagination"), expected_limit, "created_at")
    if (
        not isinstance(raw_items, list)
        or len(raw_items) > expected_limit
        or isinstance(unread_count, bool)
        or not isinstance(unread_count, int)
        or unread_count < 0
        or pagination is None
    ):
        return None
    items = []
    seen = set()
    for raw_item in raw_items:
        item = clean_notification_item(raw_item, expected_recipient_id)
        if item is None or item["id"] in seen:
            return None
        seen.add(item["id"])
        items.append(item)
    return {"items": items, "unread_count": unread_count, "pagination": pagination}


def clean_notification_count_result(value, expected_recipient_id: str) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"unread_count"}:
        return None
    unread_count = value.get("unread_count")
    if isinstance(unread_count, bool) or not isinstance(unread_count, int) or unread_count < 0:
        return None
    return {"unread_count": unread_count}


def clean_notification_read_result(value, expected_recipient_id: str, expected_notification_id: str | None) -> dict | None:
    if not isinstance(value, dict):
        return None
    if expected_notification_id is None:
        expected_keys = {"marked_count", "unread_count", "marked_at"}
        if set(value) != expected_keys:
            return None
    else:
        expected_keys = {"notification", "unread_count"}
        if set(value) != expected_keys:
            return None
    count_result = clean_notification_count_result(
        {"unread_count": value.get("unread_count")},
        expected_recipient_id,
    )
    if count_result is None:
        return None
    if expected_notification_id is not None:
        notification = clean_notification_item(value.get("notification"), expected_recipient_id)
        if notification is None or notification["id"] != expected_notification_id or notification["read_at"] is None:
            return None
        return {"notification": notification, **count_result}
    marked_count = value.get("marked_count")
    marked_at = clean_iso_timestamp(value.get("marked_at"))
    if isinstance(marked_count, bool) or not isinstance(marked_count, int) or marked_count < 0 or marked_at is None:
        return None
    return {"marked_count": marked_count, **count_result, "marked_at": marked_at}


def clean_conversation_message(
    value,
    viewer_role: str = "",
    member_roles: set[str] | None = None,
    force_is_mine: bool = False,
) -> dict | None:
    expected_keys = {
        "id", "sender_kind", "sender_role", "sender_display_name", "body",
        "delivery_status", "created_at",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    try:
        message_id = clean_uuid(value.get("id"), "conversation message id")
    except ValueError:
        return None
    sender_kind = value.get("sender_kind")
    sender_role = value.get("sender_role")
    sender_name = value.get("sender_display_name")
    body = value.get("body")
    delivery_status = value.get("delivery_status")
    created_at = clean_iso_timestamp(value.get("created_at"))
    allowed_member_roles = member_roles or {"sender", "recipient"}
    if (
        sender_kind not in {"guest", "member"}
        or (sender_kind == "guest" and sender_role != "guest")
        or (sender_kind == "member" and sender_role not in allowed_member_roles)
        or not isinstance(sender_name, str)
        or not sender_name.strip()
        or len(sender_name.strip()) > 120
        or not isinstance(body, str)
        or not body.strip()
        or len(body) > 5000
        or delivery_status not in {"recorded", "provider_unavailable"}
        or created_at is None
    ):
        return None
    return {
        "id": message_id,
        "sender_kind": sender_kind,
        "sender_role": sender_role,
        "sender_display_name": sender_name.strip(),
        "body": body,
        "delivery_status": delivery_status,
        "created_at": created_at,
        "is_mine": force_is_mine or bool(viewer_role and sender_role == viewer_role),
    }


def clean_conversation_summary(value, expected_viewer_id: str) -> tuple[dict, dict] | None:
    expected_keys = {
        "id", "participant_role", "public_reference", "status", "version", "inquiry_type",
        "organization", "project_use", "timeline", "budget_range", "sender", "recipient",
        "works", "work_count", "unread_count", "last_message", "last_message_at",
        "created_at", "updated_at",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    try:
        conversation_id = clean_uuid(value.get("id"), "conversation id")
        clean_uuid(expected_viewer_id, "conversation viewer id")
    except ValueError:
        return None
    participant_role = value.get("participant_role")
    reference = value.get("public_reference")
    status = value.get("status")
    version = value.get("version")
    inquiry_type = value.get("inquiry_type")
    project_use = value.get("project_use")
    organization = clean_optional_text(value.get("organization"), 180)
    timeline = clean_optional_text(value.get("timeline"), 120)
    budget_range = clean_optional_text(value.get("budget_range"), 120)
    if (
        participant_role not in {"sender", "recipient"}
        or not isinstance(reference, str)
        or not re.fullmatch(r"INQ-[A-F0-9]{12}", reference)
        or status not in {"open", "replied", "closed"}
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
        or inquiry_type not in COMMUNICATIONS_INQUIRY_TYPES
        or not isinstance(project_use, str)
        or not 5 <= len(project_use.strip()) <= 280
        or (value.get("organization") is not None and organization is None)
        or (value.get("timeline") is not None and timeline is None)
        or (value.get("budget_range") is not None and budget_range is None)
    ):
        return None
    raw_sender = value.get("sender")
    raw_recipient = value.get("recipient")
    if (
        not isinstance(raw_sender, dict)
        or set(raw_sender) != {"kind", "display_name", "email"}
        or not isinstance(raw_recipient, dict)
        or set(raw_recipient) != {"display_name"}
    ):
        return None
    sender_kind = raw_sender.get("kind")
    sender_name = raw_sender.get("display_name")
    sender_email = raw_sender.get("email")
    recipient_name = raw_recipient.get("display_name")
    if (
        sender_kind not in {"guest", "member"}
        or not isinstance(sender_name, str)
        or not sender_name.strip()
        or len(sender_name.strip()) > 120
        or not isinstance(sender_email, str)
        or not valid_email_address(sender_email)
        or not isinstance(recipient_name, str)
        or not recipient_name.strip()
        or len(recipient_name.strip()) > 120
    ):
        return None
    raw_works = value.get("works")
    work_count = value.get("work_count")
    unread_count = value.get("unread_count")
    if (
        not isinstance(raw_works, list)
        or len(raw_works) > 10
        or isinstance(work_count, bool)
        or not isinstance(work_count, int)
        or work_count != len(raw_works)
        or isinstance(unread_count, bool)
        or not isinstance(unread_count, int)
        or unread_count < 0
    ):
        return None
    works = []
    seen_work_ids = set()
    for raw_work in raw_works:
        if not isinstance(raw_work, dict) or set(raw_work) != {"id", "title", "position"}:
            return None
        try:
            work_id = clean_uuid(raw_work.get("id"), "conversation work id")
        except ValueError:
            return None
        title = raw_work.get("title")
        position = raw_work.get("position")
        if (
            work_id in seen_work_ids
            or not isinstance(title, str)
            or not title.strip()
            or len(title.strip()) > 512
            or isinstance(position, bool)
            or not isinstance(position, int)
            or not 1 <= position <= 10
        ):
            return None
        seen_work_ids.add(work_id)
        works.append({"id": work_id, "title": title.strip(), "position": position})
    participant_roles = {"recipient"}
    if sender_kind == "member":
        participant_roles.add("sender")
    last_message = clean_conversation_message(
        value.get("last_message"), participant_role, participant_roles
    )
    last_message_at = clean_iso_timestamp(value.get("last_message_at"))
    created_at = clean_iso_timestamp(value.get("created_at"))
    updated_at = clean_iso_timestamp(value.get("updated_at"))
    if last_message is None or last_message_at is None or created_at is None or updated_at is None:
        return None
    response = {
        "id": conversation_id,
        "reference": reference,
        "participant_role": participant_role,
        "status": status,
        "version": version,
        "inquiry_type": inquiry_type,
        "organization": organization,
        "project_use": project_use.strip(),
        "timeline": timeline,
        "budget_range": budget_range,
        "sender": {"kind": sender_kind, "display_name": sender_name.strip()},
        "recipient": {"display_name": recipient_name.strip()},
        "works": works,
        "work_count": work_count,
        "unread_count": unread_count,
        "last_message": last_message,
        "last_message_at": last_message_at,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    metadata = {
        "conversation_id": conversation_id,
        "participant_role": participant_role,
        "participant_roles": participant_roles,
    }
    return response, metadata


def clean_conversation_list_result(value, expected_viewer_id: str, expected_limit: int) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"items", "pagination"}:
        return None
    try:
        clean_uuid(expected_viewer_id, "conversation viewer id")
    except ValueError:
        return None
    raw_items = value.get("items")
    pagination = clean_cursor_pagination(value.get("pagination"), expected_limit, "last_message_at")
    if not isinstance(raw_items, list) or len(raw_items) > expected_limit or pagination is None:
        return None
    items = []
    seen = set()
    for raw_item in raw_items:
        cleaned = clean_conversation_summary(raw_item, expected_viewer_id)
        if cleaned is None or cleaned[0]["id"] in seen:
            return None
        seen.add(cleaned[0]["id"])
        items.append(cleaned[0])
    return {"items": items, "pagination": pagination}


def clean_conversation_detail_result(value, expected_viewer_id: str, expected_conversation_id: str, expected_limit: int) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"conversation", "participants", "messages", "pagination"}:
        return None
    try:
        clean_uuid(expected_viewer_id, "conversation viewer id")
    except ValueError:
        return None
    cleaned_summary = clean_conversation_summary(value.get("conversation"), expected_viewer_id)
    pagination = clean_cursor_pagination(value.get("pagination"), expected_limit, "created_at")
    if cleaned_summary is None or pagination is None:
        return None
    conversation, metadata = cleaned_summary
    if conversation["id"] != expected_conversation_id:
        return None
    raw_participants = value.get("participants")
    if not isinstance(raw_participants, list) or not 1 <= len(raw_participants) <= 2:
        return None
    participants = []
    participant_roles = set()
    for raw_participant in raw_participants:
        expected_keys = {
            "participant_role", "display_name", "email", "last_read_message_id",
            "last_read_at", "joined_at",
        }
        if not isinstance(raw_participant, dict) or set(raw_participant) != expected_keys:
            return None
        role = raw_participant.get("participant_role")
        display_name = raw_participant.get("display_name")
        email = raw_participant.get("email")
        last_read_message_id = None
        if raw_participant.get("last_read_message_id") is not None:
            try:
                last_read_message_id = clean_uuid(raw_participant.get("last_read_message_id"), "last read message id")
            except ValueError:
                return None
        last_read_at = clean_iso_timestamp(raw_participant.get("last_read_at"), nullable=True)
        joined_at = clean_iso_timestamp(raw_participant.get("joined_at"))
        if (
            role not in metadata["participant_roles"]
            or role in participant_roles
            or not isinstance(display_name, str)
            or not display_name.strip()
            or len(display_name.strip()) > 120
            or not isinstance(email, str)
            or not valid_email_address(email)
            or (raw_participant.get("last_read_at") is not None and last_read_at is None)
            or joined_at is None
        ):
            return None
        participant_roles.add(role)
        participants.append({
            "participant_role": role,
            "display_name": display_name.strip(),
            "email": email,
            "last_read_message_id": last_read_message_id,
            "last_read_at": last_read_at,
            "joined_at": joined_at,
        })
    if participant_roles != metadata["participant_roles"]:
        return None
    raw_messages = value.get("messages")
    if not isinstance(raw_messages, list) or len(raw_messages) > expected_limit:
        return None
    messages = []
    message_ids = set()
    for raw_message in raw_messages:
        message = clean_conversation_message(
            raw_message, metadata["participant_role"], metadata["participant_roles"]
        )
        if message is None or message["id"] in message_ids:
            return None
        message_ids.add(message["id"])
        messages.append(message)
    return {
        "conversation": conversation,
        "participants": participants,
        "messages": messages,
        "permissions": {"can_manage": conversation["participant_role"] == "recipient"},
        "pagination": pagination,
    }


def clean_delivery_state(value) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"record_status", "provider_status", "provider_action_required"}:
        return None
    if (
        value.get("record_status") != "recorded"
        or value.get("provider_status") not in {"unavailable", "available", "not_required"}
        or not isinstance(value.get("provider_action_required"), bool)
    ):
        return None
    return {
        "record_status": value["record_status"],
        "provider_status": value["provider_status"],
        "provider_action_required": value["provider_action_required"],
    }


def clean_conversation_reply_result(value, expected_viewer_id: str, expected_conversation_id: str, expected_version: int) -> dict | None:
    expected_keys = {
        "conversation_id", "message", "conversation_version", "status", "delivery", "replayed",
    }
    if not isinstance(value, dict) or set(value) != expected_keys or not isinstance(value.get("replayed"), bool):
        return None
    try:
        clean_uuid(expected_viewer_id, "reply viewer id")
        conversation_id = clean_uuid(value.get("conversation_id"), "reply conversation id")
    except ValueError:
        return None
    message = clean_conversation_message(value.get("message"), force_is_mine=True)
    delivery = clean_delivery_state(value.get("delivery"))
    result_version = value.get("conversation_version")
    status = value.get("status")
    if (
        conversation_id != expected_conversation_id
        or message is None
        or message.get("sender_kind") != "member"
        or isinstance(result_version, bool)
        or result_version != expected_version + 1
        or status not in {"open", "replied", "closed"}
        or delivery is None
    ):
        return None
    return {
        "conversation_id": conversation_id,
        "message": message,
        "conversation_version": result_version,
        "status": status,
        "delivery": delivery,
        "replayed": value["replayed"],
    }


def clean_conversation_read_result(value, expected_viewer_id: str, expected_conversation_id: str) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"conversation_id", "last_read_message_id", "last_read_at", "unread_count"}:
        return None
    try:
        clean_uuid(expected_viewer_id, "read viewer id")
        conversation_id = clean_uuid(value.get("conversation_id"), "read conversation id")
        message_id = clean_uuid(value.get("last_read_message_id"), "last read message id")
    except ValueError:
        return None
    last_read_at = clean_iso_timestamp(value.get("last_read_at"))
    unread_count = value.get("unread_count")
    if (
        conversation_id != expected_conversation_id
        or last_read_at is None
        or isinstance(unread_count, bool)
        or not isinstance(unread_count, int)
        or unread_count < 0
    ):
        return None
    return {"conversation_id": conversation_id, "last_read_message_id": message_id, "last_read_at": last_read_at, "unread_count": unread_count}


def clean_conversation_status_result(
    value,
    expected_conversation_id: str,
    expected_status: str,
    expected_version: int,
) -> dict | None:
    expected_keys = {"conversation_id", "status", "conversation_version", "delivery", "replayed"}
    if not isinstance(value, dict) or set(value) != expected_keys or not isinstance(value.get("replayed"), bool):
        return None
    try:
        conversation_id = clean_uuid(value.get("conversation_id"), "status conversation id")
    except ValueError:
        return None
    conversation_version = value.get("conversation_version")
    delivery = clean_delivery_state(value.get("delivery"))
    if (
        conversation_id != expected_conversation_id
        or value.get("status") != expected_status
        or isinstance(conversation_version, bool)
        or conversation_version != expected_version + 1
        or delivery is None
    ):
        return None
    return {
        "conversation_id": conversation_id,
        "status": expected_status,
        "conversation_version": conversation_version,
        "delivery": delivery,
        "replayed": value["replayed"],
    }


def clean_project_inquiry_result(value, expected_initiator_id: str | None) -> dict | None:
    expected_keys = {"reference", "status", "created_at", "replayed", "selected_work_count"}
    if expected_initiator_id is not None:
        expected_keys.add("conversation_id")
    if not isinstance(value, dict) or set(value) != expected_keys or not isinstance(value.get("replayed"), bool):
        return None
    reference = value.get("reference")
    selected_count = value.get("selected_work_count")
    created_at = clean_iso_timestamp(value.get("created_at"))
    if (
        not isinstance(reference, str)
        or not re.fullmatch(r"INQ-[A-F0-9]{12}", reference)
        or value.get("status") != "received"
        or created_at is None
        or isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or not 0 <= selected_count <= 10
    ):
        return None
    response = {
        "reference": reference,
        "status": "received",
        "created_at": created_at,
        "replayed": value["replayed"],
        "selected_work_count": selected_count,
    }
    if expected_initiator_id is not None:
        try:
            response["conversation_id"] = clean_uuid(value.get("conversation_id"), "inquiry conversation id")
        except ValueError:
            return None
    return response


def clean_admin_audit_actor(value, expected_actor_id: str, expected_roles: set[str]) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"id", "roles"}:
        return None
    try:
        actor_id = clean_uuid(value.get("id"), "audit actor id")
    except ValueError:
        return None
    roles = value.get("roles")
    if (
        actor_id != expected_actor_id
        or not isinstance(roles, list)
        or not roles
        or any(role not in ADMIN_USERS_ROLE_CODES for role in roles)
        or set(roles) != expected_roles
        or not expected_roles.intersection({"admin", "super_admin"})
    ):
        return None
    return {"id": actor_id, "roles": sorted(expected_roles)}


def clean_admin_audit_summary(value) -> dict | None:
    expected_keys = {
        "id", "target_type", "target_id", "actor", "action",
        "request_id", "reason_code", "result", "policy_version", "created_at",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return None
    try:
        audit_id = clean_uuid(value.get("id"), "audit id")
    except ValueError:
        return None
    raw_actor = value.get("actor")
    if not isinstance(raw_actor, dict) or set(raw_actor) != {"id", "display_name", "role"}:
        return None
    event_actor_id = None
    if raw_actor.get("id") is not None:
        try:
            event_actor_id = clean_uuid(raw_actor.get("id"), "audit event actor id")
        except ValueError:
            return None
    target_type = value.get("target_type")
    target_id = value.get("target_id")
    actor_display_name = raw_actor.get("display_name")
    actor_role = raw_actor.get("role")
    action = value.get("action")
    request_id = value.get("request_id")
    reason_code = value.get("reason_code")
    result = value.get("result")
    policy_version = value.get("policy_version")
    created_at = clean_iso_timestamp(value.get("created_at"))
    if (
        not isinstance(target_type, str)
        or not re.fullmatch(r"[a-z0-9_]{1,64}", target_type)
        or not isinstance(target_id, str)
        or not target_id
        or len(target_id) > 200
        or not isinstance(actor_display_name, str)
        or not actor_display_name.strip()
        or len(actor_display_name.strip()) > 120
        or (actor_role is not None and actor_role not in ADMIN_USERS_ROLE_CODES)
        or not isinstance(action, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,119}", action)
        or not isinstance(request_id, str)
        or not request_id
        or len(request_id) > 200
        or (reason_code is not None and (not isinstance(reason_code, str) or not reason_code or len(reason_code) > 120))
        or result not in {"success", "failure"}
        or (policy_version is not None and (not isinstance(policy_version, str) or not policy_version or len(policy_version) > 160))
        or created_at is None
    ):
        return None
    return {
        "id": audit_id,
        "target_type": target_type,
        "target_id": target_id,
        "actor": {"id": event_actor_id, "display_name": actor_display_name.strip(), "role": actor_role},
        "action": action,
        "request_id": request_id,
        "reason_code": reason_code,
        "result": result,
        "policy_version": policy_version,
        "created_at": created_at,
    }


def clean_admin_audit_list_result(value, expected_actor_id: str, expected_roles: set[str], expected_limit: int) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"actor", "items", "pagination"}:
        return None
    actor = clean_admin_audit_actor(value.get("actor"), expected_actor_id, expected_roles)
    raw_items = value.get("items")
    pagination = clean_cursor_pagination(value.get("pagination"), expected_limit, "created_at")
    if actor is None or not isinstance(raw_items, list) or len(raw_items) > expected_limit or pagination is None:
        return None
    items = []
    seen = set()
    for raw_item in raw_items:
        item = clean_admin_audit_summary(raw_item)
        if item is None or item["id"] in seen:
            return None
        seen.add(item["id"])
        items.append(item)
    return {"items": items, "pagination": pagination}


ADMIN_AUDIT_SAFE_STATE_FIELDS = {
    "status", "workflow_status", "publication_status", "processing_status", "submission_status",
    "account_status", "version", "image_version", "user_version", "action", "decision",
    "reason_code", "error_code", "target_role", "provider_action_required",
}


def clean_admin_audit_state(value) -> dict | None:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - ADMIN_AUDIT_SAFE_STATE_FIELDS:
        return None
    cleaned = {}
    for key, raw_value in value.items():
        if key in {"version", "image_version", "user_version"}:
            if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
                return None
        elif key == "provider_action_required":
            if not isinstance(raw_value, bool):
                return None
        elif raw_value is not None and (not isinstance(raw_value, str) or len(raw_value) > 160):
            return None
        cleaned[key] = raw_value
    return cleaned


def clean_admin_audit_detail_result(value, expected_actor_id: str, expected_roles: set[str], expected_audit_id: str) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"actor", "audit"}:
        return None
    actor = clean_admin_audit_actor(value.get("actor"), expected_actor_id, expected_roles)
    raw_audit = value.get("audit")
    if actor is None or not isinstance(raw_audit, dict) or set(raw_audit) != {
        "id", "target_type", "target_id", "actor", "action", "request_id",
        "reason_code", "result", "policy_version", "created_at", "changes",
    }:
        return None
    summary = clean_admin_audit_summary({key: raw_audit.get(key) for key in raw_audit if key != "changes"})
    raw_changes = raw_audit.get("changes")
    if summary is None or summary["id"] != expected_audit_id or not isinstance(raw_changes, dict) or set(raw_changes) != {"before", "after", "changed_fields"}:
        return None
    before = clean_admin_audit_state(raw_changes.get("before"))
    after = clean_admin_audit_state(raw_changes.get("after"))
    changed_fields = raw_changes.get("changed_fields")
    if before is None or after is None or not isinstance(changed_fields, list) or len(changed_fields) > len(ADMIN_AUDIT_SAFE_STATE_FIELDS):
        return None
    if any(not isinstance(field, str) or field not in ADMIN_AUDIT_SAFE_STATE_FIELDS for field in changed_fields):
        return None
    summary["changes"] = {"before": before, "after": after, "changed_fields": changed_fields}
    return {"audit": summary}


def clean_admin_audit_export_result(
    value,
    expected_actor_id: str,
    expected_roles: set[str],
    expected_reason_code: str,
) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"actor", "export", "items", "count", "truncated", "replayed"}:
        return None
    actor = clean_admin_audit_actor(value.get("actor"), expected_actor_id, expected_roles)
    raw_export = value.get("export")
    raw_items = value.get("items")
    count = value.get("count")
    truncated = value.get("truncated")
    if (
        actor is None
        or not isinstance(raw_export, dict)
        or set(raw_export) != {"id", "reason_code", "created_at", "replayed"}
        or not isinstance(raw_export.get("replayed"), bool)
        or not isinstance(value.get("replayed"), bool)
        or raw_export.get("reason_code") != expected_reason_code
        or clean_iso_timestamp(raw_export.get("created_at")) is None
        or not isinstance(raw_items, list)
        or len(raw_items) > 1000
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count != len(raw_items)
        or not isinstance(truncated, bool)
    ):
        return None
    try:
        clean_uuid(raw_export.get("id"), "audit export id")
    except ValueError:
        return None
    items = []
    seen = set()
    for raw_item in raw_items:
        item = clean_admin_audit_summary(raw_item)
        if item is None or item["id"] in seen:
            return None
        seen.add(item["id"])
        items.append(item)
    return {
        "items": items,
        "count": count,
        "truncated": truncated,
        "replayed": value["replayed"],
    }


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


def clean_public_delivery_asset(
    value,
    *,
    expected_image_id: str,
    expected_kind: str | None = None,
) -> dict | None:
    """Validate an anonymous derivative descriptor before Storage signing."""
    if not isinstance(value, dict):
        return None
    try:
        asset_id = clean_uuid(value.get("id"), "public asset id")
        image_id = clean_uuid(value.get("image_id"), "public asset image id")
    except ValueError:
        return None
    kind = clean_text(value.get("kind"), 32)
    bucket = clean_text(value.get("storage_bucket"), 80)
    storage_key = clean_text(value.get("storage_key"), 1024)
    mime_type = clean_text(value.get("mime_type"), 120).lower()
    width = value.get("width")
    height = value.get("height")
    key_parts = storage_key.split("/")
    if (
        image_id != expected_image_id
        or kind not in PUBLIC_DELIVERY_ASSET_KINDS
        or (expected_kind is not None and kind != expected_kind)
        or bucket != PUBLIC_DELIVERY_ASSET_BUCKETS.get(kind)
        or mime_type not in WORKSPACE_IMAGE_MIME_TYPES
        or len(key_parts) != 3
        or key_parts[1] != image_id
        or not re.fullmatch(rf"{re.escape(kind)}\.(?:jpg|jpeg|png|webp)", key_parts[2], re.IGNORECASE)
        or "\\" in storage_key
        or any(part in {"", ".", ".."} for part in key_parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in storage_key)
        or any(
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension < 1
            or dimension > 100_000
            for dimension in (width, height)
        )
    ):
        return None
    try:
        owner_prefix = clean_uuid(key_parts[0], "public asset owner prefix")
    except ValueError:
        return None
    return {
        "id": asset_id,
        "image_id": image_id,
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": storage_key,
        "mime_type": mime_type,
        "width": width,
        "height": height,
        "owner_prefix": owner_prefix,
    }


def clean_public_creator_summary(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    slug = clean_text(value.get("slug"), 96).lower()
    display_name = clean_text(value.get("display_name"), 120)
    if not PUBLIC_CREATOR_SLUG_PATTERN.fullmatch(slug) or not display_name:
        return None
    return {
        "slug": slug,
        "display_name": display_name,
        "href": f"/creators/{quote(slug, safe='')}",
    }


def clean_public_exif(value) -> dict | None:
    if not isinstance(value, dict) or len(value) > 6:
        return None
    result = {}
    for key in ("camera", "lens", "exposure", "aperture", "iso", "focal_length"):
        raw_value = value.get(key)
        if raw_value is None:
            continue
        if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
            return None
        normalized = clean_text(raw_value, 160)
        if normalized:
            result[key] = normalized
    return result


def clean_public_work(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        image_id = clean_uuid(value.get("id"), "public work id")
    except ValueError:
        return None
    title = clean_text(value.get("title"), 180) or "Untitled Work"
    published_at = clean_text(value.get("published_at"), 80)
    category = clean_text(value.get("content_category"), 80)
    ratio_code = clean_text(value.get("ratio_code"), 40)
    ratio_label = clean_text(value.get("ratio_label"), 40)
    width = value.get("width")
    height = value.get("height")
    creator = clean_public_creator_summary(value.get("creator"))
    raw_tags = value.get("tags")
    public_exif = clean_public_exif(value.get("public_exif"))
    if (
        not published_at
        or category not in ARCHIVE_CONTENT_TYPES
        or ratio_code not in set(ARCHIVE_RATIO_CODES.values())
        or not ratio_label
        or creator is None
        or not isinstance(raw_tags, list)
        or len(raw_tags) > 40
        or public_exif is None
        or any(
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension < 1
            or dimension > 100_000
            for dimension in (width, height)
        )
    ):
        return None
    tags = []
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str):
            return None
        tag = clean_text(raw_tag, 80)
        if not tag or len(raw_tag.strip()) > 80:
            return None
        tags.append(tag)
    display_asset = clean_public_delivery_asset(
        value.get("display_asset"),
        expected_image_id=image_id,
        expected_kind="display",
    )
    thumbnail_asset = clean_public_delivery_asset(
        value.get("thumbnail_asset"),
        expected_image_id=image_id,
        expected_kind="thumbnail",
    )
    if (
        display_asset is None
        or thumbnail_asset is None
        or display_asset["owner_prefix"] != thumbnail_asset["owner_prefix"]
    ):
        return None
    return {
        "id": image_id,
        "title": title,
        "caption": clean_text(value.get("caption"), 500) or None,
        "description": clean_text(value.get("description"), 6000) or None,
        "alt_text": clean_text(value.get("alt_text"), 500) or title,
        "tags": tags,
        "content_category": category,
        "captured_at": clean_text(value.get("captured_at"), 80) or None,
        "location_name": clean_text(value.get("location_name"), 240) or None,
        "public_exif": public_exif,
        "published_at": published_at,
        "width": width,
        "height": height,
        "ratio_code": ratio_code,
        "ratio_label": ratio_label,
        "creator": creator,
        "display_asset": display_asset,
        "thumbnail_asset": thumbnail_asset,
        "owner_prefix": display_asset["owner_prefix"],
    }


def clean_public_works_result(value, *, maximum: int = 100) -> dict | None:
    if not isinstance(value, dict):
        return None
    raw_items = value.get("items")
    count = value.get("count")
    if (
        not isinstance(raw_items, list)
        or len(raw_items) > maximum
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < len(raw_items)
    ):
        return None
    items = []
    seen_ids = set()
    for raw_item in raw_items:
        item = clean_public_work(raw_item)
        if item is None or item["id"] in seen_ids:
            return None
        seen_ids.add(item["id"])
        items.append(item)
    return {"items": items, "count": count}


def clean_public_creator(value, expected_slug: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    summary = clean_public_creator_summary(value)
    if summary is None or summary["slug"] != expected_slug:
        return None
    work_count = value.get("work_count")
    raw_works = value.get("works")
    if (
        isinstance(work_count, bool)
        or not isinstance(work_count, int)
        or work_count < 1
        or not isinstance(raw_works, list)
        or not 1 <= len(raw_works) <= 100
        or work_count < len(raw_works)
    ):
        return None
    works = []
    owner_prefix = ""
    for raw_work in raw_works:
        work = clean_public_work(raw_work)
        if work is None or work["creator"]["slug"] != expected_slug:
            return None
        if owner_prefix and work["owner_prefix"] != owner_prefix:
            return None
        owner_prefix = work["owner_prefix"]
        works.append(work)
    cover = None
    if value.get("cover_asset") is not None:
        raw_cover = value.get("cover_asset")
        try:
            cover_image_id = clean_uuid(
                raw_cover.get("image_id") if isinstance(raw_cover, dict) else None,
                "public creator cover image id",
            )
        except ValueError:
            return None
        cover = clean_public_delivery_asset(raw_cover, expected_image_id=cover_image_id)
        if cover is None or cover["owner_prefix"] != owner_prefix:
            return None

    creator = {**summary, "work_count": work_count, "works": works, "cover_asset": cover}
    for field, maximum in (
        ("professional_headline", 160),
        ("company", 160),
        ("city", 120),
        ("bio", 1600),
    ):
        raw_value = value.get(field)
        if raw_value is not None and not isinstance(raw_value, str):
            return None
        creator[field] = clean_text(raw_value, maximum) or None
    country_code = clean_text(value.get("country_code"), 2).upper()
    availability = clean_text(value.get("availability_status"), 32)
    if country_code and not re.fullmatch(r"[A-Z]{2}", country_code):
        return None
    if availability and availability not in PROFILE_AVAILABILITY_STATUSES:
        return None
    creator["country_code"] = country_code or None
    creator["availability_status"] = availability or None
    for field in ("website_url", "instagram_url", "linkedin_url", "avatar_url"):
        raw_value = value.get(field)
        if raw_value is not None and not isinstance(raw_value, str):
            return None
        url = clean_text(raw_value, 2048)
        if url and not valid_profile_https_url(url, allowed_hosts=PROFILE_SOCIAL_HOSTS.get(field)):
            return None
        creator[field] = url or None
    return creator


def clean_public_delivery_status(value) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("available"), bool):
        return None
    available = value["available"]
    slug = clean_text(value.get("slug"), 96).lower()
    path = clean_text(value.get("path"), 180)
    count = value.get("published_count")
    reason = clean_text(value.get("reason"), 80) or None
    if (
        not PUBLIC_CREATOR_SLUG_PATTERN.fullmatch(slug)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or available != (count > 0)
        or (available and path != f"/creators/{slug}")
        or (available and reason is not None)
        or (not available and path)
        or (not available and reason != "no_published_works")
    ):
        return None
    return {
        "available": available,
        "public_slug": slug,
        "public_path": path or None,
        "published_count": count,
        "reason": reason,
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
        "can_self_publish": "super_admin" in roles,
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


def clean_admin_work_actor(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict) or value.get("can_govern_images") is not True:
        return None
    try:
        actor_id = clean_uuid(value.get("id"), "admin works actor id")
    except ValueError:
        return None
    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list):
        return None
    roles = sorted({clean_text(role, 40) for role in raw_roles}.intersection({"admin", "super_admin"}))
    if (
        not roles
        or (expected_actor_id and actor_id != expected_actor_id)
        or (expected_roles is not None and set(roles) != expected_roles)
    ):
        return None
    return {"id": actor_id, "roles": roles, "can_govern": True}


def clean_admin_work_principal(user: dict, authorization: dict) -> tuple[str, set[str]] | None:
    try:
        user_id = clean_uuid(user.get("id"), "admin works principal id")
        authorization_id = clean_uuid(authorization.get("user_id"), "admin works authorization id")
    except ValueError:
        return None
    raw_roles = authorization.get("roles")
    if user_id != authorization_id or not isinstance(raw_roles, list):
        return None
    roles = {clean_text(role, 40) for role in raw_roles}.intersection({"admin", "super_admin"})
    return (user_id, roles) if roles else None


def clean_admin_work_asset(value, *, expected_image_id: str, expected_owner_id: str, expected_kind: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        asset_id = clean_uuid(value.get("id"), "admin work asset id")
        image_id = clean_uuid(value.get("image_id"), "admin work asset image id")
        owner_id = clean_uuid(value.get("owner_user_id"), "admin work asset owner id")
    except ValueError:
        return None
    kind = clean_text(value.get("kind"), 32)
    bucket = clean_text(value.get("storage_bucket"), 80)
    storage_key = clean_text(value.get("storage_key"), 1024)
    mime_type = clean_text(value.get("mime_type"), 120).lower()
    width = value.get("width")
    height = value.get("height")
    byte_size = value.get("byte_size")
    scan_status = clean_text(value.get("scan_status"), 20)
    scan_result_code = clean_text(value.get("scan_result_code"), 120)
    scan_policy_version = clean_text(value.get("scan_policy_version"), 120)
    scan_completed_at = clean_text(value.get("scan_completed_at"), 80) or None
    visibility = clean_text(value.get("storage_visibility"), 20)
    expected_bucket = {"display": "image-display", "thumbnail": "image-thumbnails"}.get(expected_kind)
    key_parts = storage_key.split("/")
    if (
        image_id != expected_image_id
        or owner_id != expected_owner_id
        or kind != expected_kind
        or not expected_bucket
        or bucket != expected_bucket
        or mime_type not in WORKSPACE_IMAGE_MIME_TYPES
        or len(key_parts) != 3
        or key_parts[0] != owner_id
        or key_parts[1] != image_id
        or not re.fullmatch(rf"{re.escape(kind)}\.(?:jpg|jpeg|png|webp)", key_parts[2], re.IGNORECASE)
        or "\\" in storage_key
        or any(part in {"", ".", ".."} for part in key_parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in storage_key)
        or any(
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension < 1
            or dimension > 100_000
            for dimension in (width, height)
        )
        or isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or byte_size < 1
        or scan_status not in {"pending", "clean", "flagged", "failed"}
        or visibility not in {"private", "public"}
        or value.get("deleted_at") is not None
    ):
        return None
    checksum = clean_text(value.get("checksum_sha256"), 64).lower()
    if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
        return None
    preview_eligible = (
        scan_status == "clean"
        and scan_result_code == "clean"
        and scan_policy_version == ADMIN_WORKS_SCAN_POLICY_VERSION
        and scan_completed_at is not None
    )
    return {
        "id": asset_id,
        "image_id": image_id,
        "owner_user_id": owner_id,
        "kind": kind,
        "storage_bucket": bucket,
        "storage_key": storage_key,
        "mime_type": mime_type,
        "byte_size": byte_size,
        "width": width,
        "height": height,
        "scan_status": scan_status,
        "scan_result_code": scan_result_code,
        "scan_completed_at": scan_completed_at,
        "scan_policy_version": scan_policy_version,
        "preview_eligible": preview_eligible,
    }


def clean_admin_governance_action(value, expected_image_id: str | None = None) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        action_id = clean_uuid(value.get("id"), "governance action id")
        actor_id = clean_uuid(value.get("actor_user_id"), "governance actor id")
    except ValueError:
        return None
    action = clean_text(value.get("action"), 40)
    reason_code = clean_text(value.get("reason_code"), 80)
    created_at = clean_text(value.get("created_at"), 80)
    if action not in {"unpublish", "takedown", "restore"} or reason_code not in ADMIN_WORKS_REASON_CODES or not created_at:
        return None
    result = {
        "id": action_id,
        "action": action,
        "reason_code": reason_code,
        "actor_user_id": actor_id,
        "created_at": created_at,
    }
    action_image_id = value.get("image_id")
    if action_image_id is not None:
        try:
            action_image_id = clean_uuid(action_image_id, "governance action image id")
        except ValueError:
            return None
        if expected_image_id and action_image_id != expected_image_id:
            return None
        result["image_id"] = action_image_id
    elif expected_image_id:
        return None
    user_message = clean_text(value.get("user_message"), 1000)
    if user_message:
        result["user_message"] = user_message
    actor_role = clean_text(value.get("actor_role"), 40)
    if actor_role:
        if actor_role not in {"admin", "super_admin"}:
            return None
        result["actor_role"] = actor_role
    expected_version = value.get("expected_image_version")
    if expected_version is not None:
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            return None
        result["expected_image_version"] = expected_version
    case_id = value.get("takedown_case_id")
    if case_id is not None:
        try:
            result["takedown_case_id"] = clean_uuid(case_id, "governance takedown case id")
        except ValueError:
            return None
    policy_version = clean_text(value.get("policy_version"), 120)
    if policy_version:
        result["policy_version"] = policy_version
    return result


def clean_admin_takedown(value, expected_image_id: str | None = None) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        case_id = clean_uuid(value.get("id"), "takedown case id")
    except ValueError:
        return None
    image_id = None
    if value.get("image_id") is not None:
        try:
            image_id = clean_uuid(value.get("image_id"), "takedown image id")
        except ValueError:
            return None
        if expected_image_id and image_id != expected_image_id:
            return None
    elif expected_image_id:
        return None
    reason_code = clean_text(value.get("reason_code"), 80)
    status = clean_text(value.get("status"), 40)
    created_at = clean_text(value.get("created_at"), 80)
    legal_hold = value.get("legal_hold")
    if (
        reason_code not in ADMIN_WORKS_REASON_CODES
        or status not in {"open", "investigating", "restored", "unpublished", "closed"}
        or not created_at
        or not isinstance(legal_hold, bool)
    ):
        return None
    result = {
        "id": case_id,
        "reason_code": reason_code,
        "status": status,
        "legal_hold": legal_hold,
        "created_at": created_at,
        "resolved_at": clean_text(value.get("resolved_at"), 80) or None,
    }
    if image_id:
        result["image_id"] = image_id
    for source, target in (("requester_user_id", "requester_user_id"), ("assigned_admin_id", "assigned_admin_id")):
        if value.get(source) is not None:
            try:
                result[target] = clean_uuid(value.get(source), source.replace("_", " "))
            except ValueError:
                return None
    return result


def clean_admin_work_summary(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        image_id = clean_uuid(value.get("id"), "admin work id")
    except ValueError:
        return None
    owner = value.get("owner")
    if not isinstance(owner, dict):
        return None
    try:
        owner_id = clean_uuid(owner.get("id"), "admin work owner id")
    except ValueError:
        return None
    email = clean_text(owner.get("email"), 320).lower()
    owner_status = clean_text(owner.get("account_status"), 40)
    processing_status = clean_text(value.get("processing_status"), 40)
    workflow_status = clean_text(value.get("workflow_status"), 40)
    publication_status = clean_text(value.get("publication_status"), 40)
    version = value.get("version")
    width = value.get("original_width")
    height = value.get("original_height")
    created_at = clean_text(value.get("created_at"), 80)
    updated_at = clean_text(value.get("updated_at"), 80)
    if (
        "@" not in email
        or owner_status not in {"pending_verification", "active", "suspended", "banned", "deletion_requested", "deleted"}
        or processing_status not in DASHBOARD_PROCESSING_STATUSES
        or workflow_status not in DASHBOARD_WORKFLOW_STATUSES
        or publication_status not in ADMIN_WORKS_PUBLICATION_STATUSES
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
        or not created_at
        or not updated_at
    ):
        return None
    dimensions = (width, height)
    if any(
        dimension is not None
        and (isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1 or dimension > 100_000)
        for dimension in dimensions
    ):
        return None
    if processing_status == "ready" and any(dimension is None for dimension in dimensions):
        return None
    asset_summary = value.get("asset_summary")
    if not isinstance(asset_summary, dict):
        return None
    counts = {}
    for key in ("count", "clean_count", "flagged_count", "failed_count", "pending_count"):
        count = asset_summary.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        counts[key] = count
    if sum(counts[key] for key in ("clean_count", "flagged_count", "failed_count", "pending_count")) != counts["count"]:
        return None
    thumbnail = None
    if value.get("thumbnail_asset") is not None:
        thumbnail = clean_admin_work_asset(
            value.get("thumbnail_asset"),
            expected_image_id=image_id,
            expected_owner_id=owner_id,
            expected_kind="thumbnail",
        )
        if thumbnail is None:
            return None
    latest_review = None
    if value.get("latest_review") is not None:
        raw_review = value.get("latest_review")
        if not isinstance(raw_review, dict):
            return None
        try:
            submission_id = clean_uuid(raw_review.get("submission_id"), "latest submission id")
            review_image_id = clean_uuid(raw_review.get("image_id"), "latest review image id")
            review_version_id = clean_uuid(raw_review.get("image_version_id"), "latest review version id")
        except ValueError:
            return None
        status = clean_text(raw_review.get("status"), 40)
        decision = clean_text(raw_review.get("decision"), 40) or None
        if (
            review_image_id != image_id
            or status not in REVIEW_STATUSES
            or (decision and decision not in DASHBOARD_REVIEW_DECISIONS)
        ):
            return None
        latest_review = {
            "submission_id": submission_id,
            "status": status,
            "decision": decision,
            "submitted_at": clean_text(raw_review.get("submitted_at"), 80) or None,
            "completed_at": clean_text(raw_review.get("completed_at"), 80) or None,
            "decision_at": clean_text(raw_review.get("decision_at"), 80) or None,
            "_image_version_id": review_version_id,
        }
        if raw_review.get("assigned_reviewer_id") is not None:
            try:
                latest_review["assigned_reviewer_id"] = clean_uuid(raw_review.get("assigned_reviewer_id"), "assigned reviewer id")
            except ValueError:
                return None
    latest_action = None
    if value.get("latest_governance_action") is not None:
        latest_action = clean_admin_governance_action(value.get("latest_governance_action"), image_id)
        if latest_action is None:
            return None
    return {
        "id": image_id,
        "title": clean_text(value.get("title"), 180) or clean_text(value.get("original_filename"), 512) or "Untitled Work",
        "original_filename": clean_text(value.get("original_filename"), 512),
        "owner": {
            "display_name": clean_text(owner.get("display_name"), 120) or "Member",
            "email": email,
            "account_status": owner_status,
        },
        "processing_status": processing_status,
        "workflow_status": workflow_status,
        "publication_status": publication_status,
        "version": version,
        "original_width": width,
        "original_height": height,
        "created_at": created_at,
        "updated_at": updated_at,
        "published_at": clean_text(value.get("published_at"), 80) or None,
        "unpublished_at": clean_text(value.get("unpublished_at"), 80) or None,
        "deleted_at": clean_text(value.get("deleted_at"), 80) or None,
        "asset_summary": counts,
        "latest_review": latest_review,
        "latest_governance_action": latest_action,
        "_owner_user_id": owner_id,
        "_thumbnail_asset": thumbnail,
    }


def clean_admin_work_list_result(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_admin_work_actor(value.get("actor"), expected_actor_id=expected_actor_id, expected_roles=expected_roles)
    raw_items = value.get("items")
    raw_counts = value.get("counts")
    raw_pagination = value.get("pagination")
    if actor is None or not isinstance(raw_items, list) or len(raw_items) > ADMIN_WORKS_MAX_PAGE_SIZE:
        return None
    items = []
    seen_ids = set()
    for raw_item in raw_items:
        item = clean_admin_work_summary(raw_item)
        if item is None or item["id"] in seen_ids:
            return None
        seen_ids.add(item["id"])
        items.append(item)
    if not isinstance(raw_counts, dict) or not isinstance(raw_pagination, dict):
        return None
    counts = {}
    for key in ("all", "never_published", "published", "unpublished", "quarantined", "archived", "deleted"):
        count = raw_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        counts[key] = count
    if sum(counts[key] for key in ADMIN_WORKS_PUBLICATION_STATUSES) != counts["all"]:
        return None
    pagination = {}
    for key in ("offset", "limit", "total"):
        number = raw_pagination.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return None
        pagination[key] = number
    if (
        not 1 <= pagination["limit"] <= ADMIN_WORKS_MAX_PAGE_SIZE
        or pagination["total"] < len(items)
        or (items and pagination["offset"] + len(items) > pagination["total"])
    ):
        return None
    pagination["has_more"] = raw_pagination.get("has_more") is True
    if pagination["has_more"] != (pagination["offset"] + len(items) < pagination["total"]):
        return None
    return {"actor": actor, "items": items, "counts": counts, "pagination": pagination}


def clean_admin_current_version(value, expected_image_id: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    try:
        version_id = clean_uuid(value.get("id"), "admin current version id")
        image_id = clean_uuid(value.get("image_id"), "admin current version image id")
    except ValueError:
        return None
    version_number = value.get("version_number")
    tags = value.get("tags")
    public_exif = clean_public_exif(value.get("public_exif") if isinstance(value.get("public_exif"), dict) else {})
    gps_visibility = clean_text(value.get("gps_visibility"), 40)
    if (
        image_id != expected_image_id
        or isinstance(version_number, bool)
        or not isinstance(version_number, int)
        or version_number < 1
        or not isinstance(tags, list)
        or len(tags) > 40
        or public_exif is None
        or gps_visibility not in {"private", "approximate", "public"}
    ):
        return None
    cleaned_tags = []
    for raw_tag in tags:
        if not isinstance(raw_tag, str):
            return None
        tag = clean_text(raw_tag, 80)
        if not tag or len(raw_tag.strip()) > 80:
            return None
        cleaned_tags.append(tag)
    recognizable = value.get("contains_recognizable_people")
    rights_declared = value.get("rights_declared")
    copyright_year = value.get("copyright_year")
    if recognizable is not None and not isinstance(recognizable, bool):
        return None
    if not isinstance(rights_declared, bool):
        return None
    if copyright_year is not None and (isinstance(copyright_year, bool) or not isinstance(copyright_year, int)):
        return None
    return {
        "id": version_id,
        "version_number": version_number,
        "title": clean_text(value.get("title"), 180),
        "caption": clean_text(value.get("caption"), 500),
        "description": clean_text(value.get("description"), 6000),
        "alt_text": clean_text(value.get("alt_text"), 500),
        "tags": cleaned_tags,
        "content_category": clean_text(value.get("content_category"), 80) or None,
        "captured_at": clean_text(value.get("captured_at"), 80) or None,
        "location_name": clean_text(value.get("location_name"), 240) or None,
        "gps_visibility": gps_visibility,
        "public_exif": public_exif,
        "copyright_holder": clean_text(value.get("copyright_holder"), 160) or None,
        "copyright_year": copyright_year,
        "contains_recognizable_people": recognizable,
        "model_release_status": clean_text(value.get("model_release_status"), 40) or None,
        "property_release_status": clean_text(value.get("property_release_status"), 40) or None,
        "rights_declared": rights_declared,
        "ai_disclosure": clean_text(value.get("ai_disclosure"), 40) or None,
        "sensitive_content_disclosure": clean_text(value.get("sensitive_content_disclosure"), 80) or None,
        "locked_at": clean_text(value.get("locked_at"), 80) or None,
        "created_at": clean_text(value.get("created_at"), 80) or None,
    }


def clean_admin_work_detail(value) -> dict | None:
    summary = clean_admin_work_summary(value)
    if summary is None or not isinstance(value, dict):
        return None
    image_id = summary["id"]
    owner_id = summary["_owner_user_id"]
    current_version = clean_admin_current_version(value.get("current_version"), image_id)
    if value.get("current_version") is not None and current_version is None:
        return None
    display_asset = None
    if value.get("display_asset") is not None:
        display_asset = clean_admin_work_asset(
            value.get("display_asset"), expected_image_id=image_id, expected_owner_id=owner_id, expected_kind="display"
        )
        if display_asset is None:
            return None
    thumbnail_asset = summary["_thumbnail_asset"]
    raw_versions = value.get("versions")
    raw_submissions = value.get("review_submissions")
    raw_actions = value.get("governance_actions")
    raw_takedowns = value.get("takedowns")
    raw_audit = value.get("audit_timeline")
    if (
        not isinstance(raw_versions, list) or len(raw_versions) > 50
        or not isinstance(raw_submissions, list) or len(raw_submissions) > 50
        or not isinstance(raw_actions, list) or len(raw_actions) > 100
        or not isinstance(raw_takedowns, list) or len(raw_takedowns) > 100
        or not isinstance(raw_audit, list) or len(raw_audit) > 100
    ):
        return None
    versions = []
    for raw_version in raw_versions:
        if not isinstance(raw_version, dict):
            return None
        try:
            version_id = clean_uuid(raw_version.get("id"), "history version id")
            version_image_id = clean_uuid(raw_version.get("image_id"), "history version image id")
            creator_id = clean_uuid(raw_version.get("created_by_user_id"), "history version creator id")
        except ValueError:
            return None
        number = raw_version.get("version_number")
        if version_image_id != image_id or isinstance(number, bool) or not isinstance(number, int) or number < 1:
            return None
        versions.append({
            "id": version_id,
            "version_number": number,
            "title": clean_text(raw_version.get("title"), 180),
            "created_at": clean_text(raw_version.get("created_at"), 80) or None,
            "locked_at": clean_text(raw_version.get("locked_at"), 80) or None,
        })
    submissions = []
    for raw_submission in raw_submissions:
        if not isinstance(raw_submission, dict):
            return None
        try:
            submission_id = clean_uuid(raw_submission.get("id"), "history submission id")
            submission_image_id = clean_uuid(raw_submission.get("image_id"), "history submission image id")
            version_id = clean_uuid(raw_submission.get("image_version_id"), "history submission version id")
            version_image_id = clean_uuid(
                raw_submission.get("image_version_image_id"), "history submission version image id"
            )
        except ValueError:
            return None
        status = clean_text(raw_submission.get("status"), 40)
        lock_version = raw_submission.get("lock_version")
        raw_decisions = raw_submission.get("decisions")
        if (
            submission_image_id != image_id
            or version_image_id != image_id
            or status not in REVIEW_STATUSES
            or isinstance(lock_version, bool) or not isinstance(lock_version, int) or lock_version < 1
            or not isinstance(raw_decisions, list) or len(raw_decisions) > 20
        ):
            return None
        decisions = []
        for raw_decision in raw_decisions:
            if not isinstance(raw_decision, dict):
                return None
            try:
                decision_id = clean_uuid(raw_decision.get("id"), "history decision id")
                decision_submission_id = clean_uuid(
                    raw_decision.get("submission_id"), "history decision submission id"
                )
                reviewer_id = clean_uuid(raw_decision.get("reviewer_id"), "history decision reviewer id")
            except ValueError:
                return None
            decision = clean_text(raw_decision.get("decision"), 40)
            reason_codes = raw_decision.get("reason_codes")
            if (
                decision_submission_id != submission_id
                or decision not in DASHBOARD_REVIEW_DECISIONS
                or not isinstance(reason_codes, list)
                or len(reason_codes) > 8
            ):
                return None
            decisions.append({
                "id": decision_id,
                "reviewer_id": reviewer_id,
                "decision": decision,
                "reason_codes": [clean_text(code, 80) for code in reason_codes if isinstance(code, str) and clean_text(code, 80)],
                "user_message": clean_text(raw_decision.get("user_message"), 1000),
                "policy_version": clean_text(raw_decision.get("policy_version"), 120),
                "created_at": clean_text(raw_decision.get("created_at"), 80) or None,
            })
        submission = {
            "id": submission_id,
            "image_version_id": version_id,
            "status": status,
            "policy_version": clean_text(raw_submission.get("policy_version"), 120),
            "lock_version": lock_version,
            "submitted_at": clean_text(raw_submission.get("submitted_at"), 80) or None,
            "review_started_at": clean_text(raw_submission.get("review_started_at"), 80) or None,
            "completed_at": clean_text(raw_submission.get("completed_at"), 80) or None,
            "decisions": decisions,
        }
        if raw_submission.get("assigned_reviewer_id") is not None:
            try:
                submission["assigned_reviewer_id"] = clean_uuid(raw_submission.get("assigned_reviewer_id"), "history assigned reviewer id")
            except ValueError:
                return None
        submissions.append(submission)
    latest_review = summary.get("latest_review")
    if latest_review is not None:
        matching_submissions = [item for item in submissions if item["id"] == latest_review["submission_id"]]
        if len(matching_submissions) != 1:
            return None
        latest_submission = matching_submissions[0]
        latest_decision = latest_submission["decisions"][-1] if latest_submission["decisions"] else None
        if (
            latest_submission["image_version_id"] != latest_review.get("_image_version_id")
            or latest_submission["status"] != latest_review["status"]
            or latest_submission.get("assigned_reviewer_id") != latest_review.get("assigned_reviewer_id")
            or latest_submission.get("submitted_at") != latest_review.get("submitted_at")
            or latest_submission.get("completed_at") != latest_review.get("completed_at")
            or (latest_decision or {}).get("decision") != latest_review.get("decision")
            or (latest_decision or {}).get("created_at") != latest_review.get("decision_at")
        ):
            return None
    actions = []
    for raw_action in raw_actions:
        action = clean_admin_governance_action(raw_action, image_id)
        if action is None:
            return None
        actions.append(action)
    takedowns = []
    for raw_takedown in raw_takedowns:
        takedown = clean_admin_takedown(raw_takedown, image_id)
        if takedown is None:
            return None
        takedowns.append(takedown)
    audit = []
    for raw_log in raw_audit:
        if not isinstance(raw_log, dict):
            return None
        try:
            log_id = clean_uuid(raw_log.get("id"), "audit log id")
            audit_target_id = clean_uuid(raw_log.get("target_id"), "audit target id")
        except ValueError:
            return None
        audit_target_type = clean_text(raw_log.get("target_type"), 40)
        result = clean_text(raw_log.get("result"), 20)
        created_at = clean_text(raw_log.get("created_at"), 80)
        if (
            audit_target_type != "image"
            or audit_target_id != image_id
            or result not in {"success", "failure"}
            or not created_at
        ):
            return None
        entry = {
            "id": log_id,
            "action": clean_text(raw_log.get("action"), 120),
            "request_id": clean_text(raw_log.get("request_id"), 120),
            "reason_code": clean_text(raw_log.get("reason_code"), 80) or None,
            "policy_version": clean_text(raw_log.get("policy_version"), 120) or None,
            "result": result,
            "created_at": created_at,
        }
        if raw_log.get("actor_user_id") is not None:
            try:
                entry["actor_user_id"] = clean_uuid(raw_log.get("actor_user_id"), "audit actor id")
            except ValueError:
                return None
        role = clean_text(raw_log.get("actor_role"), 40)
        if role:
            if role not in {"admin", "super_admin"}:
                return None
            entry["actor_role"] = role
        audit.append(entry)
    summary.update({
        "current_version": current_version,
        "versions": versions,
        "review_submissions": submissions,
        "governance_actions": actions,
        "takedowns": takedowns,
        "audit_timeline": audit,
        "_display_asset": display_asset,
        "_thumbnail_asset": thumbnail_asset,
    })
    return summary


def clean_admin_work_detail_result(
    value,
    expected_image_id: str,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_admin_work_actor(value.get("actor"), expected_actor_id=expected_actor_id, expected_roles=expected_roles)
    work = clean_admin_work_detail(value.get("work"))
    if actor is None or work is None or work["id"] != expected_image_id:
        return None
    return {"actor": actor, "work": work}


def clean_admin_work_mutation_result(
    value,
    expected_image_id: str,
    expected_action: str,
    expected_reason_code: str,
    expected_user_message: str,
    expected_image_version: int,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("replayed"), bool):
        return None
    actor = clean_admin_work_actor(value.get("actor"), expected_actor_id=expected_actor_id, expected_roles=expected_roles)
    action = clean_admin_governance_action(value.get("action"), expected_image_id)
    work = clean_admin_work_summary(value.get("work"))
    if (
        actor is None
        or action is None
        or work is None
        or action["action"] != expected_action
        or action["actor_user_id"] != actor["id"]
        or action.get("actor_role") not in actor["roles"]
        or action.get("policy_version") != ADMIN_WORKS_GOVERNANCE_POLICY_VERSION
        or action["reason_code"] != expected_reason_code
        or action.get("user_message") != expected_user_message
        or action.get("expected_image_version") != expected_image_version
        or work["id"] != expected_image_id
        or work["version"] != expected_image_version + 1
    ):
        return None
    expected_status = "quarantined" if expected_action == "takedown" else "published"
    if work["publication_status"] != expected_status:
        return None
    latest_action = work.get("latest_governance_action")
    if (
        latest_action is None
        or any(
            latest_action.get(key) != action.get(key)
            for key in ("id", "image_id", "action", "reason_code", "actor_user_id", "actor_role", "policy_version")
        )
    ):
        return None
    takedown = None
    if value.get("takedown") is not None:
        takedown = clean_admin_takedown(value.get("takedown"), expected_image_id)
        if takedown is None:
            return None
    if expected_action == "takedown" and takedown is None:
        return None
    if action.get("takedown_case_id") != (takedown or {}).get("id"):
        return None
    if takedown is not None and takedown.get("assigned_admin_id") != actor["id"]:
        return None
    return {
        "actor": actor,
        "action": action,
        "replayed": value["replayed"],
        "work": work,
        "takedown": takedown,
    }


def clean_admin_user_actor(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict) or value.get("can_manage_users") is not True:
        return None
    try:
        actor_id = clean_uuid(value.get("id"), "admin users actor id")
    except ValueError:
        return None
    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list):
        return None
    roles = sorted({clean_text(role, 40) for role in raw_roles}.intersection({"admin", "super_admin"}))
    can_manage_roles = value.get("can_manage_roles")
    if (
        not roles
        or (expected_actor_id and actor_id != expected_actor_id)
        or (expected_roles is not None and set(roles) != expected_roles)
        or not isinstance(can_manage_roles, bool)
        or can_manage_roles != ("super_admin" in roles)
    ):
        return None
    return {
        "id": actor_id,
        "roles": roles,
        "permissions": {
            "can_manage_users": True,
            "can_manage_roles": can_manage_roles,
        },
    }


def clean_admin_user_principal(user: dict, authorization: dict) -> tuple[str, set[str]] | None:
    try:
        user_id = clean_uuid(user.get("id"), "admin users principal id")
        authorization_id = clean_uuid(authorization.get("user_id"), "admin users authorization id")
    except ValueError:
        return None
    raw_roles = authorization.get("roles")
    if user_id != authorization_id or not isinstance(raw_roles, list):
        return None
    roles = {clean_text(role, 40) for role in raw_roles}.intersection({"admin", "super_admin"})
    return (user_id, roles) if roles else None


def clean_admin_user_profile(value, expected_user_id: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        profile_user_id = clean_uuid(value.get("user_id"), "admin user profile owner id")
    except ValueError:
        return None
    display_name = value.get("display_name")
    if (
        profile_user_id != expected_user_id
        or not isinstance(display_name, str)
        or not display_name.strip()
        or len(display_name.strip()) > 120
    ):
        return None
    profile = {"display_name": display_name.strip()}
    for field, maximum in (
        ("professional_headline", 160),
        ("company", 160),
        ("city", 120),
    ):
        raw_value = value.get(field)
        if raw_value is not None and (not isinstance(raw_value, str) or len(raw_value.strip()) > maximum):
            return None
        profile[field] = raw_value.strip() if isinstance(raw_value, str) and raw_value.strip() else None
    country_code = value.get("country_code")
    if country_code is not None and (
        not isinstance(country_code, str)
        or not re.fullmatch(r"[A-Za-z]{2}", country_code.strip())
    ):
        return None
    profile["country_code"] = country_code.strip().upper() if isinstance(country_code, str) else None
    availability = clean_text(value.get("availability_status"), 32)
    if availability not in PROFILE_AVAILABILITY_STATUSES:
        return None
    profile["availability_status"] = availability
    return profile


def admin_user_permissions(actor: dict, user: dict) -> dict:
    actor_id = actor["id"]
    actor_roles = set(actor["roles"])
    target_roles = set(user["roles"])
    is_self = actor_id == user["id"]
    is_system = user["is_system_identity"]
    target_is_privileged = bool(target_roles.intersection({"admin", "super_admin"}))
    can_manage_target = (
        not is_self
        and not is_system
        and ("super_admin" in actor_roles or not target_is_privileged)
    )
    return {
        "can_manage_status": can_manage_target and user["account_status"] in {"active", "suspended"},
        "can_manage_roles": can_manage_target and actor["permissions"]["can_manage_roles"],
        "can_revoke_sessions": can_manage_target and user["account_status"] != "deleted",
    }


def clean_admin_user_summary(value, *, actor: dict) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        user_id = clean_uuid(value.get("id"), "admin user id")
    except ValueError:
        return None
    email = value.get("email")
    account_status = clean_text(value.get("account_status"), 40)
    version = value.get("version")
    is_system_identity = value.get("is_system_identity")
    created_at = value.get("created_at")
    updated_at = value.get("updated_at")
    last_active_at = value.get("last_active_at")
    email_verified_at = value.get("email_verified_at")
    if (
        not isinstance(email, str)
        or not 3 <= len(email.strip()) <= 320
        or "@" not in email
        or account_status not in ADMIN_USERS_ACCOUNT_STATUSES
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
        or not isinstance(is_system_identity, bool)
        or not isinstance(created_at, str)
        or not created_at
        or not isinstance(updated_at, str)
        or not updated_at
        or (last_active_at is not None and (not isinstance(last_active_at, str) or not last_active_at))
        or (email_verified_at is not None and (not isinstance(email_verified_at, str) or not email_verified_at))
    ):
        return None
    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list) or any(not isinstance(role, str) for role in raw_roles):
        return None
    roles = sorted({clean_text(role, 40) for role in raw_roles})
    if not roles or len(roles) != len(raw_roles) or not set(roles).issubset(ADMIN_USERS_ROLE_CODES) or "user" not in roles:
        return None
    profile = clean_admin_user_profile(value.get("profile"), user_id)
    sessions = value.get("sessions")
    storage = value.get("storage")
    image_counts = value.get("image_counts")
    if (
        profile is None
        or value.get("mfa_status") != "unavailable"
        or not isinstance(sessions, dict)
        or sessions.get("status") != "provider_managed"
        or sessions.get("active_count") is not None
        or sessions.get("provider_action_required") is not True
        or not isinstance(storage, dict)
        or storage.get("quota_bytes") is not None
        or storage.get("quota_status") != "unavailable"
        or not isinstance(image_counts, dict)
    ):
        return None
    used_bytes = storage.get("used_bytes")
    if isinstance(used_bytes, bool) or not isinstance(used_bytes, int) or used_bytes < 0:
        return None
    counts = {}
    for key in (
        "total",
        "draft",
        "submitted",
        "in_review",
        "changes_requested",
        "rejected",
        "approved",
        "published",
        "unpublished",
        "quarantined",
        "processing_failed",
    ):
        count = image_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        counts[key] = count
    if any(counts[key] > counts["total"] for key in counts if key != "total"):
        return None
    takedown_case_count = value.get("takedown_case_count")
    if isinstance(takedown_case_count, bool) or not isinstance(takedown_case_count, int) or takedown_case_count < 0:
        return None
    user = {
        "id": user_id,
        "email": email.strip().lower(),
        "email_verified": email_verified_at is not None,
        "email_verified_at": email_verified_at,
        "account_status": account_status,
        "version": version,
        "is_system_identity": is_system_identity,
        "roles": roles,
        "profile": profile,
        "mfa_status": "unavailable",
        "sessions": {
            "status": "provider_managed",
            "active_count": None,
            "provider_action_required": True,
        },
        "image_counts": counts,
        "storage": {
            "used_bytes": used_bytes,
            "quota_bytes": None,
            "quota_status": "unavailable",
        },
        "takedown_case_count": takedown_case_count,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_active_at": last_active_at,
    }
    user["is_self"] = actor["id"] == user_id
    user["permissions"] = admin_user_permissions(actor, user)
    return user


def clean_admin_user_action(value, expected_user_id: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        action_id = clean_uuid(value.get("id"), "admin user action id")
        target_user_id = clean_uuid(value.get("target_user_id"), "admin user action target id")
        actor_user_id = clean_uuid(value.get("actor_user_id"), "admin user action actor id")
    except ValueError:
        return None
    action = clean_text(value.get("action"), 40)
    target_role = clean_text(value.get("target_role"), 40) or None
    reason_code = clean_text(value.get("reason_code"), 80)
    actor_role = clean_text(value.get("actor_role"), 40)
    expected_version = value.get("expected_user_version")
    provider_action_required = value.get("provider_action_required")
    created_at = value.get("created_at")
    if (
        target_user_id != expected_user_id
        or action not in ADMIN_USERS_ACTIONS
        or reason_code not in ADMIN_USERS_REASON_CODES[action]
        or actor_role not in {"admin", "super_admin"}
        or isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
        or not isinstance(provider_action_required, bool)
        or provider_action_required != (action == "revoke_sessions")
        or value.get("policy_version") != ADMIN_USERS_POLICY_VERSION
        or not isinstance(created_at, str)
        or not created_at
    ):
        return None
    if action in {"grant_role", "revoke_role"}:
        if target_role not in ADMIN_USERS_ROLE_CODES:
            return None
    elif target_role is not None:
        return None
    return {
        "id": action_id,
        "action": action,
        "target_role": target_role,
        "reason_code": reason_code,
        "actor_role": actor_role,
        "expected_user_version": expected_version,
        "provider_action_required": provider_action_required,
        "policy_version": ADMIN_USERS_POLICY_VERSION,
        "created_at": created_at,
        "_actor_user_id": actor_user_id,
        "_target_user_id": target_user_id,
    }


def clean_admin_user_audit(value, expected_user_id: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        audit_id = clean_uuid(value.get("id"), "admin user audit id")
        target_id = clean_uuid(value.get("target_id"), "admin user audit target id")
        target_user_id = clean_uuid(value.get("target_user_id"), "admin user audit relationship id")
        clean_uuid(value.get("actor_user_id"), "admin user audit actor id")
    except ValueError:
        return None
    actor_role = clean_text(value.get("actor_role"), 40)
    action = clean_text(value.get("action"), 120)
    result = clean_text(value.get("result"), 20)
    created_at = value.get("created_at")
    if (
        value.get("target_type") != "user"
        or target_id != expected_user_id
        or target_user_id != expected_user_id
        or actor_role not in {"admin", "super_admin"}
        or action not in ADMIN_USERS_AUDIT_ACTIONS
        or result not in {"success", "failure"}
        or not isinstance(created_at, str)
        or not created_at
    ):
        return None
    reason_code = value.get("reason_code")
    policy_version = value.get("policy_version")
    if reason_code is not None and (not isinstance(reason_code, str) or len(reason_code.strip()) > 80):
        return None
    if reason_code and reason_code.strip() not in ADMIN_USERS_ALL_REASON_CODES:
        return None
    if policy_version != ADMIN_USERS_POLICY_VERSION:
        return None
    return {
        "id": audit_id,
        "action": action,
        "reason_code": reason_code.strip() if isinstance(reason_code, str) and reason_code.strip() else None,
        "actor_role": actor_role,
        "policy_version": policy_version.strip() if isinstance(policy_version, str) and policy_version.strip() else None,
        "result": result,
        "created_at": created_at,
    }


def clean_admin_user_list_result(
    value,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_admin_user_actor(
        value.get("actor"),
        expected_actor_id=expected_actor_id,
        expected_roles=expected_roles,
    )
    raw_items = value.get("items")
    raw_counts = value.get("counts")
    raw_pagination = value.get("pagination")
    if actor is None or not isinstance(raw_items, list) or len(raw_items) > ADMIN_USERS_MAX_PAGE_SIZE:
        return None
    items = []
    seen_ids = set()
    for raw_item in raw_items:
        item = clean_admin_user_summary(raw_item, actor=actor)
        if item is None or item["id"] in seen_ids:
            return None
        seen_ids.add(item["id"])
        items.append(item)
    if not isinstance(raw_counts, dict) or not isinstance(raw_pagination, dict):
        return None
    raw_status_counts = raw_counts.get("statuses")
    raw_role_counts = raw_counts.get("roles")
    if not isinstance(raw_status_counts, dict) or not isinstance(raw_role_counts, dict):
        return None
    status_counts = {}
    for key in ("all", *sorted(ADMIN_USERS_ACCOUNT_STATUSES)):
        count = raw_status_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None
        status_counts[key] = count
    if sum(status_counts[key] for key in ADMIN_USERS_ACCOUNT_STATUSES) != status_counts["all"]:
        return None
    role_counts = {}
    for key in sorted(ADMIN_USERS_ROLE_CODES):
        count = raw_role_counts.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > status_counts["all"]:
            return None
        role_counts[key] = count
    pagination = {}
    for key in ("offset", "limit", "total"):
        number = raw_pagination.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return None
        pagination[key] = number
    if (
        not 1 <= pagination["limit"] <= ADMIN_USERS_MAX_PAGE_SIZE
        or pagination["total"] < len(items)
        or pagination["total"] > status_counts["all"]
        or (items and pagination["offset"] + len(items) > pagination["total"])
    ):
        return None
    pagination["has_more"] = raw_pagination.get("has_more") is True
    if pagination["has_more"] != (pagination["offset"] + len(items) < pagination["total"]):
        return None
    return {
        "actor": actor,
        "items": items,
        "counts": {"statuses": status_counts, "roles": role_counts},
        "pagination": pagination,
    }


def clean_admin_user_detail_result(
    value,
    expected_user_id: str,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict):
        return None
    actor = clean_admin_user_actor(
        value.get("actor"),
        expected_actor_id=expected_actor_id,
        expected_roles=expected_roles,
    )
    raw_user = value.get("user")
    if actor is None or not isinstance(raw_user, dict):
        return None
    user = clean_admin_user_summary(raw_user, actor=actor)
    if user is None or user["id"] != expected_user_id:
        return None
    raw_images = raw_user.get("recent_images")
    raw_actions = raw_user.get("governance_actions")
    raw_audit = raw_user.get("audit_timeline")
    if (
        not isinstance(raw_images, list)
        or len(raw_images) > 50
        or not isinstance(raw_actions, list)
        or len(raw_actions) > 100
        or not isinstance(raw_audit, list)
        or len(raw_audit) > 200
    ):
        return None
    for raw_image in raw_images:
        if not isinstance(raw_image, dict):
            return None
        try:
            clean_uuid(raw_image.get("id"), "admin user recent image id")
            owner_user_id = clean_uuid(raw_image.get("owner_user_id"), "admin user recent image owner id")
        except ValueError:
            return None
        if owner_user_id != expected_user_id:
            return None
    actions = []
    for raw_action in raw_actions:
        action = clean_admin_user_action(raw_action, expected_user_id)
        if action is None:
            return None
        action.pop("_actor_user_id", None)
        action.pop("_target_user_id", None)
        actions.append(action)
    audit = []
    for raw_entry in raw_audit:
        entry = clean_admin_user_audit(raw_entry, expected_user_id)
        if entry is None:
            return None
        audit.append(entry)
    user["governance_actions"] = actions
    user["audit_timeline"] = audit
    return {"actor": actor, "user": user}


def clean_admin_user_mutation_result(
    value,
    expected_user_id: str,
    expected_action: str,
    expected_role: str | None,
    expected_reason_code: str,
    expected_user_version: int,
    *,
    expected_actor_id: str = "",
    expected_roles: set[str] | None = None,
) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("replayed"), bool):
        return None
    actor = clean_admin_user_actor(
        value.get("actor"),
        expected_actor_id=expected_actor_id,
        expected_roles=expected_roles,
    )
    if actor is None:
        return None
    user = clean_admin_user_summary(value.get("user"), actor=actor)
    action = clean_admin_user_action(value.get("action"), expected_user_id)
    if (
        user is None
        or action is None
        or user["id"] != expected_user_id
        or user["version"] != expected_user_version + 1
        or action["action"] != expected_action
        or action["target_role"] != expected_role
        or action["reason_code"] != expected_reason_code
        or action["expected_user_version"] != expected_user_version
        or action["_actor_user_id"] != actor["id"]
        or action["actor_role"] not in actor["roles"]
    ):
        return None
    action.pop("_actor_user_id", None)
    action.pop("_target_user_id", None)
    return {"actor": actor, "action": action, "user": user, "replayed": value["replayed"]}


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


def clean_profile_avatar_asset(value, expected_owner_id: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        owner_id = clean_uuid(expected_owner_id, "profile avatar owner id")
    except ValueError:
        return None
    bucket = clean_text(value.get("storage_bucket"), 80)
    storage_key = clean_text(value.get("storage_key"), 1024)
    mime_type = clean_text(value.get("mime_type"), 120).lower()
    byte_size = value.get("byte_size")
    width = value.get("width")
    height = value.get("height")
    key_parts = storage_key.split("/")
    if (
        bucket != PROFILE_AVATAR_BUCKET
        or len(key_parts) != 3
        or key_parts[0] != owner_id
        or key_parts[2] != "avatar.jpg"
        or "\\" in storage_key
        or any(part in {"", ".", ".."} for part in key_parts)
        or mime_type != PROFILE_AVATAR_MIME_TYPE
        or isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or not 1 <= byte_size <= PROFILE_AVATAR_MAX_BYTES
        or width != PROFILE_AVATAR_SIZE
        or height != PROFILE_AVATAR_SIZE
    ):
        return None
    try:
        clean_uuid(key_parts[1], "profile avatar upload id")
    except ValueError:
        return None
    return {
        "storage_bucket": bucket,
        "storage_key": storage_key,
        "mime_type": mime_type,
        "byte_size": byte_size,
        "width": width,
        "height": height,
    }


def clean_profile_avatar_upload_intent(value, expected_owner_id: str) -> dict | None:
    if not isinstance(value, dict) or isinstance(value.get("error"), dict):
        return None
    try:
        upload_id = clean_uuid(value.get("upload_id"), "profile avatar upload id")
    except ValueError:
        return None
    asset = clean_profile_avatar_asset(value, expected_owner_id)
    expires_at = clean_text(value.get("expires_at"), 80)
    if asset is None or asset["storage_key"].split("/")[1] != upload_id or not expires_at:
        return None
    superseded_keys = []
    superseded_uploads = value.get("superseded_uploads")
    if not isinstance(superseded_uploads, list):
        return None
    for upload in superseded_uploads:
        if not isinstance(upload, dict):
            return None
        try:
            superseded_id = clean_uuid(upload.get("upload_id"), "superseded profile avatar upload id")
        except ValueError:
            return None
        superseded_key = clean_profile_avatar_storage_key(upload.get("storage_key"), expected_owner_id)
        if (
            clean_text(upload.get("storage_bucket"), 80) != PROFILE_AVATAR_BUCKET
            or not superseded_key
            or superseded_key.split("/")[1] != superseded_id
        ):
            return None
        superseded_keys.append(superseded_key)
    return {
        "upload_id": upload_id,
        "expires_at": expires_at,
        "superseded_storage_keys": superseded_keys,
        **asset,
    }


def clean_profile_avatar_completion(value, expected_owner_id: str) -> dict | None:
    if not isinstance(value, dict) or isinstance(value.get("error"), dict):
        return None
    avatar = clean_profile_avatar_asset(value.get("avatar"), expected_owner_id)
    previous_value = value.get("previous_avatar")
    previous = None
    if previous_value is not None:
        previous = clean_profile_avatar_asset(previous_value, expected_owner_id)
        if previous is None:
            return None
    if avatar is None:
        return None
    if value.get("replayed") not in {True, False}:
        return None
    return {
        "avatar": avatar,
        "previous_storage_key": previous["storage_key"] if previous else None,
        "replayed": value["replayed"],
    }


def clean_profile_avatar_cancellation(value, expected_owner_id: str) -> dict | None:
    if not isinstance(value, dict) or value.get("canceled") is not True:
        return None
    upload = value.get("upload")
    if not isinstance(upload, dict):
        return None
    try:
        upload_id = clean_uuid(upload.get("upload_id"), "canceled profile avatar upload id")
    except ValueError:
        return None
    storage_key = clean_profile_avatar_storage_key(upload.get("storage_key"), expected_owner_id)
    status = clean_text(value.get("status"), 20)
    if (
        clean_text(upload.get("storage_bucket"), 80) != PROFILE_AVATAR_BUCKET
        or not storage_key
        or storage_key.split("/")[1] != upload_id
        or status not in {"canceled", "expired"}
    ):
        return None
    return {"storage_key": storage_key, "status": status}


def clean_profile_avatar_removal(value, expected_owner_id: str) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("removed"), bool):
        return None
    previous_value = value.get("previous_avatar")
    previous = None
    if previous_value is not None:
        previous = clean_profile_avatar_asset(previous_value, expected_owner_id)
        if previous is None:
            return None
    canceled_keys = []
    canceled_uploads = value.get("canceled_uploads")
    if not isinstance(canceled_uploads, list):
        return None
    for upload in canceled_uploads:
        if not isinstance(upload, dict):
            return None
        try:
            upload_id = clean_uuid(upload.get("upload_id"), "canceled profile avatar upload id")
        except ValueError:
            return None
        storage_key = clean_profile_avatar_storage_key(upload.get("storage_key"), expected_owner_id)
        if (
            clean_text(upload.get("storage_bucket"), 80) != PROFILE_AVATAR_BUCKET
            or not storage_key
            or storage_key.split("/")[1] != upload_id
        ):
            return None
        canceled_keys.append(storage_key)
    if value["removed"] is False and previous is not None:
        return None
    return {
        "removed": value["removed"],
        "previous_storage_key": previous["storage_key"] if previous else None,
        "canceled_storage_keys": canceled_keys,
    }


def clean_profile_avatar_storage_key(value: str, expected_owner_id: str) -> str:
    key = clean_text(value, 1024)
    if not key:
        return ""
    asset = clean_profile_avatar_asset(
        {
            "storage_bucket": PROFILE_AVATAR_BUCKET,
            "storage_key": key,
            "mime_type": PROFILE_AVATAR_MIME_TYPE,
            "byte_size": 1,
            "width": PROFILE_AVATAR_SIZE,
            "height": PROFILE_AVATAR_SIZE,
        },
        expected_owner_id,
    )
    return key if asset is not None else ""


def clean_public_profile_avatar(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        owner_id = clean_uuid(value.get("owner_user_id"), "public profile avatar owner id")
    except ValueError:
        return None
    asset = clean_profile_avatar_asset(value, owner_id)
    if asset is None:
        return None
    return {"owner_user_id": owner_id, **asset}


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

    @staticmethod
    def header_initials(display_name: str) -> str:
        words = [word for word in clean_text(display_name, 120).split() if word]
        return "".join(word[0].upper() for word in words[:2]) or "MT"

    def header_identity_model(
        self,
        user: dict | None,
        authorization: dict | None,
        profile: dict | None,
        *,
        status: str = "authenticated",
    ) -> dict:
        if not isinstance(user, dict):
            return {
                "authenticated": False,
                "status": status,
                "display_name": "",
                "email": "",
                "initials": "",
                "avatar_url": None,
                "roles": [],
                "can_review": False,
                "can_govern": False,
                "can_manage_users": False,
                "account_status": "",
            }

        metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
        display_name = clean_text((profile or {}).get("display_name"), 120)
        display_name = display_name or clean_text(metadata.get("display_name"), 120) or "Member"
        email = clean_text(user.get("email"), 320).lower()
        raw_roles = authorization.get("roles") if isinstance(authorization, dict) else []
        roles = sorted({clean_text(role, 40) for role in raw_roles if isinstance(role, str)})
        account_status = clean_text((authorization or {}).get("account_status"), 40)
        active = account_status == "active"
        avatar_url = clean_text((profile or {}).get("avatar_url"), 2048)
        signed_avatar = self.signed_profile_avatar_coordinates(
            avatar_url,
            clean_text(user.get("id"), 64),
        )
        if avatar_url and not valid_profile_https_url(avatar_url) and signed_avatar is None:
            avatar_url = ""
        return {
            "authenticated": True,
            "status": status,
            "display_name": display_name,
            "email": email,
            "initials": self.header_initials(display_name),
            "avatar_url": avatar_url or None,
            "roles": roles,
            "can_review": active and bool(set(roles).intersection({"reviewer", "admin", "super_admin"})),
            "can_govern": active and bool(set(roles).intersection({"admin", "super_admin"})),
            "can_manage_users": active and bool(set(roles).intersection({"admin", "super_admin"})),
            "account_status": account_status,
        }

    def current_header_identity(
        self,
        *,
        user: dict | None = None,
        authorization: dict | None = None,
    ) -> dict:
        if user is None:
            if not self.cookie_value(ACCESS_COOKIE) and not self.cookie_value(REFRESH_COOKIE):
                return self.header_identity_model(None, None, None, status="anonymous")
            auth_status, user = self.current_auth_user()
            if auth_status == HTTPStatus.UNAUTHORIZED:
                return self.header_identity_model(None, None, None, status="anonymous")
            if auth_status != HTTPStatus.OK or not isinstance(user, dict):
                return self.header_identity_model(None, None, None, status="unavailable")

        if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
            return self.header_identity_model(user, None, None, status="degraded")

        if authorization is None:
            authz_status, authorization = self.current_authorization(user)
            if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
                return self.header_identity_model(user, None, None, status="degraded")

        profile_status, profile = self.fetch_current_profile(user)
        if profile_status != HTTPStatus.OK or not isinstance(profile, dict):
            return self.header_identity_model(user, authorization, None, status="degraded")
        return self.header_identity_model(user, authorization, profile)

    def signed_profile_avatar_coordinates(
        self,
        value: str,
        expected_owner_id: str = "",
    ) -> tuple[str, str] | None:
        avatar = urlparse(clean_text(value, 2048))
        provider = urlparse(SUPABASE_URL)
        prefix = f"{provider.path.rstrip('/')}/storage/v1/object/sign/"
        if (
            not provider.netloc
            or avatar.scheme != provider.scheme
            or avatar.netloc != provider.netloc
            or not avatar.path.startswith(prefix)
        ):
            return None
        encoded = avatar.path[len(prefix):]
        if "/" not in encoded:
            return None
        encoded_bucket, encoded_key = encoded.split("/", 1)
        bucket = clean_text(unquote(encoded_bucket), 80)
        storage_key = clean_text(unquote(encoded_key), 1024)
        key_parts = storage_key.split("/")
        if (
            bucket != PROFILE_AVATAR_BUCKET
            or len(key_parts) != 3
            or key_parts[2] != "avatar.jpg"
            or (expected_owner_id and key_parts[0] != clean_text(expected_owner_id, 64))
            or not clean_profile_avatar_storage_key(storage_key, key_parts[0])
        ):
            return None
        return bucket, storage_key

    def sign_profile_avatar_asset(self, user: dict, storage_key: str) -> str:
        owner_id = clean_text(user.get("id"), 64)
        safe_key = clean_profile_avatar_storage_key(storage_key, owner_id)
        if not safe_key:
            return ""
        endpoint = f"object/sign/{quote(PROFILE_AVATAR_BUCKET, safe='')}/{quote(safe_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": PROFILE_AVATAR_SIGNED_URL_TTL},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if (
            status != HTTPStatus.OK
            or self.signed_profile_avatar_coordinates(signed_url, owner_id)
            != (PROFILE_AVATAR_BUCKET, safe_key)
        ):
            return ""
        return signed_url

    def refresh_signed_profile_avatar(self, user: dict, profile: dict) -> dict:
        owner_id = clean_text(user.get("id"), 64)
        coordinates = self.signed_profile_avatar_coordinates(profile.get("avatar_url") or "", owner_id)
        if coordinates is None:
            return profile
        bucket, storage_key = coordinates
        endpoint = f"object/sign/{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": HEADER_AVATAR_SIGNED_URL_TTL},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if status != HTTPStatus.OK or self.signed_profile_avatar_coordinates(signed_url, owner_id) != coordinates:
            return profile
        refreshed = dict(profile)
        refreshed["avatar_url"] = signed_url
        return refreshed

    @staticmethod
    def header_role_label(roles: list[str]) -> str:
        if "super_admin" in roles:
            return "Super Admin"
        if "admin" in roles:
            return "Administrator"
        if "reviewer" in roles:
            return "Reviewer"
        return "Member"

    def render_header_identity(self, identity: dict) -> str:
        if identity.get("status") == "anonymous":
            return (
                '<div class="header-identity-slot" data-header-identity-slot>'
                '<a class="home-account-entry" href="/auth/sign-in" data-public-sign-in>Sign In</a>'
                "</div>"
            )
        if not identity.get("authenticated"):
            return (
                '<div class="header-identity-slot" data-header-identity-slot>'
                '<span class="header-identity-unavailable" aria-label="Account identity is temporarily unavailable">MT</span>'
                "</div>"
            )

        display_name = html.escape(clean_text(identity.get("display_name"), 120) or "Member", quote=True)
        email = html.escape(clean_text(identity.get("email"), 320), quote=True)
        initials = html.escape(clean_text(identity.get("initials"), 8) or "MT", quote=True)
        account_status = clean_text(identity.get("account_status"), 40)
        status_label = "Active account" if account_status == "active" else "Account access limited"
        avatar_url = clean_text(identity.get("avatar_url"), 2048)
        avatar_markup = ""
        if avatar_url:
            avatar_markup = (
                f'<img src="{html.escape(avatar_url, quote=True)}" alt="" decoding="async" '
                'data-account-menu-image />'
            )
        return f"""
<div class="header-identity-slot" data-header-identity-slot>
  <div class="account-menu" data-account-menu>
    <button class="account-profile-link" type="button" aria-haspopup="menu" aria-expanded="false" aria-controls="account-menu-actions" aria-label="Open account menu for {display_name}" data-account-profile-link>
      <span data-account-menu-initials aria-hidden="true">{initials}</span>
      {avatar_markup}
    </button>
    <button class="account-menu-trigger" type="button" aria-haspopup="menu" aria-expanded="false" aria-controls="account-menu-actions" aria-label="Open account menu" title="Account menu" data-account-menu-trigger>
      <span class="account-menu-trigger-icon" aria-hidden="true"><span></span><span></span><span></span></span>
    </button>
    <div class="account-menu-popover" data-account-menu-popover hidden>
      <div class="account-menu-identity">
        <a class="account-menu-avatar" href="/dashboard" aria-label="Open personal profile" data-account-menu-avatar>
          <span data-account-menu-avatar-initials aria-hidden="true">{initials}</span>
          {avatar_markup}
        </a>
        <span class="account-menu-identity-copy">
          <strong data-account-menu-name>{display_name}</strong>
          <span data-account-menu-email>{email}</span>
          <em data-account-menu-status>{status_label}</em>
        </span>
      </div>
      <div class="account-menu-actions" id="account-menu-actions" role="menu" aria-label="Account">
        <nav class="account-menu-links" role="none">
          <a href="/dashboard" role="menuitem">Dashboard</a>
          <a href="/workspace/images" role="menuitem">Workspace</a>
          <a href="/settings/account" role="menuitem">Account Settings</a>
        </nav>
        <button class="account-menu-signout" type="button" role="menuitem" data-account-menu-signout>Sign out</button>
      </div>
      <p class="account-menu-error" role="alert" tabindex="-1" data-account-menu-error hidden></p>
    </div>
  </div>
</div>""".strip()

    def serve_header_html(
        self,
        filename: str,
        *,
        user: dict | None = None,
        authorization: dict | None = None,
    ) -> None:
        try:
            source = (ROOT / filename).read_text(encoding="utf-8")
        except OSError:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Page not found."})
            return
        bootstrap_marker = next(
            (
                marker for marker in (
                    HEADER_IDENTITY_BOOTSTRAP_MARKER,
                    HEADER_IDENTITY_BOOTSTRAP_FALLBACK_MARKER,
                ) if marker in source
            ),
            "",
        )
        if not bootstrap_marker or HEADER_IDENTITY_SLOT_MARKER not in source:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Header identity shell is unavailable."})
            return

        identity = self.current_header_identity(user=user, authorization=authorization)
        bootstrap = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
        bootstrap = bootstrap.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        rendered_bootstrap = f'<template id="mt-header-identity" data-header-identity>{bootstrap}</template>'
        source = source.replace(bootstrap_marker, rendered_bootstrap, 1)
        source = source.replace(HEADER_IDENTITY_SLOT_MARKER, self.render_header_identity(identity), 1)
        if identity.get("can_review"):
            source = source.replace(" data-review-nav hidden", " data-review-nav")
        if identity.get("can_govern"):
            source = source.replace(" data-governance-nav hidden", " data-governance-nav")
        if identity.get("can_manage_users"):
            source = source.replace(" data-users-nav hidden", " data-users-nav")

        body = source.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        self.wfile.write(body)

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
        if canonical_path == "/healthz":
            body_length = len(json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(body_length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        protected_route = (
            canonical_path.startswith("/api/")
            or canonical_path.startswith("/admin/reviews")
            or canonical_path.startswith("/admin/works")
            or canonical_path.startswith("/admin/users")
            or canonical_path.startswith("/admin/audit")
            or canonical_path.startswith("/inbox")
            or canonical_path.startswith("/notifications")
            or canonical_path.startswith("/workspace/notifications")
            or canonical_path == "/readyz"
            or canonical_path == "/assets/uploads"
            or canonical_path.startswith("/assets/uploads/")
            or canonical_path in {
                "/admin-reviews.html",
                "/admin-reviews.js",
                "/admin-works.html",
                "/admin-works.js",
                "/admin-users.html",
                "/admin-users.js",
                "/admin-audit.html",
                "/admin-audit.js",
                "/notifications.html",
                "/notifications.js",
                "/inbox.html",
                "/inbox.js",
                "/manage",
                "/manage.html",
                "/dashboard",
                "/dashboard.html",
                "/dashboard.js",
                "/upload-studio.html",
                "/upload-studio.js",
                "/account-settings.js",
                "/manage.js",
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
        creator_parts = [part for part in canonical_path.split("/") if part]
        if (
            len(creator_parts) == 2
            and creator_parts[0] == "creators"
            and PUBLIC_CREATOR_SLUG_PATTERN.fullmatch(creator_parts[1].lower())
        ):
            self.path = "/creator.html"
            super().do_HEAD()
            return
        if canonical_path == "/":
            self.path = "/index.html"
            super().do_HEAD()
            return
        if not is_public_static_path(canonical_path):
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
            "/admin-works.html",
            "/admin-works.js",
            "/admin-users.html",
            "/admin-users.js",
            "/admin-audit.html",
            "/admin-audit.js",
            "/notifications.html",
            "/notifications.js",
            "/inbox.html",
            "/inbox.js",
            "/dashboard.html",
            "/dashboard.js",
            "/upload-studio.html",
            "/upload-studio.js",
            "/manage.js",
            "/account-menu.js",
            "/global-header.js",
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

    def handle_me(self, parsed=None) -> None:
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
        query = parse_qs((parsed or urlparse(self.path)).query)
        if query.get("refresh_avatar") == ["1"]:
            profile = self.refresh_signed_profile_avatar(user, profile)
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
        query = urlencode({
            "select": ",".join((*PROFILE_FIELDS, *PROFILE_AVATAR_STORAGE_FIELDS)),
            "user_id": f"eq.{user_id}",
            "limit": "1",
        })
        status, result = supabase_rest_request(
            f"user_profiles?{query}",
            self.current_access_token(user),
            method="GET",
        )
        if status != HTTPStatus.OK or not isinstance(result, list) or len(result) != 1:
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile could not be loaded.")
        provider_profile = result[0]
        profile = clean_profile_result(provider_profile)
        if profile is None:
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile could not be loaded.")
        storage_key = clean_text(provider_profile.get("avatar_storage_key"), 1024)
        storage_values = [
            provider_profile.get(field)
            for field in PROFILE_AVATAR_STORAGE_FIELDS
            if field != "avatar_updated_at"
        ]
        if storage_key:
            avatar_asset = clean_profile_avatar_asset(
                {
                    "storage_bucket": provider_profile.get("avatar_storage_bucket"),
                    "storage_key": storage_key,
                    "mime_type": provider_profile.get("avatar_mime_type"),
                    "byte_size": provider_profile.get("avatar_byte_size"),
                    "width": provider_profile.get("avatar_width"),
                    "height": provider_profile.get("avatar_height"),
                },
                user_id,
            )
            if avatar_asset is None:
                return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile avatar could not be verified.")
            profile["avatar_url"] = self.sign_profile_avatar_asset(user, storage_key) or None
        elif any(value is not None for value in storage_values):
            return HTTPStatus.BAD_GATEWAY, auth_error("PROFILE_UNAVAILABLE", "Your profile avatar could not be verified.")
        else:
            profile = self.refresh_signed_profile_avatar(user, profile)
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
            "profile": {field: profile.get(field) for field in PROFILE_FIELDS},
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
        profile_status, profile = self.fetch_current_profile(user)
        if profile_status != HTTPStatus.OK:
            self.send_json(profile_status, profile)
            return
        self.send_auth_json(HTTPStatus.OK, {"profile": profile, "saved": True})

    def send_profile_avatar_error(self, value: dict) -> None:
        code = clean_text(value.get("code"), 80) or "PROFILE_AVATAR_PROVIDER_FAILED"
        message = clean_text(value.get("message"), 500) or "Your profile photo could not be updated."
        status = {
            "PROFILE_AVATAR_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY,
            "PROFILE_AVATAR_UPLOAD_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY,
            "PROFILE_AVATAR_UPLOAD_NOT_FOUND": HTTPStatus.NOT_FOUND,
            "PROFILE_AVATAR_UPLOAD_EXPIRED": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_UPLOAD_INCOMPLETE": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_UPLOAD_ALREADY_COMPLETED": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_UPLOAD_INACTIVE": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_UPLOAD_SUPERSEDED": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_UPLOAD_COMPLETED": HTTPStatus.CONFLICT,
            "PROFILE_AVATAR_PROFILE_UNAVAILABLE": HTTPStatus.NOT_FOUND,
        }.get(code, HTTPStatus.BAD_GATEWAY)
        self.send_json(status, auth_error(code, message))

    def profile_avatar_rpc(
        self,
        name: str,
        payload: dict | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return None, None, None
        status, result = supabase_rest_request(
            f"rpc/{name}",
            self.current_access_token(user),
            payload or {},
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_PROVIDER_FAILED", "Profile photo storage is temporarily unavailable."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_profile_avatar_error(result["error"])
            return None, None, None
        return user, authorization, result

    def signed_profile_avatar_upload_url(self, user: dict, intent: dict) -> str:
        endpoint = (
            f"object/upload/sign/{quote(intent['storage_bucket'], safe='')}/"
            f"{quote(intent['storage_key'], safe='/')}"
        )
        status, signed = supabase_storage_request(endpoint, self.current_access_token(user), {})
        signed_url = self.absolute_storage_url(signed.get("url", "")) if isinstance(signed, dict) else ""
        parsed = urlparse(signed_url)
        provider = urlparse(SUPABASE_URL)
        expected_path = (
            f"{provider.path.rstrip('/')}/storage/v1/object/upload/sign/"
            f"{intent['storage_bucket']}/{intent['storage_key']}"
        )
        if (
            status != HTTPStatus.OK
            or parsed.scheme != provider.scheme
            or parsed.netloc != provider.netloc
            or unquote(parsed.path) != expected_path
            or not parsed.query
        ):
            return ""
        return signed_url

    def remove_profile_avatar_object(self, user: dict, storage_key: str) -> bool:
        owner_id = clean_text(user.get("id"), 64)
        safe_key = clean_profile_avatar_storage_key(storage_key, owner_id)
        if not safe_key:
            return False
        status, _ = supabase_storage_request(
            f"bucket/{quote(PROFILE_AVATAR_BUCKET, safe='')}/delete",
            self.current_access_token(user),
            {"prefixes": [safe_key]},
        )
        return status == HTTPStatus.OK

    def handle_profile_avatar_intent_create(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        expected_fields = {"mime_type", "byte_size", "width", "height"}
        mime_type = clean_text(body.get("mime_type"), 120).lower()
        byte_size = body.get("byte_size")
        width = body.get("width")
        height = body.get("height")
        if (
            set(body) != expected_fields
            or mime_type != PROFILE_AVATAR_MIME_TYPE
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or not 1 <= byte_size <= PROFILE_AVATAR_MAX_BYTES
            or width != PROFILE_AVATAR_SIZE
            or height != PROFILE_AVATAR_SIZE
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "PROFILE_AVATAR_VALIDATION_FAILED",
                    "Choose an image that can be prepared as a 512 by 512 JPEG under 1 MB.",
                ),
            )
            return
        user, _, result = self.profile_avatar_rpc(
            "create_my_profile_avatar_upload",
            {
                "avatar_mime_type": mime_type,
                "avatar_byte_size": byte_size,
                "avatar_width": width,
                "avatar_height": height,
            },
        )
        if not user or result is None:
            return
        intent = clean_profile_avatar_upload_intent(result, clean_text(user.get("id"), 64))
        if intent is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_PROVIDER_FAILED", "The profile photo upload destination was invalid."),
            )
            return
        for superseded_key in intent["superseded_storage_keys"]:
            self.remove_profile_avatar_object(user, superseded_key)
        signed_url = self.signed_profile_avatar_upload_url(user, intent)
        if not signed_url:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_UPLOAD_INTENT_FAILED", "A secure profile photo upload could not be created."),
            )
            return
        self.send_auth_json(
            HTTPStatus.CREATED,
            {
                "upload": {
                    "id": intent["upload_id"],
                    "signed_url": signed_url,
                    "mime_type": intent["mime_type"],
                    "byte_size": intent["byte_size"],
                    "width": intent["width"],
                    "height": intent["height"],
                    "expires_at": intent["expires_at"],
                }
            },
        )

    def handle_profile_avatar_complete(self, upload_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            safe_upload_id = clean_uuid(upload_id, "profile avatar upload id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("PROFILE_AVATAR_UPLOAD_NOT_FOUND", "This profile photo upload is unavailable."))
            return
        if body != {"confirmation": "complete-profile-avatar"}:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_AVATAR_VALIDATION_FAILED", "Confirm the profile photo upload before saving it."),
            )
            return
        user, authorization, result = self.profile_avatar_rpc(
            "complete_my_profile_avatar_upload",
            {"upload_id": safe_upload_id},
        )
        if not user or not authorization or result is None:
            return
        completed = clean_profile_avatar_completion(result, clean_text(user.get("id"), 64))
        if completed is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_PROVIDER_FAILED", "The saved profile photo could not be verified."),
            )
            return
        previous_key = completed.get("previous_storage_key")
        if previous_key and previous_key != completed["avatar"]["storage_key"]:
            self.remove_profile_avatar_object(user, previous_key)
        profile_status, profile = self.fetch_current_profile(user)
        if profile_status != HTTPStatus.OK:
            self.send_json(profile_status, profile)
            return
        self.send_auth_json(
            HTTPStatus.OK,
            {"profile": profile, "saved": True},
        )

    def handle_profile_avatar_intent_cancel(self, upload_id: str) -> None:
        body = self.read_json_body()
        if body is None:
            return
        try:
            safe_upload_id = clean_uuid(upload_id, "profile avatar upload id")
        except ValueError:
            self.send_json(HTTPStatus.NOT_FOUND, auth_error("PROFILE_AVATAR_UPLOAD_NOT_FOUND", "This profile photo upload is unavailable."))
            return
        if body != {"confirmation": "cancel-profile-avatar"}:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_AVATAR_VALIDATION_FAILED", "Confirm the upload cancellation."),
            )
            return
        user, _, result = self.profile_avatar_rpc(
            "cancel_my_profile_avatar_upload",
            {"upload_id": safe_upload_id},
        )
        if not user or result is None:
            return
        canceled = clean_profile_avatar_cancellation(result, clean_text(user.get("id"), 64))
        if canceled is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_PROVIDER_FAILED", "The canceled upload could not be verified."),
            )
            return
        self.remove_profile_avatar_object(user, canceled["storage_key"])
        self.send_auth_json(HTTPStatus.OK, {"canceled": True})

    def handle_profile_avatar_remove(self) -> None:
        body = self.read_json_body()
        if body is None:
            return
        if body != {"confirmation": "remove-profile-avatar"}:
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("PROFILE_AVATAR_VALIDATION_FAILED", "Confirm removal of the current profile photo."),
            )
            return
        user, authorization, result = self.profile_avatar_rpc("remove_my_profile_avatar")
        if not user or not authorization or result is None:
            return
        removed = clean_profile_avatar_removal(result, clean_text(user.get("id"), 64))
        if removed is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("PROFILE_AVATAR_PROVIDER_FAILED", "The profile photo removal result was invalid."),
            )
            return
        cleanup_keys = [
            key
            for key in [removed["previous_storage_key"], *removed["canceled_storage_keys"]]
            if key
        ]
        for storage_key in dict.fromkeys(cleanup_keys):
            self.remove_profile_avatar_object(user, storage_key)
        profile_status, profile = self.fetch_current_profile(user)
        if profile_status != HTTPStatus.OK:
            self.send_json(profile_status, profile)
            return
        self.send_auth_json(HTTPStatus.OK, {"profile": profile, "removed": removed["removed"]})

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

    def send_admin_works_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "ADMIN_WORKS_PROVIDER_FAILED"
        if code not in ADMIN_WORKS_ERROR_STATUS:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works provider returned an unsupported error."),
            )
            return
        message = clean_text(error.get("message"), 500) or "Unable to complete this Works request."
        self.send_auth_json(ADMIN_WORKS_ERROR_STATUS[code], auth_error(code, message))

    def send_admin_works_provider_error(self, status: int) -> None:
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_auth_json(HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue."))
            return
        if status == HTTPStatus.FORBIDDEN:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error(
                    "ADMIN_WORKS_ACCESS_REVOKED",
                    "Works governance access is no longer available. Sign in again or contact an administrator.",
                ),
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
                auth_error("ADMIN_WORKS_PROVIDER_UNAVAILABLE", "Works governance is temporarily unavailable. Try again."),
            )
            return
        self.send_auth_json(
            HTTPStatus.BAD_GATEWAY,
            auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works provider could not complete this request."),
        )

    def admin_works_rpc(
        self,
        name: str,
        payload: dict | None = None,
        *,
        principal: tuple[dict, dict] | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        if principal is None:
            allowed, authorization = self.require_admin()
            user = getattr(self, "_admin_principal_user", None)
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
            self.send_admin_works_provider_error(status)
            return None, None, None
        if not isinstance(result, dict):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works provider response was invalid."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_admin_works_error(result["error"])
            return None, None, None
        return user, authorization, result

    def send_admin_users_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "ADMIN_USERS_PROVIDER_FAILED"
        status = ADMIN_USERS_ERROR_STATUS.get(code)
        if status is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user provider returned an unsupported error."),
            )
            return
        messages = {
            "ADMIN_USER_FILTER_INVALID": "Choose supported user filters.",
            "ADMIN_USER_SORT_INVALID": "Choose a supported user sort.",
            "ADMIN_USER_SEARCH_INVALID": "Search is limited to 160 characters.",
            "ADMIN_USER_PAGE_INVALID": "Choose supported user pagination values.",
            "ADMIN_USER_NOT_FOUND": "The user is unavailable.",
            "ADMIN_USER_VERSION_CONFLICT": "This user changed. Reload before applying governance.",
            "ADMIN_USER_VALIDATION_FAILED": "Choose a supported user action and reason.",
            "ADMIN_USER_IDEMPOTENCY_CONFLICT": "This request key is already bound to another user action.",
            "ADMIN_USER_STATE_CONFLICT": "The requested action is not valid for the current user state.",
            "ADMIN_USER_SELF_ACTION_FORBIDDEN": "Use Account Settings for your own account and sessions.",
            "ADMIN_USER_SYSTEM_IDENTITY": "System identities cannot be governed here.",
            "ADMIN_USER_TARGET_FORBIDDEN": "Only a Super Admin can govern an administrator account.",
            "ADMIN_USER_ROLE_FORBIDDEN": "Only a Super Admin can manage supported roles.",
            "ADMIN_USER_LAST_SUPER_ADMIN": "At least one active Super Admin must remain.",
        }
        self.send_auth_json(status, auth_error(code, messages[code]))

    def send_admin_users_provider_error(self, status: int) -> None:
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_auth_json(HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue."))
            return
        if status == HTTPStatus.FORBIDDEN:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error(
                    "ADMIN_USERS_ACCESS_REVOKED",
                    "User administration access is no longer available. Sign in again or contact a Super Admin.",
                ),
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
                auth_error("ADMIN_USERS_PROVIDER_UNAVAILABLE", "User administration is temporarily unavailable. Try again."),
            )
            return
        self.send_auth_json(
            HTTPStatus.BAD_GATEWAY,
            auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user provider could not complete this request."),
        )

    def admin_users_rpc(
        self,
        name: str,
        payload: dict | None = None,
        *,
        principal: tuple[dict, dict] | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        if principal is None:
            allowed, authorization = self.require_admin()
            user = getattr(self, "_admin_principal_user", None)
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
            self.send_admin_users_provider_error(status)
            return None, None, None
        if not isinstance(result, dict):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user provider response was invalid."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_admin_users_error(result["error"])
            return None, None, None
        return user, authorization, result

    def send_communications_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "COMMUNICATIONS_PROVIDER_FAILED"
        status = COMMUNICATIONS_ERROR_STATUS.get(code)
        if status is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The communications provider returned an unsupported error."),
            )
            return
        messages = {
            "NOTIFICATION_PAGE_INVALID": "Choose a notification page size from 1 to 100.",
            "NOTIFICATION_CURSOR_INVALID": "Use a complete notification cursor.",
            "NOTIFICATION_NOT_FOUND": "The notification is unavailable.",
            "INQUIRY_VALIDATION_FAILED": "Review the inquiry fields and try again.",
            "INQUIRY_WORKS_INVALID": "Select up to 10 published works from one creator.",
            "INQUIRY_WORK_NOT_FOUND": "A selected work is unavailable.",
            "INQUIRY_RECIPIENT_CONFLICT": "Selected works must belong to one inquiry recipient.",
            "INQUIRY_IDEMPOTENCY_CONFLICT": "This request key is already bound to another inquiry.",
            "INQUIRY_RATE_LIMITED": "Too many recent inquiries. Try again later.",
            "INQUIRY_RECIPIENT_UNAVAILABLE": "No inquiry recipient is currently available.",
            "INQUIRY_SELF_FORBIDDEN": "An inquiry cannot be sent to the same account.",
            "INQUIRY_REJECTED": "The inquiry could not be accepted.",
            "COMMUNICATION_ACCOUNT_RESTRICTED": "This account cannot use communications.",
            "CONVERSATION_FILTER_INVALID": "Choose a supported conversation status.",
            "CONVERSATION_PAGE_INVALID": "Choose a supported conversation page size.",
            "CONVERSATION_CURSOR_INVALID": "Use a complete conversation cursor.",
            "CONVERSATION_NOT_FOUND": "The conversation is unavailable.",
            "CONVERSATION_VERSION_CONFLICT": "This conversation changed. Reload before replying.",
            "CONVERSATION_STATE_CONFLICT": "A closed conversation cannot accept replies.",
            "CONVERSATION_REPLY_INVALID": "Provide a valid reply and current conversation version.",
            "CONVERSATION_MESSAGE_INVALID": "Provide a valid reply and current conversation version.",
            "CONVERSATION_IDEMPOTENCY_CONFLICT": "This request key is already bound to another message.",
            "CONVERSATION_MESSAGE_NOT_FOUND": "The message is unavailable.",
            "CONVERSATION_READ_TARGET_INVALID": "The read target is unavailable.",
            "CONVERSATION_STATUS_INVALID": "Choose open or closed and provide the current conversation version.",
            "CONVERSATION_STATUS_IDEMPOTENCY_CONFLICT": "This request key is already bound to another status change.",
        }
        self.send_auth_json(status, auth_error(code, messages[code]))

    def send_communications_provider_error(self, status: int) -> None:
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_auth_json(HTTPStatus.UNAUTHORIZED, auth_error("AUTH_REQUIRED", "Sign in to continue."))
            return
        if status == HTTPStatus.FORBIDDEN:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error("COMMUNICATIONS_ACCESS_REVOKED", "Communications access is no longer available. Sign in again."),
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
                auth_error("COMMUNICATIONS_PROVIDER_UNAVAILABLE", "Communications are temporarily unavailable. Try again."),
            )
            return
        self.send_auth_json(
            HTTPStatus.BAD_GATEWAY,
            auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The communications provider could not complete this request."),
        )

    def communications_rpc(
        self,
        name: str,
        payload: dict | None = None,
        *,
        principal: tuple[dict, dict] | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        if principal is None:
            user, authorization = self.require_account_session()
            if not user or not authorization:
                return None, None, None
        else:
            user, authorization = principal
        status, result = supabase_rest_request(
            f"rpc/{name}",
            self.current_access_token(user),
            payload or {},
        )
        if status != HTTPStatus.OK:
            self.send_communications_provider_error(status)
            return None, None, None
        if not isinstance(result, dict):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The communications provider response was invalid."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_communications_error(result["error"])
            return None, None, None
        return user, authorization, result

    def send_admin_audit_error(self, error: dict) -> None:
        code = clean_text(error.get("code"), 80) or "ADMIN_AUDIT_PROVIDER_FAILED"
        status = ADMIN_AUDIT_ERROR_STATUS.get(code)
        if status is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The audit provider returned an unsupported error."),
            )
            return
        messages = {
            "AUDIT_FILTER_INVALID": "Choose supported audit filters.",
            "AUDIT_DATE_RANGE_INVALID": "Choose a valid audit date range.",
            "AUDIT_PAGE_INVALID": "Choose an audit page size from 1 to 100.",
            "AUDIT_CURSOR_INVALID": "Use a complete audit cursor.",
            "AUDIT_NOT_FOUND": "The audit event is unavailable.",
            "AUDIT_EXPORT_LIMIT_INVALID": "The audit export limit is invalid.",
            "AUDIT_EXPORT_REASON_INVALID": "Provide a supported audit export reason.",
            "AUDIT_EXPORT_IDEMPOTENCY_REQUIRED": "Provide a UUID request key for the audit export.",
            "AUDIT_EXPORT_IDEMPOTENCY_CONFLICT": "This request key is already bound to another audit export.",
        }
        self.send_auth_json(status, auth_error(code, messages[code]))

    def admin_audit_rpc(
        self,
        name: str,
        payload: dict | None = None,
        *,
        principal: tuple[dict, dict] | None = None,
    ) -> tuple[dict | None, dict | None, dict | None]:
        if principal is None:
            allowed, authorization = self.require_admin()
            user = getattr(self, "_admin_principal_user", None)
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
            self.send_admin_users_provider_error(status)
            return None, None, None
        if not isinstance(result, dict):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The audit provider response was invalid."),
            )
            return None, None, None
        if isinstance(result.get("error"), dict):
            self.send_admin_audit_error(result["error"])
            return None, None, None
        return user, authorization, result

    def request_rate_limit_ip(self) -> str:
        raw_ip = clean_text(self.client_address[0] if self.client_address else "", 128)
        forwarded = self.headers.get("X-Forwarded-For", "")
        if TRUST_REVERSE_PROXY and forwarded and "," not in forwarded:
            candidate = forwarded.strip()
            try:
                raw_ip = str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
        try:
            return str(ipaddress.ip_address(raw_ip))
        except ValueError:
            return "invalid"

    def sign_admin_work_asset(self, user: dict, asset: dict) -> dict | None:
        image_id = asset.get("image_id")
        owner_user_id = asset.get("owner_user_id")
        kind = asset.get("kind")
        storage_bucket = asset.get("storage_bucket")
        storage_key = asset.get("storage_key")
        expected_bucket = {"display": "image-display", "thumbnail": "image-thumbnails"}.get(kind)
        expected_prefix = f"{owner_user_id}/{image_id}/{kind}."
        if (
            not asset.get("preview_eligible")
            or asset.get("scan_status") != "clean"
            or asset.get("scan_result_code") != "clean"
            or asset.get("scan_policy_version") != "mt-asset-scan-2026-07-v1"
            or not asset.get("scan_completed_at")
            or not expected_bucket
            or storage_bucket != expected_bucket
            or not isinstance(storage_key, str)
            or not storage_key.startswith(expected_prefix)
        ):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works provider returned an unsafe preview asset."),
            )
            return None
        endpoint = f"object/sign/{quote(storage_bucket, safe='')}/{quote(storage_key, safe='/')}"
        status, signed = supabase_storage_request(
            endpoint,
            self.current_access_token(user),
            {"expiresIn": 10 * 60},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        expected_signed_path = f"/storage/v1/{endpoint}"
        if (
            status != HTTPStatus.OK
            or not signed_url
            or urlparse(signed_url).path != expected_signed_path
        ):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_ASSET_UNAVAILABLE", "A Works preview could not be loaded. Try again."),
            )
            return None
        return {
            "id": asset["id"],
            "image_id": image_id,
            "kind": kind,
            "mime_type": asset["mime_type"],
            "width": asset["width"],
            "height": asset["height"],
            "signed_url": signed_url,
            "expires_in": 10 * 60,
        }

    def present_admin_work_summary(self, user: dict, work: dict) -> dict | None:
        work.pop("_owner_user_id", None)
        latest_review = work.get("latest_review")
        if isinstance(latest_review, dict):
            latest_review.pop("_image_version_id", None)
        thumbnail_asset = work.pop("_thumbnail_asset", None)
        thumbnail = (
            self.sign_admin_work_asset(user, thumbnail_asset)
            if thumbnail_asset and thumbnail_asset.get("preview_eligible")
            else None
        )
        if thumbnail_asset and thumbnail is None:
            if thumbnail_asset.get("preview_eligible"):
                return None
        work["thumbnail"] = thumbnail
        return work

    def present_admin_work_detail(self, user: dict, work: dict) -> dict | None:
        work.pop("_owner_user_id", None)
        latest_review = work.get("latest_review")
        if isinstance(latest_review, dict):
            latest_review.pop("_image_version_id", None)
        display_asset = work.pop("_display_asset", None)
        thumbnail_asset = work.pop("_thumbnail_asset", None)
        display = (
            self.sign_admin_work_asset(user, display_asset)
            if display_asset and display_asset.get("preview_eligible")
            else None
        )
        if display_asset and display is None:
            if display_asset.get("preview_eligible"):
                return None
        thumbnail = (
            self.sign_admin_work_asset(user, thumbnail_asset)
            if thumbnail_asset and thumbnail_asset.get("preview_eligible")
            else None
        )
        if thumbnail_asset and thumbnail is None:
            if thumbnail_asset.get("preview_eligible"):
                return None
        work["display"] = display
        work["thumbnail"] = thumbnail
        return work

    def send_public_delivery_error(self) -> None:
        self.send_json(
            HTTPStatus.BAD_GATEWAY,
            {
                **auth_error(
                    "PUBLIC_DELIVERY_PROVIDER_FAILED",
                    "Published works are temporarily unavailable. Try again.",
                ),
                "source": "supabase-public",
            },
        )

    def public_delivery_rpc(self, name: str, payload: dict) -> dict | None:
        status, result = supabase_rest_request(
            f"rpc/{name}",
            SUPABASE_PUBLISHABLE_KEY,
            payload,
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_public_delivery_error()
            return None
        return result

    def sign_public_delivery_asset(self, asset: dict, cache: dict[str, dict]) -> dict | None:
        asset_id = asset["id"]
        if asset_id in cache:
            return dict(cache[asset_id])
        endpoint = (
            f"object/sign/{quote(asset['storage_bucket'], safe='')}/"
            f"{quote(asset['storage_key'], safe='/')}"
        )
        status, signed = supabase_storage_request(
            endpoint,
            SUPABASE_PUBLISHABLE_KEY,
            {"expiresIn": PUBLIC_DELIVERY_SIGNED_URL_TTL},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        if status != HTTPStatus.OK or not signed_url:
            return None
        safe_asset = {
            "id": asset_id,
            "image_id": asset["image_id"],
            "kind": asset["kind"],
            "mime_type": asset["mime_type"],
            "width": asset["width"],
            "height": asset["height"],
            "signed_url": signed_url,
            "expires_in": PUBLIC_DELIVERY_SIGNED_URL_TTL,
        }
        cache[asset_id] = safe_asset
        return dict(safe_asset)

    def sign_public_profile_avatar(self, asset: dict) -> str:
        endpoint = (
            f"object/sign/{quote(asset['storage_bucket'], safe='')}/"
            f"{quote(asset['storage_key'], safe='/')}"
        )
        status, signed = supabase_storage_request(
            endpoint,
            SUPABASE_PUBLISHABLE_KEY,
            {"expiresIn": PROFILE_AVATAR_SIGNED_URL_TTL},
        )
        signed_value = ""
        if isinstance(signed, dict):
            signed_value = signed.get("signedURL") or signed.get("signedUrl") or ""
        signed_url = self.absolute_storage_url(signed_value)
        expected = (asset["storage_bucket"], asset["storage_key"])
        if (
            status != HTTPStatus.OK
            or self.signed_profile_avatar_coordinates(signed_url, asset["owner_user_id"]) != expected
        ):
            return ""
        return signed_url

    def public_work_payload(self, work: dict, cache: dict[str, dict]) -> dict | None:
        display = self.sign_public_delivery_asset(work["display_asset"], cache)
        thumbnail = self.sign_public_delivery_asset(work["thumbnail_asset"], cache)
        if display is None or thumbnail is None:
            return None
        return {
            "id": work["id"],
            "title": work["title"],
            "caption": work["caption"],
            "description": work["description"],
            "alt_text": work["alt_text"],
            "tags": work["tags"],
            "content_type": work["content_category"],
            "content_category": work["content_category"],
            "captured_at": work["captured_at"],
            "location_name": work["location_name"],
            "public_exif": work["public_exif"],
            "published_at": work["published_at"],
            "uploaded_at": work["published_at"],
            "original_width": work["width"],
            "original_height": work["height"],
            "ratio_category_code": work["ratio_code"],
            "ratio_label": work["ratio_label"],
            "creator": work["creator"],
            "display": display,
            "thumbnail": thumbnail,
            "image_url": display["signed_url"],
            "display_url": display["signed_url"],
            "thumbnail_url": thumbnail["signed_url"],
            "visibility": "published",
            "source_type": "supabase_public",
        }

    def signed_public_works(self, result: dict, *, maximum: int = 100) -> dict | None:
        cleaned = clean_public_works_result(result, maximum=maximum)
        if cleaned is None:
            return None
        cache: dict[str, dict] = {}
        items = []
        for work in cleaned["items"]:
            item = self.public_work_payload(work, cache)
            if item is None:
                return None
            items.append(item)
        return {"items": items, "count": cleaned["count"], "source": "supabase-public"}

    def load_public_delivery_works(self, target_creator_slug: str | None, maximum: int) -> dict | None:
        items = []
        seen_ids = set()
        total_count = None
        offset = 0
        while len(items) < maximum:
            page_limit = min(100, maximum - len(items))
            result = self.public_delivery_rpc(
                "get_public_works",
                {
                    "target_creator_slug": target_creator_slug,
                    "page_limit": page_limit,
                    "page_offset": offset,
                },
            )
            if result is None:
                return None
            cleaned = clean_public_works_result(result, maximum=page_limit)
            if cleaned is None or (total_count is not None and cleaned["count"] != total_count):
                self.send_public_delivery_error()
                return None
            total_count = cleaned["count"] if total_count is None else total_count
            page_items = cleaned["items"]
            if any(item["id"] in seen_ids for item in page_items):
                self.send_public_delivery_error()
                return None
            items.extend(page_items)
            seen_ids.update(item["id"] for item in page_items)
            offset += len(page_items)
            if offset >= total_count:
                break
            if len(page_items) != page_limit:
                self.send_public_delivery_error()
                return None
        return {"items": items, "count": total_count or 0}

    def handle_public_creator_get(self, slug: str) -> None:
        normalized_slug = clean_text(slug, 96).lower()
        if not PUBLIC_CREATOR_SLUG_PATTERN.fullmatch(normalized_slug):
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("PUBLIC_CREATOR_NOT_FOUND", "This creator profile is unavailable."),
            )
            return
        if not auth_configured():
            self.handle_local_creator_get(normalized_slug)
            return
        result = self.public_delivery_rpc(
            "get_public_creator",
            {"target_creator_slug": normalized_slug},
        )
        if result is None:
            return
        if not result or isinstance(result.get("error"), dict):
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("PUBLIC_CREATOR_NOT_FOUND", "This creator profile is unavailable."),
            )
            return
        creator = clean_public_creator(result, normalized_slug)
        if creator is None:
            self.send_public_delivery_error()
            return
        avatar_result = self.public_delivery_rpc(
            "get_public_creator_avatar",
            {"target_creator_slug": normalized_slug},
        )
        if avatar_result is None:
            return
        if avatar_result:
            avatar_asset = clean_public_profile_avatar(avatar_result)
            if avatar_asset is None:
                self.send_public_delivery_error()
                return
            signed_avatar = self.sign_public_profile_avatar(avatar_asset)
            if not signed_avatar:
                self.send_public_delivery_error()
                return
            creator["avatar_url"] = signed_avatar
        if creator["work_count"] > len(creator["works"]):
            complete_works = self.load_public_delivery_works(
                normalized_slug,
                min(creator["work_count"], PUBLIC_DELIVERY_MAX_WORKS),
            )
            if complete_works is None:
                return
            if complete_works["count"] != creator["work_count"]:
                self.send_public_delivery_error()
                return
            creator["works"] = complete_works["items"]
        cache: dict[str, dict] = {}
        works = []
        for work in creator.pop("works"):
            item = self.public_work_payload(work, cache)
            if item is None:
                self.send_public_delivery_error()
                return
            works.append(item)
        cover_asset = creator.pop("cover_asset")
        cover = self.sign_public_delivery_asset(cover_asset, cache) if cover_asset else None
        if cover_asset and cover is None:
            self.send_public_delivery_error()
            return
        creator.pop("href", None)
        creator["cover"] = cover
        creator["works"] = works
        self.send_json(HTTPStatus.OK, {"creator": creator, "source": "supabase-public"})

    def handle_local_creator_get(self, slug: str) -> None:
        """Provide an explicit local preview without weakening configured delivery."""
        if slug != "mt-presence" or not ARCHIVE_DB_PATH.exists():
            self.send_json(
                HTTPStatus.NOT_FOUND,
                auth_error("PUBLIC_CREATOR_NOT_FOUND", "This creator profile is unavailable."),
            )
            return
        try:
            with sqlite3.connect(ARCHIVE_DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT * FROM archive_image_view
                    WHERE visibility = 'published'
                    ORDER BY sort_order ASC, uploaded_at DESC
                    LIMIT 100
                    """
                ).fetchall()
        except sqlite3.Error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to read the local creator preview."})
            return
        works = [
            work
            for work in (archive_image_payload(row) for row in rows)
            if work.get("image_url")
        ]
        creator_summary = {
            "slug": "mt-presence",
            "display_name": "MT Presence",
            "href": "/creators/mt-presence",
        }
        for work in works:
            work["creator"] = creator_summary
            work["alt_text"] = work.get("alt_text") or work.get("title") or "Published work"
        cover_url = works[0].get("image_url") if works else None
        self.send_json(
            HTTPStatus.OK,
            {
                "creator": {
                    "slug": "mt-presence",
                    "display_name": "MT Presence",
                    "professional_headline": "Photographic archive",
                    "company": None,
                    "city": None,
                    "country_code": None,
                    "bio": "An evolving archive of abstract and concrete photographic studies.",
                    "website_url": None,
                    "availability_status": "limited",
                    "instagram_url": None,
                    "linkedin_url": None,
                    "avatar_url": None,
                    "cover_url": cover_url,
                    "work_count": len(works),
                    "works": works,
                },
                "source": "local-sqlite-preview",
            },
        )

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

    def communication_principal_id(self, user: dict) -> str | None:
        try:
            return clean_uuid(user.get("id"), "communications user id")
        except ValueError:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The communications identity could not be verified."),
            )
            return None

    def parse_communications_cursor_query(
        self,
        parsed,
        *,
        supported_keys: set[str],
        default_limit: int,
        maximum_limit: int,
        time_key: str = "before",
    ) -> tuple[dict, int, str | None, str | None] | None:
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) - supported_keys or any(len(values) != 1 for values in query.values()):
            return None
        try:
            page_limit = int(single_query_value(query, "limit", str(default_limit)) or str(default_limit))
        except ValueError:
            return None
        cursor_time = single_query_value(query, time_key) or None
        cursor_id_raw = single_query_value(query, "before_id") or None
        cursor_id = None
        if cursor_id_raw:
            try:
                cursor_id = clean_uuid(cursor_id_raw, "cursor id")
            except ValueError:
                return None
        if (
            not 1 <= page_limit <= maximum_limit
            or (cursor_time is None) != (cursor_id is None)
            or (cursor_time is not None and clean_iso_timestamp(cursor_time) is None)
        ):
            return None
        return query, page_limit, cursor_time, cursor_id

    def handle_notifications_get(self, parsed) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        parsed_query = self.parse_communications_cursor_query(
            parsed,
            supported_keys={"limit", "before", "before_id"},
            default_limit=30,
            maximum_limit=COMMUNICATIONS_MAX_PAGE_SIZE,
        )
        if principal_id is None:
            return
        if parsed_query is None:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("NOTIFICATION_CURSOR_INVALID", "Choose supported notification pagination values."),
            )
            return
        _, page_limit, cursor_time, cursor_id = parsed_query
        _, _, result = self.communications_rpc(
            "list_my_notifications",
            {"page_limit": page_limit, "cursor_created_at": cursor_time, "cursor_id": cursor_id},
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_notification_list_result(result, principal_id, page_limit)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The notification response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_notification_unread_count_get(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        if principal_id is None:
            return
        _, _, result = self.communications_rpc(
            "get_my_notification_unread_count",
            {},
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_notification_count_result(result, principal_id)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The unread notification count was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_notifications_read(self) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        if principal_id is None:
            return
        body = self.read_json_body()
        if body is None:
            return
        notification_id = None
        if set(body) == {"notification_id"}:
            try:
                notification_id = clean_uuid(body.get("notification_id"), "notification id")
            except ValueError:
                notification_id = None
            if not notification_id:
                self.send_auth_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    auth_error("NOTIFICATION_READ_INVALID", "Choose a valid notification."),
                )
                return
            rpc_name = "mark_my_notification_read"
            rpc_payload = {"target_notification_id": notification_id}
        elif set(body) == {"all"} and body.get("all") is True:
            rpc_name = "mark_all_my_notifications_read"
            rpc_payload = {}
        else:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("NOTIFICATION_READ_INVALID", "Choose one notification or mark all as read."),
            )
            return
        _, _, result = self.communications_rpc(rpc_name, rpc_payload, principal=(user, authorization))
        if result is None:
            return
        response = clean_notification_read_result(result, principal_id, notification_id)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The notification update response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_inbox_list_get(self, parsed) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        parsed_query = self.parse_communications_cursor_query(
            parsed,
            supported_keys={"status", "limit", "before", "before_id"},
            default_limit=30,
            maximum_limit=COMMUNICATIONS_MAX_PAGE_SIZE,
        )
        if principal_id is None:
            return
        if parsed_query is None:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_CURSOR_INVALID", "Choose supported conversation filters and pagination values."),
            )
            return
        query, page_limit, cursor_time, cursor_id = parsed_query
        status_filter = single_query_value(query, "status", "all").lower() or "all"
        if status_filter not in COMMUNICATIONS_CONVERSATION_STATUSES:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_FILTER_INVALID", "Choose a supported conversation status."),
            )
            return
        _, _, result = self.communications_rpc(
            "list_my_conversations",
            {
                "status_filter": status_filter,
                "page_limit": page_limit,
                "cursor_last_message_at": cursor_time,
                "cursor_id": cursor_id,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_conversation_list_result(result, principal_id, page_limit)
        if response is None or (
            status_filter != "all" and any(item["status"] != status_filter for item in response["items"])
        ):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The inbox response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_inbox_detail_get(self, parsed, conversation_id: str) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        try:
            conversation_id = clean_uuid(conversation_id, "conversation id")
        except ValueError:
            self.send_auth_json(HTTPStatus.NOT_FOUND, auth_error("CONVERSATION_NOT_FOUND", "The conversation is unavailable."))
            return
        parsed_query = self.parse_communications_cursor_query(
            parsed,
            supported_keys={"limit", "before", "before_id"},
            default_limit=100,
            maximum_limit=COMMUNICATIONS_MESSAGE_MAX_PAGE_SIZE,
        )
        if principal_id is None:
            return
        if parsed_query is None:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_CURSOR_INVALID", "Choose supported message pagination values."),
            )
            return
        _, page_limit, cursor_time, cursor_id = parsed_query
        _, _, result = self.communications_rpc(
            "get_my_conversation",
            {
                "target_conversation_id": conversation_id,
                "page_limit": page_limit,
                "cursor_created_at": cursor_time,
                "cursor_id": cursor_id,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_conversation_detail_result(result, principal_id, conversation_id, page_limit)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The conversation response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_inbox_reply(self, conversation_id: str) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        try:
            conversation_id = clean_uuid(conversation_id, "conversation id")
        except ValueError:
            self.send_auth_json(HTTPStatus.NOT_FOUND, auth_error("CONVERSATION_NOT_FOUND", "The conversation is unavailable."))
            return
        if principal_id is None:
            return
        body = self.read_json_body()
        if body is None:
            return
        expected_version = body.get("expected_version")
        message = body.get("message")
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "message idempotency key")
        except ValueError:
            idempotency_key = ""
        if (
            set(body) != {"expected_version", "message", "idempotency_key"}
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not isinstance(message, str)
            or not 1 <= len(message.strip()) <= 5000
            or not idempotency_key
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_MESSAGE_INVALID", "Provide a reply, current version, and UUID request key."),
            )
            return
        _, _, result = self.communications_rpc(
            "reply_to_conversation",
            {
                "target_conversation_id": conversation_id,
                "expected_version": expected_version,
                "message_body": message.strip(),
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_conversation_reply_result(result, principal_id, conversation_id, expected_version)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The reply response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_inbox_read(self, conversation_id: str) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        principal_id = self.communication_principal_id(user)
        try:
            conversation_id = clean_uuid(conversation_id, "conversation id")
        except ValueError:
            self.send_auth_json(HTTPStatus.NOT_FOUND, auth_error("CONVERSATION_NOT_FOUND", "The conversation is unavailable."))
            return
        if principal_id is None:
            return
        body = self.read_json_body()
        if body is None:
            return
        if body:
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_READ_TARGET_INVALID", "Use an empty JSON object to mark the latest message as read."),
            )
            return
        _, _, result = self.communications_rpc(
            "mark_my_conversation_read",
            {"target_conversation_id": conversation_id, "target_message_id": None},
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_conversation_read_result(result, principal_id, conversation_id)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The read receipt response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_inbox_status(self, conversation_id: str) -> None:
        user, authorization = self.require_account_session()
        if not user or not authorization:
            return
        try:
            conversation_id = clean_uuid(conversation_id, "conversation id")
        except ValueError:
            self.send_auth_json(HTTPStatus.NOT_FOUND, auth_error("CONVERSATION_NOT_FOUND", "The conversation is unavailable."))
            return
        body = self.read_json_body()
        if body is None:
            return
        expected_version = body.get("expected_version")
        target_status = body.get("status")
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "conversation status idempotency key")
        except ValueError:
            idempotency_key = ""
        if (
            set(body) != {"status", "expected_version", "idempotency_key"}
            or target_status not in {"open", "closed"}
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not idempotency_key
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("CONVERSATION_STATUS_INVALID", "Choose open or closed and provide the current version and UUID request key."),
            )
            return
        _, _, result = self.communications_rpc(
            "set_my_conversation_status",
            {
                "target_conversation_id": conversation_id,
                "expected_version": expected_version,
                "target_status": target_status,
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_conversation_status_result(result, conversation_id, target_status, expected_version)
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The conversation status response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_project_inquiry_create(self) -> None:
        body = self.read_json_body(INQUIRY_BODY_MAX_BYTES)
        if body is None:
            return
        allowed_keys = {
            "sender_name", "sender_email", "inquiry_type", "organization", "project_use", "timeline",
            "budget_range", "message", "website", "work_ids", "idempotency_key",
        }
        required_keys = {"sender_name", "sender_email", "inquiry_type", "project_use", "message", "website", "idempotency_key"}
        if set(body) - allowed_keys or not required_keys.issubset(body) or not isinstance(body.get("website"), str):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("INQUIRY_VALIDATION_FAILED", "Review the inquiry fields and try again."),
            )
            return
        if body["website"].strip():
            self.send_json(
                HTTPStatus.ACCEPTED,
                {"reference": f"INQ-{secrets.token_hex(6).upper()}", "status": "received"},
            )
            return
        sender_name = body.get("sender_name")
        sender_email = body.get("sender_email")
        inquiry_type = body.get("inquiry_type")
        project_use = body.get("project_use")
        message = body.get("message")
        optional_values = {key: body.get(key) for key in ("organization", "timeline", "budget_range")}
        work_ids = body.get("work_ids", [])
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "inquiry idempotency key")
        except ValueError:
            idempotency_key = ""
        normalized_email = sender_email.strip().lower() if isinstance(sender_email, str) else ""
        cleaned_work_ids = []
        if isinstance(work_ids, list) and len(work_ids) <= 10:
            for work_id in work_ids:
                try:
                    cleaned_work_ids.append(clean_uuid(work_id, "inquiry work id"))
                except ValueError:
                    cleaned_work_ids = []
                    work_ids = None
                    break
        else:
            work_ids = None
        optional_valid = all(
            isinstance(value, str) and len(value.strip()) <= maximum
            for (key, value), maximum in zip(optional_values.items(), (180, 120, 120))
            if value is not None
        )
        if (
            not isinstance(sender_name, str)
            or not 1 <= len(sender_name.strip()) <= 120
            or not valid_email_address(normalized_email)
            or not isinstance(inquiry_type, str)
            or inquiry_type.strip().lower() not in COMMUNICATIONS_INQUIRY_TYPES
            or not isinstance(project_use, str)
            or not 5 <= len(project_use.strip()) <= 280
            or not isinstance(message, str)
            or not 10 <= len(message.strip()) <= 5000
            or not optional_valid
            or work_ids is None
            or len(set(cleaned_work_ids)) != len(cleaned_work_ids)
            or not idempotency_key
        ):
            self.send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("INQUIRY_VALIDATION_FAILED", "Review the inquiry fields and try again."),
            )
            return

        user = None
        authorization = None
        initiator_id = None
        access_token = SUPABASE_PUBLISHABLE_KEY
        has_session = bool(self.cookie_value(ACCESS_COOKIE) or self.cookie_value(REFRESH_COOKIE))
        if has_session:
            status, user = self.current_auth_user()
            if status != HTTPStatus.OK:
                self.send_current_user_error(status, user)
                return
            if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
                self.send_json(
                    HTTPStatus.FORBIDDEN,
                    auth_error("RECOVERY_SESSION_RESTRICTED", "Finish resetting your password before sending an inquiry."),
                )
                return
            authz_status, authorization = self.current_authorization(user)
            if authz_status != HTTPStatus.OK or not isinstance(authorization, dict):
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("AUTHORIZATION_FAILED", "Unable to verify inquiry access. Try again."),
                )
                return
            roles = set(authorization.get("roles") or [])
            if authorization.get("account_status") != "active":
                self.send_json(HTTPStatus.FORBIDDEN, auth_error("ACCOUNT_RESTRICTED", "This account cannot send inquiries."))
                return
            if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
                self.send_json(HTTPStatus.FORBIDDEN, auth_error("MFA_REQUIRED", "Complete multi-factor authentication to continue."))
                return
            initiator_id = self.communication_principal_id(user)
            if initiator_id is None:
                return
            account_email = clean_text(user.get("email"), 180).lower()
            if not valid_email_address(account_email) or normalized_email != account_email:
                self.send_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    auth_error("INQUIRY_VALIDATION_FAILED", "Use the email address for the signed-in account."),
                )
                return
            access_token = self.current_access_token(user)

        if not consume_inquiry_rate_limit(self.request_rate_limit_ip(), normalized_email):
            self.send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                auth_error("INQUIRY_RATE_LIMITED", "Too many recent inquiries. Try again later."),
            )
            return
        status, result = supabase_rest_request(
            "rpc/create_project_inquiry",
            access_token,
            {
                "sender_name": sender_name.strip(),
                "sender_email": normalized_email,
                "inquiry_type": inquiry_type.strip().lower(),
                "organization": optional_values["organization"].strip() if optional_values["organization"] else None,
                "project_use": project_use.strip(),
                "timeline": optional_values["timeline"].strip() if optional_values["timeline"] else None,
                "budget_range": optional_values["budget_range"].strip() if optional_values["budget_range"] else None,
                "message_body": message.strip(),
                "website": "",
                "work_ids": cleaned_work_ids,
                "idempotency_key": idempotency_key,
            },
        )
        if status != HTTPStatus.OK or not isinstance(result, dict):
            self.send_communications_provider_error(status)
            return
        if isinstance(result.get("error"), dict):
            self.send_communications_error(result["error"])
            return
        response = clean_project_inquiry_result(result, initiator_id)
        if response is None:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("COMMUNICATIONS_PROVIDER_FAILED", "The inquiry response was invalid."),
            )
            return
        if initiator_id is None:
            self.send_json(HTTPStatus.ACCEPTED, {"reference": response["reference"], "status": response["status"]})
            return
        self.send_auth_json(HTTPStatus.ACCEPTED, response)

    def handle_admin_audit_list_get(self, parsed) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        principal = clean_admin_user_principal(user, authorization)
        parsed_query = self.parse_communications_cursor_query(
            parsed,
            supported_keys={"result", "target_type", "action", "actor", "request_id", "from", "to", "limit", "before", "before_id"},
            default_limit=50,
            maximum_limit=COMMUNICATIONS_MAX_PAGE_SIZE,
        )
        if principal is None:
            self.send_auth_json(HTTPStatus.BAD_GATEWAY, auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The administrator identity was invalid."))
            return
        if parsed_query is None:
            self.send_auth_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUDIT_CURSOR_INVALID", "Choose supported audit filters and pagination values."))
            return
        query, page_limit, cursor_time, cursor_id = parsed_query
        result_filter = single_query_value(query, "result", "all").lower() or "all"
        target_filter = single_query_value(query, "target_type", "all").lower() or "all"
        action_value = single_query_value(query, "action", "all").lower() or "all"
        action_filter = "" if action_value == "all" else action_value
        actor_filter = single_query_value(query, "actor", "all").lower() or "all"
        request_value = single_query_value(query, "request_id", "all") or "all"
        request_filter = "" if request_value.lower() == "all" else request_value
        created_from = single_query_value(query, "from") or None
        created_to = single_query_value(query, "to") or None
        default_now = datetime.now(timezone.utc)
        created_from = created_from or (default_now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        created_to = created_to or default_now.isoformat().replace("+00:00", "Z")
        actor_valid = actor_filter == "all"
        if not actor_valid:
            try:
                actor_filter = clean_uuid(actor_filter, "audit actor filter")
                actor_valid = True
            except ValueError:
                actor_valid = False
        dates_valid = (
            (created_from is None or clean_iso_timestamp(created_from) is not None)
            and (created_to is None or clean_iso_timestamp(created_to) is not None)
        )
        if dates_valid and created_from and created_to:
            dates_valid = datetime.fromisoformat(created_from.replace("Z", "+00:00")) <= datetime.fromisoformat(created_to.replace("Z", "+00:00"))
        if (
            result_filter not in {"all", "success", "failure"}
            or (target_filter != "all" and not re.fullmatch(r"[a-z0-9_]{1,64}", target_filter))
            or (action_filter and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", action_filter))
            or not actor_valid
            or (request_filter and not re.fullmatch(r"[A-Za-z0-9:_-]{1,180}", request_filter))
        ):
            self.send_auth_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUDIT_FILTER_INVALID", "Choose supported audit filters."))
            return
        if not dates_valid:
            self.send_auth_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUDIT_DATE_RANGE_INVALID", "Choose a valid audit date range."))
            return
        _, _, result = self.admin_audit_rpc(
            "admin_list_audit_logs",
            {
                "result_filter": result_filter,
                "target_type_filter": target_filter,
                "action_filter": action_filter,
                "actor_filter": actor_filter,
                "request_id_filter": request_filter,
                "created_from": created_from,
                "created_to": created_to,
                "page_limit": page_limit,
                "cursor_created_at": cursor_time,
                "cursor_id": cursor_id,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_admin_audit_list_result(result, principal[0], principal[1], page_limit)
        if response is None:
            self.send_auth_json(HTTPStatus.BAD_GATEWAY, auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The audit response was inconsistent."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_audit_detail_get(self, audit_id: str) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        principal = clean_admin_user_principal(user, authorization)
        try:
            audit_id = clean_uuid(audit_id, "audit id")
        except ValueError:
            self.send_auth_json(HTTPStatus.NOT_FOUND, auth_error("AUDIT_NOT_FOUND", "The audit event is unavailable."))
            return
        if principal is None:
            self.send_auth_json(HTTPStatus.BAD_GATEWAY, auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The administrator identity was invalid."))
            return
        _, _, result = self.admin_audit_rpc(
            "admin_get_audit_log",
            {"target_audit_id": audit_id},
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_admin_audit_detail_result(result, principal[0], principal[1], audit_id)
        if response is None:
            self.send_auth_json(HTTPStatus.BAD_GATEWAY, auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The audit detail response was inconsistent."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_audit_export(self) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        principal = clean_admin_user_principal(user, authorization)
        body = self.read_json_body()
        if body is None:
            return
        expected_keys = {"result", "target_type", "action", "actor", "request_id", "from", "to", "reason_code", "idempotency_key"}
        result_filter = body.get("result")
        target_filter = body.get("target_type")
        action_value = body.get("action")
        actor_filter = body.get("actor") or "all"
        request_value = body.get("request_id") or "all"
        created_from = body.get("from") or None
        created_to = body.get("to") or None
        default_now = datetime.now(timezone.utc)
        created_from = created_from or (default_now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        created_to = created_to or default_now.isoformat().replace("+00:00", "Z")
        reason_code = body.get("reason_code")
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "audit export idempotency key")
        except ValueError:
            idempotency_key = ""
        action_filter = "" if action_value == "all" else action_value
        request_filter = "" if request_value == "all" else request_value
        actor_valid = actor_filter == "all"
        if not actor_valid and isinstance(actor_filter, str):
            try:
                actor_filter = clean_uuid(actor_filter, "audit actor filter")
                actor_valid = True
            except ValueError:
                actor_valid = False
        dates_valid = (
            (created_from is None or clean_iso_timestamp(created_from) is not None)
            and (created_to is None or clean_iso_timestamp(created_to) is not None)
        )
        if dates_valid and created_from and created_to:
            dates_valid = datetime.fromisoformat(created_from.replace("Z", "+00:00")) <= datetime.fromisoformat(created_to.replace("Z", "+00:00"))
        if (
            principal is None
            or set(body) != expected_keys
            or result_filter not in {"all", "success", "failure"}
            or not isinstance(target_filter, str)
            or (target_filter != "all" and not re.fullmatch(r"[a-z0-9_]{1,64}", target_filter))
            or not isinstance(action_value, str)
            or (action_filter and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", action_filter))
            or not actor_valid
            or not isinstance(request_value, str)
            or (request_filter and not re.fullmatch(r"[A-Za-z0-9:_-]{1,180}", request_filter))
            or not isinstance(reason_code, str)
            or reason_code not in {"operational_review", "security_investigation", "compliance_request"}
            or not idempotency_key
        ):
            self.send_auth_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUDIT_FILTER_INVALID", "Provide supported export filters, reason, and UUID request key."))
            return
        if not dates_valid:
            self.send_auth_json(HTTPStatus.UNPROCESSABLE_ENTITY, auth_error("AUDIT_DATE_RANGE_INVALID", "Choose a valid audit date range."))
            return
        _, _, result = self.admin_audit_rpc(
            "admin_export_audit_logs",
            {
                "result_filter": result_filter,
                "target_type_filter": target_filter,
                "action_filter": action_filter,
                "actor_filter": actor_filter,
                "request_id_filter": request_filter,
                "created_from": created_from,
                "created_to": created_to,
                "export_limit": 1000,
                "reason_code": reason_code,
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_admin_audit_export_result(result, principal[0], principal[1], reason_code)
        if response is None:
            self.send_auth_json(HTTPStatus.BAD_GATEWAY, auth_error("ADMIN_AUDIT_PROVIDER_FAILED", "The audit export response was inconsistent."))
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_works_list_get(self, parsed) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        supported_keys = {"q", "status", "sort", "limit", "offset"}
        status_filter = single_query_value(query, "status", "all").lower() or "all"
        sort_code = single_query_value(query, "sort", "updated_desc").lower() or "updated_desc"
        search_query = single_query_value(query, "q")
        try:
            page_size = int(single_query_value(query, "limit", "30") or "30")
            page_offset = int(single_query_value(query, "offset", "0") or "0")
        except ValueError:
            page_size = 0
            page_offset = -1
        if (
            set(query) - supported_keys
            or any(len(values) != 1 for values in query.values())
            or status_filter not in ADMIN_WORKS_FILTER_STATUSES
            or sort_code not in ADMIN_WORKS_SORT_CODES
            or len(search_query) > 200
            or not 1 <= page_size <= ADMIN_WORKS_MAX_PAGE_SIZE
            or not 0 <= page_offset <= 10_000
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("ADMIN_FILTER_INVALID", "Choose supported Works filters, sorting, and pagination values."),
            )
            return
        _, _, result = self.admin_works_rpc(
            "admin_list_images",
            {
                "status_filter": status_filter,
                "search_query": search_query,
                "sort_code": sort_code,
                "page_size": page_size,
                "page_offset": page_offset,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        principal = clean_admin_work_principal(user, authorization)
        response = clean_admin_work_list_result(
            result,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if (
            response is None
            or response["pagination"]["limit"] != page_size
            or response["pagination"]["offset"] != page_offset
            or response["pagination"]["total"] != response["counts"][status_filter]
            or (status_filter != "all" and any(item["publication_status"] != status_filter for item in response["items"]))
        ):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works inventory response was inconsistent."),
            )
            return
        for work in response["items"]:
            if self.present_admin_work_summary(user, work) is None:
                return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_work_detail_get(self, image_id: str) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        try:
            image_id = clean_uuid(image_id, "admin work id")
        except ValueError:
            self.send_auth_json(
                HTTPStatus.NOT_FOUND,
                auth_error("ADMIN_IMAGE_NOT_FOUND", "The work is unavailable."),
            )
            return
        _, _, result = self.admin_works_rpc(
            "admin_get_image",
            {"target_image_id": image_id},
            principal=(user, authorization),
        )
        if result is None:
            return
        principal = clean_admin_work_principal(user, authorization)
        response = clean_admin_work_detail_result(
            result,
            image_id,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if response is None or self.present_admin_work_detail(user, response["work"]) is None:
            if response is None:
                self.send_auth_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works detail response was invalid."),
                )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_work_mutation(self, image_id: str, action: str) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        try:
            image_id = clean_uuid(image_id, "admin work id")
        except ValueError:
            self.send_auth_json(
                HTTPStatus.NOT_FOUND,
                auth_error("ADMIN_IMAGE_NOT_FOUND", "The work is unavailable."),
            )
            return
        body = self.read_json_body()
        if body is None:
            return
        required_keys = {"expected_version", "idempotency_key", "reason_code", "public_message"}
        allowed_keys = required_keys.union({"internal_note"})
        expected_version = body.get("expected_version")
        reason_code = body.get("reason_code")
        public_message = body.get("public_message")
        internal_note = body.get("internal_note", "")
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "governance idempotency key")
        except ValueError:
            idempotency_key = ""
        normalized_reason = reason_code.strip().lower() if isinstance(reason_code, str) else ""
        normalized_message = public_message.strip() if isinstance(public_message, str) else ""
        normalized_internal_note = internal_note.strip() if isinstance(internal_note, str) else ""
        expected_reasons = (
            ADMIN_WORKS_TAKEDOWN_REASON_CODES if action == "takedown" else ADMIN_WORKS_RESTORE_REASON_CODES
        )
        if (
            action not in ADMIN_WORKS_ACTIONS
            or set(body) - allowed_keys
            or not required_keys.issubset(body)
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not idempotency_key
            or normalized_reason not in expected_reasons
            or not 5 <= len(normalized_message) <= 1000
            or not isinstance(internal_note, str)
            or len(normalized_internal_note) > 2000
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "ADMIN_GOVERNANCE_VALIDATION_FAILED",
                    "Provide the current work version, a supported reason, and a user-safe message.",
                ),
            )
            return
        _, _, result = self.admin_works_rpc(
            "admin_govern_image",
            {
                "target_image_id": image_id,
                "target_expected_version": expected_version,
                "action_code": action,
                "submitted_reason_code": normalized_reason,
                "submitted_user_message": normalized_message,
                "submitted_internal_note": normalized_internal_note,
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        principal = clean_admin_work_principal(user, authorization)
        response = clean_admin_work_mutation_result(
            result,
            image_id,
            action,
            normalized_reason,
            normalized_message,
            expected_version,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_WORKS_PROVIDER_FAILED", "The Works governance response was invalid."),
            )
            return
        if self.present_admin_work_summary(user, response["work"]) is None:
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_users_list_get(self, parsed) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        supported_keys = {"q", "status", "role", "sort", "limit", "offset"}
        status_filter = single_query_value(query, "status", "all").lower() or "all"
        role_filter = single_query_value(query, "role", "all").lower() or "all"
        sort_code = single_query_value(query, "sort", "updated_desc").lower() or "updated_desc"
        search_query = single_query_value(query, "q")
        try:
            page_size = int(single_query_value(query, "limit", "30") or "30")
            page_offset = int(single_query_value(query, "offset", "0") or "0")
        except ValueError:
            page_size = 0
            page_offset = -1
        if (
            set(query) - supported_keys
            or any(len(values) != 1 for values in query.values())
            or status_filter not in ADMIN_USERS_FILTER_STATUSES
            or role_filter not in ADMIN_USERS_FILTER_ROLES
            or sort_code not in ADMIN_USERS_SORT_CODES
            or len(search_query) > 160
            or not 1 <= page_size <= ADMIN_USERS_MAX_PAGE_SIZE
            or not 0 <= page_offset <= 10_000
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error("ADMIN_USER_FILTER_INVALID", "Choose supported user filters, sorting, and pagination values."),
            )
            return
        _, _, result = self.admin_users_rpc(
            "admin_list_users",
            {
                "status_filter": status_filter,
                "role_filter": role_filter,
                "search_query": search_query,
                "sort_code": sort_code,
                "page_size": page_size,
                "page_offset": page_offset,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        principal = clean_admin_user_principal(user, authorization)
        response = clean_admin_user_list_result(
            result,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if (
            response is None
            or response["pagination"]["limit"] != page_size
            or response["pagination"]["offset"] != page_offset
            or (status_filter != "all" and any(item["account_status"] != status_filter for item in response["items"]))
            or (role_filter != "all" and any(role_filter not in item["roles"] for item in response["items"]))
        ):
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user directory response was inconsistent."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_user_detail_get(self, target_user_id: str) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        try:
            target_user_id = clean_uuid(target_user_id, "admin user id")
        except ValueError:
            self.send_auth_json(
                HTTPStatus.NOT_FOUND,
                auth_error("ADMIN_USER_NOT_FOUND", "The user is unavailable."),
            )
            return
        _, _, result = self.admin_users_rpc(
            "admin_get_user",
            {"target_user_id": target_user_id},
            principal=(user, authorization),
        )
        if result is None:
            return
        principal = clean_admin_user_principal(user, authorization)
        response = clean_admin_user_detail_result(
            result,
            target_user_id,
            expected_actor_id=principal[0] if principal else "",
            expected_roles=principal[1] if principal else set(),
        ) if principal else None
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user detail response was invalid."),
            )
            return
        self.send_auth_json(HTTPStatus.OK, response)

    def handle_admin_user_mutation(self, target_user_id: str, endpoint: str) -> None:
        allowed, authorization = self.require_admin()
        user = getattr(self, "_admin_principal_user", None)
        if not allowed or not user or not authorization:
            return
        try:
            target_user_id = clean_uuid(target_user_id, "admin user id")
        except ValueError:
            self.send_auth_json(
                HTTPStatus.NOT_FOUND,
                auth_error("ADMIN_USER_NOT_FOUND", "The user is unavailable."),
            )
            return
        body = self.read_json_body()
        if body is None:
            return
        base_keys = {"action", "reason_code", "expected_version", "idempotency_key"}
        required_keys = base_keys.union({"target_role"}) if endpoint == "roles" else base_keys
        action = clean_text(body.get("action"), 40).lower()
        reason_code = clean_text(body.get("reason_code"), 80).lower()
        expected_version = body.get("expected_version")
        target_role = clean_text(body.get("target_role"), 40).lower() or None
        try:
            idempotency_key = clean_uuid(body.get("idempotency_key"), "user governance idempotency key")
        except ValueError:
            idempotency_key = ""
        endpoint_actions = {
            "status": {"suspend", "reactivate"},
            "roles": {"grant_role", "revoke_role"},
            "revoke-sessions": {"revoke_sessions"},
        }
        if (
            endpoint not in endpoint_actions
            or set(body) != required_keys
            or not isinstance(body.get("action"), str)
            or not isinstance(body.get("reason_code"), str)
            or (endpoint == "roles" and not isinstance(body.get("target_role"), str))
            or action not in endpoint_actions[endpoint]
            or reason_code not in ADMIN_USERS_REASON_CODES.get(action, set())
            or isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not idempotency_key
            or (endpoint == "roles" and target_role not in ADMIN_USERS_MUTABLE_ROLES)
            or (endpoint != "roles" and target_role is not None)
        ):
            self.send_auth_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                auth_error(
                    "ADMIN_USER_VALIDATION_FAILED",
                    "Provide the current user version, a UUID request key, and a supported action and reason.",
                ),
            )
            return
        principal = clean_admin_user_principal(user, authorization)
        if principal is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The administrator identity could not be verified."),
            )
            return
        if target_user_id == principal[0]:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ADMIN_USER_SELF_ACTION_FORBIDDEN", "Use Account Settings for your own account and sessions."),
            )
            return
        if endpoint == "roles" and "super_admin" not in principal[1]:
            self.send_auth_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ADMIN_USER_ROLE_FORBIDDEN", "Only a Super Admin can manage supported roles."),
            )
            return
        _, _, result = self.admin_users_rpc(
            "admin_govern_user",
            {
                "target_user_id": target_user_id,
                "expected_version": expected_version,
                "action": action,
                "target_role": target_role,
                "reason_code": reason_code,
                "idempotency_key": idempotency_key,
            },
            principal=(user, authorization),
        )
        if result is None:
            return
        response = clean_admin_user_mutation_result(
            result,
            target_user_id,
            action,
            target_role,
            reason_code,
            expected_version,
            expected_actor_id=principal[0],
            expected_roles=principal[1],
        )
        if response is None:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user governance response was invalid."),
            )
            return
        governed_user = response["user"]
        state_valid = (
            (action == "suspend" and governed_user["account_status"] == "suspended")
            or (action == "reactivate" and governed_user["account_status"] == "active")
            or (action == "grant_role" and target_role in governed_user["roles"])
            or (action == "revoke_role" and target_role not in governed_user["roles"])
            or (action == "revoke_sessions" and response["action"]["provider_action_required"] is True)
        )
        if not state_valid:
            self.send_auth_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("ADMIN_USERS_PROVIDER_FAILED", "The user governance state was inconsistent."),
            )
            return
        self.send_auth_json(
            HTTPStatus.ACCEPTED if action == "revoke_sessions" else HTTPStatus.OK,
            response,
        )

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
        actor = response["actor"]
        submission = response["submission"]
        assigned_reviewer = submission.get("assigned_reviewer") or {}
        can_read_original = (
            "reviewer" in actor["roles"]
            and assigned_reviewer.get("id") == actor["id"]
            and submission["status"] in REVIEW_OPEN_STATUSES
            and response["owner"]["id"] != actor["id"]
        )
        review_assets = [
            asset
            for asset in response["assets"]
            if asset.get("kind") != "original" or can_read_original
        ]
        if any(
            asset.get("scan_status") != "clean"
            or asset.get("scan_policy_version") != REVIEW_ASSET_SCAN_POLICY_VERSION
            for asset in review_assets
        ):
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("REVIEW_PROVIDER_FAILED", "The review detail returned an unsafe private asset."),
            )
            return
        signed_assets = []
        for asset in review_assets:
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
        self_publish = action == "super-admin-self-publish"
        decision = {
            "request-changes": "request_changes",
            "reject": "reject",
            "approve": "approve",
            "approve-and-publish": "approve_and_publish",
            "super-admin-self-publish": "approve_and_publish",
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
        if self_publish and "super_admin" not in roles:
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error(
                    "REVIEW_SELF_PUBLISH_FORBIDDEN",
                    "Only a Super Admin may use the audited self-publish action.",
                ),
            )
            return
        if not self_publish and decision == "approve_and_publish" and not roles.intersection({"admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("REVIEW_PUBLISH_ADMIN_REQUIRED", "Administrator approval is required to publish."),
            )
            return
        rpc_payload = {
            "submission_id": submission_id,
            "expected_lock_version": expected_version,
            "reason_codes": reason_codes,
            "user_message": user_message.strip(),
            "internal_note": internal_note.strip(),
            "checklist_result": checklist,
            "idempotency_key": idempotency_key,
        }
        if not self_publish:
            rpc_payload["decision"] = decision
        _, _, result = self.review_rpc(
            "review_super_admin_self_publish" if self_publish else "review_decide_submission",
            rpc_payload,
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

        public_status_code, public_status_result = supabase_rest_request(
            "rpc/get_my_public_delivery_status",
            self.current_access_token(user),
            {},
        )
        if public_status_code == HTTPStatus.OK:
            public_capability = clean_public_delivery_status(public_status_result)
            if public_capability is None:
                self.send_json(
                    HTTPStatus.BAD_GATEWAY,
                    auth_error("DASHBOARD_PROVIDER_FAILED", "Public profile status could not be verified. Try again."),
                )
                return
            response["capabilities"]["public_portfolio"] = public_capability
        elif public_status_code != HTTPStatus.NOT_FOUND:
            self.send_json(
                HTTPStatus.BAD_GATEWAY,
                auth_error("DASHBOARD_PROVIDER_FAILED", "Public profile status could not be loaded. Try again."),
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
        self._admin_principal_user = None
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            self.send_current_user_error(status, user)
            return False, None
        if session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery"):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("RECOVERY_SESSION_RESTRICTED", "Finish resetting your password before opening administrator tools."),
            )
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
        self._admin_principal_user = user
        return True, authorization

    def serve_admin_works_page(self, next_path: str = "/admin/works") -> None:
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
                auth_error("AUTHORIZATION_FAILED", "Unable to verify administrator access. Try again."),
            )
            return
        roles = set(authorization.get("roles") or [])
        if authorization.get("account_status") != "active" or not roles.intersection({"admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ADMIN_REQUIRED", "You do not have access to Works governance."),
            )
            return
        if authorization.get("aal") != "aal2":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/mfa?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.serve_header_html("admin-works.html", user=user, authorization=authorization)

    def serve_admin_users_page(self, next_path: str = "/admin/users") -> None:
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
                auth_error("AUTHORIZATION_FAILED", "Unable to verify administrator access. Try again."),
            )
            return
        roles = set(authorization.get("roles") or [])
        if authorization.get("account_status") != "active" or not roles.intersection({"admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ADMIN_REQUIRED", "You do not have access to user administration."),
            )
            return
        if authorization.get("aal") != "aal2":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/mfa?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.serve_header_html("admin-users.html", user=user, authorization=authorization)

    def serve_account_communications_page(self, filename: str, next_path: str) -> None:
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
                auth_error("AUTHORIZATION_FAILED", "Unable to verify communications access. Try again."),
            )
            return
        if authorization.get("account_status") != "active":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ACCOUNT_RESTRICTED", "This account cannot access communications."),
            )
            return
        roles = set(authorization.get("roles") or [])
        if roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/mfa?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.serve_header_html(filename, user=user, authorization=authorization)

    def serve_admin_audit_page(self, next_path: str = "/admin/audit") -> None:
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
                auth_error("AUTHORIZATION_FAILED", "Unable to verify administrator access. Try again."),
            )
            return
        roles = set(authorization.get("roles") or [])
        if authorization.get("account_status") != "active" or not roles.intersection({"admin", "super_admin"}):
            self.send_json(
                HTTPStatus.FORBIDDEN,
                auth_error("ADMIN_REQUIRED", "You do not have access to the audit log."),
            )
            return
        if authorization.get("aal") != "aal2":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/auth/mfa?{urlencode({'next': next_path})}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.serve_header_html("admin-audit.html", user=user, authorization=authorization)

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
        self.serve_header_html("admin-reviews.html", user=user, authorization=authorization)

    def has_admin_access_silently(self) -> bool:
        status, user = self.current_auth_user()
        if status != HTTPStatus.OK:
            return False
        status, authorization = self.current_authorization(user)
        if status != HTTPStatus.OK or authorization.get("account_status") != "active":
            return False
        roles = set(authorization.get("roles") or [])
        return bool(roles.intersection({"admin", "super_admin"})) and authorization.get("aal") == "aal2"

    def read_json_body(self, max_bytes: int = 128 * 1024) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length."})
            return None
        if length <= 0:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body is required."})
            return None
        if length > max_bytes:
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
        query = parse_qs(parsed.query)
        visibility = single_query_value(query, "visibility").lower()
        local_preview = (
            LOCAL_ARCHIVE_PREVIEW
            and RUNTIME_ENVIRONMENT == "development"
            and self.is_loopback_request()
            and visibility in {"", "published"}
        )
        if auth_configured() and visibility in {"", "published"} and not local_preview:
            self.handle_public_works_get(query)
            return

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
            filters, params, limit = archive_query_filters(query)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if local_preview:
            filters.append("source_type = ?")
            params.append("local_sample")

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
        if visibility in {"", "published"}:
            creator = {
                "slug": "mt-presence",
                "display_name": "MT Presence",
                "href": "/creators/mt-presence",
            }
            for item in items:
                item["creator"] = creator
                item["alt_text"] = item.get("alt_text") or item.get("title") or "Published work"
        self.send_json(
            HTTPStatus.OK,
            {
                "items": items,
                "count": len(items),
                "source": "local-sqlite-preview" if local_preview else "local-sqlite",
            },
        )

    def handle_public_works_get(self, query: dict) -> None:
        try:
            page_limit = int(single_query_value(query, "limit") or str(PUBLIC_DELIVERY_MAX_WORKS))
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Archive limit must be an integer."})
            return
        if not 1 <= page_limit <= PUBLIC_DELIVERY_MAX_WORKS:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"Archive limit must be between 1 and {PUBLIC_DELIVERY_MAX_WORKS}."},
            )
            return
        result = self.load_public_delivery_works(None, page_limit)
        if result is None:
            return
        response = self.signed_public_works(result, maximum=page_limit)
        if response is None:
            self.send_public_delivery_error()
            return
        self.send_json(HTTPStatus.OK, response)

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

    def is_loopback_request(self) -> bool:
        client_ip = self.request_rate_limit_ip() if TRUST_REVERSE_PROXY else clean_text(self.client_address[0], 128)
        try:
            return ipaddress.ip_address(client_ip).is_loopback
        except ValueError:
            return False

    def handle_health_get(self) -> None:
        self.send_json(HTTPStatus.OK, {"status": "ok"})

    def handle_readiness_get(self) -> None:
        if not self.is_loopback_request():
            allowed, _ = self.require_admin()
            if not allowed:
                return
        status, result = supabase_rest_request(
            "rpc/get_public_works",
            SUPABASE_PUBLISHABLE_KEY,
            {"target_creator_slug": None, "page_limit": 1, "page_offset": 0},
        )
        if status == HTTPStatus.OK and isinstance(result, dict) and not isinstance(result.get("error"), dict):
            self.send_json(
                HTTPStatus.OK,
                {"status": "ready", "dependencies": {"supabase": "available"}},
            )
            return
        self.send_json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"status": "unavailable", "dependencies": {"supabase": "unavailable"}},
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        canonical_path = canonical_url_path(self.path)
        if canonical_path == "/healthz":
            self.handle_health_get()
            return
        if canonical_path == "/readyz":
            self.handle_readiness_get()
            return
        communication_static_routes = {
            "/notifications.html": "/workspace/notifications",
            "/inbox.html": "/inbox",
            "/admin-audit.html": "/admin/audit",
        }
        if canonical_path in communication_static_routes and parsed.path != canonical_path:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", communication_static_routes[canonical_path])
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if canonical_path == "/admin-users.html" and parsed.path != canonical_path:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/users")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if canonical_path == "/admin-works.html" and parsed.path != canonical_path:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/works")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if canonical_path == "/admin-reviews.html" and parsed.path != canonical_path:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/reviews")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        # Route and protect the same normalized path that the static handler
        # will eventually translate. Encoded dotfiles/private directories and
        # encoded legacy upload paths must never fall through as public files.
        parsed = parsed._replace(path=canonical_path, netloc="")
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path in {
            "/notifications.js", "/inbox.js", "/dashboard.js", "/upload-studio.js", "/account-settings.js",
        }:
            user, authorization = self.require_account_session()
            if not user or not authorization:
                return
            self.path = parsed.path
            super().do_GET()
            return
        if parsed.path in {"/admin-works.js", "/admin-users.js", "/admin-audit.js"}:
            allowed, _ = self.require_admin()
            if not allowed:
                return
            self.path = parsed.path
            super().do_GET()
            return
        if parsed.path in {"/admin-reviews.js", "/manage.js"}:
            allowed, _, _ = self.require_reviewer()
            if not allowed:
                return
            self.path = parsed.path
            super().do_GET()
            return
        if parsed.path in {"/notifications", "/notifications/"}:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/workspace/notifications")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path in {"/workspace/notifications", "/workspace/notifications/"}:
            self.serve_account_communications_page("notifications.html", "/workspace/notifications")
            return
        if parsed.path in {"/inbox", "/inbox/"}:
            self.serve_account_communications_page("inbox.html", "/inbox")
            return
        if len(parts) == 2 and parts[0] == "inbox":
            try:
                conversation_id = clean_uuid(parts[1], "conversation id")
            except ValueError:
                self.send_json(HTTPStatus.NOT_FOUND, auth_error("CONVERSATION_NOT_FOUND", "The conversation is unavailable."))
                return
            self.serve_account_communications_page("inbox.html", f"/inbox/{conversation_id}")
            return
        if parsed.path in {"/admin/audit", "/admin/audit/"}:
            self.serve_admin_audit_page()
            return
        if len(parts) == 3 and parts[:2] == ["admin", "audit"]:
            try:
                audit_id = clean_uuid(parts[2], "audit id")
            except ValueError:
                self.send_json(HTTPStatus.NOT_FOUND, auth_error("AUDIT_NOT_FOUND", "The audit event is unavailable."))
                return
            self.serve_admin_audit_page(f"/admin/audit/{audit_id}")
            return
        if parsed.path in {"/manage", "/manage/", "/manage.html"}:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/reviews")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if len(parts) == 2 and parts[0] == "creators":
            creator_slug = clean_text(parts[1], 96).lower()
            if not PUBLIC_CREATOR_SLUG_PATTERN.fullmatch(creator_slug):
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Creator profile not found."})
                return
            self.serve_header_html("creator.html")
            return
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
        if parsed.path in {"/admin/works", "/admin/works/"}:
            self.serve_admin_works_page()
            return
        if len(parts) == 3 and parts[:2] == ["admin", "works"]:
            try:
                image_id = clean_uuid(parts[2], "admin work id")
            except ValueError:
                self.send_json(
                    HTTPStatus.NOT_FOUND,
                    auth_error("ADMIN_IMAGE_NOT_FOUND", "The work is unavailable."),
                )
                return
            self.serve_admin_works_page(f"/admin/works/{image_id}")
            return
        if parsed.path in {"/admin/users", "/admin/users/"}:
            self.serve_admin_users_page()
            return
        if len(parts) == 3 and parts[:2] == ["admin", "users"]:
            try:
                target_user_id = clean_uuid(parts[2], "admin user id")
            except ValueError:
                self.send_json(
                    HTTPStatus.NOT_FOUND,
                    auth_error("ADMIN_USER_NOT_FOUND", "The user is unavailable."),
                )
                return
            self.serve_admin_users_page(f"/admin/users/{target_user_id}")
            return
        if parsed.path == "/admin-users.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/users")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/admin-works.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/works")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/admin-reviews.html":
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/reviews")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path in communication_static_routes:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", communication_static_routes[parsed.path])
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
            self.serve_header_html("account-settings.html", user=user, authorization=authorization)
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
                self.serve_header_html("dashboard.html", user=user, authorization=authorization)
                return
            self.serve_header_html("upload-studio.html", user=user, authorization=authorization)
            return
        public_header_page = HEADER_IDENTITY_PUBLIC_PAGES.get(parsed.path)
        if public_header_page:
            self.serve_header_html(public_header_page)
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
            self.handle_me(parsed)
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
        if parsed.path == "/api/notifications":
            self.handle_notifications_get(parsed)
            return
        if parsed.path == "/api/notifications/unread-count":
            self.handle_notification_unread_count_get()
            return
        if parsed.path == "/api/inbox":
            self.handle_inbox_list_get(parsed)
            return
        if len(parts) == 3 and parts[:2] == ["api", "inbox"]:
            self.handle_inbox_detail_get(parsed, parts[2])
            return
        if parsed.path in {"/api/admin/audit", "/api/admin/audit-logs"}:
            self.handle_admin_audit_list_get(parsed)
            return
        if len(parts) == 4 and parts[:3] in (["api", "admin", "audit"], ["api", "admin", "audit-logs"]):
            self.handle_admin_audit_detail_get(parts[3])
            return
        if parsed.path == "/api/admin/works":
            self.handle_admin_works_list_get(parsed)
            return
        if len(parts) == 4 and parts[:3] == ["api", "admin", "works"]:
            self.handle_admin_work_detail_get(parts[3])
            return
        if parsed.path == "/api/admin/users":
            self.handle_admin_users_list_get(parsed)
            return
        if len(parts) == 4 and parts[:3] == ["api", "admin", "users"]:
            self.handle_admin_user_detail_get(parts[3])
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
        if len(parts) == 4 and parts[:3] == ["api", "public", "creators"]:
            self.handle_public_creator_get(parts[3])
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
                not auth_configured()
                and access
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

        if not is_public_static_path(canonical_path):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return

        self.path = canonical_path
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
        if parsed.path == "/api/inquiries":
            if not self.require_csrf():
                return
            self.handle_project_inquiry_create()
            return
        if parsed.path == "/api/notifications/read":
            if not self.require_csrf():
                return
            self.handle_notifications_read()
            return
        if parsed.path == "/api/admin/audit-logs/export":
            if not self.require_csrf():
                return
            self.handle_admin_audit_export()
            return
        if len(parts) == 4 and parts[:2] == ["api", "inbox"] and parts[3] in {"messages", "read", "status"}:
            if not self.require_csrf():
                return
            if parts[3] == "messages":
                self.handle_inbox_reply(parts[2])
            elif parts[3] == "read":
                self.handle_inbox_read(parts[2])
            else:
                self.handle_inbox_status(parts[2])
            return
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
        if parsed.path == "/api/me/profile/avatar/intents":
            if not self.require_csrf():
                return
            self.handle_profile_avatar_intent_create()
            return
        if (
            len(parts) == 7
            and parts[:5] == ["api", "me", "profile", "avatar", "intents"]
            and parts[6] == "complete"
        ):
            if not self.require_csrf():
                return
            self.handle_profile_avatar_complete(parts[5])
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
            if action in {
                "request-changes",
                "reject",
                "approve",
                "approve-and-publish",
                "super-admin-self-publish",
            }:
                self.handle_review_decision(submission_id, action)
                return
        if len(parts) == 5 and parts[:3] == ["api", "admin", "works"] and parts[4] in {"takedown", "restore"}:
            if not self.require_csrf():
                return
            self.handle_admin_work_mutation(parts[3], parts[4])
            return
        if len(parts) == 5 and parts[:3] == ["api", "admin", "users"] and parts[4] in {
            "status",
            "roles",
            "revoke-sessions",
        }:
            if not self.require_csrf():
                return
            self.handle_admin_user_mutation(parts[3], parts[4])
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
        if parsed.path == "/api/me/profile/avatar":
            if not self.require_csrf():
                return
            self.handle_profile_avatar_remove()
            return
        if len(parts) == 6 and parts[:5] == ["api", "me", "profile", "avatar", "intents"]:
            if not self.require_csrf():
                return
            self.handle_profile_avatar_intent_cancel(parts[5])
            return
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


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(MAX_REQUEST_THREADS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address) -> None:
        self._request_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MT Presence local static site.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8131)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = partial(MTRequestHandler, directory=str(ROOT))
    server = BoundedThreadingHTTPServer((args.host, args.port), handler)
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
