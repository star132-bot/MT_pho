#!/usr/bin/env python3
"""Local static server for MT Presence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


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


def is_private_static_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    return any(part.startswith(".") for part in parts) or (bool(parts) and parts[0] in {"data", "tmp", "shots"})


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


class MTRequestHandler(SimpleHTTPRequestHandler):
    server_version = "MTPresenceServer/1.0"

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON."})
            return None

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/archive/images":
            self.handle_archive_images(parsed)
            return

        if parsed.path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})
            return

        if is_private_static_path(parsed.path):
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

        body = self.read_json_body()
        if body is None:
            return

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

                row = connection.execute("SELECT * FROM archive_image_view WHERE id = ?", (image_id,)).fetchone()
        except sqlite3.Error as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to create image in local archive database."})
            return

        self.send_json(HTTPStatus.CREATED, {"item": archive_image_payload(row), "source": "local-sqlite"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/archive/images":
            self.handle_archive_image_create()
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[:3] == ["api", "archive", "images"]:
            self.handle_archive_image_update(parts[3])
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
