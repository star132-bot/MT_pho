#!/usr/bin/env python3
"""Static contract checks for the Phase 0 product boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "database" / "product_schema.sql"
PUBLIC_PAGES = ["index.html", "works.html", "about.html", "contact.html", "lightbox.html"]


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    sql = SCHEMA.read_text()
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
        require(html, {
            "data-public-header",
            "data-public-nav",
            "data-public-nav-toggle",
            "data-public-sign-in",
            'href="/"',
            'href="/works.html"',
            'href="/about.html"',
            'href="/lightbox.html"',
            'href="/contact.html"',
            'src="/account-menu.js',
            'src="/public-navigation.js',
        }, f"{name} unified public navigation")

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
