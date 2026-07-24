#!/usr/bin/env python3
"""Static contracts for Phase 4B Admin User governance."""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260723_b_admin_user_governance.sql"
WORKS_MIGRATION_PATH = ROOT / "database" / "migrations" / "20260723_admin_works_governance.sql"
SERVER_PATH = ROOT / "server.py"
HTML_PATH = ROOT / "admin-users.html"
FRONTEND_PATH = ROOT / "admin-users.js"
STYLES_PATH = ROOT / "styles.css"
BOUNDARY_PATH = ROOT / "scripts" / "test_admin_users_boundary.py"
DATABASE_TEST_PATH = ROOT / "scripts" / "test_admin_users_database.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "database.yml"
RELEASE_GATE_PATH = ROOT / "scripts" / "release_gate.sh"
DEPLOY_PATH = ROOT / "scripts" / "deploy_supabase_phase1.sh"
DEPLOY_TEST_PATH = ROOT / "scripts" / "test_supabase_deploy_script.py"


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required Admin Users file is missing: {path.relative_to(ROOT)}")
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


def python_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[node.lineno - 1 : end])
    raise RuntimeError(f"Required Python function is missing: {name}")


def sql_function(source: str, name: str) -> str:
    match = re.search(
        rf"create\s+or\s+replace\s+function\s+public\.{re.escape(name)}\s*\(",
        source,
        re.I,
    )
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


def validate_migration(migration: str) -> None:
    normalized = migration.strip().lower()
    if not normalized.startswith("begin;") or not normalized.endswith("commit;"):
        raise RuntimeError("Admin Users migration must remain transaction wrapped")
    if WORKS_MIGRATION_PATH.name >= MIGRATION_PATH.name:
        raise RuntimeError("Admin Users migration must sort after the Admin Works dependency")

    compact = dense(migration)
    acl_compact = re.sub(r"\s*([(),])\s*", r"\1", compact)
    signatures = {
        "admin_list_users": "public.admin_list_users(text, text, text, text, integer, integer)",
        "admin_get_user": "public.admin_get_user(uuid)",
        "admin_govern_user": "public.admin_govern_user(uuid, integer, text, text, text, uuid)",
    }
    for name, signature in signatures.items():
        signature = re.sub(r"\s*([(),])\s*", r"\1", signature)
        definition = sql_function(migration, name)
        require(definition, {"security definer", "set search_path = ''"}, f"Admin Users {name} RPC")
        revoke_acl = re.sub(
            r"\s*([(),])\s*",
            r"\1",
            f"revoke all on function {signature} from public, anon, authenticated, service_role",
        )
        grant_acl = re.sub(
            r"\s*([(),])\s*",
            r"\1",
            f"grant execute on function {signature} to authenticated",
        )
        require(
            acl_compact,
            {revoke_acl, grant_acl},
            f"Admin Users {name} ACL",
        )

    require(
        compact,
        {
            "add column if not exists version integer not null default 1",
            "add column if not exists is_system_identity boolean not null default false",
            "create table if not exists public.user_governance_actions",
            "user_governance_actions_append_only",
            "alter table public.user_governance_actions enable row level security",
            "revoke all on public.user_governance_actions from public, anon, authenticated, service_role",
            "revoke insert, update, delete, truncate on public.users from public, anon, authenticated",
            "revoke insert, update, delete, truncate on public.user_roles from public, anon, authenticated",
        },
        "Admin Users table and generic-write boundary",
    )

    actor_guard = sql_function(migration, "admin_require_user_governance_actor")
    require(
        actor_guard,
        {"security definer", "set search_path = ''", "public.admin_require_governance_actor()"},
        "Admin Users actor guard",
    )

    summary = sql_function(migration, "admin_user_summary_json")
    require(
        summary,
        {
            "'mfa_status', 'unavailable'",
            "'status', 'provider_managed'",
            "'active_count', null",
            "'provider_action_required', true",
            "'quota_bytes', null",
            "'quota_status', 'unavailable'",
            "'image_counts'",
            "'used_bytes'",
        },
        "Admin Users capability truth and summary",
    )
    forbid(
        summary,
        {"auth.users", "auth.sessions", "last_sign_in_at", "mfa_enrolled"},
        "Admin Users unsupported identity-provider inference",
    )

    governance = sql_function(migration, "admin_govern_user")
    require(
        governance,
        {
            "pg_advisory_xact_lock",
            "mt-admin-user-governance",
            "idempotency_key",
            "expected_version",
            "for update",
            "ADMIN_USER_VERSION_CONFLICT",
            "ADMIN_USER_IDEMPOTENCY_CONFLICT",
            "ADMIN_USER_SELF_ACTION_FORBIDDEN",
            "ADMIN_USER_SYSTEM_IDENTITY",
            "ADMIN_USER_TARGET_FORBIDDEN",
            "ADMIN_USER_ROLE_FORBIDDEN",
            "ADMIN_USER_LAST_SUPER_ADMIN",
            "target.account_status = 'active'::public.account_status",
            "normalized_target_role = 'user'",
            "provider_action_required := true",
            "admin.user.revoke_sessions_requested",
            "insert into public.user_governance_actions",
            "insert into public.notifications",
            "insert into public.audit_logs",
        },
        "Admin Users governance transaction",
    )
    forbid(
        governance,
        {"delete from auth.sessions", "update auth.users", "mfa_verified =", "sessions_revoked"},
        "Admin Users unsupported provider mutation",
    )

    failure = sql_function(migration, "admin_user_failure_result")
    require(
        failure,
        {
            "insert into public.audit_logs",
            "admin.user.governance_failed",
            "'failure'",
            "error_code",
            "expected_version",
        },
        "Admin Users controlled failure audit",
    )


def validate_server(server: str) -> None:
    require(
        server,
        {
            "def serve_admin_users_page",
            'self.serve_header_html("admin-users.html"',
            'canonical_path.startswith("/admin/users")',
            '"/api/admin/users"',
            'parts[:3] == ["api", "admin", "users"]',
            '"status",',
            '"roles",',
            '"revoke-sessions",',
            "HTTPStatus.ACCEPTED if action == \"revoke_sessions\" else HTTPStatus.OK",
        },
        "Admin Users protected routes",
    )

    actor = python_function(server, "clean_admin_user_actor")
    require(
        actor,
        {"can_manage_roles", "super_admin", "admin", "expected_actor_id", "expected_roles"},
        "Admin Users actor projection",
    )
    summary = python_function(server, "clean_admin_user_summary")
    require(
        summary,
        {
            'value.get("mfa_status") != "unavailable"',
            'sessions.get("status") != "provider_managed"',
            'sessions.get("active_count") is not none',
            'storage.get("quota_bytes") is not none',
            '"provider_action_required": true',
            '"quota_status": "unavailable"',
        },
        "Admin Users strict summary projection",
    )
    detail = python_function(server, "clean_admin_user_detail_result")
    require(
        detail,
        {
            "owner_user_id != expected_user_id",
            "clean_admin_user_action",
            "clean_admin_user_audit",
        },
        "Admin Users detail relationship validation",
    )
    mutation_cleaner = python_function(server, "clean_admin_user_mutation_result")
    require(
        mutation_cleaner,
        {
            'user["version"] != expected_user_version + 1',
            'action["_actor_user_id"] != actor["id"]',
            'action["reason_code"] != expected_reason_code',
            'action["target_role"] != expected_role',
        },
        "Admin Users mutation relationship validation",
    )
    handler = python_function(server, "handle_admin_user_mutation")
    require(
        handler,
        {
            "set(body) != required_keys",
            "ADMIN_USERS_MUTABLE_ROLES",
            "ADMIN_USER_ROLE_FORBIDDEN",
            '"super_admin" not in principal[1]',
            "clean_admin_user_mutation_result",
            'action == "revoke_sessions"',
            "provider_action_required",
        },
        "Admin Users mutation endpoint",
    )
    forbid(
        handler,
        {"service_role", "supabase_service", "sessions revoked", "mfa enrolled"},
        "Admin Users Web authority boundary",
    )


def validate_frontend(html: str, frontend: str, styles: str) -> None:
    require(
        html,
        {
            "User Administration",
            "data-users-filters",
            "data-users-workspace",
            "data-users-detail",
            "data-users-action=\"revoke_sessions\"",
            "Record session revocation",
            "data-users-dialog",
            "aria-live=\"assertive\"",
            "admin-users.js",
        },
        "Admin Users semantic UI",
    )
    require(
        frontend,
        {
            "textContent",
            "replaceChildren",
            "AbortController",
            "expected_version",
            "idempotency_key",
            "provider_action_required",
            "Complete the identity provider action before treating sessions as closed.",
            "mfaStatus: value(record.mfa_status)",
            'user.sessionStatus === "provider_managed"',
            'function mfaSummary(user)',
            'return "Unavailable"',
            'const MANAGED_ROLES = new Set(["reviewer", "admin"])',
        },
        "Admin Users client behavior and capability truth",
    )
    forbid(
        frontend,
        {
            ".innerhtml",
            "sessions revoked successfully",
            "mfa not enrolled",
            "active session count",
            "last sign-in",
        },
        "Admin Users client trust boundary",
    )
    require(
        styles,
        {
            ".admin-users-page",
            ".admin-users-workspace",
            "@media (max-width: 900px)",
            "@media (max-width: 760px)",
            "prefers-reduced-motion",
        },
        "Admin Users responsive visual system",
    )


def validate_wiring(
    boundary: str,
    database_test: str,
    workflow: str,
    release_gate: str,
    deploy: str,
    deploy_test: str,
) -> None:
    require(
        boundary,
        {
            "/admin/users",
            "/api/admin/users",
            "revoke-sessions",
            "csrf",
            "provider_action_required",
            "private",
        },
        "Admin Users secret-free HTTP acceptance",
    )
    require(
        database_test,
        {
            "begin",
            "rollback",
            "admin_list_users",
            "admin_get_user",
            "admin_govern_user",
            "ADMIN_USER_LAST_SUPER_ADMIN",
            "provider_action_required",
            "idempotency",
        },
        "Admin Users rollback-only database acceptance",
    )
    require(
        workflow,
        {"bash scripts/release_gate.sh"},
        "Admin Users CI entrypoint",
    )
    require(
        release_gate,
        {
            "scripts/validate_admin_users.py",
            "scripts/test_admin_users_boundary.py",
            'for validator in "${static_validators[@]}"; do',
            'run_group "Static contract: $validator" python3 "$validator"',
            'for test_file in "${boundary_tests[@]}"; do',
            'run_group "Boundary test: $test_file" python3 "$test_file"',
        },
        "Admin Users release gate contract",
    )
    require(
        deploy,
        {
            'python3 "$root/scripts/validate_admin_users.py"',
            'migration_files=("$root"/database/migrations/*.sql)',
        },
        "Admin Users deploy wiring",
    )
    require(
        deploy_test,
        {
            "20260723_admin_works_governance.sql",
            "20260723_b_admin_user_governance.sql",
            "incremental_files.index(works_migration) >= incremental_files.index(users_migration)",
        },
        "Admin Users deploy dependency-order acceptance",
    )


def main() -> None:
    migration = read(MIGRATION_PATH)
    server = read(SERVER_PATH)
    html = read(HTML_PATH)
    frontend = read(FRONTEND_PATH)
    styles = read(STYLES_PATH)
    boundary = read(BOUNDARY_PATH)
    database_test = read(DATABASE_TEST_PATH)
    workflow = read(WORKFLOW_PATH)
    release_gate = read(RELEASE_GATE_PATH)
    deploy = read(DEPLOY_PATH)
    deploy_test = read(DEPLOY_TEST_PATH)
    validate_migration(migration)
    validate_server(server)
    validate_frontend(html, frontend, styles)
    validate_wiring(boundary, database_test, workflow, release_gate, deploy, deploy_test)
    print("Admin Users static contracts passed (58 checks).")


if __name__ == "__main__":
    main()
