"""I/O and inspection adapters for the trusted image scanner worker."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import quote, urlparse
from uuid import UUID


BUCKET_BY_KIND = {
    "original": "image-originals",
    "display": "image-display",
    "thumbnail": "image-thumbnails",
}
MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_BYTES_BY_KIND = {
    "original": 50 * 1024 * 1024,
    "display": 20 * 1024 * 1024,
    "thumbnail": 10 * 1024 * 1024,
}
SAFE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,119}$")
MAX_PROVIDER_JSON_BYTES = 1024 * 1024
MAX_PROBE_JSON_BYTES = 16 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
PROBE_FAILURE_CODES = {
    "multiple_frames_not_allowed",
    "decoded_format_mismatch",
    "image_size_limit_exceeded",
    "decompression_bomb",
    "image_decode_failed",
}


@dataclass(frozen=True)
class Observation:
    mime_type: str | None = None
    byte_size: int | None = None
    width: int | None = None
    height: int | None = None
    checksum_sha256: str | None = None


class ScannerAdapterError(RuntimeError):
    """Base error carrying only a stable, non-sensitive result code."""

    def __init__(self, code: str, observation: Observation | None = None):
        safe_code = code if SAFE_CODE_PATTERN.fullmatch(code) else "scanner_adapter_error"
        super().__init__(safe_code)
        self.code = safe_code
        self.observation = observation or Observation()


class InfrastructureError(ScannerAdapterError):
    """A transient provider, dependency, or process failure."""


class DeterministicScanError(ScannerAdapterError):
    """A stable file-integrity failure that must complete as failed."""


class ProviderProtocolError(InfrastructureError):
    """The privileged provider returned a response outside its allowlist."""


class RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward scanner credentials through an HTTP redirect."""

    def redirect_request(self, _request, _fp, _code, _message, _headers, _new_url):
        raise InfrastructureError("provider_redirect_rejected")


@dataclass(frozen=True)
class AssetClaim:
    asset_id: str
    image_id: str
    kind: str
    storage_bucket: str
    storage_key: str
    mime_type: str
    byte_size: int
    width: int
    height: int
    checksum_sha256: str
    lease_token: str
    attempt_number: int
    lease_expires_at: str

    @classmethod
    def from_provider(cls, value: Any) -> "AssetClaim":
        required = {
            "asset_id",
            "image_id",
            "kind",
            "storage_bucket",
            "storage_key",
            "mime_type",
            "byte_size",
            "width",
            "height",
            "checksum_sha256",
            "lease_token",
            "attempt_number",
            "lease_expires_at",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ProviderProtocolError("claim_response_invalid")

        asset_id = _canonical_uuid(value["asset_id"], "claim_response_invalid")
        image_id = _canonical_uuid(value["image_id"], "claim_response_invalid")
        lease_token = _canonical_uuid(value["lease_token"], "claim_response_invalid")
        kind = _strict_text(value["kind"], 40, "claim_response_invalid")
        if kind not in BUCKET_BY_KIND:
            raise ProviderProtocolError("claim_response_invalid")
        storage_bucket = _strict_text(value["storage_bucket"], 80, "claim_response_invalid")
        if storage_bucket != BUCKET_BY_KIND[kind]:
            raise ProviderProtocolError("claim_response_invalid")
        mime_type = _strict_text(value["mime_type"], 80, "claim_response_invalid").lower()
        if mime_type not in EXTENSION_BY_MIME:
            raise ProviderProtocolError("claim_response_invalid")
        byte_size = _positive_int(value["byte_size"], MAX_BYTES_BY_KIND[kind], "claim_response_invalid")
        width = _positive_int(value["width"], 100_000, "claim_response_invalid")
        height = _positive_int(value["height"], 100_000, "claim_response_invalid")
        checksum = _strict_text(value["checksum_sha256"], 64, "claim_response_invalid").lower()
        if not CHECKSUM_PATTERN.fullmatch(checksum):
            raise ProviderProtocolError("claim_response_invalid")
        attempt_number = _positive_int(value["attempt_number"], 1_000_000, "claim_response_invalid")
        lease_expires_at = _strict_text(value["lease_expires_at"], 80, "claim_response_invalid")
        storage_key = _validate_storage_key(value["storage_key"], image_id, kind, mime_type)
        return cls(
            asset_id=asset_id,
            image_id=image_id,
            kind=kind,
            storage_bucket=storage_bucket,
            storage_key=storage_key,
            mime_type=mime_type,
            byte_size=byte_size,
            width=width,
            height=height,
            checksum_sha256=checksum,
            lease_token=lease_token,
            attempt_number=attempt_number,
            lease_expires_at=lease_expires_at,
        )


@dataclass(frozen=True)
class DownloadedAsset:
    path: Path
    observation: Observation


@dataclass(frozen=True)
class ImageInspection:
    mime_type: str
    width: int
    height: int
    engine_version: str


@dataclass(frozen=True)
class MalwareScan:
    flagged: bool
    engine_version: str


@dataclass(frozen=True)
class ScanResult:
    outcome: str
    result_code: str
    scanner_version: str
    engine_name: str
    engine_version: str
    observation: Observation

    def as_provider_payload(self) -> dict[str, Any]:
        if self.outcome not in {"clean", "flagged", "failed"}:
            raise ValueError("Invalid scanner outcome")
        if not SAFE_CODE_PATTERN.fullmatch(self.result_code) or len(self.result_code) > 64:
            raise ValueError("Invalid scanner result code")
        if not all(
            isinstance(value, str) and 1 <= len(value) <= 120
            for value in (self.scanner_version, self.engine_name, self.engine_version)
        ):
            raise ValueError("Invalid scanner engine identity")
        return {
            "outcome": self.outcome,
            "result_code": self.result_code,
            "scanner_version": self.scanner_version,
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "observed_mime_type": self.observation.mime_type,
            "observed_byte_size": self.observation.byte_size,
            "observed_width": self.observation.width,
            "observed_height": self.observation.height,
            "observed_checksum_sha256": self.observation.checksum_sha256,
        }


class ScannerProvider(Protocol):
    def claim(self, worker_id: str, lease_seconds: int) -> AssetClaim | None: ...

    def download(self, claim: AssetClaim) -> DownloadedAsset: ...

    def cleanup_download(self, downloaded: DownloadedAsset) -> None: ...

    def retry(self, claim: AssetClaim, error_code: str, retry_after_seconds: int) -> None: ...

    def complete(self, claim: AssetClaim, result: ScanResult) -> None: ...


class ImageInspector(Protocol):
    @property
    def engine_version(self) -> str: ...

    def inspect(self, downloaded: DownloadedAsset, claim: AssetClaim) -> ImageInspection: ...


class MalwareScanner(Protocol):
    @property
    def engine_version(self) -> str: ...

    def healthcheck(self) -> None: ...

    def scan(self, path: Path) -> MalwareScan: ...


class SupabaseScannerAdapter:
    """Claim jobs through PostgREST and stream private Storage objects to disk."""

    def __init__(
        self,
        base_url: str,
        secret_key: str,
        *,
        request_timeout_seconds: float = 30,
        download_timeout_seconds: float = 60,
        max_download_bytes: int = 50 * 1024 * 1024,
        temp_dir: Path | None = None,
        opener: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = _validate_base_url(base_url)
        self.secret_key = _strict_text(secret_key, 4096, "scanner_secret_missing")
        if self.secret_key.startswith("sb_publishable_"):
            raise ProviderProtocolError("scanner_secret_invalid")
        self.request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self.download_timeout_seconds = max(1.0, float(download_timeout_seconds))
        self.max_download_bytes = max(1, int(max_download_bytes))
        self.temp_dir = temp_dir
        self.opener = opener or urllib.request.build_opener(RejectRedirectHandler()).open
        self.clock = clock
        self._headers = {"apikey": self.secret_key}
        if not self.secret_key.startswith("sb_secret_"):
            self._headers["Authorization"] = f"Bearer {self.secret_key}"

    def claim(self, worker_id: str, lease_seconds: int) -> AssetClaim | None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 30 <= lease_seconds <= 900:
            raise ProviderProtocolError("lease_seconds_invalid")
        result = self._rpc(
            "scanner_claim_asset_scan",
            {"worker_id": _worker_id(worker_id), "lease_seconds": lease_seconds},
        )
        if not isinstance(result, dict) or set(result) != {"job"}:
            raise ProviderProtocolError("claim_response_invalid")
        if result["job"] is None:
            return None
        return AssetClaim.from_provider(result["job"])

    def retry(self, claim: AssetClaim, error_code: str, retry_after_seconds: int) -> None:
        if not SAFE_CODE_PATTERN.fullmatch(error_code) or len(error_code) > 64:
            error_code = "scanner_infrastructure_error"
        if (
            isinstance(retry_after_seconds, bool)
            or not isinstance(retry_after_seconds, int)
            or not 1 <= retry_after_seconds <= 3600
        ):
            raise ProviderProtocolError("retry_seconds_invalid")
        response = self._rpc(
            "scanner_retry_asset_scan",
            {
                "asset_id": claim.asset_id,
                "lease_token": claim.lease_token,
                "error_code": error_code,
                "retry_after_seconds": retry_after_seconds,
            },
        )
        if (
            not isinstance(response, dict)
            or response.get("asset_id") != claim.asset_id
            or not (response.get("retried") is True or response.get("terminal") is True)
        ):
            raise ProviderProtocolError("retry_response_invalid")

    def complete(self, claim: AssetClaim, result: ScanResult) -> None:
        response = self._rpc(
            "scanner_complete_asset_scan",
            {
                "asset_id": claim.asset_id,
                "lease_token": claim.lease_token,
                "result": result.as_provider_payload(),
            },
        )
        if (
            not isinstance(response, dict)
            or response.get("completed") is not True
            or response.get("asset_id") != claim.asset_id
        ):
            raise ProviderProtocolError("complete_response_invalid")

    def download(self, claim: AssetClaim) -> DownloadedAsset:
        if claim.byte_size > self.max_download_bytes:
            raise DeterministicScanError(
                "download_size_limit_exceeded",
                Observation(byte_size=claim.byte_size),
            )
        bucket = quote(claim.storage_bucket, safe="")
        storage_key = quote(claim.storage_key, safe="/")
        request = urllib.request.Request(
            f"{self.base_url}/storage/v1/object/authenticated/{bucket}/{storage_key}",
            headers={**self._headers, "Accept": "application/octet-stream"},
            method="GET",
        )
        deadline = self.clock() + self.download_timeout_seconds
        path: Path | None = None
        try:
            with self.opener(request, timeout=self.request_timeout_seconds) as response:
                if self.clock() >= deadline:
                    raise InfrastructureError("storage_download_timeout")
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared_response_size = int(content_length)
                    except ValueError as error:
                        raise InfrastructureError("storage_response_invalid") from error
                    if declared_response_size != claim.byte_size:
                        raise DeterministicScanError(
                            "byte_size_mismatch",
                            Observation(byte_size=declared_response_size),
                        )
                file_descriptor, raw_path = tempfile.mkstemp(
                    prefix=f"mt-scan-{claim.kind}-",
                    suffix=".bin",
                    dir=str(self.temp_dir) if self.temp_dir else None,
                )
                path = Path(raw_path)
                try:
                    os.fchmod(file_descriptor, 0o600)
                except OSError:
                    os.close(file_descriptor)
                    raise
                digest = hashlib.sha256()
                total = 0
                first_bytes = bytearray()
                with os.fdopen(file_descriptor, "wb") as output:
                    while True:
                        if self.clock() >= deadline:
                            raise InfrastructureError("storage_download_timeout")
                        chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                        if self.clock() >= deadline:
                            raise InfrastructureError("storage_download_timeout")
                        if not chunk:
                            break
                        total += len(chunk)
                        if (
                            total > MAX_BYTES_BY_KIND[claim.kind]
                            or total > self.max_download_bytes
                            or total > claim.byte_size
                        ):
                            raise DeterministicScanError(
                                "byte_size_mismatch",
                                Observation(byte_size=total),
                            )
                        if len(first_bytes) < 16:
                            first_bytes.extend(chunk[: 16 - len(first_bytes)])
                        digest.update(chunk)
                        output.write(chunk)
                checksum = digest.hexdigest()
                observed_mime = detect_magic_mime(bytes(first_bytes))
                observation = Observation(
                    mime_type=observed_mime,
                    byte_size=total,
                    checksum_sha256=checksum,
                )
                if total != claim.byte_size:
                    raise DeterministicScanError("byte_size_mismatch", observation)
                if checksum != claim.checksum_sha256:
                    raise DeterministicScanError("checksum_mismatch", observation)
                if observed_mime is None:
                    raise DeterministicScanError("file_signature_invalid", observation)
                if observed_mime != claim.mime_type:
                    raise DeterministicScanError("mime_type_mismatch", observation)
                return DownloadedAsset(path=path, observation=observation)
        except urllib.error.HTTPError as error:
            if path is not None:
                path.unlink(missing_ok=True)
            if error.code in {404, 410}:
                raise DeterministicScanError("storage_object_missing") from error
            raise InfrastructureError("storage_request_failed") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if path is not None:
                path.unlink(missing_ok=True)
            raise InfrastructureError("storage_unavailable") from error
        except Exception:
            if path is not None:
                path.unlink(missing_ok=True)
            raise

    def cleanup_download(self, downloaded: DownloadedAsset) -> None:
        downloaded.path.unlink(missing_ok=True)

    def _rpc(self, name: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/rest/v1/rpc/{name}",
            data=body,
            headers={**self._headers, "Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.request_timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_JSON_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise InfrastructureError("scanner_rpc_rejected") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise InfrastructureError("scanner_rpc_unavailable") from error
        if len(raw) > MAX_PROVIDER_JSON_BYTES:
            raise ProviderProtocolError("scanner_rpc_response_invalid")
        try:
            result = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderProtocolError("scanner_rpc_response_invalid") from error
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            raise InfrastructureError("scanner_rpc_error")
        return result


class PillowImageInspector:
    """Run allowlisted Pillow decoding in a credential-free subprocess."""

    def __init__(
        self,
        *,
        max_pixels: int = 80_000_000,
        max_edge: int = 20_000,
        timeout_seconds: float = 30,
        memory_limit_bytes: int = 1024 * 1024 * 1024,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        probe_path: Path | None = None,
    ):
        try:
            from PIL import __version__
        except ImportError as error:
            raise InfrastructureError("pillow_unavailable") from error
        self._engine_version = _safe_engine_version(__version__)
        self.max_pixels = max(1, int(max_pixels))
        self.max_edge = max(1, int(max_edge))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.memory_limit_bytes = max(128 * 1024 * 1024, int(memory_limit_bytes))
        self.runner = runner
        self.probe_path = probe_path or Path(__file__).with_name("image_probe.py")
        if not self.probe_path.is_file() or self.probe_path.is_symlink():
            raise InfrastructureError("image_probe_unavailable")

    @property
    def engine_version(self) -> str:
        return self._engine_version

    def inspect(self, downloaded: DownloadedAsset, claim: AssetClaim) -> ImageInspection:
        try:
            result = self.runner(
                [
                    sys.executable,
                    "-I",
                    str(self.probe_path),
                    "--max-pixels",
                    str(self.max_pixels),
                    "--max-edge",
                    str(self.max_edge),
                    str(downloaded.path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                cwd=str(downloaded.path.parent),
                env=_scanner_subprocess_environment(),
                preexec_fn=_decode_resource_limiter(
                    self.memory_limit_bytes,
                    self.timeout_seconds,
                ),
            )
        except subprocess.TimeoutExpired as error:
            raise InfrastructureError("image_decode_timeout") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise InfrastructureError("image_probe_unavailable") from error

        raw = result.stdout.encode("utf-8", errors="ignore")
        if len(raw) > MAX_PROBE_JSON_BYTES:
            raise InfrastructureError("image_probe_response_invalid")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InfrastructureError("image_probe_response_invalid") from error
        if not isinstance(payload, dict):
            raise InfrastructureError("image_probe_response_invalid")

        width = payload.get("width")
        height = payload.get("height")
        observation = Observation(
            mime_type=downloaded.observation.mime_type,
            byte_size=downloaded.observation.byte_size,
            width=width if isinstance(width, int) and not isinstance(width, bool) else None,
            height=height if isinstance(height, int) and not isinstance(height, bool) else None,
            checksum_sha256=downloaded.observation.checksum_sha256,
        )
        if result.returncode == 2 and payload.get("status") == "failed":
            result_code = payload.get("result_code")
            if isinstance(result_code, str) and result_code in PROBE_FAILURE_CODES:
                raise DeterministicScanError(result_code, observation)
            raise InfrastructureError("image_probe_response_invalid")
        if result.returncode != 0 or payload.get("status") != "ok":
            raise InfrastructureError("image_probe_failed")
        if set(payload) != {"status", "mime_type", "width", "height", "engine_version"}:
            raise InfrastructureError("image_probe_response_invalid")
        decoded_mime = payload.get("mime_type")
        if decoded_mime != downloaded.observation.mime_type or decoded_mime != claim.mime_type:
            raise DeterministicScanError("decoded_format_mismatch", observation)
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
            or width < 1
            or height < 1
            or width > self.max_edge
            or height > self.max_edge
            or width * height > self.max_pixels
        ):
            raise DeterministicScanError("image_size_limit_exceeded", observation)
        if (width, height) != (claim.width, claim.height):
            raise DeterministicScanError("dimension_mismatch", observation)
        engine_version = _safe_engine_version(payload.get("engine_version"))
        return ImageInspection(
            mime_type=decoded_mime,
            width=width,
            height=height,
            engine_version=engine_version,
        )


class ClamAVScanner:
    """ClamAV subprocess adapter with injectable runner and fail-closed results."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 60,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        process_environment: Mapping[str, str] | None = None,
    ):
        if not command or not str(command[0]).strip():
            raise InfrastructureError("clamav_command_invalid")
        self.command = tuple(str(part) for part in command)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.runner = runner
        self.process_environment = dict(process_environment or _scanner_subprocess_environment())
        self._engine_version = "unknown"

    @property
    def engine_version(self) -> str:
        return self._engine_version

    def healthcheck(self) -> None:
        try:
            result = self.runner(
                [self.command[0], "--version"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=self.process_environment,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as error:
            raise InfrastructureError("clamav_unavailable") from error
        if result.returncode != 0:
            raise InfrastructureError("clamav_unavailable")
        lines = (result.stdout or result.stderr or "unknown").splitlines()
        first_line = lines[0] if lines else "unknown"
        self._engine_version = _safe_engine_version(first_line)

    def scan(self, path: Path) -> MalwareScan:
        try:
            result = self.runner(
                [*self.command, str(path)],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=self.process_environment,
            )
        except subprocess.TimeoutExpired as error:
            raise InfrastructureError("clamav_timeout") from error
        except (FileNotFoundError, OSError) as error:
            raise InfrastructureError("clamav_unavailable") from error
        if result.returncode == 0:
            return MalwareScan(flagged=False, engine_version=self.engine_version)
        if result.returncode == 1:
            return MalwareScan(flagged=True, engine_version=self.engine_version)
        raise InfrastructureError("clamav_scan_error")


def detect_magic_mime(value: bytes) -> str | None:
    if value.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if value.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP":
        return "image/webp"
    return None


def _canonical_uuid(value: Any, error_code: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise ProviderProtocolError(error_code) from error


def _worker_id(value: Any) -> str:
    worker_id = _strict_text(value, 120, "worker_id_invalid")
    if not WORKER_ID_PATTERN.fullmatch(worker_id):
        raise ProviderProtocolError("worker_id_invalid")
    return worker_id


def _strict_text(value: Any, maximum: int, error_code: str) -> str:
    if not isinstance(value, str):
        raise ProviderProtocolError(error_code)
    text = value.strip()
    if not text or len(text) > maximum or any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ProviderProtocolError(error_code)
    return text


def _positive_int(value: Any, maximum: int, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ProviderProtocolError(error_code)
    return value


def _validate_storage_key(value: Any, image_id: str, kind: str, mime_type: str) -> str:
    storage_key = _strict_text(value, 1024, "claim_response_invalid")
    if storage_key.startswith("/") or "\\" in storage_key:
        raise ProviderProtocolError("claim_response_invalid")
    parts = storage_key.split("/")
    if len(parts) != 3 or any(part in {"", ".", ".."} for part in parts):
        raise ProviderProtocolError("claim_response_invalid")
    _canonical_uuid(parts[0], "claim_response_invalid")
    if _canonical_uuid(parts[1], "claim_response_invalid") != image_id:
        raise ProviderProtocolError("claim_response_invalid")
    expected_name = f"{kind}.{EXTENSION_BY_MIME[mime_type]}"
    if parts[2] != expected_name:
        raise ProviderProtocolError("claim_response_invalid")
    return storage_key


def _validate_base_url(value: str) -> str:
    text = _strict_text(value, 2048, "scanner_url_invalid").rstrip("/")
    parsed = urlparse(text)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme not in ({"https", "http"} if loopback else {"https"})
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ProviderProtocolError("scanner_url_invalid")
    return text


def _safe_engine_version(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9 ._+:/()=-]", "", str(value or "unknown")).strip()
    return text[:160] or "unknown"


def _decode_resource_limiter(memory_limit_bytes: int, timeout_seconds: float) -> Callable[[], None] | None:
    if os.name != "posix":
        return None

    def apply_limits() -> None:
        import resource

        cpu_seconds = max(1, int(timeout_seconds) + 1)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        if hasattr(resource, "RLIMIT_AS"):
            try:
                resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
            except (OSError, ValueError):
                # macOS may expose RLIMIT_AS while refusing to apply it.
                pass
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

    return apply_limits


def _scanner_subprocess_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
    }
