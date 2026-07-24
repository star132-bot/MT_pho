#!/usr/bin/env python3
"""Filesystem-only acceptance test for immutable production releases."""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from production_release_contract import REQUIRED_RELEASE_FILES

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts" / "manage_production_release.py"
REQUIRED = REQUIRED_RELEASE_FILES


def archive(
    root: Path,
    name: str,
    *,
    unsafe: bool = False,
    secret: bool = False,
    omit: str | None = None,
) -> tuple[Path, str]:
    output = root / f"{name}.tar.gz"
    with tarfile.open(output, "w:gz") as bundle:
        for path in sorted(REQUIRED):
            if path == omit:
                continue
            payload = f"fixture:{name}:{path}\n".encode()
            info = tarfile.TarInfo(path)
            info.size = len(payload)
            info.mode = 0o755 if path.endswith(".py") else 0o644
            bundle.addfile(info, io.BytesIO(payload))
        if secret:
            payload = b"SECRET=value\n"
            info = tarfile.TarInfo(".env")
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))
        if unsafe:
            payload = b"escape\n"
            info = tarfile.TarInfo("../escape")
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))
    return output, hashlib.sha256(output.read_bytes()).hexdigest()


def run(base: Path, *arguments: str, success: bool = True, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(MANAGER), "--root", str(base), *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if (result.returncode == 0) != success:
        raise AssertionError(f"unexpected release command result: {result.stdout}\n{result.stderr}")
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-production-release-") as temporary:
        temp = Path(temporary)
        base = temp / "runtime"
        first, first_hash = archive(temp, "v1.0.0")
        second, second_hash = archive(temp, "v1.1.0")

        run(base, "install", "--archive", str(first), "--sha256", first_hash, "--release-id", "v1.0.0")
        assert (base / "releases" / "v1.0.0").stat().st_mode & 0o055 == 0o055
        run(base, "activate", "--release-id", "v1.0.0")
        assert (base / "current").resolve().name == "v1.0.0"

        run(base, "install", "--archive", str(second), "--sha256", second_hash, "--release-id", "v1.1.0")
        run(base, "activate", "--release-id", "v1.1.0")
        assert (base / "current").resolve().name == "v1.1.0"
        assert (base / "previous").resolve().name == "v1.0.0"

        run(base, "rollback", success=False)
        rollback_environment = dict(os.environ, MT_ALLOW_ROLLBACK="yes")
        run(base, "rollback", environment=rollback_environment)
        assert (base / "current").resolve().name == "v1.0.0"
        assert (base / "previous").resolve().name == "v1.1.0"

        status = run(base, "status")
        assert "current=v1.0.0" in status.stdout
        assert "previous=v1.1.0" in status.stdout

        unsafe, unsafe_hash = archive(temp, "unsafe", unsafe=True)
        run(base, "install", "--archive", str(unsafe), "--sha256", unsafe_hash, "--release-id", "unsafe", success=False)
        assert not (temp / "escape").exists()

        secret, secret_hash = archive(temp, "secret", secret=True)
        run(base, "install", "--archive", str(secret), "--sha256", secret_hash, "--release-id", "secret", success=False)
        incomplete, incomplete_hash = archive(
            temp,
            "incomplete",
            omit="database/migrations/20260723_admin_works_governance.sql",
        )
        run(
            base,
            "install",
            "--archive",
            str(incomplete),
            "--sha256",
            incomplete_hash,
            "--release-id",
            "incomplete",
            success=False,
        )
        run(base, "install", "--archive", str(first), "--sha256", "0" * 64, "--release-id", "bad-checksum", success=False)

    print("Production release manager acceptance passed (install/activate/rollback/archive safety).")


if __name__ == "__main__":
    main()
