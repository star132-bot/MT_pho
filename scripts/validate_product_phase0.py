#!/usr/bin/env python3
"""Static contract checks for the Phase 0 product boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "database" / "product_schema.sql"
PUBLIC_PAGES = ["index.html", "works.html", "work.html", "about.html", "contact.html", "lightbox.html"]


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    sql = SCHEMA.read_text()
    server = (ROOT / "server.py").read_text()
    require(sql, {
        "CREATE TABLE users", "CREATE TABLE folders", "CREATE TABLE images",
        "CREATE TABLE image_versions", "CREATE TABLE review_submissions",
        "CREATE TABLE review_decisions", "CREATE TABLE notifications",
        "CREATE TABLE takedown_cases", "CREATE TABLE audit_logs",
        "CREATE TABLE upload_intents",
        "processing_status", "workflow_status", "publication_status",
        "review_decisions_append_only", "audit_logs_append_only",
        "CREATE VIEW public_works", "publication_status = 'published'",
    }, "product schema")

    for name in PUBLIC_PAGES:
        html = (ROOT / name).read_text()
        if 'href="collections.html' in html or 'href="/collections.html' in html:
            raise RuntimeError(f"{name} still exposes the removed Collections/Series route")
        if any(token in html for token in ("public-site-rail", "public-rail-page", '<aside class="archive-rail')):
            raise RuntimeError(f"{name} still exposes or reserves the retired public navigation rail")
        identity_shells = (
            '<template id="mt-header-identity" data-header-identity>',
            '<script id="mt-header-identity" type="application/json">',
        )
        if not any(shell in html for shell in identity_shells):
            raise RuntimeError(f"{name} unified public navigation is missing a Header Identity bootstrap")
        require(html, {
            "data-public-header",
            "data-global-header",
            'class="header-identity-slot"',
            "data-header-identity-slot",
            'src="/global-header.js',
            'src="/account-menu.js',
            'src="/public-navigation.js',
        }, f"{name} unified public navigation")

    global_header = (ROOT / "global-header.js").read_text()
    require(global_header, {
        "dataset.publicNav = \"\"",
        "dataset.publicNavToggle = \"\"",
        '["home", "Home", "/"]',
        '["works", "Works", "/works.html"]',
        '["about", "About", "/about.html"]',
        '["lightbox", "Lightbox", "/lightbox.html"]',
        '["contact", "Contact", "/contact.html"]',
        '["review", "Review", "/admin/reviews"]',
    }, "reusable GlobalHeader navigation")

    require(server, {
        "HEADER_IDENTITY_BOOTSTRAP_MARKER",
        "HEADER_IDENTITY_SLOT_MARKER",
        "HEADER_IDENTITY_PUBLIC_PAGES",
        "def render_header_identity(self, identity: dict)",
        'if identity.get("status") == "anonymous":',
        "data-public-sign-in",
        "def serve_header_html(",
        "HEADER_IDENTITY_BOOTSTRAP_FALLBACK_MARKER",
        "rendered_bootstrap = f'<template id=\"mt-header-identity\" data-header-identity>{bootstrap}</template>'",
        "source = source.replace(bootstrap_marker, rendered_bootstrap, 1)",
        "source = source.replace(HEADER_IDENTITY_SLOT_MARKER, self.render_header_identity(identity), 1)",
        'self.send_header("Cache-Control", "private, no-store")',
        "public_header_page = HEADER_IDENTITY_PUBLIC_PAGES.get(parsed.path)",
        "self.serve_header_html(public_header_page)",
    }, "server-rendered public header identity boundary")

    public_navigation = (ROOT / "public-navigation.js").read_text()
    require(public_navigation, {
        'window.matchMedia("(max-width: 760px)")',
        'trigger.setAttribute("aria-expanded"',
        'navigation.toggleAttribute("inert"',
        'event.key !== "ArrowDown"',
        'event.key !== "Escape"',
        'setOpen(false, { restoreFocus: true })',
    }, "responsive public navigation")

    upload_html = (ROOT / "upload-studio.html").read_text()
    if 'name="series"' in upload_html:
        raise RuntimeError("Upload Workspace still exposes Series as editable metadata")

    print("public_navigation_contract=yes")
    print("Phase 0 product contracts validated.")


if __name__ == "__main__":
    main()
