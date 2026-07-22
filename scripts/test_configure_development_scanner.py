#!/usr/bin/env python3
"""Secret-free execution tests for the development scanner configurator."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CONFIGURATOR = ROOT / "scripts" / "configure_development_scanner.py"
TEMPLATE = ROOT / ".env.worker.example"
CURRENT_SECRET = "sb_secret_test_abcdefghijklmnopqrstuvwxyz123456"
LEGACY_SECRET = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


def read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def environment(**values: str) -> dict[str, str]:
    selected = {
        name: value
        for name, value in os.environ.items()
        if name not in {"SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"}
    }
    selected.update(values)
    return selected


def run_configurator(
    web_env: Path,
    output: Path,
    clamav: Path,
    selected_environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CONFIGURATOR),
            "--web-env",
            str(web_env),
            "--template",
            str(TEMPLATE),
            "--output",
            str(output),
            "--clamav-command",
            str(clamav),
        ],
        cwd=ROOT,
        env=selected_environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def assert_secret_absent(result: subprocess.CompletedProcess[str], secret: str) -> None:
    combined = result.stdout + result.stderr
    if secret in combined:
        raise RuntimeError("Scanner configurator exposed a credential")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-scanner-config-") as temporary_name:
        temporary_root = Path(temporary_name)
        web_env = temporary_root / ".env"
        web_env.write_text("SUPABASE_URL=https://project.example.test\n", encoding="utf-8")
        output = temporary_root / ".env.worker"
        fake_clamav = temporary_root / "fake-clamscan"
        fake_clamav.write_text(
            "#!/bin/sh\n"
            "case \"${1:-}\" in\n"
            "  --version) printf '%s\\n' 'ClamAV test version'; exit 0 ;;\n"
            "  *) if [ -f \"$0.fail\" ]; then exit 2; fi; "
            "if [ -n \"${SUPABASE_SECRET_KEY:-}${SUPABASE_SERVICE_ROLE_KEY:-}\" ]; then exit 9; fi; exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_clamav.chmod(0o700)

        result = run_configurator(
            web_env,
            output,
            fake_clamav,
            environment(SUPABASE_SECRET_KEY=CURRENT_SECRET),
        )
        assert_secret_absent(result, CURRENT_SECRET)
        if result.returncode != 0 or "credentials_logged=no" not in result.stdout:
            raise RuntimeError(f"Current secret setup failed: {result.stderr.strip()}")
        configured = read_assignments(output)
        worker_id = configured.get("MT_SCANNER_ID", "")
        if configured.get("SUPABASE_SECRET_KEY") != CURRENT_SECRET:
            raise RuntimeError("Current scanner secret was not written")
        if "SUPABASE_SERVICE_ROLE_KEY" in configured:
            raise RuntimeError("Configurator wrote two privileged credentials")
        if configured.get("SUPABASE_URL") != "https://project.example.test":
            raise RuntimeError("Configurator did not inherit the Web Supabase URL")
        if str(fake_clamav) not in configured.get("MT_SCANNER_CLAMAV_COMMAND", ""):
            raise RuntimeError("Configurator did not write the verified ClamAV command")
        if stat.S_IMODE(output.stat().st_mode) != 0o600:
            raise RuntimeError("Scanner environment is not mode 0600")

        result = run_configurator(
            web_env,
            output,
            fake_clamav,
            environment(SUPABASE_SERVICE_ROLE_KEY=LEGACY_SECRET),
        )
        assert_secret_absent(result, LEGACY_SECRET)
        if result.returncode != 0:
            raise RuntimeError(f"Legacy service-role setup failed: {result.stderr.strip()}")
        configured = read_assignments(output)
        if configured.get("SUPABASE_SERVICE_ROLE_KEY") != LEGACY_SECRET:
            raise RuntimeError("Legacy scanner credential was not written")
        if "SUPABASE_SECRET_KEY" in configured:
            raise RuntimeError("Legacy setup retained the previous current secret")
        if configured.get("MT_SCANNER_ID") != worker_id:
            raise RuntimeError("Reconfiguration changed the stable worker ID")

        original = output.read_bytes()
        result = run_configurator(
            web_env,
            output,
            fake_clamav,
            environment(SUPABASE_SECRET_KEY="sb_publishable_not_a_scanner_secret"),
        )
        assert_secret_absent(result, "sb_publishable_not_a_scanner_secret")
        if result.returncode != 2 or "scanner_secret_invalid" not in result.stderr:
            raise RuntimeError("Publishable key did not fail closed")
        if output.read_bytes() != original:
            raise RuntimeError("Invalid credential overwrote the last valid scanner configuration")

        Path(f"{fake_clamav}.fail").touch()
        result = run_configurator(
            web_env,
            output,
            fake_clamav,
            environment(SUPABASE_SECRET_KEY=CURRENT_SECRET),
        )
        assert_secret_absent(result, CURRENT_SECRET)
        if result.returncode != 2 or "clamav_preflight_failed" not in result.stderr:
            raise RuntimeError("Failed ClamAV preflight did not stop configuration")
        if output.read_bytes() != original:
            raise RuntimeError("Failed ClamAV preflight overwrote the last valid configuration")

    print("scanner_configuration_current_secret=yes")
    print("scanner_configuration_legacy_secret=yes")
    print("scanner_configuration_stable_worker_id=yes")
    print("scanner_configuration_mode_0600=yes")
    print("scanner_configuration_invalid_key_fails_closed=yes")
    print("scanner_configuration_clamav_preflight=yes")
    print("scanner_configuration_secret_logged=no")


if __name__ == "__main__":
    main()
