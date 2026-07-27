#!/usr/bin/env python3
"""Static contracts for favorite, inquiry-selection, and Header Identity behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER_PAGES = (
    "index.html",
    "works.html",
    "work.html",
    "about.html",
    "contact.html",
    "lightbox.html",
    "creator.html",
    "dashboard.html",
    "upload-studio.html",
    "account-settings.html",
    "admin-reviews.html",
    "admin-works.html",
)
GLOBAL_HEADER_PAGES = {
    "index.html", "works.html", "work.html", "about.html", "contact.html", "lightbox.html",
    "creator.html", "dashboard.html", "admin-reviews.html",
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(source: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in source)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def block(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def main() -> None:
    archive = read("archive.js")
    public_archive = read("public-archive.js")
    lightbox_html = read("lightbox.html")
    lightbox = read("lightbox.js")
    contact = read("contact.js")
    account_menu = read("account-menu.js")
    global_header = read("global-header.js")
    site_footer = read("site-footer.js")
    server = read("server.py")
    styles = read("styles.css")

    favorite_toggle = block(archive, "function toggleLightboxWork(", "function downloadWork(")
    favorite_event = block(
        archive,
        'window.addEventListener("mt:lightbox-change"',
        'window.addEventListener("storage"',
    )
    storage_event = block(archive, 'window.addEventListener("storage"', "initArchive();")
    for label, source in (
        ("favorite toggle", favorite_toggle),
        ("favorite change event", favorite_event),
        ("favorite storage event", storage_event),
    ):
        forbidden = [token for token in ("renderGallery()", "gallery.innerHTML", "location.reload") if token in source]
        if forbidden:
            raise RuntimeError(f"{label} rebuilds or reloads the Gallery: {', '.join(forbidden)}")
    require(archive, {
        'type="button" data-card-action="lightbox"',
        "event.preventDefault();",
        "event.stopPropagation();",
        "pendingLightboxWorkIds",
        "patchLightboxWorkState",
        "reconcileLightboxWorkIds",
        "is-bookmark-popping",
        'aria-label="${isInLightbox ? "Remove from Lightbox" : "Add to Lightbox"}"',
    }, "Works favorite controller")

    require(public_archive, {
        'const LIGHTBOX_STORAGE_KEY = "mt-presence-lightbox-v1"',
        'const INQUIRY_SELECTION_STORAGE_KEY = "mt-presence-inquiry-selection-v1"',
        "function readInquirySelectionIds()",
        "function writeInquirySelectionIds(ids)",
        "pruneInquirySelection(normalized)",
    }, "public interaction state")

    require(lightbox_html, {
        "data-inquiry-selection-count",
        "data-select-all",
        "data-clear-inquiry-selection disabled",
        "data-contact-selected disabled",
        "data-remove-all-lightbox",
        "Clear all",
        "Selected 0 of 0",
        "Inquire about selected (0)",
    }, "Lightbox controls")
    require(lightbox, {
        "function persistInquirySelection(",
        'event.target.closest("[data-toggle-inquiry-work]")',
        "publicArchive.writeInquirySelectionIds",
        "publicArchive.writeLightboxIds",
        "item.remove();",
        "window.confirm(",
        'params.append("work", id)',
        'window.addEventListener("pageshow"',
        'window.addEventListener("mt:lightbox-change"',
        'window.addEventListener("storage"',
        "publicArchive.LIGHTBOX_STORAGE_KEY",
        "function reconcileLightboxCollection(",
        'window.addEventListener("mt:inquiry-selection-change"',
    }, "Lightbox selection controller")
    selection_handler = block(
        lightbox,
        'const selectionButton = event.target.closest("[data-toggle-inquiry-work]")',
        'const removeButton = event.target.closest("[data-remove-lightbox-work]")',
    )
    if "renderLightbox" in selection_handler or "innerHTML" in selection_handler or "replaceChildren" in selection_handler:
        raise RuntimeError("Inquiry selection must patch cards and toolbar without rebuilding the Lightbox Gallery")

    contact_hydration = block(contact, "async function hydrateContactContext()", "async function contactCsrfToken(")
    require(contact_hydration, {
        'if (contactSource === "lightbox")',
        "new Set(publicArchive.readInquirySelectionIds())",
        "requestedContextWorkIds.filter((id) => selectedIds.has(id))",
        'setContactContextState("loading")',
        "result.error === true",
        'setContactContextState("error")',
    }, "Contact selected-ID hydration")
    if "readLightboxIds" in contact_hydration:
        raise RuntimeError("Contact must never fall back from Inquiry Selection to every saved Lightbox work")
    require(contact, {
        'contactParams.getAll("work")',
        "publicArchive.writeInquirySelectionIds",
        "window.history.replaceState",
        'contactContextState !== "ready"',
    }, "Contact selection removal")

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
        'destination("Dashboard", "/dashboard")',
        'destination("Workspace", "/workspace/images")',
        'destination("Account Settings", "/settings/account")',
        "dataset.accountMenuAvatarInitials",
        "Active account",
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
        'parsed.path in {"/manage", "/manage/", "/manage.html"}',
        'self.send_header("Location", "/admin/reviews")',
        '"email": email',
        "data-account-menu-email",
        "data-account-menu-status",
    }, "server Header Identity bootstrap")
    rendered_identity = block(server, "def render_header_identity(", "def serve_header_html(")
    if any(secret in rendered_identity for secret in ("access_token", "refresh_token", "ACCESS_COOKIE", "REFRESH_COOKIE")):
        raise RuntimeError("Rendered Header Identity must not contain session secrets")

    require(site_footer, {
        'window.addEventListener("mt:header-identity-change"',
        "function renderHeaderIdentity(",
        'identity.status === "anonymous"',
    }, "Footer Header Identity synchronization")

    for page in HEADER_PAGES:
        html = read(page)
        identity_shells = (
            '<template id="mt-header-identity" data-header-identity>',
            '<script id="mt-header-identity" type="application/json">',
        )
        if not any(shell in html for shell in identity_shells):
            raise RuntimeError(f"{page} Header Identity shell is missing a bootstrap element")
        require(html, {
            "data-header-identity-slot",
            'src="/account-menu.js',
        }, f"{page} Header Identity shell")
        if page in GLOBAL_HEADER_PAGES:
            require(html, {
                "data-global-header",
                'src="/global-header.js',
            }, f"{page} GlobalHeader shell")
        else:
            require(html, {"data-review-nav"}, f"{page} legacy workspace navigation")

    require(global_header, {
        "dataset.globalHeaderReady",
        "Search works, artists, tags",
        "SEARCH_DELAY_MS = 260",
        'link.dataset.reviewNav = ""',
        'window.dispatchEvent(new CustomEvent("mt:global-search-change"',
        'setSearchMessage("No matching works."',
        'event.key === "Escape"',
    }, "GlobalHeader component")

    require(styles, {
        ".header-identity-slot",
        "width: 42px;",
        "height: 42px;",
        "width: 38px;",
        "height: 38px;",
        ".account-profile-link.is-image-ready",
        "@keyframes bookmark-pop",
        ".lightbox-item.is-inquiry-selected",
    }, "interaction styles")

    print("works_favorite_original_nodes=yes")
    print("lightbox_inquiry_selection=yes")
    print("header_identity_bootstrap=yes")


if __name__ == "__main__":
    main()
