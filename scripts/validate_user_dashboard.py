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
    server = read("server.py")
    html = read("dashboard.html")
    javascript = read("dashboard.js")
    account_menu = read("account-menu.js")
    styles = read("styles.css")
    home_html = read("index.html")
    home_js = read("script.js")
    workflow = read(".github/workflows/database.yml")
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

    require(server, {
        "def clean_dashboard_result(value)",
        "def sign_dashboard_asset(self, user: dict, asset: dict)",
        "def handle_dashboard_get(self)",
        '"rpc/get_my_dashboard"',
        'if parsed.path == "/api/dashboard":',
        'if parsed.path == "/dashboard.html":',
        'self.send_header("Location", "/dashboard")',
        'self.path = "/dashboard.html"',
        '"DASHBOARD_PROVIDER_FAILED"',
        '"DASHBOARD_ASSET_UNAVAILABLE"',
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
        'href="/settings/account"',
        'href="/workspace/images?folder=inbox"',
        'src="/account-menu.js',
        'src="/dashboard.js',
    }, "Dashboard page")
    require(javascript, {
        'dashboardRequest("/api/me/profile"',
        'dashboardRequest("/api/dashboard"',
        'error.status === 401',
        'error.code === "ACCOUNT_RESTRICTED"',
        'dashboardRetry.addEventListener("click", loadDashboard)',
        'new AbortController()',
        'event.key === "Home"',
        'event.key === "End"',
        'payload.capabilities?.public_portfolio?.available',
    }, "Dashboard client")
    if '"/api/images"' in javascript or "'/api/images'" in javascript:
        raise RuntimeError("Dashboard client must consume the aggregate DTO instead of walking image rows")

    require(account_menu, {
        'fetch("/api/me"',
        'fetch("/api/auth/csrf"',
        'fetch("/api/auth/sign-out"',
        'profileLink.href = "/settings/account#profile"',
        'profileLink.setAttribute("aria-label", "Open personal information")',
        'destination("Dashboard", "/dashboard")',
        'destination("Workspace", "/workspace/images")',
        'destination("Account Settings", "/settings/account")',
        'reviewLink.hidden = true',
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
    require(home_html, {'class="home-account-entry"', 'data-home-account-entry'}, "Homepage account entry")
    require(home_js, {
        'homeAccountEntry.href = "/settings/account#profile"',
        'homeAccountEntry.classList.add("is-avatar")',
        'Open personal information for',
    }, "Homepage signed-in avatar enhancement")
    require(workflow, {
        "python3 scripts/validate_user_dashboard.py",
        "python3 scripts/test_user_dashboard_boundary.py",
        "node --check dashboard.js",
        "node --check account-menu.js",
    }, "Dashboard CI wiring")
    require(deploy, {"python3 \"$root/scripts/validate_user_dashboard.py\""}, "Dashboard deployment preflight")
    compile(database_test, "scripts/test_user_dashboard_database.py", "exec")
    require(database_test, {
        "MT_TEST_ENVIRONMENT", "development", "MT_ALLOW_PRODUCTION",
        "pg_advisory_xact_lock", "aclexplode", "prosecdef", "proconfig",
        "has_function_privilege('authenticated'", "has_function_privilege('anon'",
        "has_function_privilege('service_role'", "set local role authenticated",
        "workspace_list_trashed_drafts", "dashboard_database_identity_guards=yes",
        "dashboard_database_owner_isolation=yes", "workspace_trash_database_owner_filter=yes",
        "rollback;", "assert_fixtures_absent()",
    }, "Dashboard/Trash development database acceptance")
    require(project_map, {"`scripts/test_user_dashboard_database.py`"}, "Dashboard project map")
    require(upload_testing, {
        "MT_TEST_ENVIRONMENT=development python3 scripts/test_user_dashboard_database.py",
        "dashboard_database_fixtures_absent=yes",
    }, "Dashboard/Trash database operations guide")

    print("User Dashboard static contract checks passed.")


if __name__ == "__main__":
    main()
