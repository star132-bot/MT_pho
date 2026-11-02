#!/usr/bin/env python3
"""Local preview of the staff admin with sample data and no live services.

Starts a stand-in for Supabase on 127.0.0.1 that answers the admin's calls
with the local sample works (archive-data.js, assets/archive), then runs
server.py against it on its own port with a fresh environment, so nothing
can reach the live database. Sign in at http://127.0.0.1:<port>/auth/sign-in
with any email and password. Anything that would change data is refused.

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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from seed_local_archive_db import load_archive_data  # noqa: E402

PUBLISHABLE_KEY = "admin-preview-publishable-key"
ADMIN_ID = "10000000-0000-4000-8000-00000000a001"
ROLES = ["admin"]
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
    published_at = f"2026-10-28T{9 + work['index'] // 6:02d}:{(work['index'] * 7) % 60:02d}:00Z"
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
            kind: {"byte_size": work["byte_size"], "width": work["width"], "height": work["height"], "mime_type": "image/jpeg", "scan_status": "clean"}
            for kind in ASSET_GROUP
        },
    }


def detail(work: dict) -> dict:
    version_id = uuid_for(3, work["index"])
    return {
        **summary(work),
        "current_version": {
            "id": version_id,
            "image_id": work["id"],
            "version_number": 1,
            "title": work["title"],
            "caption": work["description"],
            "description": work["description"],
            "alt_text": work["title"],
            "tags": [],
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

    return {
        "id": work["id"],
        "title": work["title"],
        "caption": work["description"],
        "description": work["description"],
        "alt_text": work["title"],
        "tags": [],
        "content_category": work["category"],
        "captured_at": None,
        "location_name": None,
        "public_exif": {},
        "published_at": summary(work)["published_at"],
        "width": work["width"],
        "height": work["height"],
        "ratio_code": "three_to_two",
        "ratio_label": "3:2",
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

    def serve_file(self, storage_path: str) -> None:
        # .../<bucket>/<owner>/<image id>/<kind>.jpg
        parts = unquote(storage_path).split("/")
        work = WORKS_BY_ID.get(parts[-2]) if len(parts) >= 2 else None
        if not work or not work["file"].exists():
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not found"})
            return
        data = (work["thumb"] if parts[-1] == "thumbnail.jpg" else work["file"]).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
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
                items = [public_work(work) for work in WORKS[offset:offset + limit]]
                self.send_json(HTTPStatus.OK, {"items": items, "count": len(WORKS)})
            elif name == "get_public_site_images":
                self.send_json(HTTPStatus.OK, {"items": []})
            else:
                self.send_json(HTTPStatus.OK, {})
            return
        if self.token() != ADMIN_TOKEN:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "sign in to the preview"})
            return
        if name == "current_authorization":
            self.send_json(HTTPStatus.OK, AUTHORIZATION)
        elif name == "admin_list_images":
            self.send_json(HTTPStatus.OK, self.list_images(body))
        elif name == "admin_get_image":
            work = WORKS_BY_ID.get(str(body.get("target_image_id")))
            if work:
                self.send_json(HTTPStatus.OK, {"actor": self.actor(), "work": detail(work)})
            else:
                self.send_json(HTTPStatus.OK, {"error": {"code": "ADMIN_WORK_NOT_FOUND", "message": "Not found."}})
        elif name == "admin_list_site_images":
            self.send_json(HTTPStatus.OK, {"items": site_image_items()})
        elif name == "workspace_list_folders":
            self.send_json(HTTPStatus.OK, {"folders": [
                {"id": uuid_for(7, 1), "name": "收件箱", "is_system": True, "created_at": CREATED_AT},
                {"id": uuid_for(7, 2), "name": "2026-11 新作品", "is_system": False, "created_at": CREATED_AT},
            ]})
        elif name in {"workspace_list_drafts", "workspace_list_trashed_drafts"}:
            self.send_json(HTTPStatus.OK, {"images": []})
        elif name == "list_my_conversations":
            self.send_json(HTTPStatus.OK, {"items": [], "pagination": empty_page(int(body.get("page_limit") or 30))})
        elif name == "admin_list_audit_logs":
            self.send_json(HTTPStatus.OK, {"actor": {"id": ADMIN_ID, "roles": ROLES}, "items": [], "pagination": empty_page(int(body.get("page_limit") or 50))})
        elif name.startswith(("admin_govern", "admin_set", "workspace_create", "workspace_restore", "update_", "set_", "remove_", "create_", "complete_", "cancel_", "review_decide")):
            self.send_json(HTTPStatus.OK, {"error": {"code": "PREVIEW_READ_ONLY", "message": "预览模式不会修改任何数据。"}})
        else:
            self.note_unknown("RPC")
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "not simulated in the preview"})

    def actor(self) -> dict:
        return {"id": ADMIN_ID, "roles": ROLES, "can_govern_images": True, "capabilities": {"can_takedown": True, "can_restore": True}}

    def list_images(self, body: dict) -> dict:
        status_filter = body.get("status_filter", "all")
        query = str(body.get("search_query") or "").strip().lower()
        matching = [work for work in WORKS if status_filter in {"all", "published"} and (not query or query in work["title"].lower())]
        if body.get("sort_code") in {"oldest", "created_asc", "updated_asc"}:
            matching = list(reversed(matching))
        size = int(body.get("page_size") or 30)
        offset = int(body.get("page_offset") or 0)
        page = matching[offset:offset + size]
        return {
            "actor": self.actor(),
            "items": [summary(work) for work in page],
            "counts": {"all": len(WORKS), "never_published": 0, "published": len(WORKS), "unpublished": 0, "quarantined": 0, "archived": 0, "deleted": 0},
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
