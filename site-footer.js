(function initializeSiteFooters() {
  const footers = Array.from(document.querySelectorAll("[data-site-footer]"));
  if (!footers.length) return;

  const currentYear = new Date().getFullYear();
  function publicFooterMarkup(isContactPage) {
    return `
      <div class="site-footer-frame">
        ${
          isContactPage
            ? ""
            : `
              <section class="public-footer-contact" aria-labelledby="footer-contact-title">
                <div class="public-footer-contact-copy">
                  <p class="site-footer-kicker">Inquiries</p>
                  <h2 id="footer-contact-title">Exhibitions, licensing, and commissions.</h2>
                  <p>For presentations, image use, and considered collaborations, begin a conversation with the artist.</p>
                </div>
                <a class="public-footer-contact-link" href="/contact.html">
                  <span>Contact Artist</span>
                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M5 12h14"></path>
                    <path d="m13 6 6 6-6 6"></path>
                  </svg>
                </a>
              </section>
            `
        }

        <div class="public-footer-main">
          <section class="public-footer-brand" aria-labelledby="footer-brand-title">
            <h2 id="footer-brand-title"><a href="/">MT Presence</a></h2>
            <p>Fine art photography for long looking.</p>
          </section>

          <nav class="site-footer-nav" aria-label="Explore">
            <h2>Explore</h2>
            <a href="/">Home</a>
            <a href="/works.html">Works</a>
            <a href="/about.html">About</a>
            <a href="/lightbox.html">Lightbox</a>
            <a href="/contact.html">Contact</a>
            <a href="/privacy.html">Privacy</a>
          </nav>

          <nav class="site-footer-nav" aria-label="Practice">
            <h2>Practice</h2>
            <a href="/contact.html?type=exhibition">Exhibition inquiries</a>
            <a href="/contact.html?type=licensing">Licensing</a>
            <a href="/contact.html?type=commission">Commissions</a>
          </nav>

          <nav class="site-footer-nav" aria-label="Account" data-footer-account-nav>
            <h2>Account</h2>
            <a href="/auth/sign-in" data-footer-account-sign-in>Sign In</a>
            <span class="site-footer-account-status" data-footer-account-unavailable hidden>Account access unavailable</span>
            <a href="/dashboard" data-footer-account-member hidden>Dashboard</a>
            <a href="/workspace/images" data-footer-account-active hidden>Upload</a>
            <a href="/settings/account" data-footer-account-member hidden>Account Settings</a>
            <a href="/admin/reviews" data-footer-account-review hidden>Review</a>
            <a href="/admin/works" data-footer-account-governance hidden>Works Governance</a>
            <a href="/admin/audit" data-footer-account-audit hidden>Audit Ledger</a>
          </nav>
        </div>

        <div class="site-footer-bottom">
          <p>&copy; <span data-footer-year>${currentYear}</span> MT Presence</p>
          <p>All rights reserved.</p>
        </div>
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
    footer.innerHTML = isWorkspace
      ? workspaceFooterMarkup()
      : publicFooterMarkup(footer.dataset.footerContext === "contact");
    footer.dataset.footerReady = "true";
    markCurrentLinks(footer);
  });

  function renderAccount(payload = {}) {
    const roles = Array.isArray(payload.account?.roles) ? payload.account.roles : [];
    const accountStatus = String(payload.account?.account_status || "");
    const isActive = accountStatus === "active";
    const canReview = isActive && roles.some((role) => ["reviewer", "admin", "super_admin"].includes(role));
    const canGovern = isActive && roles.some((role) => ["admin", "super_admin"].includes(role));

    footers.forEach((footer) => {
      const accountNavigation = footer.querySelector("[data-footer-account-nav]");
      if (!accountNavigation) return;
      accountNavigation.querySelector("[data-footer-account-sign-in]")?.setAttribute("hidden", "");
      accountNavigation.querySelectorAll("[data-footer-account-member]").forEach((link) => {
        link.hidden = !isActive;
      });
      accountNavigation.querySelectorAll("[data-footer-account-active]").forEach((link) => {
        link.hidden = !isActive;
      });
      const unavailableStatus = accountNavigation.querySelector("[data-footer-account-unavailable]");
      if (unavailableStatus) unavailableStatus.hidden = isActive;
      const reviewLink = accountNavigation.querySelector("[data-footer-account-review]");
      if (reviewLink) reviewLink.hidden = !canReview;
      const governanceLink = accountNavigation.querySelector("[data-footer-account-governance]");
      if (governanceLink) governanceLink.hidden = !canGovern;
      const auditLink = accountNavigation.querySelector("[data-footer-account-audit]");
      if (auditLink) auditLink.hidden = !canGovern;
      markCurrentLinks(footer);
    });

  }

  function renderHeaderIdentity(identity = {}) {
    if (identity.authenticated === true) {
      renderAccount({
        account: {
          roles: Array.isArray(identity.roles) ? identity.roles : [],
          account_status: identity.account_status || "",
        },
      });
      return;
    }

    const isAnonymous = identity.status === "anonymous";
    footers.forEach((footer) => {
      const accountNavigation = footer.querySelector("[data-footer-account-nav]");
      if (!accountNavigation) return;
      const signIn = accountNavigation.querySelector("[data-footer-account-sign-in]");
      if (signIn) signIn.hidden = !isAnonymous;
      const unavailable = accountNavigation.querySelector("[data-footer-account-unavailable]");
      if (unavailable) unavailable.hidden = isAnonymous;
      accountNavigation.querySelectorAll(
        "[data-footer-account-member], [data-footer-account-active], [data-footer-account-review], [data-footer-account-governance], [data-footer-account-audit]",
      ).forEach((link) => {
        link.hidden = true;
      });
      markCurrentLinks(footer);
    });
  }

  window.addEventListener("mt:account-loaded", (event) => renderAccount(event.detail || {}));
  window.addEventListener("mt:header-identity-change", (event) => renderHeaderIdentity(event.detail || {}));
})();
