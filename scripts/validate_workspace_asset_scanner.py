#!/usr/bin/env python3
"""Static validation for the trusted Workspace asset scanner boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260717_workspace_asset_scanner.sql"
SCHEMA_PATH = ROOT / "database" / "product_schema.sql"
ADAPTER_PATH = ROOT / "workers" / "scan_adapters.py"
WORKER_PATH = ROOT / "workers" / "image_scanner.py"
PROBE_PATH = ROOT / "workers" / "image_probe.py"
TEST_PATH = ROOT / "scripts" / "test_workspace_asset_scanner.py"
DATABASE_TEST_PATH = ROOT / "scripts" / "test_workspace_asset_scanner_database.sql"
CONFIGURE_PATH = ROOT / "scripts" / "configure_development_scanner.py"
CONFIGURE_TEST_PATH = ROOT / "scripts" / "test_configure_development_scanner.py"
REQUIREMENTS_PATH = ROOT / "requirements-scanner.txt"
WORKER_ENV_PATH = ROOT / ".env.worker.example"
WEB_ENV_PATH = ROOT / ".env.example"
SERVER_PATH = ROOT / "server.py"
GITIGNORE_PATH = ROOT / ".gitignore"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "database.yml"
RELEASE_GATE_PATH = ROOT / "scripts" / "release_gate.sh"
DEPLOY_PATH = ROOT / "scripts" / "deploy_supabase_phase1.sh"

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
FAILED_RESULT_CODES = {
    "download_size_limit_exceeded",
    "byte_size_mismatch",
    "checksum_mismatch",
    "file_signature_invalid",
    "mime_type_mismatch",
    "storage_object_missing",
    "multiple_frames_not_allowed",
    "decoded_format_mismatch",
    "image_size_limit_exceeded",
    "dimension_mismatch",
    "decompression_bomb",
    "image_decode_failed",
}
JOB_COLUMNS = {
    "id",
    "asset_id",
    "status",
    "attempt_count",
    "max_attempts",
    "available_at",
    "lease_token",
    "lease_owner",
    "lease_expires_at",
    "last_lease_token",
    "last_completed_attempt",
    "last_outcome",
    "last_result_fingerprint",
    "expected_storage_object_id",
    "storage_bucket",
    "storage_key",
    "mime_type",
    "byte_size",
    "width",
    "height",
    "checksum_sha256",
    "scan_policy_version",
    "scanner_version",
    "engine_name",
    "engine_version",
    "result_code",
    "result_details",
    "completed_at",
    "created_at",
    "updated_at",
}
EVENT_COLUMNS = {
    "id",
    "job_id",
    "asset_id",
    "attempt_number",
    "event_type",
    "worker_id",
    "result_code",
    "details",
    "created_at",
}


def read_required(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required Phase 2F file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def require_tokens(label: str, source: str, tokens: list[str]) -> None:
    lowered = source.lower()
    missing = [token for token in tokens if token.lower() not in lowered]
    if missing:
        raise RuntimeError(f"{label} is missing required boundary tokens: {missing}")


def require_compact_tokens(label: str, source: str, tokens: list[str]) -> None:
    normalized = compact(source)
    missing = [token for token in tokens if compact(token) not in normalized]
    if missing:
        raise RuntimeError(f"{label} is missing required normalized contracts: {missing}")


def table_columns(source: str, table_name: str) -> set[str]:
    declaration = re.search(
        rf"create\s+table(?:\s+if\s+not\s+exists)?\s+(?:public\.)?{re.escape(table_name)}\s*\(",
        source,
        flags=re.IGNORECASE,
    )
    if not declaration:
        raise RuntimeError(f"SQL table declaration is missing: {table_name}")
    opening = declaration.end() - 1
    depth = 0
    quote = False
    closing = -1
    index = opening
    while index < len(source):
        character = source[index]
        if character == "'":
            if quote and index + 1 < len(source) and source[index + 1] == "'":
                index += 2
                continue
            quote = not quote
        elif not quote:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        index += 1
    if closing < 0:
        raise RuntimeError(f"SQL table declaration is unterminated: {table_name}")

    body = source[opening + 1:closing]
    segments: list[str] = []
    start = 0
    depth = 0
    quote = False
    index = 0
    while index < len(body):
        character = body[index]
        if character == "'":
            if quote and index + 1 < len(body) and body[index + 1] == "'":
                index += 2
                continue
            quote = not quote
        elif not quote:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            elif character == "," and depth == 0:
                segments.append(body[start:index])
                start = index + 1
        index += 1
    segments.append(body[start:])

    columns: set[str] = set()
    for segment in segments:
        match = re.match(r"\s*([a-z_][a-z0-9_]*)\b", segment, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).lower()
        if name not in {"check", "constraint", "primary", "foreign", "unique"}:
            columns.add(name)
    return columns


def validate_schema_projection(migration: str, schema: str) -> None:
    for table_name, expected in (
        ("asset_scan_jobs", JOB_COLUMNS),
        ("asset_scan_events", EVENT_COLUMNS),
    ):
        migration_columns = table_columns(migration, table_name)
        schema_columns = table_columns(schema, table_name)
        if migration_columns != expected:
            raise RuntimeError(
                f"Migration {table_name} columns drifted: expected {sorted(expected)}, got {sorted(migration_columns)}"
            )
        if schema_columns != migration_columns:
            raise RuntimeError(
                f"Product schema {table_name} columns differ from the migration: {sorted(schema_columns)}"
            )


def validate_migration(source: str) -> None:
    require_tokens("asset scanner migration", source, [
        "-- Phase 2F: trusted, leased asset scanning",
        "begin;",
        "commit;",
        "add column if not exists scan_completed_at timestamptz",
        "add column if not exists scan_policy_version text",
        "create table if not exists public.asset_scan_jobs",
        "create table if not exists public.asset_scan_events",
        "asset_scan_jobs_claim_idx",
        "asset_scan_jobs_expired_lease_idx",
        "asset_scan_events_job_attempt_type_key",
        "alter table public.asset_scan_jobs enable row level security",
        "alter table public.asset_scan_events enable row level security",
        "revoke all on public.asset_scan_jobs from public, anon, authenticated, service_role",
        "revoke all on public.asset_scan_events from public, anon, authenticated, service_role",
        "revoke insert on public.image_assets from service_role",
        "revoke update on public.image_assets from service_role",
        "revoke delete on public.image_assets from service_role",
        "asset_scan_jobs_claim_prerequisites",
        "expected_storage_object_id is not null",
        "checksum_sha256 is not null",
        "asset_scan_jobs_terminal_immutable",
        "before update or delete on public.asset_scan_jobs",
        "asset_scan_events_append_only",
        "before update or delete on public.asset_scan_events",
        "image_assets_enqueue_scan_job",
        "after insert on public.image_assets",
        "new image assets must start with a pending scan",
        "every non-phase-2f clean asset is queued again",
        "coalesce(a.scan_policy_version, '') <> 'mt-asset-scan-2026-07-v1'",
        "for update of j skip locked",
        "new_lease_token := gen_random_uuid()",
        "attempt_count = j.attempt_count + 1",
        "requested_lease_seconds not between 30 and 900",
        "requested_retry_seconds not between 1 and 3600",
        "last_result_fingerprint",
        "where j.attempt_count = 0",
        "last_result_fingerprint = null",
        "job_row.last_result_fingerprint is not null",
        "scan_retry_exhausted",
        "job_row.lease_token is distinct from provided_lease_token",
        "job_row.lease_expires_at <= now()",
        "outcome_value not in ('clean', 'flagged', 'failed')",
        "outcome_value = 'clean' and result_code_value <> 'clean'",
        "outcome_value = 'flagged' and result_code_value <> 'malware_detected'",
        "result_code_value = any(allowed_failed_result_codes)",
        "scanner_version_value <> 'mt-presence-phase2f-1'",
        "engine_name_value <> 'clamav+pillow'",
        "SCAN_OBSERVATION_MISMATCH",
        "result_code_value = 'storage_object_missing'",
        "and object_row.id is not null",
        "storage.objects",
        "asset.scan.retry",
        "asset.scan.completed",
        "asset_scan_blocked",
        "assets_scan_complete",
    ])
    require_compact_tokens("asset scanner RPCs", source, [
        "create or replace function public.scanner_claim_asset_scan( worker_id text, lease_seconds integer default 300 )",
        "create or replace function public.scanner_retry_asset_scan( asset_id uuid, lease_token uuid, error_code text, retry_after_seconds integer )",
        "create or replace function public.scanner_complete_asset_scan( asset_id uuid, lease_token uuid, result jsonb )",
        "revoke all on function public.scanner_claim_asset_scan(text, integer) from public, anon, authenticated",
        "revoke all on function public.scanner_retry_asset_scan(uuid, uuid, text, integer) from public, anon, authenticated",
        "revoke all on function public.scanner_complete_asset_scan(uuid, uuid, jsonb) from public, anon, authenticated",
        "grant execute on function public.scanner_claim_asset_scan(text, integer) to service_role",
        "grant execute on function public.scanner_retry_asset_scan(uuid, uuid, text, integer) to service_role",
        "grant execute on function public.scanner_complete_asset_scan(uuid, uuid, jsonb) to service_role",
    ])

    if re.search(
        r"grant\s+(?:all|select|insert|update|delete)[^;]*"
        r"asset_scan_(?:jobs|events)[^;]*;",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raise RuntimeError("Scanner tables must remain inaccessible to API roles")

    rpc_grants = re.findall(
        r"grant\s+execute\s+on\s+function\s+public\."
        r"(scanner_(?:claim|retry|complete)_asset_scan)\([^)]*\)\s+to\s+([^;]+);",
        source,
        flags=re.IGNORECASE,
    )
    if len(rpc_grants) != 3 or any(role.strip().lower() != "service_role" for _, role in rpc_grants):
        raise RuntimeError(f"Scanner RPC grants must be service-role-only: {rpc_grants}")
    if {name.lower() for name, _ in rpc_grants} != {
        "scanner_claim_asset_scan",
        "scanner_retry_asset_scan",
        "scanner_complete_asset_scan",
    }:
        raise RuntimeError(f"Scanner RPC grant set drifted: {rpc_grants}")

    for rpc_name in (
        "scanner_claim_asset_scan",
        "scanner_retry_asset_scan",
        "scanner_complete_asset_scan",
    ):
        header = re.search(
            rf"create\s+or\s+replace\s+function\s+public\.{rpc_name}\(.*?\)"
            r"\s*returns\s+jsonb(?P<header>.*?)as\s+\$\$",
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not header:
            raise RuntimeError(f"Scanner RPC declaration cannot be parsed: {rpc_name}")
        normalized_header = compact(header.group("header"))
        if "security definer" not in normalized_header or "set search_path = ''" not in normalized_header:
            raise RuntimeError(f"Scanner RPC lacks a hardened security-definer header: {rpc_name}")

    allowlist_match = re.search(
        r"required_result_keys\s+constant\s+text\[\]\s*:=\s*array\[(.*?)\];",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not allowlist_match:
        raise RuntimeError("Completion RPC does not declare an exact result allowlist")
    declared_keys = set(re.findall(r"'([a-z][a-z0-9_]*)'", allowlist_match.group(1)))
    if declared_keys != RESULT_KEYS:
        raise RuntimeError(f"Completion result allowlist drifted: {sorted(declared_keys)}")
    if len(re.findall(r"'([a-z][a-z0-9_]*)'", allowlist_match.group(1))) != len(RESULT_KEYS):
        raise RuntimeError("Completion result allowlist contains duplicate fields")
    require_tokens("completion allowlist enforcement", source, [
        "where key <> all(required_result_keys)",
        "not (provided_result ?& required_result_keys)",
    ])

    failed_codes_match = re.search(
        r"allowed_failed_result_codes\s+constant\s+text\[\]\s*:=\s*array\[(.*?)\];",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not failed_codes_match:
        raise RuntimeError("Completion RPC does not declare deterministic failed-result codes")
    declared_failed_codes = re.findall(r"'([a-z][a-z0-9_]*)'", failed_codes_match.group(1))
    if set(declared_failed_codes) != FAILED_RESULT_CODES or len(declared_failed_codes) != len(FAILED_RESULT_CODES):
        raise RuntimeError(f"Completion failure-code allowlist drifted: {sorted(declared_failed_codes)}")


def validate_product_schema(source: str) -> None:
    require_tokens("product schema scanner projection", source, [
        "scan_completed_at timestamptz",
        "scan_policy_version text",
        "constraint image_assets_scan_terminal_metadata",
        "scan_status in ('clean', 'flagged', 'failed')",
        "create table asset_scan_jobs",
        "status in ('queued', 'leased', 'retry_wait', 'clean', 'flagged', 'failed')",
        "attempt_count integer not null default 0",
        "max_attempts integer not null default 5",
        "available_at timestamptz not null default now()",
        "lease_token uuid",
        "lease_owner text",
        "lease_expires_at timestamptz",
        "last_lease_token uuid",
        "last_result_fingerprint char(64)",
        "expected_storage_object_id uuid",
        "constraint asset_scan_jobs_claim_prerequisites",
        "expected_storage_object_id is not null",
        "checksum_sha256 is not null",
        "result_details jsonb not null default '{}'::jsonb",
        "asset_scan_jobs_claim_idx",
        "asset_scan_jobs_expired_lease_idx",
        "create table asset_scan_events",
        "asset_scan_events_job_attempt_type_key",
        "alter table asset_scan_jobs enable row level security",
        "alter table asset_scan_events enable row level security",
        "revoke all on asset_scan_jobs from public, anon, authenticated, service_role",
        "revoke all on asset_scan_events from public, anon, authenticated, service_role",
        "asset_scan_jobs_terminal_immutable",
        "asset_scan_events_append_only",
    ])


def validate_adapters(source: str) -> None:
    require_tokens("scanner adapters", source, [
        '"scanner_claim_asset_scan"',
        '"scanner_retry_asset_scan"',
        '"scanner_complete_asset_scan"',
        '"worker_id": _worker_id(worker_id)',
        "WORKER_ID_PATTERN",
        'self._headers = {"apikey": self.secret_key}',
        'if not self.secret_key.startswith("sb_secret_")',
        'self._headers["Authorization"] = f"Bearer {self.secret_key}"',
        "class RejectRedirectHandler",
        "provider_redirect_rejected",
        "build_opener(RejectRedirectHandler()).open",
        "/storage/v1/object/authenticated/",
        "DOWNLOAD_CHUNK_BYTES",
        "response.read(DOWNLOAD_CHUNK_BYTES)",
        "total > self.max_download_bytes",
        "os.fchmod(file_descriptor, 0o600)",
        "storage_object_missing",
        "storage_request_failed",
        "storage_unavailable",
        "storage_download_timeout",
        'Path(__file__).with_name("image_probe.py")',
        'sys.executable',
        '"-I"',
        "preexec_fn=_decode_resource_limiter",
        "env=_scanner_subprocess_environment()",
        "image_decode_timeout",
        "image_decode_failed",
        "decoded_format_mismatch",
        "dimension_mismatch",
        '[self.command[0], "--version"]',
        "[*self.command, str(path)]",
        "timeout=self.timeout_seconds",
        "env=self.process_environment",
        "if result.returncode == 0",
        "if result.returncode == 1",
        "clamav_scan_error",
        "downloaded.path.unlink(missing_ok=True)",
    ])
    lowered = source.lower()
    if '"cookie"' in lowered or '"x-csrf' in lowered:
        raise RuntimeError("Scanner adapters must not attach browser session or CSRF headers")


def validate_probe(source: str) -> None:
    require_tokens("credential-free Pillow probe", source, [
        'formats=("JPEG", "PNG", "WEBP")',
        "Image.MAX_IMAGE_PIXELS = max_pixels",
        "ImageFile.LOAD_TRUNCATED_IMAGES = False",
        'warnings.simplefilter("error", Image.DecompressionBombWarning)',
        "raw_width > max_edge",
        "raw_width * raw_height > max_pixels",
        "image.getexif().get(0x0112, 1)",
        "orientation in {5, 6, 7, 8}",
        "image.verify()",
        "image.load()",
        "multiple_frames_not_allowed",
        "decompression_bomb",
        "image_decode_failed",
    ])
    forbidden = [
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_URL",
        "urllib",
        "socket",
    ]
    leaked = [token for token in forbidden if token in source]
    if leaked:
        raise RuntimeError(f"Pillow probe contains privileged or network runtime access: {leaked}")


def validate_worker(source: str) -> None:
    require_tokens("scanner worker", source, [
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "MT_SCANNER_ID",
        "MT_SCANNER_CLAMAV_COMMAND",
        "MT_SCANNER_MAX_DOWNLOAD_BYTES",
        "MT_SCANNER_MAX_IMAGE_PIXELS",
        "MT_SCANNER_SCAN_TIMEOUT_SECONDS",
        "MT_SCANNER_DOWNLOAD_TIMEOUT_SECONDS",
        "MT_SCANNER_DECODE_TIMEOUT_SECONDS",
        "MT_SCANNER_DECODE_MEMORY_BYTES",
        "scanner_lease_budget_invalid",
        "mt-presence-scanner",
        "--once",
        "--poll-seconds",
        "--lease-seconds",
        "DeterministicScanError",
        "InfrastructureError",
        "cleanup_download",
        'outcome="clean"',
        'outcome="flagged"',
        'outcome="failed"',
        "provider.retry",
        "malware.flagged",
        "except Exception:",
    ])
    normalized = compact(source)
    secret_position = normalized.find('"supabase_secret_key"')
    legacy_position = normalized.find('"supabase_service_role_key"')
    if secret_position < 0 or legacy_position < 0 or secret_position >= legacy_position:
        raise RuntimeError("Worker must prefer SUPABASE_SECRET_KEY before the legacy service-role key")

    tree = ast.parse(source, filename=str(WORKER_PATH))
    safe_fields: set[str] | None = None
    claim_fields: set[str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SAFE_LOG_FIELDS"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Set):
                safe_fields = {
                    item.value for item in node.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_claim_log_fields":
            returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
            if len(returns) == 1 and isinstance(returns[0].value, ast.Dict):
                claim_fields = {
                    key.value for key in returns[0].value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
    expected_safe_fields = {
        "asset_id", "image_id", "kind", "attempt_number",
        "outcome", "result_code", "duration_ms",
    }
    if safe_fields != expected_safe_fields:
        raise RuntimeError(f"Worker structured log allowlist drifted: {sorted(safe_fields or set())}")
    expected_claim_fields = {"asset_id", "image_id", "kind", "attempt_number"}
    if claim_fields != expected_claim_fields:
        raise RuntimeError(f"Worker claim log fields drifted: {sorted(claim_fields or set())}")


def validate_no_sensitive_logging(paths: list[Path]) -> None:
    log_functions = {
        "print", "debug", "info", "warning", "warn", "error", "exception", "critical", "log",
    }
    sensitive_names = {
        "secret_key", "service_role_key", "storage_key", "lease_token",
    }
    for path in paths:
        source = read_required(path)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as error:
            raise RuntimeError(f"Python syntax invalid in {path.relative_to(ROOT)}: {error}") from error
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            function = call.func.id if isinstance(call.func, ast.Name) else (
                call.func.attr if isinstance(call.func, ast.Attribute) else ""
            )
            if function not in log_functions:
                continue
            referenced = {
                node.id
                for argument in [*call.args, *(item.value for item in call.keywords)]
                for node in ast.walk(argument)
                if isinstance(node, ast.Name)
            }
            referenced.update(
                node.attr
                for argument in [*call.args, *(item.value for item in call.keywords)]
                for node in ast.walk(argument)
                if isinstance(node, ast.Attribute)
            )
            exposed = sorted(referenced & sensitive_names)
            if exposed:
                location = f"{path.relative_to(ROOT)}:{getattr(call, 'lineno', '?')}"
                raise RuntimeError(f"Sensitive scanner data is passed to logging at {location}: {exposed}")


def validate_dynamic_test(source: str) -> None:
    require_tokens("asset scanner integration test", source, [
        "ThreadingHTTPServer",
        "127.0.0.1",
        "Image.new",
        "scanner_claim_asset_scan",
        "scanner_retry_asset_scan",
        "scanner_complete_asset_scan",
        "clean-secret-header",
        "clean-legacy-header",
        "invalid-decode",
        "metadata-mismatch",
        "malware-flagged",
        "malware-transient",
        "storage-missing",
        "storage-unavailable",
        "redirect-not-followed",
        "credential inherited by scanner subprocess",
        'environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}',
        '"SUPABASE_URL": base_url',
        '"MT_SCANNER_TEMP_DIR": str(clam_command.parent)',
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "sb_secret_authorization",
        "legacy_authorization",
        "cookie",
        "csrf",
        "RESULT_KEYS",
        "STORAGE_KEY",
        "LEASE_TOKEN",
        "CLAM_SIGNATURE",
        "asset_scanner_sensitive_logs_exposed=no",
        "asset_scanner_redirect_credentials_exposed=no",
    ])
    if "os.environ.items()" in source:
        raise RuntimeError("Scanner integration test must not inherit the host environment wholesale")
    external_urls = [
        value for value in re.findall(r"https?://[^\"'\s}]+", source)
        if not value.startswith("http://127.0.0.1:")
    ]
    if external_urls:
        raise RuntimeError(f"Scanner integration test references non-loopback URLs: {external_urls}")


def validate_database_state_machine_test(source: str) -> None:
    require_tokens("asset scanner database state-machine test", source, [
        "-- Transactional Phase 2F state-machine verification. No verdict is committed.",
        "begin;",
        "scanner_claim_asset_scan('phase2f-db-test-a', 300)",
        "scanner_claim_asset_scan('phase2f-db-test-b', 300)",
        "scanner_claim_asset_scan('phase2f-db-test-c', 300)",
        "SKIP LOCKED claims were not disjoint",
        "scanner_complete_asset_scan(first_asset_id, first_token, clean_result)",
        "same-token completion was not idempotent",
        "SCAN_COMPLETION_CONFLICT",
        "scanner_retry_asset_scan(second_asset_id, second_token, 'storage_unavailable', 1)",
        "SCAN_LEASE_CONFLICT",
        "expired lease was not safely reclaimed",
        "attempt exhaustion did not fail closed",
        "rollback;",
        "workspace_asset_scanner_database_state_machine=yes",
    ])
    if re.search(r"(?mi)^\s*commit\s*;", source):
        raise RuntimeError("Scanner database state-machine test must always roll back")
    forbidden = [
        token for token in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "PGPASSWORD")
        if token in source
    ]
    if forbidden:
        raise RuntimeError(f"Scanner database state-machine test embeds credential names: {forbidden}")


def validate_delivery_contracts(
    requirements: str,
    worker_env: str,
    web_env: str,
    server: str,
    gitignore: str,
    workflow: str,
    release_gate: str,
    deploy: str,
) -> None:
    normalized_requirements = requirements.replace("\\\n", " ")
    dependency_tokens = normalized_requirements.split()
    hashes = {token for token in dependency_tokens if token.startswith("--hash=sha256:")}
    if not dependency_tokens or dependency_tokens[0] != "Pillow==12.3.0" or len(hashes) < 10:
        raise RuntimeError("Scanner dependency must pin Pillow 12.3.0 with official artifact hashes")
    require_tokens("scanner dependency hashes", requirements, [
        "--hash=sha256:23d27a3e0307ec2244cc51e7287b919aa68d097504ebe19df4e76a98a3eea5bd",
        "--hash=sha256:37d6d0a00072fd2948eb22bce7e1475f34569d90c87c59f7a2ec59541b77f7a6",
        "--hash=sha256:3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce",
    ])
    require_tokens("scanner environment example", worker_env, [
        "SUPABASE_URL=",
        "SUPABASE_SECRET_KEY=sb_secret_replace_me",
        "SUPABASE_SERVICE_ROLE_KEY",
        "MT_SCANNER_ID=",
        "MT_SCANNER_CLAMAV_COMMAND='clamdscan --fdpass --no-summary'",
        "MT_SCANNER_LEASE_SECONDS=300",
        "MT_SCANNER_RETRY_SECONDS=30",
        "MT_SCANNER_MAX_DOWNLOAD_BYTES=52428800",
        "MT_SCANNER_MAX_IMAGE_PIXELS=80000000",
        "MT_SCANNER_DOWNLOAD_TIMEOUT_SECONDS=60",
        "MT_SCANNER_SCAN_TIMEOUT_SECONDS=60",
        "MT_SCANNER_DECODE_TIMEOUT_SECONDS=30",
        "MT_SCANNER_DECODE_MEMORY_BYTES=1073741824",
    ])
    forbidden_web_tokens = {
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "scanner_claim_asset_scan",
        "scanner_retry_asset_scan",
        "scanner_complete_asset_scan",
        "workers.image_scanner",
        "workers.scan_adapters",
    }
    web_boundary = f"{web_env}\n{server}"
    leaked = sorted(token for token in forbidden_web_tokens if token in web_boundary)
    if leaked:
        raise RuntimeError(f"Web runtime contains scanner-only credentials or RPCs: {leaked}")
    require_tokens("scanner gitignore", gitignore, [
        ".env.*",
        "!.env.worker.example",
        ".venv*/",
    ])
    require_tokens("scanner CI entrypoint", workflow, [
        "python3 -m pip install --disable-pip-version-check --require-hashes -r requirements-scanner.txt",
        "source .env.worker.example",
        'test "$MT_SCANNER_CLAMAV_COMMAND" = "clamdscan --fdpass --no-summary"',
        "bash scripts/release_gate.sh",
    ])
    require_tokens("scanner release gate contract", release_gate, [
        "scripts/validate_workspace_asset_scanner.py",
        "scripts/test_workspace_asset_scanner.py",
        "scripts/test_configure_development_scanner.py",
        'for validator in "${static_validators[@]}"; do',
        'run_group "Static contract: $validator" python3 "$validator"',
        'for test_file in "${boundary_tests[@]}"; do',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    ])
    require_tokens("scanner deployment preflight", deploy, [
        'python3 "$root/scripts/validate_workspace_asset_scanner.py"',
    ])


def validate_development_configurator(configurator: str, configurator_test: str) -> None:
    require_tokens("scanner development configurator", configurator, [
        "getpass.getpass",
        "scanner_secret_missing",
        "scanner_secret_invalid",
        "sb_publishable_",
        "--clamav-command",
        "preflight_clamav(command)",
        "os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)",
        "os.replace(temporary_name, path)",
        "credentials_logged=no",
    ])
    if '"--secret"' in configurator or "'--secret'" in configurator:
        raise RuntimeError("Scanner configurator must not accept credentials as command arguments")
    require_tokens("scanner development configurator test", configurator_test, [
        "sb_publishable_not_a_scanner_secret",
        "scanner_configuration_mode_0600=yes",
        "scanner_configuration_invalid_key_fails_closed=yes",
        "scanner_configuration_clamav_preflight=yes",
        "scanner_configuration_secret_logged=no",
    ])


def main() -> None:
    migration = read_required(MIGRATION_PATH)
    schema = read_required(SCHEMA_PATH)
    adapters = read_required(ADAPTER_PATH)
    worker = read_required(WORKER_PATH)
    probe = read_required(PROBE_PATH)
    integration_test = read_required(TEST_PATH)
    database_test = read_required(DATABASE_TEST_PATH)
    configurator = read_required(CONFIGURE_PATH)
    configurator_test = read_required(CONFIGURE_TEST_PATH)
    requirements = read_required(REQUIREMENTS_PATH)
    worker_env = read_required(WORKER_ENV_PATH)
    web_env = read_required(WEB_ENV_PATH)
    server = read_required(SERVER_PATH)
    gitignore = read_required(GITIGNORE_PATH)
    workflow = read_required(WORKFLOW_PATH)
    release_gate = read_required(RELEASE_GATE_PATH)
    deploy = read_required(DEPLOY_PATH)

    validate_migration(migration)
    validate_product_schema(schema)
    validate_schema_projection(migration, schema)
    validate_adapters(adapters)
    validate_probe(probe)
    validate_worker(worker)
    validate_no_sensitive_logging([ADAPTER_PATH, WORKER_PATH, PROBE_PATH])
    validate_dynamic_test(integration_test)
    validate_database_state_machine_test(database_test)
    validate_development_configurator(configurator, configurator_test)
    validate_delivery_contracts(
        requirements,
        worker_env,
        web_env,
        server,
        gitignore,
        workflow,
        release_gate,
        deploy,
    )

    print("workspace_asset_scanner_migration_boundary=yes")
    print("workspace_asset_scanner_service_only_rpc=yes")
    print("workspace_asset_scanner_leases_and_retry=yes")
    print("workspace_asset_scanner_fail_closed_worker=yes")
    print("workspace_asset_scanner_pillow_full_decode=yes")
    print("workspace_asset_scanner_clamav_boundary=yes")
    print("workspace_asset_scanner_environment_isolation=yes")
    print("workspace_asset_scanner_sensitive_logging=no")
    print("workspace_asset_scanner_product_schema_synced=yes")
    print("workspace_asset_scanner_database_test_contract=yes")
    print("workspace_asset_scanner_configuration_boundary=yes")


if __name__ == "__main__":
    main()
