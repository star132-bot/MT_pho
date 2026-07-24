#!/usr/bin/env python3
"""Install, activate, inspect, and roll back immutable production releases."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from production_release_contract import FORBIDDEN_RELEASE_FILES, REQUIRED_RELEASE_FILES

RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024


def fail(message: str) -> None:
    print(f"release operation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def release_root(value: str) -> Path:
    root = Path(value).resolve()
    if root == Path("/"):
        fail("release root cannot be /")
    return root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_archive_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if not member.name or path.is_absolute() or ".." in path.parts:
        fail("release archive contains an unsafe path")
    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
        fail("release archive contains an unsupported special entry")
    if not (member.isdir() or member.isfile()):
        fail("release archive contains an unsupported entry")


def validate_release_tree(path: Path) -> None:
    missing = sorted(item for item in REQUIRED_RELEASE_FILES if not (path / item).is_file())
    if missing:
        fail(f"release is missing required files: {', '.join(missing)}")
    present_secrets = sorted(item for item in FORBIDDEN_RELEASE_FILES if (path / item).exists())
    if present_secrets:
        fail(f"release contains forbidden environment files: {', '.join(present_secrets)}")
    for candidate in path.rglob("*"):
        if candidate.is_symlink():
            fail("release tree contains a symbolic link")
        if candidate.is_file() or candidate.is_dir():
            candidate.chmod(candidate.stat().st_mode & ~0o022)


def install(args: argparse.Namespace) -> None:
    root = release_root(args.root)
    archive = Path(args.archive).resolve()
    release_id = args.release_id
    expected_sha256 = args.sha256.lower()
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        fail("release id is invalid")
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        fail("expected SHA-256 is invalid")
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES or sha256_file(archive) != expected_sha256:
        fail("release archive checksum does not match")

    releases = root / "releases"
    destination = releases / release_id
    if destination.exists():
        fail("release id is already installed")
    releases.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}-", dir=releases))
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                fail("release archive is empty")
            if len(members) > MAX_ARCHIVE_MEMBERS:
                fail("release archive contains too many entries")
            if sum(member.size for member in members if member.isfile()) > MAX_EXPANDED_BYTES:
                fail("release archive expands beyond the allowed size")
            member_names: set[str] = set()
            for member in members:
                validate_archive_member(member)
                normalized_name = str(PurePosixPath(member.name))
                if normalized_name in member_names:
                    fail("release archive contains duplicate paths")
                member_names.add(normalized_name)
            bundle.extractall(staging)
        validate_release_tree(staging)
        staging.chmod(0o755)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"installed release {release_id} at {destination}")


def symlink_target(link: Path, root: Path) -> Path | None:
    if not link.is_symlink():
        return None
    target = (link.parent / os.readlink(link)).resolve()
    releases = (root / "releases").resolve()
    if target.parent != releases or not target.is_dir():
        return None
    return target


def replace_symlink(link: Path, relative_target: str) -> None:
    temporary = link.with_name(f".{link.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(relative_target)
    os.replace(temporary, link)


def activate(args: argparse.Namespace) -> None:
    root = release_root(args.root)
    release_id = args.release_id
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        fail("release id is invalid")
    destination = root / "releases" / release_id
    if not destination.is_dir():
        fail("release is not installed")
    validate_release_tree(destination)
    root.mkdir(parents=True, exist_ok=True)
    current = root / "current"
    previous = root / "previous"
    current_target = symlink_target(current, root)
    if current_target and current_target != destination:
        replace_symlink(previous, f"releases/{current_target.name}")
    replace_symlink(current, f"releases/{release_id}")
    print(f"activated release {release_id}")


def rollback(args: argparse.Namespace) -> None:
    if os.environ.get("MT_ALLOW_ROLLBACK") != "yes":
        fail("set MT_ALLOW_ROLLBACK=yes after approving the rollback")
    root = release_root(args.root)
    current = root / "current"
    previous = root / "previous"
    current_target = symlink_target(current, root)
    previous_target = symlink_target(previous, root)
    if not current_target or not previous_target or current_target == previous_target:
        fail("a distinct current and previous release are required")
    validate_release_tree(previous_target)
    replace_symlink(current, f"releases/{previous_target.name}")
    replace_symlink(previous, f"releases/{current_target.name}")
    print(f"rolled back to release {previous_target.name}")


def status(args: argparse.Namespace) -> None:
    root = release_root(args.root)
    for name in ("current", "previous"):
        target = symlink_target(root / name, root)
        print(f"{name}={target.name if target else 'unavailable'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage immutable MT Presence production releases.")
    parser.add_argument("--root", default="/opt/mt-presence")
    subcommands = parser.add_subparsers(dest="command", required=True)

    install_parser = subcommands.add_parser("install")
    install_parser.add_argument("--archive", required=True)
    install_parser.add_argument("--sha256", required=True)
    install_parser.add_argument("--release-id", required=True)
    install_parser.set_defaults(handler=install)

    activate_parser = subcommands.add_parser("activate")
    activate_parser.add_argument("--release-id", required=True)
    activate_parser.set_defaults(handler=activate)

    rollback_parser = subcommands.add_parser("rollback")
    rollback_parser.set_defaults(handler=rollback)

    status_parser = subcommands.add_parser("status")
    status_parser.set_defaults(handler=status)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
