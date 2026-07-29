const listElement = document.querySelector("[data-review-list]");
const listState = document.querySelector("[data-review-list-state]");
const listStateMessage = document.querySelector("[data-review-list-state-message]");
const listRetryButton = document.querySelector("[data-review-list-retry]");
const listCount = document.querySelector("[data-review-list-count]");
const loadMoreButton = document.querySelector("[data-review-load-more]");
const filterForm = document.querySelector("[data-review-filters]");
const filterSummary = document.querySelector("[data-review-filter-summary]");
const reviewWorkspace = document.querySelector("[data-review-workspace]");
const queueRegion = document.querySelector("[data-review-queue]");
const detailRegion = document.querySelector("[data-review-detail-region]");
const detailState = document.querySelector("[data-review-detail-state]");
const detailStateTitle = document.querySelector("[data-review-detail-state-title]");
const detailStateMessage = document.querySelector("[data-review-detail-state-message]");
const detailRetryButton = document.querySelector("[data-review-detail-retry]");
const detailElement = document.querySelector("[data-review-detail]");
const detailStatus = document.querySelector("[data-review-status]");
const detailWaiting = document.querySelector("[data-review-waiting-time]");
const detailTitle = document.querySelector("[data-review-title]");
const detailIdentity = document.querySelector("[data-review-identity]");
const detailContext = document.querySelector("[data-review-context]");
const assignmentActions = document.querySelector("[data-review-assignment-actions]");
const conflictNotice = document.querySelector("[data-review-conflict]");
const conflictMessage = document.querySelector("[data-review-conflict-message]");
const conflictReloadButton = document.querySelector("[data-review-conflict-reload]");
const reviewImageStage = document.querySelector("[data-review-image-stage]");
const reviewImage = document.querySelector("[data-review-image]");
const imageError = document.querySelector("[data-review-image-error]");
const imageRetryButton = document.querySelector("[data-review-image-retry]");
const sizeToggle = document.querySelector("[data-review-size-toggle]");
const assetSwitcher = document.querySelector("[data-review-asset-switcher]");
const assetMeta = document.querySelector("[data-review-asset-meta]");
const copyList = document.querySelector("[data-review-copy]");
const rightsList = document.querySelector("[data-review-rights]");
const readinessList = document.querySelector("[data-review-readiness]");
const historyList = document.querySelector("[data-review-history]");
const decisionForm = document.querySelector("[data-review-decision-form]");
const checklist = document.querySelector("[data-review-checklist]");
const decisionSelect = document.querySelector("[data-review-decision]");
const reasonSelect = document.querySelector("[data-review-reason]");
const formNotice = document.querySelector("[data-review-form-notice]");
const decisionSubmit = document.querySelector("[data-review-decision-submit]");
const refreshButton = document.querySelector("[data-review-refresh]");
const liveRegion = document.querySelector("[data-review-live]");
const dialog = document.querySelector("[data-review-dialog]");
const dialogTitle = document.querySelector("[data-review-dialog-title]");
const dialogMessage = document.querySelector("[data-review-dialog-message]");
const dialogCancel = document.querySelector("[data-review-dialog-cancel]");
const dialogConfirm = document.querySelector("[data-review-dialog-confirm]");
const backToQueueButton = document.querySelector("[data-review-back-to-queue]");

const CHECKLIST_ITEMS = [
  ["file_integrity", "File integrity and decode"],
  ["rights", "Rights declaration"],
  ["privacy", "Privacy risk"],
  ["minors", "Minors and vulnerable people"],
  ["sensitive_content", "Sensitive content"],
  ["hate_illegal", "Hate, violence, or illegal content"],
  ["property_release", "Property and location release"],
  ["third_party_ip", "Third-party intellectual property"],
  ["ai_disclosure", "AI disclosure"],
  ["public_metadata", "Public metadata and GPS"],
];

const REASONS = {
  request_changes: [
    ["missing_rights", "Rights information needs attention"],
    ["missing_metadata", "Metadata needs attention"],
    ["privacy_review", "Privacy detail needs attention"],
    ["release_required", "Release information is required"],
  ],
  reject: [
    ["content_policy", "Content policy"],
    ["rights_unverified", "Rights could not be verified"],
    ["privacy_risk", "Unresolved privacy risk"],
    ["misleading_metadata", "Misleading metadata"],
  ],
  approve: [["policy_complete", "Policy checks complete"]],
  approve_and_publish: [["policy_complete", "Policy checks complete"]],
};

const FILTER_STATUSES = new Set(["open", "submitted", "in_review", "completed"]);
const FILTER_ASSIGNMENTS = new Set(["all", "unassigned", "mine"]);
const CONFLICT_CODES = new Set([
  "REVIEW_VERSION_CONFLICT",
  "REVIEW_ALREADY_ASSIGNED",
  "REVIEW_ASSIGNMENT_REQUIRED",
  "REVIEW_STATE_CONFLICT",
]);

let csrfPromise = null;
let queueItems = [];
let queueActor = null;
let queueOffset = 0;
let queueTotal = 0;
let queueLoading = false;
let selectedDetail = null;
let activeAssetKind = "display";
let mutationBusy = false;
let pendingDialogAction = null;
let dialogOpener = null;
let queueController = null;
let detailController = null;
let queueRequestSerial = 0;
let detailRequestSerial = 0;

const initialParams = new URLSearchParams(window.location.search);
let queueStatus = FILTER_STATUSES.has(initialParams.get("status")) ? initialParams.get("status") : "open";
let queueAssignment = FILTER_ASSIGNMENTS.has(initialParams.get("assignment")) ? initialParams.get("assignment") : "all";
let selectedId = selectedIdFromLocation();
filterForm.elements.assignment.value = queueAssignment;
reviewWorkspace.dataset.mobileView = selectedId ? "detail" : "queue";

function selectedIdFromLocation() {
  const match = window.location.pathname.match(/^\/admin\/reviews\/([^/]+)\/?$/);
  if (match) {
    try {
      return decodeURIComponent(match[1]);
    } catch (_error) {
      return "";
    }
  }
  return new URLSearchParams(window.location.search).get("submission") || "";
}

function syncRoute() {
  const path = selectedId ? `/admin/reviews/${encodeURIComponent(selectedId)}` : "/admin/reviews";
  const params = new URLSearchParams();
  if (queueStatus !== "open") params.set("status", queueStatus);
  if (queueAssignment !== "all") params.set("assignment", queueAssignment);
  const query = params.toString();
  window.history.replaceState({}, "", `${path}${query ? `?${query}` : ""}`);
}

function isMobileReviewLayout() {
  return window.matchMedia("(max-width: 760px)").matches;
}

function setMobileReviewView(view, { focusQueue = false, scroll = false } = {}) {
  reviewWorkspace.dataset.mobileView = view === "detail" ? "detail" : "queue";
  if (!isMobileReviewLayout()) return;
  window.requestAnimationFrame(() => {
    const target = view === "detail" ? detailRegion : queueRegion;
    if (scroll) target.scrollIntoView({ block: "start", behavior: "auto" });
    if (focusQueue) {
      const active = listElement.querySelector('[data-review-submission][aria-current="true"]');
      (active || listElement.querySelector("[data-review-submission]"))?.focus({ preventScroll: true });
    }
  });
}

function showToast(message, type = "success") {
  liveRegion.textContent = message;
  liveRegion.dataset.type = type;
  liveRegion.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    liveRegion.classList.remove("is-visible");
    window.setTimeout(() => {
      liveRegion.textContent = "";
      delete liveRegion.dataset.type;
    }, 220);
  }, 4200);
}

function displayStatus(status) {
  return {
    submitted: "Waiting",
    in_review: "In review",
    changes_requested: "Changes requested",
    rejected: "Rejected",
    approved: "Approved",
    withdrawn: "Withdrawn",
    escalated: "Escalated",
  }[status] || displayValue(status, "Unknown");
}

function displayDecision(decision) {
  return {
    request_changes: "Changes requested",
    reject: "Rejected",
    approve: "Approved",
    approve_and_publish: "Approved and published",
    escalate: "Escalated",
    quarantine: "Quarantined",
  }[decision] || displayValue(decision, "Decision recorded").replaceAll("_", " ");
}

function displayValue(value, fallback = "Not provided") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatDate(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function waitingTime(value) {
  if (!value) return "";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "";
  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
  if (minutes < 60) return `${minutes}m waiting`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h waiting`;
  return `${Math.floor(hours / 24)}d waiting`;
}

function accountAge(value) {
  const created = new Date(value).getTime();
  if (!Number.isFinite(created)) return "Unknown";
  const days = Math.max(0, Math.floor((Date.now() - created) / 86400000));
  if (days < 2) return `${days} day`;
  if (days < 60) return `${days} days`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${months} months`;
  return `${Math.floor(months / 12)} years`;
}

function shortId(value) {
  const text = displayValue(value, "").replaceAll("-", "");
  return text ? text.slice(-8).toUpperCase() : "UNKNOWN";
}

function humanizeKey(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.csrf_token) throw new Error("Security verification could not be initialized.");
      return result.csrf_token;
    });
    csrfPromise = request;
    request.catch(() => {
      if (csrfPromise === request) csrfPromise = null;
    });
  }
  return csrfPromise;
}

async function reviewRequest(path, options = {}, retryCsrf = true) {
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
  const result = await response.json().catch(() => ({}));
  if (response.status === 403 && result.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await csrfToken(true);
    return reviewRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || "The review request failed.");
    error.status = response.status;
    error.code = result.error?.code || "REVIEW_REQUEST_FAILED";
    throw error;
  }
  return result;
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

function handleRequestError(error) {
  const nextPath = `${window.location.pathname}${window.location.search}`;
  if (error.status === 401) {
    window.location.assign(`/auth/sign-in?next=${encodeURIComponent(nextPath)}`);
    return;
  }
  if (error.status === 403 && error.code === "MFA_REQUIRED") {
    window.location.assign(`/auth/mfa?next=${encodeURIComponent(nextPath)}`);
    return;
  }
  if (error.status === 403 && error.code === "RECOVERY_SESSION_RESTRICTED") {
    window.location.assign("/auth/reset-password");
    return;
  }
  showToast(error.message || "The review request failed.", "error");
}

function setListState(message, tone = "", { action = "", actionLabel = "Retry" } = {}) {
  listStateMessage.textContent = message;
  listState.dataset.tone = tone;
  listState.hidden = !message;
  listState.setAttribute("role", tone === "error" ? "alert" : "status");
  listRetryButton.hidden = !action;
  listRetryButton.textContent = actionLabel;
  listRetryButton.dataset.action = action;
}

function setDetailState(title, tone = "", { message = "", action = "", actionLabel = "Retry" } = {}) {
  detailStateTitle.textContent = title;
  detailStateMessage.textContent = message;
  detailState.dataset.tone = tone;
  detailState.hidden = false;
  detailState.setAttribute("role", tone === "error" ? "alert" : "status");
  detailRetryButton.hidden = !action;
  detailRetryButton.textContent = actionLabel;
  detailRetryButton.dataset.action = action;
  detailElement.hidden = true;
}

function setQueueBusy(busy) {
  queueRegion.setAttribute("aria-busy", String(busy));
  loadMoreButton.disabled = busy || mutationBusy;
  refreshButton.disabled = busy || mutationBusy;
}

function setDetailBusy(busy) {
  detailRegion.setAttribute("aria-busy", String(busy));
}

function setMutationBusy(busy) {
  mutationBusy = busy;
  document.body.toggleAttribute("data-review-busy", busy);
  refreshButton.disabled = busy || queueLoading;
  loadMoreButton.disabled = busy || queueLoading;
  listElement.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  assignmentActions.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  decisionForm.querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = busy; });
  dialogCancel.disabled = busy;
  dialogConfirm.disabled = busy;
  dialogConfirm.textContent = busy ? "Working…" : "Confirm";
}

function showConflict(message) {
  conflictMessage.textContent = message || "This submission changed in another session.";
  conflictNotice.hidden = false;
}

function hideConflict() {
  conflictNotice.hidden = true;
  conflictMessage.textContent = "";
}

function renderMetrics(counts = {}) {
  document.querySelectorAll("[data-review-count]").forEach((element) => {
    element.textContent = String(counts[element.dataset.reviewCount] || 0);
  });
  document.querySelectorAll("[data-status-filter]").forEach((button) => {
    const active = button.dataset.statusFilter === queueStatus;
    button.setAttribute("aria-pressed", String(active));
  });
}

function rightsSummary(rights = {}) {
  if (!rights.declared) return "Rights missing";
  if (rights.recognizable_people === true) {
    return rights.model_release_status ? `People · ${humanizeKey(rights.model_release_status)}` : "People · release unstated";
  }
  return "Rights declared";
}

function appendQueueFact(container, value, className = "") {
  const fact = document.createElement("span");
  if (className) fact.className = className;
  fact.textContent = value;
  container.append(fact);
}

function renderQueueItems() {
  listElement.replaceChildren();
  queueItems.forEach((item) => {
    const active = item.id === selectedId;
    const entry = document.createElement("li");
    entry.className = `admin-review-list-item${active ? " is-active" : ""}`;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.reviewSubmission = item.id;
    const titleText = item.image.title || item.image.original_filename || "Untitled submission";
    const waitingText = waitingTime(item.submitted_at) || formatDate(item.submitted_at);
    button.setAttribute(
      "aria-label",
      `Open ${titleText}, ${displayStatus(item.status)}, owner ${item.owner.display_name}, ${waitingText}, submission ending ${shortId(item.id)}`,
    );
    button.setAttribute("aria-controls", "review-detail-content");
    if (active) button.setAttribute("aria-current", "true");
    button.disabled = mutationBusy;

    const media = document.createElement("span");
    media.className = "admin-review-list-thumb";
    if (item.image.thumbnail?.signed_url) {
      const image = document.createElement("img");
      image.src = item.image.thumbnail.signed_url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      media.append(image);
    } else {
      const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      icon.classList.add("ui-icon");
      icon.setAttribute("aria-hidden", "true");
      const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
      use.setAttribute("href", "#icon-photo");
      icon.append(use);
      media.append(icon);
    }

    const content = document.createElement("span");
    content.className = "admin-review-list-copy";
    const title = document.createElement("strong");
    title.textContent = titleText;
    const meta = document.createElement("span");
    meta.className = "admin-review-list-meta";
    meta.textContent = `${item.owner.display_name} · ${waitingTime(item.submitted_at) || formatDate(item.submitted_at)}`;
    const facts = document.createElement("span");
    facts.className = "admin-review-list-facts";
    appendQueueFact(facts, `#${shortId(item.id)}`, "is-id");
    appendQueueFact(facts, displayValue(item.image.content_category, "Uncategorized"));
    appendQueueFact(facts, rightsSummary(item.image.rights));
    appendQueueFact(facts, item.assigned_reviewer?.display_name || "Unassigned");
    const status = document.createElement("small");
    status.className = "admin-review-list-status";
    status.dataset.status = item.status;
    status.textContent = displayStatus(item.status);
    content.append(title, meta, facts, status);

    const chevron = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    chevron.classList.add("ui-icon", "admin-review-list-chevron");
    chevron.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#icon-chevron");
    chevron.append(use);
    button.append(media, content, chevron);
    entry.append(button);
    listElement.append(entry);
  });
  listCount.textContent = `${queueItems.length} of ${queueTotal}`;
  loadMoreButton.hidden = queueItems.length >= queueTotal;
  loadMoreButton.disabled = queueLoading || mutationBusy;
}

async function loadQueue({ append = false, skipDetail = false, selectFirst = true } = {}) {
  if (append && queueLoading) return;
  queueController?.abort();
  const controller = new AbortController();
  queueController = controller;
  const serial = ++queueRequestSerial;
  const requestedStatus = queueStatus;
  const requestedAssignment = queueAssignment;
  const requestedOffset = append ? queueOffset : 0;
  queueLoading = true;
  setQueueBusy(true);
  if (!append) {
    queueOffset = 0;
    setListState("Loading submissions", "loading");
  }
  try {
    const params = new URLSearchParams({
      status: requestedStatus,
      assignment: requestedAssignment,
      limit: "30",
      offset: String(requestedOffset),
    });
    const result = await reviewRequest(`/api/admin/review-submissions?${params}`, { signal: controller.signal });
    if (serial !== queueRequestSerial || requestedStatus !== queueStatus || requestedAssignment !== queueAssignment) return;
    queueActor = result.actor || null;
    const nextItems = Array.isArray(result.items) ? result.items : [];
    if (append) {
      const seen = new Set(queueItems.map((item) => item.id));
      queueItems = [...queueItems, ...nextItems.filter((item) => !seen.has(item.id))];
    } else {
      queueItems = nextItems;
    }
    queueOffset = queueItems.length;
    queueTotal = Number.isInteger(result.pagination?.total) ? result.pagination.total : queueItems.length;
    renderMetrics(result.counts || {});
    renderQueueItems();
    if (queueItems.length) {
      setListState("");
      filterSummary.textContent = `${queueTotal} submission${queueTotal === 1 ? "" : "s"}`;
    } else {
      setListState("No submissions match this filter.", "empty", { action: "refresh", actionLabel: "Refresh queue" });
      filterSummary.textContent = "No submissions";
    }

    if (selectFirst && !selectedId && queueItems[0]) {
      selectedId = queueItems[0].id;
      syncRoute();
      renderQueueItems();
    }
    const selectedQueueItem = queueItems.find((item) => item.id === selectedId);
    if (!skipDetail && selectedQueueItem) setMobileReviewView("detail");
    if (!skipDetail && selectedQueueItem && reviewerMustStart(selectedQueueItem)) {
      setDetailState("Ready to begin review", "empty", {
        message: "Start the review to claim this submission before its private evidence is opened.",
        action: "start-selected",
        actionLabel: "Start review",
      });
    } else if (!skipDetail && selectedQueueItem && reviewerCannotOpen(selectedQueueItem)) {
      setDetailState("Private detail restricted", "empty", {
        message: "Reviewer access is limited to active submissions currently assigned to you.",
      });
    } else if (!skipDetail && selectedId) {
      await loadDetail(selectedId);
    } else if (!skipDetail && !queueItems.length) {
      setDetailState("No submission selected", "empty", {
        message: "Adjust the filters or refresh the queue when new work arrives.",
        action: "refresh",
        actionLabel: "Refresh queue",
      });
    }
  } catch (error) {
    if (isAbortError(error) || serial !== queueRequestSerial) return;
    setListState(error.message || "The review queue could not be loaded.", "error", { action: "retry" });
    if (!selectedDetail) {
      setDetailState("Review queue unavailable", "error", {
        message: "Check the connection, then try loading the queue again.",
        action: "queue-retry",
      });
    }
    handleRequestError(error);
  } finally {
    if (serial === queueRequestSerial) {
      queueLoading = false;
      setQueueBusy(false);
    }
  }
}

function appendDefinition(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = displayValue(value);
  list.append(term, description);
}

function isPureReviewer(actor) {
  const roles = new Set(actor?.roles || []);
  return roles.has("reviewer") && !roles.has("admin") && !roles.has("super_admin");
}

function reviewerMustStart(item) {
  const assignedId = item?.assigned_reviewer?.id || "";
  return Boolean(
    item
      && isPureReviewer(queueActor)
      && item.status === "submitted"
      && (!assignedId || assignedId === queueActor.id),
  );
}

function reviewerCannotOpen(item) {
  if (!item || !isPureReviewer(queueActor)) return false;
  const assignedId = item.assigned_reviewer?.id || "";
  const open = ["submitted", "in_review", "escalated"].includes(item.status);
  return !open || (assignedId && assignedId !== queueActor.id);
}

function actionButton(label, action, className, { atomic = false } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `button ${className}`;
  button.dataset.reviewAction = action;
  if (atomic) button.dataset.atomic = "true";
  button.textContent = label;
  button.disabled = mutationBusy;
  return button;
}

function canSuperAdminSelfPublish(detail) {
  return detail?.actor?.can_self_publish === true
    && detail?.owner?.id === detail?.actor?.id
    && detail?.submission?.status === "submitted"
    && !detail?.submission?.assigned_reviewer?.id
    && !detail?.submission?.review_started_at
    && detail?.image?.workflow_status === "submitted"
    && detail?.image?.publication_status !== "published";
}

function renderAssignmentActions(detail) {
  assignmentActions.replaceChildren();
  const submission = detail.submission;
  const actorId = detail.actor.id;
  const assignedId = submission.assigned_reviewer?.id || "";
  if (detail.owner.id === actorId) {
    if (canSuperAdminSelfPublish(detail)) {
      assignmentActions.append(actionButton("Prepare self-publish", "decision", "button-primary"));
      return;
    }
    const note = document.createElement("span");
    note.className = "admin-review-assigned-note";
    note.textContent = assignedId
      ? `Independent review assigned to ${submission.assigned_reviewer.display_name}`
      : "Self-review is not permitted.";
    assignmentActions.append(note);
    return;
  }
  if (assignedId && assignedId !== actorId) {
    const note = document.createElement("span");
    note.className = "admin-review-assigned-note";
    note.textContent = `Assigned to ${submission.assigned_reviewer.display_name}`;
    assignmentActions.append(note);
    return;
  }
  if (submission.status === "in_review" && assignedId === actorId) {
    assignmentActions.append(actionButton("Review decision", "decision", "button-secondary"));
    return;
  }
  if (submission.status !== "submitted") return;
  if (isPureReviewer(detail.actor) && (!assignedId || assignedId === actorId)) {
    assignmentActions.append(actionButton("Start review", "start", "button-primary", { atomic: true }));
    return;
  }
  if (!assignedId) assignmentActions.append(actionButton("Assign to me", "assign", "button-secondary"));
  if (assignedId === actorId) assignmentActions.append(actionButton("Start review", "start", "button-primary"));
}

function renderDetail(detail) {
  selectedDetail = detail;
  hideConflict();
  detailState.hidden = true;
  detailElement.hidden = false;
  const submission = detail.submission;
  const version = detail.image.version;
  detailStatus.textContent = displayStatus(submission.status);
  detailStatus.dataset.status = submission.status;
  detailWaiting.textContent = waitingTime(submission.submitted_at) || formatDate(submission.submitted_at);
  detailTitle.textContent = version.title || detail.image.original_filename || "Untitled Work";
  detailIdentity.textContent = `${detail.owner.display_name} · ${detail.image.original_filename} · Submitted ${formatDate(submission.submitted_at)}`;
  renderAssignmentActions(detail);
  setActualSize(false);
  renderAssets(detail.assets);

  detailContext.replaceChildren();
  appendDefinition(detailContext, "Submission", `#${shortId(submission.id)}`);
  appendDefinition(detailContext, "Image version", `v${version.version_number}`);
  appendDefinition(detailContext, "Policy", submission.policy_version);
  appendDefinition(detailContext, "Owner account", humanizeKey(detail.owner.account_status));
  appendDefinition(detailContext, "Account age", accountAge(detail.owner.created_at));
  appendDefinition(detailContext, "Workflow", humanizeKey(detail.image.workflow_status));
  appendDefinition(detailContext, "Publication", humanizeKey(detail.image.publication_status));
  appendDefinition(detailContext, "Processing", humanizeKey(detail.image.processing_status));
  appendDefinition(
    detailContext,
    "Original dimensions",
    detail.image.original_width && detail.image.original_height
      ? `${detail.image.original_width} × ${detail.image.original_height}`
      : null,
  );

  copyList.replaceChildren();
  appendDefinition(copyList, "Title", version.title);
  appendDefinition(copyList, "Caption", version.caption);
  appendDefinition(copyList, "Description", version.description);
  appendDefinition(copyList, "Alt text", version.alt_text);
  appendDefinition(copyList, "Tags", version.tags.length ? version.tags.join(", ") : null);
  appendDefinition(copyList, "Category", version.content_category);
  appendDefinition(copyList, "Location", version.location_name);
  appendDefinition(copyList, "Captured", version.captured_at ? formatDate(version.captured_at) : null);
  Object.entries(version.public_exif || {}).forEach(([key, value]) => {
    appendDefinition(copyList, `EXIF · ${humanizeKey(key)}`, value);
  });

  rightsList.replaceChildren();
  appendDefinition(rightsList, "Rights declared", version.rights_declared ? "Yes" : "No");
  appendDefinition(
    rightsList,
    "Copyright",
    version.copyright_holder
      ? `${version.copyright_holder}${version.copyright_year ? ` (${version.copyright_year})` : ""}`
      : null,
  );
  appendDefinition(
    rightsList,
    "Recognizable people",
    version.contains_recognizable_people === true
      ? "Yes"
      : version.contains_recognizable_people === false
        ? "No"
        : "Not stated",
  );
  appendDefinition(rightsList, "Model release", humanizeKey(displayValue(version.model_release_status)));
  appendDefinition(rightsList, "Property release", humanizeKey(displayValue(version.property_release_status)));
  appendDefinition(rightsList, "AI disclosure", humanizeKey(displayValue(version.ai_disclosure)));
  appendDefinition(rightsList, "Sensitive content", humanizeKey(displayValue(version.sensitive_content_disclosure)));

  readinessList.replaceChildren();
  (submission.readiness?.checks || []).forEach((check) => {
    const item = document.createElement("li");
    item.dataset.state = check.state;
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.classList.add("ui-icon");
    icon.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", check.state === "pass" ? "#icon-check" : "#icon-shield");
    icon.append(use);
    const text = document.createElement("span");
    text.textContent = `${check.label}: ${check.message}`;
    item.append(icon, text);
    readinessList.append(item);
  });

  historyList.replaceChildren();
  if (!detail.decisions.length) {
    const empty = document.createElement("li");
    empty.className = "admin-review-history-empty";
    empty.textContent = "No decisions recorded.";
    historyList.append(empty);
  } else {
    detail.decisions.forEach((decision) => {
      const item = document.createElement("li");
      const heading = document.createElement("strong");
      heading.textContent = displayDecision(decision.decision);
      const meta = document.createElement("span");
      meta.textContent = `${decision.reviewer.display_name} · ${formatDate(decision.created_at)} · ${decision.reason_codes.map(humanizeKey).join(", ")}`;
      const message = document.createElement("p");
      message.textContent = decision.user_message;
      item.append(heading, meta, message);
      if (decision.internal_note) {
        const internalNote = document.createElement("p");
        internalNote.className = "admin-review-history-internal";
        const internalLabel = document.createElement("b");
        internalLabel.textContent = "Internal note";
        const internalCopy = document.createElement("span");
        internalCopy.textContent = decision.internal_note;
        internalNote.append(internalLabel, internalCopy);
        item.append(internalNote);
      }
      historyList.append(item);
    });
  }

  const assignedToActor = submission.assigned_reviewer?.id === detail.actor.id;
  const canReview = submission.status === "in_review"
    && assignedToActor
    && detail.owner.id !== detail.actor.id;
  const canPublishApproved = detail.actor.can_publish === true
    && submission.status === "approved"
    && detail.image.publication_status !== "published"
    && detail.owner.id !== detail.actor.id;
  const canSelfPublish = canSuperAdminSelfPublish(detail);
  const canDecide = canReview || canPublishApproved || canSelfPublish;
  decisionForm.hidden = !canDecide;
  if (canDecide) setupDecisionForm(detail);
  renderQueueItems();
}

function renderAssets(assets) {
  const order = { original: 0, display: 1, thumbnail: 2 };
  const sorted = [...assets].sort((a, b) => order[a.kind] - order[b.kind]);
  if (!sorted.some((asset) => asset.kind === activeAssetKind)) {
    activeAssetKind = sorted.some((asset) => asset.kind === "display") ? "display" : sorted[0]?.kind;
  }
  assetSwitcher.replaceChildren();
  sorted.forEach((asset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `admin-review-asset-button${asset.kind === activeAssetKind ? " is-active" : ""}`;
    button.dataset.assetKind = asset.kind;
    button.textContent = humanizeKey(asset.kind);
    button.setAttribute("aria-pressed", String(asset.kind === activeAssetKind));
    assetSwitcher.append(button);
  });
  const active = sorted.find((asset) => asset.kind === activeAssetKind) || sorted[0];
  if (!active) {
    reviewImage.removeAttribute("src");
    imageError.hidden = false;
    return;
  }
  imageError.hidden = true;
  reviewImage.hidden = false;
  reviewImage.src = active.signed_url;
  reviewImage.alt = selectedDetail?.image.version.alt_text || selectedDetail?.image.version.title || "Submitted work";
  reviewImageStage.dataset.assetKind = active.kind;
  assetMeta.replaceChildren();
  appendDefinition(assetMeta, "Variant", humanizeKey(active.kind));
  appendDefinition(assetMeta, "Dimensions", `${active.width} × ${active.height}`);
  appendDefinition(assetMeta, "Size", active.byte_size ? `${Math.round(active.byte_size / 1024)} KB` : null);
  appendDefinition(assetMeta, "MIME", active.mime_type);
  appendDefinition(assetMeta, "Scan", humanizeKey(displayValue(active.scan_status)));
  appendDefinition(assetMeta, "Scan result", humanizeKey(displayValue(active.scan_result_code)));
  appendDefinition(assetMeta, "Scan policy", active.scan_policy_version);
  appendDefinition(assetMeta, "SHA-256", active.checksum_sha256);
}

async function loadDetail(id, { focus = false } = {}) {
  if (!id) {
    setDetailState("Select a submission", "empty", {
      message: "Choose a queue item to inspect its immutable submission evidence.",
    });
    return;
  }
  setMobileReviewView("detail");
  detailController?.abort();
  const controller = new AbortController();
  detailController = controller;
  const serial = ++detailRequestSerial;
  selectedId = id;
  selectedDetail = null;
  syncRoute();
  renderQueueItems();
  setDetailBusy(true);
  setDetailState("Loading submission", "loading", { message: "Preparing private assets and review evidence." });
  try {
    const detail = await reviewRequest(`/api/admin/review-submissions/${encodeURIComponent(id)}`, { signal: controller.signal });
    if (serial !== detailRequestSerial || selectedId !== id) return;
    renderDetail(detail);
    syncRoute();
    if (focus) detailTitle.focus({ preventScroll: true });
  } catch (error) {
    if (isAbortError(error) || serial !== detailRequestSerial) return;
    setDetailState("Submission unavailable", "error", {
      message: error.message || "The submission could not be loaded.",
      action: "detail-retry",
      actionLabel: "Retry submission",
    });
    handleRequestError(error);
  } finally {
    if (serial === detailRequestSerial) setDetailBusy(false);
  }
}

function setupDecisionForm(detail) {
  decisionSelect.replaceChildren();
  const selfPublish = canSuperAdminSelfPublish(detail);
  const publishOnly = detail.submission.status === "approved";
  const decisions = selfPublish
    ? [["approve_and_publish", "Approve and publish"]]
    : publishOnly ? [] : [
      ["request_changes", "Request changes"],
      ["reject", "Reject"],
      ["approve", "Approve"],
    ];
  if (!selfPublish && detail.actor.can_publish === true) {
    decisions.push(["approve_and_publish", publishOnly ? "Publish approved work" : "Approve and publish"]);
  }
  decisions.forEach(([value, label]) => decisionSelect.add(new Option(label, value)));
  checklist.replaceChildren();
  CHECKLIST_ITEMS.forEach(([code, label]) => {
    const wrapper = document.createElement("label");
    wrapper.className = "admin-review-check-item";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = code;
    input.value = "true";
    const text = document.createElement("span");
    text.textContent = label;
    wrapper.append(input, text);
    checklist.append(wrapper);
  });
  decisionForm.reset();
  renderReasonOptions();
  checklist.querySelectorAll("input").forEach((input) => {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  });
  delete formNotice.dataset.tone;
  formNotice.textContent = selfPublish
    ? "Super Admin self-publish is restricted to this untouched submission and creates immutable audit evidence."
    : publishOnly
    ? "Publishing makes this work immediately visible in Works and on the creator's public profile."
    : "Complete each policy check before submitting a decision.";
  decisionSubmit.disabled = mutationBusy;
}

function renderReasonOptions() {
  const options = REASONS[decisionSelect.value] || [];
  reasonSelect.replaceChildren();
  options.forEach(([value, label]) => reasonSelect.add(new Option(label, value)));
}

function openDialog(pending, title, message) {
  if (mutationBusy) return;
  pendingDialogAction = pending;
  dialogOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  dialogTitle.textContent = title;
  dialogMessage.textContent = message;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  window.requestAnimationFrame(() => dialogCancel.focus());
}

function restoreDialogFocus() {
  const opener = dialogOpener;
  dialogOpener = null;
  window.requestAnimationFrame(() => {
    if (opener?.isConnected) opener.focus();
  });
}

function closeDialog({ restoreFocus = true } = {}) {
  pendingDialogAction = null;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
  if (restoreFocus) restoreDialogFocus();
}

function mutationEndpoint(action) {
  if (action === "assign") return "assign";
  if (action === "start") return "start";
  return action.replaceAll("_", "-");
}

async function mutateReview(
  action,
  body,
  {
    submissionId = selectedDetail?.submission.id || selectedId,
    successMessage = "Review state updated.",
    refresh = true,
  } = {},
) {
  if (mutationBusy || !submissionId) return false;
  setMutationBusy(true);
  hideConflict();
  try {
    await reviewRequest(`/api/admin/review-submissions/${encodeURIComponent(submissionId)}/${mutationEndpoint(action)}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    showToast(successMessage, "success");
    if (refresh) {
      const closesPrivateDetail = ["request_changes", "reject", "approve"].includes(action)
        && isPureReviewer(selectedDetail?.actor || queueActor);
      if (closesPrivateDetail) {
        detailController?.abort();
        detailRequestSerial += 1;
        selectedId = "";
        selectedDetail = null;
        activeAssetKind = "display";
        syncRoute();
        await loadQueue({ skipDetail: true, selectFirst: false });
        setDetailState("Decision recorded", "empty", {
          message: "Private access closed. Select the next submission when you are ready.",
          action: queueItems.length ? "review-next" : "",
          actionLabel: "Review next submission",
        });
        renderQueueItems();
        window.requestAnimationFrame(() => detailStateTitle.focus({ preventScroll: true }));
      } else {
        await loadQueue({ skipDetail: true });
        await loadDetail(submissionId);
      }
    }
    return true;
  } catch (error) {
    if (CONFLICT_CODES.has(error.code)) {
      const message = `${error.message || "This submission changed."} Reload the current evidence before continuing.`;
      if (detailElement.hidden) {
        setDetailState("Submission changed", "error", {
          message,
          action: "detail-retry",
          actionLabel: "Reload submission",
        });
      } else {
        showConflict(message);
      }
      formNotice.dataset.tone = "error";
      formNotice.textContent = message;
    }
    handleRequestError(error);
    return false;
  } finally {
    setMutationBusy(false);
  }
}

function currentChecklist() {
  return Object.fromEntries(
    CHECKLIST_ITEMS.map(([code]) => [code, checklist.querySelector(`[name="${code}"]`)?.checked === true]),
  );
}

function submitDecision() {
  if (!selectedDetail || mutationBusy) return;
  const checklistResult = currentChecklist();
  if (Object.values(checklistResult).some((value) => !value)) {
    checklist.querySelectorAll("input").forEach((input) => {
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
    });
    formNotice.textContent = "Complete every policy checklist item before submitting.";
    formNotice.dataset.tone = "error";
    const firstMissing = checklist.querySelector("input:not(:checked)");
    firstMissing?.setAttribute("aria-invalid", "true");
    firstMissing?.setAttribute("aria-describedby", formNotice.id);
    firstMissing?.focus();
    return;
  }
  if (!decisionForm.reportValidity()) return;
  checklist.querySelectorAll("input").forEach((input) => {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  });
  delete formNotice.dataset.tone;
  const decision = decisionSelect.value;
  const selfPublish = decision === "approve_and_publish" && canSuperAdminSelfPublish(selectedDetail);
  const action = selfPublish ? "super_admin_self_publish" : decision;
  const body = {
    confirmation: `review-${action.replaceAll("_", "-")}`,
    expected_version: selectedDetail.submission.lock_version,
    idempotency_key: createIdempotencyKey(),
    reason_codes: [reasonSelect.value],
    user_message: decisionForm.elements.user_message.value.trim(),
    internal_note: decisionForm.elements.internal_note.value.trim(),
    checklist_result: checklistResult,
  };
  openDialog(
    { action, body, submissionId: selectedDetail.submission.id },
    `Confirm ${displayDecision(decision).toLowerCase()}`,
    selfPublish
      ? "This uses the explicit Super Admin exception for your own untouched submission, records immutable audit evidence, and immediately publishes the work."
      : decision === "approve_and_publish"
      ? "This records an immutable approval decision and immediately publishes the work in Works and on the creator's public profile."
      : "The decision, reason, checklist, and user message will be written to immutable review history.",
  );
}

async function confirmPendingAction() {
  if (mutationBusy) return;
  const pending = pendingDialogAction;
  const opener = dialogOpener;
  dialogOpener = null;
  closeDialog({ restoreFocus: false });
  if (!pending) return;
  await mutateReview(pending.action, pending.body, {
    submissionId: pending.submissionId,
    successMessage: pending.successMessage || "Review state updated.",
  });
  window.requestAnimationFrame(() => {
    if (opener?.isConnected && !opener.hidden && !opener.disabled && opener.getClientRects().length) opener.focus();
    else if (!detailElement.hidden) detailTitle.focus({ preventScroll: true });
  });
}

function setActualSize(actual) {
  reviewImageStage.classList.toggle("is-actual-size", actual);
  sizeToggle.setAttribute("aria-pressed", String(actual));
  sizeToggle.setAttribute("aria-label", actual ? "Fit image to preview" : "Show image at actual size");
  sizeToggle.title = actual ? "Fit image to preview" : "Show actual size";
}

async function openQueueSubmission(item) {
  if (!item || mutationBusy) return;
  setMobileReviewView("detail", { scroll: true });
  selectedId = item.id;
  syncRoute();
  renderQueueItems();
  if (!reviewerMustStart(item)) {
    if (reviewerCannotOpen(item)) {
      setDetailState("Private detail restricted", "empty", {
        message: "Reviewer access is limited to active submissions currently assigned to you.",
      });
      return;
    }
    await loadDetail(item.id, { focus: true });
    return;
  }
  setDetailState("Claiming submission", "loading", {
    message: "Starting the review atomically before private evidence is opened.",
  });
  setDetailBusy(true);
  const started = await mutateReview(
    "start",
    { confirmation: "start-review", expected_version: item.lock_version },
    {
      submissionId: item.id,
      successMessage: "Review started and assigned to you.",
      refresh: false,
    },
  );
  if (started) {
    await loadDetail(item.id, { focus: true });
    await loadQueue({ skipDetail: true });
  }
  setDetailBusy(false);
}

async function reloadSelected() {
  hideConflict();
  await loadQueue({ skipDetail: true });
  const item = queueItems.find((entry) => entry.id === selectedId);
  if (item && reviewerMustStart(item)) {
    setDetailState("Ready to begin review", "empty", {
      message: "Start the review to claim this submission before its private evidence is opened.",
      action: "start-selected",
      actionLabel: "Start review",
    });
  } else if (item && reviewerCannotOpen(item)) {
    setDetailState("Private detail restricted", "empty", {
      message: "Reviewer access is limited to active submissions currently assigned to you.",
    });
  } else if (selectedId) {
    await loadDetail(selectedId, { focus: true });
  }
}

document.querySelectorAll("[data-status-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    const nextStatus = button.dataset.statusFilter;
    if (queueStatus === nextStatus || !FILTER_STATUSES.has(nextStatus)) return;
    queueStatus = nextStatus;
    selectedId = "";
    selectedDetail = null;
    syncRoute();
    setMobileReviewView("queue", { scroll: true });
    loadQueue({ selectFirst: !isMobileReviewLayout() });
  });
});

filterForm.addEventListener("change", (event) => {
  if (event.target.name !== "assignment" || !FILTER_ASSIGNMENTS.has(event.target.value)) return;
  queueAssignment = event.target.value;
  selectedId = "";
  selectedDetail = null;
  syncRoute();
  setMobileReviewView("queue", { scroll: true });
  loadQueue({ selectFirst: !isMobileReviewLayout() });
});

listElement.addEventListener("click", (event) => {
  const button = event.target.closest("[data-review-submission]");
  if (!button) return;
  const item = queueItems.find((entry) => entry.id === button.dataset.reviewSubmission);
  openQueueSubmission(item);
});

loadMoreButton.addEventListener("click", () => loadQueue({ append: true, skipDetail: true }));
refreshButton.addEventListener("click", reloadSelected);
sizeToggle.addEventListener("click", () => setActualSize(!reviewImageStage.classList.contains("is-actual-size")));

assetSwitcher.addEventListener("click", (event) => {
  const button = event.target.closest("[data-asset-kind]");
  if (!button || !selectedDetail) return;
  activeAssetKind = button.dataset.assetKind;
  renderAssets(selectedDetail.assets);
});

assignmentActions.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-review-action]");
  if (!button || !selectedDetail || mutationBusy) return;
  const action = button.dataset.reviewAction;
  if (action === "decision") {
    decisionForm.scrollIntoView({ block: "start", behavior: "smooth" });
    window.setTimeout(() => decisionSelect.focus({ preventScroll: true }), 220);
    return;
  }
  const body = {
    confirmation: action === "assign" ? "assign-to-me" : "start-review",
    expected_version: selectedDetail.submission.lock_version,
  };
  if (button.dataset.atomic === "true") {
    await mutateReview(action, body, {
      submissionId: selectedDetail.submission.id,
      successMessage: "Review started and assigned to you.",
    });
    return;
  }
  openDialog(
    { action, body, submissionId: selectedDetail.submission.id },
    action === "assign" ? "Assign this submission to you?" : "Start this review?",
    action === "assign"
      ? "The submission will move into your reviewer queue."
      : "The review timer will start and the assignment will be locked to you.",
  );
});

decisionSelect.addEventListener("change", renderReasonOptions);
checklist.addEventListener("change", (event) => {
  const input = event.target.closest('input[type="checkbox"]');
  if (!input || !input.checked) return;
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-describedby");
  if (!checklist.querySelector("input:not(:checked)")) {
    delete formNotice.dataset.tone;
    formNotice.textContent = "All policy checklist items are complete.";
  }
});
decisionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitDecision();
});

listRetryButton.addEventListener("click", () => loadQueue());
detailRetryButton.addEventListener("click", () => {
  const action = detailRetryButton.dataset.action;
  if (action === "queue-retry" || action === "refresh") {
    loadQueue();
    return;
  }
  if (action === "start-selected") {
    openQueueSubmission(queueItems.find((item) => item.id === selectedId));
    return;
  }
  if (action === "review-next") {
    openQueueSubmission(queueItems[0]);
    return;
  }
  if (selectedId) loadDetail(selectedId, { focus: true });
});
conflictReloadButton.addEventListener("click", reloadSelected);
imageRetryButton.addEventListener("click", () => selectedId && loadDetail(selectedId));
backToQueueButton.addEventListener("click", () => {
  setMobileReviewView("queue", { focusQueue: true, scroll: true });
});

reviewImage.addEventListener("load", () => {
  imageError.hidden = true;
  reviewImage.hidden = false;
});
reviewImage.addEventListener("error", () => {
  reviewImage.hidden = true;
  imageError.hidden = false;
});

dialogCancel.addEventListener("click", () => closeDialog());
dialogConfirm.addEventListener("click", confirmPendingAction);
dialog.addEventListener("cancel", () => {
  pendingDialogAction = null;
  window.setTimeout(restoreDialogFocus, 0);
});

renderMetrics({});
loadQueue();
