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
    ["copyright", "版权问题"],
    ["privacy", "隐私问题"],
    ["illegal_content", "违法内容"],
    ["policy_violation", "不符合网站规定"],
    ["security", "安全问题"],
    ["user_request", "本人要求"],
    ["other", "其他"],
  ],
  restore: [
    ["appeal_upheld", "申诉成立"],
    ["investigation_cleared", "核查无问题"],
    ["administrative_error", "之前操作有误"],
    ["other", "其他"],
  ],
};
// The two series of the site (content_category).
const SERIES_LABELS = { concrete: "此间留彩", abstract: "此间留灰" };
const STATUS_TONES = { published: "ok", never_published: "", unpublished: "bad", quarantined: "bad", archived: "", deleted: "bad" };
const SLOW_LOAD_SECONDS = 1.5;
const CONFLICT_CODES = new Set([
  "ADMIN_IMAGE_VERSION_CONFLICT",
  "ADMIN_GOVERNANCE_STATE_CONFLICT",
  "ADMIN_GOVERNANCE_RESTORE_BLOCKED",
  "ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT",
]);
const STATUS_LABELS = {
  published: "已发布",
  quarantined: "已撤下",
  never_published: "草稿",
  unpublished: "已下架",
  archived: "已归档",
  deleted: "已删除",
  approved: "已通过",
  in_review: "审核中",
  submitted: "已提交",
  ready: "已就绪",
  draft: "草稿",
  rejected: "未通过",
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
  return next === null ? (emptyFallback ? "" : "未记录") : String(next);
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
  return STATUS_LABELS[status] || displayValue(status, "未知").replaceAll("_", " ");
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
    series: value(record.content_category, currentVersion.content_category),
    derivatives: record.derivatives || {},
    type: SERIES_LABELS[value(record.content_category, currentVersion.content_category)] || "未分类",
    ratio: displayValue(record.ratio_label, record.ratio, record.aspect_ratio, "未记录"),
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
  if (!candidate) return "未记录";
  const date = new Date(candidate);
  if (Number.isNaN(date.getTime())) return String(candidate);
  return new Intl.DateTimeFormat("zh-CN", includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(date);
}

function shortId(candidate) {
  const text = displayValue(candidate, "").replaceAll("-", "");
  return text ? text.slice(-8).toUpperCase() : "UNKNOWN";
}

function humanize(candidate) {
  const action = displayValue(candidate, "");
  if (/takedown|quarantine/.test(action)) return "撤下作品";
  if (/unpublish/.test(action)) return "下架作品";
  if (/restore/.test(action)) return "恢复作品";
  if (/publish/.test(action)) return "发布作品";
  return action.replace(/[._-]+/g, " ") || "操作";
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
  // With nothing selected the table takes the full width.
  if (tone === "empty") {
    detailRegion.hidden = true;
    delete workspace.dataset.detailOpen;
  }
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
  dialogConfirm.textContent = busy ? "处理中…" : pendingAction === "restore" ? "恢复作品" : "撤下作品";
}

function renderMetrics(counts = {}) {
  const allCount = value(counts.all, counts.total, total, 0);
  document.querySelectorAll("[data-work-count]").forEach((element) => {
    const key = element.dataset.workCount;
    element.textContent = String(key === "all" ? allCount : value(counts[key], 0));
  });
  document.querySelectorAll("[data-status-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.statusFilter === statusFilter));
    if (button.hasAttribute("data-optional-filter")) {
      const key = button.dataset.statusFilter;
      button.hidden = key !== statusFilter && !(Number(counts[key]) > 0);
    }
  });
}

function createStatusBadge(status, className = "admin-works-status") {
  const badge = document.createElement("span");
  badge.className = className;
  badge.dataset.status = status;
  badge.textContent = statusLabel(status);
  return badge;
}

function cell(label, ...children) {
  const element = document.createElement("td");
  element.dataset.label = label;
  element.append(...children);
  return element;
}

function stateElement(tone, text) {
  const wrapper = document.createElement("span");
  wrapper.className = "admin-state";
  const dot = document.createElement("span");
  dot.className = "admin-dot";
  if (tone) dot.dataset.tone = tone;
  wrapper.append(dot, text);
  return wrapper;
}

function formatBytes(bytes) {
  const size = Number(bytes);
  if (!Number.isFinite(size) || size <= 0) return "—";
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function filesElement(work) {
  const wrapper = document.createElement("span");
  wrapper.className = "admin-works-files";
  const summary = work.asset_summary || {};
  [["display", "展示图"], ["thumbnail", "缩略图"]].forEach(([kind, label]) => {
    const line = document.createElement("span");
    const file = work.derivatives?.[kind];
    if (!file) {
      line.dataset.tone = "warn";
      line.textContent = `${label}缺失`;
    } else if (file.scan_status === "pending") {
      line.textContent = `${label} · 扫描中`;
    } else if (file.scan_status === "flagged" || file.scan_status === "failed") {
      line.dataset.tone = "bad";
      line.textContent = `${label} · 未通过扫描`;
    } else {
      line.textContent = `${label} ✓`;
    }
    wrapper.append(line);
  });
  if (!work.derivatives?.display && !work.derivatives?.thumbnail && Number(summary.pending_count) > 0) {
    wrapper.replaceChildren(Object.assign(document.createElement("span"), { textContent: "处理中" }));
  }
  return wrapper;
}

// 加载: how long this browser took to load the work's thumbnail.
function timedThumbnail(work, loadCell) {
  const thumb = document.createElement("span");
  thumb.className = "admin-thumb";
  if (!work.thumbnailUrl) {
    loadCell.replaceChildren("—");
    return thumb;
  }
  const image = document.createElement("img");
  const started = performance.now();
  image.alt = "";
  image.decoding = "async";
  image.addEventListener("load", () => {
    const seconds = (performance.now() - started) / 1000;
    loadCell.replaceChildren(stateElement(seconds > SLOW_LOAD_SECONDS ? "warn" : "ok", `${seconds < 0.1 ? "<0.1" : seconds.toFixed(1)} s`));
  });
  image.addEventListener("error", () => {
    image.remove();
    loadCell.replaceChildren(stateElement("bad", "加载失败"));
  });
  image.src = work.thumbnailUrl;
  thumb.append(image);
  return thumb;
}

function renderRows() {
  const fragment = document.createDocumentFragment();
  items.forEach((work) => {
    const row = document.createElement("tr");
    row.dataset.workId = work.id;
    row.classList.toggle("is-active", work.id === selectedId);

    const loadCell = cell("加载", "…");
    const openButton = document.createElement("button");
    openButton.className = "admin-works-row-button";
    openButton.type = "button";
    openButton.dataset.openWork = work.id;
    openButton.setAttribute("aria-label", `查看《${work.title}》`);
    if (work.id === selectedId) openButton.setAttribute("aria-current", "true");
    const titleCopy = document.createElement("span");
    titleCopy.className = "admin-works-title-copy";
    const strong = document.createElement("strong");
    strong.textContent = work.title;
    const small = document.createElement("small");
    small.textContent = displayValue(work.original_filename, "");
    titleCopy.append(strong, small);
    openButton.append(timedThumbnail(work, loadCell), titleCopy);

    const syncTime = document.createElement("time");
    if (work.updatedAt) syncTime.dateTime = String(work.updatedAt);
    const updated = new Date(work.updatedAt);
    syncTime.textContent = Number.isNaN(updated.getTime())
      ? "已同步"
      : `已同步 · ${String(updated.getMonth() + 1).padStart(2, "0")}-${String(updated.getDate()).padStart(2, "0")}`;
    const sync = stateElement("ok", "");
    sync.lastChild.replaceWith(syncTime);

    const actions = document.createElement("span");
    actions.className = "admin-works-row-actions";
    const edit = document.createElement("a");
    edit.className = "admin-link";
    edit.href = `/workspace/images?image=${encodeURIComponent(work.id)}`;
    edit.textContent = "编辑";
    const detail = document.createElement("button");
    detail.className = "admin-link";
    detail.type = "button";
    detail.dataset.openWork = work.id;
    detail.textContent = "详情";
    actions.append(edit, " · ", detail);

    row.append(
      cell("作品", openButton),
      cell("系列", SERIES_LABELS[work.series] || "—"),
      cell("状态", stateElement(STATUS_TONES[work.status] || "", statusLabel(work.status))),
      cell("图片文件", filesElement(work)),
      cell("大小", formatBytes(work.derivatives?.display?.byte_size)),
      loadCell,
      cell("后台同步", sync),
      cell("操作", actions),
    );
    fragment.append(row);
  });
  worksList.replaceChildren(fragment);
}

function renderListSummary() {
  const shown = items.length;
  listCount.textContent = `${total.toLocaleString()} 件`;
  rangeLabel.textContent = `已显示 ${shown.toLocaleString()} / ${total.toLocaleString()}`;
  loadMoreButton.hidden = !hasMore;
  clearButton.hidden = !query;
  filterSummary.textContent = `${statusFilter === "all" ? "全部状态" : statusLabel(statusFilter)}${query ? ` · 搜索「${query}」` : ""} · 数据来自后台，打开页面时读取`;
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
    empty.textContent = "这件作品还没有下架或恢复记录。";
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
    title.textContent = `${humanize(value(event.action, event.event_type, event.type, event.status))}${failed ? "（未成功）" : ""}`;
    const meta = document.createElement("small");
    const actorName = displayValue(event.actor_name, event.admin_name, event.actor?.display_name, "管理员");
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
    actionNote.textContent = "你的账号没有下架和恢复的权限。";
    return;
  }
  if (work.status === "published") {
    const permitted = explicitPermission(work, "can_takedown");
    if (permitted === false) {
      actionNote.textContent = "这件作品当前状态下不能撤下。";
      return;
    }
    actionButton.hidden = false;
    actionButton.dataset.action = "takedown";
    actionButton.classList.add("admin-works-danger");
    actionButton.textContent = "撤下作品";
    actionNote.textContent = "撤下后，作品会立即从网站的作品页和展厅中消失。";
  } else if (work.status === "quarantined") {
    const permitted = explicitPermission(work, "can_restore");
    if (permitted === false) {
      actionNote.textContent = "展示图和缩略图都通过检查后才能恢复。";
      return;
    }
    actionButton.hidden = false;
    actionButton.dataset.action = "restore";
    actionButton.classList.add("button-secondary");
    actionButton.textContent = "恢复到网站";
    actionNote.textContent = "恢复前会再检查一次作品状态和图片文件。";
  } else {
    actionNote.textContent = "作品发布或被撤下后，才能在这里撤下或恢复。";
  }
  if (!actionButton.hidden && (work.version === null || work.version === undefined || work.version === "")) {
    actionButton.disabled = true;
    actionNote.textContent = "作品版本未知，请先刷新。";
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

  detailRegion.hidden = false;
  workspace.dataset.detailOpen = "true";
  detailState.hidden = true;
  detailElement.hidden = false;
  detailStatus.dataset.status = work.status;
  detailStatus.textContent = statusLabel(work.status);
  const listed = items.find((item) => item.id === work.id) || {};
  const series = SERIES_LABELS[value(work.series, listed.series)] || "未分类";
  const derivatives = Object.keys(work.derivatives || {}).length ? work.derivatives : listed.derivatives || {};
  detailVersion.textContent = work.version === null ? "版本未知" : `第 ${work.version} 版`;
  detailTitle.textContent = work.title;
  detailCreator.textContent = work.publishedAt ? `${series} · ${formatDate(work.publishedAt)} 发布` : series;

  detailImageError.hidden = true;
  if (work.displayUrl) {
    detailImage.src = work.displayUrl;
    detailImage.alt = `《${work.title}》预览`;
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
  appendDefinition(publicationList, "状态", statusLabel(work.status));
  appendDefinition(publicationList, "发布时间", formatDate(work.publishedAt, true));
  if (work.status === "quarantined" || work.quarantinedAt) {
    appendDefinition(publicationList, "撤下时间", formatDate(work.quarantinedAt, true));
    appendDefinition(publicationList, "原因", humanize(value(work.takedown.reason_code, work.reason_code)));
    appendDefinition(publicationList, "说明", value(work.takedown.public_message, work.takedown.user_message, work.public_message));
  } else if (work.unpublishedAt) {
    appendDefinition(publicationList, "下架时间", formatDate(work.unpublishedAt, true));
  }

  recordList.replaceChildren();
  appendDefinition(recordList, "系列", series);
  [["original", "原图"], ["display", "展示图"], ["thumbnail", "缩略图"]].forEach(([kind, label]) => {
    const file = derivatives[kind];
    appendDefinition(recordList, label, file ? `${file.width}×${file.height} · ${formatBytes(file.byte_size)}` : "缺失");
  });
  appendDefinition(recordList, "上传时间", formatDate(work.createdAt, true));
  appendDefinition(recordList, "最后更新", formatDate(work.updatedAt, true));
  appendDefinition(recordList, "作品编号", work.id);

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
    setListState("正在读取作品…", "loading");
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
        ? "没有符合搜索条件的作品。"
        : "这个状态下还没有作品。";
      setListState(description, "empty");
      if (selectedId) await loadDetail(selectedId, { showMobile: true });
      else setDetailState("没有选中作品", "empty", "换一个状态或搜索条件试试。");
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
      ? "需要管理员权限才能查看作品。"
      : "作品读取失败，请重试。";
    setListState(permissionMessage, "error", true);
    filterSummary.textContent = "作品读取失败";
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
  detailRegion.hidden = false;
  workspace.dataset.detailOpen = "true";
  setDetailState("正在读取作品…", "loading", "");
  if (showMobile) setMobileView("detail");
  try {
    const payload = detailPayload(await worksRequest(`/api/admin/works/${encodeURIComponent(workId)}`, { signal: controller.signal }));
    if (serial !== detailRequestSerial) return;
    if (!payload.work.id) throw new Error("The work response did not include an identifier.");
    renderDetail(payload.work, payload.actor);
    if (showMobile && window.matchMedia("(max-width: 900px)").matches) {
      window.requestAnimationFrame(() => {
        const headerHeight = document.querySelector(".admin-sidebar")?.getBoundingClientRect().height || 0;
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
      ? "这件作品已不存在。"
      : "作品详情读取失败，请重试。";
    setDetailState(error.status === 404 ? "作品不存在" : "读取失败", "error", message, true);
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
  setDetailState("选择一件作品", "empty", "点击表格中的「详情」查看这件作品。");
  detailRegion.hidden = true;
  delete workspace.dataset.detailOpen;
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
    showToast("请先刷新这件作品再操作。", "error");
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
  placeholder.textContent = "选择原因";
  reasonSelect.replaceChildren(placeholder);
  ACTION_REASONS[action].forEach(([code, label]) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = label;
    reasonSelect.append(option);
  });
  const restoring = action === "restore";
  dialogKicker.textContent = restoring ? "恢复到网站" : "撤下作品";
  dialogTitle.textContent = restoring ? "把这件作品恢复到网站？" : "从网站撤下这件作品？";
  dialogDescription.textContent = restoring
    ? "恢复前会再检查一次作品状态、展示图和缩略图。"
    : "作品会立即从作品页和展厅中消失。这次操作和说明会写入操作记录。";
  dialogConfirm.textContent = restoring ? "恢复作品" : "撤下作品";
  dialogConfirm.classList.toggle("admin-works-danger", !restoring);
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  window.requestAnimationFrame(() => dialogForm.elements.reason_code.focus());
}

function showConflict(message) {
  detailConflict = true;
  conflictMessage.textContent = "这件作品刚在别处被修改过，请重新读取后再操作。";
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
    dialogError.textContent = "请选择原因。";
    dialogForm.elements.reason_code.focus();
    return;
  }
  if (publicMessage.length < 5) {
    dialogError.textContent = "说明至少写 5 个字。";
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
        ? "这次操作之前已经完成。"
        : restored
          ? "作品已恢复到网站。"
          : "作品已从网站撤下。",
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
      dialogError.textContent = "操作没有成功，请重试。";
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
    setDetailState("选择一件作品", "empty", "点击表格中的「详情」查看这件作品。");
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
  setDetailState("选择一件作品", "empty", "点击表格中的「详情」查看这件作品。");
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
  setDetailState("选择一件作品", "empty", "点击表格中的「详情」查看这件作品。");
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
  if (!selectedId) setDetailState("选择一件作品", "empty", "点击表格中的「详情」查看这件作品。");
  loadList({ selectFirst: false });
});

renderMetrics({});
renderListSummary();
loadList();
