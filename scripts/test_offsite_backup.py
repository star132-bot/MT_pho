#!/usr/bin/env python3
"""Network-free acceptance for encrypted offsite backup tooling."""

from __future__ import annotations

import csv
import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "export_production_storage.py"
VERIFY_CIPHERS = ROOT / "scripts" / "verify_offsite_ciphertexts.sh"
OBJECTS = {
    "/storage/v1/object/authenticated/image-originals/owner/work/original.jpg": b"original-image-bytes",
    "/storage/v1/object/authenticated/profile-avatars/owner/avatar.webp": b"avatar-bytes",
}


class StorageHandler(BaseHTTPRequestHandler):
    calls: list[str] = []

    def do_GET(self) -> None:
        path = unquote(self.path)
        self.calls.append(path)
        if self.headers.get("apikey") != "sb_secret_backup_fixture" or self.headers.get("Authorization"):
            self.send_error(HTTPStatus.UNAUTHORIZED)
            return
        body = OBJECTS.get(path)
        if body is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args) -> None:
        return


def write_inventory(path: Path, rows: list[tuple[str, str, int, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("bucket_id", "name", "expected_size", "updated_at"))
        writer.writerows(rows)


def run_exporter(
    action: str,
    inventory: Path,
    output: Path,
    manifest: Path,
    environment: dict[str, str],
    *,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            sys.executable,
            str(EXPORTER),
            action,
            "--inventory",
            str(inventory),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"exporter {action} returned {result.returncode}, expected {expected}: {result.stderr}"
        )
    return result


def verify_exporter() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StorageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="mt-offsite-backup-test-") as temporary:
            root = Path(temporary)
            inventory = root / "inventory.csv"
            output = root / "storage"
            manifest = root / "manifest.jsonl"
            rows = [
                ("image-originals", "owner/work/original.jpg", len(OBJECTS[next(iter(OBJECTS))]), "2026-08-11 00:00:00+00"),
                ("profile-avatars", "owner/avatar.webp", len(OBJECTS[next(reversed(OBJECTS))]), "2026-08-11 00:00:00+00"),
            ]
            write_inventory(inventory, rows)
            environment = {
                **os.environ,
                "SUPABASE_URL": f"http://127.0.0.1:{server.server_port}",
                "SUPABASE_SECRET_KEY": "sb_secret_backup_fixture",
                "MT_OFFSITE_ALLOW_HTTP_LOOPBACK": "1",
            }
            exported = run_exporter("export", inventory, output, manifest, environment)
            if "storage_backup_objects=2" not in exported.stdout:
                raise AssertionError("exporter did not report the bounded object count")
            verified = run_exporter("verify", inventory, output, manifest, environment)
            if "storage_backup_verified_objects=2" not in verified.stdout:
                raise AssertionError("export verifier did not report success")
            records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            if len(records) != 2 or any(len(record.get("sha256", "")) != 64 for record in records):
                raise AssertionError("storage manifest is incomplete")
            if set(StorageHandler.calls) != set(OBJECTS):
                raise AssertionError("exporter requested an unexpected Storage object")

            first = output / "image-originals" / "owner" / "work" / "original.jpg"
            first.write_bytes(b"tampered")
            failed = run_exporter("verify", inventory, output, manifest, environment, expected=1)
            if "storage_backup_checksum_mismatch" not in failed.stderr:
                raise AssertionError("tampered Storage backup did not fail closed")

            unsafe_inventory = root / "unsafe.csv"
            write_inventory(unsafe_inventory, [("image-originals", "../secret", 1, "")])
            failed = run_exporter(
                "export",
                unsafe_inventory,
                root / "unsafe-output",
                root / "unsafe-manifest.jsonl",
                environment,
                expected=1,
            )
            if "storage_name_invalid" not in failed.stderr:
                raise AssertionError("unsafe Storage key did not fail before export")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def verify_ciphertext_checker() -> None:
    with tempfile.TemporaryDirectory(prefix="mt-offsite-cipher-test-") as temporary:
        root = Path(temporary)
        incoming = root / "incoming"
        incoming.mkdir(mode=0o700)
        cipher = incoming / "mt-presence-offsite-20260811T000000Z.tar.gpg"
        cipher.write_bytes(b"encrypted-fixture")
        cipher.chmod(0o600)
        manifest = cipher.with_name(f"{cipher.name}.sha256")
        manifest.write_text(
            f"{hashlib.sha256(cipher.read_bytes()).hexdigest()}  {cipher.name}\n",
            encoding="ascii",
        )
        manifest.chmod(0o600)
        environment = {
            **os.environ,
            "MT_OFFSITE_MIN_FREE_PERCENT": "0",
            "MT_OFFSITE_RECEIVE_USER": getpass.getuser(),
        }
        result = subprocess.run(
            ["bash", str(VERIFY_CIPHERS), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if (
            result.returncode != 0
            or "offsite_backup_promoted=1" not in result.stdout
            or "offsite_backup_ciphertexts_verified=1" not in result.stdout
        ):
            raise AssertionError(f"valid ciphertext batch failed verification: {result.stderr}")
        vault_cipher = (
            root
            / "vault"
            / "mt-presence-offsite-20260811T000000Z"
            / "mt-presence-offsite-20260811T000000Z.tar.gpg"
        )
        if not vault_cipher.is_file() or cipher.exists() or manifest.exists():
            raise AssertionError("verified ciphertext was not atomically promoted out of incoming")

        unexpected = incoming / "unexpected.txt"
        unexpected.write_text("not a backup", encoding="utf-8")
        unexpected.chmod(0o600)
        failed = subprocess.run(
            ["bash", str(VERIFY_CIPHERS), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if failed.returncode != 4 or "unexpected entry" not in failed.stderr:
            raise AssertionError("unexpected incoming entry did not fail closed")
        unexpected.unlink()

        vault_cipher.write_bytes(b"tampered")
        vault_cipher.chmod(0o600)
        failed = subprocess.run(
            ["bash", str(VERIFY_CIPHERS), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if failed.returncode != 5:
            raise AssertionError(
                "tampered ciphertext did not fail checksum verification: "
                f"returncode={failed.returncode} stdout={failed.stdout!r} stderr={failed.stderr!r}"
            )


def main() -> None:
    verify_exporter()
    verify_ciphertext_checker()
    print("Offsite backup acceptance passed (Storage export + ciphertext integrity).")


if __name__ == "__main__":
    main()
