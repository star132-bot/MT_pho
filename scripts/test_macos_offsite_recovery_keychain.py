#!/usr/bin/env python3
"""Secret-free acceptance for chunked macOS Keychain recovery storage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "macos_offsite_recovery_keychain.py"
FINGERPRINT = "A" * 40
FIXTURE = bytes(range(256)) * 9


FAKE_SECURITY = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

store = Path(os.environ["FAKE_KEYCHAIN_STORE"])
items = json.loads(store.read_text()) if store.exists() else {}
command = sys.argv[1]
arguments = sys.argv[2:]

def option(name):
    return arguments[arguments.index(name) + 1]

key = f"{option('-a')}\0{option('-s')}"
if command == "add-generic-password":
    first = sys.stdin.readline().rstrip("\n")
    second = sys.stdin.readline().rstrip("\n")
    if first != second:
        raise SystemExit(1)
    items[key] = first
    store.write_text(json.dumps(items, sort_keys=True))
elif command == "find-generic-password":
    if key not in items:
        raise SystemExit(44)
    sys.stdout.write(items[key] + "\n")
elif command == "delete-generic-password":
    if key not in items:
        raise SystemExit(44)
    del items[key]
    store.write_text(json.dumps(items, sort_keys=True))
else:
    raise SystemExit(2)
'''


def run(action: str, environment: dict[str, str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(HELPER), action, "--fingerprint", FINGERPRINT],
        cwd=ROOT,
        env=environment,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-recovery-keychain-test-") as temporary:
        root = Path(temporary)
        binary = root / "security"
        binary.write_text(FAKE_SECURITY)
        binary.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": f"{root}:{os.environ.get('PATH', '')}",
            "FAKE_KEYCHAIN_STORE": str(root / "items.json"),
        }
        stored = run("store", environment, input_bytes=FIXTURE)
        if stored.returncode or b"recovery_keychain_chunks=" not in stored.stdout:
            raise AssertionError(stored.stderr.decode())
        audited = run("audit", environment)
        if audited.returncode or b"recovery_keychain_bytes=2304" not in audited.stdout:
            raise AssertionError(audited.stderr.decode())
        exported = run("export", environment)
        if exported.returncode or exported.stdout != FIXTURE:
            raise AssertionError("chunked recovery key did not round-trip")

        items_path = root / "items.json"
        items = json.loads(items_path.read_text())
        chunk_key = next(key for key in items if ".chunk." in key)
        replacement = "B" if items[chunk_key][0] != "B" else "C"
        items[chunk_key] = replacement + items[chunk_key][1:]
        items_path.write_text(json.dumps(items, sort_keys=True))
        failed = run("audit", environment)
        if failed.returncode != 1 or b"integrity verification failed" not in failed.stderr:
            raise AssertionError("tampered Keychain chunk did not fail closed")

        # A wrong fingerprint must not allow accidental deletion.
        deletion = subprocess.run(
            [
                sys.executable,
                str(HELPER),
                "delete",
                "--fingerprint",
                FINGERPRINT,
                "--confirm-fingerprint",
                "B" * 40,
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if deletion.returncode != 1 or b"confirmation" not in deletion.stderr:
            raise AssertionError("Keychain deletion confirmation was not enforced")
    print("macOS recovery Keychain acceptance passed.")


if __name__ == "__main__":
    main()
