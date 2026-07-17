#!/usr/bin/env python3
"""Independent polling worker for trusted image asset scanning."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import stat
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, TextIO

# Keep both `python -m workers.image_scanner` and direct script execution usable.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers import SCANNER_VERSION
from workers.scan_adapters import (
    AssetClaim,
    ClamAVScanner,
    DeterministicScanError,
    DownloadedAsset,
    ImageInspection,
    ImageInspector,
    InfrastructureError,
    MalwareScan,
    MalwareScanner,
    Observation,
    PillowImageInspector,
    ProviderProtocolError,
    ScanResult,
    ScannerAdapterError,
    ScannerProvider,
    SupabaseScannerAdapter,
    WORKER_ID_PATTERN,
)


ENGINE_NAME = "clamav+pillow"
SAFE_LOG_FIELDS = {
    "asset_id",
    "image_id",
    "kind",
    "attempt_number",
    "outcome",
    "result_code",
    "duration_ms",
}


class ConfigurationError(RuntimeError):
    """A startup error represented by a stable, non-sensitive code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class EventLogger(Protocol):
    def emit(self, event: str, **fields: Any) -> None: ...


class JsonEventLogger:
    """Write allowlisted structured events without provider or file locators."""

    def __init__(self, stream: TextIO = sys.stdout):
        self.stream = stream

    def emit(self, event: str, **fields: Any) -> None:
        record: dict[str, Any] = {"event": _safe_log_text(event, 80)}
        for key, value in fields.items():
            if key not in SAFE_LOG_FIELDS or value is None:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                record[key] = value
            else:
                record[key] = _safe_log_text(value, 160)
        self.stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
        self.stream.flush()


@dataclass(frozen=True)
class ScannerConfig:
    base_url: str
    secret_key: str
    worker_id: str
    clamav_command: tuple[str, ...]
    poll_seconds: float = 5.0
    lease_seconds: int = 300
    retry_seconds: int = 30
    request_timeout_seconds: float = 30.0
    download_timeout_seconds: float = 60.0
    scan_timeout_seconds: float = 60.0
    decode_timeout_seconds: float = 30.0
    decode_memory_bytes: int = 1024 * 1024 * 1024
    max_download_bytes: int = 50 * 1024 * 1024
    max_image_pixels: int = 80_000_000
    max_edge: int = 20_000
    temp_dir: Path | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "ScannerConfig":
        values = os.environ if environment is None else environment
        base_url = _required_environment(values, "SUPABASE_URL", "scanner_url_missing")
        secret_key = (values.get("SUPABASE_SECRET_KEY") or "").strip()
        if not secret_key:
            secret_key = (values.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not secret_key:
            raise ConfigurationError("scanner_secret_missing")
        if secret_key.startswith("sb_publishable_"):
            raise ConfigurationError("scanner_secret_invalid")
        worker_id = _required_environment(values, "MT_SCANNER_ID", "worker_id_missing")
        if not WORKER_ID_PATTERN.fullmatch(worker_id):
            raise ConfigurationError("worker_id_invalid")

        command_text = _required_environment(
            values,
            "MT_SCANNER_CLAMAV_COMMAND",
            "clamav_command_missing",
        )
        try:
            clamav_command = tuple(shlex.split(command_text))
        except ValueError as error:
            raise ConfigurationError("clamav_command_invalid") from error
        if not clamav_command:
            raise ConfigurationError("clamav_command_invalid")

        temp_root_text = (values.get("MT_SCANNER_TEMP_DIR") or "").strip()
        temp_root = (
            Path(temp_root_text).expanduser()
            if temp_root_text
            else Path(tempfile.gettempdir()) / "mt-presence-scanner"
        )
        temp_dir = _prepare_scanner_temp_dir(temp_root, worker_id)

        config = cls(
            base_url=base_url,
            secret_key=secret_key,
            worker_id=worker_id,
            clamav_command=clamav_command,
            poll_seconds=_environment_float(values, "MT_SCANNER_POLL_SECONDS", 5.0, 0.1, 3600.0),
            lease_seconds=_environment_int(values, "MT_SCANNER_LEASE_SECONDS", 300, 30, 900),
            retry_seconds=_environment_int(values, "MT_SCANNER_RETRY_SECONDS", 30, 1, 3600),
            request_timeout_seconds=_environment_float(
                values,
                "MT_SCANNER_REQUEST_TIMEOUT_SECONDS",
                30.0,
                1.0,
                120.0,
            ),
            download_timeout_seconds=_environment_float(
                values,
                "MT_SCANNER_DOWNLOAD_TIMEOUT_SECONDS",
                60.0,
                1.0,
                300.0,
            ),
            scan_timeout_seconds=_environment_float(
                values,
                "MT_SCANNER_SCAN_TIMEOUT_SECONDS",
                60.0,
                1.0,
                300.0,
            ),
            decode_timeout_seconds=_environment_float(
                values,
                "MT_SCANNER_DECODE_TIMEOUT_SECONDS",
                30.0,
                1.0,
                300.0,
            ),
            decode_memory_bytes=_environment_int(
                values,
                "MT_SCANNER_DECODE_MEMORY_BYTES",
                1024 * 1024 * 1024,
                128 * 1024 * 1024,
                4 * 1024 * 1024 * 1024,
            ),
            max_download_bytes=_environment_int(
                values,
                "MT_SCANNER_MAX_DOWNLOAD_BYTES",
                50 * 1024 * 1024,
                1,
                1024 * 1024 * 1024,
            ),
            max_image_pixels=_environment_int(
                values,
                "MT_SCANNER_MAX_IMAGE_PIXELS",
                80_000_000,
                1,
                1_000_000_000,
            ),
            max_edge=_environment_int(values, "MT_SCANNER_MAX_EDGE", 20_000, 1, 100_000),
            temp_dir=temp_dir,
        )
        return _validate_operation_budget(config)


class ImageScannerWorker:
    """Orchestrate one leased asset at a time through the scanner boundary."""

    def __init__(
        self,
        provider: ScannerProvider,
        image_inspector: ImageInspector,
        malware_scanner: MalwareScanner,
        *,
        worker_id: str,
        lease_seconds: int = 300,
        retry_seconds: int = 30,
        logger: EventLogger | None = None,
        clock: Any = time.monotonic,
    ):
        if not WORKER_ID_PATTERN.fullmatch(worker_id):
            raise ConfigurationError("worker_id_invalid")
        self.provider = provider
        self.image_inspector = image_inspector
        self.malware_scanner = malware_scanner
        self.worker_id = worker_id
        if not 30 <= lease_seconds <= 900:
            raise ConfigurationError("lease_seconds_invalid")
        if not 1 <= retry_seconds <= 3600:
            raise ConfigurationError("retry_seconds_invalid")
        self.lease_seconds = int(lease_seconds)
        self.retry_seconds = int(retry_seconds)
        self.logger = logger or JsonEventLogger()
        self.clock = clock

    def preflight(self) -> None:
        self.malware_scanner.healthcheck()

    def run_once(self) -> bool:
        claim = self.provider.claim(self.worker_id, self.lease_seconds)
        if claim is None:
            self.logger.emit("scanner_idle")
            return False
        self._process_claim(claim)
        return True

    def _process_claim(self, claim: AssetClaim) -> None:
        started_at = self.clock()
        downloaded: DownloadedAsset | None = None
        self.logger.emit("scan_started", **_claim_log_fields(claim))
        try:
            downloaded = self.provider.download(claim)
            malware = self.malware_scanner.scan(downloaded.path)
            if malware.flagged:
                result = self._result(
                    outcome="flagged",
                    result_code="malware_detected",
                    observation=downloaded.observation,
                    malware=malware,
                )
                self._complete(claim, result, started_at)
                return

            inspection = self.image_inspector.inspect(downloaded, claim)
            result = self._result(
                outcome="clean",
                result_code="clean",
                observation=_with_dimensions(downloaded.observation, inspection),
                malware=malware,
                inspection=inspection,
            )
            self._complete(claim, result, started_at)
        except DeterministicScanError as error:
            result = self._result(
                outcome="failed",
                result_code=error.code,
                observation=error.observation,
            )
            self._complete(claim, result, started_at)
        except InfrastructureError as error:
            self._retry(claim, error.code, started_at)
        except Exception:
            self._retry(claim, "scanner_internal_error", started_at)
        finally:
            if downloaded is not None:
                try:
                    self.provider.cleanup_download(downloaded)
                except Exception:
                    self.logger.emit("download_cleanup_failed", **_claim_log_fields(claim))

    def _result(
        self,
        *,
        outcome: str,
        result_code: str,
        observation: Observation,
        malware: MalwareScan | None = None,
        inspection: ImageInspection | None = None,
    ) -> ScanResult:
        versions = [
            f"clamav={malware.engine_version if malware else self.malware_scanner.engine_version}",
            f"pillow={inspection.engine_version if inspection else self.image_inspector.engine_version}",
        ]
        return ScanResult(
            outcome=outcome,
            result_code=result_code,
            scanner_version=SCANNER_VERSION,
            engine_name=ENGINE_NAME,
            engine_version=";".join(versions)[:120],
            observation=observation,
        )

    def _complete(self, claim: AssetClaim, result: ScanResult, started_at: float) -> None:
        try:
            self.provider.complete(claim, result)
        except Exception:
            self._retry(claim, "completion_failed", started_at)
            return
        self.logger.emit(
            "scan_completed",
            **_claim_log_fields(claim),
            outcome=result.outcome,
            result_code=result.result_code,
            duration_ms=_elapsed_ms(self.clock(), started_at),
        )

    def _retry(self, claim: AssetClaim, error_code: str, started_at: float) -> None:
        try:
            self.provider.retry(claim, error_code, self.retry_seconds)
        except Exception:
            self.logger.emit(
                "scan_retry_unacknowledged",
                **_claim_log_fields(claim),
                result_code="retry_failed",
                duration_ms=_elapsed_ms(self.clock(), started_at),
            )
            return
        self.logger.emit(
            "scan_retried",
            **_claim_log_fields(claim),
            result_code=error_code,
            duration_ms=_elapsed_ms(self.clock(), started_at),
        )


def build_worker(config: ScannerConfig, logger: EventLogger | None = None) -> ImageScannerWorker:
    provider = SupabaseScannerAdapter(
        config.base_url,
        config.secret_key,
        request_timeout_seconds=config.request_timeout_seconds,
        download_timeout_seconds=config.download_timeout_seconds,
        max_download_bytes=config.max_download_bytes,
        temp_dir=config.temp_dir,
    )
    inspector = PillowImageInspector(
        max_pixels=config.max_image_pixels,
        max_edge=config.max_edge,
        timeout_seconds=config.decode_timeout_seconds,
        memory_limit_bytes=config.decode_memory_bytes,
    )
    malware = ClamAVScanner(
        config.clamav_command,
        timeout_seconds=config.scan_timeout_seconds,
    )
    return ImageScannerWorker(
        provider,
        inspector,
        malware,
        worker_id=config.worker_id,
        lease_seconds=config.lease_seconds,
        retry_seconds=config.retry_seconds,
        logger=logger,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Poll and scan private MT Presence image assets.")
    parser.add_argument("--once", action="store_true", help="Claim at most one asset, then exit.")
    parser.add_argument("--poll-seconds", type=float, help="Override the idle polling interval.")
    parser.add_argument("--lease-seconds", type=int, help="Override the claimed lease duration.")
    parser.add_argument("--retry-seconds", type=int, help="Override the transient retry delay.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logger = JsonEventLogger()
    arguments = _argument_parser().parse_args(argv)
    try:
        config = ScannerConfig.from_environment()
        config = _apply_cli_overrides(config, arguments)
        worker = build_worker(config, logger)
        worker.preflight()
    except (ConfigurationError, ScannerAdapterError) as error:
        logger.emit("scanner_startup_failed", result_code=error.code)
        return 2
    except Exception:
        logger.emit("scanner_startup_failed", result_code="scanner_startup_error")
        return 2

    logger.emit("scanner_ready")
    if arguments.once:
        try:
            worker.run_once()
            return 0
        except (InfrastructureError, ProviderProtocolError) as error:
            logger.emit("scanner_claim_failed", result_code=error.code)
            return 2
        except Exception:
            logger.emit("scanner_claim_failed", result_code="scanner_internal_error")
            return 2

    try:
        while True:
            try:
                processed = worker.run_once()
            except ScannerAdapterError as error:
                logger.emit("scanner_claim_failed", result_code=error.code)
                processed = False
            except Exception:
                logger.emit("scanner_claim_failed", result_code="scanner_internal_error")
                processed = False
            if not processed:
                time.sleep(config.poll_seconds)
    except KeyboardInterrupt:
        logger.emit("scanner_stopped")
        return 0


def _apply_cli_overrides(config: ScannerConfig, arguments: argparse.Namespace) -> ScannerConfig:
    poll_seconds = config.poll_seconds
    lease_seconds = config.lease_seconds
    retry_seconds = config.retry_seconds
    if arguments.poll_seconds is not None:
        poll_seconds = _bounded_number(arguments.poll_seconds, 0.1, 3600.0, "poll_seconds_invalid")
    if arguments.lease_seconds is not None:
        lease_seconds = int(_bounded_number(arguments.lease_seconds, 30, 900, "lease_seconds_invalid"))
    if arguments.retry_seconds is not None:
        retry_seconds = int(_bounded_number(arguments.retry_seconds, 1, 3600, "retry_seconds_invalid"))
    return _validate_operation_budget(replace(
        config,
        poll_seconds=float(poll_seconds),
        lease_seconds=lease_seconds,
        retry_seconds=retry_seconds,
    ))


def _required_environment(values: Mapping[str, str], name: str, error_code: str) -> str:
    value = (values.get(name) or "").strip()
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ConfigurationError(error_code)
    return value


def _environment_int(
    values: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = (values.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name.lower()}_invalid") from error
    return int(_bounded_number(value, minimum, maximum, f"{name.lower()}_invalid"))


def _environment_float(
    values: Mapping[str, str],
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = (values.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name.lower()}_invalid") from error
    return float(_bounded_number(value, minimum, maximum, f"{name.lower()}_invalid"))


def _bounded_number(value: float, minimum: float, maximum: float, error_code: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < minimum or value > maximum:
        raise ConfigurationError(error_code)
    return value


def _validate_operation_budget(config: ScannerConfig) -> ScannerConfig:
    required_seconds = math.ceil(
        config.download_timeout_seconds
        + config.scan_timeout_seconds
        + config.decode_timeout_seconds
        + (3 * config.request_timeout_seconds)
        + 30
    )
    if config.lease_seconds < required_seconds:
        raise ConfigurationError("scanner_lease_budget_invalid")
    return config


def _prepare_scanner_temp_dir(root: Path, worker_id: str) -> Path:
    try:
        if root.exists() and root.is_symlink():
            raise ConfigurationError("scanner_temp_dir_invalid")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        worker_hash = hashlib.sha256(worker_id.encode("utf-8")).hexdigest()[:20]
        worker_dir = root / worker_hash
        if worker_dir.exists() and worker_dir.is_symlink():
            raise ConfigurationError("scanner_temp_dir_invalid")
        worker_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(worker_dir, 0o700)
        if stat.S_IMODE(worker_dir.stat().st_mode) != 0o700:
            raise ConfigurationError("scanner_temp_dir_invalid")
        for candidate in worker_dir.glob("mt-scan-*.bin"):
            if candidate.is_file() and not candidate.is_symlink():
                candidate.unlink(missing_ok=True)
        return worker_dir
    except ConfigurationError:
        raise
    except OSError as error:
        raise ConfigurationError("scanner_temp_dir_invalid") from error


def _with_dimensions(observation: Observation, inspection: ImageInspection) -> Observation:
    return Observation(
        mime_type=inspection.mime_type,
        byte_size=observation.byte_size,
        width=inspection.width,
        height=inspection.height,
        checksum_sha256=observation.checksum_sha256,
    )


def _claim_log_fields(claim: AssetClaim) -> dict[str, Any]:
    return {
        "asset_id": claim.asset_id,
        "image_id": claim.image_id,
        "kind": claim.kind,
        "attempt_number": claim.attempt_number,
    }


def _elapsed_ms(current: float, started: float) -> int:
    return max(0, int((current - started) * 1000))


def _safe_log_text(value: Any, maximum: int) -> str:
    text = str(value)
    return "".join(character for character in text if 32 <= ord(character) < 127)[:maximum]


if __name__ == "__main__":
    raise SystemExit(main())
