(function initializeSiteFooters() {
  const footers = Array.from(document.querySelectorAll("[data-site-footer]"));
  if (!footers.length) return;

  const currentYear = new Date().getFullYear();
  // Visitor footer: one quiet line on the paper, as in design/site-mockups-v2.
  function publicFooterMarkup() {
    return `
      <div class="mt-footer-inner">
        <a class="mt-footer-brand" href="/">MT Presence</a>
        <nav class="mt-footer-nav" aria-label="Explore">
          <a href="/">Home</a>
          <a href="/works.html">Works</a>
          <a href="/contact.html">Contact</a>
          <a href="/privacy.html">Privacy</a>
        </nav>
        <p class="mt-footer-copy">&copy; <span data-footer-year>${currentYear}</span> MT Presence</p>
      </div>
    `;
  }
  function workspaceFooterMarkup() {
    return `
      <div class="workspace-footer-inner">
        <p>&copy; <span data-footer-year>${currentYear}</span> MT Presence</p>
        <nav aria-label="Workspace footer">
          <a href="/works.html">Public Works</a>
          <a href="/contact.html">Contact</a>
          <a href="/privacy.html">Privacy</a>
        </nav>
      </div>
    `;
  }

  function normalizePath(value) {
    const path = String(value || "/").replace(/\/$/, "") || "/";
    return path === "/index.html" ? "/" : path;
  }

  function markCurrentLinks(footer) {
    const currentPath = normalizePath(window.location.pathname);
    footer.querySelectorAll("a[href]").forEach((link) => {
      const linkUrl = new URL(link.href, window.location.href);
      const linkPath = normalizePath(linkUrl.pathname);
      if (linkPath === currentPath && !linkUrl.search) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  footers.forEach((footer) => {
    const isWorkspace = footer.dataset.footerVariant === "workspace";
    footer.innerHTML = isWorkspace ? workspaceFooterMarkup() : publicFooterMarkup();
    if (!isWorkspace) footer.classList.add("mt-footer");
    footer.dataset.footerReady = "true";
    markCurrentLinks(footer);
  });

})();
