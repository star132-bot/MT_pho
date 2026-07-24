#!/usr/bin/env python3
"""Static contract checks for the protected user Dashboard slice."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    migration = read("database/migrations/20260722_user_dashboard.sql")
    creator_migration = read("database/migrations/20260722_z_creator_profile.sql")
    server = read("server.py")
    html = read("dashboard.html")
    javascript = read("dashboard.js")
    account_menu = read("account-menu.js")
    styles = read("styles.css")
    home_html = read("index.html")
    workflow = read(".github/workflows/database.yml")
    release_gate = read("scripts/release_gate.sh")
    deploy = read("scripts/deploy_supabase_phase1.sh")
    database_test = read("scripts/test_user_dashboard_database.py")
    project_map = read("docs/architecture/project-map.md")
    upload_testing = read("docs/operations/upload-testing.md")

    require(migration, {
        "begin;",
        "commit;",
        "create or replace function public.dashboard_image_json",
        "create or replace function public.get_my_dashboard()",
        "public.is_recovery_auth_session()",
        "recovery session cannot access the user dashboard",
        "public.require_active_workspace_user()",
        "v.id = i.current_version_id and v.image_id = i.id",
        "v.id = s.image_version_id and v.image_id = i.id",
        "'status_counts'",
        "'needs_attention'",
        "'recent_images'",
        "'review_activity'",
        "'storage_usage'",
        "'capabilities'",
        "grant execute on function public.get_my_dashboard() to authenticated;",
    }, "Dashboard migration")
    if migration.strip().splitlines()[0].strip().lower() != "begin;" or migration.strip().splitlines()[-1].strip().lower() != "commit;":
        raise RuntimeError("Dashboard migration must remain transaction wrapped")
    recovery_guard = migration.index("if public.is_recovery_auth_session() then")
    active_guard = migration.index("app_user_id := public.require_active_workspace_user();")
    if recovery_guard > active_guard:
        raise RuntimeError("Dashboard RPC must reject recovery JWTs before resolving account data")

    require(creator_migration, {
        "begin;",
        "commit;",
        "create type public.creator_availability_status as enum ('unavailable', 'open', 'limited')",
        "add column if not exists professional_headline text",
        "add column if not exists company text",
        "add column if not exists city text",
        "add column if not exists availability_status public.creator_availability_status",
        "add column if not exists instagram_url text",
        "add column if not exists linkedin_url text",
        "add column if not exists cover_asset_id uuid",
        "create or replace function public.require_creator_profile_user()",
        "recovery session cannot access creator profile settings",
        "create or replace function public.update_my_profile(profile_patch jsonb)",
        "'professional_headline', 'company', 'city', 'availability_status'",
        "instagram_url ~*",
        "linkedin_url ~*",
        "create or replace function public.creator_profile_cover_asset_json",
        "join public.asset_scan_jobs scan_job",
        "scan_job.storage_bucket = case a.kind",
        "scan_job.storage_key = a.storage_key",
        "create or replace function public.get_my_profile_cover()",
        "join lateral (",
        "case a.kind when 'display' then 0 else 1 end as kind_order",
        "limit 24",
        "create or replace function public.set_my_profile_cover",
        "PROFILE_COVER_NOT_AVAILABLE",
        "grant execute on function public.get_my_profile_cover() to authenticated;",
        "grant execute on function public.set_my_profile_cover(uuid) to authenticated;",
    }, "Creator profile migration")
    if (
        creator_migration.strip().splitlines()[0].strip().lower() != "begin;"
        or creator_migration.strip().splitlines()[-1].strip().lower() != "commit;"
    ):
        raise RuntimeError("Creator profile migration must remain transaction wrapped")

    require(server, {
        "def clean_dashboard_result(value)",
        "def sign_dashboard_asset(self, user: dict, asset: dict)",
        "def handle_dashboard_get(self)",
        '"rpc/get_my_dashboard"',
        'if parsed.path == "/api/dashboard":',
        'if parsed.path == "/dashboard.html":',
        'self.send_header("Location", "/dashboard")',
        'self.serve_header_html("dashboard.html", user=user, authorization=authorization)',
        '"DASHBOARD_PROVIDER_FAILED"',
        '"DASHBOARD_ASSET_UNAVAILABLE"',
        "def clean_profile_result(value)",
        "def normalize_profile_cover_update(body: dict)",
        "def clean_profile_cover_result(value, *, include_candidates: bool)",
        "def sign_profile_cover_asset(",
        "def handle_profile_cover_get(self)",
        "def handle_profile_cover_update(self)",
        '"rpc/get_my_profile_cover"',
        '"rpc/set_my_profile_cover"',
        'if parsed.path == "/api/me/profile/cover":',
        '"PROFILE_COVER_ASSET_UNAVAILABLE"',
        '"PROFILE_COVER_NOT_AVAILABLE"',
        '{"cover": None, "saved": True}',
    }, "Dashboard server boundary")

    require(html, {
        'data-dashboard-loading',
        'data-dashboard-error',
        'data-dashboard-retry',
        'data-dashboard-tab="overview"',
        'data-dashboard-tab="works"',
        'data-dashboard-attention',
        'data-dashboard-recent',
        'data-dashboard-activity',
        'data-dashboard-storage',
        'data-dashboard-drafts',
        'href="/settings/account#profile"',
        'href="/workspace/images?folder=inbox"',
        'data-dashboard-cover-open',
        'data-dashboard-cover-dialog',
        'data-dashboard-cover-candidates',
        'src="/account-menu.js',
        'src="/dashboard.js',
    }, "Dashboard page")
    require(javascript, {
        'dashboardRequest("/api/me/profile"',
        'dashboardRequest("/api/dashboard"',
        'dashboardRequest("/api/me/profile/cover"',
        'dashboardMutation("/api/me/profile/cover", { asset_id: assetId })',
        "function cleanCover(value)",
        "signed_url: signedUrl",
        "expires_in:",
        'error.status === 401',
        'error.code === "ACCOUNT_RESTRICTED"',
        'dashboardRetry.addEventListener("click", loadDashboard)',
        'new AbortController()',
        'event.key === "Home"',
        'event.key === "End"',
        'capability.available === true && capability.public_path',
        'renderPublicPortfolio(payload.capabilities?.public_portfolio || {})',
        'data-dashboard-public-link',
    }, "Dashboard client")
    if '"/api/images"' in javascript or "'/api/images'" in javascript:
        raise RuntimeError("Dashboard client must consume the aggregate DTO instead of walking image rows")

    require(account_menu, {
        'new URLSearchParams({ header_identity: "1" })',
        'fetch(`/api/me?${params.toString()}`',
        'fetch("/api/auth/csrf"',
        'fetch("/api/auth/sign-out"',
        'profileLink.href = "/dashboard"',
        'container.querySelector("[data-account-profile-link]").setAttribute("aria-label", `Open personal profile for ${displayName}`)',
        'avatar.href = "/dashboard"',
        'destination("Dashboard", "/dashboard")',
        'destination("Workspace", "/workspace/images")',
        'destination("Account Settings", "/settings/account")',
        'document.querySelectorAll("[data-review-nav]").forEach',
        'link.hidden = !identity.can_review',
        'event.key === "Escape"',
        'event.key === "ArrowDown"',
        'event.key === "ArrowUp"',
        'closeMenu(true)',
    }, "Shared account menu")
    if "innerHTML" in account_menu or "insertAdjacentHTML" in account_menu:
        raise RuntimeError("Shared account menu must not build its shell through an HTML injection sink")
    forbidden_storage = ("localStorage", "sessionStorage", "indexedDB", "IndexedDB")
    for name, source in (("Dashboard", javascript), ("Account menu", account_menu)):
        found = [token for token in forbidden_storage if token in source]
        if found:
            raise RuntimeError(f"{name} cannot use browser storage: {', '.join(found)}")

    require(styles, {
        ".account-profile-link",
        ".account-menu-popover",
        ".dashboard-cover",
        ".dashboard-status-grid",
        ".dashboard-overview-grid",
        ".dashboard-draft-grid",
        "@media (max-width: 760px)",
    }, "Dashboard styles")
    require(home_html, {
        '<template id="mt-header-identity" data-header-identity>',
        'data-public-header',
        'class="header-identity-slot"',
        'data-header-identity-slot',
        'src="/account-menu.js',
    }, "Homepage shared header identity shell")
    require(workflow, {"bash scripts/release_gate.sh"}, "Dashboard CI release-gate wiring")
    require(release_gate, {
        "scripts/validate_user_dashboard.py",
        "scripts/test_user_dashboard_boundary.py",
        "dashboard.js",
        "account-menu.js",
        'run_group "Static contract: $validator" python3 "$validator"',
        'run_group "JavaScript syntax: $script" node --check "$script"',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    }, "Dashboard release-gate wiring")
    require(deploy, {"python3 \"$root/scripts/validate_user_dashboard.py\""}, "Dashboard deployment preflight")
    compile(database_test, "scripts/test_user_dashboard_database.py", "exec")
    require(database_test, {
        "MT_TEST_ENVIRONMENT", "development", "MT_ALLOW_PRODUCTION",
        "pg_advisory_xact_lock", "aclexplode", "prosecdef", "proconfig",
        "has_function_privilege('authenticated'", "has_function_privilege('anon'",
        "has_function_privilege('service_role'", "set local role authenticated",
        "workspace_list_trashed_drafts", "dashboard_database_identity_guards=yes",
        "dashboard_database_owner_isolation=yes", "workspace_trash_database_owner_filter=yes",
        "creator_profile_database_fields=yes", "creator_profile_database_cover_owner=yes",
        "creator_profile_database_identity_guards=yes", "get_my_profile_cover",
        "set_my_profile_cover", "update_my_profile", "asset_scan_jobs",
        "rollback;", "assert_fixtures_absent()",
    }, "Dashboard/Trash/creator profile development database acceptance")
    require(project_map, {"`scripts/test_user_dashboard_database.py`"}, "Dashboard project map")
    require(upload_testing, {
        "MT_TEST_ENVIRONMENT=development python3 scripts/test_user_dashboard_database.py",
        "dashboard_database_fixtures_absent=yes",
    }, "Dashboard/Trash database operations guide")

    print("User Dashboard static contract checks passed.")


if __name__ == "__main__":
    main()
