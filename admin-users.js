const usersList = document.querySelector("[data-users-list]");
const listState = document.querySelector("[data-users-list-state]");
const listStateMessage = document.querySelector("[data-users-list-state-message]");
const listRetryButton = document.querySelector("[data-users-list-retry]");
const listCount = document.querySelector("[data-users-list-count]");
const rangeLabel = document.querySelector("[data-users-range]");
const loadMoreButton = document.querySelector("[data-users-load-more]");
const inventoryRegion = document.querySelector("[data-users-inventory]");
const workspace = document.querySelector("[data-users-workspace]");
const filterForm = document.querySelector("[data-users-filters]");
const searchInput = filterForm.elements.q;
const roleSelect = filterForm.elements.role;
const sortSelect = filterForm.elements.sort;
const clearButton = document.querySelector("[data-users-clear]");
const filterSummary = document.querySelector("[data-users-filter-summary]");
const refreshButton = document.querySelector("[data-users-refresh]");
const detailRegion = document.querySelector("[data-users-detail-region]");
const detailState = document.querySelector("[data-users-detail-state]");
const detailStateTitle = document.querySelector("[data-users-detail-state-title]");
const detailStateMessage = document.querySelector("[data-users-detail-state-message]");
const detailRetryButton = document.querySelector("[data-users-detail-retry]");
const detailElement = document.querySelector("[data-users-detail]");
const detailAvatar = document.querySelector("[data-users-avatar]");
const detailStatus = document.querySelector("[data-users-status]");
const detailVersion = document.querySelector("[data-users-version]");
const detailName = document.querySelector("[data-users-name]");
const detailEmail = document.querySelector("[data-users-email]");
const identityList = document.querySelector("[data-users-identity]");
const securityList = document.querySelector("[data-users-security]");
const activityList = document.querySelector("[data-users-activity]");
const rolesList = document.querySelector("[data-users-roles]");
const roleActions = document.querySelector("[data-users-role-actions]");
const roleNote = document.querySelector("[data-users-role-note]");
const historyList = document.querySelector("[data-users-history]");
const actionNote = document.querySelector("[data-users-action-note]");
const statusActionButton = document.querySelector("[data-users-status-action]");
const sessionActionButton = document.querySelector("[data-users-action='revoke_sessions']");
const conflictNotice = document.querySelector("[data-users-conflict]");
const conflictMessage = document.querySelector("[data-users-conflict-message]");
const conflictReloadButton = document.querySelector("[data-users-conflict-reload]");
const backToListButton = document.querySelector("[data-users-back-to-list]");
const closeDetailButton = document.querySelector("[data-users-close-detail]");
const liveRegion = document.querySelector("[data-users-live]");
const dialog = document.querySelector("[data-users-dialog]");
const dialogForm = document.querySelector("[data-users-dialog-form]");
const dialogKicker = document.querySelector("[data-users-dialog-kicker]");
const dialogTitle = document.querySelector("[data-users-dialog-title]");
const dialogDescription = document.querySelector("[data-users-dialog-description]");
const dialogRoleField = document.querySelector("[data-users-dialog-role-field]");
const dialogConfirmationField = document.querySelector("[data-users-dialog-confirmation-field]");
const dialogConfirmationLabel = document.querySelector("[data-users-dialog-confirmation-label]");
const dialogHelp = document.querySelector("[data-users-dialog-help]");
const dialogError = document.querySelector("[data-users-dialog-error]");
const dialogCancel = document.querySelector("[data-users-dialog-cancel]");
const dialogConfirm = document.querySelector("[data-users-dialog-confirm]");

const PAGE_SIZE = 30;
const MAX_OFFSET = 10000;
const FILTER_STATUSES = new Set(["all", "active", "pending_verification", "suspended", "banned"]);
const FILTER_ROLES = new Set(["all", "user", "reviewer", "admin", "super_admin"]);
const SORT_OPTIONS = new Set(["updated_desc", "created_desc", "last_login_desc", "email_asc"]);
const MANAGED_ROLES = new Set(["reviewer", "admin"]);
const STATUS_LABELS = {
  active: "Active",
  pending_verification: "Pending",
  suspended: "Suspended",
  banned: "Banned",
  deleted: "Deleted",
};
const ROLE_LABELS = {
  user: "User",
  reviewer: "Reviewer",
  admin: "Admin",
  super_admin: "Super Admin",
};
const ACTION_CONFIG = {
  suspend: {
    endpoint: "status",
    apiAction: "suspend",
    kicker: "Account status",
    title: "Suspend this account?",
    description: "The account will lose protected product access according to server policy. Existing work and audit evidence remain intact.",
    confirmLabel: "Suspend account",
    confirmation: "SUSPEND",
    reasons: [
      ["policy_violation", "Policy violation"],
      ["security_review", "Security review"],
      ["suspected_compromise", "Suspected compromise"],
      ["other", "Other"],
    ],
  },
  reactivate: {
    endpoint: "status",
    apiAction: "reactivate",
    kicker: "Account status",
    title: "Reactivate this account?",
    description: "The account will return to active status after the server verifies the current record and access boundary.",
    confirmLabel: "Reactivate account",
    reasons: [
      ["investigation_cleared", "Investigation cleared"],
      ["appeal_upheld", "Appeal upheld"],
      ["administrative_error", "Administrative error"],
      ["other", "Other"],
    ],
  },
  grant_role: {
    endpoint: "roles",
    apiAction: "grant_role",
    kicker: "Role assignment",
    title: "Grant an operational role?",
    description: "The selected role grants protected product capabilities. Only Reviewer and Admin roles can be assigned here.",
    confirmLabel: "Grant role",
    reasons: [
      ["operational_need", "Operational need"],
      ["staffing_change", "Staffing change"],
      ["access_review", "Access review"],
      ["other", "Other"],
    ],
  },
  revoke_role: {
    endpoint: "roles",
    apiAction: "revoke_role",
    kicker: "Role assignment",
    title: "Revoke this operational role?",
    description: "Protected capabilities associated with the selected role will be removed. The assignment history remains auditable.",
    confirmLabel: "Revoke role",
    confirmation: "REVOKE ROLE",
    reasons: [
      ["access_review", "Access review"],
      ["staffing_change", "Staffing change"],
      ["security_review", "Security review"],
      ["other", "Other"],
    ],
  },
  revoke_sessions: {
    endpoint: "revoke-sessions",
    apiAction: "revoke_sessions",
    kicker: "Session security",
    title: "Record a session revocation request?",
    description: "This creates an audited provider action request. Do not treat sessions as closed until the identity provider action is completed.",
    confirmLabel: "Record request",
    confirmation: "REVOKE SESSIONS",
    reasons: [
      ["suspected_compromise", "Suspected compromise"],
      ["access_review", "Access review"],
      ["user_request", "User request"],
      ["other", "Other"],
    ],
  },
};
const CONFLICT_CODES = new Set([
  "ADMIN_USER_VERSION_CONFLICT",
  "ADMIN_USER_STATE_CONFLICT",
  "ADMIN_USER_ROLE_CONFLICT",
  "ADMIN_USER_IDEMPOTENCY_CONFLICT",
]);

let csrfPromise = null;
let items = [];
let total = 0;
let hasMore = false;
let actor = null;
let selectedId = "";
let selectedDetail = null;
let query = "";
let statusFilter = "all";
let roleFilter = "all";
let sort = "updated_desc";
let listLoading = false;
let mutationBusy = false;
let detailConflict = false;
let listController = null;
let detailController = null;
let listRequestSerial = 0;
let detailRequestSerial = 0;
let pendingAction = "";
let pendingIdempotencyKey = "";
let dialogOpener = null;
let toastTimer = null;

const initialParams = new URLSearchParams(window.location.search);
const initialStatus = initialParams.get("status");
const initialRole = initialParams.get("role");
statusFilter = FILTER_STATUSES.has(initialStatus) ? initialStatus : "all";
roleFilter = FILTER_ROLES.has(initialRole) ? initialRole : "all";
query = String(initialParams.get("q") || "").trim().slice(0, 160);
sort = SORT_OPTIONS.has(initialParams.get("sort")) ? initialParams.get("sort") : "updated_desc";
const initialPathMatch = window.location.pathname.match(/^\/admin\/users\/([^/]+)\/?$/);
selectedId = initialPathMatch ? decodeURIComponent(initialPathMatch[1]) : String(initialParams.get("user") || "").trim();
searchInput.value = query;
roleSelect.value = roleFilter;
sortSelect.value = sort;

function value(...candidates) {
  for (const candidate of candidates) {
    if (candidate !== undefined && candidate !== null && candidate !== "") return candidate;
  }
  return null;
}

function displayValue(...candidates) {
  const emptyFallback = candidates.at(-1) === "";
  const next = value(...candidates);
  return next === null ? (emptyFallback ? "" : "Unavailable") : String(next);
}

function normalizeStatus(candidate) {
  const status = displayValue(candidate, "pending_verification").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (["pending", "unverified", "pending_email_verification"].includes(status)) return "pending_verification";
  if (["disabled", "locked"].includes(status)) return "suspended";
  return status;
}

function statusLabel(status) {
  return STATUS_LABELS[status] || humanize(status);
}

function roleLabel(role) {
  return ROLE_LABELS[role] || humanize(role);
}

function normalizeRole(candidate) {
  const raw = typeof candidate === "object" && candidate !== null
    ? value(candidate.role_code, candidate.code, candidate.role, candidate.name)
    : candidate;
  return displayValue(raw, "").toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
}

function normalizeRoles(record = {}) {
  const source = Array.isArray(record.roles)
    ? record.roles
    : Array.isArray(record.role_codes)
      ? record.role_codes
      : value(record.role, record.role_code)
        ? [value(record.role, record.role_code)]
        : [];
  const roles = source.map(normalizeRole).filter(Boolean);
  return Array.from(new Set(roles)).sort((left, right) => {
    const order = ["super_admin", "admin", "reviewer", "user"];
    return order.indexOf(left) - order.indexOf(right);
  });
}

function normalizeHistory(record = {}) {
  const governanceActions = Array.isArray(record.governance_actions) ? record.governance_actions : [];
  const failedAudit = Array.isArray(record.audit_timeline)
    ? record.audit_timeline.filter((event) => event?.result === "failure")
    : [];
  const fallbackSources = [record.audit_history, record.admin_history, record.actions, record.history];
  const fallback = fallbackSources.find(Array.isArray) || [];
  const history = governanceActions.length || failedAudit.length ? [...governanceActions, ...failedAudit] : fallback;
  return [...history].sort((left, right) => {
    const leftTime = Date.parse(value(left.created_at, left.occurred_at, left.timestamp, "")) || 0;
    const rightTime = Date.parse(value(right.created_at, right.occurred_at, right.timestamp, "")) || 0;
    return rightTime - leftTime;
  });
}

function normalizeUser(record = {}) {
  const profile = record.profile || {};
  const sessions = record.sessions || record.session_summary || {};
  const storage = record.storage || {};
  const imageCounts = record.image_counts || {};
  const profileLocation = [profile.city, profile.country_code].filter(Boolean).join(", ");
  return {
    ...record,
    id: displayValue(record.id, record.user_id, record.profile_id, ""),
    displayName: displayValue(record.display_name, record.name, record.full_name, profile.display_name, profile.name, record.email, "Unnamed user"),
    email: displayValue(record.email, profile.email, ""),
    avatarUrl: displayValue(record.avatar_url, profile.avatar_url, ""),
    publicSlug: displayValue(record.public_slug, record.slug, profile.public_slug, ""),
    professionalHeadline: displayValue(record.professional_headline, profile.professional_headline, ""),
    company: displayValue(record.company, profile.company, ""),
    location: displayValue(record.location, profile.location, profileLocation, ""),
    status: normalizeStatus(record.account_status),
    roles: normalizeRoles(record),
    version: value(record.lock_version, record.version, record.row_version),
    emailVerified: value(record.email_verified),
    emailVerifiedAt: value(record.email_verified_at),
    mfaStatus: value(record.mfa_status),
    sessionStatus: value(sessions.status),
    sessionProviderActionRequired: value(sessions.provider_action_required),
    imageCounts,
    storageUsedBytes: value(record.storage_used_bytes, storage.used_bytes),
    storageQuotaBytes: value(record.storage_quota_bytes, storage.quota_bytes),
    storageQuotaStatus: value(record.storage_quota_status, storage.quota_status),
    takedownCaseCount: value(record.takedown_case_count),
    lastActiveAt: value(record.last_active_at),
    createdAt: value(record.created_at, record.createdAt),
    updatedAt: value(record.updated_at, record.updatedAt),
    history: normalizeHistory(record),
    permissions: record.permissions || record.capabilities || {},
    isSelf: value(record.is_self, record.is_current_user, false) === true,
    isSystemIdentity: value(record.is_system_identity),
  };
}

function formatDate(candidate, includeTime = false) {
  if (!candidate) return "Unavailable";
  const date = new Date(candidate);
  if (Number.isNaN(date.getTime())) return String(candidate);
  return new Intl.DateTimeFormat(undefined, includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(date);
}

function shortId(candidate) {
  const text = displayValue(candidate, "").replaceAll("-", "");
  return text ? text.slice(-8).toUpperCase() : "UNKNOWN";
}

function humanize(candidate) {
  return displayValue(candidate, "Unknown").replace(/[._-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function initials(user) {
  const source = displayValue(user.displayName, user.email, "User").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length > 1) return `${parts[0][0]}${parts.at(-1)[0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

function displayBoolean(candidate, positive, negative, unavailable = "Unavailable") {
  if (candidate === true || candidate === "true") return positive;
  if (candidate === false || candidate === "false") return negative;
  return unavailable;
}

function formatBytes(candidate) {
  if (candidate === null || candidate === undefined || candidate === "") return "Unavailable";
  const bytes = Number(candidate);
  if (!Number.isFinite(bytes) || bytes < 0) return "Unavailable";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const amount = bytes / (1024 ** unitIndex);
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: unitIndex ? 1 : 0 }).format(amount)} ${units[unitIndex]}`;
}

function safeImageUrl(candidate) {
  if (!candidate) return "";
  try {
    const url = new URL(candidate, window.location.origin);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.href;
  } catch (_error) {
    return "";
  }
}

function createIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (window.crypto?.getRandomValues) window.crypto.getRandomValues(bytes);
  else bytes.forEach((_byte, index) => { bytes[index] = Math.floor(Math.random() * 256); });
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function csrfToken(force = false) {
  if (force) csrfPromise = null;
  if (!csrfPromise) {
    const request = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification could not be initialized.");
      return payload.csrf_token;
    });
    csrfPromise = request;
    request.catch(() => {
      if (csrfPromise === request) csrfPromise = null;
    });
  }
  return csrfPromise;
}

async function usersRequest(path, options = {}, retryCsrf = true) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (!["GET", "HEAD"].includes(method)) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = await csrfToken();
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
    await csrfToken(true);
    return usersRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(payload.error?.message || "The user administration request failed.");
    error.status = response.status;
    error.code = payload.error?.code || "ADMIN_USERS_REQUEST_FAILED";
    error.details = payload.error?.details || null;
    throw error;
  }
  return payload;
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

function handleBoundaryError(error) {
  const nextPath = `${window.location.pathname}${window.location.search}`;
  if (error.status === 401) {
    window.location.assign(`/auth/sign-in?next=${encodeURIComponent(nextPath)}`);
    return true;
  }
  if (error.status === 403 && error.code === "MFA_REQUIRED") {
    window.location.assign(`/auth/mfa?next=${encodeURIComponent(nextPath)}`);
    return true;
  }
  if (error.status === 403 && error.code === "RECOVERY_SESSION_RESTRICTED") {
    window.location.assign("/auth/reset-password");
    return true;
  }
  return false;
}

function showToast(message, tone = "") {
  window.clearTimeout(toastTimer);
  liveRegion.textContent = message;
  liveRegion.dataset.type = tone;
  liveRegion.classList.add("is-visible");
  toastTimer = window.setTimeout(() => liveRegion.classList.remove("is-visible"), 5200);
}

function syncUrl({ push = false } = {}) {
  const params = new URLSearchParams();
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (roleFilter !== "all") params.set("role", roleFilter);
  if (query) params.set("q", query);
  if (sort !== "updated_desc") params.set("sort", sort);
  const search = params.toString();
  const path = selectedId ? `/admin/users/${encodeURIComponent(selectedId)}` : "/admin/users";
  window.history[push ? "pushState" : "replaceState"](null, "", `${path}${search ? `?${search}` : ""}`);
}

function setListState(message, tone = "", retry = false) {
  listStateMessage.textContent = message;
  listState.dataset.tone = tone;
  listState.hidden = !message;
  listState.setAttribute("role", tone === "error" ? "alert" : "status");
  listRetryButton.hidden = !retry;
}

function setDetailState(title, tone = "", message = "", retry = false) {
  detailStateTitle.textContent = title;
  detailStateMessage.textContent = message;
  detailState.dataset.tone = tone;
  detailState.hidden = false;
  detailState.setAttribute("role", tone === "error" ? "alert" : "status");
  detailRetryButton.hidden = !retry;
  detailElement.hidden = true;
}

function setListBusy(busy) {
  listLoading = busy;
  inventoryRegion.setAttribute("aria-busy", String(busy));
  refreshButton.disabled = busy || mutationBusy;
  loadMoreButton.disabled = busy || mutationBusy;
}

function setDetailBusy(busy) {
  detailRegion.setAttribute("aria-busy", String(busy));
}

function setMutationBusy(busy) {
  mutationBusy = busy;
  document.body.toggleAttribute("data-users-busy", busy);
  refreshButton.disabled = busy || listLoading;
  loadMoreButton.disabled = busy || listLoading;
  statusActionButton.disabled = busy || detailConflict;
  sessionActionButton.disabled = busy || detailConflict || sessionActionButton.dataset.allowed !== "true";
  roleActions.querySelectorAll("button").forEach((button) => {
    button.disabled = busy || detailConflict || button.dataset.allowed !== "true";
  });
  dialogForm.querySelectorAll("select, input, button").forEach((control) => { control.disabled = busy; });
  dialogConfirm.textContent = busy ? "Working..." : ACTION_CONFIG[pendingAction]?.confirmLabel || "Confirm";
}

function renderMetrics(counts = {}) {
  const statusCounts = counts.statuses || counts.status_counts || counts;
  const allCount = value(statusCounts.all, statusCounts.total, counts.total, total, 0);
  document.querySelectorAll("[data-user-count]").forEach((element) => {
    const key = element.dataset.userCount;
    element.textContent = String(key === "all" ? allCount : value(statusCounts[key], 0));
  });
  document.querySelectorAll("[data-status-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.statusFilter === statusFilter));
  });
}

function createStatusBadge(status, className = "admin-users-status") {
  const badge = document.createElement("span");
  badge.className = className;
  badge.dataset.status = status;
  badge.textContent = statusLabel(status);
  return badge;
}

function createRoleBadge(role) {
  const badge = document.createElement("span");
  badge.className = "admin-users-role";
  badge.dataset.role = role;
  badge.textContent = roleLabel(role);
  return badge;
}

function appendAvatar(container, user) {
  container.replaceChildren();
  container.textContent = initials(user);
  const avatarUrl = safeImageUrl(user.avatarUrl);
  if (!avatarUrl) return;
  const image = document.createElement("img");
  image.src = avatarUrl;
  image.alt = "";
  image.decoding = "async";
  image.addEventListener("load", () => {
    container.replaceChildren(image);
  }, { once: true });
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  items.forEach((user) => {
    const row = document.createElement("tr");
    row.dataset.userId = user.id;
    row.classList.toggle("is-active", user.id === selectedId);

    const identityCell = document.createElement("td");
    identityCell.dataset.label = "Identity";
    const openButton = document.createElement("button");
    openButton.className = "admin-users-row-button";
    openButton.type = "button";
    openButton.dataset.openUser = user.id;
    openButton.setAttribute("aria-label", `Inspect ${user.displayName}`);
    if (user.id === selectedId) openButton.setAttribute("aria-current", "true");
    const avatar = document.createElement("span");
    avatar.className = "admin-users-row-avatar";
    avatar.setAttribute("aria-hidden", "true");
    appendAvatar(avatar, user);
    const identityCopy = document.createElement("span");
    identityCopy.className = "admin-users-identity-copy";
    const strong = document.createElement("strong");
    strong.textContent = user.displayName;
    const small = document.createElement("small");
    small.textContent = user.email || `#${shortId(user.id)}`;
    identityCopy.append(strong, small);
    openButton.append(avatar, identityCopy);
    identityCell.append(openButton);

    const roleCell = document.createElement("td");
    roleCell.dataset.label = "Role";
    const role = user.roles[0] || "user";
    roleCell.append(createRoleBadge(role));
    if (user.roles.length > 1) {
      const roleCount = document.createElement("small");
      roleCount.textContent = `+${user.roles.length - 1}`;
      roleCell.append(roleCount);
    }

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Status";
    statusCell.append(createStatusBadge(user.status));

    const loginCell = document.createElement("td");
    loginCell.dataset.label = "Last active";
    const time = document.createElement("time");
    if (user.lastActiveAt) time.dateTime = String(user.lastActiveAt);
    time.textContent = formatDate(user.lastActiveAt);
    loginCell.append(time);

    const arrowCell = document.createElement("td");
    arrowCell.className = "admin-users-row-arrow";
    arrowCell.setAttribute("aria-hidden", "true");
    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    arrow.setAttribute("class", "ui-icon");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#icon-chevron");
    arrow.append(use);
    arrowCell.append(arrow);

    row.append(identityCell, roleCell, statusCell, loginCell, arrowCell);
    fragment.append(row);
  });
  usersList.replaceChildren(fragment);
}

function renderListSummary() {
  const shown = items.length;
  listCount.textContent = `${total.toLocaleString()} ${total === 1 ? "user" : "users"}`;
  rangeLabel.textContent = `${shown.toLocaleString()} of ${total.toLocaleString()}`;
  loadMoreButton.hidden = !hasMore || shown >= MAX_OFFSET;
  clearButton.hidden = !query;
  const statusCopy = statusFilter === "all" ? "All states" : statusLabel(statusFilter);
  const roleCopy = roleFilter === "all" ? "All roles" : roleLabel(roleFilter);
  filterSummary.textContent = `${total.toLocaleString()} ${total === 1 ? "result" : "results"} · ${statusCopy} · ${roleCopy}`;
}

function markSelectedRow() {
  usersList.querySelectorAll("tr").forEach((row) => {
    const active = row.dataset.userId === selectedId;
    row.classList.toggle("is-active", active);
    const button = row.querySelector("[data-open-user]");
    if (active) button?.setAttribute("aria-current", "true");
    else button?.removeAttribute("aria-current");
  });
}

function appendDefinition(list, label, nextValue) {
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = displayValue(nextValue);
  list.append(dt, dd);
}

function renderHistory(user) {
  historyList.replaceChildren();
  if (!user.history.length) {
    const empty = document.createElement("li");
    empty.className = "is-empty";
    empty.textContent = "No administrative events have been recorded for this user.";
    historyList.append(empty);
    return;
  }
  user.history.forEach((event) => {
    const item = document.createElement("li");
    const failed = event.result === "failure" || event.outcome === "failure";
    item.dataset.result = failed ? "failure" : "success";
    const marker = document.createElement("span");
    marker.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    const eventName = humanize(value(event.action, event.event_type, event.type, event.status));
    title.textContent = `${eventName}${failed ? " - Failed" : ""}`;
    const meta = document.createElement("small");
    const actorName = displayValue(event.actor_name, event.admin_name, event.actor?.display_name, "Administrator");
    meta.textContent = `${formatDate(value(event.created_at, event.occurred_at, event.timestamp), true)} · ${actorName}`;
    copy.append(title, meta);
    const reason = value(event.reason_label, event.reason_code, event.reason);
    if (reason) {
      const paragraph = document.createElement("p");
      paragraph.textContent = humanize(reason);
      copy.append(paragraph);
    }
    item.append(marker, copy);
    historyList.append(item);
  });
}

function permissionFor(user, key) {
  const aliases = {
    can_manage_status: ["can_manage_status", "can_change_status", "can_suspend", "manage_status"],
    can_manage_roles: ["can_manage_roles", "can_change_roles", "manage_roles"],
    can_revoke_sessions: ["can_revoke_sessions", "can_request_session_revocation", "revoke_sessions"],
  };
  const sources = [user.permissions, actor?.permissions, actor?.capabilities, actor];
  for (const source of sources) {
    if (!source) continue;
    for (const alias of aliases[key] || [key]) {
      if (source[alias] !== undefined && source[alias] !== null) return source[alias] === true;
    }
  }
  return false;
}

function renderRoles(user) {
  rolesList.replaceChildren();
  const roles = user.roles.length ? user.roles : ["user"];
  roles.forEach((role) => rolesList.append(createRoleBadge(role)));

  const canManageRoles = permissionFor(user, "can_manage_roles") && !user.isSelf;
  const grantable = ["reviewer", "admin"].some((role) => !roles.includes(role));
  const revokable = ["reviewer", "admin"].some((role) => roles.includes(role));
  const grantButton = roleActions.querySelector("[data-users-action='grant_role']");
  const revokeButton = roleActions.querySelector("[data-users-action='revoke_role']");
  grantButton.dataset.allowed = String(canManageRoles && grantable);
  revokeButton.dataset.allowed = String(canManageRoles && revokable);
  grantButton.disabled = mutationBusy || detailConflict || !canManageRoles || !grantable;
  revokeButton.disabled = mutationBusy || detailConflict || !canManageRoles || !revokable;
  if (user.isSelf) roleNote.textContent = "You cannot change your own operational roles.";
  else if (!canManageRoles) roleNote.textContent = "Super Admin access is required to change roles.";
  else if (!grantable && !revokable) roleNote.textContent = "No managed role changes are available.";
  else roleNote.textContent = "Only Reviewer and Admin assignments are managed here. Super Admin cannot be granted from this interface.";
}

function renderActions(user) {
  statusActionButton.hidden = true;
  statusActionButton.classList.remove("admin-users-danger", "button-secondary");
  statusActionButton.removeAttribute("data-users-action");
  const versionAvailable = user.version !== null && user.version !== undefined && user.version !== "";
  const canManageStatus = permissionFor(user, "can_manage_status") && !user.isSelf;
  const canRequestSessionRevocation = permissionFor(user, "can_revoke_sessions") && !user.isSelf;

  if (canManageStatus && user.status === "active") {
    statusActionButton.hidden = false;
    statusActionButton.dataset.usersAction = "suspend";
    statusActionButton.classList.add("admin-users-danger");
    statusActionButton.textContent = "Suspend account";
  } else if (canManageStatus && user.status === "suspended") {
    statusActionButton.hidden = false;
    statusActionButton.dataset.usersAction = "reactivate";
    statusActionButton.classList.add("button-secondary");
    statusActionButton.textContent = "Reactivate account";
  }

  sessionActionButton.dataset.allowed = String(canRequestSessionRevocation && versionAvailable);
  sessionActionButton.disabled = mutationBusy || detailConflict || !canRequestSessionRevocation || !versionAvailable;
  if (!versionAvailable) {
    actionNote.textContent = "The record version is unavailable. Reload before applying an account control.";
  } else if (user.isSelf) {
    actionNote.textContent = "You cannot apply account controls to your own administrator identity.";
  } else if (!canManageStatus && !canRequestSessionRevocation) {
    actionNote.textContent = "Your administrator role does not include controls for this account.";
  } else {
    actionNote.textContent = "Session revocation records a provider action request; it does not claim that provider sessions are already closed.";
  }
  statusActionButton.disabled = mutationBusy || detailConflict || !versionAvailable;
}

function sessionSummary(user) {
  if (user.sessionStatus === "provider_managed") return "Provider managed";
  return "Unavailable";
}

function mfaSummary(user) {
  if (user.mfaStatus) return humanize(user.mfaStatus);
  return "Unavailable";
}

function renderDetail(user, nextActor = null) {
  if (nextActor) actor = nextActor;
  selectedDetail = user;
  selectedId = user.id;
  syncUrl();
  markSelectedRow();
  detailConflict = false;
  conflictNotice.hidden = true;
  conflictMessage.textContent = "";

  detailState.hidden = true;
  detailElement.hidden = false;
  appendAvatar(detailAvatar, user);
  detailStatus.dataset.status = user.status;
  detailStatus.textContent = statusLabel(user.status);
  detailVersion.textContent = user.version === null ? "Version unavailable" : `Version ${user.version}`;
  detailName.textContent = user.displayName;
  detailEmail.textContent = user.email || `User #${shortId(user.id)}`;

  identityList.replaceChildren();
  appendDefinition(identityList, "User ID", user.id);
  appendDefinition(identityList, "Email", user.email || "Unavailable");
  appendDefinition(identityList, "Email verification", displayBoolean(user.emailVerified, "Verified", "Not verified"));
  appendDefinition(identityList, "Verified at", formatDate(user.emailVerifiedAt, true));
  appendDefinition(identityList, "Professional title", user.professionalHeadline || "Unavailable");
  appendDefinition(identityList, "Company", user.company || "Unavailable");
  appendDefinition(identityList, "Public slug", user.publicSlug || "Unavailable");
  appendDefinition(identityList, "Location", user.location || "Unavailable");
  appendDefinition(identityList, "System identity", displayBoolean(user.isSystemIdentity, "Yes", "No"));

  securityList.replaceChildren();
  appendDefinition(securityList, "MFA", mfaSummary(user));
  appendDefinition(securityList, "Active sessions", sessionSummary(user));
  appendDefinition(securityList, "Last active", formatDate(user.lastActiveAt, true));
  appendDefinition(securityList, "Created", formatDate(user.createdAt, true));
  appendDefinition(securityList, "Updated", formatDate(user.updatedAt, true));

  activityList.replaceChildren();
  appendDefinition(activityList, "Works", value(user.imageCounts.total, "Unavailable"));
  appendDefinition(activityList, "Published", value(user.imageCounts.published, "Unavailable"));
  appendDefinition(activityList, "In review", value(user.imageCounts.in_review, "Unavailable"));
  appendDefinition(activityList, "Storage used", formatBytes(user.storageUsedBytes));
  appendDefinition(
    activityList,
    "Storage quota",
    user.storageQuotaStatus === "unavailable" ? "Unavailable" : formatBytes(user.storageQuotaBytes),
  );
  appendDefinition(activityList, "Open takedown cases", value(user.takedownCaseCount, "Unavailable"));

  renderRoles(user);
  renderHistory(user);
  renderActions(user);
}

function listPayload(payload) {
  const source = payload?.data || payload || {};
  const rawItems = Array.isArray(source.items)
    ? source.items
    : Array.isArray(source.users)
      ? source.users
      : Array.isArray(payload)
        ? payload
        : [];
  const pagination = source.pagination || {};
  const nextTotal = Number(value(source.total, pagination.total, rawItems.length, 0));
  const more = value(source.has_more, pagination.has_more, source.next_cursor !== undefined ? Boolean(source.next_cursor) : null);
  return {
    items: rawItems.map(normalizeUser).filter((user) => user.id),
    total: Number.isFinite(nextTotal) ? nextTotal : rawItems.length,
    counts: source.counts || source.status_counts || {},
    actor: source.actor || payload?.actor || null,
    hasMore: more,
  };
}

async function loadList({ append = false, selectFirst = false } = {}) {
  if (mutationBusy || (append && (listLoading || items.length >= MAX_OFFSET))) return;
  listController?.abort();
  const controller = new AbortController();
  listController = controller;
  const serial = ++listRequestSerial;
  const offset = append ? items.length : 0;
  const params = new URLSearchParams({
    status: statusFilter,
    role: roleFilter,
    sort,
    limit: String(PAGE_SIZE),
    offset: String(Math.min(offset, MAX_OFFSET)),
  });
  if (query) params.set("q", query);
  setListBusy(true);
  if (!append) setListState("Loading users", "loading");
  try {
    const result = listPayload(await usersRequest(`/api/admin/users?${params}`, { signal: controller.signal }));
    if (serial !== listRequestSerial) return;
    if (result.actor) actor = result.actor;
    items = append ? [...items, ...result.items] : result.items;
    total = result.total;
    hasMore = result.hasMore === null
      ? items.length < total && result.items.length === PAGE_SIZE
      : Boolean(result.hasMore) && items.length < total;
    renderMetrics(result.counts);
    renderRows();
    renderListSummary();
    if (!items.length) {
      const description = query
        ? "No users match this search, account state, and role."
        : "No users are available for the active filters.";
      setListState(description, "empty");
      if (selectedId) await loadDetail(selectedId, { showMobile: true });
      else setDetailState("No user selected", "empty", "Adjust the filters to inspect another account.");
      return;
    }
    setListState("", "");
    if (!append && selectedId) await loadDetail(selectedId, { showMobile: true });
    else if (!append && selectFirst) await loadDetail(items[0].id);
  } catch (error) {
    if (isAbortError(error) || serial !== listRequestSerial) return;
    if (handleBoundaryError(error)) return;
    const permissionMessage = error.status === 403
      ? "Administrator access is required to view user records."
      : error.message || "Users could not be loaded.";
    setListState(permissionMessage, "error", true);
    filterSummary.textContent = "Users unavailable";
    showToast(permissionMessage, "error");
  } finally {
    if (serial === listRequestSerial) setListBusy(false);
  }
}

function detailPayload(payload) {
  const source = payload?.data || payload || {};
  const raw = source.user || source.item || source;
  return { actor: source.actor || payload?.actor || null, user: normalizeUser(raw) };
}

async function loadDetail(userId, { focus = false, showMobile = false, historyMode = "replace" } = {}) {
  if (!userId || mutationBusy) return;
  detailController?.abort();
  const controller = new AbortController();
  detailController = controller;
  const serial = ++detailRequestSerial;
  selectedId = userId;
  syncUrl({ push: historyMode === "push" });
  markSelectedRow();
  setDetailBusy(true);
  setDetailState("Loading user", "loading", "Retrieving identity, security posture, and administrative evidence.");
  if (showMobile) setMobileView("detail");
  try {
    const payload = detailPayload(await usersRequest(`/api/admin/users/${encodeURIComponent(userId)}`, { signal: controller.signal }));
    if (serial !== detailRequestSerial) return;
    if (!payload.user.id) throw new Error("The user response did not include an identifier.");
    renderDetail(payload.user, payload.actor);
    if (showMobile && window.matchMedia("(max-width: 900px)").matches) {
      window.requestAnimationFrame(() => {
        const headerHeight = document.querySelector(".admin-users-header")?.getBoundingClientRect().height || 0;
        const top = window.scrollY + workspace.getBoundingClientRect().top - headerHeight - 8;
        const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
        window.scrollTo({ top: Math.max(0, top), behavior });
      });
    }
    if (focus) window.requestAnimationFrame(() => detailName.focus({ preventScroll: true }));
  } catch (error) {
    if (isAbortError(error) || serial !== detailRequestSerial) return;
    if (handleBoundaryError(error)) return;
    const message = error.status === 404
      ? "This user no longer exists or is outside your administrative scope."
      : error.message || "User details could not be loaded.";
    setDetailState(error.status === 404 ? "User unavailable" : "Could not load user", "error", message, true);
    showToast(message, "error");
  } finally {
    if (serial === detailRequestSerial) setDetailBusy(false);
  }
}

function setMobileView(view, { focusList = false, focusId = "" } = {}) {
  workspace.dataset.mobileView = view;
  if (focusList) {
    const buttons = Array.from(usersList.querySelectorAll("[data-open-user]"));
    const active = buttons.find((button) => button.dataset.openUser === focusId)
      || usersList.querySelector("[aria-current='true']")
      || buttons[0];
    window.requestAnimationFrame(() => active?.focus({ preventScroll: true }));
  }
}

function closeDetail({ push = true, focusList = true } = {}) {
  const closingId = selectedId;
  detailController?.abort();
  detailRequestSerial += 1;
  selectedId = "";
  selectedDetail = null;
  syncUrl({ push });
  markSelectedRow();
  setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
  setMobileView("list", { focusList, focusId: closingId });
}

function closeDialog({ restoreFocus = true } = {}) {
  if (typeof dialog.close === "function" && dialog.open) dialog.close();
  else dialog.removeAttribute("open");
  pendingAction = "";
  pendingIdempotencyKey = "";
  dialogForm.reset();
  dialogError.textContent = "";
  if (restoreFocus) {
    const opener = dialogOpener;
    dialogOpener = null;
    window.requestAnimationFrame(() => opener?.isConnected && opener.focus());
  } else {
    dialogOpener = null;
  }
}

function managedRoleOptions(action, user) {
  const held = new Set(user.roles);
  return [...MANAGED_ROLES].filter((role) => action === "grant_role" ? !held.has(role) : held.has(role));
}

function openDialog(action) {
  const config = ACTION_CONFIG[action];
  if (!selectedDetail || mutationBusy || !config) return;
  if (selectedDetail.version === null || selectedDetail.version === undefined || selectedDetail.version === "") {
    showToast("Reload this user before applying an account control.", "error");
    return;
  }
  const roleOperation = ["grant_role", "revoke_role"].includes(action);
  const roleOptions = roleOperation ? managedRoleOptions(action, selectedDetail) : [];
  if (roleOperation && !roleOptions.length) {
    showToast(action === "grant_role" ? "No managed role is available to grant." : "No managed role is available to revoke.", "error");
    return;
  }

  pendingAction = action;
  pendingIdempotencyKey = createIdempotencyKey();
  dialogOpener = document.activeElement;
  dialogForm.reset();
  dialogError.textContent = "";
  dialogKicker.textContent = config.kicker;
  dialogTitle.textContent = config.title;
  dialogDescription.textContent = config.description;
  dialogConfirm.textContent = config.confirmLabel;
  dialogConfirm.classList.toggle("admin-users-danger", Boolean(config.confirmation));

  const reasonSelect = dialogForm.elements.reason_code;
  const reasonPlaceholder = document.createElement("option");
  reasonPlaceholder.value = "";
  reasonPlaceholder.textContent = "Select a reason";
  reasonSelect.replaceChildren(reasonPlaceholder);
  config.reasons.forEach(([code, label]) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = label;
    reasonSelect.append(option);
  });

  dialogRoleField.hidden = !roleOperation;
  const targetRoleSelect = dialogForm.elements.target_role;
  targetRoleSelect.required = roleOperation;
  const rolePlaceholder = document.createElement("option");
  rolePlaceholder.value = "";
  rolePlaceholder.textContent = "Select a role";
  targetRoleSelect.replaceChildren(rolePlaceholder);
  roleOptions.forEach((role) => {
    const option = document.createElement("option");
    option.value = role;
    option.textContent = roleLabel(role);
    targetRoleSelect.append(option);
  });

  const confirmationInput = dialogForm.elements.confirmation;
  dialogConfirmationField.hidden = !config.confirmation;
  confirmationInput.required = Boolean(config.confirmation);
  if (config.confirmation) {
    dialogConfirmationLabel.textContent = `Type ${config.confirmation} to confirm`;
    dialogHelp.textContent = `The reason and resulting action are retained in the immutable audit record. Type ${config.confirmation} exactly to continue.`;
  } else {
    dialogHelp.textContent = "The reason and resulting action are retained in the immutable audit record.";
  }

  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  window.requestAnimationFrame(() => (roleOperation ? targetRoleSelect : reasonSelect).focus());
}

function showConflict(message) {
  detailConflict = true;
  conflictMessage.textContent = `${message || "This user changed in another session."} Reload the current record before continuing.`;
  conflictNotice.hidden = false;
  statusActionButton.disabled = true;
  sessionActionButton.disabled = true;
  roleActions.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  window.requestAnimationFrame(() => conflictReloadButton.focus({ preventScroll: true }));
}

async function mutateUser() {
  const config = ACTION_CONFIG[pendingAction];
  if (!selectedDetail || mutationBusy || !config) return;
  dialogError.textContent = "";
  const reasonCode = String(dialogForm.elements.reason_code.value || "");
  const allowedReasons = new Set(config.reasons.map(([code]) => code));
  if (!allowedReasons.has(reasonCode)) {
    dialogError.textContent = "Select a valid reason category.";
    dialogForm.elements.reason_code.focus();
    return;
  }
  const roleOperation = ["grant_role", "revoke_role"].includes(pendingAction);
  const targetRole = roleOperation ? String(dialogForm.elements.target_role.value || "") : null;
  if (roleOperation && (!MANAGED_ROLES.has(targetRole) || !managedRoleOptions(pendingAction, selectedDetail).includes(targetRole))) {
    dialogError.textContent = "Select an available managed role.";
    dialogForm.elements.target_role.focus();
    return;
  }
  if (config.confirmation) {
    const confirmation = String(dialogForm.elements.confirmation.value || "").trim();
    if (confirmation !== config.confirmation) {
      dialogError.textContent = `Type ${config.confirmation} exactly to continue.`;
      dialogForm.elements.confirmation.focus();
      return;
    }
  }
  if (!dialogForm.reportValidity()) return;

  const action = pendingAction;
  const userId = selectedDetail.id;
  const opener = dialogOpener;
  const body = {
    action: config.apiAction,
    reason_code: reasonCode,
    expected_version: selectedDetail.version,
    idempotency_key: pendingIdempotencyKey || createIdempotencyKey(),
  };
  if (roleOperation) body.target_role = targetRole;
  setMutationBusy(true);
  conflictNotice.hidden = true;
  try {
    const payload = await usersRequest(`/api/admin/users/${encodeURIComponent(userId)}/${config.endpoint}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    closeDialog({ restoreFocus: false });
    const replayed = payload.replayed === true || payload.data?.replayed === true;
    const providerActionRequired = payload.action?.provider_action_required === true
      || payload.provider_action_required === true
      || payload.data?.action?.provider_action_required === true
      || payload.data?.provider_action_required === true;
    let message = "The account control was recorded.";
    if (action === "suspend") message = "Account suspended.";
    else if (action === "reactivate") message = "Account reactivated.";
    else if (action === "grant_role") message = `${roleLabel(targetRole)} role granted.`;
    else if (action === "revoke_role") message = `${roleLabel(targetRole)} role revoked.`;
    else if (action === "revoke_sessions") {
      message = providerActionRequired
        ? "Revocation request recorded. Complete the identity provider action before treating sessions as closed."
        : "Session revocation response recorded.";
    }
    showToast(replayed ? `Existing result loaded. ${message}` : message, "success");
    setMutationBusy(false);
    await loadList({ selectFirst: false });
    window.requestAnimationFrame(() => !detailElement.hidden && detailName.focus({ preventScroll: true }));
    window.requestAnimationFrame(() => {
      if (detailElement.hidden && opener?.isConnected) opener.focus();
    });
  } catch (error) {
    if (handleBoundaryError(error)) return;
    if (error.status === 409 || CONFLICT_CODES.has(error.code)) {
      closeDialog({ restoreFocus: false });
      showConflict(error.message);
    } else {
      dialogError.textContent = error.message || "The account control failed.";
      showToast(dialogError.textContent, "error");
    }
  } finally {
    setMutationBusy(false);
  }
}

document.querySelectorAll("[data-status-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    const next = button.dataset.statusFilter;
    if (!FILTER_STATUSES.has(next) || next === statusFilter || mutationBusy) return;
    statusFilter = next;
    selectedId = "";
    selectedDetail = null;
    syncUrl();
    renderMetrics({});
    setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
    setMobileView("list");
    loadList();
  });
});

filterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const next = String(searchInput.value || "").trim().slice(0, 160);
  if (next === query && items.length) return;
  query = next;
  searchInput.value = query;
  selectedId = "";
  selectedDetail = null;
  syncUrl();
  setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
  setMobileView("list");
  loadList();
});

roleSelect.addEventListener("change", () => {
  const next = roleSelect.value;
  if (!FILTER_ROLES.has(next) || next === roleFilter || mutationBusy) return;
  roleFilter = next;
  selectedId = "";
  selectedDetail = null;
  syncUrl();
  setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
  setMobileView("list");
  loadList();
});

sortSelect.addEventListener("change", () => {
  const next = sortSelect.value;
  if (!SORT_OPTIONS.has(next) || next === sort || mutationBusy) return;
  sort = next;
  selectedId = "";
  selectedDetail = null;
  syncUrl();
  setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
  setMobileView("list");
  loadList();
});

clearButton.addEventListener("click", () => {
  if (!query || mutationBusy) return;
  query = "";
  searchInput.value = "";
  selectedId = "";
  selectedDetail = null;
  syncUrl();
  loadList();
  searchInput.focus();
});

usersList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-user]");
  if (!button || mutationBusy) return;
  loadDetail(button.dataset.openUser, {
    focus: true,
    showMobile: true,
    historyMode: button.dataset.openUser === selectedId ? "replace" : "push",
  });
});

refreshButton.addEventListener("click", () => loadList({ selectFirst: Boolean(selectedId) }));
loadMoreButton.addEventListener("click", () => loadList({ append: true, selectFirst: false }));
listRetryButton.addEventListener("click", () => loadList());
detailRetryButton.addEventListener("click", () => selectedId && loadDetail(selectedId, { focus: true }));
conflictReloadButton.addEventListener("click", () => selectedId && loadDetail(selectedId, { focus: true }));
backToListButton.addEventListener("click", () => closeDetail());
closeDetailButton.addEventListener("click", () => closeDetail());

document.querySelectorAll("[data-users-action]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.disabled || button.dataset.allowed === "false") return;
    openDialog(button.dataset.usersAction);
  });
});
statusActionButton.addEventListener("click", () => openDialog(statusActionButton.dataset.usersAction));

dialogForm.addEventListener("submit", (event) => {
  event.preventDefault();
  mutateUser();
});
dialogCancel.addEventListener("click", () => closeDialog());
dialog.addEventListener("cancel", (event) => {
  if (mutationBusy) {
    event.preventDefault();
    return;
  }
  const opener = dialogOpener;
  pendingAction = "";
  pendingIdempotencyKey = "";
  dialogOpener = null;
  window.setTimeout(() => opener?.isConnected && opener.focus(), 0);
});

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  const nextStatus = params.get("status");
  const nextRole = params.get("role");
  statusFilter = FILTER_STATUSES.has(nextStatus) ? nextStatus : "all";
  roleFilter = FILTER_ROLES.has(nextRole) ? nextRole : "all";
  query = String(params.get("q") || "").trim().slice(0, 160);
  sort = SORT_OPTIONS.has(params.get("sort")) ? params.get("sort") : "updated_desc";
  const match = window.location.pathname.match(/^\/admin\/users\/([^/]+)\/?$/);
  selectedId = match ? decodeURIComponent(match[1]) : "";
  selectedDetail = null;
  searchInput.value = query;
  roleSelect.value = roleFilter;
  sortSelect.value = sort;
  renderMetrics({});
  setMobileView(selectedId ? "detail" : "list");
  if (!selectedId) setDetailState("Select a user", "empty", "Choose a row to inspect identity, security posture, roles, and audit history.");
  loadList({ selectFirst: false });
});

renderMetrics({});
renderListSummary();
loadList();
