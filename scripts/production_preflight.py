#!/usr/bin/env python3
"""Fail-closed runtime checks used by the production systemd services."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from production_release_contract import FORBIDDEN_RELEASE_FILES, REQUIRED_RELEASE_FILES


ROOT = Path(__file__).resolve().parents[1]
SCANNER_TEMP_ROOT = Path("/var/lib/mt-presence-scanner")
SCANNER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,119}$")


def fail(message: str) -> None:
    print(f"production preflight failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        fail(f"{name} is missing or invalid")
    return value


def require_https_origin(name: str, *, allow_path: bool) -> str:
    value = required_environment(name)
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (not allow_path and parsed.path not in {"", "/"})
    ):
        fail(f"{name} must be an HTTPS origin without credentials or query data")
    return value.rstrip("/")


def require_release_files() -> None:
    missing = sorted(path for path in REQUIRED_RELEASE_FILES if not (ROOT / path).is_file())
    if missing:
        fail(f"release is incomplete: {', '.join(missing)}")
    for private_file in FORBIDDEN_RELEASE_FILES:
        if (ROOT / private_file).exists():
            fail(f"{private_file} must not be packaged in a production release")


def check_web() -> None:
    require_release_files()
    if required_environment("MT_RUNTIME_ENVIRONMENT") != "production":
        fail("MT_RUNTIME_ENVIRONMENT must be production")
    if os.environ.get("MT_LOCAL_ARCHIVE_PREVIEW", "").strip() not in {"", "0"}:
        fail("MT_LOCAL_ARCHIVE_PREVIEW must be disabled in production")
    if required_environment("MT_COOKIE_SECURE") != "1":
        fail("MT_COOKIE_SECURE must be 1")
    if required_environment("MT_TRUST_PROXY") != "1":
        fail("MT_TRUST_PROXY must be 1 behind the production reverse proxy")
    try:
        maximum_threads = int(required_environment("MT_MAX_REQUEST_THREADS"))
    except ValueError:
        fail("MT_MAX_REQUEST_THREADS must be an integer")
    if not 4 <= maximum_threads <= 128:
        fail("MT_MAX_REQUEST_THREADS must be between 4 and 128")
    require_https_origin("MT_PUBLIC_BASE_URL", allow_path=False)
    require_https_origin("SUPABASE_URL", allow_path=True)
    publishable_key = required_environment("SUPABASE_PUBLISHABLE_KEY")
    lowered_key = publishable_key.lower()
    if "service_role" in lowered_key or lowered_key.startswith("sb_secret_"):
        fail("the Web process must use a publishable Supabase key")
    forbidden = [name for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "PGPASSWORD") if os.environ.get(name)]
    if forbidden:
        fail(f"privileged credentials are forbidden in the Web process: {', '.join(forbidden)}")


def check_scanner() -> None:
    require_release_files()
    require_https_origin("SUPABASE_URL", allow_path=True)
    secret_names = [
        name for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
        if os.environ.get(name, "").strip()
    ]
    if not secret_names:
        fail("the isolated scanner credential is missing")
    if len(secret_names) != 1:
        fail("configure exactly one isolated scanner credential")
    scanner_secret = required_environment(secret_names[0])
    if scanner_secret.lower().startswith("sb_publishable_"):
        fail("the scanner credential must not be a publishable key")
    scanner_id = required_environment("MT_SCANNER_ID")
    if not SCANNER_ID_PATTERN.fullmatch(scanner_id):
        fail("MT_SCANNER_ID is invalid")
    try:
        scanner_command = shlex.split(required_environment("MT_SCANNER_CLAMAV_COMMAND"))
    except ValueError:
        fail("MT_SCANNER_CLAMAV_COMMAND is invalid")
    if (
        not scanner_command
        or Path(scanner_command[0]).name not in {"clamdscan", "clamscan"}
        or not shutil.which(scanner_command[0])
    ):
        fail("MT_SCANNER_CLAMAV_COMMAND must select an available ClamAV scanner")
    if "--fdpass" in scanner_command:
        fail("MT_SCANNER_CLAMAV_COMMAND must not use --fdpass inside the hardened production mount namespace")
    temp_dir = Path(required_environment("MT_SCANNER_TEMP_DIR")).resolve()
    allowed_root = SCANNER_TEMP_ROOT.resolve()
    if temp_dir != allowed_root and allowed_root not in temp_dir.parents:
        fail("MT_SCANNER_TEMP_DIR must stay below /var/lib/mt-presence-scanner")
    if not temp_dir.is_dir() or not os.access(temp_dir, os.W_OK):
        fail("the scanner temporary directory is not writable")
    if importlib.util.find_spec("PIL") is None:
        fail("Pillow is unavailable in the scanner environment")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate MT Presence production runtime configuration.")
    parser.add_argument("--runtime", choices=("web", "scanner"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if sys.version_info < (3, 11):
        fail("Python 3.11 or newer is required")
    if args.runtime == "web":
        check_web()
    else:
        check_scanner()
    print(f"production {args.runtime} preflight passed")


if __name__ == "__main__":
    main()
