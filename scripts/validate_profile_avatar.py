#!/usr/bin/env python3
"""Static contract checks for the real profile-avatar upload vertical slice."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def forbid(source: str, tokens: set[str], label: str) -> None:
    found = sorted(token for token in tokens if token in source)
    if found:
        raise RuntimeError(f"{label} contains forbidden contracts: {', '.join(found)}")


def block(source: str, start: str, end: str) -> str:
    try:
        start_index = source.index(start)
        end_index = source.index(end, start_index + len(start))
    except ValueError as error:
        raise RuntimeError(f"Unable to locate contract block: {start} -> {end}") from error
    return source[start_index:end_index]


def validate_migration(migration: str, creator_migration: str) -> None:
    normalized_lines = [
        line.strip().lower()
        for line in migration.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    if not normalized_lines or normalized_lines[0] != "begin;" or normalized_lines[-1] != "commit;":
        raise RuntimeError("Profile avatar migration must remain transaction wrapped")

    require(migration, {
        "add column if not exists avatar_storage_bucket text",
        "add column if not exists avatar_storage_key text",
        "add column if not exists avatar_mime_type text",
        "add column if not exists avatar_byte_size bigint",
        "add column if not exists avatar_width integer",
        "add column if not exists avatar_height integer",
        "create table if not exists public.profile_avatar_upload_intents",
        "alter table public.profile_avatar_upload_intents enable row level security;",
        "revoke all on table public.profile_avatar_upload_intents",
        "using (owner_user_id = (select public.current_app_user_id()));",
        "'profile-avatars'",
        "false,",
        "1048576",
        "array['image/jpeg']",
        "create policy profile_avatar_owner_insert",
        "for insert to authenticated",
        "(storage.foldername(name))[1] = (select auth.uid())::text",
        "create policy profile_avatar_owner_select",
        "owner_id = (select auth.uid())::text",
        "create policy profile_avatar_owner_delete",
        "create or replace function public.is_profile_avatar_upload_target",
        "intent.owner_user_id = (select auth.uid())",
        "intent.status = 'issued'",
        "intent.expires_at > now()",
        "create or replace function public.create_my_profile_avatar_upload",
        "create or replace function public.complete_my_profile_avatar_upload",
        "create or replace function public.cancel_my_profile_avatar_upload",
        "create or replace function public.remove_my_profile_avatar()",
        "app_user_id := public.require_creator_profile_user();",
        "from storage.objects object",
        "object.owner_id = app_user_id::text",
        "lower(coalesce(object.metadata ->> 'mimetype', '')) = intent_row.mime_type",
        "coalesce(object.metadata ->> 'size', '') = intent_row.byte_size::text",
        "avatar_url = null",
        "avatar_storage_bucket = intent_row.storage_bucket",
        "avatar_storage_key = intent_row.storage_key",
        "grant execute on function public.create_my_profile_avatar_upload(text, bigint, integer, integer)",
        "grant execute on function public.complete_my_profile_avatar_upload(uuid)",
        "grant execute on function public.cancel_my_profile_avatar_upload(uuid)",
        "grant execute on function public.remove_my_profile_avatar()",
    }, "profile avatar migration")

    bucket = block(
        migration,
        "insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)",
        "create or replace function public.is_profile_avatar_upload_target",
    )
    require(bucket, {"'profile-avatars'", "false", "1048576", "array['image/jpeg']"}, "private avatar bucket")

    completion = block(
        migration,
        "create or replace function public.complete_my_profile_avatar_upload",
        "create or replace function public.cancel_my_profile_avatar_upload",
    )
    require(completion, {
        "intent.owner_user_id = app_user_id",
        "intent_row.expires_at <= now()",
        "intent_row.status <> 'issued'",
        "object.bucket_id = intent_row.storage_bucket",
        "object.name = intent_row.storage_key",
        "object.owner_id = app_user_id::text",
        "status = 'completed'",
        "avatar_url = null",
    }, "owner-scoped avatar completion RPC")

    profile_update = block(
        creator_migration,
        "create or replace function public.update_my_profile(profile_patch jsonb)",
        "create or replace function public.creator_profile_cover_asset_json",
    )
    allowlist = block(profile_update, "where key not in (", "if unsupported_fields is not null then")
    if "avatar_url" in allowlist:
        raise RuntimeError("avatar_url must not become a general editable profile field")


def validate_server(server: str) -> None:
    require(server, {
        'PROFILE_EDITABLE_FIELDS = tuple(field for field in PROFILE_FIELDS if field != "avatar_url")',
        'PROFILE_AVATAR_BUCKET = "profile-avatars"',
        'PROFILE_AVATAR_MIME_TYPE = "image/jpeg"',
        "PROFILE_AVATAR_SIZE = 512",
        "PROFILE_AVATAR_MAX_BYTES = 1024 * 1024",
        "def clean_profile_avatar_asset(value, expected_owner_id: str) -> dict | None:",
        'key_parts[0] != owner_id',
        'key_parts[2] != "avatar.jpg"',
        "def signed_profile_avatar_upload_url(self, user: dict, intent: dict) -> str:",
        'f"object/upload/sign/{quote(intent[\'storage_bucket\'], safe=\'\')}/"',
        "def handle_profile_avatar_intent_create(self) -> None:",
        '"create_my_profile_avatar_upload"',
        "def handle_profile_avatar_complete(self, upload_id: str) -> None:",
        '"complete_my_profile_avatar_upload"',
        "def handle_profile_avatar_intent_cancel(self, upload_id: str) -> None:",
        '"cancel_my_profile_avatar_upload"',
        "def handle_profile_avatar_remove(self) -> None:",
        'self.profile_avatar_rpc("remove_my_profile_avatar")',
        'body != {"confirmation": "complete-profile-avatar"}',
        'body != {"confirmation": "cancel-profile-avatar"}',
        'body != {"confirmation": "remove-profile-avatar"}',
        'if parsed.path == "/api/me/profile/avatar/intents":',
        'if parsed.path == "/api/me/profile/avatar":',
        "self.handle_profile_avatar_complete(parts[5])",
        "self.handle_profile_avatar_intent_cancel(parts[5])",
        "if not self.require_csrf():",
        '"profile": {field: profile.get(field) for field in PROFILE_FIELDS}',
    }, "profile avatar server boundary")

    intent_response = block(
        server,
        "def handle_profile_avatar_intent_create(self) -> None:",
        "def handle_profile_avatar_complete(self, upload_id: str) -> None:",
    )
    require(intent_response, {
        '"signed_url": signed_url',
        '"mime_type": intent["mime_type"]',
        '"byte_size": intent["byte_size"]',
        '"width": intent["width"]',
        '"height": intent["height"]',
    }, "avatar signed-upload response")
    forbid(intent_response, {'"storage_bucket":', '"storage_key":'}, "avatar browser upload DTO")

    account_payload = block(server, "def account_payload(", "def handle_profile_get(")
    require(account_payload, {"for field in PROFILE_FIELDS"}, "account profile projection")
    forbid(account_payload, {"PROFILE_AVATAR_STORAGE_FIELDS", '"avatar_storage_key"'}, "account browser profile DTO")


def validate_account_ui(html: str, javascript: str) -> None:
    require(html, {
        'type="file"',
        'accept="image/jpeg,image/png,image/webp"',
        "data-profile-avatar-input",
        'data-profile-avatar-image hidden',
        'decoding="async"',
        'type="button" data-profile-avatar-choose',
        'type="button" data-profile-avatar-remove hidden',
        'role="status" aria-live="polite" data-profile-avatar-status',
        "Center-cropped to a square; the original file is not uploaded.",
    }, "Account Settings avatar controls")
    forbid(html, {'name="avatar_url"'}, "Account Settings avatar form")

    require(javascript, {
        "async function showProfileAvatar(",
        "await profileAvatarImage.decode()",
        'profileAvatarVisual.classList.add("is-image-ready")',
        'profileAvatarVisual.classList.remove("is-image-ready")',
        "profileAvatarImage.hidden = true",
        "async function prepareProfileAvatar(file)",
        'new Set(["image/jpeg", "image/png", "image/webp"])',
        "width * height > 40_000_000",
        "canvas.width = 512",
        "canvas.height = 512",
        "const cropSize = Math.min(width, height)",
        "const sourceX = (width - cropSize) / 2",
        "const sourceY = (height - cropSize) / 2",
        '"image/jpeg"',
        "blob.size > 1024 * 1024",
        "context.drawImage(decoded.image, sourceX, sourceY, cropSize, cropSize, 0, 0, 512, 512)",
        "URL.revokeObjectURL(profileAvatarPreviewUrl)",
        'accountRequest("/api/me/profile/avatar/intents"',
        'method: "POST"',
        "async function uploadPreparedAvatar(destination, blob)",
        'method: "PUT"',
        'credentials: "omit"',
        'headers: { "x-upsert": "false" }',
        'confirmation: "complete-profile-avatar"',
        'confirmation: "cancel-profile-avatar"',
        'accountRequest("/api/me/profile/avatar",',
        'method: "DELETE"',
        'confirmation: "remove-profile-avatar"',
        'new CustomEvent("mt:profile-committed"',
        "emitProfileCommitted(accountData.profile)",
    }, "Account Settings avatar controller")

    upload_flow = block(javascript, "async function uploadProfileAvatar(file)", "async function removeProfileAvatar()")
    if upload_flow.index("prepareProfileAvatar(file)") > upload_flow.index("/api/me/profile/avatar/intents"):
        raise RuntimeError("Avatar must be center-cropped and re-encoded before creating an upload intent")
    if upload_flow.index("uploadPreparedAvatar(destination, blob)") > upload_flow.index("/complete"):
        raise RuntimeError("Avatar bytes must reach the signed URL before the upload is completed")


def validate_shared_header(account_menu: str, styles: str) -> None:
    committed = block(
        account_menu,
        'window.addEventListener("mt:profile-committed"',
        "const bootstrap = bootstrapIdentity();",
    )
    require(committed, {
        "currentIdentity?.authenticated",
        "currentPayload?.profile",
        "identityFromPayload(payload)",
        "renderAuthenticated(",
    }, "shared Header Identity profile commit")

    avatar_styles = block(
        styles,
        ".account-settings-page .account-profile-avatar-summary",
        ".account-settings-page .account-profile-grid",
    )
    require(avatar_styles, {
        ".account-settings-page .account-profile-avatar > img",
        "object-fit: cover;",
        "transition: opacity 190ms ease;",
        ".account-settings-page .account-profile-avatar.is-image-ready > span",
        ".account-settings-page .account-profile-avatar.is-image-ready > img",
        "@media (prefers-reduced-motion: reduce)",
        "transition: none;",
        ".account-settings-page .account-profile-avatar-action:focus-visible",
    }, "Account Settings avatar styles")

    require(styles, {
        ".account-profile-link.is-image-ready > [data-account-menu-initials]",
        ".account-profile-link.is-image-ready > [data-account-menu-image]",
        "@media (prefers-reduced-motion: reduce)",
    }, "shared Header Identity avatar styles")


def validate_wiring(release_gate: str, deploy: str, boundary: str) -> None:
    require(release_gate, {
        "scripts/validate_profile_avatar.py",
        "scripts/test_user_dashboard_boundary.py",
        'run_group "Static contract: $validator" python3 "$validator"',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    }, "profile avatar release-gate wiring")
    require(deploy, {
        'python3 "$root/scripts/validate_profile_avatar.py"',
        'migration_files=("$root"/database/migrations/*.sql)',
    }, "profile avatar deployment preflight")
    require(boundary, {
        '"/api/me/profile/avatar/intents"',
        '"/api/me/profile/avatar"',
        "upload_signed_avatar(upload[\"signed_url\"])",
        "Profile avatar intent reached the provider without CSRF protection",
        "assert_private_fields_absent(intent_payload)",
        "Profile avatar removal did not return the header to its first-frame initials fallback",
    }, "profile avatar HTTP lifecycle acceptance")


def main() -> None:
    migration = read("database/migrations/20260723_c_profile_avatar_upload.sql")
    creator_migration = read("database/migrations/20260722_z_creator_profile.sql")
    server = read("server.py")
    html = read("account-settings.html")
    javascript = read("account-settings.js")
    account_menu = read("account-menu.js")
    styles = read("styles.css")
    release_gate = read("scripts/release_gate.sh")
    deploy = read("scripts/deploy_supabase_phase1.sh")
    boundary = read("scripts/test_user_dashboard_boundary.py")

    validate_migration(migration, creator_migration)
    validate_server(server)
    validate_account_ui(html, javascript)
    validate_shared_header(account_menu, styles)
    validate_wiring(release_gate, deploy, boundary)

    print("profile_avatar_private_storage=yes")
    print("profile_avatar_owner_scoped_lifecycle=yes")
    print("profile_avatar_real_upload_ui=yes")
    print("profile_avatar_header_sync=yes")
    print("profile_avatar_accessibility_and_motion=yes")


if __name__ == "__main__":
    main()
