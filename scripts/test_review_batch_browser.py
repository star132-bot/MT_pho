#!/usr/bin/env python3
"""Secret-free browser acceptance for Super Admin batch self-publication."""

from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.test_review_queue_boundary import (  # noqa: E402
    FakeSupabaseHandler,
    SUBMISSION_A,
    SUBMISSION_PUBLIC,
    SUPER_ADMIN_TOKEN,
)
from scripts.test_workspace_trash_browser import Browser, BrowserFailure, assert_browser  # noqa: E402


def main() -> None:
    FakeSupabaseHandler.review_calls = []
    FakeSupabaseHandler.storage_sign_calls = 0
    FakeSupabaseHandler.next_review_status = None
    FakeSupabaseHandler.next_review_error_code = None
    FakeSupabaseHandler.next_decision_result = None
    FakeSupabaseHandler.decision_results = {}
    FakeSupabaseHandler.decision_payloads = {}
    FakeSupabaseHandler.decision_writes = 0
    FakeSupabaseHandler.browser_batch_mode = True

    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{provider.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_COOKIE_SECURE"] = "0"

    app = importlib.import_module("server")
    application = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(app.MTRequestHandler, directory=str(ROOT)),
    )
    threading.Thread(target=application.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{application.server_address[1]}"
    os.environ["MT_PUBLIC_BASE_URL"] = base_url
    browser = Browser("mt-review-batch")

    try:
        browser.close()
        browser.command("set", "viewport", "1440", "1000")
        browser.command("open", base_url)
        cookie = f"mt_access_token={SUPER_ADMIN_TOKEN}; Path=/; SameSite=Lax"
        browser.evaluate(f"document.cookie = {json.dumps(cookie)}; true")
        browser.command("open", f"{base_url}/admin/reviews")
        browser.wait_for("document.querySelector('[data-review-queue]')?.getAttribute('aria-busy') === 'false'", timeout=20)

        assert_browser(
            browser,
            "document.querySelectorAll('[data-review-bulk-item]').length === 2 && document.querySelector('[data-review-bulk-tools]')?.hidden === false",
            "Eligible owned submissions were not exposed as an explicit batch selection.",
        )
        browser.command("click", "[data-review-bulk-select-all]")
        assert_browser(
            browser,
            "document.querySelector('[data-review-bulk-publish]')?.disabled === false && document.querySelector('[data-review-bulk-publish]')?.textContent.includes('(2)')",
            "Select eligible did not select both owned untouched submissions.",
        )
        assert_browser(
            browser,
            "(() => { const heading = document.querySelector('.admin-review-queue-heading')?.getBoundingClientRect(); const tools = document.querySelector('[data-review-bulk-tools]')?.getBoundingClientRect(); const button = document.querySelector('[data-review-bulk-publish]'); return heading && tools && button && tools.top >= heading.bottom - 1 && button.scrollWidth <= button.clientWidth + 1 && getComputedStyle(button).whiteSpace === 'nowrap'; })()",
            "Review batch controls overlapped the queue heading or clipped the publish command.",
        )
        browser.command("screenshot", "/tmp/mt-review-batch-desktop.png")
        print("review_batch_selection=yes")

        browser.command("click", "[data-review-bulk-publish]")
        browser.wait_for("document.querySelector('[data-review-bulk-dialog]')?.open === true")
        assert_browser(
            browser,
            "document.querySelectorAll('.admin-review-bulk-policy li').length === 10 && document.querySelector('[data-review-bulk-form] [name=policy_attestation]')?.required === true && document.querySelector('[data-review-bulk-description]')?.textContent.includes('individually')",
            "Batch publication did not retain the ten-check attestation and per-work revalidation warning.",
        )
        browser.command("screenshot", "/tmp/mt-review-batch-dialog.png")
        print("review_batch_policy_attestation=yes")

        browser.command("click", "[data-review-bulk-form] [name=policy_attestation]")
        browser.command("click", "[data-review-bulk-confirm]")
        browser.wait_for("document.querySelector('[data-review-live]')?.textContent.includes('2 works published')", timeout=20)

        decision_calls = [
            (path, payload, token)
            for path, payload, token in FakeSupabaseHandler.review_calls
            if path == "/rest/v1/rpc/review_super_admin_self_publish"
        ]
        if len(decision_calls) != 2 or FakeSupabaseHandler.decision_writes != 2:
            raise BrowserFailure("Batch publication did not create one dedicated decision per selected work.")
        if {payload.get("submission_id") for _, payload, _ in decision_calls} != {SUBMISSION_PUBLIC, SUBMISSION_A}:
            raise BrowserFailure("Batch publication changed the selected submission set.")
        if any(
            token != SUPER_ADMIN_TOKEN
            or payload.get("reason_codes") != ["policy_complete"]
            or "decision" in payload
            or set(payload.get("checklist_result", {}).values()) != {True}
            for _, payload, token in decision_calls
        ):
            raise BrowserFailure("A batch item bypassed the dedicated Super Admin policy contract.")
        print("review_batch_independent_audit_requests=yes")

        browser.command("click", f"[data-review-submission='{SUBMISSION_PUBLIC}']")
        browser.wait_for("document.querySelector('[data-review-decision-form]')?.hidden === false")
        browser.command("click", "[data-review-check-all]")
        assert_browser(
            browser,
            "[...document.querySelectorAll('[data-review-checklist] input')].length === 10 && [...document.querySelectorAll('[data-review-checklist] input')].every((input) => input.checked)",
            "The single-item checklist shortcut did not confirm all ten visible checks.",
        )
        print("review_check_all_shortcut=yes")

        assert_browser(
            browser,
            "document.documentElement.scrollWidth <= window.innerWidth",
            "Review Queue overflowed the desktop viewport.",
        )
        browser.command("set", "viewport", "390", "844")
        browser.command("wait", "200")
        browser.command("click", "[data-review-back-to-queue]")
        browser.wait_for("document.querySelector('[data-review-workspace]')?.dataset.mobileView === 'queue'")
        browser.evaluate("window.scrollTo(0, 0); true")
        assert_browser(
            browser,
            "(() => { const tools = document.querySelector('[data-review-bulk-tools]')?.getBoundingClientRect(); const button = document.querySelector('[data-review-bulk-publish]')?.getBoundingClientRect(); return document.documentElement.scrollWidth <= window.innerWidth && tools && button && tools.right <= innerWidth + 1 && tools.left >= -1 && button.left >= tools.left - 1 && button.right <= tools.right + 1; })()",
            "Review batch controls overflowed the mobile viewport.",
        )
        browser.command("screenshot", "/tmp/mt-review-batch-mobile.png")
        print("review_batch_responsive=yes")

        error_payload = browser.json_command("errors")
        error_data = error_payload.get("data") if isinstance(error_payload.get("data"), dict) else error_payload
        errors = error_data.get("errors", error_data.get("items", []))
        if errors:
            raise BrowserFailure("Review batch browser reported page errors.")
        print("review_batch_console_clean=yes")
        print("review_batch_browser_acceptance=yes")
    finally:
        browser.close()
        application.shutdown()
        application.server_close()
        provider.shutdown()
        provider.server_close()
        FakeSupabaseHandler.browser_batch_mode = False


if __name__ == "__main__":
    main()
