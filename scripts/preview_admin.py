#!/usr/bin/env python3
"""Local preview of the staff admin with sample data and no live services.

Starts a stand-in for Supabase on 127.0.0.1 that answers the admin's calls
with the local sample works (archive-data.js, assets/archive), then runs
server.py against it on its own port with a fresh environment, so nothing
can reach the live database. Sign in at http://127.0.0.1:<port>/auth/sign-in
with any email and password; the preview admin is the site owner (Super
Admin), so the upload page works end to end: images uploaded there are kept
in memory, pass a simulated security scan after a few seconds and, once
published, appear in Works management and on the public pages until the
preview stops. Other changes (site image places, take-downs) are refused.

Open it on 127.0.0.1, not localhost: cookies are kept per host, so the
preview's sign-in never touches a session on the local site at localhost.

Usage: python3 scripts/preview_admin.py [--port 8132]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from seed_local_archive_db import load_archive_data  # noqa: E402

PUBLISHABLE_KEY = "admin-preview-publishable-key"
ADMIN_ID = "10000000-0000-4000-8000-00000000a001"
# The owner's account: publishing from the upload page needs Super Admin.
ROLES = ["admin", "super_admin"]
CREATED_AT = "2026-10-28T09:00:00Z"
POLICY_VERSION = "mt-asset-scan-2026-07-v1"


def fake_access_token(user_id: str) -> str:
    claims = {"sub": user_id, "aal": "aal2", "amr": [{"method": "totp"}]}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{payload}.preview"


ADMIN_TOKEN = fake_access_token(ADMIN_ID)
ADMIN_USER = {
    "id": ADMIN_ID,
    "email": "preview@mtdo.cn",
    "email_confirmed_at": CREATED_AT,
    "factors": [],
    "identities": [],
    "app_metadata": {"provider": "email", "providers": ["email"]},
    "user_metadata": {"display_name": "预览管理员"},
    "created_at": CREATED_AT,
}
AUTHORIZATION = {"user_id": ADMIN_ID, "account_status": "active", "roles": ROLES, "aal": "aal2"}
PROFILE = {
    "display_name": "预览管理员",
    "avatar_url": None,
    "bio": None,
    "website_url": None,
    "country_code": "CN",
    "preferred_locale": "en",
    "timezone": "Asia/Shanghai",
    "copyright_name": "MT Presence",
    "default_license_preference": None,
    "professional_headline": None,
    "company": None,
    "city": None,
    "availability_status": "unavailable",
    "instagram_url": None,
    "linkedin_url": None,
    "avatar_storage_bucket": None,
    "avatar_storage_key": None,
    "avatar_mime_type": None,
    "avatar_byte_size": None,
    "avatar_width": None,
    "avatar_height": None,
    "avatar_updated_at": None,
}


def uuid_for(group: int, index: int) -> str:
    return f"{group}0000000-0000-4000-8000-{index:012d}"


def load_works() -> list[dict]:
    """The sample works as admin records, with ids and files of their own."""
    works = []
    for index, item in enumerate(load_archive_data()["sampleItems"], start=1):
        path = ROOT / item["src"]
        thumb = path.parent / "thumbs" / path.name
        works.append({
            "index": index,
            "id": uuid_for(2, index),
            "title": item["title"],
            "description": item.get("description") or "",
            "file": path,
            # The 600px copy, as the live site's thumbnails, when there is one.
            "thumb": thumb if thumb.exists() else path,
            "byte_size": path.stat().st_size if path.exists() else 0,
            "width": int(item["width"]),
            "height": int(item["height"]),
            "category": "abstract" if item.get("type") == "Abstract" else "concrete",
            "filename": path.name,
        })
    return works


WORKS = load_works()
WORKS_BY_ID = {work["id"]: work for work in WORKS}
ASSET_GROUP = {"original": 4, "display": 5, "thumbnail": 6}
BUCKETS = {"original": "image-originals", "display": "image-display", "thumbnail": "image-thumbnails"}


def asset(work: dict, kind: str) -> dict:
    if "uploaded_assets" in work:
        return dict(work["uploaded_assets"][kind])
    scale = 600 / max(work["width"], work["height"]) if kind == "thumbnail" and work["thumb"] != work["file"] else 1
    return {
        "id": uuid_for(ASSET_GROUP[kind], work["index"]),
        "image_id": work["id"],
        "owner_user_id": ADMIN_ID,
        "kind": kind,
        "storage_bucket": BUCKETS[kind],
        "storage_key": f"{ADMIN_ID}/{work['id']}/{kind}.jpg",
        "mime_type": "image/jpeg",
        "byte_size": work["thumb"].stat().st_size if scale != 1 else work["byte_size"],
        "width": round(work["width"] * scale),
        "height": round(work["height"] * scale),
        "checksum_sha256": "a" * 64,
        "scan_status": "clean",
        "scan_result_code": "clean",
        "scan_completed_at": CREATED_AT,
        "scan_policy_version": POLICY_VERSION,
        "storage_visibility": "private" if kind == "original" else "public",
        "deleted_at": None,
        "created_at": CREATED_AT,
    }


def summary(work: dict) -> dict:
    published_at = work.get("published_at") or f"2026-10-28T{9 + work['index'] // 6:02d}:{(work['index'] * 7) % 60:02d}:00Z"
    return {
        "id": work["id"],
        "version": 1,
        "title": work["title"],
        "original_filename": work["filename"],
        "original_width": work["width"],
        "original_height": work["height"],
        "processing_status": "ready",
        "workflow_status": "approved",
        "publication_status": "published",
        "created_at": CREATED_AT,
        "updated_at": published_at,
        "published_at": published_at,
        "unpublished_at": None,
        "owner": {"id": ADMIN_ID, "email": ADMIN_USER["email"], "display_name": "MT Presence", "account_status": "active"},
        "asset_summary": {"count": 3, "clean_count": 3, "flagged_count": 0, "failed_count": 0, "pending_count": 0},
        "thumbnail_asset": asset(work, "thumbnail"),
        "latest_review": None,
        "latest_governance_action": None,
        "content_category": work["category"],
        "derivatives": {
            kind: {key: asset(work, kind)[key] for key in ("byte_size", "width", "height", "mime_type", "scan_status")}
            if "uploaded_assets" in work
            else {"byte_size": work["byte_size"], "width": work["width"], "height": work["height"], "mime_type": "image/jpeg", "scan_status": "clean"}
            for kind in ASSET_GROUP
        },
    }


def detail(work: dict) -> dict:
    version_id = work.get("version_id") or uuid_for(3, work["index"])
    return {
        **summary(work),
        "current_version": {
            "id": version_id,
            "image_id": work["id"],
            "version_number": 1,
            "title": work["title"],
            "caption": work["description"],
            "description": work["description"],
            "alt_text": work.get("alt_text") or work["title"],
            "tags": work.get("tags", []),
            "content_category": work["category"],
            "captured_at": None,
            "location_name": None,
            "gps_visibility": "private",
            "public_exif": {},
            "copyright_holder": "MT Presence",
            "copyright_year": 2026,
            "contains_recognizable_people": False,
            "model_release_status": "not_applicable",
            "property_release_status": "not_applicable",
            "rights_declared": True,
            "ai_disclosure": "none",
            "sensitive_content_disclosure": "none",
            "locked_at": CREATED_AT,
            "created_at": CREATED_AT,
        },
        "original_asset": asset(work, "original"),
        "display_asset": asset(work, "display"),
        "thumbnail_asset": asset(work, "thumbnail"),
        "versions": [{"id": version_id, "image_id": work["id"], "version_number": 1, "title": work["title"], "created_by_user_id": ADMIN_ID, "created_at": CREATED_AT, "locked_at": CREATED_AT}],
        "review_submissions": [],
        "takedowns": [],
        "governance_actions": [],
        "audit_timeline": [],
    }


def public_work(work: dict) -> dict:
    def public_asset(kind: str) -> dict:
        value = asset(work, kind)
        for key in ("owner_user_id", "byte_size", "scan_status", "scan_result_code", "scan_policy_version"):
            value.pop(key, None)
        return value

    ratio_code, ratio_label = ratio_of(work["width"], work["height"])
    return {
        "id": work["id"],
        "title": work["title"],
        "caption": work["description"],
        "description": work["description"],
        "alt_text": work.get("alt_text") or work["title"],
        "tags": work.get("tags", []),
        "content_category": work["category"],
        "captured_at": None,
        "location_name": None,
        "public_exif": {},
        "published_at": summary(work)["published_at"],
        "width": work["width"],
        "height": work["height"],
        "ratio_code": ratio_code,
        "ratio_label": ratio_label,
        "creator": {"slug": "mt-presence", "display_name": "MT Presence"},
        "display_asset": public_asset("display"),
        "thumbnail_asset": public_asset("thumbnail"),
    }


# A few places filled, as a site in use would have them.
def site_image_items() -> list[dict]:
    grey = [work for work in WORKS if work["category"] == "abstract"]
    colour = [work for work in WORKS if work["category"] == "concrete"]
    places = [("home_hero", 1, grey[2])]
    places += [("home_selected", position, work) for position, work in enumerate([grey[0], colour[0], grey[8], colour[4], grey[6]], start=1)]
    places += [("works_poster_colour", 1, colour[3]), ("works_poster_grey", 1, grey[4])]
    return [
        {"slot_key": slot, "position": position, "image_id": work["id"], "live": True, "updated_at": CREATED_AT, "work": summary(work)}
        for slot, position, work in places
    ]


def empty_page(limit: int) -> dict:
    return {"limit": limit, "has_more": False, "next_cursor": None}


def ratio_of(width: int, height: int) -> tuple[str, str]:
    shape = width / height
    if shape > 2.1:
        return "panorama", "panorama"
    shapes = {"1:1": 1, "4:3": 4 / 3, "4:5": 4 / 5, "2:3": 2 / 3, "3:2": 3 / 2, "16:9": 16 / 9}
    label = min(shapes, key=lambda name: abs(shapes[name] - shape))
    codes = {"1:1": "one_to_one", "4:3": "four_to_three", "4:5": "four_to_five", "2:3": "two_to_three", "3:2": "three_to_two", "16:9": "sixteen_to_nine"}
    return codes[label], label


# The upload page, kept in memory. Each uploaded image runs the same states as
# the database: Draft -> Submitted -> published by the owner. The security
# scan the server's scanner does is simulated: assets turn clean a few seconds
# after the upload completes.
SCAN_SECONDS = 3.0
SUBMISSION_POLICY_VERSION = "workspace-review-v1"
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
STUDIO_LOCK = threading.Lock()
FOLDERS = [
    {"id": uuid_for(7, 1), "name": "收件箱", "is_system": True, "created_at": CREATED_AT},
    {"id": uuid_for(7, 2), "name": "2026-11 新作品", "is_system": False, "created_at": CREATED_AT},
]
UPLOADS: dict[str, dict] = {}
OBJECTS: dict[str, tuple[str, bytes]] = {}
IMAGES: dict[str, dict] = {}
SUBMISSIONS: dict[str, dict] = {}
SUBMIT_REPLAYS: dict[str, dict] = {}
COMPLIANCE_FIELDS = (
    "alt_text", "copyright_holder", "copyright_year", "contains_recognizable_people", "model_release_status",
    "property_release_status", "rights_declared", "ai_disclosure", "sensitive_content_disclosure",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def failure(code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, **extra}}


def studio_assets(image: dict) -> list[dict]:
    scanned = time.time() >= image["scan_ready_at"]
    return [
        {
            **value,
            "scan_status": "clean" if scanned else "pending",
            "scan_policy_version": POLICY_VERSION if scanned else None,
        }
        for value in image["assets"]
    ]


def draft_view(image: dict) -> dict:
    return {
        "id": image["id"],
        "folder_id": image["folder_id"],
        "processing_status": "ready",
        "workflow_status": image["workflow_status"],
        "publication_status": image["publication_status"],
        "original_filename": image["original_filename"],
        "original_width": image["original_width"],
        "original_height": image["original_height"],
        "checksum_sha256": image["checksum_sha256"],
        "lock_version": image["lock_version"],
        "created_at": image["created_at"],
        "updated_at": image["updated_at"],
        "deleted_at": image["deleted_at"],
        "version": dict(image["version"]),
        "assets": studio_assets(image),
    }


def readiness(image: dict) -> dict:
    """The database's publish rules (workspace_get_submit_readiness)."""
    version = image["version"]
    errors: dict[str, str] = {}

    def blank(key: str) -> bool:
        return not str(version.get(key) or "").strip()

    if blank("title"):
        errors["title"] = "Title is required."
    if blank("alt_text"):
        errors["alt_text"] = "Alt text is required."
    if version.get("content_category") not in {"abstract", "concrete"}:
        errors["content_category"] = "Choose a content category."
    work_fail = bool(errors)
    if blank("copyright_holder"):
        errors["copyright_holder"] = "Copyright holder is required."
    year = version.get("copyright_year")
    if not isinstance(year, int) or not 1000 <= year <= datetime.now().year + 1:
        errors["copyright_year"] = "Confirm a valid copyright year."
    people = version.get("contains_recognizable_people")
    if people is None:
        errors["contains_recognizable_people"] = "Choose whether the image contains recognizable people."
    elif people and version.get("model_release_status") not in {"available", "not_available", "pending"}:
        errors["model_release_status"] = "Choose a model release status."
    elif not people and version.get("model_release_status") != "not_applicable":
        errors["model_release_status"] = "Model release must be Not Applicable when no recognizable people are present."
    if version.get("property_release_status") is None:
        errors["property_release_status"] = "Choose a property release status, including Not Applicable."
    if version.get("rights_declared") is not True:
        errors["rights_declared"] = "Confirm that you own or control the required rights."
    if version.get("ai_disclosure") is None:
        errors["ai_disclosure"] = "Choose an AI disclosure."
    if version.get("sensitive_content_disclosure") is None:
        errors["sensitive_content_disclosure"] = "Choose a sensitive-content disclosure."
    rights_fail = bool(set(errors) - {"title", "alt_text", "content_category"})

    stored = all(f"{value['storage_bucket']}/{value['storage_key']}" in OBJECTS for value in image["assets"])
    scanned = time.time() >= image["scan_ready_at"]
    editable = (
        image["deleted_at"] is None
        and image["workflow_status"] in {"draft", "changes_requested"}
        and image["publication_status"] in {"never_published", "unpublished"}
    )
    checks = [
        ("work_details", "fail" if work_fail else "pass", "Complete the required title, alt text, and content category." if work_fail else "Work details are complete."),
        ("rights_disclosures", "fail" if rights_fail else "pass", "Complete the required rights and disclosure fields." if rights_fail else "Rights and disclosures are complete."),
        ("image_assets", "pass" if stored else "fail", "All required assets are available." if stored else "Original, display, and thumbnail assets must be complete and available."),
        ("security_scan", "pass" if scanned else "pending", "All asset security scans passed." if scanned else "Asset security scanning is still in progress."),
        ("submission_state", "pass" if editable else "fail", "This Draft can enter the review queue." if editable else "This image is not in an editable Draft state."),
    ]
    states = [state for _, state, _ in checks]
    status = "blocked" if "fail" in states else "pending" if "pending" in states else "ready"
    return {
        "image_id": image["id"],
        "lock_version": image["lock_version"],
        "workflow_status": image["workflow_status"],
        "status": status,
        "ready": status == "ready",
        "blocker_count": sum(state != "pass" for state in states),
        "checks": [{"code": code, "label": code, "state": state, "message": message} for code, state, message in checks],
        "field_errors": errors,
    }


def published_work(image: dict) -> dict:
    """An uploaded image the owner published, in the sample works' shape."""
    version = image["version"]
    assets = {value["kind"]: value for value in studio_assets(image)}
    for value in assets.values():
        value.update({
            "image_id": image["id"],
            "owner_user_id": ADMIN_ID,
            "scan_result_code": "clean",
            "scan_completed_at": image["published_at"],
            "storage_visibility": "private" if value["kind"] == "original" else "public",
            "deleted_at": None,
            "created_at": image["created_at"],
        })
    return {
        "id": image["id"],
        "version_id": version["id"],
        "title": version.get("title") or "",
        "description": version.get("caption") or version.get("description") or "",
        "alt_text": version.get("alt_text") or "",
        "tags": list(version.get("tags") or []),
        "byte_size": assets["original"]["byte_size"],
        "width": image["original_width"],
        "height": image["original_height"],
        "category": version.get("content_category") or "concrete",
        "filename": image["original_filename"],
        "published_at": image["published_at"],
        "uploaded_assets": assets,
    }


def all_works() -> list[dict]:
    with STUDIO_LOCK:
        uploaded = [published_work(image) for image in IMAGES.values() if image["publication_status"] == "published"]
    uploaded.sort(key=lambda work: work["published_at"], reverse=True)
    return uploaded + WORKS


def find_work(image_id: str) -> dict | None:
    return next((work for work in all_works() if work["id"] == image_id), None)


def folder_counts() -> list[dict]:
    return [
        {
            **folder,
            "image_count": sum(
                1 for image in IMAGES.values()
                if image["folder_id"] == folder["id"] and image["deleted_at"] is None and image["workflow_status"] in {"draft", "changes_requested"}
            ),
        }
        for folder in FOLDERS
    ]


def studio_rpc(name: str, body: dict) -> dict | None:
    """The upload page's database functions; None when the name is not one."""
    with STUDIO_LOCK:
        if name == "workspace_list_folders":
            return {"folders": folder_counts()}
        if name == "workspace_create_folder":
            folder_name = str(body.get("folder_name") or "").strip()
            if any(folder["name"] == folder_name for folder in FOLDERS):
                return failure("FOLDER_NAME_CONFLICT", "A folder with this name already exists.")
            folder = {"id": str(uuid.uuid4()), "name": folder_name, "is_system": False, "created_at": now_iso()}
            FOLDERS.append(folder)
            return {"folder": {**folder, "image_count": 0}}
        if name in {"workspace_list_drafts", "workspace_list_trashed_drafts"}:
            trashed = name == "workspace_list_trashed_drafts"
            images = [
                draft_view(image) for image in IMAGES.values()
                if image["workflow_status"] in {"draft", "changes_requested"} and (image["deleted_at"] is not None) == trashed
            ]
            images.sort(key=lambda draft: draft["created_at"], reverse=True)
            return {"images": images}
        if name == "workspace_create_upload_intent":
            intent = body.get("intent") or {}
            upload_id, image_id = str(uuid.uuid4()), str(uuid.uuid4())
            folder_id = intent.get("folder_id") if any(folder["id"] == intent.get("folder_id") for folder in FOLDERS) else FOLDERS[0]["id"]
            assets = []
            for value in intent.get("assets") or []:
                kind = value.get("kind")
                assets.append({
                    "id": str(uuid.uuid4()),
                    "kind": kind,
                    "storage_bucket": BUCKETS[kind],
                    "storage_key": f"{ADMIN_ID}/{image_id}/{kind}.{EXTENSIONS.get(value.get('mime_type'), 'jpg')}",
                    "mime_type": value.get("mime_type"),
                    "byte_size": value.get("byte_size"),
                    "width": value.get("width"),
                    "height": value.get("height"),
                    "checksum_sha256": value.get("checksum_sha256"),
                })
            UPLOADS[upload_id] = {"intent": intent, "image_id": image_id, "folder_id": folder_id, "assets": assets}
            return {"upload_id": upload_id, "image_id": image_id, "folder_id": folder_id, "expires_at": "2099-01-01T00:00:00Z", "assets": assets}
        if name == "workspace_complete_upload":
            upload = UPLOADS.get(str(body.get("upload_id")))
            if not upload:
                return failure("UPLOAD_INTENT_NOT_FOUND", "The upload intent is unavailable.")
            if not all(f"{value['storage_bucket']}/{value['storage_key']}" in OBJECTS for value in upload["assets"]):
                return failure("UPLOAD_ASSETS_INCOMPLETE", "Upload every image file before completing.")
            UPLOADS.pop(str(body.get("upload_id")))
            patch = body.get("draft") or {}
            intent = upload["intent"]
            created = now_iso()
            version = {
                "id": str(uuid.uuid4()), "version_number": 1,
                "title": "", "caption": "", "description": "", "tags": [], "content_category": "concrete",
                "captured_at": None, "location_name": None,
                **{field: None for field in COMPLIANCE_FIELDS}, "rights_declared": False,
                "created_at": created, "locked_at": None,
            }
            version.update({key: value for key, value in patch.items() if key != "folder_id"})
            for value in upload["assets"]:
                value["byte_size"] = len(OBJECTS[f"{value['storage_bucket']}/{value['storage_key']}"][1])
            image = {
                "id": upload["image_id"], "folder_id": patch.get("folder_id") or upload["folder_id"],
                "workflow_status": "draft", "publication_status": "never_published",
                "original_filename": intent.get("original_filename") or "image.jpg",
                "original_width": intent.get("original_width"), "original_height": intent.get("original_height"),
                "checksum_sha256": intent.get("checksum_sha256"),
                "lock_version": 1, "created_at": created, "updated_at": created, "deleted_at": None, "published_at": None,
                "version": version, "assets": upload["assets"], "scan_ready_at": time.time() + SCAN_SECONDS,
            }
            IMAGES[image["id"]] = image
            print(f"[preview] uploaded {image['original_filename']} as a Draft", flush=True)
            return {"draft": draft_view(image)}
        if name == "workspace_cancel_upload_intent":
            UPLOADS.pop(str(body.get("upload_id")), None)
            return {"canceled": True, "upload_id": body.get("upload_id"), "cleanup_status": "complete", "assets": []}

        image = IMAGES.get(str(body.get("image_id")))
        if name in {"workspace_update_draft_versioned", "workspace_trash_draft_versioned", "workspace_restore_draft",
                    "workspace_get_submit_readiness", "workspace_submit_draft_versioned"} and image is None:
            return failure("DRAFT_NOT_FOUND", "The Draft is unavailable.")
        if name == "workspace_get_submit_readiness":
            return {"readiness": readiness(image)}
        if name in {"workspace_update_draft_versioned", "workspace_trash_draft_versioned"}:
            if body.get("expected_version") != image["lock_version"]:
                return failure("DRAFT_VERSION_CONFLICT", "A newer version of this Draft is available. Reload before saving.")
            if image["workflow_status"] not in {"draft", "changes_requested"}:
                return failure("DRAFT_LOCKED", "Submitted or reviewed images cannot be edited as Drafts.")
            if name == "workspace_trash_draft_versioned":
                image["deleted_at"] = now_iso()
            else:
                patch = body.get("patch") or {}
                if patch.get("folder_id"):
                    image["folder_id"] = patch["folder_id"]
                image["version"].update({key: value for key, value in patch.items() if key != "folder_id"})
            image["lock_version"] += 1
            image["updated_at"] = now_iso()
            if name == "workspace_trash_draft_versioned":
                return {"trashed": True, "image_id": image["id"]}
            return {"draft": draft_view(image)}
        if name == "workspace_restore_draft":
            image["deleted_at"] = None
            image["lock_version"] += 1
            return {"draft": draft_view(image)}
        if name == "workspace_submit_draft_versioned":
            replay = SUBMIT_REPLAYS.get(str(body.get("idempotency_key")))
            if replay:
                return replay
            if body.get("expected_version") != image["lock_version"]:
                return failure("DRAFT_VERSION_CONFLICT", "A newer version of this Draft is available. Reload before submitting.")
            check = readiness(image)
            if not check["ready"]:
                return failure("DRAFT_NOT_READY", "This Draft is not ready to submit.", field_errors=check["field_errors"], details=check)
            submitted_at = now_iso()
            submission = {
                "id": str(uuid.uuid4()), "image_id": image["id"], "image_version_id": image["version"]["id"],
                "status": "submitted", "policy_version": SUBMISSION_POLICY_VERSION, "submitted_at": submitted_at,
                "lock_version": 1, "readiness": check,
            }
            SUBMISSIONS[submission["id"]] = submission
            image["workflow_status"] = "submitted"
            image["version"]["locked_at"] = submitted_at
            image["lock_version"] += 1
            result = {
                "submitted": True,
                "submission": {key: submission[key] for key in ("id", "image_id", "image_version_id", "status", "policy_version", "submitted_at")},
                "image": {"id": image["id"], "workflow_status": "submitted", "lock_version": image["lock_version"]},
            }
            SUBMIT_REPLAYS[str(body.get("idempotency_key"))] = result
            return result

        if name in {"review_get_submission", "review_super_admin_self_publish"}:
            submission = SUBMISSIONS.get(str(body.get("submission_id")))
            if submission is None:
                return failure("REVIEW_SUBMISSION_NOT_FOUND", "The review submission is unavailable.")
            image = IMAGES[submission["image_id"]]
            if name == "review_get_submission":
                return {
                    "actor": {"id": ADMIN_ID, "roles": ROLES},
                    "submission": {
                        "id": submission["id"], "status": submission["status"], "lock_version": submission["lock_version"],
                        "policy_version": submission["policy_version"], "submitted_at": submission["submitted_at"],
                        "assigned_reviewer": None, "readiness_snapshot": submission["readiness"],
                    },
                    "owner": {"id": ADMIN_ID, "display_name": "MT Presence", "account_status": "active", "created_at": CREATED_AT},
                    "image": {**draft_view(image), "processing_status": "ready", "published_at": image["published_at"]},
                    "assets": studio_assets(image),
                    "decisions": [],
                }
            if submission["status"] != "submitted":
                return failure("REVIEW_ALREADY_PUBLISHED", "This submission has already been decided.")
            if body.get("expected_lock_version") != submission["lock_version"]:
                return failure("REVIEW_VERSION_CONFLICT", "The submission changed. Reload and try again.")
            published_at = now_iso()
            submission.update({"status": "approved", "lock_version": submission["lock_version"] + 1})
            image.update({"workflow_status": "approved", "publication_status": "published", "published_at": published_at, "updated_at": published_at})
            print(f"[preview] published {image['version'].get('title') or image['original_filename']}", flush=True)
            return {
                "submission": {"id": submission["id"], "status": "approved", "lock_version": submission["lock_version"], "completed_at": published_at},
                "decision": {"id": str(uuid.uuid4()), "decision": "approve_and_publish", "created_at": published_at},
                "image": {"id": image["id"], "workflow_status": "approved", "publication_status": "published", "published_at": published_at},
            }
    return None


def multipart_file(content_type: str, data: bytes) -> tuple[str, bytes] | None:
    """The file part of the multipart body Supabase Storage uploads send."""
    boundary = next((part.split("=", 1)[1].strip('"') for part in content_type.split(";") if part.strip().startswith("boundary=")), "")
    if not boundary:
        return None
    for part in data.split(b"--" + boundary.encode()):
        head, _, content = part.partition(b"\r\n\r\n")
        if b"filename=" not in head:
            continue
        mime = "application/octet-stream"
        for line in head.decode("utf-8", "replace").split("\r\n"):
            if line.lower().startswith("content-type:"):
                mime = line.split(":", 1)[1].strip()
        return mime, content.removesuffix(b"\r\n")
    return None


class PreviewSupabase(BaseHTTPRequestHandler):
    """Answers as Supabase would for the signed-in preview admin."""

    unknown: set[str] = set()

    def log_message(self, _format, *_args) -> None:
        return

    def token(self) -> str:
        return self.headers.get("Authorization", "").removeprefix("Bearer ")

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        try:
            return json.loads(self.rfile.read(length).decode()) if length else {}
        except ValueError:
            return {}

    def send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def note_unknown(self, method: str) -> None:
        key = f"{method} {urlparse(self.path).path}"
        if key not in type(self).unknown:
            type(self).unknown.add(key)
            print(f"[preview] not simulated: {key}", flush=True)

    def send_cors(self) -> None:
        # The browser uploads straight to Storage from the admin's own origin.
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-upsert, cache-control")

    def serve_file(self, storage_path: str) -> None:
        # .../<bucket>/<owner>/<image id>/<kind>.jpg
        parts = unquote(storage_path).split("/")
        stored = OBJECTS.get("/".join(parts[-4:])) if len(parts) >= 4 else None
        work = WORKS_BY_ID.get(parts[-2]) if len(parts) >= 2 else None
        if stored:
            mime, data = stored
        elif work and work["file"].exists():
            mime, data = "image/jpeg", (work["thumb"] if parts[-1] == "thumbnail.jpg" else work["file"]).read_bytes()
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not found"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith(("/storage/v1/object/sign/", "/storage/v1/object/public/", "/storage/v1/render/image/")):
            self.serve_file(path)
            return
        if path == "/auth/v1/user" and self.token() == ADMIN_TOKEN:
            self.send_json(HTTPStatus.OK, ADMIN_USER)
            return
        if path == "/auth/v1/factors" and self.token() == ADMIN_TOKEN:
            self.send_json(HTTPStatus.OK, [])
            return
        if path == "/rest/v1/user_profiles" and self.token() == ADMIN_TOKEN:
            self.send_json(HTTPStatus.OK, [PROFILE])
            return
        self.note_unknown("GET")
        self.send_json(HTTPStatus.NOT_FOUND, {"message": "not simulated in the preview"})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors()
        self.end_headers()

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        data = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
        target = unquote(path.removeprefix("/storage/v1/object/upload/sign/"))
        upload = multipart_file(self.headers.get("Content-Type", ""), data) if path != target else None
        if not upload:
            self.note_unknown("PUT")
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not simulated in the preview"})
            return
        OBJECTS[target] = upload
        body = json.dumps({"Key": target}).encode()
        self.send_response(HTTPStatus.OK)
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.body()
        if path == "/auth/v1/token":
            # Any email and password: this is the preview admin.
            self.send_json(HTTPStatus.OK, {
                "access_token": ADMIN_TOKEN,
                "refresh_token": "admin-preview-refresh",
                "expires_in": 3600,
                "token_type": "bearer",
                "user": ADMIN_USER,
            })
            return
        if path == "/auth/v1/logout":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path.startswith("/storage/v1/object/upload/sign/"):
            self.send_json(HTTPStatus.OK, {"url": f"{path.removeprefix('/storage/v1')}?token=preview"})
            return
        if path.startswith("/storage/v1/object/sign/"):
            suffix = path.removeprefix("/storage/v1")
            if isinstance(body.get("paths"), list):
                bucket = suffix.removeprefix("/object/sign/").strip("/")
                self.send_json(HTTPStatus.OK, [
                    {"path": item, "signedURL": f"/object/sign/{bucket}/{item}?token=preview", "error": None}
                    for item in body["paths"]
                ])
            else:
                self.send_json(HTTPStatus.OK, {"signedURL": f"{suffix}?token=preview"})
            return
        if not path.startswith("/rest/v1/rpc/"):
            self.note_unknown("POST")
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not simulated in the preview"})
            return

        name = path.removeprefix("/rest/v1/rpc/")
        if name in {"get_public_works", "get_public_site_images", "get_public_creator", "get_public_creator_avatar"}:
            if name == "get_public_works":
                limit = int(body.get("page_limit") or 100)
                offset = int(body.get("page_offset") or 0)
                works = all_works()
                items = [public_work(work) for work in works[offset:offset + limit]]
                self.send_json(HTTPStatus.OK, {"items": items, "count": len(works)})
            elif name == "get_public_site_images":
                self.send_json(HTTPStatus.OK, {"items": []})
            else:
                self.send_json(HTTPStatus.OK, {})
            return
        if self.token() != ADMIN_TOKEN:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "sign in to the preview"})
            return
        studio = studio_rpc(name, body)
        if studio is not None:
            self.send_json(HTTPStatus.OK, studio)
        elif name == "current_authorization":
            self.send_json(HTTPStatus.OK, AUTHORIZATION)
        elif name == "admin_list_images":
            self.send_json(HTTPStatus.OK, self.list_images(body))
        elif name == "admin_get_image":
            work = find_work(str(body.get("target_image_id")))
            if work:
                self.send_json(HTTPStatus.OK, {"actor": self.actor(), "work": detail(work)})
            else:
                self.send_json(HTTPStatus.OK, {"error": {"code": "ADMIN_WORK_NOT_FOUND", "message": "Not found."}})
        elif name == "admin_list_site_images":
            self.send_json(HTTPStatus.OK, {"items": site_image_items()})
        elif name == "list_my_conversations":
            self.send_json(HTTPStatus.OK, {"items": [], "pagination": empty_page(int(body.get("page_limit") or 30))})
        elif name == "admin_list_audit_logs":
            self.send_json(HTTPStatus.OK, {"actor": {"id": ADMIN_ID, "roles": ROLES}, "items": [], "pagination": empty_page(int(body.get("page_limit") or 50))})
        elif name.startswith(("admin_govern", "admin_set", "workspace_", "update_", "set_", "remove_", "create_", "complete_", "cancel_", "review_decide")):
            self.send_json(HTTPStatus.OK, {"error": {"code": "PREVIEW_READ_ONLY", "message": "预览模式不会修改任何数据。"}})
        else:
            self.note_unknown("RPC")
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not simulated in the preview"})

    def actor(self) -> dict:
        return {"id": ADMIN_ID, "roles": ROLES, "can_govern_images": True, "capabilities": {"can_takedown": True, "can_restore": True}}

    def list_images(self, body: dict) -> dict:
        status_filter = body.get("status_filter", "all")
        query = str(body.get("search_query") or "").strip().lower()
        works = all_works()
        matching = [work for work in works if status_filter in {"all", "published"} and (not query or query in work["title"].lower())]
        if body.get("sort_code") in {"oldest", "created_asc", "updated_asc"}:
            matching = list(reversed(matching))
        size = int(body.get("page_size") or 30)
        offset = int(body.get("page_offset") or 0)
        page = matching[offset:offset + size]
        return {
            "actor": self.actor(),
            "items": [summary(work) for work in page],
            "counts": {"all": len(works), "never_published": 0, "published": len(works), "unpublished": 0, "quarantined": 0, "archived": 0, "deleted": 0},
            "pagination": {"total": len(matching), "limit": size, "offset": offset, "has_more": offset + size < len(matching)},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview the staff admin locally with sample data.")
    parser.add_argument("--port", type=int, default=8132)
    args = parser.parse_args()

    provider = ThreadingHTTPServer(("127.0.0.1", 0), PreviewSupabase)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    provider_url = f"http://127.0.0.1:{provider.server_address[1]}"
    base_url = f"http://127.0.0.1:{args.port}"
    # A fresh environment: nothing from the shell (no live addresses or keys).
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "SUPABASE_URL": provider_url,
        "SUPABASE_PUBLISHABLE_KEY": PUBLISHABLE_KEY,
        "MT_RUNTIME_ENVIRONMENT": "development",
        "MT_PUBLIC_BASE_URL": base_url,
        "MT_COOKIE_SECURE": "0",
        "MT_PUBLIC_WORKS_CACHE_SECONDS": "0",
        "MT_LOCAL_ARCHIVE_PREVIEW": "0",
    }
    print(f"[preview] {len(WORKS)} sample works; stand-in database at {provider_url}", flush=True)
    print(f"[preview] open {base_url}/admin and sign in with any email and password", flush=True)
    server = subprocess.Popen([sys.executable, str(ROOT / "server.py"), "--port", str(args.port)], cwd=ROOT, env=env)
    try:
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.terminate()
        provider.shutdown()


if __name__ == "__main__":
    main()
