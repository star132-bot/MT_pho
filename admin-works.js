const worksList = document.querySelector("[data-works-list]");
const listState = document.querySelector("[data-works-list-state]");
const listStateMessage = document.querySelector("[data-works-list-state-message]");
const listRetryButton = document.querySelector("[data-works-list-retry]");
const listCount = document.querySelector("[data-works-list-count]");
const rangeLabel = document.querySelector("[data-works-range]");
const loadMoreButton = document.querySelector("[data-works-load-more]");
const inventoryRegion = document.querySelector("[data-works-inventory]");
const workspace = document.querySelector("[data-works-workspace]");
const filterForm = document.querySelector("[data-works-filters]");
const searchInput = filterForm.elements.q;
const sortSelect = filterForm.elements.sort;
const clearButton = document.querySelector("[data-works-clear]");
const filterSummary = document.querySelector("[data-works-filter-summary]");
const refreshButton = document.querySelector("[data-works-refresh]");
const detailRegion = document.querySelector("[data-works-detail-region]");
const detailState = document.querySelector("[data-works-detail-state]");
const detailStateTitle = document.querySelector("[data-works-detail-state-title]");
const detailStateMessage = document.querySelector("[data-works-detail-state-message]");
const detailRetryButton = document.querySelector("[data-works-detail-retry]");
const detailElement = document.querySelector("[data-works-detail]");
const detailImage = document.querySelector("[data-works-image]");
const detailImageError = document.querySelector("[data-works-image-error]");
const detailStatus = document.querySelector("[data-works-status]");
const detailVersion = document.querySelector("[data-works-version]");
const detailTitle = document.querySelector("[data-works-title]");
const detailCreator = document.querySelector("[data-works-creator]");
const detailPublicLink = document.querySelector("[data-works-public-link]");
const publicationList = document.querySelector("[data-works-publication]");
const recordList = document.querySelector("[data-works-record]");
const historyList = document.querySelector("[data-works-history]");
const actionButton = document.querySelector("[data-works-action]");
const actionNote = document.querySelector("[data-works-action-note]");
const conflictNotice = document.querySelector("[data-works-conflict]");
const conflictMessage = document.querySelector("[data-works-conflict-message]");
const conflictReloadButton = document.querySelector("[data-works-conflict-reload]");
const backToListButton = document.querySelector("[data-works-back-to-list]");
const closeDetailButton = document.querySelector("[data-works-close-detail]");
const liveRegion = document.querySelector("[data-works-live]");
const dialog = document.querySelector("[data-works-dialog]");
const dialogForm = document.querySelector("[data-works-dialog-form]");
const dialogKicker = document.querySelector("[data-works-dialog-kicker]");
const dialogTitle = document.querySelector("[data-works-dialog-title]");
const dialogDescription = document.querySelector("[data-works-dialog-description]");
const dialogError = document.querySelector("[data-works-dialog-error]");
const dialogCancel = document.querySelector("[data-works-dialog-cancel]");
const dialogConfirm = document.querySelector("[data-works-dialog-confirm]");

const PAGE_SIZE = 50;
const FILTER_STATUSES = new Set(["all", "never_published", "published", "unpublished", "quarantined", "archived", "deleted"]);
const SORT_OPTIONS = new Set(["updated_desc", "published_desc", "uploaded_desc", "title_asc"]);
const ACTION_REASONS = {
  takedown: [
    ["copyright", "Copyright"],
    ["privacy", "Privacy"],
    ["illegal_content", "Illegal content"],
    ["policy_violation", "Policy violation"],
    ["security", "Security"],
    ["user_request", "User request"],
    ["other", "Other"],
  ],
  restore: [
    ["appeal_upheld", "Appeal upheld"],
    ["investigation_cleared", "Investigation cleared"],
    ["administrative_error", "Administrative error"],
    ["other", "Other"],
  ],
};
const CONFLICT_CODES = new Set([
  "ADMIN_IMAGE_VERSION_CONFLICT",
  "ADMIN_GOVERNANCE_STATE_CONFLICT",
  "ADMIN_GOVERNANCE_RESTORE_BLOCKED",
  "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT",
]);
const STATUS_LABELS = {
  published: "Published",
  quarantined: "Taken down",
  never_published: "Never published",
  unpublished: "Unpublished",
  archived: "Archived",
  deleted: "Deleted",
  approved: "Approved",
  in_review: "In review",
  submitted: "Submitted",
  ready: "Ready",
  draft: "Draft",
  rejected: "Rejected",
};

let csrfPromise = null;
let items = [];
let total = 0;
let hasMore = false;
let actor = null;
let selectedId = "";
let selectedDetail = null;
let query = "";
let statusFilter = "all";
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
statusFilter = FILTER_STATUSES.has(initialStatus) ? initialStatus : "all";
query = String(initialParams.get("q") || "").trim().slice(0, 160);
sort = SORT_OPTIONS.has(initialParams.get("sort")) ? initialParams.get("sort") : "updated_desc";
const initialPathMatch = window.location.pathname.match(/^\/admin\/works\/([^/]+)\/?$/);
selectedId = initialPathMatch ? decodeURIComponent(initialPathMatch[1]) : String(initialParams.get("work") || "").trim();
searchInput.value = query;
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
  return next === null ? (emptyFallback ? "" : "Not recorded") : String(next);
}

function canonicalStatus(record = {}) {
  const publication = record.publication || {};
  const takedown = record.takedown || (Array.isArray(record.takedowns) ? record.takedowns[0] : {}) || {};
  if (record.taken_down_at || record.quarantined_at || takedown.active === true) return "quarantined";
  const raw = displayValue(
    record.publication_status,
    publication.status,
    record.public_status,
    record.state,
    record.status,
    record.governance_status,
    record.review_status,
    "draft",
  ).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (["taken_down", "takedown", "removed", "quarantine"].includes(raw)) return "quarantined";
  if (["inreview", "reviewing"].includes(raw)) return "in_review";
  if (
    record.published_at
    && !["published", "unpublished", "quarantined", "taken_down", "archived", "deleted", "never_published"].includes(raw)
  ) return "published";
  return raw;
}

function statusLabel(status) {
  return STATUS_LABELS[status] || displayValue(status, "Unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function creatorFrom(record = {}) {
  const creator = record.creator || record.owner || {};
  return {
    id: displayValue(record.creator_id, record.owner_id, creator.id, ""),
    name: displayValue(record.creator_name, record.owner_name, creator.display_name, creator.name, "Unknown creator"),
    email: displayValue(record.creator_email, record.owner_email, creator.email, ""),
    slug: displayValue(record.creator_slug, creator.public_slug, creator.slug, ""),
  };
}

function imageUrl(record = {}, kind = "thumbnail") {
  const assets = record.assets || {};
  const thumbnail = assets.thumbnail || record.thumbnail || {};
  const display = assets.display || record.display || {};
  if (kind === "display") {
    return displayValue(
      record.display_url,
      display.signed_url,
      display.url,
      record.image_url,
      record.preview_url,
      record.thumbnail_url,
      thumbnail.url,
      "",
    );
  }
  return displayValue(record.thumbnail_url, thumbnail.signed_url, thumbnail.url, record.display_url, display.signed_url, display.url, record.image_url, "");
}

function normalizeWork(record = {}) {
  const publication = record.publication || {};
  const takedown = record.takedown || (Array.isArray(record.takedowns) ? record.takedowns[0] : {}) || {};
  const currentVersion = record.current_version || {};
  const governanceHistory = Array.isArray(record.governance_actions)
    ? record.governance_actions
    : Array.isArray(record.governance_history)
      ? record.governance_history
      : [];
  const failedAuditHistory = Array.isArray(record.audit_timeline)
    ? record.audit_timeline.filter((event) => event?.result === "failure")
    : [];
  const normalized = {
    ...record,
    id: displayValue(record.id, record.image_id, record.work_id, ""),
    title: displayValue(record.title, record.name, "Untitled work"),
    status: canonicalStatus(record),
    creator: creatorFrom(record),
    thumbnailUrl: imageUrl(record, "thumbnail"),
    displayUrl: imageUrl(record, "display"),
    version: value(record.lock_version, record.version, record.row_version, publication.version),
    createdAt: value(record.created_at, record.createdAt),
    updatedAt: value(record.updated_at, record.updatedAt, record.published_at),
    publishedAt: value(record.published_at, publication.published_at, publication.created_at),
    quarantinedAt: value(record.quarantined_at, record.taken_down_at, takedown.created_at, takedown.taken_down_at),
    unpublishedAt: value(record.unpublished_at, publication.unpublished_at),
    publicUrl: displayValue(record.public_url, publication.url, record.work_url, ""),
    type: displayValue(record.work_type, record.type, record.category, currentVersion.content_category, "Not classified"),
    ratio: displayValue(record.ratio_label, record.ratio, record.aspect_ratio, "Not recorded"),
    history: governanceHistory.length || failedAuditHistory.length
      ? [...governanceHistory, ...failedAuditHistory].sort((left, right) => {
        const leftTime = Date.parse(value(left.created_at, left.occurred_at, left.timestamp, "")) || 0;
        const rightTime = Date.parse(value(right.created_at, right.occurred_at, right.timestamp, "")) || 0;
        return rightTime - leftTime;
      })
      : Array.isArray(record.audit_events)
        ? record.audit_events
        : Array.isArray(record.history)
          ? record.history
          : [],
    takedown,
  };
  return normalized;
}

function formatDate(candidate, includeTime = false) {
  if (!candidate) return "Not recorded";
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

async function worksRequest(path, options = {}, retryCsrf = true) {
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
    return worksRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(payload.error?.message || "The works request failed.");
    error.status = response.status;
    error.code = payload.error?.code || "ADMIN_WORKS_REQUEST_FAILED";
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
  toastTimer = window.setTimeout(() => liveRegion.classList.remove("is-visible"), 4200);
}

function syncUrl({ push = false } = {}) {
  const params = new URLSearchParams();
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (query) params.set("q", query);
  if (sort !== "updated_desc") params.set("sort", sort);
  const search = params.toString();
  const path = selectedId ? `/admin/works/${encodeURIComponent(selectedId)}` : "/admin/works";
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
  document.body.toggleAttribute("data-works-busy", busy);
  actionButton.disabled = busy || detailConflict;
  refreshButton.disabled = busy || listLoading;
  loadMoreButton.disabled = busy || listLoading;
  dialogForm.querySelectorAll("select, textarea, button").forEach((control) => { control.disabled = busy; });
  dialogConfirm.textContent = busy ? "Working…" : pendingAction === "restore" ? "Restore work" : "Take down work";
}

function renderMetrics(counts = {}) {
  const allCount = value(counts.all, counts.total, total, 0);
  document.querySelectorAll("[data-work-count]").forEach((element) => {
    const key = element.dataset.workCount;
    element.textContent = String(key === "all" ? allCount : value(counts[key], 0));
  });
  document.querySelectorAll("[data-status-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.statusFilter === statusFilter));
  });
}

function createStatusBadge(status, className = "admin-works-status") {
  const badge = document.createElement("span");
  badge.className = className;
  badge.dataset.status = status;
  badge.textContent = statusLabel(status);
  return badge;
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  items.forEach((work) => {
    const row = document.createElement("tr");
    row.dataset.workId = work.id;
    row.classList.toggle("is-active", work.id === selectedId);

    const workCell = document.createElement("td");
    workCell.dataset.label = "Work";
    const openButton = document.createElement("button");
    openButton.className = "admin-works-row-button";
    openButton.type = "button";
    openButton.dataset.openWork = work.id;
    openButton.setAttribute("aria-label", `Inspect ${work.title}`);
    if (work.id === selectedId) openButton.setAttribute("aria-current", "true");
    const thumb = document.createElement("span");
    thumb.className = "admin-works-thumb";
    if (work.thumbnailUrl) {
      const image = document.createElement("img");
      image.src = work.thumbnailUrl;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove());
      thumb.append(image);
    }
    const titleCopy = document.createElement("span");
    titleCopy.className = "admin-works-title-copy";
    const strong = document.createElement("strong");
    strong.textContent = work.title;
    const small = document.createElement("small");
    small.textContent = `#${shortId(work.id)} · ${work.type}`;
    titleCopy.append(strong, small);
    openButton.append(thumb, titleCopy);
    workCell.append(openButton);

    const creatorCell = document.createElement("td");
    creatorCell.dataset.label = "Creator";
    const creatorName = document.createElement("strong");
    creatorName.textContent = work.creator.name;
    const creatorMeta = document.createElement("small");
    creatorMeta.textContent = work.creator.email || (work.creator.id ? `#${shortId(work.creator.id)}` : "Identity unavailable");
    creatorCell.append(creatorName, creatorMeta);

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Publication";
    statusCell.append(createStatusBadge(work.status));

    const updatedCell = document.createElement("td");
    updatedCell.dataset.label = "Updated";
    const time = document.createElement("time");
    if (work.updatedAt) time.dateTime = String(work.updatedAt);
    time.textContent = formatDate(work.updatedAt);
    updatedCell.append(time);

    const arrowCell = document.createElement("td");
    arrowCell.className = "admin-works-row-arrow";
    arrowCell.setAttribute("aria-hidden", "true");
    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    arrow.setAttribute("class", "ui-icon");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#icon-chevron");
    arrow.append(use);
    arrowCell.append(arrow);

    row.append(workCell, creatorCell, statusCell, updatedCell, arrowCell);
    fragment.append(row);
  });
  worksList.replaceChildren(fragment);
}

function renderListSummary() {
  const shown = items.length;
  listCount.textContent = `${total.toLocaleString()} ${total === 1 ? "work" : "works"}`;
  rangeLabel.textContent = `${shown.toLocaleString()} of ${total.toLocaleString()}`;
  loadMoreButton.hidden = !hasMore;
  clearButton.hidden = !query;
  filterSummary.textContent = `${total.toLocaleString()} ${total === 1 ? "result" : "results"} · ${statusFilter === "all" ? "All states" : statusLabel(statusFilter)}`;
}

function markSelectedRow() {
  worksList.querySelectorAll("tr").forEach((row) => {
    const active = row.dataset.workId === selectedId;
    row.classList.toggle("is-active", active);
    const button = row.querySelector("[data-open-work]");
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

function safePublicUrl(candidate) {
  if (!candidate) return "";
  try {
    const url = new URL(candidate, window.location.origin);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.href;
  } catch (_error) {
    return "";
  }
}

function renderHistory(work) {
  const events = work.history;
  historyList.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("li");
    empty.className = "is-empty";
    empty.textContent = "No governance events have been recorded for this work.";
    historyList.append(empty);
    return;
  }
  events.forEach((event) => {
    const item = document.createElement("li");
    const failed = event.result === "failure";
    item.dataset.result = failed ? "failure" : "success";
    const marker = document.createElement("span");
    marker.setAttribute("aria-hidden", "true");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${humanize(value(event.action, event.event_type, event.type, event.status))}${failed ? " - Failed" : ""}`;
    const meta = document.createElement("small");
    const actorName = displayValue(event.actor_name, event.admin_name, event.actor?.display_name, "Administrator");
    meta.textContent = `${formatDate(value(event.created_at, event.occurred_at, event.timestamp), true)} · ${actorName}`;
    copy.append(title, meta);
    const message = value(event.public_message, event.user_message, event.reason, event.message, event.internal_note);
    if (message) {
      const paragraph = document.createElement("p");
      paragraph.textContent = String(message);
      copy.append(paragraph);
    }
    item.append(marker, copy);
    historyList.append(item);
  });
}

function explicitPermission(work, key) {
  const permissions = work.permissions || actor?.permissions || actor?.capabilities || {};
  return value(work[key], actor?.[key], key === "can_govern" ? actor?.can_govern : null, permissions[key], permissions[`works_${key}`]);
}

function renderAction(work) {
  actionButton.hidden = true;
  actionButton.classList.remove("admin-works-danger", "button-secondary");
  actionButton.removeAttribute("data-action");
  const canGovern = explicitPermission(work, "can_govern");
  if (canGovern === false) {
    actionNote.textContent = "Your administrator role does not include publication controls.";
    return;
  }
  if (work.status === "published") {
    const permitted = explicitPermission(work, "can_takedown");
    if (permitted === false) {
      actionNote.textContent = "This work cannot be taken down in its current state.";
      return;
    }
    actionButton.hidden = false;
    actionButton.dataset.action = "takedown";
    actionButton.classList.add("admin-works-danger");
    actionButton.textContent = "Take down work";
    actionNote.textContent = "Taking down removes the work from public Works and the creator profile immediately.";
  } else if (work.status === "quarantined") {
    const permitted = explicitPermission(work, "can_restore");
    if (permitted === false) {
      actionNote.textContent = "Restore is unavailable until the current approved, ready, clean display and thumbnail are verified.";
      return;
    }
    actionButton.hidden = false;
    actionButton.dataset.action = "restore";
    actionButton.classList.add("button-secondary");
    actionButton.textContent = "Restore publication";
    actionNote.textContent = "Restore succeeds only when current approval, readiness, policy, display, and thumbnail checks pass.";
  } else {
    actionNote.textContent = "Publication controls become available when a work is published or taken down.";
  }
  if (!actionButton.hidden && (work.version === null || work.version === undefined || work.version === "")) {
    actionButton.disabled = true;
    actionNote.textContent = "The work version is unavailable. Reload before applying a publication control.";
  } else {
    actionButton.disabled = mutationBusy;
  }
}

function renderDetail(work, nextActor = null) {
  if (nextActor) actor = nextActor;
  selectedDetail = work;
  selectedId = work.id;
  syncUrl();
  markSelectedRow();
  detailConflict = false;
  conflictNotice.hidden = true;
  conflictMessage.textContent = "";

  detailState.hidden = true;
  detailElement.hidden = false;
  detailStatus.dataset.status = work.status;
  detailStatus.textContent = statusLabel(work.status);
  detailVersion.textContent = work.version === null ? "Version unavailable" : `Version ${work.version}`;
  detailTitle.textContent = work.title;
  detailCreator.textContent = work.creator.email ? `${work.creator.name} · ${work.creator.email}` : work.creator.name;

  detailImageError.hidden = true;
  if (work.displayUrl) {
    detailImage.src = work.displayUrl;
    detailImage.alt = `${work.title} preview`;
    detailImage.hidden = false;
  } else {
    detailImage.removeAttribute("src");
    detailImage.alt = "";
    detailImage.hidden = true;
    detailImageError.hidden = false;
  }

  const publicUrl = safePublicUrl(work.publicUrl);
  if (publicUrl && work.status === "published") {
    detailPublicLink.href = publicUrl;
    detailPublicLink.hidden = false;
  } else {
    detailPublicLink.removeAttribute("href");
    detailPublicLink.hidden = true;
  }

  publicationList.replaceChildren();
  appendDefinition(publicationList, "State", statusLabel(work.status));
  appendDefinition(publicationList, "Published", formatDate(work.publishedAt, true));
  if (work.status === "quarantined" || work.quarantinedAt) {
    appendDefinition(publicationList, "Taken down", formatDate(work.quarantinedAt, true));
    appendDefinition(publicationList, "Category", humanize(value(work.takedown.reason_code, work.reason_code)));
    appendDefinition(publicationList, "Creator message", value(work.takedown.public_message, work.takedown.user_message, work.public_message));
  } else if (work.unpublishedAt) {
    appendDefinition(publicationList, "Unpublished", formatDate(work.unpublishedAt, true));
  }

  recordList.replaceChildren();
  appendDefinition(recordList, "Work ID", work.id);
  appendDefinition(recordList, "Type", work.type);
  appendDefinition(recordList, "Ratio", work.ratio);
  appendDefinition(recordList, "Created", formatDate(work.createdAt, true));
  appendDefinition(recordList, "Updated", formatDate(work.updatedAt, true));
  appendDefinition(recordList, "Version", work.version);

  renderHistory(work);
  renderAction(work);
}

function listPayload(payload) {
  const source = payload?.data && Array.isArray(payload.data.items) ? payload.data : payload || {};
  const rawItems = Array.isArray(source.items) ? source.items : Array.isArray(source.works) ? source.works : [];
  const pagination = source.pagination || {};
  return {
    actor: source.actor || payload?.actor || null,
    items: rawItems.map(normalizeWork).filter((work) => work.id),
    counts: source.counts || source.status_counts || {},
    total: Number(value(pagination.total, source.total, source.count, rawItems.length)) || 0,
    hasMore: Boolean(value(pagination.has_more, source.has_more, false)),
  };
}

async function loadList({ append = false, selectFirst = false } = {}) {
  if (mutationBusy) return;
  listController?.abort();
  const controller = new AbortController();
  listController = controller;
  const serial = ++listRequestSerial;
  const offset = append ? items.length : 0;
  if (!append) {
    items = [];
    total = 0;
    hasMore = false;
    worksList.replaceChildren();
    renderListSummary();
    setListState("Loading works", "loading");
  }
  setListBusy(true);
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset), sort });
  if (statusFilter !== "all") params.set("status", statusFilter);
  if (query) params.set("q", query);
  try {
    const payload = listPayload(await worksRequest(`/api/admin/works?${params}`, { signal: controller.signal }));
    if (serial !== listRequestSerial) return;
    actor = payload.actor || actor;
    items = append ? [...items, ...payload.items.filter((next) => !items.some((item) => item.id === next.id))] : payload.items;
    total = payload.total;
    hasMore = payload.hasMore || items.length < total;
    renderMetrics(payload.counts);
    renderRows();
    renderListSummary();
    if (!items.length) {
      const description = query
        ? "No works match this search and publication state."
        : "No works are available in this publication state.";
      setListState(description, "empty");
      if (selectedId) await loadDetail(selectedId, { showMobile: true });
      else setDetailState("No work selected", "empty", "Adjust the filters to inspect another publication state.");
      return;
    }
    setListState("", "");
    if (!append && selectedId) {
      await loadDetail(selectedId, { showMobile: true });
    } else if (!append && selectFirst) {
      await loadDetail(items[0].id);
    }
  } catch (error) {
    if (isAbortError(error) || serial !== listRequestSerial) return;
    if (handleBoundaryError(error)) return;
    const permissionMessage = error.status === 403
      ? "Administrator access is required to view governed works."
      : error.message || "Works could not be loaded.";
    setListState(permissionMessage, "error", true);
    filterSummary.textContent = "Works unavailable";
    showToast(permissionMessage, "error");
  } finally {
    if (serial === listRequestSerial) setListBusy(false);
  }
}

function detailPayload(payload) {
  const source = payload?.data || payload || {};
  const raw = source.work || source.item || source;
  return { actor: source.actor || payload?.actor || null, work: normalizeWork(raw) };
}

async function loadDetail(workId, { focus = false, showMobile = false, historyMode = "replace" } = {}) {
  if (!workId || mutationBusy) return;
  detailController?.abort();
  const controller = new AbortController();
  detailController = controller;
  const serial = ++detailRequestSerial;
  selectedId = workId;
  syncUrl({ push: historyMode === "push" });
  markSelectedRow();
  setDetailBusy(true);
  setDetailState("Loading work", "loading", "Retrieving publication and governance evidence.");
  if (showMobile) setMobileView("detail");
  try {
    const payload = detailPayload(await worksRequest(`/api/admin/works/${encodeURIComponent(workId)}`, { signal: controller.signal }));
    if (serial !== detailRequestSerial) return;
    if (!payload.work.id) throw new Error("The work response did not include an identifier.");
    renderDetail(payload.work, payload.actor);
    if (showMobile && window.matchMedia("(max-width: 900px)").matches) {
      window.requestAnimationFrame(() => {
        const headerHeight = document.querySelector(".admin-works-header")?.getBoundingClientRect().height || 0;
        const top = window.scrollY + workspace.getBoundingClientRect().top - headerHeight - 8;
        const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
        window.scrollTo({ top: Math.max(0, top), behavior });
      });
    }
    if (focus) window.requestAnimationFrame(() => detailTitle.focus({ preventScroll: true }));
  } catch (error) {
    if (isAbortError(error) || serial !== detailRequestSerial) return;
    if (handleBoundaryError(error)) return;
    const message = error.status === 404
      ? "This work no longer exists or is outside your administrative scope."
      : error.message || "Work details could not be loaded.";
    setDetailState(error.status === 404 ? "Work unavailable" : "Could not load work", "error", message, true);
    showToast(message, "error");
  } finally {
    if (serial === detailRequestSerial) setDetailBusy(false);
  }
}

function setMobileView(view, { focusList = false, focusId = "" } = {}) {
  workspace.dataset.mobileView = view;
  if (focusList) {
    const buttons = Array.from(worksList.querySelectorAll("[data-open-work]"));
    const active = buttons.find((button) => button.dataset.openWork === focusId)
      || worksList.querySelector("[aria-current='true']")
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
  setDetailState("Select a work", "empty", "Choose a row to inspect publication evidence and governance history.");
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

function openDialog(action) {
  if (!selectedDetail || mutationBusy || !["takedown", "restore"].includes(action)) return;
  if (selectedDetail.version === null || selectedDetail.version === undefined || selectedDetail.version === "") {
    showToast("Reload this work before applying a publication control.", "error");
    return;
  }
  pendingAction = action;
  pendingIdempotencyKey = createIdempotencyKey();
  dialogOpener = document.activeElement;
  dialogForm.reset();
  dialogError.textContent = "";
  const reasonSelect = dialogForm.elements.reason_code;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select a reason";
  reasonSelect.replaceChildren(placeholder);
  ACTION_REASONS[action].forEach(([code, label]) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = label;
    reasonSelect.append(option);
  });
  const restoring = action === "restore";
  dialogKicker.textContent = restoring ? "Restore publication" : "Public takedown";
  dialogTitle.textContent = restoring ? "Restore this work?" : "Take down this work?";
  dialogDescription.textContent = restoring
    ? "The server will verify current approval, readiness, policy, display, and thumbnail evidence before returning the work to public delivery."
    : "The work will leave public Works and the creator profile immediately. The action and creator message will be audited.";
  dialogConfirm.textContent = restoring ? "Restore work" : "Take down work";
  dialogConfirm.classList.toggle("admin-works-danger", !restoring);
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  window.requestAnimationFrame(() => dialogForm.elements.reason_code.focus());
}

function showConflict(message) {
  detailConflict = true;
  conflictMessage.textContent = `${message || "This work changed in another session."} Reload the current record before continuing.`;
  conflictNotice.hidden = false;
  actionButton.disabled = true;
  window.requestAnimationFrame(() => conflictReloadButton.focus({ preventScroll: true }));
}

async function mutateWork() {
  if (!selectedDetail || mutationBusy || !pendingAction) return;
  dialogError.textContent = "";
  const reasonCode = String(dialogForm.elements.reason_code.value || "");
  const publicMessage = String(dialogForm.elements.public_message.value || "").trim();
  const internalNote = String(dialogForm.elements.internal_note.value || "").trim();
  const allowedReasons = new Set(ACTION_REASONS[pendingAction]?.map(([code]) => code) || []);
  if (!allowedReasons.has(reasonCode)) {
    dialogError.textContent = "Select a valid reason category.";
    dialogForm.elements.reason_code.focus();
    return;
  }
  if (publicMessage.length < 5) {
    dialogError.textContent = "Enter at least 5 characters in the message to the creator.";
    dialogForm.elements.public_message.focus();
    return;
  }
  if (!dialogForm.reportValidity()) return;
  const action = pendingAction;
  const workId = selectedDetail.id;
  const opener = dialogOpener;
  const body = {
    expected_version: selectedDetail.version,
    idempotency_key: pendingIdempotencyKey || createIdempotencyKey(),
    reason_code: reasonCode,
    public_message: publicMessage,
    internal_note: internalNote,
  };
  setMutationBusy(true);
  conflictNotice.hidden = true;
  try {
    const payload = await worksRequest(`/api/admin/works/${encodeURIComponent(workId)}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    closeDialog({ restoreFocus: false });
    const replayed = payload.replayed === true;
    const completedAction = typeof payload.action === "object" ? payload.action.action : payload.action;
    const restored = completedAction === "restore" || (!completedAction && action === "restore");
    showToast(
      replayed
        ? "The existing publication control result was loaded."
        : restored
          ? "Work restored to public delivery."
          : "Work taken down from public delivery.",
      "success",
    );
    setMutationBusy(false);
    await loadList({ selectFirst: false });
    window.requestAnimationFrame(() => !detailElement.hidden && detailTitle.focus({ preventScroll: true }));
    window.requestAnimationFrame(() => {
      if (detailElement.hidden && opener?.isConnected) opener.focus();
    });
  } catch (error) {
    if (handleBoundaryError(error)) return;
    if (error.status === 409 || CONFLICT_CODES.has(error.code)) {
      closeDialog({ restoreFocus: false });
      showConflict(error.message);
    } else {
      dialogError.textContent = error.message || "The publication control failed.";
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
    setDetailState("Select a work", "empty", "Choose a row to inspect publication evidence and governance history.");
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
  setDetailState("Select a work", "empty", "Choose a row to inspect publication evidence and governance history.");
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
  setDetailState("Select a work", "empty", "Choose a row to inspect publication evidence and governance history.");
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

worksList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-work]");
  if (!button || mutationBusy) return;
  loadDetail(button.dataset.openWork, {
    focus: true,
    showMobile: true,
    historyMode: button.dataset.openWork === selectedId ? "replace" : "push",
  });
});

refreshButton.addEventListener("click", () => loadList({ selectFirst: Boolean(selectedId) }));
loadMoreButton.addEventListener("click", () => loadList({ append: true, selectFirst: false }));
listRetryButton.addEventListener("click", () => loadList());
detailRetryButton.addEventListener("click", () => selectedId && loadDetail(selectedId, { focus: true }));
conflictReloadButton.addEventListener("click", () => selectedId && loadDetail(selectedId, { focus: true }));
backToListButton.addEventListener("click", () => closeDetail());
closeDetailButton.addEventListener("click", () => closeDetail());
actionButton.addEventListener("click", () => openDialog(actionButton.dataset.action));

detailImage.addEventListener("load", () => {
  detailImage.hidden = false;
  detailImageError.hidden = true;
});
detailImage.addEventListener("error", () => {
  detailImage.hidden = true;
  detailImageError.hidden = false;
});

dialogForm.addEventListener("submit", (event) => {
  event.preventDefault();
  mutateWork();
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
  statusFilter = FILTER_STATUSES.has(nextStatus) ? nextStatus : "all";
  query = String(params.get("q") || "").trim().slice(0, 160);
  sort = SORT_OPTIONS.has(params.get("sort")) ? params.get("sort") : "updated_desc";
  const match = window.location.pathname.match(/^\/admin\/works\/([^/]+)\/?$/);
  selectedId = match ? decodeURIComponent(match[1]) : "";
  selectedDetail = null;
  searchInput.value = query;
  sortSelect.value = sort;
  renderMetrics({});
  setMobileView(selectedId ? "detail" : "list");
  if (!selectedId) setDetailState("Select a work", "empty", "Choose a row to inspect publication evidence and governance history.");
  loadList({ selectFirst: false });
});

renderMetrics({});
renderListSummary();
loadList();
