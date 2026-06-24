#!/usr/bin/env python3
"""Validate the local SQLite archive database workflow."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "scripts" / "seed_local_archive_db.py"
ARCHIVE_DATA_PATH = ROOT / "archive-data.js"

EXPECTED_TABLES = {
    "ratio_categories",
    "artists",
    "images",
    "image_assets",
    "image_square_slices",
    "image_analysis_events",
    "image_tags",
    "image_taggings",
    "collections",
    "collection_images",
}

EXPECTED_TAG_GROUPS = {
    "Subject",
    "Form / Ratio",
    "Mood",
    "Palette / Tone",
    "Series / Collection",
}

RATIO_CODE_BY_LABEL = {
    "1:1": "one_to_one",
    "4:3": "four_to_three",
    "4:5": "four_to_five",
    "2:3": "two_to_three",
    "3:2": "three_to_two",
    "16:9": "sixteen_to_nine",
    "Panorama": "panorama",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def run_seed(db_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT), "--db", str(db_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    print(result.stdout.strip())


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
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def scalar(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int | str | None:
    return connection.execute(sql, params).fetchone()[0]


def validate_schema(connection: sqlite3.Connection) -> None:
    integrity = scalar(connection, "PRAGMA integrity_check")
    if integrity != "ok":
        fail(f"SQLite integrity_check failed: {integrity}")

    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        fail(f"SQLite foreign_key_check failed: {foreign_key_rows}")

    actual_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    missing_tables = sorted(EXPECTED_TABLES - actual_tables)
    if missing_tables:
        fail(f"Missing expected tables: {', '.join(missing_tables)}")

    view_exists = scalar(
        connection,
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'view' AND name = 'archive_image_view'",
    )
    if view_exists != 1:
        fail("Missing archive_image_view.")


def validate_counts(connection: sqlite3.Connection, sample_items: list[dict]) -> None:
    expected_images = len(sample_items)
    expected_assets = expected_images * 3
    required_counts = {
        "images": expected_images,
        "image_assets": expected_assets,
        "collection_images": expected_images,
        "image_analysis_events": expected_images,
    }
    for table, expected in required_counts.items():
        count = scalar(connection, f"SELECT COUNT(*) FROM {table}")
        if count != expected:
            fail(f"{table} count mismatch: expected {expected}, got {count}.")

    published_count = scalar(connection, "SELECT COUNT(*) FROM archive_image_view WHERE visibility = 'published'")
    if published_count != expected_images:
        fail(f"archive_image_view published count mismatch: expected {expected_images}, got {published_count}.")

    tag_count = scalar(connection, "SELECT COUNT(*) FROM image_tags")
    tagging_count = scalar(connection, "SELECT COUNT(*) FROM image_taggings")
    if tag_count <= 0 or tagging_count < expected_images:
        fail(f"Tag seed is incomplete: image_tags={tag_count}, image_taggings={tagging_count}.")


def validate_assets(connection: sqlite3.Connection) -> None:
    incomplete_assets = connection.execute(
        """
        SELECT image_id, group_concat(kind, ',') AS kinds
        FROM image_assets
        GROUP BY image_id
        HAVING SUM(kind = 'original') != 1
          OR SUM(kind = 'display') != 1
          OR SUM(kind = 'thumbnail') != 1
        """
    ).fetchall()
    if incomplete_assets:
        fail(f"Images missing required original/display/thumbnail assets: {incomplete_assets}")

    missing_urls = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM archive_image_view
        WHERE image_url IS NULL
           OR thumbnail_url IS NULL
           OR original_url IS NULL
        """,
    )
    if missing_urls:
        fail(f"archive_image_view has {missing_urls} rows with missing image URLs.")

    missing_files = []
    for asset_id, public_url in connection.execute("SELECT id, public_url FROM image_assets"):
        if public_url and not (ROOT / public_url).exists():
            missing_files.append(f"{asset_id}:{public_url}")
    if missing_files:
        fail(f"Asset public_url paths do not exist: {', '.join(missing_files[:10])}")


def validate_archive_view(connection: sqlite3.Connection, sample_items: list[dict]) -> None:
    expected_ratio_by_id = {
        item["id"]: RATIO_CODE_BY_LABEL[item["ratio"]]
        for item in sample_items
    }
    mismatched_ratios = []
    for image_id, ratio_code in connection.execute("SELECT id, ratio_category_code FROM images"):
        if expected_ratio_by_id.get(image_id) != ratio_code:
            mismatched_ratios.append((image_id, expected_ratio_by_id.get(image_id), ratio_code))
    if mismatched_ratios:
        fail(f"Ratio category mismatches: {mismatched_ratios[:10]}")

    display_mode_violations = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM images
        WHERE (content_type = 'abstract' AND display_mode != 'black_white')
           OR (content_type = 'concrete' AND display_mode != 'color')
        """,
    )
    if display_mode_violations:
        fail(f"Found {display_mode_violations} content_type/display_mode violations.")

    required_ratio_codes = set(RATIO_CODE_BY_LABEL.values())
    actual_ratio_codes = {
        row[0]
        for row in connection.execute("SELECT DISTINCT ratio_category_code FROM archive_image_view")
    }
    missing_ratio_codes = sorted(required_ratio_codes - actual_ratio_codes)
    if missing_ratio_codes:
        fail(f"archive_image_view does not cover ratio categories: {', '.join(missing_ratio_codes)}")

    rows = connection.execute("SELECT id, tags, tag_groups FROM archive_image_view").fetchall()
    for image_id, tags_json, tag_groups_json in rows:
        tags = json.loads(tags_json)
        tag_groups = json.loads(tag_groups_json)
        if not isinstance(tags, list) or not tags:
            fail(f"{image_id} has empty or invalid tags JSON.")
        if not isinstance(tag_groups, list) or not tag_groups:
            fail(f"{image_id} has empty or invalid tag_groups JSON.")
        actual_groups = {group.get("label") for group in tag_groups if isinstance(group, dict)}
        missing_groups = EXPECTED_TAG_GROUPS - actual_groups
        if missing_groups:
            fail(f"{image_id} tag_groups missing required groups: {', '.join(sorted(missing_groups))}")


def validate_database(db_path: Path) -> None:
    archive_data = load_archive_data()
    sample_items = archive_data.get("sampleItems") or []
    if not sample_items:
        fail("archive-data.js did not provide sampleItems.")

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        validate_schema(connection)
        validate_counts(connection, sample_items)
        validate_assets(connection)
        validate_archive_view(connection, sample_items)

    print(f"Validated local archive database at {db_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed and validate the MT Presence local archive SQLite database.")
    parser.add_argument("--db", help="Optional fresh SQLite path to create for validation.")
    parser.add_argument("--keep-db", action="store_true", help="Keep a generated temporary database for inspection.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    temp_dir = None

    if args.db:
        db_path = Path(args.db).resolve()
        if db_path.exists():
            fail(f"Refusing to overwrite existing database: {db_path}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        if args.keep_db:
            db_path = Path(tempfile.mkdtemp(prefix="mt-presence-db-")) / "archive.db"
        else:
            temp_dir = tempfile.TemporaryDirectory(prefix="mt-presence-db-")
            db_path = Path(temp_dir.name) / "archive.db"

    try:
        run_seed(db_path)
        validate_database(db_path)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Database validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
