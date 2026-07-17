#!/usr/bin/env python3
"""Static security-contract checks for the Supabase Phase 1 migration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "database" / "supabase_phase1_auth_rls.sql").read_text()
PROFILE_PATCH_SQL = (ROOT / "database" / "migrations" / "20260714_account_profile_boundary.sql").read_text()


def require(tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token.lower() not in SQL.lower())
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def require_profile_patch(tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token.lower() not in PROFILE_PATCH_SQL.lower())
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    require({
        "after insert or update of email, email_confirmed_at on auth.users",
        "security definer", "set search_path = ''", "default role assigned at registration",
        "create or replace function public.current_app_user_id()",
        "create or replace function public.has_any_role",
        "create or replace function public.has_aal2()",
        "create or replace function public.current_authorization()",
        "and u.account_status = 'active'::public.account_status",
    }, "identity and authorization helpers")

    tables = {
        "users", "user_profiles", "user_roles", "folders", "images",
        "image_versions", "image_assets", "review_submissions",
        "review_decisions", "notifications", "takedown_cases", "audit_logs",
    }
    for table in tables:
        require({f"alter table public.{table} enable row level security"}, f"RLS for {table}")

    require({
        "owner_user_id = (select public.current_app_user_id())",
        "submitted_by_user_id = (select public.current_app_user_id())",
        "reviewer_id = (select public.current_app_user_id())",
        "(select public.has_aal2())",
        "publication_status = 'published' and deleted_at is null",
        "alter view public.public_works set (security_invoker = true)",
        "(storage.foldername(name))[1] = (select auth.uid())::text",
    }, "ownership, public, MFA and storage policies")

    profile_contract = {
        "revoke update on public.user_profiles from authenticated",
        "create or replace function public.update_my_profile(profile_patch jsonb)",
        "profile_patch must be a non-empty object",
        "active account required",
        "aal2 required for administrator profile updates",
        "unsupported profile fields",
        "grant execute on function public.update_my_profile(jsonb) to authenticated",
        "revoke all on function public.update_my_profile(jsonb) from anon, public",
    }
    require(profile_contract, "profile update RPC baseline")
    require_profile_patch(profile_contract | {"begin;", "commit;"}, "profile update incremental migration")

    forbidden_role_writes = [
        "policy roles_insert", "policy roles_update", "policy roles_delete",
        "policy admin_roles_insert", "policy admin_roles_update", "policy admin_roles_delete",
    ]
    found = [token for token in forbidden_role_writes if token in SQL.lower()]
    if found:
        raise RuntimeError(f"Direct authenticated role writes are forbidden: {', '.join(found)}")

    print("Supabase Phase 1 identity/RLS contracts validated.")


if __name__ == "__main__":
    main()
