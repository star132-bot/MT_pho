const dashboardLoading = document.querySelector("[data-dashboard-loading]");
const dashboardContent = document.querySelector("[data-dashboard-content]");
const dashboardError = document.querySelector("[data-dashboard-error]");
const dashboardRetry = document.querySelector("[data-dashboard-retry]");
const dashboardLive = document.querySelector("[data-dashboard-live]");
const dashboardTabs = Array.from(document.querySelectorAll("[data-dashboard-tab]"));
const dashboardPanels = Array.from(document.querySelectorAll("[data-dashboard-panel]"));
let dashboardController = null;
let dashboardRequestSerial = 0;

function cleanText(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function displayValue(value) {
  return cleanText(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function initials(value) {
  const parts = cleanText(value || "MT").split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
}

function formatDate(value, includeTime = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en", includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(date);
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const amount = bytes / (1024 ** index);
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: index > 1 ? 1 : 0 }).format(amount)} ${units[index]}`;
}

function announce(message) {
  dashboardLive.textContent = "";
  window.setTimeout(() => { dashboardLive.textContent = message; }, 20);
}

function icon(symbol) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ui-icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${symbol}`);
  svg.append(use);
  return svg;
}

function emptyState(title, message, action = null) {
  const state = document.createElement("div");
  state.className = "dashboard-empty-state";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const copy = document.createElement("p");
  copy.textContent = message;
  state.append(heading, copy);
  if (action) {
    const link = document.createElement("a");
    link.href = action.href;
    link.textContent = action.label;
    state.append(link);
  }
  return state;
}

function setActiveTab(name, focus = false) {
  dashboardTabs.forEach((tab) => {
    const active = tab.dataset.dashboardTab === name;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
  });
  dashboardPanels.forEach((panel) => {
    panel.hidden = panel.dataset.dashboardPanel !== name;
  });
}

async function dashboardRequest(path, signal) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error?.message || "Dashboard data is unavailable.");
    error.status = response.status;
    error.code = payload.error?.code || "DASHBOARD_REQUEST_FAILED";
    throw error;
  }
  return payload;
}

function renderProfile(payload) {
  const profile = payload.profile || {};
  const account = payload.account || {};
  const displayName = profile.display_name || payload.user?.display_name || "Member";
  document.querySelector("[data-dashboard-initials]").textContent = initials(displayName);
  document.querySelector("[data-dashboard-name]").textContent = displayName;
  document.querySelector("[data-dashboard-email]").textContent = account.email || payload.user?.email || "";
  document.querySelector("[data-dashboard-account-status]").textContent = `${displayValue(account.account_status || "active")} account`;
  document.querySelector("[data-dashboard-verification]").textContent = account.email_verified ? "Email verified" : "Email verification pending";
  document.querySelector("[data-dashboard-bio]").textContent = cleanText(profile.bio) || "No bio has been added yet.";
}

function renderStatusCounts(counts) {
  const target = document.querySelector("[data-dashboard-status-grid]");
  target.replaceChildren();
  [
    ["drafts", "Drafts"],
    ["submitted", "Submitted"],
    ["changes_requested", "Changes requested"],
    ["published", "Published"],
    ["unpublished", "Unpublished"],
  ].forEach(([key, label]) => {
    const item = document.createElement("div");
    item.dataset.status = key;
    const term = document.createElement("dt");
    term.textContent = label;
    const value = document.createElement("dd");
    value.textContent = String(counts?.[key] ?? 0);
    item.append(term, value);
    target.append(item);
  });
}

function imageThumbnail(image) {
  const figure = document.createElement("figure");
  figure.className = "dashboard-image-thumbnail";
  if (image.thumbnail?.signed_url) {
    const preview = document.createElement("img");
    preview.src = image.thumbnail.signed_url;
    preview.alt = "";
    preview.decoding = "async";
    figure.append(preview);
  } else {
    figure.append(icon("icon-photo"));
  }
  return figure;
}

function imageRow(image) {
  const row = document.createElement("a");
  row.className = "dashboard-image-row";
  row.href = "/workspace/images";
  row.append(imageThumbnail(image));
  const copy = document.createElement("span");
  copy.className = "dashboard-image-copy";
  const title = document.createElement("strong");
  title.textContent = cleanText(image.title) || "Untitled Work";
  const meta = document.createElement("small");
  meta.textContent = `${displayValue(image.workflow_status)} / Updated ${formatDate(image.updated_at)}`;
  copy.append(title, meta);
  const status = document.createElement("em");
  status.dataset.status = image.workflow_status;
  status.textContent = displayValue(image.publication_status);
  row.append(copy, status);
  return row;
}

function renderRecent(images) {
  const target = document.querySelector("[data-dashboard-recent]");
  target.replaceChildren();
  if (!images.length) {
    target.append(emptyState("No images yet", "Import an image to begin your private Workspace.", { href: "/workspace/images", label: "Import images" }));
    return;
  }
  const list = document.createElement("div");
  list.className = "dashboard-image-list";
  images.forEach((image) => list.append(imageRow(image)));
  target.append(list);
}

function renderAttention(items) {
  const target = document.querySelector("[data-dashboard-attention]");
  target.replaceChildren();
  if (!items.length) {
    target.append(emptyState("Nothing requires action", "Processing and review requests will appear here."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "dashboard-attention-list";
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.dataset.type = item.type;
    entry.append(icon("icon-alert"));
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.title;
    const message = document.createElement("p");
    message.textContent = item.message;
    const date = document.createElement("small");
    date.textContent = formatDate(item.updated_at, true);
    copy.append(title, message, date);
    const link = document.createElement("a");
    link.href = item.workspace_path;
    link.setAttribute("aria-label", `Open ${item.title} in Workspace`);
    link.append(icon("icon-arrow-right"));
    entry.append(copy, link);
    list.append(entry);
  });
  target.append(list);
}

function renderActivity(items) {
  const target = document.querySelector("[data-dashboard-activity]");
  target.replaceChildren();
  if (!items.length) {
    target.append(emptyState("No review activity", "Submitted works and reviewer decisions will appear here."));
    return;
  }
  const list = document.createElement("ol");
  list.className = "dashboard-activity-list";
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.append(icon("icon-clock"));
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.title;
    const state = document.createElement("p");
    state.textContent = item.decision ? displayValue(item.decision) : displayValue(item.status);
    const date = document.createElement("small");
    date.textContent = formatDate(item.occurred_at, true);
    copy.append(title, state, date);
    entry.append(copy);
    list.append(entry);
  });
  target.append(list);
}

function renderStorage(usage, capabilities) {
  const target = document.querySelector("[data-dashboard-storage]");
  target.replaceChildren();
  const list = document.createElement("dl");
  list.className = "dashboard-storage-list";
  [
    ["Stored assets", String(usage.asset_count)],
    ["Images with assets", String(usage.image_count)],
    ["Space used", formatBytes(usage.used_bytes)],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    item.append(term, detail);
    list.append(item);
  });
  const note = document.createElement("p");
  note.className = "dashboard-storage-note";
  note.textContent = capabilities.storage_quota?.available
    ? "Storage quota is available."
    : "No storage quota is configured, so remaining capacity is unknown.";
  target.append(list, note);
}

function renderDrafts(images) {
  const target = document.querySelector("[data-dashboard-drafts]");
  target.replaceChildren();
  if (!images.length) {
    target.append(emptyState("No editable drafts", "Import images or open the Workspace to prepare a new work.", { href: "/workspace/images", label: "Open Workspace" }));
    return;
  }
  images.forEach((image) => {
    const card = document.createElement("a");
    card.className = "dashboard-draft-card";
    card.href = "/workspace/images";
    card.append(imageThumbnail(image));
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = image.title;
    const status = document.createElement("small");
    status.textContent = `${displayValue(image.workflow_status)} / ${formatDate(image.updated_at)}`;
    copy.append(title, status);
    card.append(copy);
    target.append(card);
  });
}

function renderDashboard(payload) {
  renderStatusCounts(payload.status_counts || {});
  renderAttention(Array.isArray(payload.needs_attention) ? payload.needs_attention : []);
  renderRecent(Array.isArray(payload.recent_images) ? payload.recent_images : []);
  renderActivity(Array.isArray(payload.review_activity) ? payload.review_activity : []);
  renderStorage(payload.storage_usage || {}, payload.capabilities || {});
  renderDrafts(Array.isArray(payload.drafts) ? payload.drafts : []);
  document.querySelector("[data-dashboard-generated]").textContent = `Updated ${formatDate(payload.generated_at, true)}`;
  document.querySelector("[data-dashboard-public-note]").hidden = payload.capabilities?.public_portfolio?.available === true;
}

function showDashboardError(error) {
  const permissionError = error.status === 403 && error.code === "ACCOUNT_RESTRICTED";
  document.querySelector("[data-dashboard-error-title]").textContent = permissionError
    ? "Dashboard access is unavailable for this account."
    : "We could not load your account overview.";
  document.querySelector("[data-dashboard-error-message]").textContent = error.message || "Try the request again.";
  dashboardRetry.hidden = permissionError;
  dashboardLoading.hidden = true;
  dashboardContent.hidden = true;
  dashboardError.hidden = false;
  dashboardError.focus();
}

async function loadDashboard() {
  dashboardController?.abort();
  dashboardController = new AbortController();
  const requestId = ++dashboardRequestSerial;
  dashboardLoading.hidden = false;
  dashboardContent.hidden = true;
  dashboardError.hidden = true;
  document.querySelector(".dashboard-shell").setAttribute("aria-busy", "true");
  try {
    const [profile, dashboard] = await Promise.all([
      dashboardRequest("/api/me/profile", dashboardController.signal),
      dashboardRequest("/api/dashboard", dashboardController.signal),
    ]);
    if (requestId !== dashboardRequestSerial) return;
    renderProfile(profile);
    renderDashboard(dashboard);
    dashboardLoading.hidden = true;
    dashboardContent.hidden = false;
    announce("Dashboard loaded.");
  } catch (error) {
    if (error.name === "AbortError" || requestId !== dashboardRequestSerial) return;
    if (error.status === 401) {
      window.location.assign("/auth/sign-in?next=%2Fdashboard");
      return;
    }
    if (error.status === 403 && error.code === "MFA_REQUIRED") {
      window.location.assign("/auth/mfa?next=%2Fdashboard");
      return;
    }
    showDashboardError(error);
  } finally {
    if (requestId === dashboardRequestSerial) document.querySelector(".dashboard-shell").removeAttribute("aria-busy");
  }
}

dashboardTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => setActiveTab(tab.dataset.dashboardTab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? dashboardTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + dashboardTabs.length) % dashboardTabs.length;
    setActiveTab(dashboardTabs[nextIndex].dataset.dashboardTab, true);
  });
});

document.querySelector("[data-dashboard-open-works]").addEventListener("click", () => setActiveTab("works", true));
dashboardRetry.addEventListener("click", loadDashboard);
window.addEventListener("pagehide", () => dashboardController?.abort(), { once: true });

loadDashboard();
