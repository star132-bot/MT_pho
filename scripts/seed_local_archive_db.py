#!/usr/bin/env python3
"""Seed the local SQLite archive database from archive-data.js."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "archive.db"
SCHEMA_PATH = ROOT / "database" / "local_archive_schema.sql"
ARCHIVE_DATA_PATH = ROOT / "archive-data.js"
SEED_ARTIST_ID = "artist-mt-presence"
SEED_COLLECTION_ID = "collection-archive-featured"
SEED_COLLECTION_SLUG = "archive-featured"

RATIO_CATEGORIES = [
    ("one_to_one", "1:1", 1, 1, 10),
    ("four_to_three", "4:3", 4, 3, 5),
    ("four_to_five", "4:5", 4, 5, 20),
    ("two_to_three", "2:3", 2, 3, 30),
    ("three_to_two", "3:2", 3, 2, 40),
    ("sixteen_to_nine", "16:9", 16, 9, 50),
    ("panorama", "Panorama", 2, 1, 60),
]

RATIO_CODE_BY_LABEL = {
    "1:1": "one_to_one",
    "4:3": "four_to_three",
    "4:5": "four_to_five",
    "2:3": "two_to_three",
    "3:2": "three_to_two",
    "16:9": "sixteen_to_nine",
    "Panorama": "panorama",
}

GROUP_SORT_ORDER = {
    "Subject": 10,
    "Place": 20,
    "Form / Ratio": 30,
    "Mood": 40,
    "Material / Surface": 50,
    "Palette / Tone": 60,
    "Series / Collection": 70,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def seed_time(index: int) -> str:
    return datetime(2026, 6, 6, 0, 0, index, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def load_archive_data() -> dict:
    node_script = """
const fs = require('fs');
const vm = require('vm');
const filePath = process.argv[1];
const context = { window: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(filePath, 'utf8'), context, { filename: filePath });
process.stdout.write(JSON.stringify(context.window.MTPresenceArchiveData || {}));
"""
    result = subprocess.run(
        ["node", "-e", node_script, str(ARCHIVE_DATA_PATH)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_size(path: Path) -> int | None:
    return path.stat().st_size if path.exists() else None


def content_type_code(value: str) -> str:
    return "abstract" if value.strip().lower() == "abstract" else "concrete"


def display_mode_for_type(value: str) -> str:
    return "black_white" if content_type_code(value) == "abstract" else "color"


def orientation_for_ratio(ratio_label: str, width: int, height: int) -> str:
    if ratio_label == "Panorama":
        return "Panorama"
    if width == height:
        return "Square"
    if height > width:
        return "Vertical"
    return "Horizontal"


def title_contains(title: str, tokens: list[str]) -> bool:
    lower = title.lower()
    return any(token in lower for token in tokens)


def title_subject_tags(title: str, content_type: str) -> list[str]:
    lower = title.lower()
    type_label = "Abstract" if content_type == "abstract" else "Concrete"
    tags = [type_label]
    if content_type == "abstract":
        tags.append("Abstract Study")
    if title_contains(title, ["landscape", "valley", "coast", "weather", "horizon", "panorama", "field", "mountain", "snow", "sky", "wide"]):
        tags.append("Landscape")
    if title_contains(title, ["architect", "building", "house", "home", "room", "interior", "facade", "roof", "wall", "window"]):
        tags.extend(["House / Building", "Architecture"])
    if title_contains(title, ["coast", "water", "sea", "shore", "ocean"]):
        tags.append("Coast / Water")
    if title_contains(title, ["valley", "mountain", "snow"]):
        tags.append("Mountain / Valley")
    if "animal" in lower:
        tags.append("Animal")
    if "object" in lower:
        tags.append("Object")
    if title_contains(title, ["stone", "rock"]):
        tags.append("Stone")
    if title_contains(title, ["surface", "pattern", "plane", "shadow", "light", "interval"]):
        tags.append("Surface / Pattern")
    if len(tags) == 1:
        tags.append("Surface / Pattern" if content_type == "abstract" else "Observed World")
    return unique(tags)


def place_tags(title: str) -> list[str]:
    tags: list[str] = []
    if title_contains(title, ["landscape", "valley", "coast", "weather", "horizon", "panorama", "field", "mountain", "snow", "sky", "wide"]):
        tags.append("Natural Landscape")
    if title_contains(title, ["architect", "building", "house", "home", "room", "interior", "facade", "roof", "wall", "window"]):
        tags.append("Built Environment")
    if title_contains(title, ["coast", "water", "sea", "shore", "ocean"]):
        tags.append("Coast")
    if title_contains(title, ["valley", "mountain", "snow"]):
        tags.append("Valley")
    return unique(tags)


def material_surface_tags(title: str) -> list[str]:
    tags: list[str] = []
    if title_contains(title, ["stone", "rock"]):
        tags.append("Stone")
    return unique(tags)


def mood_tags(title: str) -> list[str]:
    lower = title.lower()
    candidates = [
        ("shadow", "Shadow"),
        ("light", "Light"),
        ("minimal", "Minimal"),
        ("silence", "Silence"),
        ("weather", "Weather"),
        ("balanced", "Balance"),
        ("wide", "Open Space"),
        ("long", "Open Horizon"),
        ("horizon", "Open Horizon"),
        ("vertical", "Vertical Stillness"),
        ("tall", "Vertical Stillness"),
        ("interval", "Interval"),
        ("field", "Field"),
        ("plane", "Plane"),
        ("surface", "Surface"),
    ]
    tags = [label for token, label in candidates if token in lower]
    return tags or ["Quiet Observation"]


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = value.strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def build_tag_groups(item: dict) -> list[dict]:
    title = item["title"]
    content_type = content_type_code(item["type"])
    type_label = "Abstract" if content_type == "abstract" else "Concrete"
    ratio_label = item["ratio"]
    orientation = orientation_for_ratio(ratio_label, int(item["width"]), int(item["height"]))
    tone = "Black and white" if content_type == "abstract" else "Color"
    display_tone = "Monochrome" if content_type == "abstract" else "Color"
    archive_label = f"{type_label} Archive"

    return [
        {"label": "Subject", "tags": title_subject_tags(title, content_type)},
        {"label": "Place", "tags": place_tags(title)},
        {"label": "Form / Ratio", "tags": unique([ratio_label, orientation])},
        {"label": "Mood", "tags": mood_tags(title)},
        {"label": "Material / Surface", "tags": material_surface_tags(title)},
        {"label": "Palette / Tone", "tags": unique([tone, display_tone])},
        {"label": "Series / Collection", "tags": unique(["Local Sample", archive_label])},
    ]


def execute_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def seed_static_tables(connection: sqlite3.Connection) -> None:
    timestamp = now_iso()
    connection.executemany(
        """
        INSERT INTO ratio_categories (code, label, numerator, denominator, target_aspect_ratio, sort_order)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
          label = excluded.label,
          numerator = excluded.numerator,
          denominator = excluded.denominator,
          target_aspect_ratio = excluded.target_aspect_ratio,
          sort_order = excluded.sort_order
        """,
        [(code, label, num, den, num / den, sort_order) for code, label, num, den, sort_order in RATIO_CATEGORIES],
    )
    connection.execute(
        """
        INSERT INTO artists (id, display_name, slug, email, bio, website_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          display_name = excluded.display_name,
          slug = excluded.slug,
          email = excluded.email,
          bio = excluded.bio,
          website_url = excluded.website_url,
          updated_at = excluded.updated_at
        """,
        (
            SEED_ARTIST_ID,
            "MT Presence",
            "mt-presence",
            None,
            "Fine art photography archive for MT Presence.",
            None,
            timestamp,
            timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO collections (id, artist_id, slug, title, description, is_featured, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          artist_id = excluded.artist_id,
          slug = excluded.slug,
          title = excluded.title,
          description = excluded.description,
          is_featured = excluded.is_featured,
          updated_at = excluded.updated_at
        """,
        (
            SEED_COLLECTION_ID,
            SEED_ARTIST_ID,
            SEED_COLLECTION_SLUG,
            "Archive Featured",
            "Local seed collection built from archive-data.js sampleItems.",
            1,
            timestamp,
            timestamp,
        ),
    )


def clear_seed_rows(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM collection_images WHERE image_id IN (SELECT id FROM images WHERE source_type = 'local_sample')")
    connection.execute("DELETE FROM image_analysis_events WHERE image_id IN (SELECT id FROM images WHERE source_type = 'local_sample')")
    connection.execute("DELETE FROM images WHERE source_type = 'local_sample'")
    connection.execute("DELETE FROM image_tags WHERE id NOT IN (SELECT tag_id FROM image_taggings)")


def upsert_tag(connection: sqlite3.Connection, group_name: str, tag_name: str, group_sort: int) -> str:
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
        (tag_id, tag_name, tag_slug, group_name, group_sort, now_iso()),
    )
    return tag_id


def seed_item(connection: sqlite3.Connection, item: dict, index: int) -> None:
    image_id = item["id"]
    title = item["title"]
    src = item["src"]
    width = int(item["width"])
    height = int(item["height"])
    ratio_label = item["ratio"]
    ratio_code = RATIO_CODE_BY_LABEL[ratio_label]
    content_type = content_type_code(item["type"])
    display_mode = display_mode_for_type(content_type)
    created_at = seed_time(index)
    asset_path = ROOT / src
    byte_size = file_size(asset_path)
    checksum = file_sha256(asset_path)
    mime_type = mimetypes.guess_type(src)[0] or "image/jpeg"

    connection.execute(
        """
        INSERT INTO images (
          id, artist_id, title, slug, description, curatorial_note, artist_statement, series,
          source_type, visibility, original_filename, original_width, original_height,
          original_aspect_ratio, ratio_category_code, display_ratio_override, content_type,
          display_mode, ai_model, ai_confidence, ai_analysis, exif, sort_order, captured_at,
          uploaded_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            image_id,
            SEED_ARTIST_ID,
            title,
            slugify(title, image_id),
            "",
            "",
            "",
            "",
            "local_sample",
            "published",
            src,
            width,
            height,
            width / height,
            ratio_code,
            None,
            content_type,
            display_mode,
            "local-seed",
            1.0,
            json.dumps({"source": "archive-data.js", "content_type": content_type}, ensure_ascii=False),
            "{}",
            index,
            None,
            created_at,
            created_at,
            created_at,
        ),
    )

    original_asset_id = f"{image_id}-original"
    asset_rows = [
        (original_asset_id, "original", None),
        (f"{image_id}-display", "display", original_asset_id),
        (f"{image_id}-thumbnail", "thumbnail", original_asset_id),
    ]
    for asset_id, kind, source_asset_id in asset_rows:
        connection.execute(
            """
            INSERT INTO image_assets (
              id, image_id, kind, storage_bucket, storage_path, public_url, url_expires_at,
              mime_type, byte_size, width, height, checksum_sha256, source_asset_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                image_id,
                kind,
                f"local-assets-{kind}",
                f"{kind}/{src}",
                src,
                None,
                mime_type,
                byte_size,
                width,
                height,
                checksum,
                source_asset_id,
                created_at,
            ),
        )

    tag_groups = build_tag_groups(item)
    tag_order = 0
    for group in tag_groups:
        group_name = group["label"]
        group_sort = GROUP_SORT_ORDER[group_name]
        for tag_name in group["tags"]:
            tag_id = upsert_tag(connection, group_name, tag_name, group_sort)
            connection.execute(
                """
                INSERT INTO image_taggings (image_id, tag_id, sort_order, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(image_id, tag_id) DO UPDATE SET
                  sort_order = excluded.sort_order
                """,
                (image_id, tag_id, tag_order, created_at),
            )
            tag_order += 1

    connection.execute(
        """
        INSERT INTO image_analysis_events (
          id, image_id, input_asset_id, provider, model_name, content_type, confidence, result, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{image_id}-seed-analysis",
            image_id,
            original_asset_id,
            "local-seed",
            "archive-data-derived-tags-v1",
            content_type,
            1.0,
            json.dumps({"tag_groups": tag_groups, "ratio": ratio_label}, ensure_ascii=False),
            created_at,
        ),
    )

    connection.execute(
        """
        INSERT INTO collection_images (collection_id, image_id, sort_order, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(collection_id, image_id) DO UPDATE SET
          sort_order = excluded.sort_order
        """,
        (SEED_COLLECTION_ID, image_id, index, created_at),
    )


def validate_seed(connection: sqlite3.Connection, expected_images: int) -> dict:
    counts = {}
    for table in [
        "images",
        "image_assets",
        "image_tags",
        "image_taggings",
        "collections",
        "collection_images",
        "image_analysis_events",
    ]:
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    visible_rows = connection.execute("SELECT COUNT(*) FROM archive_image_view WHERE visibility = 'published'").fetchone()[0]
    counts["archive_image_view_published"] = visible_rows
    if counts["images"] < expected_images or visible_rows < expected_images:
        raise RuntimeError(f"Seed validation failed: expected at least {expected_images} published images, got {visible_rows}.")
    if counts["image_taggings"] == 0:
        raise RuntimeError("Seed validation failed: no image_taggings were inserted.")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MT Presence local archive SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    archive_data = load_archive_data()
    sample_items = archive_data.get("sampleItems") or []
    if not sample_items:
        raise RuntimeError("archive-data.js did not provide sampleItems.")

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        execute_schema(connection)
        with connection:
            seed_static_tables(connection)
            clear_seed_rows(connection)
            for index, item in enumerate(sample_items):
                seed_item(connection, item, index)
            counts = validate_seed(connection, len(sample_items))

    print(f"Seeded {len(sample_items)} images into {db_path}")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
