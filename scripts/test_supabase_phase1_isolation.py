#!/usr/bin/env python3
"""Non-mutating Supabase Phase 1 user A/B RLS integration test."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def request(path: str, *, token: str = "", payload: dict | None = None, method: str = "GET"):
    headers = {"apikey": KEY, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        body = json.loads(raw.decode("utf-8")) if raw else {}
        raise RuntimeError(f"{method} {path} failed with {error.code}: {body}") from error


def sign_in(email: str, password: str) -> tuple[str, str]:
    _, session = request(
        "/auth/v1/token?grant_type=password",
        payload={"email": email, "password": password},
        method="POST",
    )
    user = session.get("user") or {}
    token = session.get("access_token")
    if not token or not user.get("id"):
        raise RuntimeError(f"Supabase did not return a complete verified session for {email}")
    return user["id"], token


def visible_ids(token: str, table: str, column: str) -> set[str]:
    query = urllib.parse.urlencode({"select": column})
    _, rows = request(f"/rest/v1/{table}?{query}", token=token)
    return {row[column] for row in rows}


def authorization(token: str) -> dict:
    _, result = request("/rest/v1/rpc/current_authorization", token=token, payload={}, method="POST")
    return result


def main() -> None:
    global URL, KEY
    URL = required("SUPABASE_URL").rstrip("/")
    KEY = required("SUPABASE_PUBLISHABLE_KEY")
    a_id, a_token = sign_in(required("MT_TEST_USER_A_EMAIL"), required("MT_TEST_USER_A_PASSWORD"))
    b_id, b_token = sign_in(required("MT_TEST_USER_B_EMAIL"), required("MT_TEST_USER_B_PASSWORD"))
    if a_id == b_id:
        raise RuntimeError("User A and User B must be different accounts")

    for label, own_id, other_id, token in (
        ("A", a_id, b_id, a_token),
        ("B", b_id, a_id, b_token),
    ):
        user_ids = visible_ids(token, "users", "id")
        profile_ids = visible_ids(token, "user_profiles", "user_id")
        role_ids = visible_ids(token, "user_roles", "user_id")
        if own_id not in user_ids or own_id not in profile_ids or own_id not in role_ids:
            raise RuntimeError(f"User {label} cannot read its own identity/profile/role rows")
        if other_id in user_ids or other_id in profile_ids or other_id in role_ids:
            raise RuntimeError(f"RLS failure: User {label} can read the other user's private rows")
        authz = authorization(token)
        if authz.get("user_id") != own_id or "user" not in (authz.get("roles") or []):
            raise RuntimeError(f"User {label} authorization RPC is inconsistent: {authz}")

    print("Supabase Phase 1 user A/B isolation validated without mutating data.")


if __name__ == "__main__":
    main()
