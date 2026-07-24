const notificationsRegion = document.querySelector("[data-notifications-region]");
const notificationsState = document.querySelector("[data-notifications-state]");
const notificationsList = document.querySelector("[data-notifications-list]");
const notificationsSummary = document.querySelector("[data-notifications-summary]");
const notificationsUnreadCount = document.querySelector("[data-notifications-unread-count]");
const notificationsMarkAll = document.querySelector("[data-notifications-mark-all]");
const notificationsRefresh = document.querySelector("[data-notifications-refresh]");
const notificationsPagination = document.querySelector("[data-notifications-pagination]");
const notificationsMore = document.querySelector("[data-notifications-more]");
const notificationsToast = document.querySelector("[data-notifications-toast]");
const notificationsLive = document.querySelector("[data-notifications-live]");
const notificationFilters = Array.from(document.querySelectorAll("[data-notifications-filter]"));

const NOTIFICATIONS_LIMIT = 30;
const NOTIFICATION_LABELS = {
  admin_session_revocation_requested: "Security",
  account_reactivated_by_admin: "Account",
  account_suspended_by_admin: "Account",
  image_approved: "Review",
  image_changes_requested: "Review",
  image_published: "Publication",
  image_rejected: "Review",
  image_restored_by_admin: "Publication",
  image_review_started: "Review",
  image_submitted: "Submission",
  image_taken_down: "Publication",
  image_unpublished_by_admin: "Publication",
  conversation_reply_received: "Inbox",
  role_granted_by_admin: "Account",
  role_revoked_by_admin: "Account",
  upload_failed: "Upload",
};
const NOTIFICATION_TITLES = {
  admin_session_revocation_requested: "Session review requested",
  account_reactivated_by_admin: "Account reactivated",
  account_suspended_by_admin: "Account suspended",
  image_approved: "Work approved",
  image_changes_requested: "Changes requested",
  image_published: "Work published",
  image_rejected: "Work not approved",
  image_restored_by_admin: "Work restored",
  image_review_started: "Review in progress",
  image_submitted: "Submitted for review",
  image_taken_down: "Work taken down",
  image_unpublished_by_admin: "Work removed from public view",
  conversation_reply_received: "New inbox reply",
  role_granted_by_admin: "Role granted",
  role_revoked_by_admin: "Role updated",
  upload_failed: "Upload failed",
};

let notifications = [];
let notificationsNextCursor = null;
let notificationsUnread = 0;
let notificationsFilter = "all";
let notificationsLoading = false;
let notificationsMutationBusy = false;
let notificationsController = null;
let notificationsRequestSerial = 0;
let notificationsCsrfPromise = null;
let notificationsToastTimer = null;

function notificationText(value, maxLength = 5000) {
  if (value === null || value === undefined) return "";
  return String(value).trim().slice(0, maxLength);
}

function notificationObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function notificationNumber(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) && result >= 0 ? result : fallback;
}

function notificationIcon(symbol) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ui-icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${symbol}`);
  svg.append(use);
  return svg;
}

function notificationDate(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function notificationMessage(type, explicitMessage) {
  if (explicitMessage) return explicitMessage;
  if (type === "image_review_started") return "Your submitted work is now being reviewed.";
  if (type === "image_approved") return "Your work passed review.";
  if (type === "image_published") return "Your work is now visible in the public Works archive.";
  if (type === "image_submitted") return "Your work was recorded in the review queue.";
  if (type === "image_restored_by_admin") return "Public visibility has been restored for this work.";
  if (type === "image_unpublished_by_admin" || type === "image_taken_down") {
    return "Public visibility changed after an administrative review.";
  }
  if (type === "account_suspended_by_admin") return "Access to this account has been restricted.";
  if (type === "account_reactivated_by_admin") return "Access to this account is active again.";
  if (type === "role_granted_by_admin") return "An operational role was added to your account.";
  if (type === "role_revoked_by_admin") return "An operational role was removed from your account.";
  if (type === "admin_session_revocation_requested") return "A request to revoke account sessions was recorded.";
  if (type === "conversation_reply_received") return "A reply was recorded in one of your inquiry conversations.";
  return "An update was recorded for your account.";
}

function normalizeNotification(value) {
  const raw = notificationObject(value?.notification || value);
  const id = notificationText(raw.id, 120);
  if (!id) return null;
  const type = notificationText(raw.type, 120) || "account_update";
  return {
    id,
    type,
    title: notificationText(raw.title, 240) || NOTIFICATION_TITLES[type] || "Account update",
    message: notificationMessage(type, notificationText(raw.message, 1200)),
    created_at: notificationText(raw.created_at, 80),
    read_at: notificationText(raw.read_at, 80),
    href: safeNotificationHref(raw.href),
  };
}

function safeNotificationHref(value) {
  const source = notificationText(value, 2000);
  if (!source.startsWith("/") || source.startsWith("//")) return "";
  try {
    const url = new URL(source, window.location.origin);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/") || url.pathname.startsWith("//")) return "";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch (_error) {
    return "";
  }
}

function announceNotification(message) {
  if (!notificationsLive) return;
  notificationsLive.textContent = "";
  window.setTimeout(() => { notificationsLive.textContent = message; }, 20);
}

function showNotificationToast(message, type = "success") {
  if (!notificationsToast) return;
  window.clearTimeout(notificationsToastTimer);
  notificationsToast.textContent = message;
  notificationsToast.dataset.type = type;
  notificationsToast.classList.add("is-visible");
  notificationsToastTimer = window.setTimeout(() => notificationsToast.classList.remove("is-visible"), 3600);
}

function setNotificationsState(tone, title, message = "", action = null) {
  notificationsState.dataset.tone = tone;
  notificationsState.replaceChildren();
  if (tone === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "communications-spinner";
    spinner.setAttribute("aria-hidden", "true");
    notificationsState.append(spinner);
  } else if (tone === "error") {
    notificationsState.append(notificationIcon("icon-alert"));
  } else {
    notificationsState.append(notificationIcon("icon-bell"));
  }
  const copy = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  copy.append(heading);
  if (message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    copy.append(paragraph);
  }
  notificationsState.append(copy);
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", action.handler, { once: true });
    notificationsState.append(button);
  }
  notificationsState.hidden = false;
}

async function notificationsCsrfToken(force = false) {
  if (force) notificationsCsrfPromise = null;
  if (!notificationsCsrfPromise) {
    const request = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
      return payload.csrf_token;
    });
    notificationsCsrfPromise = request;
    request.catch(() => {
      if (notificationsCsrfPromise === request) notificationsCsrfPromise = null;
    });
  }
  return notificationsCsrfPromise;
}

async function notificationsRequest(path, options = {}, retryCsrf = true) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (!new Set(["GET", "HEAD"]).has(method)) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = await notificationsCsrfToken();
  }
  const response = await fetch(path, {
    ...options,
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await notificationsCsrfToken(true);
    return notificationsRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(payload.error?.message || "The notification request failed.");
    error.status = response.status;
    error.code = payload.error?.code || "NOTIFICATIONS_REQUEST_FAILED";
    throw error;
  }
  return payload;
}

function handleNotificationsBoundary(error) {
  const nextPath = `${window.location.pathname}${window.location.search}`;
  if (error?.status === 401) {
    window.location.assign(`/auth/sign-in?next=${encodeURIComponent(nextPath)}`);
    return true;
  }
  return false;
}

function dispatchUnreadCount() {
  const unreadCount = Math.max(0, Math.trunc(notificationsUnread));
  window.dispatchEvent(new CustomEvent("mt:notifications-updated", { detail: { unread_count: unreadCount } }));
}

function updateNotificationControls() {
  const unreadCount = Math.max(0, Math.trunc(notificationsUnread));
  notificationsUnreadCount.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
  notificationsMarkAll.disabled = notificationsLoading || notificationsMutationBusy || unreadCount === 0;
  notificationsRefresh.disabled = notificationsLoading || notificationsMutationBusy;
  notificationFilters.forEach((button) => {
    const selected = button.dataset.notificationsFilter === notificationsFilter;
    button.setAttribute("aria-pressed", String(selected));
    button.disabled = notificationsLoading || notificationsMutationBusy;
  });
  dispatchUnreadCount();
}

function createNotificationItem(item) {
  const row = document.createElement("li");
  row.className = "notifications-item";
  row.dataset.notificationId = item.id;
  row.dataset.read = String(Boolean(item.read_at));

  const marker = document.createElement("span");
  marker.className = "notifications-item-marker";
  marker.append(notificationIcon(item.read_at ? "icon-check" : "icon-bell"));

  const content = document.createElement("div");
  content.className = "notifications-item-content";
  const heading = document.createElement("div");
  heading.className = "notifications-item-heading";
  const title = document.createElement("strong");
  title.textContent = item.title;
  const time = document.createElement("time");
  time.dateTime = item.created_at;
  time.textContent = notificationDate(item.created_at);
  heading.append(title, time);
  const message = document.createElement("p");
  message.textContent = item.message;
  const footer = document.createElement("div");
  footer.className = "notifications-item-footer";
  const label = document.createElement("span");
  label.textContent = NOTIFICATION_LABELS[item.type] || "Account";
  footer.append(label);
  if (item.href) {
    const link = document.createElement("a");
    link.href = item.href;
    link.textContent = "Open update";
    link.append(notificationIcon("icon-arrow-right"));
    footer.append(link);
  }
  content.append(heading, message, footer);
  row.append(marker, content);

  if (!item.read_at) {
    const readButton = document.createElement("button");
    readButton.className = "notifications-read-button";
    readButton.type = "button";
    readButton.dataset.notificationRead = item.id;
    readButton.setAttribute("aria-label", `Mark ${item.title} as read`);
    readButton.title = "Mark as read";
    readButton.append(notificationIcon("icon-check"));
    row.append(readButton);
  }
  return row;
}

function renderNotifications() {
  const visible = notifications.filter((item) => notificationsFilter === "all" || !item.read_at);
  notificationsList.replaceChildren(...visible.map(createNotificationItem));
  notificationsList.hidden = visible.length === 0;
  notificationsPagination.hidden = !notificationsNextCursor;
  notificationsMore.disabled = notificationsLoading || notificationsMutationBusy;
  if (visible.length === 0 && !notificationsLoading) {
    const isUnread = notificationsFilter === "unread";
    setNotificationsState(
      "empty",
      isUnread ? "No unread notifications" : "No notifications yet",
      isUnread ? "New account and work updates will appear here." : "Updates will appear here when activity is recorded.",
    );
  } else if (visible.length > 0) {
    notificationsState.hidden = true;
  }
  const noun = notifications.length === 1 ? "notification" : "notifications";
  notificationsSummary.textContent = `${notifications.length} ${noun}`;
  updateNotificationControls();
}

async function loadNotifications({ append = false } = {}) {
  if (notificationsLoading || (append && !notificationsNextCursor)) return;
  notificationsLoading = true;
  const requestId = ++notificationsRequestSerial;
  if (!append) {
    notificationsController?.abort();
    notificationsController = new AbortController();
    notificationsRegion.setAttribute("aria-busy", "true");
    setNotificationsState("loading", "Loading notifications...");
    notificationsList.hidden = true;
  }
  updateNotificationControls();
  try {
    const params = new URLSearchParams({ limit: String(NOTIFICATIONS_LIMIT) });
    if (append && notificationsNextCursor) {
      params.set("before", notificationsNextCursor.before);
      params.set("before_id", notificationsNextCursor.before_id);
    }
    const payload = await notificationsRequest(`/api/notifications?${params.toString()}`, {
      signal: notificationsController?.signal,
    });
    if (requestId !== notificationsRequestSerial) return;
    const nextItems = Array.isArray(payload.items) ? payload.items.map(normalizeNotification).filter(Boolean) : [];
    const merged = append ? [...notifications, ...nextItems] : nextItems;
    notifications = Array.from(new Map(merged.map((item) => [item.id, item])).values());
    const rawCursor = notificationObject(payload.next_cursor || payload.pagination?.next_cursor);
    const before = notificationText(rawCursor.before || rawCursor.created_at, 80);
    const beforeId = notificationText(rawCursor.before_id || rawCursor.id, 120);
    notificationsNextCursor = before && beforeId ? { before, before_id: beforeId } : null;
    notificationsUnread = notificationNumber(payload.unread_count, notifications.filter((item) => !item.read_at).length);
    renderNotifications();
  } catch (error) {
    if (error?.name === "AbortError" || requestId !== notificationsRequestSerial) return;
    if (handleNotificationsBoundary(error)) return;
    if (!append) {
      notifications = [];
      notificationsNextCursor = null;
      notificationsList.replaceChildren();
      notificationsList.hidden = true;
    }
    setNotificationsState(
      error?.status === 403 ? "permission" : "error",
      error?.status === 403 ? "Notifications unavailable" : "Notifications could not be loaded",
      error.message || "Try the request again.",
      { label: "Retry", handler: () => loadNotifications() },
    );
  } finally {
    if (requestId === notificationsRequestSerial) {
      notificationsLoading = false;
      notificationsRegion.setAttribute("aria-busy", "false");
      updateNotificationControls();
    }
  }
}

async function markNotificationsRead(notificationId = "") {
  if (notificationsMutationBusy) return;
  const markAll = !notificationId;
  notificationsMutationBusy = true;
  updateNotificationControls();
  const affectedButton = notificationId
    ? notificationsList.querySelector(`[data-notification-read="${CSS.escape(notificationId)}"]`)
    : notificationsMarkAll;
  affectedButton?.setAttribute("aria-busy", "true");
  try {
    const payload = await notificationsRequest("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify(markAll ? { all: true } : { notification_id: notificationId }),
    });
    const readAt = notificationText(payload.read_at, 80) || new Date().toISOString();
    notifications = notifications.map((item) => (
      markAll || item.id === notificationId ? { ...item, read_at: item.read_at || readAt } : item
    ));
    notificationsUnread = notificationNumber(payload.unread_count, notifications.filter((item) => !item.read_at).length);
    renderNotifications();
    const message = markAll ? "All notifications marked as read." : "Notification marked as read.";
    showNotificationToast(message);
    announceNotification(message);
  } catch (error) {
    if (!handleNotificationsBoundary(error)) {
      showNotificationToast(error.message || "The notification could not be updated.", "error");
    }
  } finally {
    notificationsMutationBusy = false;
    affectedButton?.removeAttribute("aria-busy");
    updateNotificationControls();
  }
}

notificationFilters.forEach((button) => {
  button.addEventListener("click", () => {
    const nextFilter = button.dataset.notificationsFilter;
    if (!new Set(["all", "unread"]).has(nextFilter) || nextFilter === notificationsFilter) return;
    notificationsFilter = nextFilter;
    renderNotifications();
  });
});

notificationsList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-notification-read]");
  if (!button) return;
  markNotificationsRead(button.dataset.notificationRead);
});
notificationsMarkAll?.addEventListener("click", () => markNotificationsRead());
notificationsRefresh?.addEventListener("click", () => loadNotifications());
notificationsMore?.addEventListener("click", () => loadNotifications({ append: true }));

loadNotifications();
