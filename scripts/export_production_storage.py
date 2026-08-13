#!/usr/bin/env python3
"""Export and verify an allowlisted Supabase Storage inventory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import BinaryIO, Iterable


ALLOWED_BUCKETS = frozenset({
    "image-display",
    "image-originals",
    "image-thumbnails",
    "profile-avatars",
})
INVENTORY_FIELDS = ("bucket_id", "name", "expected_size", "updated_at")
CHUNK_BYTES = 1024 * 1024


class BackupError(RuntimeError):
    """A stable, non-sensitive backup failure."""


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise BackupError("storage_redirect_rejected")


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BackupError(f"missing_environment:{name}")
    return value


def storage_origin() -> str:
    raw = required_environment("SUPABASE_URL").rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    allow_loopback = os.environ.get("MT_OFFSITE_ALLOW_HTTP_LOOPBACK") == "1"
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or (parsed.scheme != "https" and not (allow_loopback and parsed.scheme == "http" and loopback))
    ):
        raise BackupError("storage_origin_invalid")
    return raw


def storage_headers() -> dict[str, str]:
    secret = (
        os.environ.get("SUPABASE_SECRET_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not secret or secret.startswith("sb_publishable_"):
        raise BackupError("storage_secret_invalid")
    headers = {"apikey": secret, "Accept": "application/octet-stream"}
    if not secret.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def safe_storage_name(value: str) -> tuple[str, ...]:
    if (
        not value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise BackupError("storage_name_invalid")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise BackupError("storage_name_invalid")
    return parts


def load_inventory(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if tuple(reader.fieldnames or ()) != INVENTORY_FIELDS:
            raise BackupError("storage_inventory_header_invalid")
        for index, row in enumerate(reader, start=2):
            bucket = (row.get("bucket_id") or "").strip()
            name = row.get("name") or ""
            if bucket not in ALLOWED_BUCKETS:
                raise BackupError(f"storage_inventory_bucket_invalid:{index}")
            safe_storage_name(name)
            identity = (bucket, name)
            if identity in seen:
                raise BackupError(f"storage_inventory_duplicate:{index}")
            seen.add(identity)
            try:
                expected_size = int(row.get("expected_size") or "")
            except ValueError as error:
                raise BackupError(f"storage_inventory_size_invalid:{index}") from error
            if expected_size < 0:
                raise BackupError(f"storage_inventory_size_invalid:{index}")
            rows.append({
                "bucket_id": bucket,
                "name": name,
                "expected_size": expected_size,
                "updated_at": row.get("updated_at") or "",
            })
    return rows


def destination_path(root: Path, bucket: str, name: str) -> Path:
    target = root.joinpath(bucket, *safe_storage_name(name))
    resolved_root = root.resolve()
    if not target.resolve().is_relative_to(resolved_root):
        raise BackupError("storage_destination_invalid")
    return target


def response_stream(
    opener: urllib.request.OpenerDirector,
    origin: str,
    headers: dict[str, str],
    bucket: str,
    name: str,
) -> BinaryIO:
    encoded_bucket = urllib.parse.quote(bucket, safe="")
    encoded_name = urllib.parse.quote(name, safe="/")
    request = urllib.request.Request(
        f"{origin}/storage/v1/object/authenticated/{encoded_bucket}/{encoded_name}",
        headers=headers,
        method="GET",
    )
    try:
        return opener.open(request, timeout=30)
    except BackupError:
        raise
    except urllib.error.HTTPError as error:
        raise BackupError(f"storage_http_error:{error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise BackupError("storage_unavailable") from error


def write_manifest(path: Path, records: Iterable[dict[str, str | int]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        os.chmod(temporary, 0o600)
        for record in records:
            output.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    os.replace(temporary, path)


def export_storage(inventory_path: Path, output_root: Path, manifest_path: Path) -> None:
    rows = load_inventory(inventory_path)
    max_object_bytes = int(os.environ.get("MT_OFFSITE_MAX_OBJECT_BYTES", str(64 * 1024 * 1024)))
    max_total_bytes = int(os.environ.get("MT_OFFSITE_MAX_TOTAL_BYTES", str(1024 * 1024 * 1024 * 1024)))
    if max_object_bytes <= 0 or max_total_bytes <= 0:
        raise BackupError("storage_limit_invalid")
    declared_total = sum(int(row["expected_size"]) for row in rows)
    if any(int(row["expected_size"]) > max_object_bytes for row in rows) or declared_total > max_total_bytes:
        raise BackupError("storage_inventory_limit_exceeded")

    output_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    origin = storage_origin()
    headers = storage_headers()
    opener = urllib.request.build_opener(RejectRedirects(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    records: list[dict[str, str | int]] = []
    total = 0
    for row in rows:
        bucket = str(row["bucket_id"])
        name = str(row["name"])
        expected_size = int(row["expected_size"])
        target = destination_path(output_root, bucket, name)
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        temporary = target.with_name(f".{target.name}.part")
        digest = hashlib.sha256()
        observed_size = 0
        try:
            with response_stream(opener, origin, headers, bucket, name) as response:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) != expected_size:
                            raise BackupError("storage_content_length_mismatch")
                    except ValueError as error:
                        raise BackupError("storage_content_length_invalid") from error
                with temporary.open("xb") as output:
                    os.chmod(temporary, 0o600)
                    while True:
                        chunk = response.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        observed_size += len(chunk)
                        total += len(chunk)
                        if observed_size > expected_size or observed_size > max_object_bytes or total > max_total_bytes:
                            raise BackupError("storage_download_limit_exceeded")
                        digest.update(chunk)
                        output.write(chunk)
            if observed_size != expected_size:
                raise BackupError("storage_size_mismatch")
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        records.append({
            "bucket": bucket,
            "name": name,
            "sha256": digest.hexdigest(),
            "size": observed_size,
        })
    write_manifest(manifest_path, records)
    print(f"storage_backup_objects={len(records)}")
    print(f"storage_backup_bytes={total}")


def load_manifest(path: Path) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    with path.open("r", encoding="utf-8") as input_file:
        for index, line in enumerate(input_file, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise BackupError(f"storage_manifest_invalid:{index}") from error
            if not isinstance(record, dict) or set(record) != {"bucket", "name", "sha256", "size"}:
                raise BackupError(f"storage_manifest_invalid:{index}")
            if record["bucket"] not in ALLOWED_BUCKETS or not isinstance(record["name"], str):
                raise BackupError(f"storage_manifest_invalid:{index}")
            safe_storage_name(record["name"])
            if (
                not isinstance(record["size"], int)
                or record["size"] < 0
                or not isinstance(record["sha256"], str)
                or len(record["sha256"]) != 64
                or any(character not in "0123456789abcdef" for character in record["sha256"])
            ):
                raise BackupError(f"storage_manifest_invalid:{index}")
            records.append(record)
    return records


def verify_storage(inventory_path: Path, output_root: Path, manifest_path: Path) -> None:
    inventory = load_inventory(inventory_path)
    records = load_manifest(manifest_path)
    expected_identities = {(str(row["bucket_id"]), str(row["name"])) for row in inventory}
    manifest_identities = {(str(row["bucket"]), str(row["name"])) for row in records}
    if len(manifest_identities) != len(records) or manifest_identities != expected_identities:
        raise BackupError("storage_manifest_inventory_mismatch")
    expected_paths: set[Path] = set()
    total = 0
    for record in records:
        target = destination_path(output_root, str(record["bucket"]), str(record["name"]))
        if target.is_symlink() or not target.is_file():
            raise BackupError("storage_backup_file_missing")
        digest = hashlib.sha256()
        observed_size = 0
        with target.open("rb") as input_file:
            for chunk in iter(lambda: input_file.read(CHUNK_BYTES), b""):
                observed_size += len(chunk)
                digest.update(chunk)
        if observed_size != record["size"] or digest.hexdigest() != record["sha256"]:
            raise BackupError("storage_backup_checksum_mismatch")
        expected_paths.add(target.resolve())
        total += observed_size
    actual_paths = {path.resolve() for path in output_root.rglob("*") if path.is_file() and not path.is_symlink()}
    if actual_paths != expected_paths or any(path.is_symlink() for path in output_root.rglob("*")):
        raise BackupError("storage_backup_unexpected_file")
    print(f"storage_backup_verified_objects={len(records)}")
    print(f"storage_backup_verified_bytes={total}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("export", "verify"))
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.action == "export":
            export_storage(args.inventory, args.output, args.manifest)
        else:
            verify_storage(args.inventory, args.output, args.manifest)
    except (BackupError, OSError, ValueError) as error:
        print(f"offsite storage backup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
