(function initializeAccountMenu() {
  const header = document.querySelector(".site-header");
  if (!header || header.querySelector("[data-account-menu]")) return;

  const container = document.createElement("div");
  container.className = "account-menu";
  container.dataset.accountMenu = "";
  const profileLink = document.createElement("a");
  profileLink.className = "account-profile-link";
  profileLink.href = "/dashboard";
  profileLink.dataset.accountProfileLink = "";
  profileLink.setAttribute("aria-label", "Open personal profile");
  const profileInitials = document.createElement("span");
  profileInitials.dataset.accountMenuInitials = "";
  profileInitials.setAttribute("aria-hidden", "true");
  profileInitials.textContent = "MT";
  profileLink.append(profileInitials);
  const trigger = document.createElement("button");
  trigger.className = "account-menu-trigger";
  trigger.type = "button";
  trigger.dataset.accountMenuTrigger = "";
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-controls", "account-menu-actions");
  trigger.setAttribute("aria-label", "Open account menu");
  trigger.title = "Account menu";
  const triggerIcon = document.createElement("span");
  triggerIcon.className = "account-menu-trigger-icon";
  triggerIcon.setAttribute("aria-hidden", "true");
  triggerIcon.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
  trigger.append(triggerIcon);

  const popover = document.createElement("div");
  popover.className = "account-menu-popover";
  popover.dataset.accountMenuPopover = "";
  popover.hidden = true;
  const identity = document.createElement("div");
  identity.className = "account-menu-identity";
  identity.setAttribute("aria-live", "polite");
  const avatar = document.createElement("a");
  avatar.className = "account-menu-avatar";
  avatar.href = "/dashboard";
  avatar.dataset.accountMenuAvatar = "";
  avatar.setAttribute("aria-label", "Open personal profile");
  avatar.textContent = "MT";
  const identityCopy = document.createElement("span");
  const accountName = document.createElement("strong");
  accountName.dataset.accountMenuName = "";
  accountName.textContent = "Loading account";
  const accountEmail = document.createElement("small");
  accountEmail.dataset.accountMenuEmail = "";
  const accountRoleLabel = document.createElement("em");
  accountRoleLabel.dataset.accountMenuRole = "";
  accountRoleLabel.textContent = "Member";
  identityCopy.append(accountName, accountEmail, accountRoleLabel);
  identity.append(avatar, identityCopy);

  const actions = document.createElement("div");
  actions.className = "account-menu-actions";
  actions.id = "account-menu-actions";
  actions.setAttribute("role", "menu");
  actions.setAttribute("aria-label", "Account");
  const links = document.createElement("nav");
  links.className = "account-menu-links";
  links.setAttribute("role", "none");
  function destination(label, href) {
    const link = document.createElement("a");
    link.href = href;
    link.setAttribute("role", "menuitem");
    link.textContent = label;
    return link;
  }
  links.append(
    destination("Dashboard", "/dashboard"),
    destination("Workspace", "/workspace/images"),
    destination("Account Settings", "/settings/account"),
  );
  const reviewLink = destination("Review", "/admin/reviews");
  reviewLink.dataset.accountMenuReview = "";
  reviewLink.hidden = true;
  links.append(reviewLink);
  const signout = document.createElement("button");
  signout.className = "account-menu-signout";
  signout.type = "button";
  signout.dataset.accountMenuSignout = "";
  signout.setAttribute("role", "menuitem");
  signout.textContent = "Sign out";
  actions.append(links, signout);
  const errorElement = document.createElement("p");
  errorElement.className = "account-menu-error";
  errorElement.dataset.accountMenuError = "";
  errorElement.hidden = true;
  errorElement.tabIndex = -1;
  errorElement.setAttribute("role", "alert");
  popover.append(identity, actions, errorElement);
  container.append(profileLink, trigger, popover);
  header.append(container);

  let csrfPromise = null;
  let signoutBusy = false;

  function initials(value) {
    const parts = String(value || "MT").trim().split(/\s+/).filter(Boolean);
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
  }

  function menuItems() {
    return Array.from(popover.querySelectorAll('[role="menuitem"]')).filter((item) => !item.hidden && !item.disabled);
  }

  function closeMenu(restoreFocus = false) {
    if (popover.hidden) return;
    popover.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  function openMenu(focus = "first") {
    popover.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    const items = menuItems();
    if (focus === "first") items[0]?.focus();
    if (focus === "last") items.at(-1)?.focus();
  }

  function toggleMenu() {
    if (popover.hidden) openMenu();
    else closeMenu(true);
  }

  function accountRole(roles) {
    if (roles.includes("super_admin")) return "Super Admin";
    if (roles.includes("admin")) return "Administrator";
    if (roles.includes("reviewer")) return "Reviewer";
    return "Member";
  }

  function renderAccount(payload) {
    const profile = payload.profile || {};
    const account = payload.account || {};
    const displayName = profile.display_name || payload.user?.display_name || "Member";
    const avatarText = initials(displayName);
    const roles = Array.isArray(account.roles) ? account.roles : [];
    container.querySelector("[data-account-menu-initials]").textContent = avatarText;
    container.querySelector("[data-account-menu-avatar]").textContent = avatarText;
    container.querySelector("[data-account-menu-name]").textContent = displayName;
    container.querySelector("[data-account-menu-email]").textContent = account.email || payload.user?.email || "";
    container.querySelector("[data-account-menu-role]").textContent = `${accountRole(roles)} / ${account.email_verified ? "Verified" : "Verification pending"}`;
    const canReview = roles.some((role) => ["reviewer", "admin", "super_admin"].includes(role));
    reviewLink.hidden = !canReview;
    document.querySelectorAll("[data-admin-only]").forEach((link) => { link.hidden = !canReview; });
    const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
    container.querySelectorAll("a[role='menuitem']").forEach((link) => {
      const linkPath = new URL(link.href).pathname.replace(/\/$/, "") || "/";
      if (linkPath === currentPath) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    window.dispatchEvent(new CustomEvent("mt:account-loaded", { detail: payload }));
  }

  async function loadAccount() {
    try {
      const response = await fetch("/api/me", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error?.message || "Account details are unavailable.");
      renderAccount(payload);
    } catch (_error) {
      container.querySelector("[data-account-menu-name]").textContent = "Account";
      container.querySelector("[data-account-menu-role]").textContent = "Identity unavailable";
    }
  }

  async function csrfToken(force = false) {
    if (force) csrfPromise = null;
    if (!csrfPromise) {
      csrfPromise = fetch("/api/auth/csrf", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      }).then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
        return payload.csrf_token;
      }).catch((error) => {
        csrfPromise = null;
        throw error;
      });
    }
    return csrfPromise;
  }

  async function signOut(retry = true) {
    if (signoutBusy) return;
    signoutBusy = true;
    signout.disabled = true;
    signout.textContent = "Signing out...";
    errorElement.hidden = true;
    try {
      const response = await fetch("/api/auth/sign-out", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": await csrfToken(),
        },
        body: JSON.stringify({}),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retry) {
        signoutBusy = false;
        await csrfToken(true);
        return signOut(false);
      }
      if (!response.ok) throw new Error(payload.error?.message || "Sign out failed. Try again.");
      window.location.assign("/");
    } catch (error) {
      errorElement.textContent = error.message || "Sign out failed. Try again.";
      errorElement.hidden = false;
      signoutBusy = false;
      signout.disabled = false;
      signout.textContent = "Sign out";
      errorElement.focus?.();
    }
  }

  trigger.addEventListener("click", toggleMenu);
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(event.key === "ArrowUp" ? "last" : "first");
    }
  });
  popover.addEventListener("keydown", (event) => {
    const items = menuItems();
    const index = items.indexOf(document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !items.length) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : index < 0
          ? (event.key === "ArrowDown" ? 0 : items.length - 1)
          : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[nextIndex].focus();
  });
  popover.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu(false);
  });
  signout.addEventListener("click", () => signOut());
  document.addEventListener("pointerdown", (event) => {
    if (!popover.hidden && !container.contains(event.target)) closeMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !popover.hidden) {
      event.preventDefault();
      closeMenu(true);
    }
  });
  container.addEventListener("focusout", () => {
    window.setTimeout(() => {
      if (!popover.hidden && !container.contains(document.activeElement)) closeMenu(false);
    }, 0);
  });

  loadAccount();
})();
