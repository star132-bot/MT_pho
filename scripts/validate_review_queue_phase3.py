#!/usr/bin/env python3
"""Static contracts for the Phase 3 Review Queue.

This validator is deliberately mutation-resistant: SQL function bodies, RLS
policy predicates, grants, Python handlers, and browser contracts are checked
in their owning scope instead of by searching the migration as one blob.

It is still a static contract check, not a PostgreSQL parser. A real
development database must parse/apply the migration and exercise RLS,
Storage, concurrency, and audit behaviour before release.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "database" / "migrations" / "20260717_review_queue.sql"
SERVER_PATH = ROOT / "server.py"
PAGE_PATH = ROOT / "admin-reviews.html"
CLIENT_PATH = ROOT / "admin-reviews.js"
STYLES_PATH = ROOT / "styles.css"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "database.yml"
PROJECT_MAP_PATH = ROOT / "docs" / "architecture" / "project-map.md"
REVIEW_TESTING_PATH = ROOT / "docs" / "operations" / "review-testing.md"
DATABASE_TEST_PATH = ROOT / "scripts" / "test_review_queue_database.sql"
CONCURRENCY_TEST_PATH = ROOT / "scripts" / "test_review_queue_concurrency.py"
PRODUCT_SPEC_PATH = ROOT / "docs" / "product" / "user-upload-admin-spec.md"
DESIGN_SYSTEM_PATH = ROOT / "docs" / "design" / "design-system.md"
README_PATH = ROOT / "README.md"

CURRENT_SCAN_POLICY = "mt-asset-scan-2026-07-v1"
STORAGE_HELPER = "can_read_review_storage_object"
RECOVERY_HELPER = "is_recovery_auth_session"
PUBLIC_RPCS = {
    "review_list_submissions": "text,text,integer,integer",
    "review_get_submission": "uuid",
    "review_assign_submission": "uuid,integer",
    "review_start_submission": "uuid,integer",
    "review_decide_submission": "uuid,integer,text,jsonb,text,text,jsonb,uuid",
}
ACTIVE_STATUSES = {
    "'submitted'::public.submission_status",
    "'in_review'::public.submission_status",
    "'escalated'::public.submission_status",
}
CHECKLIST_CODES = {
    "file_integrity",
    "rights",
    "privacy",
    "minors",
    "sensitive_content",
    "hate_illegal",
    "property_release",
    "third_party_ip",
    "ai_disclosure",
    "public_metadata",
}
REASON_CODES = {
    "request_changes": (
        "missing_rights",
        "missing_metadata",
        "privacy_review",
        "release_required",
    ),
    "reject": (
        "content_policy",
        "rights_unverified",
        "privacy_risk",
        "misleading_metadata",
    ),
    "approve": ("policy_complete",),
}


def read(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required Phase 3 file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def compact(source: str) -> str:
    return re.sub(r"\s+", " ", source.strip().lower())


def dense(source: str) -> str:
    return re.sub(r"\s+", "", source.lower())


def require(source: str, tokens: set[str] | tuple[str, ...] | list[str], label: str) -> None:
    missing = sorted(token for token in tokens if token.lower() not in source.lower())
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def forbid(source: str, tokens: set[str] | tuple[str, ...] | list[str], label: str) -> None:
    found = sorted(token for token in tokens if token.lower() in source.lower())
    if found:
        raise RuntimeError(f"{label} contains forbidden contract(s): {', '.join(found)}")


def require_regex(source: str, pattern: str, label: str, flags: int = 0) -> re.Match[str]:
    match = re.search(pattern, source, flags | re.IGNORECASE)
    if not match:
        raise RuntimeError(f"{label} does not match its required contract")
    return match


def require_order(source: str, tokens: list[str], label: str) -> None:
    lowered = source.lower()
    cursor = -1
    for token in tokens:
        cursor = lowered.find(token.lower(), cursor + 1)
        if cursor < 0:
            raise RuntimeError(f"{label} is missing or out of order at: {token}")


def require_any(source: str, alternatives: tuple[str, ...], label: str) -> None:
    lowered = source.lower()
    if not any(alternative.lower() in lowered for alternative in alternatives):
        raise RuntimeError(f"{label} is missing every accepted form: {', '.join(alternatives)}")


def _skip_single_quoted(source: str, index: int, quote: str) -> int:
    index += 1
    while index < len(source):
        if source[index] == quote:
            if index + 1 < len(source) and source[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise RuntimeError("Unterminated quoted SQL value")


def scan_balanced(source: str, opening_index: int) -> int:
    """Return the matching closing parenthesis while respecting SQL quoting."""
    if opening_index >= len(source) or source[opening_index] != "(":
        raise RuntimeError("Internal validator error: balanced scan did not start at '('")
    depth = 0
    index = opening_index
    while index < len(source):
        if source.startswith("--", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise RuntimeError("Unterminated SQL block comment")
            index = end + 2
            continue
        character = source[index]
        if character in {"'", '"'}:
            index = _skip_single_quoted(source, index, character)
            continue
        if character == "$":
            tag_match = re.match(r"\$(?:[a-zA-Z_][a-zA-Z0-9_]*)?\$", source[index:])
            if tag_match:
                tag = tag_match.group(0)
                end = source.find(tag, index + len(tag))
                if end < 0:
                    raise RuntimeError(f"Unterminated SQL dollar quote {tag}")
                index = end + len(tag)
                continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
        index += 1
    raise RuntimeError("Unbalanced SQL parentheses")


def scan_css_block(source: str, opening_index: int) -> int:
    """Return a CSS block's closing brace while ignoring strings/comments."""
    if opening_index >= len(source) or source[opening_index] != "{":
        raise RuntimeError("Internal validator error: CSS block scan did not start at '{'")
    depth = 0
    index = opening_index
    while index < len(source):
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise RuntimeError("Unterminated CSS comment")
            index = end + 2
            continue
        character = source[index]
        if character in {"'", '"'}:
            quote = character
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            else:
                raise RuntimeError("Unterminated CSS string")
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
        index += 1
    raise RuntimeError("Unbalanced CSS braces")


def css_media_blocks(source: str, max_width: int) -> list[str]:
    pattern = re.compile(rf"@media\s*\(\s*max-width\s*:\s*{max_width}px\s*\)\s*\{{", re.I)
    blocks: list[str] = []
    for match in pattern.finditer(source):
        opening = source.find("{", match.start())
        closing = scan_css_block(source, opening)
        blocks.append(source[opening + 1 : closing])
    return blocks


def css_rule_body(source: str, selector: str) -> str:
    matches = list(re.finditer(rf"{re.escape(selector)}\s*\{{", source, re.I))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one CSS rule for {selector}; found {len(matches)}")
    opening = source.find("{", matches[0].start())
    closing = scan_css_block(source, opening)
    return source[opening + 1 : closing]


@dataclass(frozen=True)
class SqlFunction:
    name: str
    signature: str
    header: str
    body: str
    definition: str


@dataclass(frozen=True)
class SqlPolicy:
    name: str
    table: str
    command: str
    roles: tuple[str, ...]
    using: str
    definition: str


def extract_sql_functions(source: str) -> dict[str, SqlFunction]:
    functions: dict[str, SqlFunction] = {}
    pattern = re.compile(r"\bcreate\s+or\s+replace\s+function\s+public\.([a-z_][a-z0-9_]*)\s*\(", re.I)
    for match in pattern.finditer(source):
        name = match.group(1).lower()
        if name in functions:
            raise RuntimeError(f"Duplicate Phase 3 SQL function definition: public.{name}")
        opening = source.find("(", match.start())
        closing = scan_balanced(source, opening)
        dollar_match = re.search(
            r"\bas\s+(\$(?:[a-zA-Z_][a-zA-Z0-9_]*)?\$)",
            source[closing + 1 :],
            re.I,
        )
        if not dollar_match:
            raise RuntimeError(f"SQL function public.{name} has no dollar-quoted body")
        tag = dollar_match.group(1)
        tag_start = closing + 1 + dollar_match.start(1)
        body_start = tag_start + len(tag)
        body_end = source.find(tag, body_start)
        if body_end < 0:
            raise RuntimeError(f"SQL function public.{name} has an unterminated body")
        semicolon_match = re.match(r"\s*;", source[body_end + len(tag) :])
        if not semicolon_match:
            raise RuntimeError(f"SQL function public.{name} is missing its terminating semicolon")
        definition_end = body_end + len(tag) + semicolon_match.end()
        signature = source[opening + 1 : closing]
        parameter_names = [
            re.match(r"\s*([a-z_][a-z0-9_]*)", parameter, re.I).group(1).lower()
            for parameter in signature.split(",")
            if parameter.strip() and re.match(r"\s*([a-z_][a-z0-9_]*)", parameter, re.I)
        ]
        if len(parameter_names) != len(set(parameter_names)):
            raise RuntimeError(f"SQL function public.{name} repeats a parameter name")
        functions[name] = SqlFunction(
            name=name,
            signature=signature,
            header=source[match.start() : body_start],
            body=source[body_start:body_end],
            definition=source[match.start() : definition_end],
        )
    return functions


def extract_sql_policies(source: str) -> dict[str, SqlPolicy]:
    policies: dict[str, SqlPolicy] = {}
    pattern = re.compile(
        r"\bcreate\s+policy\s+([a-z_][a-z0-9_]*)\s+on\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)",
        re.I,
    )
    for match in pattern.finditer(source):
        name = match.group(1).lower()
        if name in policies:
            raise RuntimeError(f"Duplicate Phase 3 SQL policy definition: {name}")
        next_statement = source.find(";", match.end())
        if next_statement < 0:
            raise RuntimeError(f"SQL policy {name} has no terminating semicolon")
        using_match = re.search(r"\busing\s*\(", source[match.end() : next_statement], re.I)
        if not using_match:
            raise RuntimeError(f"SELECT policy {name} has no USING predicate")
        opening = match.end() + using_match.end() - 1
        closing = scan_balanced(source, opening)
        tail = source[closing + 1 :]
        semicolon_match = re.match(r"\s*;", tail)
        if not semicolon_match:
            raise RuntimeError(f"SQL policy {name} contains trailing or malformed clauses")
        definition_end = closing + 1 + semicolon_match.end()
        definition = source[match.start() : definition_end]
        metadata = require_regex(
            definition,
            r"\bfor\s+([a-z]+)\s+to\s+([a-z_,\s]+?)\s+using\s*\(",
            f"SQL policy metadata for {name}",
            re.DOTALL,
        )
        roles = tuple(sorted(role.strip().lower() for role in metadata.group(2).split(",")))
        policies[name] = SqlPolicy(
            name=name,
            table=match.group(2).lower(),
            command=metadata.group(1).lower(),
            roles=roles,
            using=source[opening + 1 : closing],
            definition=definition,
        )
    return policies


def sql_function(functions: dict[str, SqlFunction], name: str) -> SqlFunction:
    try:
        return functions[name]
    except KeyError as error:
        raise RuntimeError(f"Phase 3 SQL function is missing: public.{name}") from error


def sql_policy(policies: dict[str, SqlPolicy], name: str, table: str) -> SqlPolicy:
    try:
        policy = policies[name]
    except KeyError as error:
        raise RuntimeError(f"Phase 3 RLS policy is missing: {name}") from error
    if policy.table != table or policy.command != "select" or policy.roles != ("authenticated",):
        raise RuntimeError(
            f"RLS policy {name} must be SELECT TO authenticated on {table}; "
            f"got {policy.command} TO {policy.roles} on {policy.table}"
        )
    return policy


def python_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one Python function/method {name}; found {len(matches)}")
    node = matches[0]
    return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])


def assert_security_definer(function: SqlFunction, label: str, *, stable: bool = False) -> None:
    header = compact(function.header)
    require(header, {"security definer", "set search_path = ''"}, label)
    if stable and " stable " not in f" {header} ":
        raise RuntimeError(f"{label} must be STABLE")


def assert_role_stacking_boundary(source: str, label: str) -> None:
    value = dense(source)
    reviewer = "(selectpublic.has_any_role(array['reviewer']::public.role_code[]))"
    admin = "(selectpublic.has_any_role(array['admin','super_admin']::public.role_code[]))"
    aal2 = "(selectpublic.has_aal2())"
    if f"{reviewer}andnot{admin}" not in value:
        raise RuntimeError(f"{label} must keep the pure-Reviewer branch separate from privileged role stacking")
    if f"{admin}and{aal2}" not in value:
        raise RuntimeError(f"{label} must join the Admin/Super Admin branch to AAL2 with AND")


def assert_recovery_policy_boundary(policy: SqlPolicy, label: str) -> None:
    expected_prefix = f"not(selectpublic.{RECOVERY_HELPER}())and"
    if not dense(policy.using).startswith(expected_prefix):
        raise RuntimeError(f"{label} must reject recovery sessions before every role/row branch")


def assert_self_exclusion(source: str, label: str, *, policy: bool = False) -> None:
    value = dense(source)
    operands = ["actor_id"]
    if policy:
        operands.insert(0, "(selectpublic.current_app_user_id())")
    accepted = {
        f"submitted_by_user_id<>{operand}" for operand in operands
    } | {
        f"submitted_by_user_idisdistinctfrom{operand}" for operand in operands
    } | {
        f"s.submitted_by_user_id<>{operand}" for operand in operands
    } | {
        f"s.submitted_by_user_idisdistinctfrom{operand}" for operand in operands
    }
    if not any(contract in value for contract in accepted):
        raise RuntimeError(f"{label} must exclude the submission owner from review access")


def validate_acl(migration: str) -> None:
    if re.search(r"\bgrant\s+execute\s+on\s+all\s+functions\s+in\s+schema\s+public\b", migration, re.I):
        raise RuntimeError("Phase 3 must not use a schema-wide function EXECUTE grant")
    if re.search(r"\balter\s+default\s+privileges\b[^;]*\bgrant\s+execute\b", migration, re.I | re.DOTALL):
        raise RuntimeError("Phase 3 must not change default function EXECUTE privileges")
    grant_pattern = re.compile(
        r"\bgrant\s+([^;]+?)\s+on\s+function\s+public\.([a-z_][a-z0-9_]*)\s*"
        r"\(([^)]*)\)\s+to\s+([^;]+);",
        re.I | re.DOTALL,
    )
    grants: dict[str, list[tuple[str, str, set[str]]]] = defaultdict(list)
    for match in grant_pattern.finditer(migration):
        privilege = compact(match.group(1))
        name = match.group(2).lower()
        signature = re.sub(r"\s+", "", match.group(3).lower())
        roles = {role.strip().lower() for role in match.group(4).split(",")}
        grants[name].append((privilege, signature, roles))

    granted_review_functions = {name for name in grants if name.startswith("review_")}
    if granted_review_functions != set(PUBLIC_RPCS):
        raise RuntimeError(
            "Only the five public Review RPCs may receive grants; got "
            f"{sorted(granted_review_functions)}"
        )
    for name, signature in PUBLIC_RPCS.items():
        records = grants[name]
        if records != [("execute", signature, {"authenticated"})]:
            raise RuntimeError(
                f"public.{name} must have exactly GRANT EXECUTE ({signature}) TO authenticated; got {records}"
            )

    helper_signatures = {STORAGE_HELPER: "text,text,text", RECOVERY_HELPER: ""}
    for helper_name, helper_signature in helper_signatures.items():
        helper_records = grants.get(helper_name, [])
        if helper_records != [("execute", helper_signature, {"authenticated"})]:
            raise RuntimeError(
                f"public.{helper_name}({helper_signature}) must be granted only to authenticated; got {helper_records}"
            )

    protected_names = set(PUBLIC_RPCS) | set(helper_signatures)
    for match in re.finditer(
        r"\bgrant\s+[^;]+?\s+on\s+function\s+public\.([a-z_][a-z0-9_]*)\s*\([^;]*?\)\s+to\s+([^;]+);",
        migration,
        re.I | re.DOTALL,
    ):
        name = match.group(1).lower()
        roles = {role.strip().lower() for role in match.group(2).split(",")}
        if name in protected_names and roles.intersection({"public", "anon", "service_role"}):
            raise RuntimeError(f"public.{name} exposes EXECUTE to a forbidden role: {sorted(roles)}")

    normalized = compact(migration)
    normalized_dense = dense(migration)
    for name, signature in {**PUBLIC_RPCS, **helper_signatures}.items():
        expected_revoke = dense(
            f"revoke all on function public.{name}({signature}) "
            "from public, anon, authenticated, service_role;"
        )
        if expected_revoke not in normalized_dense:
            raise RuntimeError(f"ACL reset for public.{name} is missing its four-role REVOKE ALL")
    require(
        normalized,
        {
            "drop policy if exists reviewer_decisions_insert on public.review_decisions;",
            "revoke insert, update, delete, truncate on public.review_decisions from public, anon, authenticated, service_role;",
            "revoke insert, update, delete, truncate on public.review_submissions from public, anon, authenticated, service_role;",
            "revoke insert, update, delete, truncate on public.audit_logs from public, anon, authenticated, service_role;",
            "where d.expected_lock_version is null or d.result_snapshot is null",
            "existing review decisions require a controlled result snapshot backfill",
            "alter column expected_lock_version set not null",
            "alter column result_snapshot set not null",
        },
        "Review table mutation ACLs and replay evidence",
    )


def validate_queue_and_detail(functions: dict[str, SqlFunction]) -> None:
    recovery = sql_function(functions, RECOVERY_HELPER)
    recovery_header = compact(recovery.header)
    require(
        recovery_header,
        {"returns boolean", "language sql", "stable", "set search_path = ''"},
        "Recovery-session JWT predicate",
    )
    forbid(recovery_header, {"security definer"}, "Recovery-session JWT predicate")
    require(
        recovery.body,
        {
            "select auth.jwt()",
            "jsonb_typeof",
            "jsonb_array_elements",
            "entry ->> 'method' = 'recovery'",
            "bool_or",
            "coalesce",
            "false",
        },
        "Recovery-session JWT AMR predicate",
    )

    actor = sql_function(functions, "review_require_actor")
    assert_security_definer(actor, "Review actor boundary", stable=True)
    require(
        actor.body,
        {
            "has_reviewer boolean",
            "has_privileged_role boolean",
            "if public.is_recovery_auth_session() then",
            "recovery session cannot access review administration",
            "if has_privileged_role and not (select public.has_aal2())",
            "account_status = 'active'::public.account_status",
        },
        "Review actor active-account/AAL2 boundary",
    )
    require_order(
        actor.body,
        ["if public.is_recovery_auth_session() then", "select public.current_app_user_id() into app_user_id"],
        "Review RPC recovery-session rejection order",
    )

    queue = sql_function(functions, "review_list_submissions")
    assert_security_definer(queue, "Review queue RPC", stable=True)
    require(
        queue.body,
        {
            "actor_id := public.review_require_actor()",
            "'open', 'completed', 'all'",
            "status_filter = 'completed'",
            "'withdrawn'::public.submission_status",
            "jsonb_agg(entry order by sort_rank, sort_submitted_at, sort_id)",
            "s.id as sort_id",
            "'scan_status', thumbnail.scan_status",
            "'scan_policy_version', thumbnail.scan_policy_version",
            "page_size := least(greatest(coalesce(page_size, 30), 1), 50)",
        },
        "Review queue DTO/filter/pagination contract",
    )
    require_regex(
        queue.body,
        r"order\s+by\s+case\s+s\.status\b.*?\bend\s*,\s*s\.submitted_at\s*,\s*s\.id\s+"
        r"limit\s+page_size\s+offset\s+page_offset",
        "Review queue deterministic UUID tie-break ordering",
        re.DOTALL,
    )
    require_any(
        queue.body,
        ("a.scan_status = 'clean'", "thumbnail.scan_status = 'clean'"),
        "Review queue thumbnail clean-scan predicate",
    )
    require_any(
        queue.body,
        (
            f"a.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
            f"thumbnail.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
        ),
        "Review queue thumbnail current scan-policy predicate",
    )
    assert_self_exclusion(queue.body, "Review queue DTO")
    if queue.body.lower().count("s.submitted_by_user_id <> actor_id") < 3:
        raise RuntimeError("Review queue items, total, and aggregate counts must all exclude self-review for Reviewers")

    detail = sql_function(functions, "review_get_submission")
    assert_security_definer(detail, "Review detail RPC", stable=True)
    require(
        detail.body,
        {
            "actor_id := public.review_require_actor()",
            "s.assigned_reviewer_id = actor_id",
            "actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)",
            "or d.reviewer_id = actor_id then d.internal_note",
            "a.scan_status = 'clean'",
            f"a.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
            "'scan_status', a.scan_status",
            "'scan_policy_version', a.scan_policy_version",
        },
        "Review detail least-privilege/current-scan DTO",
    )
    assert_self_exclusion(detail.body, "Review detail DTO")


def validate_rls_and_storage(
    functions: dict[str, SqlFunction],
    policies: dict[str, SqlPolicy],
) -> None:
    submissions = sql_policy(policies, "reviewer_submissions_select", "public.review_submissions")
    assert_recovery_policy_boundary(submissions, "reviewer_submissions_select")
    assert_role_stacking_boundary(submissions.using, "reviewer_submissions_select")
    assert_self_exclusion(submissions.using, "reviewer_submissions_select", policy=True)
    require(
        submissions.using,
        {
            "assigned_reviewer_id = (select public.current_app_user_id())",
            *ACTIVE_STATUSES,
        },
        "Reviewer raw-submission active assignment RLS",
    )
    forbid(
        submissions.using,
        {"assigned_reviewer_id is null"},
        "Reviewer raw-submission RLS (unassigned rows belong only in the SECURITY DEFINER queue DTO)",
    )

    decisions = sql_policy(policies, "reviewer_decisions_select", "public.review_decisions")
    assert_recovery_policy_boundary(decisions, "reviewer_decisions_select")
    assert_role_stacking_boundary(decisions.using, "reviewer_decisions_select")
    require(
        decisions.using,
        {"reviewer_id = (select public.current_app_user_id())"},
        "Review decision history RLS",
    )

    assets = sql_policy(policies, "review_assets_select", "public.image_assets")
    assert_recovery_policy_boundary(assets, "review_assets_select")
    assert_role_stacking_boundary(assets.using, "review_assets_select")
    assert_self_exclusion(assets.using, "review_assets_select", policy=True)
    require(
        assets.using,
        {
            "image_assets.deleted_at is null",
            "image_assets.scan_status = 'clean'",
            f"image_assets.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
            "s.assigned_reviewer_id = (select public.current_app_user_id())",
            *ACTIVE_STATUSES,
        },
        "Review asset metadata RLS",
    )
    forbid(
        assets.using,
        {"assigned_reviewer_id is null"},
        "Review raw asset metadata RLS",
    )

    helper = sql_function(functions, STORAGE_HELPER)
    assert_security_definer(helper, "Review Storage predicate", stable=True)
    require(helper.header, {"returns boolean"}, "Review Storage predicate return type")
    if dense(helper.signature) != "target_buckettext,target_keytext,target_ownertext":
        raise RuntimeError("Review Storage predicate must bind bucket, key, and Storage owner")
    require(
        helper.body,
        {
            "public.current_app_user_id()",
            "if public.is_recovery_auth_session() then",
            "has_reviewer := public.has_any_role(array['reviewer']::public.role_code[])",
            "has_privileged_role := public.has_any_role(array['admin','super_admin']::public.role_code[])",
            "if has_privileged_role then",
            "if not public.has_aal2() then",
            "if not has_reviewer then",
            "join public.images i on i.id = a.image_id",
            "target_owner = i.owner_user_id::text",
            "a.deleted_at is null",
            "a.scan_status = 'clean'",
            f"a.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
            "a.kind = 'thumbnail'",
            "s.assigned_reviewer_id is null",
            "s.assigned_reviewer_id = actor_id",
            *ACTIVE_STATUSES,
        },
        "Review Storage predicate bucket/current-scan/lifecycle scope",
    )
    if helper.body.lower().count("join public.images i on i.id = a.image_id") < 2:
        raise RuntimeError("Review Storage Admin and Reviewer branches must both join the canonical image owner")
    if helper.body.lower().count("target_owner = i.owner_user_id::text") < 2:
        raise RuntimeError("Review Storage Admin and Reviewer branches must both bind Storage owner to image owner")
    require(
        helper.body,
        {
            "a.kind = 'original' and target_bucket = 'image-originals'",
            "a.kind = 'display' and target_bucket = 'image-display'",
            "a.kind = 'thumbnail' and target_bucket = 'image-thumbnails'",
        },
        "Review Storage bucket-kind binding",
    )
    require_order(
        helper.body,
        [
            "if public.is_recovery_auth_session() then",
            "actor_id := public.current_app_user_id()",
            "has_privileged_role := public.has_any_role",
            "if has_privileged_role then",
            "if not public.has_aal2() then",
            "return exists",
            "if not has_reviewer then",
            "return exists",
        ],
        "Review Storage role-stacking/AAL2 control flow",
    )
    assert_self_exclusion(helper.body, "Review Storage predicate")
    forbid(
        helper.body,
        {"review_require_actor()", "service_role"},
        "Non-throwing Review Storage predicate",
    )

    storage = sql_policy(policies, "review_storage_objects_select", "storage.objects")
    storage_predicate = dense(storage.using)
    if not re.fullmatch(
        rf"(?:\(select)?public\.{re.escape(STORAGE_HELPER)}\("
        rf"(?:storage\.objects\.)?bucket_id,(?:storage\.objects\.)?name,"
        rf"(?:storage\.objects\.)?owner_id\)(?:\))?",
        storage_predicate,
    ):
        raise RuntimeError(
            "storage.objects Review policy must delegate exclusively to the dedicated SECURITY DEFINER predicate"
        )


def validate_assignment_start_and_constraint(
    migration: str,
    functions: dict[str, SqlFunction],
) -> None:
    normalized = dense(migration)
    require(
        normalized,
        {
            "review_submissions_active_assignment",
            "ifexists(select1frompublic.review_submissionss",
            "s.statusin('in_review'::public.submission_status,'escalated'::public.submission_status)",
            "ands.assigned_reviewer_idisnull",
            "raiseexception'activereviewsubmissionsrequireanassignedreviewer'usingerrcode='23514';",
            "frompg_constraint",
            "conrelid='public.review_submissions'::regclass",
            "statusnotin('in_review'::public.submission_status,'escalated'::public.submission_status)",
            "orassigned_reviewer_idisnotnull",
            ")notvalid;",
            "validateconstraintreview_submissions_active_assignment",
        },
        "Active review assignment check constraint",
    )
    require_order(
        normalized,
        [
            "ifexists(select1frompublic.review_submissionss",
            "ifnotexists(select1frompg_constraint",
            "addconstraintreview_submissions_active_assignment",
            "notvalid;",
            "validateconstraintreview_submissions_active_assignment",
        ],
        "Active-assignment bad-row preflight/add/validate order",
    )

    assignment = sql_function(functions, "review_assign_submission")
    assert_security_definer(assignment, "Review assignment RPC")
    require(
        assignment.body,
        {
            "submission_row.submitted_by_user_id = actor_id",
            "'REVIEW_SELF_REVIEW_FORBIDDEN'",
            "where s.id = submission_id for update",
            "submission_row.lock_version <> expected_lock_version",
            "submission_row.assigned_reviewer_id is not null",
            "'review.assign_to_self'",
        },
        "Atomic assignment/self-review boundary",
    )
    require_regex(
        assignment.body,
        r"if\s+submission_row\.assigned_reviewer_id\s*=\s*actor_id\s+and\s+"
        r"submission_row\.status\s*=\s*'submitted'::public\.submission_status\s+then\s+"
        r"return\s+jsonb_build_object",
        "Assignment idempotent shortcut submitted-only state guard",
        re.DOTALL,
    )
    require_order(
        assignment.body,
        [
            "where s.id = submission_id for update",
            "if submission_row.id is null",
            "if submission_row.submitted_by_user_id = actor_id",
            "if submission_row.assigned_reviewer_id = actor_id",
            "update public.review_submissions",
        ],
        "Assignment lock/self-review/mutation order",
    )

    start = sql_function(functions, "review_start_submission")
    assert_security_definer(start, "Review start RPC")
    require(
        start.body,
        {
            "submission_row.submitted_by_user_id = actor_id",
            "'REVIEW_SELF_REVIEW_FORBIDDEN'",
            "where s.id = submission_id for update",
            "where i.id = submission_row.image_id for update",
            "before_state_snapshot := jsonb_build_object",
            "after_state_snapshot := jsonb_build_object",
            "before_state_snapshot,",
            "after_state_snapshot,",
        },
        "Review start lock/self-review/audit boundary",
    )
    for field in (
        "submission_status",
        "assigned_reviewer_id",
        "review_started_at",
        "submission_lock_version",
        "workflow_status",
        "image_lock_version",
        "image_updated_at",
    ):
        if start.body.lower().count(f"'{field}'") < 2:
            raise RuntimeError(f"Review start before/after audit is missing field: {field}")
    require_order(
        start.body,
        [
            "where s.id = submission_id for update",
            "if submission_row.submitted_by_user_id = actor_id",
            "before_state_snapshot := jsonb_build_object",
            "update public.review_submissions",
            "update public.images",
            "after_state_snapshot := jsonb_build_object",
            "insert into public.audit_logs",
        ],
        "Review start immutable audit order",
    )


def _assert_reason_allowlist(decision: str) -> None:
    value = dense(decision)
    request_changes = "when'request_changes'thenarray[" + ",".join(
        f"'{code}'" for code in REASON_CODES["request_changes"]
    ) + "]"
    reject = "when'reject'thenarray[" + ",".join(f"'{code}'" for code in REASON_CODES["reject"]) + "]"
    if request_changes not in value or reject not in value:
        raise RuntimeError("Decision reason allowlist must be action-specific and exact for Request Changes/Reject")
    approve_forms = ("when'approve'thenarray['policy_complete']", "elsearray['policy_complete']")
    if not any(form in value for form in approve_forms):
        raise RuntimeError("Decision reason allowlist must restrict approval to policy_complete")
    if "allowed_reason_codes" not in value:
        raise RuntimeError("Decision reason codes must be checked against an explicit allowlist")
    if "entry#>>'{}'isdistinctfrombtrim(entry#>>'{}')" not in value:
        raise RuntimeError("Decision reason codes must already be trimmed; silent normalization is not allowed")
    if not any(
        contract in value
        for contract in (
            "<>all(allowed_reason_codes)",
            "!=all(allowed_reason_codes)",
            "not(entry#>>'{}'=any(allowed_reason_codes))",
            "not(reason_code=any(allowed_reason_codes))",
        )
    ):
        raise RuntimeError("Submitted reason codes are not enforced against allowed_reason_codes")
    if "jsonb_array_length(submitted_reason_codes)" not in value or not re.search(
        r"count\(distinct", value
    ) or not any(
        element_reader in value
        for element_reader in (
            "jsonb_array_elements_text(submitted_reason_codes)",
            "jsonb_array_elements(submitted_reason_codes)",
        )
    ):
        raise RuntimeError("Decision reason codes must reject duplicates with a distinct-count check")


def validate_decision(functions: dict[str, SqlFunction]) -> None:
    result_helper = sql_function(functions, "review_decision_result")
    assert_security_definer(result_helper, "Review decision result snapshot", stable=True)
    require(
        result_helper.body,
        {"select d.result_snapshot", "from public.review_decisions d", "where d.id = decision_id"},
        "Immutable Review decision result snapshot",
    )
    forbid(
        result_helper.body,
        {"coalesce", "review_submissions", "images"},
        "Review decision replay must not read mutable state",
    )

    decision_function = sql_function(functions, "review_decide_submission")
    assert_security_definer(decision_function, "Review decision RPC")
    decision = decision_function.body
    lowered = decision.lower()
    value = dense(decision)
    require(
        decision,
        {
            "jsonb_typeof(submitted_reason_codes) is distinct from 'array'",
            "jsonb_typeof(submitted_checklist) is distinct from 'object'",
            "this decision key was already used with different review data",
            "return public.review_decision_result(existing_decision.id)",
            "get stacked diagnostics violated_constraint = constraint_name",
            "review_decisions_idempotency_key_key",
            "if violated_constraint is distinct from",
            "image_row.current_version_id is distinct from submission_row.image_version_id",
            "version_row.image_id is distinct from image_row.id",
            "version_row.locked_at is null",
            "image_row.deleted_at is not null",
            "image_row.processing_status <> 'ready'::public.processing_status",
            "submission_row.readiness_snapshot -> 'ready' is distinct from 'true'::jsonb",
            "review_assets_not_ready",
            "active_asset_count <> 3",
            "active_asset_kind_count <> 3",
            "review_already_published",
            "submission_row.submitted_by_user_id = actor_id",
            "review_self_review_forbidden",
            "submission_row.assigned_reviewer_id is distinct from actor_id",
            "before_asset_visibility",
            "after_asset_visibility",
            "'asset_storage_visibility', before_asset_visibility",
            "'asset_storage_visibility', after_asset_visibility",
            f"a.scan_policy_version = '{CURRENT_SCAN_POLICY}'",
            "decision_result_snapshot := jsonb_build_object",
            "expected_lock_version, result_snapshot, created_at",
            "target_expected_lock_version, decision_result_snapshot, decision_created_at",
        },
        "Review decision CAS/idempotency/self-review/current-scan/audit contract",
    )
    forbid(
        decision,
        {
            "submission_row.assigned_reviewer_id <> actor_id",
            "existing_decision.policy_version is distinct from decision_policy",
            "existing_decision.policy_version is not distinct from decision_policy",
        },
        "Review decision NULL-safe assignment and stable idempotent replay",
    )
    _assert_reason_allowlist(decision)

    if not re.search(
        rf"bool_and\s*\(\s*a\.scan_status\s*=\s*'clean'\s+and\s+"
        rf"a\.scan_policy_version\s*=\s*'{re.escape(CURRENT_SCAN_POLICY)}'\s*\)",
        decision,
        re.I,
    ):
        raise RuntimeError("Approval must require every active asset to be clean under the current scan policy")

    idempotency_lookup = "where d.idempotency_key = request_key::text"
    if lowered.count(idempotency_lookup) < 3:
        raise RuntimeError("Decision idempotency must be checked before lock, after lock, and after unique conflict")
    first_lookup = lowered.find(idempotency_lookup)
    validation = lowered.find("if target_expected_lock_version is null")
    row_lock = lowered.find("where s.id = target_submission_id for update")
    post_lock_lookup = lowered.find(idempotency_lookup, row_lock)
    cas = lowered.find("submission_row.lock_version <> target_expected_lock_version", row_lock)
    self_review = lowered.find("submission_row.submitted_by_user_id = actor_id", row_lock)
    if min(first_lookup, validation, row_lock, post_lock_lookup, self_review, cas) < 0:
        raise RuntimeError("Decision idempotency/lock/CAS markers are incomplete")
    if first_lookup > validation:
        raise RuntimeError("Same-key replay must be resolved before validating mutable policy/request fields")
    if not row_lock < post_lock_lookup < self_review < cas:
        raise RuntimeError("Decision must recheck idempotency, reject self-review, then CAS after the row lock")

    before_snapshot = lowered.find("before_state_snapshot := jsonb_build_object")
    before_visibility = lowered.rfind("before_asset_visibility", 0, before_snapshot)
    asset_update = lowered.find("update public.image_assets")
    after_snapshot = lowered.find("after_state_snapshot := jsonb_build_object")
    after_visibility = lowered.rfind("after_asset_visibility", max(asset_update, before_snapshot), after_snapshot)
    audit_insert = lowered.find("insert into public.audit_logs")
    if min(before_visibility, before_snapshot, asset_update, after_visibility, after_snapshot, audit_insert) < 0:
        raise RuntimeError("Decision visibility/audit capture markers are incomplete")
    if not before_visibility < before_snapshot < asset_update < after_visibility < after_snapshot < audit_insert:
        raise RuntimeError("Decision audit must capture asset visibility exactly before and after the publish mutation")
    if lowered.count("before_asset_visibility") < 3 or lowered.count("after_asset_visibility") < 3:
        raise RuntimeError("Decision asset visibility must be declared, populated, and embedded in each audit snapshot")
    for field in (
        "submission_status",
        "assigned_reviewer_id",
        "review_started_at",
        "completed_at",
        "submission_lock_version",
        "workflow_status",
        "publication_status",
        "image_version_id",
        "published_at",
        "unpublished_at",
        "image_lock_version",
        "asset_storage_visibility",
    ):
        if lowered.count(f"'{field}'") < 2:
            raise RuntimeError(f"Review decision before/after audit is missing field: {field}")

    result_snapshot = lowered.find("decision_result_snapshot := jsonb_build_object")
    decision_insert = lowered.find("insert into public.review_decisions", result_snapshot)
    request_changes_insert = lowered.find("insert into public.image_versions", decision_insert)
    submission_update = lowered.find("update public.review_submissions", decision_insert)
    if min(result_snapshot, decision_insert, request_changes_insert, submission_update) < 0:
        raise RuntimeError("Decision immutable result snapshot markers are incomplete")
    if not result_snapshot < decision_insert < request_changes_insert < submission_update:
        raise RuntimeError("Decision replay evidence must be inserted before any workflow mutation")


def validate_database_test(database_test: str) -> None:
    normalized = database_test.strip().lower()
    if not normalized.startswith("\\set on_error_stop on"):
        raise RuntimeError("Review database test must stop on the first SQL error")
    require(
        database_test,
        {
            "begin;",
            "pg_advisory_xact_lock",
            "has_function_privilege",
            "has_table_privilege",
            "set local role authenticated",
            "stacked Admin AAL1 bypassed MFA through Reviewer",
            "REVIEW_SELF_REVIEW_FORBIDDEN",
            "REVIEW_VERSION_CONFLICT",
            "REVIEW_PUBLISH_ADMIN_REQUIRED",
            "same-payload replay drifted after a later publish decision",
            "d.expected_lock_version = 2",
            "d.result_snapshot = approval_result",
            "legacy-policy",
            "review.approve_and_publish",
            "alter table public.image_assets enable trigger image_assets_enqueue_scan_job",
            "rollback;",
            "review_database_fixtures_rolled_back=yes",
        },
        "Rollback-only Review development database test",
    )
    forbid(database_test, {"commit;"}, "Review development database test")
    require_order(
        database_test,
        [
            "begin;",
            "alter table public.image_assets disable trigger image_assets_enqueue_scan_job",
            "alter table public.image_assets enable trigger image_assets_enqueue_scan_job",
            "same-payload replay drifted after a later publish decision",
            "rollback;",
            "review_database_fixtures_rolled_back=yes",
        ],
        "Review database fixture/rollback order",
    )


def validate_server(server: str) -> None:
    ast.parse(server)
    require(
        server,
        {
            '"REVIEW_SELF_REVIEW_FORBIDDEN": HTTPStatus.FORBIDDEN',
            '"REVIEW_ASSETS_NOT_READY": HTTPStatus.CONFLICT',
            '"REVIEW_ALREADY_PUBLISHED": HTTPStatus.CONFLICT',
            "def canonical_url_path(value: str)",
            "import posixpath",
            "from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse",
        },
        "Review API error/canonical path boundary",
    )

    canonical = python_function(server, "canonical_url_path")
    require(
        canonical,
        {'unquote(value.split("?", 1)[0].split("#", 1)[0])', "posixpath.normpath"},
        "Canonical URL path query/fragment normalizer",
    )
    private_path = python_function(server, "is_private_static_path")
    require(
        private_path,
        {'part.startswith(".")', '{"data", "tmp", "shots"}', '["assets", "uploads"]'},
        "Private static path classifier",
    )
    do_head = python_function(server, "do_HEAD")
    require(
        do_head,
        {
            "canonical_path = canonical_url_path(self.path)",
            'canonical_path.startswith("/api/")',
            'canonical_path.startswith("/admin/reviews")',
            'canonical_path == "/assets/uploads"',
            'canonical_path.startswith("/assets/uploads/")',
            '"/admin-reviews.html"',
            '"/admin-reviews.js"',
            "is_private_static_path(canonical_path)",
            "self.send_response(HTTPStatus.NOT_FOUND)",
            'self.send_header("Cache-Control", "no-store")',
            'self.send_header("Content-Length", "0")',
            "self.path = canonical_path",
            "super().do_HEAD()",
        },
        "HEAD Review/API/private/static non-disclosure boundary",
    )
    require_order(
        do_head,
        [
            "canonical_path = canonical_url_path(self.path)",
            "if protected_route:",
            "self.send_response(HTTPStatus.NOT_FOUND)",
            "return",
            "self.path = canonical_path",
            "super().do_HEAD()",
        ],
        "HEAD protected-route deny before public-static fallback",
    )
    do_get = python_function(server, "do_GET")
    require(
        do_get,
        {
            "canonical_path = canonical_url_path(self.path)",
            "parsed = parsed._replace(path=canonical_path, netloc=\"\")",
            'if canonical_path == "/assets/uploads" or canonical_path.startswith("/assets/uploads/")',
            "if is_private_static_path(canonical_path)",
            'if parsed.path in {"/admin/reviews", "/admin/reviews/"}',
            'if parsed.path == "/admin-reviews.html"',
            'if parsed.path == "/api/admin/review-submissions"',
        },
        "Canonical protected Review/static GET routing",
    )
    require_order(
        do_get,
        [
            "canonical_path = canonical_url_path(self.path)",
            "parsed = parsed._replace(path=canonical_path",
            'if canonical_path == "/assets/uploads" or canonical_path.startswith("/assets/uploads/")',
            "if is_private_static_path(canonical_path)",
        ],
        "Encoded private/static alias protection order",
    )
    end_headers = python_function(server, "end_headers")
    require(
        end_headers,
        {"canonical_url_path(self.path)", '"/admin-reviews.html"', '"/admin-reviews.js"', '"no-store"'},
        "Review page canonical no-store headers",
    )
    serve_review = python_function(server, "serve_review_page")
    require(
        serve_review,
        {
            'next_path: str = "/admin/reviews"',
            'self.path = "/admin-reviews.html"',
            'roles.intersection({"reviewer", "admin", "super_admin"})',
            'roles.intersection({"admin", "super_admin"}) and authorization.get("aal") != "aal2"',
        },
        "Protected Review page role/AAL2/no-store projection",
    )

    clean_asset = python_function(server, "clean_review_asset")
    require(
        clean_asset,
        {"storage_bucket", "storage_key", "scan_status", "scan_policy_version"},
        "Review provider asset projection",
    )
    sign_asset = python_function(server, "sign_review_asset")
    require(
        sign_asset,
        {
            'if key not in {"storage_bucket", "storage_key"}',
            'safe_asset["signed_url"]',
            'safe_asset["expires_in"] = 10 * 60',
        },
        "Signed Review asset public DTO",
    )
    for handler_name in ("handle_review_submissions_get", "handle_review_submission_get"):
        handler = python_function(server, handler_name)
        require(handler, {"scan_status", "scan_policy_version"}, f"{handler_name} current-scan guard")
        require_regex(
            handler,
            r"\.get\(\s*[\"']scan_status[\"']\s*\)\s*!=\s*[\"']clean[\"']",
            f"{handler_name} clean-status guard",
        )
        scan_match = require_regex(
            handler,
            r"\.get\(\s*[\"']scan_policy_version[\"']\s*\)\s*!=\s*"
            r"(?P<expected>[A-Z][A-Z0-9_]*|[\"']mt-asset-scan-2026-07-v1[\"'])",
            f"{handler_name} current scan-policy guard",
        )
        expected = scan_match.group("expected")
        if expected[0].isupper():
            require_regex(
                server,
                rf"\b{re.escape(expected)}\s*=\s*[\"']{re.escape(CURRENT_SCAN_POLICY)}[\"']",
                f"{handler_name} scan-policy constant",
            )

    decision_handler = python_function(server, "handle_review_decision")
    require(
        decision_handler,
        {
            '"request-changes": "request_changes"',
            '"reject": "reject"',
            '"approve": "approve"',
            '"approve-and-publish": "approve_and_publish"',
            'set(body) != expected_fields',
            'body.get("confirmation") != f"review-{action}"',
            'response.get("decision", {}).get("decision") != decision',
            'response.get("submission", {}).get("status") != expected_status',
            'response.get("image", {}).get("workflow_status") != expected_status',
            'response.get("image", {}).get("publication_status") != "published"',
        },
        "Review decision request/result DTO contract",
    )
    do_post = python_function(server, "do_POST")
    require(
        do_post,
        {
            '["api", "admin", "review-submissions"]',
            "if not self.require_csrf()",
            'if action == "assign"',
            'if action == "start"',
            '{"request-changes", "reject", "approve", "approve-and-publish"}',
        },
        "Review mutation routes and CSRF boundary",
    )


def validate_browser(page: str, client: str, styles: str) -> None:
    require(
        page,
        {
            'href="#admin-review-main"',
            'data-review-count="open"',
            'data-review-count="submitted"',
            'data-review-count="in_review"',
            'data-review-count="completed"',
            ">Completed<",
            'data-review-list-state role="status"',
            'data-review-conflict role="alert"',
            'data-review-detail-state role="status"',
            'data-review-decision-form hidden',
            'data-review-dialog aria-labelledby=',
            'data-review-dialog-cancel',
            'data-review-live',
        },
        "Review page accessible queue/detail/dialog states",
    )
    forbid(page, {"approve-and-publish", "approve_and_publish", "Approve and Publish"}, "Browser Review page")

    require(
        client,
        {
            "new AbortController()",
            "await csrfToken(true)",
            "if (csrfPromise === request) csrfPromise = null",
            '["request_changes", "Request changes"]',
            '["reject", "Reject"]',
            '["approve", "Approve"]',
            'const closesPrivateDetail = ["request_changes", "reject", "approve"].includes(action)',
            'setDetailState("Decision recorded", "empty"',
            'internalLabel.textContent = "Internal note"',
            "dialogCancel.focus()",
            "restoreDialogFocus()",
            'sizeToggle.setAttribute("aria-pressed"',
            'setListState("Loading submissions", "loading"',
            'setDetailState("Loading submission", "loading"',
            'setDetailState("Submission unavailable", "error"',
            'setDetailState("No submission selected", "empty"',
            'Self-review is not permitted.',
            'detail.owner.id === actorId',
            'detail.owner.id !== detail.actor.id',
        },
        "Review client loading/error/success/security/accessibility states",
    )
    if client.count("new AbortController()") < 2:
        raise RuntimeError("Queue and detail requests must each use latest-wins AbortController cancellation")
    publish_mentions = [line.strip() for line in client.splitlines() if "approve_and_publish" in line]
    if publish_mentions != ['approve_and_publish: "Approved and published",']:
        raise RuntimeError(
            "approve_and_publish may appear in browser JavaScript only as a history display label; "
            f"got {publish_mentions}"
        )
    forbid(client, {"approve-and-publish"}, "Browser Review mutation actions")
    for action, codes in REASON_CODES.items():
        for code in codes:
            if client.count(f'["{code}",') != 1:
                raise RuntimeError(f"Browser reason code {action}.{code} must be declared exactly once")
    for checklist_code in CHECKLIST_CODES:
        if client.count(f'["{checklist_code}",') != 1:
            raise RuntimeError(f"Browser checklist code {checklist_code} must be declared exactly once")

    require(
        styles,
        {
            "/* Admin Review Queue: quiet-luxury editorial moderation workspace. */",
            ".admin-review-workspace",
            ".admin-review-list-state[data-tone=\"loading\"]",
            ".admin-review-list-state[data-tone=\"empty\"]",
            ".admin-review-list-state[data-tone=\"error\"]",
            ".admin-review-detail-state[data-tone=\"error\"]",
            ".admin-review-image-stage > img",
            "object-fit: contain",
            ".admin-review-dialog::backdrop",
            "@media (max-width: 1024px)",
            "@media (max-width: 760px)",
            "--admin-review-header-height: 68px",
            "@media (max-width: 480px)",
            "overflow-x: clip",
        },
        "Review gallery-white responsive state system",
    )
    mobile_review_blocks = [block for block in css_media_blocks(styles, 480) if ".admin-review-metrics" in block]
    if len(mobile_review_blocks) != 1:
        raise RuntimeError(
            "The <=480px Review layout must have exactly one scoped metrics contract; "
            f"found {len(mobile_review_blocks)}"
        )
    mobile_metrics = css_rule_body(mobile_review_blocks[0], ".admin-review-metrics")
    require(
        compact(mobile_metrics),
        {
            "display: grid",
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
            "overflow: visible",
        },
        "<=480px four-metric visibility grid",
    )
    mobile_metric_button = css_rule_body(mobile_review_blocks[0], ".admin-review-metrics button")
    require(compact(mobile_metric_button), {"min-width: 0"}, "<=480px metric button shrink boundary")
    forbid(
        mobile_review_blocks[0],
        {".admin-review-metrics button:nth-child", ".admin-review-metrics > :nth-child"},
        "<=480px four-metric visibility grid",
    )


def validate_concurrency_test(concurrency_test: str) -> None:
    require(
        concurrency_test,
        {
            'os.environ.get("MT_TEST_ENVIRONMENT") != "development"',
            'os.environ.get("MT_ALLOW_PRODUCTION") == "yes"',
            "pg_try_advisory_lock",
            "pg_advisory_lock_shared",
            "pg_advisory_unlock_shared",
            "pg_backend_pid()",
            "public.review_start_submission",
            "public.review_decide_submission",
            "REVIEW_VERSION_CONFLICT",
            "Concurrent same-key decision replay did not return one stable result",
            "review_concurrency_start_claim_race=yes",
            "review_concurrency_decision_cas_race=yes",
            "review_concurrency_same_key_replay=yes",
            "review_concurrency_distinct_backends=yes",
            "review_concurrency_fixtures_cleaned=yes",
            "finally:",
            "run_sql(cleanup_sql())",
        },
        "Two-session Review concurrency test",
    )
    require_order(
        concurrency_test,
        [
            "alter table public.audit_logs disable trigger audit_logs_append_only",
            "delete from public.review_decisions",
            "delete from public.review_submissions",
            "alter table public.audit_logs enable trigger audit_logs_append_only",
        ],
        "Review concurrency fixture cleanup",
    )
    forbid(
        concurrency_test,
        {"SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"},
        "Review concurrency test credential boundary",
    )


def validate_ci_and_docs(
    workflow: str,
    project_map: str,
    review_testing: str,
    product_spec: str,
    design_system: str,
    readme: str,
) -> None:
    require(
        workflow,
        {
            "python3 scripts/validate_review_queue_phase3.py",
            "node --check admin-reviews.js",
            "python3 scripts/test_review_queue_boundary.py",
        },
        "Review Queue CI",
    )
    require(
        project_map,
        {
            "## 11. Supabase Admin Review Queue",
            "`admin-reviews.html` / `admin-reviews.js`",
            "`database/migrations/20260717_review_queue.sql`",
            "`scripts/validate_review_queue_phase3.py` / `scripts/test_review_queue_boundary.py`",
            "`scripts/test_review_queue_database.sql`",
            "`scripts/test_review_queue_concurrency.py`",
            "`docs/operations/review-testing.md`",
            "1024px",
            "760px",
            "390px",
            "migration 已部署 development",
        },
        "Review Queue project map",
    )
    require(
        review_testing,
        {
            "# Admin Review Queue Testing",
            "Role stacking must not let an Admin who also has `reviewer` bypass AAL2.",
            "| Recovery session | Denied | Denied | Denied |",
            "python3 scripts/validate_review_queue_phase3.py",
            "python3 scripts/test_review_queue_boundary.py",
            "psql --set ON_ERROR_STOP=1 --file scripts/test_review_queue_database.sql",
            "MT_TEST_ENVIRONMENT=development python3 scripts/test_review_queue_concurrency.py",
            "The rollback-only development test passed on 2026-07-20.",
            "The two-session development concurrency test passed on 2026-07-20.",
            "Static",
            "cannot prove",
            "PostgreSQL",
            "self-review",
        },
        "Review testing runbook and honest static-check boundary",
    )
    require(
        product_spec,
        {
            "/admin/reviews",
            "same-key/same-payload",
            "approve_and_publish",
            "浏览器不暴露",
        },
        "Product Review Queue contract",
    )
    require(
        design_system,
        {
            "### Admin Review Queue",
            "Request Changes、Reject 和 Approve",
            "1024px",
            "760px",
            "68px",
        },
        "Review Queue design-system contract",
    )
    require(
        readme,
        {
            "GET    /api/admin/review-submissions",
            "POST   /api/admin/review-submissions/{submissionId}/assign",
            "POST   /api/admin/review-submissions/{submissionId}/start",
            "POST   /api/admin/review-submissions/{submissionId}/{request-changes|reject|approve}",
            "`scripts/test_review_queue_database.sql`",
            "`scripts/test_review_queue_concurrency.py`",
            "Phase 3",
            "deployed to development",
        },
        "Review Queue README status/routes",
    )


def main() -> None:
    migration = read(MIGRATION_PATH)
    server = read(SERVER_PATH)
    page = read(PAGE_PATH)
    client = read(CLIENT_PATH)
    styles = read(STYLES_PATH)
    workflow = read(WORKFLOW_PATH)
    project_map = read(PROJECT_MAP_PATH)
    review_testing = read(REVIEW_TESTING_PATH)
    database_test = read(DATABASE_TEST_PATH)
    concurrency_test = read(CONCURRENCY_TEST_PATH)
    product_spec = read(PRODUCT_SPEC_PATH)
    design_system = read(DESIGN_SYSTEM_PATH)
    readme = read(README_PATH)

    normalized = migration.strip().lower()
    if not normalized.startswith("begin;") or not normalized.endswith("commit;"):
        raise RuntimeError("Phase 3 migration must be one explicit transaction")

    functions = extract_sql_functions(migration)
    policies = extract_sql_policies(migration)
    for name in set(PUBLIC_RPCS) | {
        "review_require_actor",
        "review_actor_role",
        "review_error",
        "review_decision_result",
        STORAGE_HELPER,
        RECOVERY_HELPER,
    }:
        sql_function(functions, name)

    validate_acl(migration)
    validate_queue_and_detail(functions)
    validate_rls_and_storage(functions, policies)
    validate_assignment_start_and_constraint(migration, functions)
    validate_decision(functions)
    validate_database_test(database_test)
    validate_concurrency_test(concurrency_test)
    validate_server(server)
    validate_browser(page, client, styles)
    validate_ci_and_docs(workflow, project_map, review_testing, product_spec, design_system, readme)

    print(
        "Phase 3 Review Queue static contracts validated. "
        "Static validation does not replace the rollback-only or two-session development database tests."
    )


if __name__ == "__main__":
    main()
