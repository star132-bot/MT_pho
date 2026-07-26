#!/usr/bin/env python3
"""Development-only real-browser acceptance for profile avatar upload.

The test creates one short-lived ordinary user, exercises the real Account
Settings crop/upload/complete flow through server.py and Supabase Storage,
verifies Header Identity synchronization plus refresh persistence, removes the
avatar through the product UI, and deletes every fixture.  Output is limited to
stable markers; credentials, tokens, signed URLs, object keys, and image bytes
are never printed.
"""

from __future__ import annotations

import json
from pathlib import Path
import secrets
import tempfile
import urllib.parse
import uuid

import test_review_queue_browser as support


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_EMAIL = "mt-profile-avatar-browser@example.com"
SESSION_NAME = "mt-profile-avatar-browser"
SCREENSHOT_PATH = ROOT / "output" / "validation" / "profile-avatar-live.png"
MARKERS = (
    "profile_avatar_browser_environment_guard",
    "profile_avatar_browser_upload_saved",
    "profile_avatar_browser_header_updated",
    "profile_avatar_browser_refresh_persisted",
    "profile_avatar_browser_remove_synced",
    "profile_avatar_browser_storage_clean",
    "profile_avatar_browser_session_closed",
    "profile_avatar_browser_fixture_cleaned",
    "profile_avatar_browser_acceptance",
    "credentials_logged",
)


def fixture_user_ids(values: dict[str, str]) -> set[str]:
    email = support.sql_literal(FIXTURE_EMAIL.lower())
    raw = support.run_sql(
        "select id::text from auth.users "
        f"where lower(email)=lower('{email}') "
        "union select id::text from public.users "
        f"where lower(email)=lower('{email}');",
        values,
    )
    result: set[str] = set()
    for line in raw.splitlines():
        if line.strip():
            result.add(str(uuid.UUID(line.strip())))
    return result


def avatar_storage_keys(values: dict[str, str], user_ids: set[str]) -> list[str]:
    if not user_ids:
        return []
    identifiers = ", ".join(f"'{support.sql_literal(user_id)}'::uuid" for user_id in sorted(user_ids))
    raw = support.run_sql(
        "select name from storage.objects "
        "where bucket_id='profile-avatars' "
        f"and split_part(name, '/', 1)::uuid in ({identifiers}) order by name;",
        values,
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def remove_avatar_objects(base_url: str, secret: str, keys: list[str]) -> None:
    if not keys:
        return
    support.request(
        f"{base_url}/storage/v1/object/profile-avatars",
        method="DELETE",
        headers=support.service_headers(secret),
        payload={"prefixes": keys},
        expected={200, 204, 404},
    )


def delete_fixture_rows(values: dict[str, str]) -> None:
    email = support.sql_literal(FIXTURE_EMAIL.lower())
    support.run_sql(
        "begin; "
        "delete from public.profile_avatar_upload_intents where owner_user_id in "
        f"(select id from public.users where lower(email)=lower('{email}')); "
        "delete from public.folders where owner_user_id in "
        f"(select id from public.users where lower(email)=lower('{email}')); "
        "delete from public.user_roles where user_id in "
        f"(select id from public.users where lower(email)=lower('{email}')); "
        "delete from public.user_profiles where user_id in "
        f"(select id from public.users where lower(email)=lower('{email}')); "
        f"delete from public.users where lower(email)=lower('{email}'); "
        "commit;",
        values,
    )


def cleanup_fixture(values: dict[str, str], base_url: str, secret: str) -> bool:
    user_ids = fixture_user_ids(values)
    try:
        remove_avatar_objects(base_url, secret, avatar_storage_keys(values, user_ids))
        if avatar_storage_keys(values, user_ids):
            return False
    except Exception:
        return False
    for user_id in sorted(user_ids):
        try:
            support.auth_admin_delete(base_url, secret, user_id)
        except Exception:
            return False
    try:
        delete_fixture_rows(values)
    except Exception:
        return False
    counts = support.run_sql(
        "select json_build_object("
        f"'auth', (select count(*) from auth.users where lower(email)=lower('{support.sql_literal(FIXTURE_EMAIL)}')), "
        f"'business', (select count(*) from public.users where lower(email)=lower('{support.sql_literal(FIXTURE_EMAIL)}'))"
        ")::text;",
        values,
    )
    try:
        parsed = json.loads(counts)
    except json.JSONDecodeError:
        return False
    return parsed == {"auth": 0, "business": 0}


def login_member(
    browser: support.Browser,
    base_url: str,
    email: str,
    password: str,
) -> None:
    next_path = urllib.parse.quote("/settings/account", safe="")
    browser.command(SESSION_NAME, "open", f"{base_url}/auth/sign-in?next={next_path}")
    browser.wait_condition(SESSION_NAME, "document.querySelector('#auth-email') !== null")
    support.fill_secret_form(
        browser,
        SESSION_NAME,
        {"#auth-email": email, "#auth-password": password},
    )
    browser.command(SESSION_NAME, "click", "[data-auth-submit]")
    browser.wait_condition(
        SESSION_NAME,
        "location.pathname === '/settings/account'",
        timeout=35,
        failure_code="avatar_member_login_failed",
    )
    wait_for_account(browser)


def wait_for_account(browser: support.Browser) -> None:
    browser.wait_condition(
        SESSION_NAME,
        "document.querySelector('[data-account-content]')?.hidden === false && "
        "document.querySelector('[data-profile-avatar-input]') instanceof HTMLInputElement",
        timeout=35,
        failure_code="avatar_account_settings_unavailable",
    )


def avatar_is_loaded_expression() -> str:
    return (
        "document.querySelector('[data-profile-avatar-visual]')?.classList.contains('is-image-ready') && "
        "document.querySelector('[data-profile-avatar-image]')?.naturalWidth > 0 && "
        "document.querySelector('[data-account-profile-link]')?.classList.contains('is-image-ready') && "
        "Array.from(document.querySelectorAll('[data-account-menu-image]')).some((image) => image.naturalWidth > 0)"
    )


def database_avatar_state(values: dict[str, str], expected: str) -> None:
    email = support.sql_literal(FIXTURE_EMAIL.lower())
    support.wait_database(
        values,
        "select (case when p.avatar_storage_key is null then '0' else '1' end) || '|' || "
        "(select count(*)::text from storage.objects o where o.bucket_id='profile-avatars' "
        "and o.name=p.avatar_storage_key) "
        "from public.user_profiles p join public.users u on u.id=p.user_id "
        f"where lower(u.email)=lower('{email}');",
        expected,
        timeout=30,
    )


def exercise_avatar(
    browser: support.Browser,
    values: dict[str, str],
    loopback_url: str,
) -> tuple[bool, bool, bool, bool]:
    browser.command(
        SESSION_NAME,
        "upload",
        "#account-profile-avatar-input",
        str(support.JPEG_PATH),
        timeout=70,
    )
    browser.wait_condition(
        SESSION_NAME,
        "document.querySelector('[data-profile-avatar-status]')?.textContent.trim() === 'Profile photo saved.'",
        timeout=70,
        failure_code="avatar_upload_not_saved",
    )
    database_avatar_state(values, "1|1")
    browser.wait_condition(
        SESSION_NAME,
        avatar_is_loaded_expression(),
        timeout=35,
        failure_code="avatar_header_not_updated",
    )
    SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    browser.command(SESSION_NAME, "screenshot", str(SCREENSHOT_PATH), timeout=30)

    browser.command(SESSION_NAME, "open", f"{loopback_url}/settings/account")
    wait_for_account(browser)
    browser.wait_condition(
        SESSION_NAME,
        avatar_is_loaded_expression(),
        timeout=35,
        failure_code="avatar_refresh_not_persisted",
    )
    database_avatar_state(values, "1|1")

    browser.json_command(
        SESSION_NAME,
        "eval",
        "--stdin",
        stdin="window.confirm = () => true; 'MT_ACCEPT_YES';",
    )
    browser.command(SESSION_NAME, "click", "[data-profile-avatar-remove]")
    browser.wait_condition(
        SESSION_NAME,
        "document.querySelector('[data-profile-avatar-status]')?.textContent.trim() === 'Profile photo removed.'",
        timeout=40,
        failure_code="avatar_remove_not_saved",
    )
    browser.wait_condition(
        SESSION_NAME,
        "!document.querySelector('[data-profile-avatar-visual]')?.classList.contains('is-image-ready') && "
        "!document.querySelector('[data-account-profile-link]')?.classList.contains('is-image-ready')",
        timeout=20,
        failure_code="avatar_remove_not_synchronized",
    )
    database_avatar_state(values, "0|0")
    support.browser_diagnostics_clean(browser, SESSION_NAME)
    return True, True, True, True


def main() -> int:
    markers = {name: False for name in MARKERS}
    values: dict[str, str] | None = None
    base_url = ""
    secret = ""
    browser: support.Browser | None = None
    server = None
    lock: support.AdvisoryLock | None = None
    failure_stage = "none"
    user_id = ""

    with tempfile.TemporaryDirectory(prefix="mt-profile-avatar-browser-") as temporary_directory:
        config_path = Path(temporary_directory) / "agent-browser.json"
        config_path.write_text('{"headed":false}\n', encoding="utf-8")
        try:
            values = support.configuration()
            support.require_development(values)
            markers["profile_avatar_browser_environment_guard"] = True
            base_url = support.required(values, "SUPABASE_URL").rstrip("/")
            secret = support.service_secret(values)
            lock = support.AdvisoryLock(values)
            lock.acquire()
            if not cleanup_fixture(values, base_url, secret):
                raise support.AcceptanceError("avatar_preclean_failed")

            password = f"Mt!{secrets.token_urlsafe(28)}7a"
            user_id = support.auth_admin_create(
                base_url,
                secret,
                FIXTURE_EMAIL,
                password,
                "Profile Avatar Browser Member",
            )
            support.wait_database(
                values,
                "select count(*)::text from public.users "
                f"where id='{support.sql_literal(user_id)}'::uuid and account_status='active';",
                "1",
                timeout=25,
            )
            server, loopback_url = support.start_server(values)
            browser = support.Browser(config_path)
            if not browser.close(SESSION_NAME):
                raise support.AcceptanceError("avatar_browser_preclose_failed")
            login_member(browser, loopback_url, FIXTURE_EMAIL, password)
            uploaded, header, persisted, removed = exercise_avatar(browser, values, loopback_url)
            markers["profile_avatar_browser_upload_saved"] = uploaded
            markers["profile_avatar_browser_header_updated"] = header
            markers["profile_avatar_browser_refresh_persisted"] = persisted
            markers["profile_avatar_browser_remove_synced"] = removed
            markers["profile_avatar_browser_storage_clean"] = True
        except support.AcceptanceError as error:
            failure_stage = str(error) or "acceptance_error"
        except (OSError, ValueError, KeyError, TypeError) as error:
            failure_stage = f"unexpected_{type(error).__name__.lower()}"
        finally:
            session_closed = browser is not None
            if browser is not None:
                browser.sign_out(SESSION_NAME)
                session_closed = browser.close(SESSION_NAME)
            markers["profile_avatar_browser_session_closed"] = session_closed
            support.stop_server(server)
            if values is not None and base_url and secret:
                markers["profile_avatar_browser_fixture_cleaned"] = cleanup_fixture(values, base_url, secret)
            if lock is not None:
                lock.close()

    markers["profile_avatar_browser_acceptance"] = (
        all(markers[name] for name in MARKERS if name not in {"profile_avatar_browser_acceptance", "credentials_logged"})
        and not markers["credentials_logged"]
    )
    for name in MARKERS:
        print(f"{name}={'yes' if markers[name] else 'no'}")
    print(f"profile_avatar_browser_failure_stage={failure_stage}")
    return 0 if markers["profile_avatar_browser_acceptance"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        for marker in MARKERS:
            print(f"{marker}=no")
        print(f"profile_avatar_browser_failure_stage=unexpected_{type(error).__name__.lower()}")
        raise SystemExit(1)
