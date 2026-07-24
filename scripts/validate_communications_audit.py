#!/usr/bin/env python3
"""Static database contracts for Phase 5 communications and Audit."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260723_d_communications_audit.sql"
DEPENDENCY_PATH = ROOT / "database" / "migrations" / "20260723_c_profile_avatar_upload.sql"
DATABASE_TEST_PATH = ROOT / "scripts" / "test_communications_audit_database.py"

FUNCTION_SIGNATURES = {
    "public.protect_conversation_identity()",
    "public.protect_conversation_participant()",
    "public.communications_error(text,text)",
    "public.communications_require_actor(boolean)",
    "public.notification_safe_json(uuid)",
    "public.get_my_notification_unread_count()",
    "public.list_my_notifications(integer,timestamptz,uuid)",
    "public.mark_my_notification_read(uuid)",
    "public.mark_all_my_notifications_read()",
    "public.conversation_work_items(uuid)",
    "public.conversation_message_json(uuid)",
    "public.conversation_summary_json(uuid,uuid)",
    "public.project_inquiry_result(uuid,boolean)",
    "public.create_project_inquiry(text,text,text,text,text,text,text,text,text,uuid[],uuid)",
    "public.list_my_conversations(text,integer,timestamptz,uuid)",
    "public.get_my_conversation(uuid,integer,timestamptz,uuid)",
    "public.conversation_reply_result(uuid,boolean)",
    "public.reply_to_conversation(uuid,integer,text,uuid)",
    "public.conversation_status_result(uuid,boolean)",
    "public.set_my_conversation_status(uuid,integer,text,uuid)",
    "public.mark_my_conversation_read(uuid,uuid)",
    "public.audit_safe_state(jsonb)",
    "public.admin_audit_actor_json(uuid)",
    "public.admin_audit_summary_json(uuid)",
    "public.admin_list_audit_logs(text,text,text,text,text,timestamptz,timestamptz,integer,timestamptz,uuid)",
    "public.admin_get_audit_log(uuid)",
    "public.admin_audit_export_result(uuid,boolean)",
    "public.admin_export_audit_logs(text,text,text,text,text,timestamptz,timestamptz,integer,text,uuid)",
}

EXPOSED_FUNCTION_ROLES = {
    "public.create_project_inquiry(text,text,text,text,text,text,text,text,text,uuid[],uuid)": (
        "anon,authenticated"
    ),
    "public.get_my_notification_unread_count()": "authenticated",
    "public.list_my_notifications(integer,timestamptz,uuid)": "authenticated",
    "public.mark_my_notification_read(uuid)": "authenticated",
    "public.mark_all_my_notifications_read()": "authenticated",
    "public.list_my_conversations(text,integer,timestamptz,uuid)": "authenticated",
    "public.get_my_conversation(uuid,integer,timestamptz,uuid)": "authenticated",
    "public.reply_to_conversation(uuid,integer,text,uuid)": "authenticated",
    "public.set_my_conversation_status(uuid,integer,text,uuid)": "authenticated",
    "public.mark_my_conversation_read(uuid,uuid)": "authenticated",
    "public.admin_list_audit_logs(text,text,text,text,text,timestamptz,timestamptz,integer,timestamptz,uuid)": (
        "authenticated"
    ),
    "public.admin_get_audit_log(uuid)": "authenticated",
    "public.admin_export_audit_logs(text,text,text,text,text,timestamptz,timestamptz,integer,text,uuid)": (
        "authenticated"
    ),
}


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(
            f"Required Communications/Audit file is missing: {path.relative_to(ROOT)}"
        )
    return path.read_text(encoding="utf-8")


def dense(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip().lower())


def acl_dense(source: str) -> str:
    return re.sub(r"\s*([(),;])\s*", r"\1", dense(source))


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


def require_order(source: str, tokens: list[str], label: str) -> None:
    lowered = source.lower()
    offset = -1
    for token in tokens:
        next_offset = lowered.find(token.lower(), offset + 1)
        if next_offset < 0:
            raise RuntimeError(f"{label} is missing ordered token: {token}")
        if next_offset <= offset:
            raise RuntimeError(f"{label} has an invalid order near: {token}")
        offset = next_offset


def sql_function(source: str, name: str) -> str:
    match = re.search(
        rf"create\s+or\s+replace\s+function\s+public\.{re.escape(name)}\s*\(",
        source,
        re.I,
    )
    if not match:
        raise RuntimeError(f"Required SQL function is missing: public.{name}")
    tag_match = re.search(
        r"\bas\s+(\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)",
        source[match.end() :],
        re.I,
    )
    if not tag_match:
        raise RuntimeError(f"SQL function public.{name} has no dollar-quoted body")
    tag = tag_match.group(1)
    body_start = match.end() + tag_match.end()
    body_end = source.find(tag, body_start)
    if body_end < 0:
        raise RuntimeError(f"SQL function public.{name} has an unterminated body")
    return source[match.start() : body_end + len(tag)]


def sql_function_names(source: str) -> list[str]:
    return re.findall(
        r"create\s+or\s+replace\s+function\s+public\.([a-z0-9_]+)\s*\(",
        source,
        re.I,
    )


def first_call_arguments(source: str, call_name: str) -> list[str]:
    match = re.search(rf"\b{re.escape(call_name)}\s*\(", source, re.I)
    if not match:
        raise RuntimeError(f"Required SQL call is missing: {call_name}")
    start = match.end()
    depth = 1
    quote = False
    index = start
    while index < len(source):
        character = source[index]
        if quote:
            if character == "'" and index + 1 < len(source) and source[index + 1] == "'":
                index += 2
                continue
            if character == "'":
                quote = False
        elif character == "'":
            quote = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                arguments = source[start:index]
                break
        index += 1
    else:
        raise RuntimeError(f"SQL call has an unterminated argument list: {call_name}")

    parts: list[str] = []
    part_start = 0
    depth = 0
    quote = False
    index = 0
    while index < len(arguments):
        character = arguments[index]
        if quote:
            if character == "'" and index + 1 < len(arguments) and arguments[index + 1] == "'":
                index += 2
                continue
            if character == "'":
                quote = False
        elif character == "'":
            quote = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(arguments[part_start:index].strip())
            part_start = index + 1
        index += 1
    parts.append(arguments[part_start:].strip())
    return parts


def exact_json_keys(source: str, expected: set[str], label: str) -> None:
    arguments = first_call_arguments(source, "jsonb_build_object")
    if len(arguments) % 2:
        raise RuntimeError(f"{label} has an invalid jsonb_build_object argument count")
    keys: set[str] = set()
    for argument in arguments[::2]:
        match = re.fullmatch(r"'([a-z0-9_]+)'", argument, re.I)
        if not match:
            raise RuntimeError(f"{label} has a non-literal top-level response key: {argument}")
        keys.add(match.group(1).lower())
    if keys != expected:
        missing = sorted(expected - keys)
        unexpected = sorted(keys - expected)
        raise RuntimeError(
            f"{label} keys differ; missing={missing or 'none'}, "
            f"unexpected={unexpected or 'none'}"
        )


def assert_security_definers(migration: str) -> None:
    names = sql_function_names(migration)
    if len(names) != len(set(names)):
        raise RuntimeError("Communications/Audit migration defines a function name more than once")
    secured = 0
    for name in names:
        definition = sql_function(migration, name)
        if "security definer" not in definition.lower():
            continue
        secured += 1
        require(
            definition,
            {"set search_path = ''"},
            f"Communications/Audit SECURITY DEFINER public.{name}",
        )
    if secured < 20:
        raise RuntimeError("Communications/Audit SECURITY DEFINER surface is unexpectedly small")


def validate_exact_function_acls(migration: str) -> None:
    created_names = set(sql_function_names(migration))
    signature_names = {
        signature.removeprefix("public.").split("(", 1)[0]
        for signature in FUNCTION_SIGNATURES
    }
    if created_names != signature_names:
        missing = sorted(signature_names - created_names)
        unexpected = sorted(created_names - signature_names)
        raise RuntimeError(
            "Communications/Audit function signature inventory differs; "
            f"missing={missing or 'none'}, unexpected={unexpected or 'none'}"
        )
    compact = acl_dense(migration)
    for signature in FUNCTION_SIGNATURES:
        revoke = acl_dense(
            f"revoke all on function {signature} "
            "from public, anon, authenticated, service_role;"
        )
        require(compact, {revoke}, f"Exact revoke ACL for {signature}")

    actual_grants = {
        acl_dense(match.group(0))
        for match in re.finditer(
            r"grant\s+execute\s+on\s+function\s+public\..*?;",
            migration,
            re.I | re.S,
        )
    }
    expected_grants = {
        acl_dense(f"grant execute on function {signature} to {roles};")
        for signature, roles in EXPOSED_FUNCTION_ROLES.items()
    }
    if actual_grants != expected_grants:
        missing = sorted(expected_grants - actual_grants)
        unexpected = sorted(actual_grants - expected_grants)
        raise RuntimeError(
            "Communications/Audit function grant allowlist differs; "
            f"missing={missing or 'none'}, unexpected={unexpected or 'none'}"
        )


def validate_transaction_schema_and_private_tables(migration: str) -> None:
    normalized = migration.strip().lower()
    if not normalized.startswith("begin;") or not normalized.endswith("commit;"):
        raise RuntimeError("Communications/Audit migration must remain transaction wrapped")
    if not DEPENDENCY_PATH.is_file() or DEPENDENCY_PATH.name >= MIGRATION_PATH.name:
        raise RuntimeError("Communications/Audit migration must sort after the avatar dependency")

    private_tables = (
        "conversations",
        "conversation_participants",
        "conversation_works",
        "conversation_messages",
        "conversation_status_actions",
        "audit_export_actions",
    )
    compact = dense(migration)
    for table in private_tables:
        require(
            compact,
            {
                f"create table if not exists public.{table}",
                f"alter table public.{table} enable row level security",
                f"revoke all on public.{table} from public, anon, authenticated, service_role",
            },
            f"Communications/Audit private table public.{table}",
        )
        if re.search(rf"grant\s+.+?\s+on\s+(?:table\s+)?public\.{table}\b", migration, re.I):
            raise RuntimeError(f"Private table public.{table} must remain RPC-only")
        if re.search(rf"create\s+policy\s+.+?\s+on\s+public\.{table}\b", migration, re.I | re.S):
            raise RuntimeError(f"Private table public.{table} must not expose a direct RLS policy")

    require(
        compact,
        {
            "revoke all on public.notifications from public, anon, authenticated, service_role",
            "revoke all on public.audit_logs from public, anon, authenticated, service_role",
            "drop policy if exists notifications_owner_select on public.notifications",
            "drop policy if exists notifications_owner_update on public.notifications",
            "drop policy if exists audit_owner_activity_select on public.audit_logs",
            "drop policy if exists admin_audit_select on public.audit_logs",
            "audit_event_id uuid not null unique references public.audit_logs(id) on delete restrict",
        },
        "Notifications/Audit raw-table boundary",
    )
    require_order(
        compact,
        [
            "begin;",
            "create table if not exists public.conversations",
            "create table if not exists public.conversation_participants",
            "create table if not exists public.conversation_works",
            "create table if not exists public.conversation_messages",
            "create table if not exists public.conversation_status_actions",
            "create table if not exists public.audit_export_actions",
            "alter table public.conversations enable row level security",
            "create or replace function public.create_project_inquiry",
            "revoke all on function public.create_project_inquiry",
            "grant execute on function public.create_project_inquiry",
            "commit;",
        ],
        "Communications/Audit schema/function/ACL transaction order",
    )


def validate_append_only_guards(migration: str) -> None:
    require(
        dense(migration),
        {
            "create trigger conversations_identity_guard before update or delete on public.conversations",
            "create trigger conversation_participants_identity_guard before update or delete on public.conversation_participants",
            "create trigger conversation_works_append_only before update or delete on public.conversation_works for each row execute function public.reject_mutation()",
            "create trigger conversation_messages_append_only before update or delete on public.conversation_messages for each row execute function public.reject_mutation()",
            "create trigger conversation_status_actions_append_only before update or delete on public.conversation_status_actions for each row execute function public.reject_mutation()",
            "create trigger audit_export_actions_append_only before update or delete on public.audit_export_actions for each row execute function public.reject_mutation()",
        },
        "Communications/Audit append-only triggers",
    )
    identity = sql_function(migration, "protect_conversation_identity")
    require(
        identity,
        {
            "if tg_op = 'DELETE'",
            "new.version <> old.version + 1",
            "new.public_reference is distinct from old.public_reference",
            "new.recipient_user_id is distinct from old.recipient_user_id",
            "new.initiator_user_id is distinct from old.initiator_user_id",
            "new.request_fingerprint is distinct from old.request_fingerprint",
            "new.idempotency_key is distinct from old.idempotency_key",
        },
        "Conversation identity/version guard",
    )
    participant = sql_function(migration, "protect_conversation_participant")
    require(
        participant,
        {
            "if tg_op = 'DELETE'",
            "new.conversation_id is distinct from old.conversation_id",
            "new.user_id is distinct from old.user_id",
            "new.participant_role is distinct from old.participant_role",
            "new.last_read_at is null",
            "< (old.last_read_at, old.last_read_message_id)",
        },
        "Conversation participant identity/read guard",
    )


def validate_pgcrypto_qualification(migration: str) -> None:
    if re.search(r"(?<![.a-z0-9_])digest\s*\(", migration, re.I):
        raise RuntimeError(
            "Communications/Audit migration must schema-qualify pgcrypto digest calls"
        )
    for function_name in (
        "create_project_inquiry",
        "reply_to_conversation",
        "set_my_conversation_status",
        "admin_export_audit_logs",
    ):
        require(
            sql_function(migration, function_name),
            {"extensions.digest("},
            f"Qualified pgcrypto use in public.{function_name}",
        )


def validate_notification_contract(migration: str) -> None:
    projection = sql_function(migration, "notification_safe_json")
    exact_json_keys(
        projection,
        {"id", "type", "message", "href", "read_at", "created_at"},
        "Notification safe DTO",
    )
    forbid(
        projection,
        {"'recipient_user_id',", "'payload',"},
        "Notification safe DTO output",
    )
    require(
        projection,
        {
            "'/inbox/' ||",
            "'/workspace/images?image=' ||",
            "'/settings/account'",
            "'/workspace/notifications'",
            "~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'",
        },
        "Notification allowlisted internal href",
    )
    for name in (
        "get_my_notification_unread_count",
        "list_my_notifications",
        "mark_my_notification_read",
        "mark_all_my_notifications_read",
    ):
        function = sql_function(migration, name)
        require(
            function,
            {"public.communications_require_actor(true)", "recipient_user_id = actor_id"},
            f"Notification recipient isolation public.{name}",
        )
    require(
        sql_function(migration, "mark_my_notification_read"),
        {"for update", "if target.read_at is null"},
        "Notification idempotent single-read mutation",
    )
    require(
        sql_function(migration, "mark_all_my_notifications_read"),
        {"notification.read_at is null", "get diagnostics marked_count = row_count"},
        "Notification idempotent read-all mutation",
    )


def validate_inquiry_contract(migration: str) -> None:
    result = sql_function(migration, "project_inquiry_result")
    exact_json_keys(
        result,
        {
            "reference",
            "status",
            "created_at",
            "replayed",
            "selected_work_count",
            "conversation_id",
        },
        "Project inquiry result DTO",
    )
    require(
        result,
        {
            "jsonb_strip_nulls",
            "when conversation.initiator_user_id is not null then conversation.id",
        },
        "Anonymous project inquiry minimal response",
    )
    forbid(
        result,
        {
            "recipient_user_id",
            "sender_email",
            "image_id",
            "public.conversation_work_items",
        },
        "Project inquiry public response privacy",
    )

    inquiry = sql_function(migration, "create_project_inquiry")
    require(
        inquiry,
        {
            "public.is_recovery_auth_session()",
            "actor_status <> 'active'::public.account_status",
            "normalized_email <> actor_email",
            "cardinality(coalesce(work_ids, '{}'::uuid[])) > 10",
            "cardinality(coalesce(work_ids, '{}'::uuid[])) <> cardinality(normalized_works)",
            "image.processing_status = 'ready'::public.processing_status",
            "image.workflow_status = 'approved'::public.workflow_status",
            "image.publication_status = 'published'::public.publication_status",
            "image.published_at is not null",
            "image.unpublished_at is null",
            "owner.account_status = 'active'::public.account_status",
            "eligible_work_count <> cardinality(normalized_works)",
            "work_owner_count <> 1",
            "creator.account_status = 'active'::public.account_status",
            "administrator.account_status = 'active'::public.account_status",
            "recipient_id = actor_id",
            "'INQUIRY_IDEMPOTENCY_CONFLICT'",
            "'INQUIRY_RATE_LIMITED'",
            "insert into public.conversations",
            "insert into public.conversation_participants",
            "insert into public.conversation_works",
            "insert into public.conversation_messages",
            "insert into public.notifications",
            "insert into public.audit_logs",
        },
        "Project inquiry validation/persistence boundary",
    )
    if inquiry.lower().count("[[:cntrl:]]") < 7:
        raise RuntimeError("Project inquiry must reject control characters across every text field")
    require(
        inquiry,
        {
            "mt-project-inquiry-key:",
            "mt-project-inquiry-rate:",
            "mt-project-inquiry-global-hourly",
            "mt-project-inquiry-recipient-hourly:",
            "recent_request_count >= 5",
            "global_request_count >= 500",
            "recipient_request_count >= 100",
        },
        "Project inquiry serialized rate caps",
    )
    if inquiry.lower().count("pg_advisory_xact_lock") < 4:
        raise RuntimeError("Project inquiry idempotency and rate caps must use transaction locks")
    require_order(
        inquiry,
        [
            "mt-project-inquiry-key:",
            "where message.idempotency_key = request_key",
            "mt-project-inquiry-rate:",
            "recent_request_count >= 5",
            "mt-project-inquiry-global-hourly",
            "global_request_count >= 500",
            "image.id = any(normalized_works)",
            "mt-project-inquiry-recipient-hourly:",
            "recipient_request_count >= 100",
            "insert into public.conversations",
        ],
        "Project inquiry replay/rate/eligibility/mutation order",
    )


def validate_participant_reply_and_read(migration: str) -> None:
    summary = sql_function(migration, "conversation_summary_json")
    require(
        summary,
        {
            "join public.conversation_participants viewer",
            "viewer.conversation_id = conversation.id and viewer.user_id = $2",
            "message.sender_user_id is distinct from $2",
        },
        "Conversation participant-scoped summary",
    )
    listing = sql_function(migration, "list_my_conversations")
    require(
        listing,
        {
            "public.communications_require_actor(true)",
            "join public.conversation_participants participant",
            "participant.user_id = actor_id",
        },
        "Conversation participant-scoped list",
    )
    detail = sql_function(migration, "get_my_conversation")
    require(
        detail,
        {
            "public.communications_require_actor(true)",
            "public.conversation_summary_json(target_conversation_id, actor_id)",
            "if summary is null",
        },
        "Conversation participant-scoped detail",
    )

    reply = sql_function(migration, "reply_to_conversation")
    require(
        reply,
        {
            "public.communications_require_actor(true)",
            "mt-conversation-reply-key:",
            "where message.idempotency_key = request_key",
            "existing_message.sender_user_id = actor_id",
            "existing_message.conversation_id = target_conversation_id",
            "existing_message.request_fingerprint = request_hash",
            "return public.conversation_reply_result(existing_message.id, true)",
            "for update",
            "target.user_id = actor_id",
            "conversation.version <> expected_version",
            "'CONVERSATION_VERSION_CONFLICT'",
            "conversation.status = 'closed'",
            "version = target.version + 1",
            "insert into public.conversation_messages",
            "insert into public.notifications",
            "insert into public.audit_logs",
        },
        "Conversation reply participant/CAS/idempotency transaction",
    )
    require_order(
        reply,
        [
            "mt-conversation-reply-key:",
            "where message.idempotency_key = request_key",
            "where target.id = target_conversation_id",
            "for update",
            "target.user_id = actor_id",
            "conversation.version <> expected_version",
            "update public.conversations",
            "insert into public.conversation_messages",
            "insert into public.audit_logs",
        ],
        "Conversation reply replay/lock/isolation/CAS/audit order",
    )

    read_receipt = sql_function(migration, "mark_my_conversation_read")
    require(
        read_receipt,
        {
            "public.communications_require_actor(true)",
            "target.user_id = actor_id",
            "for update",
            "message.conversation_id = target_conversation_id",
            "> (participant.last_read_at, participant.last_read_message_id)",
            "message.sender_user_id is distinct from actor_id",
        },
        "Conversation read receipt isolation/monotonicity",
    )


def validate_conversation_status(migration: str) -> None:
    result = sql_function(migration, "conversation_status_result")
    require(
        result,
        {
            "action.result_snapshot || jsonb_build_object('replayed', $2)",
            "from public.conversation_status_actions action",
            "where action.id = $1",
        },
        "Conversation status immutable replay result",
    )
    status = sql_function(migration, "set_my_conversation_status")
    require(
        status,
        {
            "public.communications_require_actor(true)",
            "normalized_status not in ('open', 'closed')",
            "mt-conversation-status-key:",
            "where action.idempotency_key = request_key",
            "existing_action.actor_user_id = actor_id",
            "existing_action.conversation_id = target_conversation_id",
            "existing_action.expected_conversation_version = expected_version",
            "existing_action.request_fingerprint = request_hash",
            "return public.conversation_status_result(existing_action.id, true)",
            "for update",
            "target.user_id = actor_id",
            "target.participant_role = 'recipient'",
            "conversation.version <> expected_version",
            "'CONVERSATION_VERSION_CONFLICT'",
            "normalized_status = conversation.status",
            "version = target.version + 1",
            "result_snapshot := jsonb_build_object",
            "insert into public.conversation_status_actions",
            "insert into public.notifications",
            "insert into public.audit_logs",
            "return public.conversation_status_result(action_id, false)",
        },
        "Conversation status recipient/CAS/idempotency transaction",
    )
    require_order(
        status,
        [
            "mt-conversation-status-key:",
            "where action.idempotency_key = request_key",
            "where target.id = target_conversation_id",
            "for update",
            "target.participant_role = 'recipient'",
            "conversation.version <> expected_version",
            "update public.conversations",
            "result_snapshot := jsonb_build_object",
            "insert into public.conversation_status_actions",
            "insert into public.notifications",
            "insert into public.audit_logs",
        ],
        "Conversation status replay/lock/recipient/CAS/evidence order",
    )


def validate_audit_read_contract(migration: str) -> None:
    safe_state = sql_function(migration, "audit_safe_state")
    require(
        safe_state,
        {
            "jsonb_typeof($1) = 'object'",
            "'status'",
            "'workflow_status'",
            "'publication_status'",
            "'account_status'",
            "'version'",
            "'reason_code'",
            "'error_code'",
            "'provider_action_required'",
        },
        "Audit safe before/after projection",
    )
    forbid(
        safe_state,
        {"email", "token", "secret", "password", "internal_note", "storage_key"},
        "Audit safe-state sensitive data",
    )
    actor = sql_function(migration, "admin_audit_actor_json")
    require(
        actor,
        {
            "public.user_roles",
            "where role_row.user_id = $1",
            "role_row.role in ('admin'::public.role_code, 'super_admin'::public.role_code)",
        },
        "Audit actor projection",
    )
    summary = sql_function(migration, "admin_audit_summary_json")
    require(
        summary,
        {
            "audit.actor_user_id",
            "audit.actor_role",
            "'display_name'",
            "public.user_profiles",
            "audit.request_id",
            "audit.reason_code",
            "audit.result",
            "audit.policy_version",
            "audit.created_at",
        },
        "Audit list/export safe summary",
    )
    listing = sql_function(migration, "admin_list_audit_logs")
    require(
        listing,
        {
            "public.admin_require_user_governance_actor()",
            "normalized_actor text",
            "normalized_request text",
            "normalized_actor_id uuid",
            "'AUDIT_FILTER_INVALID'",
            "'AUDIT_DATE_RANGE_INVALID'",
            "created_from is null or created_to is null or created_from > created_to",
            "created_to - created_from > interval '366 days'",
            "audit.created_at between created_from and created_to",
            "audit.actor_user_id = normalized_actor_id",
            "position(normalized_request in audit.request_id) = 1",
            "public.admin_audit_summary_json(candidate.id)",
        },
        "Audit result/target/action/actor/request/date filtered list",
    )
    detail = sql_function(migration, "admin_get_audit_log")
    require(
        detail,
        {
            "public.admin_require_user_governance_actor()",
            "public.admin_audit_summary_json(audit.id)",
            "public.audit_safe_state(audit.before_state)",
            "public.audit_safe_state(audit.after_state)",
            "jsonb_object_keys(safe_before || safe_after)",
            "'changed_fields'",
        },
        "Audit detail authorization/safe evidence",
    )


def validate_audit_export_contract(migration: str) -> None:
    result = sql_function(migration, "admin_audit_export_result")
    require(
        result,
        {
            "action.result_snapshot || jsonb_build_object(",
            "(action.result_snapshot -> 'export')",
            "jsonb_build_object('replayed', $2)",
            "from public.audit_export_actions action",
            "where action.id = $1",
        },
        "Audit export immutable replay result",
    )
    export = sql_function(migration, "admin_export_audit_logs")
    require(
        export,
        {
            "public.admin_require_user_governance_actor()",
            "normalized_actor text",
            "normalized_request text",
            "normalized_actor_id uuid",
            "normalized_reason text",
            "'AUDIT_FILTER_INVALID'",
            "'AUDIT_DATE_RANGE_INVALID'",
            "created_from is null or created_to is null or created_from > created_to",
            "created_to - created_from > interval '366 days'",
            "export_limit not between 1 and 1000",
            "'operational_review', 'security_investigation', 'compliance_request'",
            "'AUDIT_EXPORT_REASON_INVALID'",
            "'AUDIT_EXPORT_IDEMPOTENCY_REQUIRED'",
            "mt-audit-export-key:",
            "where action.idempotency_key = request_key",
            "existing_action.actor_user_id = actor_id",
            "existing_action.request_fingerprint = request_hash",
            "return public.admin_audit_export_result(existing_action.id, true)",
            "'AUDIT_EXPORT_IDEMPOTENCY_CONFLICT'",
            "audit.created_at between created_from and created_to",
            "audit.actor_user_id = normalized_actor_id",
            "position(normalized_request in audit.request_id) = 1",
            "limit export_limit + 1",
            "public.admin_audit_summary_json(candidate.id)",
            "result_snapshot := jsonb_build_object",
            "'truncated', candidate_count > export_limit",
            "insert into public.audit_logs",
            "'audit.exported'",
            "'mt-audit-export-2026-07-v1'",
            "insert into public.audit_export_actions",
            "audit_id, exported_at",
            "return public.admin_audit_export_result(export_id, false)",
        },
        "Audit filtered/reason-bound/idempotent export",
    )
    forbid(
        export,
        {
            "audit.before_state",
            "audit.after_state",
            "select * from public.audit_logs",
        },
        "Audit export raw-state boundary",
    )
    require_order(
        export,
        [
            "public.admin_require_user_governance_actor()",
            "AUDIT_FILTER_INVALID",
            "AUDIT_DATE_RANGE_INVALID",
            "AUDIT_EXPORT_LIMIT_INVALID",
            "AUDIT_EXPORT_REASON_INVALID",
            "mt-audit-export-key:",
            "where action.idempotency_key = request_key",
            "with candidates as",
            "public.admin_audit_summary_json(candidate.id)",
            "result_snapshot := jsonb_build_object",
            "insert into public.audit_logs",
            "insert into public.audit_export_actions",
            "return public.admin_audit_export_result(export_id, false)",
        ],
        "Audit export validation/replay/projection/evidence order",
    )


def validate_database_test(database_test: str) -> None:
    compile(database_test, str(DATABASE_TEST_PATH.relative_to(ROOT)), "exec")
    require(
        database_test,
        {
            "EXPECTED = (",
            "\\set ON_ERROR_STOP on",
            "begin;",
            "pg_advisory_xact_lock",
            "has_function_privilege",
            "has_table_privilege",
            "fixture collision",
            "rollback;",
            "absence = subprocess.run",
            "fixtures were not rolled back",
            "fixtures_rolled_back=yes",
        },
        "Communications/Audit rollback-only database acceptance",
    )
    forbid(database_test, {"commit;"}, "Communications/Audit rollback-only database acceptance")
    require_order(
        database_test,
        [
            "SQL = r\"\"\"",
            "begin;",
            "rollback;",
            "\"\"\"",
            "absence = subprocess.run",
            "fixtures_rolled_back=yes",
        ],
        "Communications/Audit database fixture/rollback order",
    )
    marker_literals = set(
        re.findall(r'"(communications_database_[a-z0-9_]+=yes)"', database_test)
    )
    expected_markers = {
        "communications_database_security=yes",
        "communications_database_inquiry=yes",
        "communications_database_isolation=yes",
        "communications_database_inbox=yes",
        "communications_database_status=yes",
        "communications_database_notifications=yes",
        "communications_database_audit_export=yes",
        "communications_database_append_only=yes",
        "communications_database_fixtures_rolled_back=yes",
    }
    if marker_literals != expected_markers:
        missing = sorted(expected_markers - marker_literals)
        unexpected = sorted(marker_literals - expected_markers)
        raise RuntimeError(
            "Communications/Audit database marker set differs; "
            f"missing={missing or 'none'}, unexpected={unexpected or 'none'}"
        )
    transaction_markers = expected_markers - {
        "communications_database_fixtures_rolled_back=yes"
    }
    expected_block = re.search(
        r"\bEXPECTED\s*=\s*\((.*?)\)\s*\n",
        database_test,
        re.S,
    )
    if not expected_block:
        raise RuntimeError("Communications/Audit database EXPECTED marker tuple is missing")
    declared_markers = set(
        re.findall(r'"(communications_database_[a-z0-9_]+=yes)"', expected_block.group(1))
    )
    if declared_markers != transaction_markers:
        raise RuntimeError("Communications/Audit database EXPECTED marker tuple differs")
    for marker in transaction_markers:
        if database_test.count(marker) < 2:
            raise RuntimeError(f"Database marker is not both declared and emitted: {marker}")


def main() -> None:
    migration = read(MIGRATION_PATH)
    database_test = read(DATABASE_TEST_PATH)

    validate_transaction_schema_and_private_tables(migration)
    assert_security_definers(migration)
    validate_exact_function_acls(migration)
    validate_append_only_guards(migration)
    validate_pgcrypto_qualification(migration)
    validate_notification_contract(migration)
    validate_inquiry_contract(migration)
    validate_participant_reply_and_read(migration)
    validate_conversation_status(migration)
    validate_audit_read_contract(migration)
    validate_audit_export_contract(migration)
    validate_database_test(database_test)

    print("Communications/Audit static contracts passed (52 checks).")


if __name__ == "__main__":
    main()
