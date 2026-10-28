#!/usr/bin/env python3
"""Static contracts for visitor-only public pages and the staff Header Identity."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Visitors browse anonymously: no account menu, Lightbox, save, or download.
VISITOR_PAGES = ("index.html", "works.html", "contact.html")
# Staff pages keep the server-rendered Header Identity and account menu.
STAFF_PAGES = ("admin.html", "upload-studio.html", "account-settings.html", "admin-works.html")
GLOBAL_HEADER_PAGES = {"index.html", "works.html", "contact.html"}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def forbid(source: str, tokens: tuple[str, ...], label: str) -> None:
    present = [token for token in tokens if token in source]
    if present:
        raise RuntimeError(f"{label} still contains: {', '.join(present)}")


def block(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    works_html = read("works.html")
    exhibition_html = read("exhibition.html")
    exhibition = read("exhibition.js")
    homepage = read("index.html")
    site_styles = read("site.css")
    contact = read("contact.js")
    account_menu = read("account-menu.js")
    global_header = read("global-header.js")
    site_footer = read("site-footer.js")
    server = read("server.py")
    styles = read("styles.css")

    # Saving to a Lightbox and downloading images were retired with public accounts
    # (requirements 02 and 04); works are viewed in the exhibition (requirement 07).
    forbid(works_html, ("lightbox", "download", "/creators/"), "Works series posters")
    forbid(exhibition_html, ("lightbox", "download"), "Exhibition view")
    forbid(exhibition, ("requireAuthentication", "toggleLightboxId", "link.download", ".download ="), "Exhibition controller")
    require(works_html, {'href="/exhibition.html?series=colour"', 'href="/exhibition.html?series=grey"'}, "Works series posters")
    forbid(contact, ("lightbox", "readInquirySelectionIds"), "Contact inquiry context")
    require(contact, {
        'contactParams.getAll("work")',
        'contactContextState !== "ready"',
        'const supportedContactSources = new Set(["general", "work", "series"]);',
    }, "Contact work context")

    require(account_menu, {
        "function normalizeIdentity(",
        "authenticated,",
        "display_name: displayName",
        "initials:",
        "avatar_url:",
        "roles,",
        "can_review:",
        "email:",
        "await image.decode()",
        'error.status === 401',
        'refresh_avatar", "1"',
        'document.querySelectorAll("[data-review-nav]")',
        "bootstrapElement?.content?.textContent",
        'destination("总览", "/admin")',
        'destination("上传图片", "/workspace/images")',
        'destination("账号与安全", "/settings/account")',
        "dataset.accountMenuAvatarInitials",
        "账号正常",
        "window.MTPresenceHeaderIdentity = identity",
    }, "Header Identity controller")
    forbidden_menu = (
        "dataAccountMenuReview", "data-account-menu-review", 'destination("Review"',
        'destination("Notifications"', 'destination("Inbox"',
    )
    if any(token in account_menu for token in forbidden_menu):
        raise RuntimeError("Review must not be created inside the account menu")

    require(server, {
        "def header_identity_model(",
        "def current_header_identity(",
        "def render_header_identity(",
        "def serve_header_html(",
        "HEADER_IDENTITY_BOOTSTRAP_MARKER",
        "HEADER_IDENTITY_SLOT_MARKER",
        'source.replace(" data-review-nav hidden", " data-review-nav")',
        "def signed_profile_avatar_coordinates(",
        "def refresh_signed_profile_avatar(",
        'query.get("refresh_avatar") == ["1"]',
        '"/manage": "/admin",',
        'RETIRED_PAGE_PREFIXES = ("/admin/reviews", "/admin/users")',
        '"email": email',
        "data-account-menu-email",
        "data-account-menu-status",
    }, "server Header Identity bootstrap")
    rendered_identity = block(server, "def render_header_identity(", "def serve_header_html(")
    if any(secret in rendered_identity for secret in ("access_token", "refresh_token", "ACCESS_COOKIE", "REFRESH_COOKIE")):
        raise RuntimeError("Rendered Header Identity must not contain session secrets")

    forbid(site_footer, ("/auth/sign-in", "/dashboard", "/lightbox.html", "mt:header-identity-change"), "Public footer")
    forbid(account_menu, ('"/dashboard"',), "Header Identity controller")

    for page in VISITOR_PAGES:
        html = read(page)
        if '<template id="mt-header-identity" data-header-identity>' not in html:
            raise RuntimeError(f"{page} is missing its Header Identity bootstrap marker")
        forbid(html, ('src="/account-menu.js',), f"{page} visitor shell")
        if page in GLOBAL_HEADER_PAGES:
            require(html, {"data-global-header", 'src="/global-header.js'}, f"{page} GlobalHeader shell")
    for page in STAFF_PAGES:
        html = read(page)
        identity_shells = (
            '<template id="mt-header-identity" data-header-identity>',
            '<script id="mt-header-identity" type="application/json">',
        )
        if not any(shell in html for shell in identity_shells):
            raise RuntimeError(f"{page} Header Identity shell is missing a bootstrap element")
        require(html, {"data-header-identity-slot", 'src="/account-menu.js'}, f"{page} Header Identity shell")
        if page in GLOBAL_HEADER_PAGES:
            require(html, {"data-global-header", 'src="/global-header.js'}, f"{page} GlobalHeader shell")
        else:
            # The 2026-10-27 admin shell renders its navigation from admin-shell.js.
            if "data-admin-nav" in html:
                require(html, {'href="/admin"', 'src="/admin-shell.js'}, f"{page} staff navigation")
            else:
                require(html, {'aria-label="Staff navigation"', 'href="/admin"'}, f"{page} staff navigation")
            forbid(html, ('href="/admin/reviews"', 'href="/admin/users"', 'href="/dashboard"'), f"{page} staff navigation")

    require(global_header, {
        "dataset.globalHeaderReady",
        "Search works, artists, tags",
        "SEARCH_DELAY_MS = 260",
        'setSearchMessage("No matching works."',
        'event.key === "Escape"',
        "return `/exhibition.html?${params.toString()}`;",
    }, "GlobalHeader component")

    require(styles, {
        ".header-identity-slot",
        "width: 42px;",
        "height: 42px;",
        "width: 38px;",
        "height: 38px;",
        ".account-profile-link.is-image-ready",
    }, "interaction styles")

    # Home (design/site-mockups-v2): one full-bleed hero, then the selected
    # works, the About section (requirement 05) and the contact invitation.
    require(homepage, {
        'class="mt-hero"',
        'fetchpriority="high"',
        'id="about"',
        "data-about-name",
        'src="/about.js',
        'href="/contact.html"',
    }, "Home editorial structure")
    require(site_styles, {
        ".mt-hero {",
        "height: 100svh;",
        "@media (prefers-reduced-motion: reduce)",
        "animation: none;",
    }, "Home hero styles")

    print("visitor_save_download_retired=yes")
    print("header_identity_bootstrap=yes")
    print("home_editorial_structure=yes")


if __name__ == "__main__":
    main()
