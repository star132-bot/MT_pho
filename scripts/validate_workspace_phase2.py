#!/usr/bin/env python3
"""Static contracts for the Phase 2 Workspace upload and Draft slices."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    schema = (ROOT / "database" / "product_schema.sql").read_text()
    migration = (ROOT / "database" / "migrations" / "20260715_workspace_drafts_folders.sql").read_text()
    resilience_migration = (ROOT / "database" / "migrations" / "20260716_upload_retry_cancel.sql").read_text()
    compliance_migration = (ROOT / "database" / "migrations" / "20260716_workspace_draft_compliance.sql").read_text()
    versioning_migration = (ROOT / "database" / "migrations" / "20260716_workspace_draft_versioning.sql").read_text()
    folder_integrity_migration = (ROOT / "database" / "migrations" / "20260716_workspace_folder_integrity.sql").read_text()
    submit_migration = (ROOT / "database" / "migrations" / "20260716_workspace_submit_readiness.sql").read_text()
    trash_migration = (ROOT / "database" / "migrations" / "20260722_workspace_trash_restore.sql").read_text()
    server = (ROOT / "server.py").read_text()
    upload_html = (ROOT / "upload-studio.html").read_text()
    upload_js = (ROOT / "upload-studio.js").read_text()
    manage_js = (ROOT / "manage.js").read_text()
    works_html = (ROOT / "works.html").read_text()
    account_menu = (ROOT / "account-menu.js").read_text()
    workflow = (ROOT / ".github" / "workflows" / "database.yml").read_text()
    release_gate = (ROOT / "scripts" / "release_gate.sh").read_text()

    require(schema, {
        "CREATE TABLE upload_intents", "expected_assets jsonb", "status IN ('issued', 'completed', 'expired', 'canceled')",
        "upload_intents_owner_status_idx", "canceled_at timestamptz",
        "cleanup_status text NOT NULL DEFAULT 'not_required'",
        "copyright_year BETWEEN 1000 AND 2200", "rights_declared boolean NOT NULL DEFAULT false",
        "contains_recognizable_people boolean", "model_release_status IN ('not_applicable', 'available', 'not_available', 'pending')",
        "ai_disclosure IN ('none', 'ai_edited', 'ai_generated')",
        "sensitive_content_disclosure IN ('none', 'contains_sensitive_content')",
        "idempotency_key uuid NOT NULL", "readiness_snapshot jsonb NOT NULL", "asset_snapshot jsonb NOT NULL",
        "review_submissions_idempotency_key", "review_submissions_snapshot_immutable",
        "image_versions_locked_immutable",
    }, "Phase 2 product schema")

    require(migration, {
        "begin;", "commit;", "create table if not exists public.upload_intents",
        "revoke insert, update, delete on public.folders from authenticated",
        "revoke insert, update, delete on public.images from authenticated",
        "revoke insert, update, delete on public.image_versions from authenticated",
        "revoke insert, update, delete on public.image_assets from authenticated",
        "('image-originals', 'image-originals', false, 52428800",
        "storage_owner_delete", "owner_id = (select auth.uid()::text)",
        "create or replace function public.require_active_workspace_user()",
        "create or replace function public.workspace_list_folders()",
        "create or replace function public.workspace_create_folder(folder_name text)",
        "create or replace function public.workspace_rename_folder(folder_id uuid, folder_name text)",
        "create or replace function public.workspace_delete_folder(folder_id uuid, non_empty_policy text default 'reject')",
        "create or replace function public.workspace_create_upload_intent(intent jsonb)",
        "auth_user_id::text || '/' || image_id::text || '/' || kind",
        "create or replace function public.workspace_complete_upload(upload_id uuid, draft jsonb default '{}'::jsonb)",
        "UPLOAD_ASSETS_INCOMPLETE", "o.owner_id = (select auth.uid()::text)",
        "create or replace function public.workspace_list_drafts()",
        "create or replace function public.workspace_update_draft(image_id uuid, patch jsonb)",
        "create or replace function public.workspace_trash_draft(image_id uuid)",
        "workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)",
        "revoke all on function public.workspace_create_upload_intent(jsonb) from anon, public",
    }, "Phase 2 migration")

    require(resilience_migration, {
        "begin;", "commit;", "add column if not exists canceled_at timestamptz",
        "add column if not exists cleanup_status text not null default 'not_required'",
        "create or replace function public.workspace_cancel_upload_intent(upload_id uuid)",
        "create or replace function public.workspace_finish_upload_cleanup(upload_id uuid, cleanup_succeeded boolean)",
        "status = 'canceled'", "cleanup_status = 'pending'", "cleanup_status = next_status",
        "grant execute on function public.workspace_cancel_upload_intent(uuid) to authenticated",
        "revoke all on function public.workspace_cancel_upload_intent(uuid) from anon, public",
    }, "Phase 2B upload resilience migration")

    require(compliance_migration, {
        "begin;", "commit;", "image_versions_copyright_year_range",
        "image_versions_model_release_status", "image_versions_property_release_status",
        "image_versions_ai_disclosure", "image_versions_sensitive_disclosure",
        "create or replace function public.workspace_draft_json(target_image_id uuid)",
        "create or replace function public.workspace_update_draft(image_id uuid, patch jsonb)",
        "contains_recognizable_people", "rights_declared", "copyright_holder", "copyright_year",
        "model_release_status", "property_release_status", "ai_disclosure", "sensitive_content_disclosure",
        "grant execute on function public.workspace_update_draft(uuid, jsonb) to authenticated",
        "revoke all on function public.workspace_update_draft(uuid, jsonb) from anon, public",
    }, "Phase 2C Draft compliance migration")

    require(versioning_migration, {
        "begin;", "commit;", "'lock_version', i.version",
        "create or replace function public.workspace_update_draft_versioned(",
        "expected_version integer", "for update", "image_row.version <> expected_version",
        "DRAFT_VERSION_REQUIRED", "DRAFT_VERSION_CONFLICT",
        "return public.workspace_update_draft(image_id, patch)",
        "revoke execute on function public.workspace_update_draft(uuid, jsonb) from authenticated",
        "grant execute on function public.workspace_update_draft_versioned(uuid, jsonb, integer) to authenticated",
        "create or replace function public.workspace_trash_draft_versioned(",
        "revoke execute on function public.workspace_trash_draft(uuid) from authenticated",
        "grant execute on function public.workspace_trash_draft_versioned(uuid, integer) to authenticated",
        "version = version + 1", "create or replace function public.workspace_delete_folder",
    }, "Phase 2D Draft versioning migration")

    require(folder_integrity_migration, {
        "workspace_folder_assignment_guard", "pg_advisory_xact_lock", "hashtextextended",
        "images_workspace_folder_assignment_guard", "upload_intents_workspace_folder_assignment_guard",
        "workspace_delete_folder", "workspace_update_draft_versioned", "workspace_restore_draft",
        "restore_folder_id", "FOLDER_NOT_FOUND",
        "version = version + 1",
    }, "Phase 2D folder assignment integrity migration")

    require(submit_migration, {
        "begin;", "commit;", "add column if not exists idempotency_key uuid",
        "add column if not exists readiness_snapshot jsonb", "add column if not exists asset_snapshot jsonb",
        "drop policy if exists submissions_owner_insert on public.review_submissions",
        "revoke insert, update, delete on public.review_submissions from authenticated",
        "image_versions_locked_immutable", "review_submissions_snapshot_immutable",
        "drop policy if exists storage_owner_delete on storage.objects",
        "not exists (", "from public.image_assets a",
        "create or replace function public.workspace_submit_readiness_json(",
        "create or replace function public.workspace_get_submit_readiness(image_id uuid)",
        "create or replace function public.workspace_submit_draft_versioned(",
        "expected_version integer", "idempotency_key uuid", "for update", "for share",
        "DRAFT_NOT_READY", "DRAFT_VERSION_CONFLICT", "SUBMISSION_IDEMPOTENCY_CONFLICT",
        "work_details", "rights_disclosures", "image_assets", "security_scan", "submission_state",
        "scan_status = 'clean'", "scan_status = 'pending'", "scan_status in ('flagged', 'failed')",
        "to_jsonb(a) ->> 'scan_policy_version'", "mt-asset-scan-2026-07-v1",
        "readiness_snapshot", "asset_snapshot", "workspace.submit_for_review",
        "grant execute on function public.workspace_get_submit_readiness(uuid) to authenticated",
        "grant execute on function public.workspace_submit_draft_versioned(uuid, integer, uuid) to authenticated",
        "revoke all on function public.workspace_submit_draft_versioned(uuid, integer, uuid) from anon, public",
    }, "Phase 2E Submit readiness migration")

    require(trash_migration, {
        "begin;", "commit;", "create or replace function public.workspace_list_trashed_drafts()",
        "stable", "security definer", "set search_path = ''",
        "public.is_recovery_auth_session()", "recovery session cannot access Workspace Trash",
        "public.require_active_workspace_user()", "i.owner_user_id = app_user_id",
        "public.workspace_draft_json(i.id)",
        "jsonb_build_object('deleted_at', i.deleted_at)", "i.deleted_at is not null",
        "i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)",
        "from public, anon, authenticated, service_role",
        "grant execute on function public.workspace_list_trashed_drafts() to authenticated",
    }, "Phase 2G Trash/Restore migration")

    require(server, {
        "def supabase_storage_request(", "normalize_workspace_upload_intent", "normalize_workspace_draft_patch",
        'parsed.path == "/api/folders"', 'parsed.path == "/api/images"',
        'parsed.path == "/api/uploads/intents"', "handle_workspace_upload_complete",
        "handle_workspace_draft_update", "handle_workspace_draft_trash",
        "create_signed_upload_urls", "sign_workspace_draft", "require_account_session()",
        "UPLOAD_ASSETS_INCOMPLETE", "DRAFT_LOCKED", "UPLOAD_INTENT_NOT_CANCELABLE",
        "remove_workspace_upload_objects", "handle_workspace_upload_cancel",
        'f"bucket/{quote(bucket, safe=\'\')}/delete"', '"confirmation": "cancel-upload"',
        "WORKSPACE_RELEASE_STATUSES", "WORKSPACE_AI_DISCLOSURES", "WORKSPACE_SENSITIVE_DISCLOSURES",
        '"contains_recognizable_people"', '"rights_declared"', '"copyright_year"',
        "allow_compliance=False",
        "DRAFT_VERSION_REQUIRED", "DRAFT_VERSION_CONFLICT",
        'set(body) != {"draft", "expected_version"}',
        '"workspace_update_draft_versioned"', 'key != "assets"',
        '"workspace_trash_draft_versioned"',
        'parse_qs(parsed.query, keep_blank_values=True)',
        'set(query) - {"workflow_status"}', 'len(workflow_values) != 1',
        '"trashed": "workspace_list_trashed_drafts"', "handle_workspace_draft_restore",
        'auth_error("DRAFT_RESTORE_INVALID"',
        "clean_workspace_submit_readiness", "clean_workspace_submission_result",
        "handle_workspace_submit_readiness", "handle_workspace_draft_submit",
        '"workspace_get_submit_readiness"', '"workspace_submit_draft_versioned"',
        '"confirmation"', '"submit-for-review"', '"idempotency_key"',
        "DRAFT_NOT_READY", "SUBMISSION_IDEMPOTENCY_CONFLICT",
    }, "Phase 2 server boundary")

    require(upload_html, {
        'accept="image/jpeg,image/png,image/webp"', ">Content Category<", ">Caption<",
        "Save Draft", "Move to Trash", "data-folder-form", "data-folder-list",
        'id="icon-retry"', 'id="icon-x"',
        'data-editor-state="empty"', "Loading folders", "upload-studio-loading",
        'name="alt_text"', 'name="copyright_holder"', 'name="copyright_year"',
        'name="contains_recognizable_people"', 'data-model-release-field',
        'name="property_release_status"', 'name="rights_declared"',
        'name="ai_disclosure"', 'name="sensitive_content_disclosure"',
        "data-studio-reload-record", "20260729-quick-upload",
        "data-studio-readiness", "data-studio-readiness-refresh", "data-studio-readiness-list",
        "Submission readiness", "Submission state", "data-studio-submit-record",
        "Submit for Review", "data-studio-submit-dialog",
        'data-studio-view="drafts"', 'data-studio-view="trash"', "data-studio-trash-count",
        "data-quick-upload-open", "data-quick-upload-dialog", "data-quick-upload-form",
        "data-quick-upload-input", "data-studio-submit-ready", "Quick Upload does not bypass",
    }, "Phase 2 Upload Studio page")
    require(upload_js, {
        'const WORKSPACE_FOLDERS_API = "/api/folders"',
        'const WORKSPACE_IMAGES_API = "/api/images"',
        'const WORKSPACE_UPLOAD_INTENTS_API = "/api/uploads/intents"',
        'method: "PUT"', 'credentials: "omit"', 'signed_url',
        "createWorkspaceUploadIntent", "completeWorkspaceUpload", "saveWorkspaceDraft",
        "trashWorkspaceDraft", "Offline read-only", "loadOfflineCache",
        "restoreWorkspaceDraft", "loadTrashRecords", "restoreTrashedRecord", "data-trash-restore",
        "window.history.replaceState", "data-folder-rename", "data-folder-delete",
        "allowEmptyTitle: true", 'record.title || "Untitled Work"',
        "const UPLOAD_CONCURRENCY = 2", "new AbortController()", "processTasksWithLimit",
        "cancelWorkspaceUpload", "cancelUploadTask", "retryUploadTask", "dismissUploadTask",
        "data-task-retry", "data-task-cancel", "data-task-dismiss", "cleanupStatus",
        "workspaceLoading", "studioGrid.dataset.editorState", "primaryImport",
        "includeCompliance", "syncComplianceFieldVisibility", "nullableBoolean",
        "contains_recognizable_people", "rights_declared", "sensitive_content_disclosure",
        "DRAFT_AUTOSAVE_DELAY", "scheduleAutosave", "markDraftDirty",
        "draftEditRevision", "pendingAutosave", "DRAFT_VERSION_CONFLICT",
        "reloadActiveRecord", "flushDraftBeforeNavigation", "expected_version",
        "location_name: cleanText(record.location_name),",
        "draftSaveInFlight || draftConflict",
        "activeRecordId !== recordId", "renderEditor();", 'window.addEventListener("pagehide"',
        "READINESS_CHECK_DEFAULTS", 'code: "submission_state"', "refreshActiveReadiness",
        "scheduleReadinessPoll", "readinessRequestId", "submissionInFlight",
        "submissionIdempotencyKeys", "createSubmissionIdempotencyKey", "confirmDraftSubmission",
        "performActiveRecordSubmission", "submitWorkspaceDraft", 'confirmation: "submit-for-review"',
        "error?.details", 'window.addEventListener("beforeunload"',
        "applyQuickUploadDefaults", "quickUploadDefaultsFromForm", "rememberedQuickUploadDefaults",
        "record = await saveWorkspaceDraft(applyQuickUploadDefaults(record, task.quickDefaults))",
        "submitReadyRecordsInFolder", "getWorkspaceDraftReadiness", "mapWithConcurrency",
        "Only ready Drafts in", "submitWorkspaceDraft(record, idempotencyKey)",
    }, "Phase 2 Upload Studio client")
    require(works_html, {
        "data-public-header",
        "data-global-header",
        'src="/global-header.js',
        'src="/account-menu.js',
    }, "Works public shell")
    require(account_menu, {
        'destination("Workspace", "/workspace/images")',
    }, "authenticated Works Upload navigation")
    title_input = re.search(r'<input\b[^>]*\bname="title"[^>]*>', upload_html)
    if not title_input or re.search(r"\brequired\b", title_input.group(0)):
        raise RuntimeError("Phase 2 Draft title must remain optional")
    forbidden = ["localStorage", '"/api/archive/images"', "syncArchiveApiRecord"]
    found = [token for token in forbidden if token in upload_js]
    if found:
        raise RuntimeError(f"Upload Studio still uses a legacy authoritative store: {', '.join(found)}")
    if 'href="/manage.html?filter=draft"' in upload_html:
        raise RuntimeError("User Upload Workspace still links into the Admin Review surface")
    if "Submission capacity" in upload_html or "submission_capacity" in upload_js:
        raise RuntimeError("Submit UI claims a user quota/capacity policy that is not implemented")
    if re.search(r"scan_status\s*[:=]\s*['\"]clean['\"]", upload_js):
        raise RuntimeError("Browser code must not mark security scans clean")

    require(manage_js, {
        "function homepageEditableSnapshot(settings)",
        "stableStringify(homepageEditableSnapshot(settings))",
        'window.addEventListener("beforeunload"',
    }, "Review dirty-state boundary")
    signature_block = re.search(
        r"function homepageEditableSnapshot\(settings\)\s*\{(?P<body>.*?)\n\}",
        manage_js,
        re.DOTALL,
    )
    if not signature_block or "database_shape" in signature_block.group("body"):
        raise RuntimeError("Review dirty signature still includes derived database_shape")
    unload_block = re.search(
        r'window\.addEventListener\("beforeunload", \(event\) => \{(?P<body>.*?)\n\}\);',
        manage_js,
        re.DOTALL,
    )
    if not unload_block or any(token in unload_block.group("body") for token in ("syncActiveFormToRecord", "syncHomepageForm")):
        raise RuntimeError("Review beforeunload must not mutate dirty state")

    require(workflow, {
        "bash scripts/release_gate.sh",
    }, "Phase 2 CI entrypoint")
    require(release_gate, {
        "scripts/validate_workspace_phase2.py",
        "scripts/test_workspace_phase2_boundary.py",
        'for validator in "${static_validators[@]}"; do',
        'run_group "Static contract: $validator" python3 "$validator"',
        'for test_file in "${boundary_tests[@]}"; do',
        'run_group "Boundary test: $test_file" python3 "$test_file"',
    }, "Phase 2 release gate contract")
    print("Phase 2A/2B/2C/2D/2E/2G Workspace contracts validated.")


if __name__ == "__main__":
    main()
