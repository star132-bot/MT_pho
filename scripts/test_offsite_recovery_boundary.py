#!/usr/bin/env python3
"""Secret-free boundary acceptance for the disposable database restore runner."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "rehearse_offsite_database_restore.sh"
TARGET = "local-mt-presence-recovery-fixture01"


FAKE_PG_RESTORE = r'''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
if "--list" in arguments:
    print("1; 1259 100 TABLE public users postgres")
    print("2; 1255 101 FUNCTION public fixture() postgres")
    print("3; 0 0 ACL public TABLE users postgres")
    raise SystemExit(0)
Path(os.environ["FAKE_RESTORE_LOG"]).write_text("\n".join(arguments))
'''


FAKE_PSQL = r'''#!/usr/bin/env python3
import os
import sys

arguments = sys.argv[1:]
command = next((value.split("=", 1)[1] for value in arguments if value.startswith("--command=")), "")
if "shobj_description" in command:
    print(os.environ.get("FAKE_DATABASE_GUARD", ""))
elif "nspname not like" in command:
    print("0")
elif "database_schemas" in command:
    print("database_schemas=3")
    print("database_tables=32")
    print("database_functions=88")
    print("database_rls_tables=20")
    print("database_policies=28")
    print("database_acl_rows=41")
    print("auth_users=1")
    print("application_users=1")
    print("application_images=2")
    print("storage_objects=6")
elif "n.nspname='public'" in command and "relkind" in command:
    print("0")
'''


FAKE_SHA256SUM = r'''#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

if len(sys.argv) == 2:
    target = Path(sys.argv[1])
    print(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}")
    raise SystemExit(0)
if sys.argv[1:2] != ["--check"]:
    raise SystemExit(2)
manifest = Path(sys.argv[2])
digest, name = manifest.read_text().strip().split(None, 1)
target = manifest.parent / name.strip()
raise SystemExit(0 if hashlib.sha256(target.read_bytes()).hexdigest() == digest else 1)
'''


def run(environment: dict[str, str], dump: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUNNER), str(dump), str(manifest)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-offsite-recovery-boundary-") as temporary:
        root = Path(temporary)
        binary = root / "bin"
        binary.mkdir()
        for name, source in (("pg_restore", FAKE_PG_RESTORE), ("psql", FAKE_PSQL), ("sha256sum", FAKE_SHA256SUM)):
            path = binary / name
            path.write_text(source)
            path.chmod(0o755)
        dump = root / "fixture.dump"
        dump.write_bytes(b"fixture-custom-dump")
        manifest = root / "fixture.dump.sha256"
        manifest.write_text(f"{hashlib.sha256(dump.read_bytes()).hexdigest()}  {dump.name}\n")
        base = {
            **os.environ,
            "PATH": f"{binary}:{os.environ.get('PATH', '')}",
            "PGHOST": "127.0.0.1",
            "PGPORT": "54322",
            "PGDATABASE": "postgres",
            "PGUSER": "supabase_admin",
            "PGPASSWORD": "fixture-password-never-log",
            "MT_RECOVERY_TARGET": "isolated-supabase",
            "MT_RECOVERY_TARGET_REF": TARGET,
            "MT_RECOVERY_PRODUCTION_REF": "production-project-ref",
            "MT_RECOVERY_CONFIRM": TARGET,
            "MT_RECOVERY_ALLOW_HTTP_LOOPBACK": "1",
            "FAKE_DATABASE_GUARD": f"mt-presence-recovery:{TARGET}",
            "FAKE_RESTORE_LOG": str(root / "restore.log"),
        }

        restored = run(base, dump, manifest)
        if restored.returncode or "offsite_database_restore=passed" not in restored.stdout:
            raise AssertionError(f"valid isolated recovery failed: {restored.stderr}")
        arguments = (root / "restore.log").read_text()
        for marker in ("--single-transaction", "--exit-on-error"):
            if marker not in arguments:
                raise AssertionError(f"restore runner omitted {marker}")
        for forbidden in ("--clean", base["PGPASSWORD"]):
            if forbidden in arguments or forbidden in restored.stdout or forbidden in restored.stderr:
                raise AssertionError("restore runner leaked a secret or used destructive clean mode")

        production = run({**base, "MT_RECOVERY_PRODUCTION_REF": TARGET}, dump, manifest)
        if production.returncode != 3 or "boundary is invalid" not in production.stderr:
            raise AssertionError("restore runner accepted the production project reference")

        remote = run({**base, "PGHOST": "db.example.com"}, dump, manifest)
        if remote.returncode != 3 or "loopback" not in remote.stderr:
            raise AssertionError("restore runner accepted a remote database")

        unmarked = run({**base, "FAKE_DATABASE_GUARD": ""}, dump, manifest)
        if unmarked.returncode != 5 or "disposable-target guard" not in unmarked.stderr:
            raise AssertionError("restore runner accepted an unmarked database")

        incomplete = run({key: value for key, value in base.items() if key != "MT_RECOVERY_CONFIRM"}, dump, manifest)
        if incomplete.returncode != 2 or "MT_RECOVERY_CONFIRM" not in incomplete.stderr:
            raise AssertionError("restore runner did not require explicit confirmation")

    print("Offsite recovery boundary acceptance passed (loopback, guard, atomic restore, ACL evidence).")


if __name__ == "__main__":
    main()
