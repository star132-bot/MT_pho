#!/usr/bin/env python3
"""Provision one persistent development Admin without logging credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required to provision a development Admin")


def sql(command: str) -> str:
    completed = subprocess.run(
        [psql_binary(), "--set", "ON_ERROR_STOP=1", "--quiet", "--no-align", "--tuples-only"],
        input=command,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if completed.returncode:
        raise RuntimeError("Development Admin database provisioning failed")
    return completed.stdout.strip()


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def select_target() -> dict:
    configured = os.environ.get("MT_DEV_ADMIN_EMAIL", "").strip().lower()
    if configured:
        where = f"lower(au.email)=lower('{sql_literal(configured)}')"
    else:
        where = "au.email like 'mt-presence-%@example.com'"
    raw = sql(
        "select json_build_object("
        "'id', au.id, 'email', au.email, 'roles', coalesce(("
        "select json_agg(ur.role::text order by ur.role::text) from public.user_roles ur where ur.user_id=au.id"
        "), '[]'::json))::text "
        "from auth.users au join public.users u on u.id=au.id "
        f"where {where} and au.email_confirmed_at is not null "
        "and u.account_status='active'::public.account_status "
        "order by au.created_at asc limit 1;"
    )
    if not raw:
        raise RuntimeError("No active, verified disposable user is available for development Admin provisioning")
    target = json.loads(raw)
    uuid.UUID(str(target["id"]))
    if not target.get("email"):
        raise RuntimeError("Selected development Admin identity has no email")
    return target


def auth_request(path: str, payload: dict, key: str, url: str) -> dict:
    request = urllib.request.Request(
        f"{url}/auth/v1/{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"apikey": key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error.read()
        raise RuntimeError(f"Development Admin sign-in verification failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Supabase Auth is unavailable during Admin verification") from error


def rest_request(path: str, token: str, key: str, url: str, *, payload: dict | None = None) -> object:
    headers = {"apikey": key, "Authorization": f"Bearer {token}", "Accept": "application/json"}
    method = "GET"
    data = None
    if payload is not None:
        method = "POST"
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(f"{url}/rest/v1/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as error:
        error.read()
        raise RuntimeError(f"Development Admin authorization verification failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Supabase REST is unavailable during Admin verification") from error


def update_local_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            name = line.split("=", 1)[0].strip()
            if name in remaining:
                updated.append(f'{name}="{remaining.pop(name)}"')
                continue
        updated.append(line)
    if remaining:
        if updated and updated[-1]:
            updated.append("")
        updated.append("# Persistent development Admin. Local only; never commit.")
        updated.extend(f'{name}="{value}"' for name, value in remaining.items())
    content = "\n".join(updated) + "\n"
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".env-admin-", dir=ENV_PATH.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        os.chmod(temp_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_name, ENV_PATH)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> None:
    load_dotenv()
    url = required("SUPABASE_URL").rstrip("/")
    key = required("SUPABASE_PUBLISHABLE_KEY")
    for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        required(name)

    target = select_target()
    user_id = str(target["id"])
    email = str(target["email"]).lower()
    before_roles = list(target.get("roles") or [])
    password = f"Mt!{secrets.token_urlsafe(30)}7a"
    request_id = f"dev-admin-{uuid.uuid4()}"
    before_json = sql_literal(json.dumps({"roles": before_roles}, separators=(",", ":")))
    after_roles = sorted(set(before_roles) | {"admin"})
    after_json = sql_literal(json.dumps({"roles": after_roles}, separators=(",", ":")))

    sql(
        "begin; "
        "update auth.users set encrypted_password="
        f"extensions.crypt('{sql_literal(password)}', extensions.gen_salt('bf')), updated_at=now() "
        f"where id='{user_id}'::uuid; "
        f"delete from auth.sessions where user_id='{user_id}'::uuid; "
        "insert into public.user_roles(user_id, role, assigned_by, reason) "
        f"values ('{user_id}'::uuid, 'admin'::public.role_code, null, 'Persistent development Admin provisioning') "
        "on conflict (user_id, role) do nothing; "
        f"update public.user_profiles set display_name='MT Development Admin' where user_id='{user_id}'::uuid; "
        "insert into public.audit_logs(actor_user_id, actor_role, action, target_type, target_id, request_id, reason_code, before_state, after_state, policy_version, result) "
        f"values (null, null, 'development_admin.provisioned', 'user', '{user_id}', '{request_id}', "
        f"'development_bootstrap', '{before_json}'::jsonb, '{after_json}'::jsonb, '2026-07-phase1', 'success'); "
        "commit;"
    )
    update_local_env({"MT_DEV_ADMIN_EMAIL": email, "MT_DEV_ADMIN_PASSWORD": password})

    session = auth_request("token?grant_type=password", {"email": email, "password": password}, key, url)
    token = str(session.get("access_token") or "")
    if not token:
        raise RuntimeError("Supabase did not issue an AAL1 development Admin session")
    authorization = rest_request("rpc/current_authorization", token, key, url, payload={})
    if authorization.get("account_status") != "active" or "admin" not in authorization.get("roles", []):
        raise RuntimeError("Development Admin authorization is inconsistent after provisioning")
    if authorization.get("aal") != "aal1":
        raise RuntimeError("Development Admin password login did not begin at AAL1")
    query = urllib.parse.urlencode({"select": "id"})
    visible = rest_request(f"users?{query}", token, key, url)
    if {row["id"] for row in visible} != {user_id}:
        raise RuntimeError("AAL1 development Admin unexpectedly received cross-user scope")

    print("development_admin_provisioned=yes")
    print("email_verified=yes")
    print("admin_role=yes")
    print("password_login_aal=aal1")
    print("admin_cross_user_scope_before_mfa=denied")
    print("credentials_location=.env")
    print("credentials_logged=no")


if __name__ == "__main__":
    main()
