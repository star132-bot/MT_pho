#!/usr/bin/env python3
"""Static contracts for Admin Works governance.

This validator keeps the PostgreSQL authority, protected HTTP boundary and
secret-free acceptance wired together. It is intentionally strict about
privilege, DTO projection and mutation semantics; it does not replace the
rollback-only PostgreSQL acceptance for the migration.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260723_admin_works_governance.sql"
SERVER_PATH = ROOT / "server.py"
BOUNDARY_PATH = ROOT / "scripts" / "test_admin_works_boundary.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "database.yml"
RELEASE_GATE_PATH = ROOT / "scripts" / "release_gate.sh"
SPEC_PATH = ROOT / "docs" / "product" / "user-upload-admin-spec.md"
FRONTEND_PATH = ROOT / "admin-works.js"


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required Admin Works file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def dense(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip().lower())


def require(source: str, tokens: set[str] | tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    missing = sorted(token for token in tokens if token.lower() not in lowered)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def forbid(source: str, tokens: set[str] | tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    found = sorted(token for token in tokens if token.lower() in lowered)
    if found:
        raise RuntimeError(f"{label} contains forbidden contract(s): {', '.join(found)}")


def require_order(source: str, tokens: tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    cursor = -1
    for token in tokens:
        cursor = lowered.find(token.lower(), cursor + 1)
        if cursor < 0:
            raise RuntimeError(f"{label} is missing or out of order at: {token}")


def python_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        candidates = node.body if isinstance(node, ast.ClassDef) else (node,)
        for candidate in candidates:
            if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and candidate.name == name:
                end = getattr(candidate, "end_lineno", candidate.lineno)
                return "\n".join(lines[candidate.lineno - 1 : end])
    raise RuntimeError(f"Required Python function is missing: {name}")


def sql_function(source: str, name: str) -> str:
    pattern = re.compile(
        rf"create\s+or\s+replace\s+function\s+public\.{re.escape(name)}\s*\(",
        re.I,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"Required SQL function is missing: public.{name}")
    tag_match = re.search(r"\bas\s+(\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)", source[match.end() :], re.I)
    if not tag_match:
        raise RuntimeError(f"SQL function public.{name} has no dollar-quoted body")
    tag = tag_match.group(1)
    body_start = match.end() + tag_match.end()
    body_end = source.find(tag, body_start)
    if body_end < 0:
        raise RuntimeError(f"SQL function public.{name} has an unterminated body")
    return source[match.start() : body_end + len(tag)]


def assert_security_definer(definition: str, label: str) -> None:
    require(definition, {"security definer", "set search_path = ''"}, label)


def validate_migration(migration: str) -> None:
    normalized = migration.strip().lower()
    if not normalized.startswith("begin;") or not normalized.endswith("commit;"):
        raise RuntimeError("Admin Works migration must remain transaction wrapped")

    compact = dense(migration)
    signatures = {
        "admin_list_images": "public.admin_list_images(text, text, text, integer, integer)",
        "admin_get_image": "public.admin_get_image(uuid)",
        "admin_govern_image": "public.admin_govern_image(uuid, integer, text, text, text, text, uuid)",
    }
    for name, signature in signatures.items():
        definition = sql_function(migration, name)
        assert_security_definer(definition, f"Admin Works {name} RPC")
        require(compact, {
            f"revoke all on function {signature} from public, anon, authenticated, service_role",
            f"grant execute on function {signature} to authenticated",
        }, f"Admin Works {name} ACL")

    storage_guard_signature = "public.can_read_admin_work_storage_object(uuid, text, text, text)"
    storage_guard = sql_function(migration, "can_read_admin_work_storage_object")
    assert_security_definer(storage_guard, "Admin Works Storage authorization guard")
    require(compact, {
        f"revoke all on function {storage_guard_signature} from public, anon, authenticated, service_role",
        f"grant execute on function {storage_guard_signature} to authenticated",
        "create policy admin_work_storage_objects_select on storage.objects",
    }, "Admin Works Storage policy/ACL")
    require(storage_guard, {
        "public.is_recovery_auth_session()",
        "public.has_aal2()",
        "public.current_app_user_id()",
        "account_status = 'active'",
        "'admin'::public.role_code",
        "'super_admin'::public.role_code",
        "target_object_id",
        "scan_job.expected_storage_object_id = storage_object.id",
        "asset.kind in ('display', 'thumbnail')",
        "asset.scan_status = 'clean'",
        "asset.scan_result_code = 'clean'",
        "asset.scan_policy_version = 'mt-asset-scan-2026-07-v1'",
        "scan_job.status = 'clean'",
        "scan_job.result_code = 'clean'",
        "scan_job.scan_policy_version = 'mt-asset-scan-2026-07-v1'",
        "scan_job.checksum_sha256 = asset.checksum_sha256",
    }, "Admin Works derivative Storage authorization")
    forbid(storage_guard, {
        "review_submissions",
        "'original'",
        "image-originals",
    }, "Admin Works original Storage authorization")

    review_storage_signature = "public.can_read_review_storage_object(text, text, text)"
    review_storage = sql_function(migration, "can_read_review_storage_object")
    assert_security_definer(review_storage, "Review Storage narrowed authorization guard")
    require(compact, {
        f"revoke all on function {review_storage_signature} from public, anon, authenticated, service_role",
        f"grant execute on function {review_storage_signature} to authenticated",
        "create policy review_storage_objects_select on storage.objects",
    }, "Review Storage policy/ACL")
    require(review_storage, {
        "public.is_recovery_auth_session()",
        "account_status = 'active'",
        "public.has_aal2()",
        "'reviewer'",
        "'admin','super_admin'",
        "asset.kind = 'original'",
        "asset.kind = 'display'",
        "asset.kind = 'thumbnail'",
        "submission.assigned_reviewer_id = actor_id",
        "submission.submitted_by_user_id <> actor_id",
    }, "Review Storage Admin/assigned-Reviewer authorization")

    helper_signatures = {
        "admin_governance_error": "public.admin_governance_error(text, text)",
        "admin_governance_failure_result": (
            "public.admin_governance_failure_result(uuid, public.role_code, uuid, text, text, integer, uuid, text, text)"
        ),
        "admin_require_governance_actor": "public.admin_require_governance_actor()",
        "admin_governance_actor_role": "public.admin_governance_actor_role(uuid)",
        "admin_image_asset_json": "public.admin_image_asset_json(uuid)",
        "admin_image_summary_json": "public.admin_image_summary_json(uuid)",
        "admin_governance_action_result": "public.admin_governance_action_result(uuid, boolean)",
    }
    for name, signature in helper_signatures.items():
        sql_function(migration, name)
        require(compact, {
            f"revoke all on function {signature} from public, anon, authenticated, service_role",
        }, f"Admin Works internal helper {name} ACL")

    actor_guard = sql_function(migration, "admin_require_governance_actor")
    assert_security_definer(actor_guard, "Admin Works database actor guard")
    require(actor_guard, {
        "public.is_recovery_auth_session()",
        "public.current_app_user_id()",
        "account_status = 'active'",
        "'admin'::public.role_code",
        "'super_admin'::public.role_code",
        "public.has_aal2()",
    }, "Admin Works database role/MFA/recovery guard")

    failure_audit = sql_function(migration, "admin_governance_failure_result")
    assert_security_definer(failure_audit, "Admin Works failure audit helper")
    require(failure_audit, {
        "public.current_app_user_id()",
        "actor.id = failure_actor_id",
        "actor.account_status = 'active'",
        "public.is_recovery_auth_session()",
        "public.has_aal2()",
        "insert into public.audit_logs",
        "'admin.image.governance_failed'",
        "'image_id', failure_image_id",
        "'action', safe_action",
        "'reason_code', safe_reason",
        "'error_code', failure_error_code",
        "'expected_version', safe_expected_version",
        "'current_version', current_image_version",
        "'policy_version', policy",
        "'failure'",
    }, "Admin Works controlled failure audit")
    forbid(failure_audit, {
        "submitted_user_message",
        "submitted_internal_note",
        "user_message",
        "internal_note",
        "access_token",
        "refresh_token",
    }, "Admin Works failure audit sensitive-data boundary")

    require(compact, {
        "account_status = 'active'",
        "'admin'::public.role_code",
        "'super_admin'::public.role_code",
        "public.has_aal2()",
        "public.is_recovery_auth_session()",
        "page_size",
        "page_offset",
        "search_query",
        "status_filter",
        "sort_code",
        "'actor'",
        "'items'",
        "'counts'",
        "'pagination'",
    }, "Admin Works list authorization/filter/DTO contract")

    summary = sql_function(migration, "admin_image_summary_json")
    assert_security_definer(summary, "Admin Works summary projection")
    require(summary, {
        "'owner'",
        "'thumbnail_asset'",
        "'asset_summary'",
        "'image_id', latest_submission.image_id",
        "'image_version_id', latest_submission.image_version_id",
    }, "Admin Works summary DTO")

    detail = sql_function(migration, "admin_get_image")
    require(detail, {
        "'work'",
        "'display_asset'",
        "'thumbnail_asset'",
        "'review_submissions'",
        "'governance_actions'",
        "'takedowns'",
        "'audit_timeline'",
    }, "Admin Works detail history DTO")
    forbid(detail, {"'original_asset'"}, "Admin Works detail original descriptor boundary")
    require(detail, {
        "'image_id', v.image_id",
        "'image_id', history.image_id",
        "'image_id', s.image_id",
        "'image_version_image_id', s.image_version_image_id",
        "'submission_id', d.submission_id",
        "'image_id', action_row.image_id",
        "'target_type', log_row.target_type",
        "'target_id', log_row.target_id",
    }, "Admin Works detail cross-record locators")

    govern = sql_function(migration, "admin_govern_image")
    require(govern, {
        "for update",
        "target_expected_version",
        "idempotency_key",
        "existing_action.expected_image_version is distinct from target_expected_version",
        "result_snapshot",
        "unpublish",
        "takedown",
        "restore",
        "copyright",
        "privacy",
        "illegal_content",
        "policy_violation",
        "security",
        "user_request",
        "appeal_upheld",
        "investigation_cleared",
        "administrative_error",
        "storage_visibility",
        "display",
        "thumbnail",
        "else 'private'",
        "mt-asset-scan-2026-07-v1",
        "storage_object.id = scan_job.expected_storage_object_id",
        "storage_object.owner_id = image_row.owner_user_id::text",
        "insert into public.takedown_cases",
        "insert into public.notifications",
        "insert into public.audit_logs",
        "public.admin_governance_failure_result(",
        "'image_id', image_row.id",
        "'actor_role', actor_role",
        "'policy_version', policy",
        "publication_status",
        "published_at",
        "unpublished_at",
    }, "Admin Works CAS/idempotency/governance contract")
    require_order(govern, (
        "idempotency_key",
        "for update",
        "target_expected_version",
        "update public.images",
        "insert into public.audit_logs",
    ), "Admin Works replay/lock/CAS/audit order")
    forbid(govern, {
        "update public.audit_logs",
        "delete from public.audit_logs",
        "kind = 'original' and storage_visibility = 'public'",
    }, "Admin Works immutable audit/original boundary")


def validate_server(server: str) -> None:
    ast.parse(server)
    require(server, {
        '"ADMIN_IMAGE_VERSION_CONFLICT": HTTPStatus.CONFLICT',
        '"ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT": HTTPStatus.CONFLICT',
        '"ADMIN_GOVERNANCE_STATE_CONFLICT": HTTPStatus.CONFLICT',
        '"ADMIN_GOVERNANCE_RESTORE_BLOCKED": HTTPStatus.CONFLICT',
        '"ADMIN_IMAGE_NOT_FOUND": HTTPStatus.NOT_FOUND',
        '"ADMIN_FILTER_INVALID": HTTPStatus.UNPROCESSABLE_ENTITY',
        '"ADMIN_GOVERNANCE_VALIDATION_FAILED": HTTPStatus.UNPROCESSABLE_ENTITY',
        '"admin_list_images"',
        '"admin_get_image"',
        '"admin_govern_image"',
        '"/admin/works"',
    }, "Admin Works stable HTTP/provider contract")

    admin_guard = python_function(server, "require_admin")
    require(admin_guard, {
        "session_has_auth_method",
        '"recovery"',
        '"RECOVERY_SESSION_RESTRICTED"',
        'authorization.get("account_status") != "active"',
        '{"admin", "super_admin"}',
        'authorization.get("aal") != "aal2"',
    }, "Admin Works shared Admin/recovery guard")

    for name in (
        "clean_admin_governance_action",
        "clean_admin_work_summary",
        "clean_admin_work_detail",
        "clean_admin_work_mutation_result",
        "admin_works_rpc",
        "sign_admin_work_asset",
        "present_admin_work_summary",
        "present_admin_work_detail",
        "handle_admin_works_list_get",
        "handle_admin_work_detail_get",
        "handle_admin_work_mutation",
        "serve_admin_works_page",
    ):
        python_function(server, name)

    action_cleaner = python_function(server, "clean_admin_governance_action")
    require(action_cleaner, {
        "expected_image_id",
        'value.get("image_id")',
        'value.get("actor_user_id")',
        'value.get("actor_role")',
        'value.get("policy_version")',
    }, "Admin Works governance action relationship projection")

    summary_cleaner = python_function(server, "clean_admin_work_summary")
    require(summary_cleaner, {
        'clean_admin_governance_action(value.get("latest_governance_action"), image_id)',
        'raw_review.get("image_id")',
        'raw_review.get("image_version_id")',
        "review_image_id != image_id",
    }, "Admin Works latest governance action relationship binding")

    detail_cleaner = python_function(server, "clean_admin_work_detail")
    require(detail_cleaner, {
        "clean_admin_governance_action(raw_action, image_id)",
        'clean_admin_current_version(value.get("current_version"), image_id)',
        'raw_version.get("image_id")',
        'raw_submission.get("image_id")',
        'raw_submission.get("image_version_image_id")',
        'raw_decision.get("submission_id")',
        'latest_review["submission_id"]',
        'raw_log.get("target_type")',
        'raw_log.get("target_id")',
    }, "Admin Works governance history relationship binding")

    mutation_cleaner = python_function(server, "clean_admin_work_mutation_result")
    require(mutation_cleaner, {
        'action["actor_user_id"] != actor["id"]',
        'action.get("actor_role") not in actor["roles"]',
        "ADMIN_WORKS_GOVERNANCE_POLICY_VERSION",
        'work["version"] != expected_image_version + 1',
        '"id", "image_id", "action", "reason_code", "actor_user_id", "actor_role", "policy_version"',
    }, "Admin Works mutation actor/version/latest-action binding")

    provider = python_function(server, "admin_works_rpc")
    require(provider, {'f"rpc/{name}"', "self.current_access_token", "ADMIN_WORKS_PROVIDER"}, "Admin Works provider boundary")
    forbid(provider, {"SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_PUBLISHABLE_KEY"}, "Admin Works provider credential boundary")

    signer = python_function(server, "sign_admin_work_asset")
    require(signer, {
        "self.current_access_token",
        "storage_bucket",
        "storage_key",
        "owner_user_id",
        "image_id",
        "mt-asset-scan-2026-07-v1",
        "signed_url",
        "10 * 60",
        "expected_signed_path",
        "urlparse(signed_url).path != expected_signed_path",
    }, "Admin Works private derivative signer")
    forbid(signer, {"SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_PUBLISHABLE_KEY"}, "Admin Works signer credential boundary")

    summary_presenter = python_function(server, "present_admin_work_summary")
    require(summary_presenter, {
        "sign_admin_work_asset",
        'work.pop("_owner_user_id", None)',
        '"_thumbnail_asset"',
        'thumbnail_asset.get("preview_eligible")',
        'latest_review.pop("_image_version_id", None)',
    }, "Admin Works list presenter")
    detail_presenter = python_function(server, "present_admin_work_detail")
    require(detail_presenter, {
        "sign_admin_work_asset",
        'work.pop("_owner_user_id", None)',
        '"_display_asset"',
        '"_thumbnail_asset"',
        'display_asset.get("preview_eligible")',
        'thumbnail_asset.get("preview_eligible")',
        'latest_review.pop("_image_version_id", None)',
    }, "Admin Works detail presenter")
    list_handler = python_function(server, "handle_admin_works_list_get")
    require(list_handler, {
        "require_admin",
        '"admin_list_images"',
        "clean_admin_work_list_result",
        "present_admin_work_summary",
        "page_size",
        "page_offset",
    }, "Admin Works list handler")

    detail_handler = python_function(server, "handle_admin_work_detail_get")
    require(detail_handler, {
        "require_admin",
        '"admin_get_image"',
        "clean_admin_work_detail_result",
        "present_admin_work_detail",
    }, "Admin Works detail handler")

    mutation_handler = python_function(server, "handle_admin_work_mutation")
    require(mutation_handler, {
        "require_admin",
        "read_json_body",
        '"expected_version"',
        '"idempotency_key"',
        '"reason_code"',
        '"public_message"',
        '"internal_note"',
        '"admin_govern_image"',
        "clean_admin_work_mutation_result",
    }, "Admin Works mutation validation/CAS handler")

    do_get = python_function(server, "do_GET")
    require(do_get, {
        '["api", "admin", "works"]',
        "handle_admin_works_list_get",
        "handle_admin_work_detail_get",
        "serve_admin_works_page",
    }, "Admin Works GET/page routes")
    do_post = python_function(server, "do_POST")
    require(do_post, {
        '["api", "admin", "works"]',
        '{"takedown", "restore"}',
        "require_csrf",
        "handle_admin_work_mutation",
    }, "Admin Works mutation routes")

    # Public disappearance must remain driven by the authoritative public RPC;
    # an Admin mutation cannot be masked by local sample/SQLite fallbacks.
    archive_handler = python_function(server, "handle_archive_images")
    require(archive_handler, {"auth_configured()", "handle_public_works_get"}, "Admin takedown public Works propagation")


def validate_frontend(frontend: str) -> None:
    require(frontend, {
        "record.audit_timeline",
        'event?.result === "failure"',
        "[...governanceHistory, ...failedAuditHistory]",
        'item.dataset.result = failed ? "failure" : "success"',
        'failed ? " - Failed" : ""',
    }, "Admin Works failure audit history UI")


def validate_boundary_and_wiring(boundary: str, workflow: str, release_gate: str, spec: str) -> None:
    compile(boundary, str(BOUNDARY_PATH.relative_to(ROOT)), "exec")
    require(boundary, {
        "FakeSupabaseHandler",
        "/api/admin/works",
        "/takedown",
        "/restore",
        "RECOVERY_SESSION_RESTRICTED",
        "ACCOUNT_RESTRICTED",
        "ADMIN_REQUIRED",
        "MFA_REQUIRED",
        "CSRF_REJECTED",
        "CONTENT_TYPE_INVALID",
        "ADMIN_IMAGE_VERSION_CONFLICT",
        "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT",
        "/api/archive/images",
        "/api/public/creators/",
        "admin_works_route_guards=yes",
        "admin_works_list_detail_allowlist=yes",
        "admin_works_governance_cas_idempotency=yes",
        "admin_works_derivative_preview_suppression=yes",
        "latest_actor_user_id",
        "latest_action",
        "latest_reason_code",
        "admin_works_public_takedown_restore=yes",
        "admin_works_provider_error_mapping=yes",
        "admin_works_governance_cross_record_binding=yes",
        "admin_works_signed_url_path_binding=yes",
        "assert_latest_review_allowlist",
        "admin_works_sensitive_fields_exposed=no",
    }, "Admin Works secret-free HTTP acceptance")
    require(workflow, {
        "bash scripts/release_gate.sh",
    }, "Admin Works CI entrypoint")
    require(release_gate, {
        "scripts/validate_admin_works.py",
        "scripts/test_admin_works_boundary.py",
        "admin-works.js",
        'for validator in "${static_validators[@]}"; do',
        'run_group "Static contract: $validator" python3 "$validator"',
        'for script in "${browser_scripts[@]}"; do',
        'run_group "JavaScript syntax: $script" node --check "$script"',
        'for test_file in "${boundary_tests[@]}"; do',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    }, "Admin Works release gate contract")
    require(spec, {
        "### 10.4 All Images",
        "### 10.5 Admin Image Detail",
        "#### Admin Takedown",
        "Published 图片被 Quarantine 后公开 API 立即不可见",
    }, "Admin Works product specification")


def main() -> None:
    migration = read(MIGRATION_PATH)
    server = read(SERVER_PATH)
    boundary = read(BOUNDARY_PATH)
    workflow = read(WORKFLOW_PATH)
    release_gate = read(RELEASE_GATE_PATH)
    spec = read(SPEC_PATH)
    frontend = read(FRONTEND_PATH)

    validate_migration(migration)
    validate_server(server)
    validate_frontend(frontend)
    validate_boundary_and_wiring(boundary, workflow, release_gate, spec)

    print("admin_works_static_contract=yes")
    print("Admin Works static contracts validated; run the secret-free HTTP boundary next.")


if __name__ == "__main__":
    main()
