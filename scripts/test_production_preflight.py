#!/usr/bin/env python3
"""Unit acceptance for the fail-closed production Web preflight."""

from __future__ import annotations

import importlib.util
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from production_release_contract import REQUIRED_RELEASE_FILES


SCRIPT = Path(__file__).with_name("production_preflight.py")
SPEC = importlib.util.spec_from_file_location("mt_production_preflight", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("production preflight module is unavailable")
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


VALID_ENVIRONMENT = {
    "MT_RUNTIME_ENVIRONMENT": "production",
    "MT_COOKIE_SECURE": "1",
    "MT_TRUST_PROXY": "1",
    "MT_MAX_REQUEST_THREADS": "32",
    "MT_PUBLIC_BASE_URL": "https://portfolio.example.com",
    "SUPABASE_URL": "https://project.example.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture",
}

VALID_SCANNER_ENVIRONMENT = {
    "SUPABASE_URL": "https://project.example.supabase.co",
    "SUPABASE_SECRET_KEY": "sb_secret_scanner_fixture",
    "MT_SCANNER_ID": "production-scanner-01",
    "MT_SCANNER_CLAMAV_COMMAND": "clamscan --no-summary",
}


@contextmanager
def environment(values: dict[str, str]):
    names = set(VALID_ENVIRONMENT) | set(VALID_SCANNER_ENVIRONMENT) | {
        "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "PGPASSWORD",
        "MT_SCANNER_WORKER_ID", "MT_SCANNER_TEMP_DIR", "MT_LOCAL_ARCHIVE_PREVIEW",
    }
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ.pop(name, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for name in names:
            os.environ.pop(name, None)
            if previous[name] is not None:
                os.environ[name] = previous[name] or ""


def expect_failure(values: dict[str, str]) -> None:
    try:
        with environment(values):
            PREFLIGHT.check_web()
    except SystemExit as error:
        if error.code != 1:
            raise
        return
    raise AssertionError("production Web preflight unexpectedly accepted unsafe configuration")


def main() -> None:
    original_root = PREFLIGHT.ROOT
    original_scanner_temp_root = PREFLIGHT.SCANNER_TEMP_ROOT
    try:
        with tempfile.TemporaryDirectory(prefix="mt-production-preflight-") as temporary:
            root = Path(temporary)
            for relative in REQUIRED_RELEASE_FILES:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture\n", encoding="utf-8")
            PREFLIGHT.ROOT = root

            with environment(VALID_ENVIRONMENT):
                PREFLIGHT.check_web()

            expect_failure({**VALID_ENVIRONMENT, "MT_COOKIE_SECURE": "0"})
            expect_failure({**VALID_ENVIRONMENT, "MT_LOCAL_ARCHIVE_PREVIEW": "1"})
            expect_failure({**VALID_ENVIRONMENT, "MT_TRUST_PROXY": "0"})
            expect_failure({**VALID_ENVIRONMENT, "MT_MAX_REQUEST_THREADS": "512"})
            expect_failure({**VALID_ENVIRONMENT, "MT_PUBLIC_BASE_URL": "http://portfolio.example.com"})
            expect_failure({**VALID_ENVIRONMENT, "SUPABASE_PUBLISHABLE_KEY": "sb_secret_fixture"})
            expect_failure({**VALID_ENVIRONMENT, "PGPASSWORD": "forbidden"})

            (root / ".env").write_text("SECRET=forbidden\n", encoding="utf-8")
            expect_failure(VALID_ENVIRONMENT)
            (root / ".env").unlink()

            scanner_temp = root / "scanner-temp"
            scanner_temp.mkdir()
            PREFLIGHT.SCANNER_TEMP_ROOT = scanner_temp
            scanner_environment = {
                **VALID_SCANNER_ENVIRONMENT,
                "MT_SCANNER_TEMP_DIR": str(scanner_temp),
            }
            with (
                environment(scanner_environment),
                mock.patch.object(PREFLIGHT.shutil, "which", return_value="/usr/bin/clamscan"),
                mock.patch.object(PREFLIGHT.importlib.util, "find_spec", return_value=object()),
            ):
                PREFLIGHT.check_scanner()
            for name, value in (
                ("MT_SCANNER_ID", "invalid scanner id"),
                ("MT_SCANNER_CLAMAV_COMMAND", "curl https://example.com"),
                ("MT_SCANNER_CLAMAV_COMMAND", "clamdscan --fdpass --no-summary"),
                ("SUPABASE_SECRET_KEY", "sb_publishable_wrong_boundary"),
            ):
                invalid = {**scanner_environment, name: value}
                try:
                    with (
                        environment(invalid),
                        mock.patch.object(PREFLIGHT.shutil, "which", return_value="/usr/bin/clamscan"),
                        mock.patch.object(PREFLIGHT.importlib.util, "find_spec", return_value=object()),
                    ):
                        PREFLIGHT.check_scanner()
                except SystemExit as error:
                    if error.code != 1:
                        raise
                else:
                    raise AssertionError(f"scanner preflight accepted invalid {name}")
    finally:
        PREFLIGHT.ROOT = original_root
        PREFLIGHT.SCANNER_TEMP_ROOT = original_scanner_temp_root

    print("Production preflight acceptance passed (Web + scanner fail-closed boundaries).")


if __name__ == "__main__":
    main()
