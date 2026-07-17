#!/usr/bin/env python3
"""Reversible Supabase Admin TOTP/AAL2 integration test.

The script reuses one of the explicitly disposable Phase 1 users so it does not
depend on email delivery or signup rate limits. Identity state is restored in a
finally block. It never
prints credentials, password hashes, TOTP secrets, tokens, or response bodies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def auth_request(path: str, key: str, url: str, *, token: str = "", payload: dict | None = None, method: str = "POST") -> dict:
    headers = {"apikey": key, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(f"{url}/auth/v1/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            provider_code = json.loads(raw.decode("utf-8")).get("error_code", "")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            provider_code = ""
        suffix = f" ({provider_code})" if provider_code else ""
        raise RuntimeError(f"Supabase Auth {path} failed with HTTP {error.code}{suffix}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Supabase Auth {path} is unavailable") from error


def rest_request(path: str, key: str, url: str, token: str, *, payload: dict | None = None) -> object:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
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
        raise RuntimeError(f"Supabase REST {path} failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Supabase REST {path} is unavailable") from error


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required for the Admin role fixture")


def sql(command: str) -> str:
    completed = subprocess.run(
        [
            psql_binary(), "--set", "ON_ERROR_STOP=1", "--quiet",
            "--no-align", "--tuples-only", "--command", command,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if completed.returncode:
        raise RuntimeError("Supabase fixture database operation failed")
    return completed.stdout.strip()


def sql_literal(value: str) -> str:
    return value.replace("'", "''")


def jwt_aal(token: str) -> str:
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        return str(json.loads(base64.urlsafe_b64decode(encoded))["aal"])
    except (IndexError, KeyError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("Supabase returned an invalid access token") from error


def totp(secret: str, at: int | None = None) -> str:
    counter = int((at or int(time.time())) / 30)
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def visible_user_ids(key: str, url: str, token: str) -> set[str]:
    query = urllib.parse.urlencode({"select": "id"})
    rows = rest_request(f"users?{query}", key, url, token)
    return {row["id"] for row in rows}


def main() -> None:
    load_dotenv()
    url = required("SUPABASE_URL").rstrip("/")
    key = required("SUPABASE_PUBLISHABLE_KEY")
    for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        required(name)

    user_id = ""
    original_password_hash = ""
    try:
        password = f"Mt!{secrets.token_urlsafe(24)}9a"
        fixture = sql(
            "select au.id::text || E'\\t' || au.email || E'\\t' || au.encrypted_password "
            "from auth.users au join public.users u on u.id=au.id "
            "where au.email like 'mt-presence-%@example.com' and u.account_status='active'::public.account_status "
            "order by au.created_at desc limit 1;"
        )
        parts = fixture.split("\t", 2)
        if len(parts) != 3:
            raise RuntimeError("No reusable disposable verified user is available for the MFA test")
        user_id, email, original_password_hash = parts
        uuid.UUID(user_id)
        sql(
            "update auth.users set encrypted_password="
            f"extensions.crypt('{sql_literal(password)}', extensions.gen_salt('bf')), updated_at=now() "
            f"where id='{user_id}'::uuid;"
        )
        session = auth_request(
            "token?grant_type=password", key, url, payload={"email": email, "password": password}
        )
        access_token = str(session.get("access_token") or "")
        if not access_token:
            raise RuntimeError("Reusable disposable user could not establish an AAL1 session")

        sql(
            "insert into public.user_roles(user_id, role, assigned_by, reason) "
            f"values ('{user_id}'::uuid, 'admin'::public.role_code, null, 'Disposable Admin MFA integration test') "
            "on conflict (user_id, role) do nothing;"
        )
        authorization = rest_request("rpc/current_authorization", key, url, access_token, payload={})
        if jwt_aal(access_token) != "aal1" or "admin" not in authorization.get("roles", []):
            raise RuntimeError("AAL1 Admin fixture was not established")
        if visible_user_ids(key, url, access_token) != {user_id}:
            raise RuntimeError("AAL1 Admin unexpectedly received cross-user read access")

        factor = auth_request(
            "factors",
            key,
            url,
            token=access_token,
            payload={"factor_type": "totp", "friendly_name": "Disposable Admin MFA test"},
        )
        factor_id = str(factor.get("id") or "")
        secret = str((factor.get("totp") or {}).get("secret") or "")
        uuid.UUID(factor_id)
        if not secret:
            raise RuntimeError("Supabase did not return a TOTP enrollment secret")
        challenge = auth_request(f"factors/{factor_id}/challenge", key, url, token=access_token, payload={})
        challenge_id = str(challenge.get("id") or "")
        uuid.UUID(challenge_id)
        verified = auth_request(
            f"factors/{factor_id}/verify",
            key,
            url,
            token=access_token,
            payload={"challenge_id": challenge_id, "code": totp(secret)},
        )
        aal2_token = str(verified.get("access_token") or "")
        if not aal2_token or jwt_aal(aal2_token) != "aal2":
            raise RuntimeError("MFA verification did not issue an AAL2 session")
        admin_visible = visible_user_ids(key, url, aal2_token)
        if user_id not in admin_visible or len(admin_visible) < 2:
            raise RuntimeError("AAL2 Admin did not receive the expected protected read scope")

        sql(f"delete from public.user_roles where user_id='{user_id}'::uuid and role='admin'::public.role_code;")
        authorization = rest_request("rpc/current_authorization", key, url, aal2_token, payload={})
        if "admin" in authorization.get("roles", []) or visible_user_ids(key, url, aal2_token) != {user_id}:
            raise RuntimeError("AAL2 without an Admin role unexpectedly retained Admin access")

        print("admin_aal1_cross_user_access=denied")
        print("totp_enrollment=verified")
        print("admin_aal2_cross_user_access=allowed")
        print("non_admin_aal2_cross_user_access=denied")
        print("disposable_credentials_logged=no")
    finally:
        if user_id:
            sql(
                "begin; "
                f"delete from public.user_roles where user_id='{user_id}'::uuid and role='admin'::public.role_code; "
                f"delete from auth.mfa_factors where user_id='{user_id}'::uuid; "
                f"delete from auth.sessions where user_id='{user_id}'::uuid; "
                f"update auth.users set encrypted_password='{sql_literal(original_password_hash)}', updated_at=now() where id='{user_id}'::uuid; "
                "commit;"
            )


if __name__ == "__main__":
    main()
