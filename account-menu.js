(function initializeHeaderIdentity() {
  const header = document.querySelector(".site-header");
  const slot = header?.querySelector("[data-header-identity-slot]");
  if (!header || !slot) return;

  const isPublicHeader = header.hasAttribute("data-public-header");
  const bootstrapElement = document.querySelector("#mt-header-identity");
  let currentIdentity = null;
  let currentPayload = null;
  let accountRequest = null;
  let csrfPromise = null;
  let signoutBusy = false;
  let avatarGeneration = 0;
  let avatarRefreshAttempted = false;
  let notificationCountRequest = null;
  let notificationCountGeneration = 0;
  let notificationUnreadCount = null;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function initials(value) {
    const parts = cleanText(value || "MT").split(/\s+/).filter(Boolean);
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
  }

  function rolesFrom(value) {
    return Array.isArray(value) ? value.filter((role) => typeof role === "string") : [];
  }

  function roleLabel(roles) {
    if (roles.includes("super_admin")) return "Super Admin";
    if (roles.includes("admin")) return "Administrator";
    if (roles.includes("reviewer")) return "Reviewer";
    return "Member";
  }

  function safeAvatarUrl(value) {
    const source = cleanText(value);
    if (!source) return "";
    try {
      const url = new URL(source, window.location.origin);
      const loopback = url.protocol === "http:"
        && new Set(["localhost", "127.0.0.1", "[::1]"]).has(url.hostname);
      return url.protocol === "https:" || loopback ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function normalizeIdentity(value = {}) {
    const authenticated = value.authenticated === true;
    const roles = rolesFrom(value.roles);
    const accountStatus = cleanText(value.account_status);
    const active = accountStatus === "active";
    const displayName = cleanText(value.display_name) || (authenticated ? "Member" : "");
    return {
      authenticated,
      status: cleanText(value.status) || (authenticated ? "authenticated" : "pending"),
      display_name: displayName,
      initials: cleanText(value.initials) || (authenticated ? initials(displayName) : ""),
      avatar_url: safeAvatarUrl(value.avatar_url),
      roles,
      can_review: value.can_review === true || (active && roles.some((role) => ["reviewer", "admin", "super_admin"].includes(role))),
      can_govern: value.can_govern === true || (active && roles.some((role) => ["admin", "super_admin"].includes(role))),
      can_manage_users: value.can_manage_users === true || (active && roles.some((role) => ["admin", "super_admin"].includes(role))),
      account_status: accountStatus,
    };
  }

  function identityFromPayload(payload = {}) {
    const profile = payload.profile || {};
    const account = payload.account || {};
    const roles = rolesFrom(account.roles);
    const accountStatus = cleanText(account.account_status);
    const active = accountStatus === "active";
    const displayName = cleanText(profile.display_name || payload.user?.display_name) || "Member";
    return normalizeIdentity({
      authenticated: true,
      status: "authenticated",
      display_name: displayName,
      initials: initials(displayName),
      avatar_url: profile.avatar_url,
      roles,
      can_review: active && roles.some((role) => ["reviewer", "admin", "super_admin"].includes(role)),
      can_govern: active && roles.some((role) => ["admin", "super_admin"].includes(role)),
      can_manage_users: active && roles.some((role) => ["admin", "super_admin"].includes(role)),
      account_status: accountStatus,
    });
  }

  function bootstrapIdentity() {
    try {
      return normalizeIdentity(JSON.parse(bootstrapElement?.content?.textContent || bootstrapElement?.textContent || "{}"));
    } catch (_error) {
      return normalizeIdentity({ status: "pending" });
    }
  }

  function accountEventPayload(identity, payload = null) {
    if (payload && typeof payload === "object") return payload;
    return {
      user: { display_name: identity.display_name },
      account: {
        roles: identity.roles,
        account_status: identity.account_status,
      },
      profile: {
        display_name: identity.display_name,
        avatar_url: identity.avatar_url || null,
      },
    };
  }

  function emitIdentity(identity, payload = null) {
    window.dispatchEvent(new CustomEvent("mt:header-identity-change", { detail: identity }));
    if (identity.authenticated) {
      window.dispatchEvent(new CustomEvent("mt:account-loaded", { detail: accountEventPayload(identity, payload) }));
    }
  }

  function destination(label, href) {
    const link = document.createElement("a");
    link.href = href;
    link.setAttribute("role", "menuitem");
    link.textContent = label;
    return link;
  }

  function createAccountShell() {
    const container = document.createElement("div");
    container.className = "account-menu";
    container.dataset.accountMenu = "";

    const profileLink = document.createElement("a");
    profileLink.className = "account-profile-link";
    profileLink.href = "/dashboard";
    profileLink.dataset.accountProfileLink = "";
    const profileInitials = document.createElement("span");
    profileInitials.dataset.accountMenuInitials = "";
    profileInitials.setAttribute("aria-hidden", "true");
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
    const avatar = document.createElement("a");
    avatar.className = "account-menu-avatar";
    avatar.href = "/dashboard";
    avatar.dataset.accountMenuAvatar = "";
    avatar.setAttribute("aria-label", "Open personal profile");
    const identityCopy = document.createElement("span");
    const accountName = document.createElement("strong");
    accountName.dataset.accountMenuName = "";
    const accountRole = document.createElement("em");
    accountRole.dataset.accountMenuRole = "";
    identityCopy.append(accountName, accountRole);
    identity.append(avatar, identityCopy);

    const actions = document.createElement("div");
    actions.className = "account-menu-actions";
    actions.id = "account-menu-actions";
    actions.setAttribute("role", "menu");
    actions.setAttribute("aria-label", "Account");
    const links = document.createElement("nav");
    links.className = "account-menu-links";
    links.setAttribute("role", "none");
    const notificationsLink = destination("Notifications", "/workspace/notifications");
    notificationsLink.dataset.accountMenuNotifications = "";
    const notificationBadge = document.createElement("span");
    notificationBadge.className = "account-menu-notification-badge";
    notificationBadge.dataset.accountMenuNotificationBadge = "";
    notificationBadge.setAttribute("aria-hidden", "true");
    notificationBadge.hidden = true;
    notificationsLink.append(notificationBadge);
    links.append(
      destination("Dashboard", "/dashboard"),
      destination("Workspace", "/workspace/images"),
      notificationsLink,
      destination("Inbox", "/inbox"),
      destination("Account Settings", "/settings/account"),
    );
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
    return container;
  }

  function currentPath() {
    return window.location.pathname.replace(/\/$/, "") || "/";
  }

  function markCurrentMenuLinks(container) {
    const path = currentPath();
    container.querySelectorAll("a[role='menuitem']").forEach((link) => {
      const linkPath = new URL(link.href).pathname.replace(/\/$/, "") || "/";
      if (linkPath === path) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function updateTopNavigation(identity) {
    const path = currentPath();
    document.querySelectorAll("[data-review-nav]").forEach((link) => {
      link.hidden = !identity.can_review;
      if (path === "/admin/reviews" || path.startsWith("/admin/reviews/")) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-governance-nav]").forEach((link) => {
      link.hidden = !identity.can_govern;
      if (path === "/admin/works" || path.startsWith("/admin/works/")) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-users-nav]").forEach((link) => {
      link.hidden = !identity.can_manage_users;
      if (path === "/admin/users" || path.startsWith("/admin/users/")) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function menuElements() {
    const container = slot.querySelector("[data-account-menu]");
    if (!container) return null;
    return {
      container,
      trigger: container.querySelector("[data-account-menu-trigger]"),
      popover: container.querySelector("[data-account-menu-popover]"),
      signout: container.querySelector("[data-account-menu-signout]"),
      error: container.querySelector("[data-account-menu-error]"),
    };
  }

  function menuItems(elements) {
    return Array.from(elements.popover.querySelectorAll('[role="menuitem"]')).filter((item) => !item.hidden && !item.disabled);
  }

  function closeMenu(restoreFocus = false) {
    const elements = menuElements();
    if (!elements || elements.popover.hidden) return;
    elements.popover.hidden = true;
    elements.trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) elements.trigger.focus();
  }

  function openMenu(focus = "first") {
    const elements = menuElements();
    if (!elements) return;
    elements.popover.hidden = false;
    elements.trigger.setAttribute("aria-expanded", "true");
    const items = menuItems(elements);
    if (focus === "first") items[0]?.focus();
    if (focus === "last") items.at(-1)?.focus();
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
    const elements = menuElements();
    if (!elements || signoutBusy) return;
    signoutBusy = true;
    elements.signout.disabled = true;
    elements.signout.textContent = "Signing out...";
    elements.error.hidden = true;
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
      elements.error.textContent = error.message || "Sign out failed. Try again.";
      elements.error.hidden = false;
      signoutBusy = false;
      elements.signout.disabled = false;
      elements.signout.textContent = "Sign out";
      elements.error.focus?.();
    }
  }

  function bindAccountShell(container) {
    if (container.dataset.accountMenuBound === "true") return;
    container.dataset.accountMenuBound = "true";
    const trigger = container.querySelector("[data-account-menu-trigger]");
    const popover = container.querySelector("[data-account-menu-popover]");
    const signout = container.querySelector("[data-account-menu-signout]");
    trigger.addEventListener("click", () => {
      if (popover.hidden) openMenu();
      else closeMenu(true);
    });
    trigger.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openMenu(event.key === "ArrowUp" ? "last" : "first");
      }
    });
    popover.addEventListener("keydown", (event) => {
      const elements = menuElements();
      if (!elements) return;
      const items = menuItems(elements);
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
    container.addEventListener("focusout", () => {
      window.setTimeout(() => {
        const elements = menuElements();
        if (elements && !elements.popover.hidden && !elements.container.contains(document.activeElement)) closeMenu(false);
      }, 0);
    });
  }

  async function decodeAvatar(container, value) {
    const url = safeAvatarUrl(value);
    const profileLink = container.querySelector("[data-account-profile-link]");
    let image = container.querySelector("[data-account-menu-image]");
    const generation = ++avatarGeneration;
    profileLink.classList.remove("is-image-ready");
    if (!url) {
      image?.remove();
      return;
    }
    if (!image) {
      image = document.createElement("img");
      image.alt = "";
      image.decoding = "async";
      image.dataset.accountMenuImage = "";
      profileLink.append(image);
    }
    if (image.src !== url) image.src = url;
    try {
      if (typeof image.decode === "function") await image.decode();
      else if (!image.complete || !image.naturalWidth) {
        await new Promise((resolve, reject) => {
          image.addEventListener("load", resolve, { once: true });
          image.addEventListener("error", reject, { once: true });
        });
      }
      if (generation !== avatarGeneration || !image.naturalWidth) return;
      profileLink.classList.add("is-image-ready");
      avatarRefreshAttempted = false;
    } catch (_error) {
      if (generation !== avatarGeneration) return;
      profileLink.classList.remove("is-image-ready");
      if (!avatarRefreshAttempted) {
        avatarRefreshAttempted = true;
        loadAccount({ preserveIdentity: true, refreshAvatar: true });
      }
    }
  }

  function updateNotificationBadge() {
    const link = slot.querySelector("[data-account-menu-notifications]");
    const badge = slot.querySelector("[data-account-menu-notification-badge]");
    if (!link || !badge) return;
    const count = Number(notificationUnreadCount);
    const available = Number.isFinite(count) && count > 0;
    badge.hidden = !available;
    badge.textContent = available ? (count > 99 ? "99+" : String(Math.trunc(count))) : "";
    link.setAttribute("aria-label", available
      ? `Notifications, ${Math.trunc(count)} unread`
      : "Notifications");
  }

  async function loadNotificationCount() {
    if (!currentIdentity?.authenticated) return null;
    if (notificationCountRequest) return notificationCountRequest;
    const generation = ++notificationCountGeneration;
    notificationCountRequest = (async () => {
      try {
        const response = await fetch("/api/notifications/unread-count", {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error("Notification count is unavailable.");
        if (generation !== notificationCountGeneration || !currentIdentity?.authenticated) return null;
        const count = Number(payload.unread_count);
        notificationUnreadCount = Number.isFinite(count) && count >= 0 ? Math.trunc(count) : null;
        updateNotificationBadge();
        return notificationUnreadCount;
      } catch (_error) {
        if (generation === notificationCountGeneration) {
          notificationUnreadCount = null;
          updateNotificationBadge();
        }
        return null;
      } finally {
        notificationCountRequest = null;
      }
    })();
    return notificationCountRequest;
  }

  function renderAuthenticated(identity, payload = null) {
    let container = slot.querySelector("[data-account-menu]");
    if (!container) {
      container = createAccountShell();
      slot.replaceChildren(container);
    }
    const displayName = identity.display_name || "Member";
    const avatarText = identity.initials || initials(displayName);
    container.querySelector("[data-account-menu-initials]").textContent = avatarText;
    container.querySelector("[data-account-menu-avatar]").textContent = avatarText;
    container.querySelector("[data-account-menu-name]").textContent = displayName;
    container.querySelector("[data-account-menu-role]").textContent = roleLabel(identity.roles);
    container.querySelector("[data-account-profile-link]").setAttribute("aria-label", `Open personal profile for ${displayName}`);
    markCurrentMenuLinks(container);
    bindAccountShell(container);
    currentIdentity = identity;
    currentPayload = payload;
    updateTopNavigation(identity);
    decodeAvatar(container, identity.avatar_url);
    emitIdentity(identity, payload);
    updateNotificationBadge();
    loadNotificationCount();
  }

  function renderAnonymous() {
    const link = document.createElement("a");
    link.className = "home-account-entry";
    link.href = "/auth/sign-in";
    link.dataset.publicSignIn = "";
    link.textContent = "Sign In";
    slot.replaceChildren(link);
    currentIdentity = normalizeIdentity({ status: "anonymous" });
    currentPayload = null;
    notificationCountGeneration += 1;
    notificationUnreadCount = null;
    updateTopNavigation(currentIdentity);
    emitIdentity(currentIdentity);
  }

  function renderUnavailable() {
    if (currentIdentity?.authenticated) return;
    const fallback = document.createElement("span");
    fallback.className = "header-identity-unavailable";
    fallback.setAttribute("aria-label", "Account identity is temporarily unavailable");
    fallback.textContent = "MT";
    slot.replaceChildren(fallback);
    currentIdentity = normalizeIdentity({ status: "unavailable" });
    notificationCountGeneration += 1;
    notificationUnreadCount = null;
    updateTopNavigation(currentIdentity);
    emitIdentity(currentIdentity);
  }

  async function loadAccount({ preserveIdentity = false, refreshAvatar = false } = {}) {
    if (accountRequest) return accountRequest;
    accountRequest = (async () => {
      try {
        const params = new URLSearchParams({ header_identity: "1" });
        if (refreshAvatar) params.set("refresh_avatar", "1");
        const response = await fetch(`/api/me?${params.toString()}`, {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const error = new Error(payload.error?.message || "Account details are unavailable.");
          error.status = response.status;
          throw error;
        }
        const identity = identityFromPayload(payload);
        renderAuthenticated(identity, payload);
        return identity;
      } catch (error) {
        if (error.status === 401) {
          if (isPublicHeader) renderAnonymous();
          else {
            const target = `${window.location.pathname}${window.location.search}`;
            window.location.assign(`/auth/sign-in?next=${encodeURIComponent(target)}`);
          }
        } else if (!preserveIdentity || !currentIdentity?.authenticated) {
          renderUnavailable();
        }
        return null;
      } finally {
        accountRequest = null;
      }
    })();
    return accountRequest;
  }

  document.addEventListener("pointerdown", (event) => {
    const elements = menuElements();
    if (elements && !elements.popover.hidden && !elements.container.contains(event.target)) closeMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    const elements = menuElements();
    if (event.key === "Escape" && elements && !elements.popover.hidden) {
      event.preventDefault();
      closeMenu(true);
    }
  });
  window.addEventListener("mt:profile-committed", (event) => {
    if (!currentIdentity?.authenticated) {
      loadAccount({ preserveIdentity: true });
      return;
    }
    const detail = event.detail && typeof event.detail === "object" ? event.detail : {};
    const profile = detail.profile && typeof detail.profile === "object" ? detail.profile : {};
    const payload = {
      user: currentPayload?.user || {},
      account: {
        ...(currentPayload?.account || {}),
        roles: currentIdentity.roles,
        account_status: currentIdentity.account_status,
      },
      profile: {
        ...(currentPayload?.profile || {}),
        ...profile,
      },
    };
    renderAuthenticated(identityFromPayload(payload), payload);
  });
  window.addEventListener("mt:notifications-updated", (event) => {
    const count = Number(event.detail?.unread_count);
    if (!currentIdentity?.authenticated || !Number.isFinite(count) || count < 0) return;
    notificationUnreadCount = Math.trunc(count);
    updateNotificationBadge();
  });

  const bootstrap = bootstrapIdentity();
  if (bootstrap.authenticated) {
    renderAuthenticated(bootstrap);
    if (bootstrap.status !== "authenticated") loadAccount({ preserveIdentity: true });
  }
  else if (bootstrap.status === "anonymous") renderAnonymous();
  else {
    renderUnavailable();
    loadAccount();
  }
})();
