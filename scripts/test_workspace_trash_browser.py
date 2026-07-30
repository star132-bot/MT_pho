#!/usr/bin/env python3
"""Secret-free browser acceptance for Workspace Trash/Restore and quick upload."""

from __future__ import annotations

from functools import partial
from http.server import ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.test_workspace_phase2_boundary import FakeSupabaseHandler  # noqa: E402


class BrowserFailure(RuntimeError):
    pass


class Browser:
    def __init__(self, session_prefix: str = "mt-workspace-trash") -> None:
        binary = shutil.which("agent-browser")
        if not binary:
            raise BrowserFailure("agent-browser is required for Workspace browser acceptance")
        self.binary = binary
        self.session = f"{session_prefix}-{os.getpid()}"

    def command(self, *args: str, timeout: int = 20) -> str:
        completed = subprocess.run(
            [self.binary, "--session-name", self.session, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise BrowserFailure(f"agent-browser command failed: {' '.join(args[:2])}")
        return completed.stdout.strip()

    def evaluate(self, expression: str):
        output = self.command("eval", expression)
        try:
            return json.loads(output)
        except json.JSONDecodeError as error:
            raise BrowserFailure("agent-browser returned invalid evaluation JSON") from error

    def json_command(self, *args: str) -> dict:
        completed = subprocess.run(
            [self.binary, "--session-name", self.session, "--json", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            raise BrowserFailure(f"agent-browser JSON command failed: {' '.join(args[:2])}")
        for line in reversed(completed.stdout.splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise BrowserFailure("agent-browser returned invalid structured output")

    def wait_for(self, expression: str, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(f"Boolean({expression})") is True:
                return
            time.sleep(0.1)
        raise BrowserFailure("browser condition timed out")

    def close(self) -> None:
        subprocess.run(
            [self.binary, "--session-name", self.session, "close"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


def assert_browser(browser: Browser, expression: str, message: str) -> None:
    if browser.evaluate(f"Boolean({expression})") is not True:
        raise BrowserFailure(message)


def assert_responsive(browser: Browser, screenshot_name: str) -> None:
    assert_browser(
        browser,
        "document.documentElement.scrollWidth <= window.innerWidth",
        "Workspace has horizontal viewport overflow",
    )
    assert_browser(
        browser,
        "[...document.querySelectorAll('.upload-studio-card, .upload-studio-view-switch')].every((node) => { const r=node.getBoundingClientRect(); return r.left >= -1 && r.right <= innerWidth + 1; })",
        "Trash controls escape the viewport",
    )
    assert_browser(
        browser,
        "document.querySelector('#upload-studio-title').getBoundingClientRect().top >= document.querySelector('.upload-studio-header').getBoundingClientRect().bottom + 12",
        "Workspace title overlaps the fixed header",
    )
    browser.command("screenshot", f"/tmp/{screenshot_name}")


def main() -> None:
    FakeSupabaseHandler.rpc_calls = []
    FakeSupabaseHandler.storage_calls = []
    FakeSupabaseHandler.storage_delete_calls = []
    FakeSupabaseHandler.reset_draft_state()
    FakeSupabaseHandler.draft_deleted_at = "2026-07-22T03:00:00Z"
    FakeSupabaseHandler.restore_folder_missing = True
    FakeSupabaseHandler.restore_delay_seconds = 2.0

    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabaseHandler)
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()
    os.environ["SUPABASE_URL"] = f"http://127.0.0.1:{fake_server.server_address[1]}"
    os.environ["SUPABASE_PUBLISHABLE_KEY"] = "test-publishable-key"
    os.environ["MT_COOKIE_SECURE"] = "0"

    app = importlib.import_module("server")
    handler = partial(app.MTRequestHandler, directory=str(ROOT))
    app_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    base_url = f"http://127.0.0.1:{app_server.server_address[1]}"
    os.environ["MT_PUBLIC_BASE_URL"] = base_url
    browser = Browser()

    try:
        browser.close()
        browser.command("set", "viewport", "1440", "900")
        browser.command("open", f"{base_url}/auth/sign-in?next=%2Fworkspace%2Fimages")
        browser.wait_for("document.querySelector('#auth-email')")
        browser.command("fill", "#auth-email", "member@example.test")
        browser.command("fill", "#auth-password", "Member-password-2026!")
        browser.command("click", "[data-auth-submit]")
        browser.wait_for("location.pathname === '/workspace/images'", timeout=20)
        browser.wait_for("document.querySelector('[data-studio-queue]')?.getAttribute('aria-busy') === 'false'", timeout=20)
        print("workspace_browser_login=yes")

        browser.command("click", "[data-studio-view=trash]")
        browser.wait_for("document.querySelector('.upload-studio-trash-card')")
        assert_browser(
            browser,
            "document.querySelectorAll('.upload-studio-trash-card').length === 1 && document.querySelectorAll('[data-trash-restore]').length === 1 && document.querySelectorAll('[data-studio-delete-record]:not([disabled])').length === 0",
            "Trash did not remain read-only with one Restore command",
        )
        assert_responsive(browser, "mt-workspace-trash-desktop.png")
        browser.command("set", "viewport", "390", "844")
        browser.command("wait", "200")
        assert_responsive(browser, "mt-workspace-trash-mobile.png")
        print("workspace_trash_read_only=yes")
        print("workspace_trash_responsive=yes")

        browser.command("click", "[data-trash-restore]")
        browser.wait_for("document.querySelector('.upload-studio-trash-card')?.getAttribute('aria-busy') === 'true'")
        assert_browser(
            browser,
            "document.querySelector('.upload-studio-trash-card')?.textContent.includes('Restoring') && [...document.querySelectorAll('[data-studio-view]')].every((button) => button.disabled)",
            "Restore did not expose a stable in-progress state",
        )
        browser.wait_for("document.querySelector('.upload-studio-trash-card') === null")
        assert_browser(
            browser,
            "document.querySelector('[data-studio-queue]')?.textContent.includes('Trash is empty') && document.activeElement?.matches('[data-studio-view=trash]')",
            "Restore did not remove the Draft from Trash and return focus",
        )
        browser.command("click", "[data-studio-view=drafts]")
        browser.wait_for("document.querySelector('[data-record-id]')")
        assert_browser(
            browser,
            "document.querySelector('[data-record-id]')?.textContent.includes('Server Draft') && document.querySelector('[data-folder-id].is-active')?.textContent.includes('Inbox')",
            "Restored Draft did not return to the active Inbox",
        )
        print("workspace_trash_restore=yes")

        browser.command("set", "viewport", "1440", "900")
        browser.command("click", "[data-quick-upload-open]")
        browser.wait_for("document.querySelector('[data-quick-upload-dialog]')?.open === true")
        assert_browser(
            browser,
            "document.querySelector('[data-quick-upload-input]')?.multiple === true && document.querySelector('[data-quick-upload-form] [name=copyright_year]')?.value.length === 4 && document.querySelector('[data-quick-upload-form] [name=content_category]')?.value === 'auto' && document.querySelector('[data-quick-upload-form] [name=rights_declared]')?.required === true && document.querySelector('[data-quick-upload-form] .upload-studio-confirm-actions')?.getBoundingClientRect().bottom <= innerHeight + 1",
            "Quick Upload did not expose one reusable declaration form for a multi-file batch",
        )
        browser.command("screenshot", "/tmp/mt-workspace-quick-upload-desktop.png")
        browser.command("click", "[data-quick-upload-cancel]")
        browser.wait_for("document.querySelector('[data-quick-upload-dialog]')?.open === false")

        browser.command("set", "viewport", "390", "844")
        browser.command("click", "[data-quick-upload-open]")
        browser.wait_for("document.querySelector('[data-quick-upload-dialog]')?.open === true")
        assert_browser(
            browser,
            "document.documentElement.scrollWidth <= window.innerWidth && document.querySelector('[data-quick-upload-dialog]').scrollWidth <= window.innerWidth && document.querySelector('[data-quick-upload-form] .upload-studio-confirm-actions')?.getBoundingClientRect().bottom <= innerHeight + 1",
            "Quick Upload dialog overflowed the mobile viewport",
        )
        browser.command("screenshot", "/tmp/mt-workspace-quick-upload-mobile.png")
        browser.command("click", "[data-quick-upload-cancel]")
        browser.wait_for("document.querySelector('[data-quick-upload-dialog]')?.open === false")
        print("workspace_quick_upload_defaults=yes")

        FakeSupabaseHandler.draft_version_patch = {
            "alt_text": "A quiet field beneath a pale sky.",
            "copyright_holder": "MT Presence",
            "copyright_year": 2026,
            "contains_recognizable_people": False,
            "model_release_status": "not_applicable",
            "property_release_status": "not_applicable",
            "rights_declared": True,
            "ai_disclosure": "none",
            "sensitive_content_disclosure": "none",
        }
        FakeSupabaseHandler.asset_scan_statuses = {
            "original": "clean",
            "display": "clean",
            "thumbnail": "clean",
        }
        browser.command("click", "[data-studio-submit-ready]")
        browser.wait_for("document.querySelector('[data-studio-submit-dialog]')?.open === true")
        assert_browser(
            browser,
            "document.querySelector('[data-studio-submit-dialog-title]')?.textContent.includes('Submit 1 ready Draft') && document.querySelector('[data-studio-submit-dialog-description]')?.textContent.includes('Only ready Drafts')",
            "Batch submission did not recheck readiness before presenting its bounded confirmation",
        )
        browser.command("click", "[data-studio-submit-dialog] button[value=cancel]")
        browser.wait_for("document.querySelector('[data-studio-submit-dialog]')?.open === false")
        print("workspace_batch_submit_ready=yes")

        error_payload = browser.json_command("errors")
        error_data = error_payload.get("data") if isinstance(error_payload.get("data"), dict) else error_payload
        errors = error_data.get("errors", error_data.get("items", []))
        if errors:
            raise BrowserFailure("Workspace browser reported page errors")
        print("workspace_trash_console_clean=yes")
        print("workspace_trash_browser_acceptance=yes")
    finally:
        browser.close()
        app_server.shutdown()
        app_server.server_close()
        fake_server.shutdown()
        fake_server.server_close()


if __name__ == "__main__":
    main()
