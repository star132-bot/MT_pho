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
  let menuInvoker = null;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function initials(value) {
    const parts = cleanText(value || "MT").split(/\s+/).filter(Boolean);
    if (parts[0]?.toUpperCase() === "MT") return "MT";
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
  }

  function rolesFrom(value) {
    return Array.isArray(value) ? value.filter((role) => typeof role === "string") : [];
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
      email: cleanText(value.email),
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
      email: account.email || payload.user?.email,
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
      user: { display_name: identity.display_name, email: identity.email },
      account: {
        roles: identity.roles,
        account_status: identity.account_status,
        email: identity.email,
      },
      profile: {
        display_name: identity.display_name,
        avatar_url: identity.avatar_url || null,
      },
    };
  }

  function emitIdentity(identity, payload = null) {
    window.MTPresenceHeaderIdentity = identity;
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

    const profileLink = document.createElement("button");
    profileLink.className = "account-profile-link";
    profileLink.type = "button";
    profileLink.dataset.accountProfileLink = "";
    profileLink.setAttribute("aria-haspopup", "menu");
    profileLink.setAttribute("aria-expanded", "false");
    profileLink.setAttribute("aria-controls", "account-menu-actions");
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
    const avatarInitials = document.createElement("span");
    avatarInitials.dataset.accountMenuAvatarInitials = "";
    avatarInitials.setAttribute("aria-hidden", "true");
    avatar.append(avatarInitials);
    const identityCopy = document.createElement("span");
    identityCopy.className = "account-menu-identity-copy";
    const accountName = document.createElement("strong");
    accountName.dataset.accountMenuName = "";
    const accountEmail = document.createElement("span");
    accountEmail.dataset.accountMenuEmail = "";
    const accountStatus = document.createElement("em");
    accountStatus.dataset.accountMenuStatus = "";
    identityCopy.append(accountName, accountEmail, accountStatus);
    identity.append(avatar, identityCopy);

    const actions = document.createElement("div");
    actions.className = "account-menu-actions";
    actions.id = "account-menu-actions";
    actions.setAttribute("role", "menu");
    actions.setAttribute("aria-label", "Account");
    const links = document.createElement("nav");
    links.className = "account-menu-links";
    links.setAttribute("role", "none");
    links.append(
      destination("Dashboard", "/dashboard"),
      destination("Workspace", "/workspace/images"),
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
      profile: container.querySelector("[data-account-profile-link]"),
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
    elements.profile.setAttribute("aria-expanded", "false");
    if (restoreFocus) (menuInvoker || elements.trigger).focus();
    menuInvoker = null;
  }

  function openMenu(focus = "first", invoker = null) {
    const elements = menuElements();
    if (!elements) return;
    menuInvoker = invoker || menuInvoker || elements.trigger;
    elements.popover.hidden = false;
    elements.trigger.setAttribute("aria-expanded", "true");
    elements.profile.setAttribute("aria-expanded", "true");
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
    const profile = container.querySelector("[data-account-profile-link]");
    const popover = container.querySelector("[data-account-menu-popover]");
    const signout = container.querySelector("[data-account-menu-signout]");
    [profile, trigger].forEach((control) => {
      control.addEventListener("click", () => {
        if (popover.hidden) openMenu("first", control);
        else closeMenu(true);
      });
      control.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          openMenu(event.key === "ArrowUp" ? "last" : "first", control);
        }
      });
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
    const targets = [
      container.querySelector("[data-account-profile-link]"),
      container.querySelector("[data-account-menu-avatar]"),
    ].filter(Boolean);
    const generation = ++avatarGeneration;
    targets.forEach((target) => target.classList.remove("is-image-ready"));
    if (!url) {
      container.querySelectorAll("[data-account-menu-image]").forEach((image) => image.remove());
      return;
    }
    const images = targets.map((target) => {
      let image = target.querySelector("[data-account-menu-image]");
      if (!image) {
        image = document.createElement("img");
        image.alt = "";
        image.decoding = "async";
        image.dataset.accountMenuImage = "";
        target.append(image);
      }
      if (image.src !== url) image.src = url;
      return image;
    });
    try {
      await Promise.all(images.map(async (image) => {
        if (typeof image.decode === "function") await image.decode();
        else if (!image.complete || !image.naturalWidth) {
          await new Promise((resolve, reject) => {
            image.addEventListener("load", resolve, { once: true });
            image.addEventListener("error", reject, { once: true });
          });
        }
        if (!image.naturalWidth) throw new Error("Avatar image is unavailable.");
      }));
      if (generation !== avatarGeneration) return;
      targets.forEach((target) => target.classList.add("is-image-ready"));
      avatarRefreshAttempted = false;
    } catch (_error) {
      if (generation !== avatarGeneration) return;
      targets.forEach((target) => target.classList.remove("is-image-ready"));
      if (!avatarRefreshAttempted) {
        avatarRefreshAttempted = true;
        loadAccount({ preserveIdentity: true, refreshAvatar: true });
      }
    }
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
    container.querySelector("[data-account-menu-avatar-initials]").textContent = avatarText;
    container.querySelector("[data-account-menu-name]").textContent = displayName;
    container.querySelector("[data-account-menu-email]").textContent = identity.email;
    container.querySelector("[data-account-menu-status]").textContent = identity.account_status === "active"
      ? "Active account"
      : "Account access limited";
    container.querySelector("[data-account-profile-link]").setAttribute("aria-label", `Open account menu for ${displayName}`);
    markCurrentMenuLinks(container);
    bindAccountShell(container);
    currentIdentity = identity;
    currentPayload = payload;
    updateTopNavigation(identity);
    decodeAvatar(container, identity.avatar_url);
    emitIdentity(identity, payload);
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
        email: currentIdentity.email,
      },
      profile: {
        ...(currentPayload?.profile || {}),
        ...profile,
      },
    };
    renderAuthenticated(identityFromPayload(payload), payload);
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
