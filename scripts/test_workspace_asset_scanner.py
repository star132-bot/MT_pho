#!/usr/bin/env python3
"""Secret-free integration boundary for the Phase 2F asset scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.parse

try:
    from PIL import Image
except ImportError as error:  # pragma: no cover - environment contract
    raise RuntimeError("Pillow is required for the asset scanner integration test") from error


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.scan_adapters import (
    AssetClaim,
    DeterministicScanError,
    DownloadedAsset,
    Observation,
    PillowImageInspector,
)


WORKER = ROOT / "workers" / "image_scanner.py"
ASSET_ID = "71000000-0000-4000-8000-000000000001"
IMAGE_ID = "51000000-0000-4000-8000-000000000001"
OWNER_ID = "21000000-0000-4000-8000-000000000001"
LEASE_TOKEN = "81000000-0000-4000-8000-000000000001"
WORKER_ID = "phase2f-loopback-worker"
SECRET_KEY = "sb_secret_phase2f_test_key_never_log"
LEGACY_KEY = "eyJhbGciOiJIUzI1NiJ9.phase2f-service-role.signature"
FALLBACK_SENTINEL = "eyJhbGciOiJIUzI1NiJ9.must-not-win.signature"
STORAGE_KEY = f"{OWNER_ID}/{IMAGE_ID}/original.jpg"
CLAM_SIGNATURE = "MT.Test.Signature.Should.Not.Leak"
RESULT_KEYS = {
    "outcome",
    "result_code",
    "scanner_version",
    "engine_name",
    "engine_version",
    "observed_mime_type",
    "observed_byte_size",
    "observed_width",
    "observed_height",
    "observed_checksum_sha256",
}


@dataclass
class Scenario:
    name: str
    object_bytes: bytes
    expected_key: str
    storage_status: int = HTTPStatus.OK
    storage_redirect_url: str | None = None
    clam_exit: int = 0
    checksum_override: str | None = None
    byte_size_override: int | None = None
    width_override: int | None = None
    height_override: int | None = None
    claim_delivered: bool = False
    claim_calls: list[dict] = field(default_factory=list)
    retry_calls: list[dict] = field(default_factory=list)
    complete_calls: list[dict] = field(default_factory=list)
    request_paths: list[str] = field(default_factory=list)
    header_failures: list[str] = field(default_factory=list)

    def job(self) -> dict:
        return {
            "asset_id": ASSET_ID,
            "image_id": IMAGE_ID,
            "kind": "original",
            "storage_bucket": "image-originals",
            "storage_key": STORAGE_KEY,
            "mime_type": "image/jpeg",
            "byte_size": self.byte_size_override if self.byte_size_override is not None else len(self.object_bytes),
            "width": self.width_override if self.width_override is not None else 7,
            "height": self.height_override if self.height_override is not None else 5,
            "checksum_sha256": self.checksum_override or hashlib.sha256(self.object_bytes).hexdigest(),
            "lease_token": LEASE_TOKEN,
            "attempt_number": 1,
            "lease_expires_at": "2026-07-17T01:02:00Z",
        }


class FakeScannerProvider(BaseHTTPRequestHandler):
    server: "ScannerTestServer"

    def log_message(self, _format, *_args) -> None:
        return

    def send_json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else {}

    def authorized(self) -> bool:
        scenario = self.server.scenario
        key = self.headers.get("apikey")
        authorization = self.headers.get("Authorization")
        cookie = self.headers.get("Cookie")
        header_names = {name.lower() for name in self.headers.keys()}
        if key != scenario.expected_key:
            scenario.header_failures.append("apikey")
        if scenario.expected_key.startswith("sb_secret_"):
            if authorization is not None:
                scenario.header_failures.append("sb_secret_authorization")
        elif authorization != f"Bearer {scenario.expected_key}":
            scenario.header_failures.append("legacy_authorization")
        if cookie is not None:
            scenario.header_failures.append("cookie")
        if any("csrf" in name for name in header_names):
            scenario.header_failures.append("csrf")
        return not scenario.header_failures

    def do_POST(self) -> None:
        scenario = self.server.scenario
        scenario.request_paths.append(self.path)
        if not self.authorized():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid internal worker headers"})
            return
        if not self.path.startswith("/rest/v1/rpc/"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        name = self.path.rsplit("/", 1)[-1]
        body = self.read_json()
        if name == "scanner_claim_asset_scan":
            scenario.claim_calls.append(body)
            if scenario.claim_delivered:
                self.send_json(HTTPStatus.OK, {"job": None})
            else:
                scenario.claim_delivered = True
                self.send_json(HTTPStatus.OK, {"job": scenario.job()})
            return
        if name == "scanner_retry_asset_scan":
            scenario.retry_calls.append(body)
            self.send_json(HTTPStatus.OK, {"retried": True, "asset_id": ASSET_ID})
            return
        if name == "scanner_complete_asset_scan":
            scenario.complete_calls.append(body)
            self.send_json(HTTPStatus.OK, {"completed": True, "asset_id": ASSET_ID})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"message": "unknown scanner RPC"})

    def do_GET(self) -> None:
        scenario = self.server.scenario
        scenario.request_paths.append(self.path)
        if not self.authorized():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "invalid internal worker headers"})
            return
        if not self.path.startswith("/storage/v1/object/"):
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        decoded_path = urllib.parse.unquote(self.path)
        if "image-originals" not in decoded_path or STORAGE_KEY not in decoded_path:
            self.send_json(HTTPStatus.NOT_FOUND, {})
            return
        if scenario.storage_redirect_url:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", scenario.storage_redirect_url)
            self.end_headers()
            return
        if scenario.storage_status != HTTPStatus.OK:
            self.send_json(scenario.storage_status, {"message": "storage object unavailable"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(scenario.object_bytes)))
        self.end_headers()
        self.wfile.write(scenario.object_bytes)


class ScannerTestServer(ThreadingHTTPServer):
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        super().__init__(("127.0.0.1", 0), FakeScannerProvider)


class CredentialSink(BaseHTTPRequestHandler):
    server: "CredentialSinkServer"

    def log_message(self, _format, *_args) -> None:
        return

    def do_GET(self) -> None:
        self.server.received_headers.append(dict(self.headers.items()))
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


class CredentialSinkServer(ThreadingHTTPServer):
    def __init__(self):
        self.received_headers: list[dict[str, str]] = []
        super().__init__(("127.0.0.1", 0), CredentialSink)


def jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (7, 5), color=(31, 97, 149)).save(output, format="JPEG", quality=91)
    return output.getvalue()


def encoded_image(format_name: str, size: tuple[int, int] = (7, 5)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(31, 97, 149)).save(output, format=format_name)
    return output.getvalue()


def inspect_fixture(
    path: Path,
    payload: bytes,
    *,
    mime_type: str,
    width: int,
    height: int,
    max_pixels: int = 1_000_000,
) -> object:
    path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    downloaded = DownloadedAsset(
        path,
        Observation(mime_type=mime_type, byte_size=len(payload), checksum_sha256=checksum),
    )
    claim = AssetClaim(
        asset_id=ASSET_ID,
        image_id=IMAGE_ID,
        kind="original",
        storage_bucket="image-originals",
        storage_key=STORAGE_KEY,
        mime_type=mime_type,
        byte_size=len(payload),
        width=width,
        height=height,
        checksum_sha256=checksum,
        lease_token=LEASE_TOKEN,
        attempt_number=1,
        lease_expires_at="2099-01-01T00:00:00Z",
    )
    inspector = PillowImageInspector(
        max_pixels=max_pixels,
        max_edge=20_000,
        timeout_seconds=5,
        memory_limit_bytes=512 * 1024 * 1024,
    )
    return inspector.inspect(downloaded, claim)


def assert_probe_boundaries(temp_root: Path) -> None:
    png = encoded_image("PNG")
    png_result = inspect_fixture(
        temp_root / "valid.png",
        png,
        mime_type="image/png",
        width=7,
        height=5,
    )
    if getattr(png_result, "mime_type", None) != "image/png":
        raise RuntimeError("Credential-free probe did not decode PNG")

    webp = encoded_image("WEBP")
    webp_result = inspect_fixture(
        temp_root / "valid.webp",
        webp,
        mime_type="image/webp",
        width=7,
        height=5,
    )
    if getattr(webp_result, "mime_type", None) != "image/webp":
        raise RuntimeError("Credential-free probe did not decode WebP")

    exif = Image.Exif()
    exif[0x0112] = 6
    oriented_output = BytesIO()
    Image.new("RGB", (7, 5), color=(31, 97, 149)).save(
        oriented_output,
        format="JPEG",
        exif=exif,
    )
    oriented = inspect_fixture(
        temp_root / "oriented.jpg",
        oriented_output.getvalue(),
        mime_type="image/jpeg",
        width=5,
        height=7,
    )
    if (getattr(oriented, "width", None), getattr(oriented, "height", None)) != (5, 7):
        raise RuntimeError("Credential-free probe did not apply EXIF-oriented dimensions")

    animated_output = BytesIO()
    first = Image.new("RGB", (7, 5), color=(31, 97, 149))
    second = Image.new("RGB", (7, 5), color=(149, 31, 97))
    first.save(animated_output, format="WEBP", save_all=True, append_images=[second], duration=100)
    try:
        inspect_fixture(
            temp_root / "animated.webp",
            animated_output.getvalue(),
            mime_type="image/webp",
            width=7,
            height=5,
        )
    except DeterministicScanError as error:
        if error.code != "multiple_frames_not_allowed":
            raise RuntimeError("Animated WebP used an unexpected failure code") from error
    else:
        raise RuntimeError("Animated WebP was accepted by the scanner probe")

    bomb = encoded_image("PNG", (5, 5))
    try:
        inspect_fixture(
            temp_root / "pixel-limit.png",
            bomb,
            mime_type="image/png",
            width=5,
            height=5,
            max_pixels=20,
        )
    except DeterministicScanError as error:
        if error.code not in {"decompression_bomb", "image_size_limit_exceeded"}:
            raise RuntimeError("Pixel limit used an unexpected failure code") from error
    else:
        raise RuntimeError("Pixel limit fixture was accepted by the scanner probe")


def write_fake_clam(path: Path, exit_code: int) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "if [ -n \"${SUPABASE_SECRET_KEY:-}${SUPABASE_SERVICE_ROLE_KEY:-}${PGPASSWORD:-}\" ]; then\n"
        "  printf '%s\\n' 'credential inherited by scanner subprocess' >&2; exit 9\n"
        "fi\n"
        "if [ \"${1:-}\" = \"--version\" ]; then\n"
        "  printf '%s\\n' 'FakeClam 1.0'; exit 0\n"
        "fi\n"
        f"case \"{exit_code}\" in\n"
        f"  1) printf '%s FOUND\\n' '{CLAM_SIGNATURE}'; exit 1 ;;\n"
        "  2) printf '%s\\n' 'scanner temporarily unavailable' >&2; exit 2 ;;\n"
        "  *) printf '%s\\n' 'stream OK'; exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def scanner_environment(
    base_url: str,
    clam_command: Path,
    scenario: Scenario,
    *,
    key_mode: str,
) -> dict[str, str]:
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    environment.update({
        "SUPABASE_URL": base_url,
        "MT_SCANNER_ID": WORKER_ID,
        "MT_SCANNER_CLAMAV_COMMAND": str(clam_command),
        "MT_SCANNER_TEMP_DIR": str(clam_command.parent),
        "MT_SCANNER_MAX_DOWNLOAD_BYTES": str(2 * 1024 * 1024),
        "MT_SCANNER_MAX_IMAGE_PIXELS": "1000000",
        "MT_SCANNER_REQUEST_TIMEOUT_SECONDS": "2",
        "MT_SCANNER_DOWNLOAD_TIMEOUT_SECONDS": "5",
        "MT_SCANNER_SCAN_TIMEOUT_SECONDS": "5",
        "MT_SCANNER_DECODE_TIMEOUT_SECONDS": "5",
        "MT_SCANNER_DECODE_MEMORY_BYTES": str(512 * 1024 * 1024),
        "PYTHONPATH": str(ROOT),
        "PYTHONUNBUFFERED": "1",
    })
    if key_mode == "secret":
        environment["SUPABASE_SECRET_KEY"] = SECRET_KEY
        environment["SUPABASE_SERVICE_ROLE_KEY"] = FALLBACK_SENTINEL
    else:
        environment["SUPABASE_SERVICE_ROLE_KEY"] = LEGACY_KEY
    return environment


def run_scenario(scenario: Scenario, temp_root: Path, *, key_mode: str = "secret") -> subprocess.CompletedProcess[str]:
    server = ScannerTestServer(scenario)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    clam_command = temp_root / f"fake-clam-{scenario.name}.sh"
    write_fake_clam(clam_command, scenario.clam_exit)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        result = subprocess.run(
            [sys.executable, str(WORKER), "--once", "--lease-seconds", "120"],
            cwd=ROOT,
            env=scanner_environment(base_url, clam_command, scenario, key_mode=key_mode),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
    combined_output = f"{result.stdout}\n{result.stderr}"
    for sensitive in (scenario.expected_key, FALLBACK_SENTINEL, STORAGE_KEY, LEASE_TOKEN, CLAM_SIGNATURE):
        if sensitive and sensitive in combined_output:
            raise RuntimeError(f"{scenario.name}: worker logs exposed an internal secret or asset locator")
    if scenario.header_failures:
        raise RuntimeError(f"{scenario.name}: invalid internal request headers: {scenario.header_failures}")
    if result.returncode != 0:
        raise RuntimeError(f"{scenario.name}: worker exited {result.returncode}: {combined_output.strip()}")
    if scenario.claim_calls != [{"worker_id": WORKER_ID, "lease_seconds": 120}]:
        raise RuntimeError(f"{scenario.name}: claim RPC body was not exact: {scenario.claim_calls}")
    return result


def completed_result(scenario: Scenario) -> dict:
    if len(scenario.complete_calls) != 1 or scenario.retry_calls:
        retry_codes = [call.get("error_code") for call in scenario.retry_calls]
        raise RuntimeError(
            f"{scenario.name}: expected one completion and no retry; retry_codes={retry_codes}"
        )
    body = scenario.complete_calls[0]
    if set(body) != {"asset_id", "lease_token", "result"}:
        raise RuntimeError(f"{scenario.name}: complete RPC body was not exact")
    if body.get("asset_id") != ASSET_ID or body.get("lease_token") != LEASE_TOKEN:
        raise RuntimeError(f"{scenario.name}: complete RPC did not use the claimed lease")
    result = body.get("result")
    if not isinstance(result, dict) or set(result) != RESULT_KEYS:
        raise RuntimeError(f"{scenario.name}: scanner result did not use the exact allowlist")
    return result


def retried_error(scenario: Scenario) -> str:
    if len(scenario.retry_calls) != 1 or scenario.complete_calls:
        raise RuntimeError(f"{scenario.name}: expected one retry and no completion")
    body = scenario.retry_calls[0]
    if set(body) != {"asset_id", "lease_token", "error_code", "retry_after_seconds"}:
        raise RuntimeError(f"{scenario.name}: retry RPC body was not exact")
    if body.get("asset_id") != ASSET_ID or body.get("lease_token") != LEASE_TOKEN:
        raise RuntimeError(f"{scenario.name}: retry RPC did not use the claimed lease")
    if not isinstance(body.get("retry_after_seconds"), int) or body["retry_after_seconds"] < 1:
        raise RuntimeError(f"{scenario.name}: retry delay was invalid")
    error_code = body.get("error_code")
    if not isinstance(error_code, str) or not error_code:
        raise RuntimeError(f"{scenario.name}: retry error code was missing")
    return error_code


def main() -> None:
    if not WORKER.exists():
        raise RuntimeError(f"Asset scanner worker is missing: {WORKER}")
    valid = jpeg_bytes()
    with tempfile.TemporaryDirectory(prefix="mt-asset-scanner-") as temp_name:
        temp_root = Path(temp_name)
        assert_probe_boundaries(temp_root)

        clean = Scenario("clean-secret-header", valid, SECRET_KEY)
        run_scenario(clean, temp_root)
        clean_result = completed_result(clean)
        if clean_result.get("outcome") != "clean" or clean_result.get("result_code") != "clean":
            raise RuntimeError("Valid decoded image was not marked clean")
        if (
            clean_result.get("observed_mime_type") != "image/jpeg"
            or clean_result.get("observed_byte_size") != len(valid)
            or clean_result.get("observed_width") != 7
            or clean_result.get("observed_height") != 5
            or clean_result.get("observed_checksum_sha256") != hashlib.sha256(valid).hexdigest()
        ):
            raise RuntimeError("Clean scanner result did not preserve observed image metadata")

        legacy = Scenario("clean-legacy-header", valid, LEGACY_KEY)
        run_scenario(legacy, temp_root, key_mode="legacy")
        if completed_result(legacy).get("outcome") != "clean":
            raise RuntimeError("Legacy service-role header path did not complete cleanly")

        invalid = Scenario("invalid-decode", b"\xff\xd8\xffnot-a-decodable-jpeg\x00\x01", SECRET_KEY)
        run_scenario(invalid, temp_root)
        invalid_result = completed_result(invalid)
        if invalid_result.get("outcome") != "failed" or invalid_result.get("result_code") != "image_decode_failed":
            raise RuntimeError("Invalid image decode did not fail closed")

        mismatch = Scenario("metadata-mismatch", valid, SECRET_KEY, checksum_override="0" * 64)
        run_scenario(mismatch, temp_root)
        mismatch_result = completed_result(mismatch)
        if mismatch_result.get("outcome") != "failed" or mismatch_result.get("result_code") != "checksum_mismatch":
            raise RuntimeError("Image metadata mismatch did not fail closed")

        malware = Scenario("malware-flagged", valid, SECRET_KEY, clam_exit=1)
        run_scenario(malware, temp_root)
        malware_result = completed_result(malware)
        if malware_result.get("outcome") != "flagged" or malware_result.get("result_code") != "malware_detected":
            raise RuntimeError("Malware adapter finding did not flag the asset")
        if (
            malware_result.get("observed_mime_type") != "image/jpeg"
            or malware_result.get("observed_byte_size") != len(valid)
            or malware_result.get("observed_checksum_sha256") != hashlib.sha256(valid).hexdigest()
            or malware_result.get("observed_width") is not None
            or malware_result.get("observed_height") is not None
        ):
            raise RuntimeError("Malware result did not preserve the pre-decode observation boundary")

        transient = Scenario("malware-transient", valid, SECRET_KEY, clam_exit=2)
        run_scenario(transient, temp_root)
        if retried_error(transient) != "clamav_scan_error":
            raise RuntimeError("Transient malware scanner failure used an unexpected retry code")

        missing = Scenario("storage-missing", valid, SECRET_KEY, storage_status=HTTPStatus.NOT_FOUND)
        run_scenario(missing, temp_root)
        missing_result = completed_result(missing)
        if missing_result.get("outcome") != "failed" or missing_result.get("result_code") != "storage_object_missing":
            raise RuntimeError("Missing registered Storage object did not fail closed")
        if any(missing_result.get(key) is not None for key in (
            "observed_mime_type",
            "observed_byte_size",
            "observed_width",
            "observed_height",
            "observed_checksum_sha256",
        )):
            raise RuntimeError("Missing Storage object unexpectedly reported observed metadata")

        unavailable = Scenario("storage-unavailable", valid, SECRET_KEY, storage_status=HTTPStatus.SERVICE_UNAVAILABLE)
        run_scenario(unavailable, temp_root)
        if retried_error(unavailable) != "storage_request_failed":
            raise RuntimeError("Transient Storage failure used an unexpected retry code")

        sink = CredentialSinkServer()
        sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
        sink_thread.start()
        redirect = Scenario(
            "redirect-not-followed",
            valid,
            SECRET_KEY,
            storage_redirect_url=f"http://127.0.0.1:{sink.server_address[1]}/capture",
        )
        try:
            run_scenario(redirect, temp_root)
        finally:
            sink.shutdown()
            sink.server_close()
        if retried_error(redirect) != "provider_redirect_rejected":
            raise RuntimeError("Provider redirect did not fail closed")
        if sink.received_headers:
            raise RuntimeError("Scanner followed a provider redirect and exposed request headers")

        if list(temp_root.rglob("mt-scan-*.bin")):
            raise RuntimeError("Scanner left a private downloaded asset in its temp root")

    print("asset_scanner_secret_key_header=yes")
    print("asset_scanner_legacy_key_header=yes")
    print("asset_scanner_valid_decode_clean=yes")
    print("asset_scanner_png_webp_decode=yes")
    print("asset_scanner_exif_orientation=yes")
    print("asset_scanner_multiframe_and_pixel_limits=yes")
    print("asset_scanner_invalid_decode_failed=yes")
    print("asset_scanner_metadata_mismatch_failed=yes")
    print("asset_scanner_malware_flagged=yes")
    print("asset_scanner_transient_retry=yes")
    print("asset_scanner_storage_failure_boundary=yes")
    print("asset_scanner_redirect_credentials_exposed=no")
    print("asset_scanner_temp_files_retained=no")
    print("asset_scanner_sensitive_logs_exposed=no")


if __name__ == "__main__":
    main()
