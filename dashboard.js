const dashboardLoading = document.querySelector("[data-dashboard-loading]");
const dashboardContent = document.querySelector("[data-dashboard-content]");
const dashboardError = document.querySelector("[data-dashboard-error]");
const dashboardRetry = document.querySelector("[data-dashboard-retry]");
const dashboardLive = document.querySelector("[data-dashboard-live]");
const dashboardTabs = Array.from(document.querySelectorAll("[data-dashboard-tab]"));
const dashboardPanels = Array.from(document.querySelectorAll("[data-dashboard-panel]"));
const dashboardCoverImage = document.querySelector("[data-dashboard-cover-image]");
const dashboardCoverOpen = document.querySelector("[data-dashboard-cover-open]");
const dashboardCoverStatus = document.querySelector("[data-dashboard-cover-status]");
const dashboardCoverDialog = document.querySelector("[data-dashboard-cover-dialog]");
const dashboardCoverDialogState = document.querySelector("[data-dashboard-cover-dialog-state]");
const dashboardCoverCandidates = document.querySelector("[data-dashboard-cover-candidates]");
const dashboardCoverEmpty = document.querySelector("[data-dashboard-cover-empty]");
const dashboardCoverActions = document.querySelector("[data-dashboard-cover-actions]");
const dashboardCoverUpload = document.querySelector("[data-dashboard-cover-upload]");
const dashboardCoverFile = document.querySelector("[data-dashboard-cover-file]");
const dashboardCoverSave = document.querySelector("[data-dashboard-cover-save]");
const dashboardCoverRemove = document.querySelector("[data-dashboard-cover-remove]");
const dashboardCoverCancel = document.querySelector("[data-dashboard-cover-cancel]");
const dashboardCoverClose = document.querySelector("[data-dashboard-cover-close]");
const DEFAULT_COVER_URL = "/assets/art/hero-concrete.jpg";
const COVER_UPLOAD_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const COVER_UPLOAD_MAX_BYTES = 50 * 1024 * 1024;
const COVER_ASSET_MAX_BYTES = { original: 50 * 1024 * 1024, display: 20 * 1024 * 1024, thumbnail: 10 * 1024 * 1024 };
const COVER_SCAN_ATTEMPTS = 45;
const COVER_SCAN_DELAY = 2000;
let dashboardController = null;
let dashboardRequestSerial = 0;
let dashboardCsrfTokenPromise = null;
let coverController = null;
let coverData = { cover: null, candidates: [] };
let selectedCoverId = null;
let coverBusy = false;
let coverReturnFocus = null;
let coverUploadController = null;
let coverUploadIntentId = null;

function cleanText(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function displayValue(value) {
  return cleanText(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function initials(value) {
  const parts = cleanText(value || "MT").split(/\s+/).filter(Boolean);
  if (parts[0]?.toUpperCase() === "MT") return "MT";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
}

function safeMediaUrl(value) {
  const source = cleanText(value);
  if (!source) return "";
  try {
    const url = new URL(source, window.location.origin);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.href;
  } catch (_error) {
    return "";
  }
}

function displayCountry(value) {
  const code = cleanText(value).toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return "Not set";
  try {
    return new Intl.DisplayNames([document.documentElement.lang || "en"], { type: "region" }).of(code) || code;
  } catch (_error) {
    return code;
  }
}

function websiteLabel(value) {
  const url = safeMediaUrl(value);
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (_error) {
    return cleanText(value);
  }
}

function availabilityLabel(value) {
  return {
    open: "Open to work",
    limited: "Limited availability",
    unavailable: "Not available",
  }[cleanText(value)] || "Not set";
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

async function dashboardCsrfToken(force = false) {
  if (force) dashboardCsrfTokenPromise = null;
  if (!dashboardCsrfTokenPromise) {
    dashboardCsrfTokenPromise = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
      return payload.csrf_token;
    }).catch((error) => {
      dashboardCsrfTokenPromise = null;
      throw error;
    });
  }
  return dashboardCsrfTokenPromise;
}

async function dashboardApiMutation(path, { method = "PATCH", body = {}, signal } = {}, retryCsrf = true) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": await dashboardCsrfToken(),
    },
    body: JSON.stringify(body),
    signal,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await dashboardCsrfToken(true);
    return dashboardApiMutation(path, { method, body, signal }, false);
  }
  if (!response.ok) {
    const error = new Error(payload.error?.message || "The request could not be completed.");
    error.status = response.status;
    error.code = payload.error?.code || "DASHBOARD_MUTATION_FAILED";
    throw error;
  }
  return payload;
}

function dashboardMutation(path, body, retryCsrf = true) {
  return dashboardApiMutation(path, { method: "PATCH", body }, retryCsrf);
}

function renderProfile(payload) {
  const profile = payload.profile || {};
  const account = payload.account || {};
  const displayName = profile.display_name || payload.user?.display_name || "Member";
  document.querySelector("[data-dashboard-initials]").textContent = initials(displayName);
  document.querySelector("[data-dashboard-name]").textContent = displayName;
  document.querySelector("[data-dashboard-cover-name]").textContent = displayName;
  document.querySelector("[data-dashboard-email]").textContent = account.email || payload.user?.email || "";
  document.querySelector("[data-dashboard-account-status]").textContent = `${displayValue(account.account_status || "active")} account`;
  document.querySelector("[data-dashboard-verification]").textContent = account.email_verified ? "Email verified" : "Email verification pending";
  document.querySelector("[data-dashboard-bio]").textContent = cleanText(profile.bio) || "No bio has been added yet.";

  const avatar = document.querySelector("[data-dashboard-avatar-image]");
  const avatarUrl = safeMediaUrl(profile.avatar_url);
  const initialText = document.querySelector("[data-dashboard-initials]");
  if (avatarUrl) {
    avatar.src = avatarUrl;
    avatar.hidden = false;
    initialText.hidden = true;
    avatar.addEventListener("error", () => {
      avatar.hidden = true;
      initialText.hidden = false;
    }, { once: true });
  } else {
    avatar.hidden = true;
    initialText.hidden = false;
  }

  const country = displayCountry(profile.country_code);
  const city = cleanText(profile.city);
  const timezone = cleanText(profile.timezone);
  const location = [city, country === "Not set" ? "" : country].filter(Boolean).join(", ") || "Not set";
  document.querySelector("[data-dashboard-location]").textContent = location === "Not set" ? "Location not set" : location;
  document.querySelector("[data-dashboard-region]").textContent = location;
  document.querySelector("[data-dashboard-timezone]").textContent = timezone || "Timezone not set";
  document.querySelector("[data-dashboard-availability]").textContent = availabilityLabel(profile.availability_status);

  const professionalHeadline = cleanText(profile.professional_headline);
  const company = cleanText(profile.company);
  document.querySelector("[data-dashboard-headline]").textContent = professionalHeadline || "Artist profile";
  document.querySelector("[data-dashboard-professional]").textContent = professionalHeadline || "Headline not set";
  document.querySelector("[data-dashboard-company]").textContent = company || "Company not set";

  const website = document.querySelector("[data-dashboard-website]");
  const websiteUrl = safeMediaUrl(profile.website_url);
  if (websiteUrl) {
    website.href = websiteUrl;
    website.target = "_blank";
    website.rel = "noreferrer";
    website.textContent = websiteLabel(websiteUrl);
    website.setAttribute("aria-label", `Open ${websiteLabel(websiteUrl)} in a new tab`);
  } else {
    website.href = "/settings/account#profile";
    website.removeAttribute("target");
    website.removeAttribute("rel");
    website.textContent = "Add website";
    website.setAttribute("aria-label", "Add a website in personal information");
  }

  const socialLinks = document.querySelector("[data-dashboard-social-links]");
  socialLinks.replaceChildren();
  [
    ["Instagram", profile.instagram_url],
    ["LinkedIn", profile.linkedin_url],
  ].forEach(([label, value]) => {
    const url = safeMediaUrl(value);
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    link.setAttribute("aria-label", `Open ${label} in a new tab`);
    socialLinks.append(link);
  });
  if (!socialLinks.childElementCount) {
    const link = document.createElement("a");
    link.href = "/settings/account#profile";
    link.textContent = "Add social links";
    socialLinks.append(link);
  }

  const completionFields = [
    profile.display_name,
    profile.bio,
    profile.website_url,
    profile.country_code,
    profile.professional_headline,
    profile.company,
    profile.city,
    profile.instagram_url,
    profile.linkedin_url,
    ["open", "limited", "unavailable"].includes(profile.availability_status) ? profile.availability_status : "",
  ];
  const completedFields = completionFields.filter((value) => cleanText(value)).length;
  const completion = Math.round((completedFields / completionFields.length) * 100);
  const completionBar = document.querySelector("[data-dashboard-completion]");
  completionBar.setAttribute("aria-valuenow", String(completion));
  completionBar.querySelector("span").style.width = `${completion}%`;
  document.querySelector("[data-dashboard-completion-value]").textContent = `${completion}%`;
  document.querySelector("[data-dashboard-completion-note]").textContent = `${completedFields} of ${completionFields.length} core details complete`;
}

function cleanCover(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const id = cleanText(value.id);
  const imageId = cleanText(value.image_id);
  const signedUrl = safeMediaUrl(value.signed_url);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id) || !imageId || !signedUrl) return null;
  return {
    id,
    image_id: imageId,
    title: cleanText(value.title) || "Untitled work",
    kind: cleanText(value.kind) || "display",
    mime_type: cleanText(value.mime_type),
    width: Number.isFinite(Number(value.width)) ? Number(value.width) : null,
    height: Number.isFinite(Number(value.height)) ? Number(value.height) : null,
    signed_url: signedUrl,
    expires_in: Number.isFinite(Number(value.expires_in)) ? Number(value.expires_in) : null,
  };
}

function cleanCoverPayload(payload) {
  const candidates = Array.isArray(payload?.candidates)
    ? payload.candidates.slice(0, 24).map(cleanCover).filter(Boolean)
    : [];
  return { cover: cleanCover(payload?.cover), candidates };
}

function setCoverImage(cover) {
  dashboardCoverImage.src = cover?.signed_url || DEFAULT_COVER_URL;
  dashboardCoverImage.alt = cover ? `${cover.title} profile cover` : "";
}

function showCoverPageStatus(message, tone = "success") {
  dashboardCoverStatus.textContent = message;
  dashboardCoverStatus.dataset.tone = tone;
  dashboardCoverStatus.hidden = false;
}

function hideCoverPageStatus() {
  dashboardCoverStatus.hidden = true;
  dashboardCoverStatus.textContent = "";
  delete dashboardCoverStatus.dataset.tone;
}

async function loadCoverData(signal) {
  const payload = await dashboardRequest("/api/me/profile/cover", signal);
  coverData = cleanCoverPayload(payload);
  setCoverImage(coverData.cover);
  return coverData;
}

function setCoverDialogState(message = "", tone = "loading", focus = false) {
  dashboardCoverDialogState.textContent = message;
  dashboardCoverDialogState.dataset.tone = tone;
  dashboardCoverDialogState.hidden = !message;
  if (focus && message) dashboardCoverDialogState.focus();
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(cleanText(value));
}

function coverUploadAssets(item) {
  const assets = Array.isArray(item?.assets) ? item.assets : [];
  const original = assets.find((asset) => asset.kind === "original" && asset.blob instanceof Blob);
  if (!original) throw new Error("The original image could not be prepared for upload.");
  const display = assets.find((asset) => asset.kind === "display" && asset.blob instanceof Blob) || original;
  const thumbnail = assets.find((asset) => asset.kind === "thumbnail" && asset.blob instanceof Blob) || display;
  const sources = { original, display, thumbnail };
  return ["original", "display", "thumbnail"].map((kind) => {
    const source = sources[kind];
    const checksum = cleanText(source.checksum_sha256);
    if (!/^[0-9a-f]{64}$/i.test(checksum)) throw new Error("Image checksum verification is unavailable in this browser.");
    const asset = {
      kind,
      blob: source.blob,
      mime_type: cleanText(source.mime_type || source.blob.type).toLowerCase(),
      byte_size: Number(source.byte_size || source.blob.size),
      width: Number(source.width || item.width),
      height: Number(source.height || item.height),
      checksum_sha256: checksum.toLowerCase(),
    };
    if (
      !COVER_UPLOAD_MIME_TYPES.has(asset.mime_type)
      || !Number.isInteger(asset.byte_size)
      || asset.byte_size < 1
      || asset.byte_size > COVER_ASSET_MAX_BYTES[kind]
      || !Number.isInteger(asset.width)
      || !Number.isInteger(asset.height)
      || asset.width < 1
      || asset.height < 1
    ) {
      throw new Error("This image could not be prepared within the secure upload limits.");
    }
    return asset;
  });
}

async function createCoverUploadIntent(item, assets, signal) {
  const original = assets.find((asset) => asset.kind === "original");
  const payload = await dashboardApiMutation("/api/uploads/intents", {
    method: "POST",
    signal,
    body: {
      folder_id: null,
      original_filename: cleanText(item.imageRecord?.original_filename || item.title),
      original_width: original.width,
      original_height: original.height,
      checksum_sha256: original.checksum_sha256,
      assets: assets.map(({ blob, ...asset }) => asset),
    },
  });
  if (!isUuid(payload.upload_id) || !Array.isArray(payload.assets) || payload.assets.length !== 3) {
    throw new Error("Secure upload destinations could not be verified.");
  }
  const destinations = payload.assets.map((destination) => ({
    kind: cleanText(destination.kind),
    signed_url: safeMediaUrl(destination.signed_url),
  }));
  if (destinations.some((destination) => !["original", "display", "thumbnail"].includes(destination.kind) || !destination.signed_url)) {
    throw new Error("Secure upload destinations could not be verified.");
  }
  return { upload_id: payload.upload_id, assets: destinations };
}

async function uploadCoverAsset(destination, asset, signal) {
  const extension = asset.mime_type.split("/")[1] || "jpg";
  const formData = new FormData();
  formData.append("cacheControl", "3600");
  formData.append("", asset.blob, `${destination.kind}.${extension}`);
  const response = await fetch(destination.signed_url, {
    method: "PUT",
    credentials: "omit",
    headers: { "x-upsert": "false" },
    body: formData,
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || payload.error || `The ${destination.kind} image could not be uploaded.`);
  }
}

async function completeCoverUpload(intent, item, signal) {
  const payload = await dashboardApiMutation(`/api/uploads/${encodeURIComponent(intent.upload_id)}/complete`, {
    method: "POST",
    signal,
    body: {
      draft: {
        title: cleanText(item.title).slice(0, 180) || "Profile cover",
        content_category: cleanText(item.imageRecord?.content_type) === "abstract" ? "abstract" : "concrete",
      },
    },
  });
  const imageId = cleanText(payload.draft?.id);
  if (!isUuid(imageId)) throw new Error("The uploaded image response could not be verified.");
  return imageId;
}

async function cancelCoverUploadIntent(uploadId) {
  if (!isUuid(uploadId)) return;
  await dashboardApiMutation(`/api/uploads/${encodeURIComponent(uploadId)}`, {
    method: "DELETE",
    body: { confirmation: "cancel-upload" },
  }).catch(() => undefined);
}

function coverScanDelay(signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Upload canceled.", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Upload canceled.", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, COVER_SCAN_DELAY);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function waitForCoverCandidate(imageId, signal) {
  for (let attempt = 0; attempt < COVER_SCAN_ATTEMPTS; attempt += 1) {
    signal.throwIfAborted();
    await loadCoverData(signal);
    const candidate = coverData.candidates.find((item) => item.image_id === imageId);
    if (candidate) return candidate;
    setCoverDialogState("Upload complete. Running the required security scan...", "loading");
    await coverScanDelay(signal);
  }
  const error = new Error("The image was uploaded as a private draft and is still being scanned. Reopen this chooser shortly.");
  error.code = "COVER_SCAN_PENDING";
  throw error;
}

async function uploadLocalCover(file) {
  if (coverBusy || !file) return;
  if (!COVER_UPLOAD_MIME_TYPES.has(file.type)) {
    setCoverDialogState("Choose a JPEG, PNG, or WebP image.", "error", true);
    return;
  }
  if (file.size < 1 || file.size > COVER_UPLOAD_MAX_BYTES) {
    setCoverDialogState("Choose an image smaller than 50 MB.", "error", true);
    return;
  }
  if (!window.MTArchiveUpload?.buildUploadedItem) {
    setCoverDialogState("Local image preparation is unavailable. Reload and try again.", "error", true);
    return;
  }

  coverUploadController = new AbortController();
  const { signal } = coverUploadController;
  setCoverBusy(true);
  try {
    const task = {
      update(stage, progress) {
        const label = {
          reading: "Reading and verifying the image",
          compressing: "Preparing the display image",
          slicing: "Optimizing the image",
          analyzing: "Finalizing image metadata",
        }[stage] || "Preparing the image";
        setCoverDialogState(`${label}... ${Math.round(progress)}%`, "loading");
      },
    };
    const { item } = await window.MTArchiveUpload.buildUploadedItem(file, task, 0);
    signal.throwIfAborted();
    const assets = coverUploadAssets(item);
    setCoverDialogState("Creating secure upload destinations...", "loading");
    const intent = await createCoverUploadIntent(item, assets, signal);
    coverUploadIntentId = intent.upload_id;
    for (const [index, destination] of intent.assets.entries()) {
      const asset = assets.find((candidate) => candidate.kind === destination.kind);
      setCoverDialogState(`Uploading image ${index + 1} of ${intent.assets.length}...`, "loading");
      await uploadCoverAsset(destination, asset, signal);
    }
    setCoverDialogState("Creating your private image draft...", "loading");
    const imageId = await completeCoverUpload(intent, item, signal);
    coverUploadIntentId = null;
    const candidate = await waitForCoverCandidate(imageId, signal);
    setCoverDialogState("Applying the new profile cover...", "loading");
    const payload = await dashboardApiMutation("/api/me/profile/cover", {
      method: "PATCH",
      signal,
      body: { asset_id: candidate.id },
    });
    const savedCover = cleanCover(payload.cover);
    if (payload.saved !== true || !savedCover) throw new Error("The saved cover response could not be verified.");
    coverData.cover = savedCover;
    setCoverImage(savedCover);
    renderCoverChooser();
    setCoverDialogState("Upload complete. Your profile cover is updated.", "success");
    showCoverPageStatus("Profile cover updated from your device.");
    announce("Profile cover updated from your device.");
    window.setTimeout(() => {
      setCoverBusy(false);
      closeCoverChooser();
    }, 750);
  } catch (error) {
    if (coverUploadIntentId) await cancelCoverUploadIntent(coverUploadIntentId);
    coverUploadIntentId = null;
    if (redirectForDashboardAuth(error)) return;
    setCoverBusy(false);
    const pending = error.code === "COVER_SCAN_PENDING";
    setCoverDialogState(error.message || "The local image could not be uploaded.", pending ? "success" : "error", !pending);
    if (pending) {
      showCoverPageStatus("Local image uploaded. Security scanning is still in progress.");
      announce("Local image uploaded. Security scanning is still in progress.");
    }
  } finally {
    coverUploadController = null;
    dashboardCoverFile.value = "";
  }
}

function showCoverLoadError(error) {
  const message = document.createElement("span");
  message.textContent = error.message || "Available cover images could not be loaded.";
  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "Retry";
  retry.addEventListener("click", refreshCoverChooser, { once: true });
  dashboardCoverDialogState.replaceChildren(message, retry);
  dashboardCoverDialogState.dataset.tone = "error";
  dashboardCoverDialogState.hidden = false;
  dashboardCoverDialogState.focus();
}

function updateCoverSelection() {
  dashboardCoverCandidates.querySelectorAll("[data-cover-id]").forEach((button) => {
    const selected = button.dataset.coverId === selectedCoverId;
    button.setAttribute("aria-pressed", String(selected));
  });
  const currentId = coverData.cover?.id || null;
  dashboardCoverSave.disabled = coverBusy || selectedCoverId === currentId;
  dashboardCoverRemove.disabled = coverBusy || !currentId;
  dashboardCoverRemove.hidden = !currentId;
}

function coverCandidateButton(cover) {
  const button = document.createElement("button");
  button.className = "dashboard-cover-candidate";
  button.type = "button";
  button.dataset.coverId = cover.id;
  button.setAttribute("aria-pressed", String(cover.id === selectedCoverId));
  button.setAttribute("aria-label", `Use ${cover.title} as profile cover`);

  const image = document.createElement("img");
  image.src = cover.signed_url;
  image.alt = "";
  image.decoding = "async";
  const copy = document.createElement("span");
  const title = document.createElement("strong");
  title.textContent = cover.title;
  const dimensions = cover.width && cover.height ? `${cover.width} x ${cover.height}` : displayValue(cover.kind);
  const meta = document.createElement("small");
  meta.textContent = dimensions;
  copy.append(title, meta);
  const marker = document.createElement("span");
  marker.className = "dashboard-cover-candidate-marker";
  marker.setAttribute("aria-hidden", "true");
  marker.append(icon("icon-check"));
  button.append(image, copy, marker);
  if (cover.id === coverData.cover?.id) button.dataset.current = "true";
  button.addEventListener("click", () => {
    if (coverBusy) return;
    selectedCoverId = cover.id;
    setCoverDialogState();
    updateCoverSelection();
  });
  return button;
}

function renderCoverChooser() {
  dashboardCoverCandidates.replaceChildren();
  selectedCoverId = coverData.cover?.id || null;
  coverData.candidates.forEach((cover) => dashboardCoverCandidates.append(coverCandidateButton(cover)));
  const empty = coverData.candidates.length === 0;
  dashboardCoverEmpty.hidden = !empty;
  dashboardCoverCandidates.hidden = empty;
  dashboardCoverActions.hidden = empty && !coverData.cover;
  setCoverDialogState();
  updateCoverSelection();
}

function setCoverBusy(busy) {
  coverBusy = busy;
  dashboardCoverClose.disabled = busy;
  dashboardCoverCancel.disabled = busy;
  dashboardCoverUpload.disabled = busy;
  dashboardCoverFile.disabled = busy;
  dashboardCoverCandidates.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  updateCoverSelection();
}

function redirectForDashboardAuth(error) {
  if (error.status === 401) {
    window.location.assign("/auth/sign-in?next=%2Fdashboard");
    return true;
  }
  if (error.status === 403 && error.code === "MFA_REQUIRED") {
    window.location.assign("/auth/mfa?next=%2Fdashboard");
    return true;
  }
  return false;
}

async function refreshCoverChooser() {
  coverController?.abort();
  coverController = new AbortController();
  dashboardCoverEmpty.hidden = true;
  dashboardCoverCandidates.hidden = true;
  dashboardCoverActions.hidden = true;
  setCoverDialogState("Loading available work...", "loading");
  try {
    await loadCoverData(coverController.signal);
    renderCoverChooser();
  } catch (error) {
    if (error.name === "AbortError") return;
    if (redirectForDashboardAuth(error)) return;
    showCoverLoadError(error);
    dashboardCoverActions.hidden = false;
    dashboardCoverSave.disabled = true;
    dashboardCoverRemove.hidden = true;
  }
}

function closeCoverChooser() {
  if (coverBusy || !dashboardCoverDialog.open) return;
  dashboardCoverDialog.close();
}

async function saveCover(assetId) {
  if (coverBusy) return;
  setCoverBusy(true);
  setCoverDialogState(assetId ? "Saving your new cover..." : "Removing your current cover...", "loading");
  try {
    const payload = await dashboardMutation("/api/me/profile/cover", { asset_id: assetId });
    const savedCover = cleanCover(payload.cover);
    const previewUnavailable = assetId !== null && payload.cover === null;
    if (
      payload.saved !== true
      || (assetId !== null && !savedCover && !previewUnavailable)
      || (assetId === null && payload.cover !== null)
    ) {
      throw new Error("The saved cover response could not be verified. Try again.");
    }
    if (previewUnavailable) {
      selectedCoverId = assetId;
      setCoverDialogState("Cover saved. Preview temporarily unavailable.", "success");
      showCoverPageStatus("Profile cover saved. Preview temporarily unavailable.", "error");
      announce("Profile cover saved. Preview temporarily unavailable.");
      window.setTimeout(() => {
        setCoverBusy(false);
        closeCoverChooser();
      }, 650);
      return;
    }
    coverData.cover = savedCover;
    setCoverImage(savedCover);
    selectedCoverId = savedCover?.id || null;
    setCoverDialogState(savedCover ? "Cover updated." : "Cover removed.", "success");
    showCoverPageStatus(savedCover ? "Profile cover updated." : "Profile cover removed.");
    announce(savedCover ? "Profile cover updated." : "Profile cover removed.");
    window.setTimeout(() => {
      setCoverBusy(false);
      closeCoverChooser();
    }, 650);
  } catch (error) {
    if (redirectForDashboardAuth(error)) return;
    setCoverBusy(false);
    setCoverDialogState(error.message || "Your cover could not be saved. Try again.", "error", true);
  }
}

async function openCoverChooser() {
  coverReturnFocus = document.activeElement;
  hideCoverPageStatus();
  dashboardCoverDialog.showModal();
  await refreshCoverChooser();
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

function renderPublicPortfolio(capability = {}) {
  const section = document.querySelector("[data-dashboard-public-note]");
  const title = section.querySelector("[data-dashboard-public-title]");
  const message = section.querySelector("[data-dashboard-public-message]");
  const link = section.querySelector("[data-dashboard-public-link]");
  const count = Number(capability.published_count || 0);
  section.hidden = false;
  link.hidden = true;
  if (capability.available === true && capability.public_path) {
    title.textContent = "Your public profile is live.";
    message.textContent = `${count} published ${count === 1 ? "work is" : "works are"} visible to visitors.`;
    link.href = capability.public_path;
    link.hidden = false;
    return;
  }
  if (capability.reason === "no_published_works") {
    title.textContent = "No public works yet.";
    message.textContent = "Your profile will become public when an administrator publishes your first approved work.";
    return;
  }
  title.textContent = "Public profile status is unavailable.";
  message.textContent = "Published work is still tracked here while public delivery is being configured.";
}

function renderDashboard(payload) {
  renderStatusCounts(payload.status_counts || {});
  renderAttention(Array.isArray(payload.needs_attention) ? payload.needs_attention : []);
  renderRecent(Array.isArray(payload.recent_images) ? payload.recent_images : []);
  renderActivity(Array.isArray(payload.review_activity) ? payload.review_activity : []);
  renderStorage(payload.storage_usage || {}, payload.capabilities || {});
  renderDrafts(Array.isArray(payload.drafts) ? payload.drafts : []);
  renderPublicPortfolio(payload.capabilities?.public_portfolio || {});
  document.querySelector("[data-dashboard-generated]").textContent = `Updated ${formatDate(payload.generated_at, true)}`;
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
    loadCoverData(dashboardController.signal).catch((error) => {
      if (error.name !== "AbortError" && !redirectForDashboardAuth(error)) {
        showCoverPageStatus("Cover preview is temporarily unavailable.", "error");
      }
    });
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
dashboardCoverOpen.addEventListener("click", openCoverChooser);
dashboardCoverClose.addEventListener("click", closeCoverChooser);
dashboardCoverCancel.addEventListener("click", closeCoverChooser);
dashboardCoverUpload.addEventListener("click", () => {
  if (coverBusy) return;
  dashboardCoverFile.value = "";
  dashboardCoverFile.click();
});
dashboardCoverFile.addEventListener("change", () => uploadLocalCover(dashboardCoverFile.files?.[0]));
dashboardCoverSave.addEventListener("click", () => saveCover(selectedCoverId));
dashboardCoverRemove.addEventListener("click", () => saveCover(null));
dashboardCoverDialog.addEventListener("cancel", (event) => {
  if (coverBusy) event.preventDefault();
});
dashboardCoverDialog.addEventListener("close", () => {
  coverController?.abort();
  if (coverReturnFocus instanceof HTMLElement) coverReturnFocus.focus();
  coverReturnFocus = null;
});
dashboardCoverImage.addEventListener("error", () => {
  if (!dashboardCoverImage.src.endsWith(DEFAULT_COVER_URL)) dashboardCoverImage.src = DEFAULT_COVER_URL;
});
window.addEventListener("pagehide", () => {
  dashboardController?.abort();
  coverController?.abort();
  coverUploadController?.abort();
}, { once: true });

loadDashboard();
