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
        if name == "index.html":
            if "public-site-rail" in html or "public-rail-page" in html:
                raise RuntimeError("index.html must keep the homepage free of the left navigation rail")
            require(html, {
                'class="site-header"',
                'href="/works.html"',
                'href="/about.html"',
                'href="/contact.html"',
                'href="/lightbox.html"',
                "data-home-account-entry",
            }, "index.html top navigation")
            continue
        require(html, {
            "public-site-rail",
            'href="index.html" aria-label="Home"',
            'href="/workspace/images" aria-label="Upload images"',
            'href="lightbox.html"',
            'href="about.html"',
            'href="contact.html"',
        }, f"{name} public navigation")

    upload_html = (ROOT / "upload-studio.html").read_text()
    if 'name="series"' in upload_html:
        raise RuntimeError("Upload Workspace still exposes Series as editable metadata")

    print("public_navigation_contract=yes")
    print("Phase 0 product contracts validated.")


if __name__ == "__main__":
    main()
