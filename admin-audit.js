const auditList = document.querySelector("[data-audit-list]");
const inventory = document.querySelector("[data-audit-inventory]");
const listState = document.querySelector("[data-audit-list-state]");
const listStateMessage = document.querySelector("[data-audit-list-state-message]");
const listRetry = document.querySelector("[data-audit-list-retry]");
const listCount = document.querySelector("[data-audit-list-count]");
const rangeLabel = document.querySelector("[data-audit-range]");
const loadMore = document.querySelector("[data-audit-load-more]");
const filterForm = document.querySelector("[data-audit-filters]");
const filterSummary = document.querySelector("[data-audit-filter-summary]");
const clearFilters = document.querySelector("[data-audit-clear]");
const refreshButton = document.querySelector("[data-audit-refresh]");
const exportButton = document.querySelector("[data-audit-export]");
const filterError = document.querySelector("[data-audit-filter-error]");
const advancedFilters = document.querySelector("[data-audit-advanced]");
const exportDialog = document.querySelector("[data-audit-export-dialog]");
const exportForm = document.querySelector("[data-audit-export-form]");
const exportCancel = document.querySelector("[data-audit-export-cancel]");
const exportSubmit = document.querySelector("[data-audit-export-submit]");
const exportError = document.querySelector("[data-audit-export-error]");
const workspace = document.querySelector("[data-audit-workspace]");
const detailRegion = document.querySelector("[data-audit-detail-region]");
const detailState = document.querySelector("[data-audit-detail-state]");
const detailStateTitle = document.querySelector("[data-audit-detail-state-title]");
const detailStateMessage = document.querySelector("[data-audit-detail-state-message]");
const detailRetry = document.querySelector("[data-audit-detail-retry]");
const detail = document.querySelector("[data-audit-detail]");
const detailResult = document.querySelector("[data-audit-result]");
const detailCreated = document.querySelector("[data-audit-created]");
const detailAction = document.querySelector("[data-audit-action]");
const detailTarget = document.querySelector("[data-audit-target]");
const detailContext = document.querySelector("[data-audit-context]");
const changedFields = document.querySelector("[data-audit-changed-fields]");
const beforeList = document.querySelector("[data-audit-before]");
const afterList = document.querySelector("[data-audit-after]");
const liveRegion = document.querySelector("[data-audit-live]");

const state = {
  items: [],
  nextCursor: null,
  selectedId: "",
  listRequest: 0,
  detailRequest: 0,
  exportBusy: false,
  exportIdempotencyKey: "",
};

const AUDIT_EXPORT_REASONS = new Set([
  "operational_review",
  "security_investigation",
  "compliance_request",
]);

function clean(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function title(value) {
  return clean(value).replace(/[._-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase()) || "Unavailable";
}

function formatDate(value) {
  const parsed = new Date(clean(value));
  if (Number.isNaN(parsed.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function errorMessage(payload, fallback) {
  return clean(payload?.error?.message || payload?.error || payload?.message) || fallback;
}

function filters() {
  return {
    result: clean(filterForm.elements.result.value) || "all",
    target_type: clean(filterForm.elements.target_type.value).toLowerCase() || "all",
    action: clean(filterForm.elements.action.value).toLowerCase() || "all",
    actor: clean(filterForm.elements.actor.value).toLowerCase(),
    request_id: clean(filterForm.elements.request_id.value),
    from: clean(filterForm.elements.from.value),
    to: clean(filterForm.elements.to.value),
  };
}

function uuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function isoDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

function validateFilters(active = filters()) {
  let message = "";
  if (active.actor && !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(active.actor)) {
    message = "Actor ID must be a valid UUID.";
  } else if (active.request_id && !/^[A-Za-z0-9:_-]{1,180}$/.test(active.request_id)) {
    message = "Request ID may contain letters, numbers, colon, underscore, and hyphen.";
  } else if ((active.from && !isoDate(active.from)) || (active.to && !isoDate(active.to))) {
    message = "Choose valid dates.";
  } else if (active.from && active.to && new Date(active.from) > new Date(active.to)) {
    message = "The start date must be before the end date.";
  }
  filterError.textContent = message;
  filterError.hidden = !message;
  return !message;
}

function appendApiFilters(params, active = filters()) {
  params.set("result", active.result);
  params.set("target_type", active.target_type);
  params.set("action", active.action);
  if (active.actor) params.set("actor", active.actor);
  if (active.request_id) params.set("request_id", active.request_id);
  if (active.from) params.set("from", isoDate(active.from));
  if (active.to) params.set("to", isoDate(active.to));
  return params;
}

function setFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const result = params.get("result") || "all";
  filterForm.elements.result.value = ["all", "success", "failure"].includes(result) ? result : "all";
  filterForm.elements.target_type.value = params.get("target_type") === "all" ? "" : clean(params.get("target_type"));
  filterForm.elements.action.value = params.get("action") === "all" ? "" : clean(params.get("action"));
  filterForm.elements.actor.value = clean(params.get("actor"));
  filterForm.elements.request_id.value = clean(params.get("request_id"));
  filterForm.elements.from.value = clean(params.get("from"));
  filterForm.elements.to.value = clean(params.get("to"));
  advancedFilters.open = Boolean(
    filterForm.elements.actor.value
    || filterForm.elements.request_id.value
    || filterForm.elements.from.value
    || filterForm.elements.to.value
  );
}

function selectedIdFromPath() {
  const match = window.location.pathname.match(/^\/admin\/audit\/([0-9a-f-]{36})\/?$/i);
  return match ? match[1].toLowerCase() : "";
}

function updateUrl({ selectedId = state.selectedId, replace = false } = {}) {
  const active = filters();
  const params = new URLSearchParams();
  if (active.result !== "all") params.set("result", active.result);
  if (active.target_type !== "all") params.set("target_type", active.target_type);
  if (active.action !== "all") params.set("action", active.action);
  if (active.actor) params.set("actor", active.actor);
  if (active.request_id) params.set("request_id", active.request_id);
  if (active.from) params.set("from", active.from);
  if (active.to) params.set("to", active.to);
  const path = selectedId ? `/admin/audit/${selectedId}` : "/admin/audit";
  const next = `${path}${params.size ? `?${params}` : ""}`;
  window.history[replace ? "replaceState" : "pushState"]({}, "", next);
}

function setListState(tone, message, retry = false) {
  listState.dataset.tone = tone;
  listStateMessage.textContent = message;
  listRetry.hidden = !retry;
  listState.hidden = !message;
}

function setDetailState(tone, heading, message, retry = false) {
  detail.hidden = true;
  detailState.hidden = false;
  detailState.dataset.tone = tone;
  detailStateTitle.textContent = heading;
  detailStateMessage.textContent = message;
  detailRetry.hidden = !retry;
}

function showToast(message, tone = "success") {
  liveRegion.textContent = message;
  liveRegion.dataset.type = tone;
  liveRegion.classList.add("is-visible");
  window.setTimeout(() => liveRegion.classList.remove("is-visible"), 3600);
}

function appendDefinition(list, label, value) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = clean(value) || "Unavailable";
  row.append(term, description);
  list.append(row);
}

function renderSafeState(list, value) {
  list.replaceChildren();
  const entries = value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value) : [];
  if (!entries.length) {
    appendDefinition(list, "State", "Not recorded");
    return;
  }
  entries.forEach(([key, item]) => {
    const display = Array.isArray(item) ? item.join(", ") : typeof item === "object" && item !== null ? "Changed" : item;
    appendDefinition(list, title(key), display);
  });
}

function eventRow(item) {
  const row = document.createElement("tr");
  row.dataset.auditId = clean(item.id);
  row.tabIndex = 0;
  row.setAttribute("aria-selected", String(clean(item.id) === state.selectedId));

  const resultCell = document.createElement("td");
  const result = document.createElement("span");
  result.className = "admin-audit-result";
  result.dataset.result = clean(item.result);
  result.textContent = title(item.result);
  resultCell.append(result);

  const actionCell = document.createElement("td");
  const action = document.createElement("strong");
  action.textContent = clean(item.action) || "Unknown action";
  actionCell.append(action);

  const targetCell = document.createElement("td");
  targetCell.append(document.createTextNode(title(item.target_type)));
  const targetId = document.createElement("small");
  targetId.textContent = clean(item.target_id) || "Unavailable";
  targetCell.append(targetId);

  const actorCell = document.createElement("td");
  const actor = item.actor && typeof item.actor === "object" ? item.actor : {};
  actorCell.append(document.createTextNode(clean(actor.display_name) || "System"));
  const actorRole = document.createElement("small");
  actorRole.textContent = title(actor.role || item.actor_role);
  actorCell.append(actorRole);
  const createdCell = document.createElement("td");
  createdCell.textContent = formatDate(item.created_at);
  const arrowCell = document.createElement("td");
  arrowCell.className = "admin-audit-row-arrow";
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("class", "ui-icon");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#icon-chevron");
  icon.append(use);
  arrowCell.append(icon);
  row.append(resultCell, actionCell, targetCell, actorCell, createdCell, arrowCell);
  return row;
}

function renderList() {
  auditList.replaceChildren(...state.items.map(eventRow));
  listCount.textContent = `${state.items.length} event${state.items.length === 1 ? "" : "s"}`;
  rangeLabel.textContent = `${state.items.length} loaded`;
  loadMore.hidden = !state.nextCursor;
  exportButton.disabled = !state.items.length;
  if (!state.items.length) setListState("empty", "No audit events match these filters.");
  else setListState("ready", "");
  auditList.querySelector(`[data-audit-id="${CSS.escape(state.selectedId)}"]`)?.setAttribute("aria-selected", "true");
}

function csvValue(value) {
  const source = clean(value);
  const spreadsheetSafe = /^[=+\-@]/.test(source) ? `'${source}` : source;
  const normalized = spreadsheetSafe.replaceAll('"', '""');
  return `"${normalized}"`;
}

function exportRows(items) {
  const fields = [
    ["id", (item) => item.id],
    ["created_at", (item) => item.created_at],
    ["result", (item) => item.result],
    ["action", (item) => item.action],
    ["target_type", (item) => item.target_type],
    ["target_id", (item) => item.target_id],
    ["actor_display_name", (item) => item.actor?.display_name],
    ["actor_role", (item) => item.actor?.role || item.actor_role],
    ["reason_code", (item) => item.reason_code],
    ["policy_version", (item) => item.policy_version],
    ["request_id", (item) => item.request_id],
  ];
  const rows = [fields.map(([field]) => csvValue(field)).join(",")];
  items.forEach((item) => rows.push(fields.map(([, read]) => csvValue(read(item))).join(",")));
  const blob = new Blob([`${rows.join("\r\n")}\r\n`], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const day = new Date().toISOString().slice(0, 10);
  link.href = URL.createObjectURL(blob);
  link.download = `mt-presence-audit-${day}.csv`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

let auditCsrfPromise = null;

async function csrfToken(force = false) {
  if (force) auditCsrfPromise = null;
  if (!auditCsrfPromise) {
    const request = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
      return payload.csrf_token;
    });
    auditCsrfPromise = request;
    request.catch(() => {
      if (auditCsrfPromise === request) auditCsrfPromise = null;
    });
  }
  return auditCsrfPromise;
}

async function exportRequest(body, retryCsrf = true) {
  const response = await fetch("/api/admin/audit-logs/export", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": await csrfToken(),
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await csrfToken(true);
    return exportRequest(body, false);
  }
  if (response.status === 401) {
    window.location.assign(`/auth/sign-in?${new URLSearchParams({ next: `${window.location.pathname}${window.location.search}` })}`);
    throw new Error("Your session has ended.");
  }
  if (!response.ok) throw new Error(errorMessage(payload, "The audit export could not be created."));
  return payload;
}

function exportPayload(reasonCode) {
  const active = filters();
  return {
    result: active.result,
    target_type: active.target_type,
    action: active.action,
    actor: active.actor,
    request_id: active.request_id,
    from: isoDate(active.from),
    to: isoDate(active.to),
    reason_code: reasonCode,
    idempotency_key: state.exportIdempotencyKey || uuid(),
  };
}

function openExportDialog() {
  if (!state.items.length || !validateFilters()) return;
  exportError.hidden = true;
  exportError.textContent = "";
  exportDialog.showModal();
  exportForm.elements.reason_code.focus();
}

function closeExportDialog() {
  if (state.exportBusy) return;
  exportDialog.close();
  exportButton.focus();
}

async function submitExport(event) {
  event.preventDefault();
  if (state.exportBusy || !validateFilters()) return;
  const reasonCode = clean(exportForm.elements.reason_code.value);
  if (!AUDIT_EXPORT_REASONS.has(reasonCode)) {
    exportError.textContent = "Select an export reason.";
    exportError.hidden = false;
    exportForm.elements.reason_code.focus();
    return;
  }
  state.exportBusy = true;
  state.exportIdempotencyKey ||= uuid();
  exportSubmit.disabled = true;
  exportCancel.disabled = true;
  exportSubmit.textContent = "Preparing...";
  exportError.hidden = true;
  try {
    const payload = await exportRequest(exportPayload(reasonCode));
    const result = payload.export && typeof payload.export === "object" ? payload.export : payload;
    const items = Array.isArray(result.items) ? result.items : [];
    exportRows(items);
    const count = Number.isInteger(result.count) ? result.count : items.length;
    const suffix = result.truncated === true ? " The export reached the 1,000-row limit." : "";
    showToast(`${count} safe event${count === 1 ? "" : "s"} exported.${suffix}`);
    state.exportIdempotencyKey = "";
    exportForm.reset();
    exportDialog.close();
  } catch (error) {
    exportError.textContent = error.message || "The audit export could not be created.";
    exportError.hidden = false;
  } finally {
    state.exportBusy = false;
    exportSubmit.disabled = false;
    exportCancel.disabled = false;
    exportSubmit.textContent = "Export CSV";
  }
}

async function fetchList({ append = false } = {}) {
  const requestId = ++state.listRequest;
  inventory.setAttribute("aria-busy", "true");
  if (!append) setListState("loading", "Loading audit events");
  const active = filters();
  if (!validateFilters(active)) {
    inventory.setAttribute("aria-busy", "false");
    setListState("error", "Review the audit filters before loading events.");
    return;
  }
  const params = appendApiFilters(new URLSearchParams({ limit: "30" }), active);
  if (append && state.nextCursor) {
    params.set("before", clean(state.nextCursor.created_at));
    params.set("before_id", clean(state.nextCursor.id));
  }
  try {
    const response = await fetch(`/api/admin/audit-logs?${params}`, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(payload, "Audit events are unavailable."));
    if (requestId !== state.listRequest) return;
    const items = Array.isArray(payload.items) ? payload.items : [];
    state.items = append ? [...state.items, ...items] : items;
    state.nextCursor = payload.pagination?.has_more ? payload.pagination.next_cursor || null : null;
    renderList();
    const activeCount = [
      active.result !== "all",
      active.target_type !== "all",
      active.action !== "all",
      active.actor,
      active.request_id,
      active.from,
      active.to,
    ].filter(Boolean).length;
    filterSummary.textContent = activeCount ? `${activeCount} active filter${activeCount === 1 ? "" : "s"}` : "All audit events";
    clearFilters.hidden = !activeCount;
  } catch (error) {
    if (requestId !== state.listRequest) return;
    setListState("error", error.message || "Audit events are unavailable.", true);
  } finally {
    if (requestId === state.listRequest) inventory.setAttribute("aria-busy", "false");
  }
}

function renderDetail(item) {
  detailResult.dataset.result = clean(item.result);
  detailResult.textContent = title(item.result);
  detailCreated.textContent = formatDate(item.created_at);
  detailAction.textContent = clean(item.action) || "Audit event";
  detailTarget.textContent = `${title(item.target_type)} / ${clean(item.target_id) || "Unavailable"}`;

  detailContext.replaceChildren();
  appendDefinition(detailContext, "Event ID", item.id);
  appendDefinition(detailContext, "Request ID", item.request_id);
  const actor = item.actor && typeof item.actor === "object" ? item.actor : {};
  appendDefinition(detailContext, "Actor", actor.display_name || "System");
  appendDefinition(detailContext, "Actor role", title(actor.role || item.actor_role));
  appendDefinition(detailContext, "Reason", item.reason_code ? title(item.reason_code) : "Not supplied");
  appendDefinition(detailContext, "Policy", item.policy_version || "Unavailable");

  const changes = item.changes && typeof item.changes === "object" ? item.changes : {};
  const fields = Array.isArray(changes.changed_fields) ? changes.changed_fields : [];
  changedFields.replaceChildren();
  if (!fields.length) {
    const quiet = document.createElement("span");
    quiet.textContent = "No safe changed fields recorded";
    changedFields.append(quiet);
  } else {
    fields.forEach((field) => {
      const chip = document.createElement("span");
      chip.textContent = title(field);
      changedFields.append(chip);
    });
  }
  renderSafeState(beforeList, changes.before);
  renderSafeState(afterList, changes.after);
  detailState.hidden = true;
  detail.hidden = false;
  detailAction.focus({ preventScroll: true });
}

async function selectEvent(id, { history = true } = {}) {
  const normalized = clean(id).toLowerCase();
  if (!normalized) return;
  state.selectedId = normalized;
  if (history) updateUrl({ selectedId: normalized });
  workspace.dataset.mobileView = "detail";
  renderList();
  const requestId = ++state.detailRequest;
  detailRegion.setAttribute("aria-busy", "true");
  setDetailState("loading", "Loading evidence", "Retrieving the safe audit projection.");
  try {
    const response = await fetch(`/api/admin/audit-logs/${encodeURIComponent(normalized)}`, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(payload, "Audit evidence is unavailable."));
    if (requestId !== state.detailRequest) return;
    renderDetail(payload.audit || payload.item || {});
  } catch (error) {
    if (requestId !== state.detailRequest) return;
    setDetailState("error", "Evidence unavailable", error.message || "Audit evidence is unavailable.", true);
  } finally {
    if (requestId === state.detailRequest) detailRegion.setAttribute("aria-busy", "false");
  }
}

function closeDetail({ history = true } = {}) {
  state.selectedId = "";
  state.detailRequest += 1;
  workspace.dataset.mobileView = "list";
  if (history) updateUrl({ selectedId: "" });
  setDetailState("empty", "Select an event", "Choose a ledger row to inspect its safe evidence projection.");
  renderList();
  document.querySelector("[data-audit-list]")?.focus?.({ preventScroll: true });
}

auditList.addEventListener("click", (event) => {
  const row = event.target.closest("[data-audit-id]");
  if (row) selectEvent(row.dataset.auditId);
});
auditList.addEventListener("keydown", (event) => {
  if (!["Enter", " "].includes(event.key)) return;
  const row = event.target.closest("[data-audit-id]");
  if (!row) return;
  event.preventDefault();
  selectEvent(row.dataset.auditId);
});
filterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!validateFilters()) return;
  state.exportIdempotencyKey = "";
  state.nextCursor = null;
  closeDetail({ history: false });
  updateUrl({ selectedId: "" });
  fetchList();
});
clearFilters.addEventListener("click", () => {
  filterForm.reset();
  advancedFilters.open = false;
  filterError.hidden = true;
  filterError.textContent = "";
  state.exportIdempotencyKey = "";
  state.nextCursor = null;
  closeDetail({ history: false });
  updateUrl({ selectedId: "" });
  fetchList();
});
refreshButton.addEventListener("click", async () => {
  state.nextCursor = null;
  await fetchList();
  if (state.selectedId) await selectEvent(state.selectedId, { history: false });
  showToast("Audit ledger refreshed.");
});
exportButton.addEventListener("click", openExportDialog);
exportForm.addEventListener("submit", submitExport);
exportCancel.addEventListener("click", closeExportDialog);
exportDialog.addEventListener("cancel", (event) => {
  if (!state.exportBusy) return;
  event.preventDefault();
});
filterForm.addEventListener("input", () => {
  state.exportIdempotencyKey = "";
  if (!filterError.hidden) validateFilters();
});
loadMore.addEventListener("click", () => fetchList({ append: true }));
listRetry.addEventListener("click", () => fetchList());
detailRetry.addEventListener("click", () => selectEvent(state.selectedId, { history: false }));
document.querySelector("[data-audit-back-to-list]").addEventListener("click", () => closeDetail());

window.addEventListener("popstate", async () => {
  setFiltersFromUrl();
  const selected = selectedIdFromPath();
  await fetchList();
  if (selected) await selectEvent(selected, { history: false });
  else closeDetail({ history: false });
});

setFiltersFromUrl();
state.selectedId = selectedIdFromPath();
fetchList().then(() => {
  if (state.selectedId) selectEvent(state.selectedId, { history: false });
});
