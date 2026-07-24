#!/usr/bin/env python3
"""Static contracts for published Works and public creator delivery.

These checks deliberately complement, rather than replace, the secret-free
HTTP boundary and rollback-only PostgreSQL acceptance. They keep the public
read model, anonymous asset-signing boundary, browser source, CI, and deploy
preflight wired together as one vertical slice.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260722_public_delivery.sql"
SERVER_PATH = ROOT / "server.py"
ARCHIVE_CLIENT_PATH = ROOT / "archive.js"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "database.yml"
RELEASE_GATE_PATH = ROOT / "scripts" / "release_gate.sh"
DEPLOY_PATH = ROOT / "scripts" / "deploy_supabase_phase1.sh"
BOUNDARY_TEST_PATH = ROOT / "scripts" / "test_public_delivery_boundary.py"
DATABASE_TEST_PATH = ROOT / "scripts" / "test_public_delivery_database.py"
TESTING_PATH = ROOT / "docs" / "operations" / "public-delivery-testing.md"


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required public-delivery file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def compact(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip().lower())


def require(source: str, tokens: set[str] | tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    missing = sorted(token for token in tokens if token.lower() not in lowered)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def require_order(source: str, tokens: tuple[str, ...], label: str) -> None:
    cursor = -1
    for token in tokens:
        cursor = source.find(token, cursor + 1)
        if cursor < 0:
            raise RuntimeError(f"{label} is missing or out of order at: {token}")


def forbid(source: str, tokens: set[str] | tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    found = sorted(token for token in tokens if token.lower() in lowered)
    if found:
        raise RuntimeError(f"{label} contains forbidden contract(s): {', '.join(found)}")


def python_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[node.lineno - 1:end])
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                    end = getattr(child, "end_lineno", child.lineno)
                    return "\n".join(lines[child.lineno - 1:end])
    raise RuntimeError(f"Required Python function is missing: {name}")


def validate_migration(migration: str) -> None:
    normalized = migration.strip().lower()
    if not normalized.startswith("begin;") or not normalized.endswith("commit;"):
        raise RuntimeError("Public delivery migration must remain transaction wrapped")

    dense = compact(migration)
    require(dense, {
        "create or replace function public.get_public_works( target_creator_slug text default null, page_limit integer default 100, page_offset integer default 0 )",
        "create or replace function public.get_public_creator(target_creator_slug text)",
        "create or replace function public.get_my_public_delivery_status()",
        "security definer",
        "set search_path = ''",
        "publication_status = 'published'",
        "processing_status = 'ready'",
        "deleted_at is null",
        "account_status = 'active'",
        "storage_visibility = 'public'",
        "scan_status = 'clean'",
        "scan_policy_version = 'mt-asset-scan-2026-07-v1'",
        "kind in ('display', 'thumbnail')",
        "public.public_delivery_work_json(a.image_id) as value",
        "work.value is not null",
        "work.value #>> '{display_asset,id}'",
        "work.value #>> '{thumbnail_asset,id}'",
        "drop policy if exists images_public_select on public.images",
        "drop policy if exists versions_public_select on public.image_versions",
        "revoke select on public.images from anon, authenticated",
        "revoke select on public.image_versions from anon, authenticated",
        "grant execute on function public.get_public_works(text, integer, integer) to anon, authenticated",
        "grant execute on function public.get_public_creator(text) to anon, authenticated",
        "grant execute on function public.get_my_public_delivery_status() to authenticated",
        "grant execute on function public.can_read_public_storage_object(text, text, text) to anon, authenticated",
    }, "Public delivery migration")
    require(dense, {
        "revoke all on function public.get_public_works(text, integer, integer) from public, anon, authenticated, service_role",
        "revoke all on function public.get_public_creator(text) from public, anon, authenticated, service_role",
        "revoke all on function public.get_my_public_delivery_status() from public, anon, authenticated, service_role",
        "revoke all on function public.can_read_public_storage_object(text, text, text) from public, anon, authenticated, service_role",
    }, "Public delivery RPC least-privilege reset")

    if migration.lower().count("security definer") < 6:
        raise RuntimeError("Every public-delivery security boundary function must be SECURITY DEFINER")
    if migration.lower().count("set search_path = ''") < 6:
        raise RuntimeError("Every public-delivery security boundary function must pin an empty search_path")

    forbid(dense, {
        "grant select on public.user_profiles to anon",
        "grant select on public.image_assets to anon",
        "storage_visibility = 'private' and i.publication_status = 'published'",
    }, "Public delivery raw-table/private-asset boundary")


def validate_server(server: str) -> None:
    ast.parse(server)
    require(server, {
        'if parsed.path == "/api/archive/images":',
        '["api", "public", "creators"]',
        'self.path = "/creator.html"',
        '"get_public_works"',
        '"get_public_creator"',
        '"rpc/get_my_public_delivery_status"',
        '"PUBLIC_DELIVERY_PROVIDER_FAILED"',
        'SUPABASE_PUBLISHABLE_KEY',
    }, "Public delivery HTTP boundary")

    do_get = python_function(server, "do_GET")
    require(do_get, {
        'parsed.path == "/api/archive/images"',
        '["api", "public", "creators"]',
    }, "Public delivery GET routes")

    # These names form the stable server-side projection boundary. Storage
    # coordinates may exist only before projection and must never reach JSON.
    for name in (
        "clean_public_delivery_asset",
        "clean_public_work",
        "clean_public_creator",
        "public_delivery_rpc",
        "sign_public_delivery_asset",
        "public_work_payload",
        "handle_public_works_get",
        "handle_public_creator_get",
    ):
        python_function(server, name)

    asset_cleaner = python_function(server, "clean_public_delivery_asset")
    require(asset_cleaner, {
        "PUBLIC_DELIVERY_ASSET_KINDS",
        "PUBLIC_DELIVERY_ASSET_BUCKETS",
        "expected_kind",
        'storage_key.split("/")',
        'part in {"", ".", ".."}',
        "owner_prefix",
    }, "Public derivative descriptor validator")

    provider = python_function(server, "public_delivery_rpc")
    require(provider, {
        'f"rpc/{name}"',
        "SUPABASE_PUBLISHABLE_KEY",
        "send_public_delivery_error",
    }, "Anonymous public RPC provider")
    forbid(provider, {"current_access_token", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"}, "Anonymous public RPC provider")

    signer = python_function(server, "sign_public_delivery_asset")
    require(signer, {
        "SUPABASE_PUBLISHABLE_KEY",
        "asset['storage_bucket']",
        "asset['storage_key']",
        '"signed_url"',
        '"expires_in"',
    }, "Anonymous derivative signer")
    forbid(signer, {"current_access_token", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"}, "Anonymous derivative signer")

    projection = python_function(server, "public_work_payload")
    require(projection, {
        'work["display_asset"]',
        'work["thumbnail_asset"]',
        '"visibility": "published"',
        '"source_type": "supabase_public"',
    }, "Public browser work projection")
    forbid(projection, {'"storage_bucket"', '"storage_key"', '"original"'}, "Public browser work projection")

    archive_handler = python_function(server, "handle_archive_images")
    require(archive_handler, {
        "auth_configured()",
        "self.handle_public_works_get(query)",
        '"local-sqlite"',
        "LOCAL_ARCHIVE_PREVIEW",
        'RUNTIME_ENVIRONMENT == "development"',
        "self.is_loopback_request()",
        'filters.append("source_type = ?")',
        'params.append("local_sample")',
        '"local-sqlite-preview" if local_preview else "local-sqlite"',
    }, "Configured public Works dispatch")

    do_get = python_function(server, "do_GET")
    require(do_get, {
        "not auth_configured()",
        "is_public_derivative",
        'canonical_path == "/assets/uploads"',
    }, "Configured legacy asset fail-closed boundary")

    for name in ("handle_public_works_get", "handle_public_creator_get"):
        handler = python_function(server, name)
        forbid(handler, {"require_account_session", "require_admin", "require_reviewer"}, f"{name} anonymous access")

    works_handler = python_function(server, "handle_public_works_get")
    require(works_handler, {
        "load_public_delivery_works",
        "PUBLIC_DELIVERY_MAX_WORKS",
        "signed_public_works",
    }, "Public Works handler")
    paged_works = python_function(server, "load_public_delivery_works")
    require(paged_works, {
        '"get_public_works"',
        '"page_offset": offset',
        'page_limit = min(100, maximum - len(items))',
        'cleaned["count"] != total_count',
        'item["id"] in seen_ids',
        "send_public_delivery_error",
    }, "Bounded public Works pagination")
    creator_handler = python_function(server, "handle_public_creator_get")
    require(creator_handler, {
        '"get_public_creator"',
        "clean_public_creator",
        "load_public_delivery_works",
        "public_work_payload",
        "sign_public_delivery_asset",
    }, "Public creator handler")


def validate_archive_client(client: str) -> None:
    require(client, {
        'const ARCHIVE_API_URL = "/api/archive/images"',
        "async function fetchArchiveApiItems()",
        "apiResult = await fetchArchiveApiItems()",
        "const authoritative = apiResult?.authoritative === true || apiError?.authoritative === true",
        "if (authoritative)",
        'archiveDataSource = apiResult?.source || apiError?.source || "supabase"',
        'archiveItems = (apiResult?.items || []).filter(isPublishedArchiveItem)',
        'setArchiveDataStatus(archiveItems.length ? "Published works loaded." : "No published works yet.", "ready")',
        'typeof apiError.authoritative !== "boolean"',
        "apiError.authoritative = true",
    }, "Works authoritative public source")
    require_order(client, (
        "if (authoritative) {",
        'archiveItems = (apiResult?.items || []).filter(isPublishedArchiveItem);',
        "} else {",
        "let baseItems = sampleItems;",
    ), "Works authoritative result before legacy fallback")


def validate_tests_and_wiring(
    boundary: str,
    database_test: str,
    workflow: str,
    release_gate: str,
    deploy: str,
    testing: str,
) -> None:
    compile(boundary, str(BOUNDARY_TEST_PATH.relative_to(ROOT)), "exec")
    compile(database_test, str(DATABASE_TEST_PATH.relative_to(ROOT)), "exec")
    require(boundary, {
        "FakeSupabaseHandler",
        "approve-and-publish",
        "/api/archive/images",
        "/api/public/creators/",
        "public_delivery_approve_hidden=yes",
        "public_delivery_publish_visible=yes",
        "public_delivery_derivative_signing=yes",
        "public_delivery_original_exposed=no",
        "public_delivery_private_fields_exposed=no",
        "public_delivery_authoritative_empty=yes",
    }, "Secret-free public delivery boundary")
    require(database_test, {
        "MT_TEST_ENVIRONMENT",
        "MT_ALLOW_PRODUCTION",
        "pg_advisory_xact_lock",
        "rollback;",
        "assert_fixtures_absent",
        "insert into public.folders",
        "'Inbox'",
        "partial_thumbnail_allowed := public.can_read_public_storage_object(",
        "anonymous Storage boundary mismatch (count=%, display=%, original=%, suspended=%, partial_thumbnail=%)",
        "public_delivery_database_published_only=yes",
        "public_delivery_database_account_status=yes",
        "public_delivery_database_storage_boundary=yes",
        "public_delivery_database_selected_derivatives=yes",
        "public_delivery_database_creator_projection=yes",
        "public_delivery_database_owner_cover=yes",
        "public_delivery_database_fixtures_rolled_back=yes",
    }, "Rollback-only public delivery database acceptance")
    require(workflow, {
        "bash scripts/release_gate.sh",
    }, "Public delivery CI entrypoint")
    require(release_gate, {
        "scripts/validate_public_delivery.py",
        "scripts/test_public_delivery_boundary.py",
        'for validator in "${static_validators[@]}"; do',
        'run_group "Static contract: $validator" python3 "$validator"',
        'for test_file in "${boundary_tests[@]}"; do',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    }, "Public delivery release gate contract")
    require(deploy, {"python3 \"$root/scripts/validate_public_delivery.py\""}, "Public delivery deploy preflight")
    require(testing, {
        "# Public Delivery Testing",
        "python3 scripts/validate_public_delivery.py",
        "python3 scripts/test_public_delivery_boundary.py",
        "MT_TEST_ENVIRONMENT=development python3 scripts/test_public_delivery_database.py",
        "Static validation cannot prove",
        "PostgreSQL RLS or Storage behavior.",
    }, "Public delivery testing runbook")


def main() -> None:
    migration = read(MIGRATION_PATH)
    server = read(SERVER_PATH)
    archive_client = read(ARCHIVE_CLIENT_PATH)
    boundary = read(BOUNDARY_TEST_PATH)
    database_test = read(DATABASE_TEST_PATH)
    workflow = read(WORKFLOW_PATH)
    release_gate = read(RELEASE_GATE_PATH)
    deploy = read(DEPLOY_PATH)
    testing = read(TESTING_PATH)

    validate_migration(migration)
    validate_server(server)
    validate_archive_client(archive_client)
    validate_tests_and_wiring(boundary, database_test, workflow, release_gate, deploy, testing)

    print("public_delivery_static_contract=yes")
    print("Public delivery static contracts validated; run the boundary and rollback-only database acceptances next.")


if __name__ == "__main__":
    main()
