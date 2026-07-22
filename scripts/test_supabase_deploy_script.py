#!/usr/bin/env python3
"""Secret-free execution test for the Phase 1 deployment entry point."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_supabase_phase1.sh"


def run_deploy(
    fake_bin: Path,
    log_path: Path,
    baseline: str,
    *,
    fail_match: str = "",
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "PGHOST": "database.example.test",
        "PGDATABASE": "postgres",
        "PGUSER": "deployment-test",
        "PGPASSWORD": "not-a-real-secret",
        "MT_DEPLOY_ENVIRONMENT": "development",
        "MT_APPLY_PHASE1_BASELINE": baseline,
        "MT_PSQL_LOG": str(log_path),
        "MT_PSQL_FAIL_MATCH": fail_match,
    }
    return subprocess.run(
        ["bash", str(DEPLOY_SCRIPT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def logged_files(log_path: Path) -> list[str]:
    return [
        Path(value).name
        for line in log_path.read_text().splitlines()
        for value in re.findall(r"--file ([^ ]+)", line)
    ]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-deploy-script-") as temp_name:
        temp_root = Path(temp_name)
        fake_bin = temp_root / "bin"
        fake_bin.mkdir()
        fake_psql = fake_bin / "psql"
        fake_psql.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$MT_PSQL_LOG\"\n"
            "if [ -n \"${MT_PSQL_FAIL_MATCH:-}\" ]; then\n"
            "  case \"$*\" in *\"$MT_PSQL_FAIL_MATCH\"*) exit 23 ;; esac\n"
            "fi\n"
        )
        fake_psql.chmod(0o700)

        incremental_log = temp_root / "incremental.log"
        result = run_deploy(fake_bin, incremental_log, "no")
        if result.returncode != 0:
            raise RuntimeError(f"Incremental deployment path failed: {result.stderr.strip()}")
        if "Phase 3 Review Queue static contracts validated." not in result.stdout:
            raise RuntimeError("Incremental deployment skipped the Phase 3 Review Queue validator")
        incremental_files = logged_files(incremental_log)
        expected_migrations = sorted(path.name for path in (ROOT / "database" / "migrations").glob("*.sql"))
        if incremental_files != expected_migrations:
            raise RuntimeError(f"Incremental deployment order is incorrect: {incremental_files}")
        if "product_schema.sql" in incremental_files or "supabase_phase1_auth_rls.sql" in incremental_files:
            raise RuntimeError("Incremental deployment replayed a fresh-database baseline")

        baseline_log = temp_root / "baseline.log"
        result = run_deploy(fake_bin, baseline_log, "yes")
        if result.returncode != 0:
            raise RuntimeError(f"Fresh deployment path failed: {result.stderr.strip()}")
        baseline_files = logged_files(baseline_log)
        expected_baseline = ["product_schema.sql", "supabase_phase1_auth_rls.sql", *expected_migrations]
        if baseline_files != expected_baseline:
            raise RuntimeError(f"Fresh deployment order is incorrect: {baseline_files}")
        baseline_invocations = baseline_log.read_text().splitlines()
        if (
            len(baseline_invocations) < 1
            or "--single-transaction" not in baseline_invocations[0]
            or "product_schema.sql" not in baseline_invocations[0]
            or "supabase_phase1_auth_rls.sql" not in baseline_invocations[0]
        ):
            raise RuntimeError("Fresh Phase 0/1 baseline is not one atomic psql invocation")

        failed_baseline_log = temp_root / "failed-baseline.log"
        result = run_deploy(
            fake_bin,
            failed_baseline_log,
            "yes",
            fail_match="supabase_phase1_auth_rls.sql",
        )
        if result.returncode != 23:
            raise RuntimeError("Injected Phase 1 baseline failure did not stop deployment")
        if len(failed_baseline_log.read_text().splitlines()) != 1:
            raise RuntimeError("Migrations ran after an atomic baseline failure")

        invalid_log = temp_root / "invalid.log"
        result = run_deploy(fake_bin, invalid_log, "sometimes")
        if result.returncode != 6 or invalid_log.exists():
            raise RuntimeError("Invalid baseline mode did not fail before database execution")

    print("supabase_incremental_deploy_order=yes")
    print("supabase_fresh_deploy_order=yes")
    print("supabase_fresh_baseline_atomic=yes")
    print("supabase_baseline_failure_stops=yes")
    print("supabase_invalid_mode_fails_closed=yes")
    print("supabase_phase3_validation_gate=yes")


if __name__ == "__main__":
    main()
