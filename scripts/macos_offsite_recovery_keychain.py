#!/usr/bin/env python3
"""Store and recover the encrypted offsite GPG secret key in macOS Keychain."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import re
import secrets
import shutil
import subprocess
import sys


SERVICE_PREFIX = "com.mt-presence.offsite.recovery-private-key-v1"
CHUNK_CHARACTERS = 96
MAX_SECRET_BYTES = 64 * 1024
MAX_CHUNKS = 1024
FINGERPRINT_PATTERN = re.compile(r"^[0-9A-F]{40}$")
MANIFEST_PATTERN = re.compile(
    r"^v1:(?P<count>[1-9][0-9]{0,3}):(?P<bytes>[1-9][0-9]*):"
    r"(?P<digest>[0-9a-f]{64}):(?P<token>[0-9a-f]{16})$"
)


class KeychainError(RuntimeError):
    """A stable failure that never includes recovery material."""


def security_binary() -> str:
    binary = shutil.which("security")
    if not binary:
        raise KeychainError("macOS security command is unavailable")
    return binary


def service_for_chunk(token: str, index: int) -> str:
    return f"{SERVICE_PREFIX}.chunk.{token}.{index:04d}"


def run_security(arguments: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [security_binary(), *arguments],
        input=None if input_text is None else input_text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def read_item(account: str, service: str) -> str | None:
    result = run_security(["find-generic-password", "-a", account, "-s", service, "-w"])
    if result.returncode != 0:
        return None
    try:
        return result.stdout.removesuffix(b"\n").decode("ascii")
    except UnicodeDecodeError as error:
        raise KeychainError("Keychain item is not ASCII") from error


def write_item(account: str, service: str, label: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise KeychainError("Keychain value contains a line break")
    result = run_security(
        [
            "add-generic-password",
            "-U",
            "-a",
            account,
            "-s",
            service,
            "-l",
            label,
            "-w",
        ],
        input_text=f"{value}\n{value}\n",
    )
    if result.returncode != 0:
        raise KeychainError("Keychain write failed")
    if read_item(account, service) != value:
        raise KeychainError("Keychain read-after-write verification failed")


def delete_item(account: str, service: str) -> None:
    result = run_security(["delete-generic-password", "-a", account, "-s", service])
    if result.returncode not in (0, 44):
        raise KeychainError("Keychain delete failed")
    if read_item(account, service) is not None:
        raise KeychainError("Keychain delete verification failed")


def parse_manifest(account: str) -> tuple[int, int, str, str]:
    raw = read_item(account, f"{SERVICE_PREFIX}.manifest")
    return parse_manifest_value(raw)


def parse_manifest_value(raw: str | None) -> tuple[int, int, str, str]:
    match = MANIFEST_PATTERN.fullmatch(raw or "")
    if not match:
        raise KeychainError("Recovery key manifest is missing or invalid")
    count = int(match.group("count"))
    byte_count = int(match.group("bytes"))
    if count > MAX_CHUNKS or byte_count > MAX_SECRET_BYTES:
        raise KeychainError("Recovery key manifest exceeds limits")
    return count, byte_count, match.group("digest"), match.group("token")


def read_secret(account: str) -> tuple[bytes, int, str]:
    count, expected_bytes, expected_digest, token = parse_manifest(account)
    encoded_parts: list[str] = []
    for index in range(count):
        value = read_item(account, service_for_chunk(token, index))
        if value is None or len(value) > CHUNK_CHARACTERS:
            raise KeychainError("Recovery key chunk is missing or invalid")
        encoded_parts.append(value)
    try:
        secret = base64.b64decode("".join(encoded_parts), validate=True)
    except (ValueError, binascii.Error) as error:
        raise KeychainError("Recovery key encoding is invalid") from error
    digest = hashlib.sha256(secret).hexdigest()
    if len(secret) != expected_bytes or digest != expected_digest:
        raise KeychainError("Recovery key integrity verification failed")
    return secret, count, digest


def clean_generation(account: str, count: int, token: str) -> None:
    for index in range(min(count, MAX_CHUNKS)):
        delete_item(account, service_for_chunk(token, index))


def store(account: str) -> None:
    secret = sys.stdin.buffer.read(MAX_SECRET_BYTES + 1)
    if not secret or len(secret) > MAX_SECRET_BYTES:
        raise KeychainError("Recovery key input is empty or exceeds 64 KiB")
    encoded = base64.b64encode(secret).decode("ascii")
    chunks = [encoded[index : index + CHUNK_CHARACTERS] for index in range(0, len(encoded), CHUNK_CHARACTERS)]
    if not chunks or len(chunks) > MAX_CHUNKS:
        raise KeychainError("Recovery key requires too many Keychain chunks")
    digest = hashlib.sha256(secret).hexdigest()
    token = secrets.token_hex(8)
    manifest_service = f"{SERVICE_PREFIX}.manifest"
    previous_raw = read_item(account, manifest_service)
    previous: tuple[int, int, str, str] | None = None
    if previous_raw is not None:
        try:
            previous = parse_manifest_value(previous_raw)
        except KeychainError:
            previous = None

    written_services: list[str] = []
    try:
        for index, chunk in enumerate(chunks):
            service = service_for_chunk(token, index)
            written_services.append(service)
            write_item(account, service, "MT Presence recovery key chunk", chunk)
        manifest = f"v1:{len(chunks)}:{len(secret)}:{digest}:{token}"
        write_item(account, manifest_service, "MT Presence recovery key manifest", manifest)
        restored, restored_chunks, restored_digest = read_secret(account)
        if restored != secret or restored_chunks != len(chunks) or restored_digest != digest:
            raise KeychainError("Recovery key final verification failed")
    except Exception:
        for service in written_services:
            delete_item(account, service)
        if previous_raw is None:
            delete_item(account, manifest_service)
        else:
            write_item(account, manifest_service, "MT Presence recovery key manifest", previous_raw)
        raise
    finally:
        secret = b""

    if previous and previous[3] != token:
        clean_generation(account, previous[0], previous[3])
    # Remove the legacy single item and the first manually chunked layout.
    delete_item(account, SERVICE_PREFIX)
    for index in range(MAX_CHUNKS):
        legacy = f"{SERVICE_PREFIX}.chunk.{index:03d}"
        if read_item(account, legacy) is None:
            if index >= 32:
                break
            continue
        delete_item(account, legacy)
    print(f"recovery_keychain_chunks={len(chunks)}")
    print(f"recovery_keychain_bytes={len(restored)}")
    print(f"recovery_keychain_sha256={digest}")


def audit(account: str) -> None:
    secret, count, digest = read_secret(account)
    print(f"recovery_keychain_chunks={count}")
    print(f"recovery_keychain_bytes={len(secret)}")
    print(f"recovery_keychain_sha256={digest}")


def export(account: str) -> None:
    secret, _, _ = read_secret(account)
    sys.stdout.buffer.write(secret)
    sys.stdout.buffer.flush()


def delete(account: str, confirmation: str) -> None:
    if confirmation != account:
        raise KeychainError("Deletion confirmation does not match the fingerprint")
    count, _, _, token = parse_manifest(account)
    clean_generation(account, count, token)
    delete_item(account, f"{SERVICE_PREFIX}.manifest")
    delete_item(account, SERVICE_PREFIX)
    print("recovery_keychain_deleted=yes")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("store", "audit", "export", "delete"))
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--confirm-fingerprint", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fingerprint = args.fingerprint.strip().upper()
    if not FINGERPRINT_PATTERN.fullmatch(fingerprint):
        print("Recovery key fingerprint must be 40 uppercase hexadecimal characters.", file=sys.stderr)
        return 2
    try:
        if args.action == "store":
            store(fingerprint)
        elif args.action == "audit":
            audit(fingerprint)
        elif args.action == "export":
            export(fingerprint)
        else:
            delete(fingerprint, args.confirm_fingerprint.strip().upper())
    except (KeychainError, OSError) as error:
        print(f"offsite recovery keychain failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
