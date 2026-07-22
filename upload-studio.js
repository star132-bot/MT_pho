const DB_NAME = "mt-cijian-archive";
const DB_VERSION = 4;
const DB_STORE = "images";
const WORKSPACE_FOLDERS_API = "/api/folders";
const WORKSPACE_IMAGES_API = "/api/images";
const WORKSPACE_UPLOAD_INTENTS_API = "/api/uploads/intents";
const WORKSPACE_IMAGE_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const UPLOAD_CONCURRENCY = 2;
const DRAFT_AUTOSAVE_DELAY = 900;
const READINESS_POLL_DELAY = 5000;
let archiveCsrfTokenPromise = null;

async function archiveCsrfToken(force = false) {
  if (force) archiveCsrfTokenPromise = null;
  if (!archiveCsrfTokenPromise) {
    archiveCsrfTokenPromise = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.csrf_token) throw new Error("Unable to initialize secure archive access.");
      return result.csrf_token;
    });
  }
  return archiveCsrfTokenPromise;
}

async function archiveMutationFetch(url, options = {}, retryCsrf = true) {
  const headers = { ...(options.headers || {}), "X-CSRF-Token": await archiveCsrfToken() };
  const response = await fetch(url, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers,
  });
  if (response.status === 403 && retryCsrf) {
    const result = await response.clone().json().catch(() => ({}));
    if (result.error?.code === "CSRF_REJECTED") {
      await archiveCsrfToken(true);
      return archiveMutationFetch(url, options, false);
    }
  }
  return response;
}

async function workspaceRequest(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const response = ["GET", "HEAD"].includes(method)
    ? await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      ...options,
      headers: { Accept: "application/json", ...(options.headers || {}) },
    })
    : await archiveMutationFetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.assign("/auth/sign-in?next=%2Fworkspace%2Fimages");
    throw new Error("Your session has expired.");
  }
  if (response.status === 403 && result.error?.code === "MFA_REQUIRED") {
    window.location.assign("/auth/mfa?next=%2Fworkspace%2Fimages");
    throw new Error("Administrator MFA is required.");
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || result.error || "Unable to complete this Workspace request.");
    error.code = result.error?.code || "WORKSPACE_REQUEST_FAILED";
    error.status = response.status;
    error.fieldErrors = result.error?.field_errors || {};
    error.details = result.error?.details || {};
    error.readiness = result.readiness
      || result.error?.readiness
      || result.error?.details?.readiness
      || (result.error?.code === "DRAFT_NOT_READY" ? result.error?.details : null);
    throw error;
  }
  return result;
}

const LOCAL_STORAGE_BUCKET = "indexeddb-local";

const uploadInput = document.querySelector("[data-upload-studio-input]");
const primaryImport = document.querySelector(".upload-studio-primary");
const dropzone = document.querySelector("[data-upload-dropzone]");
const queueElement = document.querySelector("[data-studio-queue]");
const countElement = document.querySelector("[data-studio-count]");
const statusElement = document.querySelector("[data-studio-status]");
const folderForm = document.querySelector("[data-folder-form]");
const folderList = document.querySelector("[data-folder-list]");
const folderSummary = document.querySelector("[data-folder-summary]");
const folderSelect = document.querySelector("[data-folder-select]");
const emptyElement = document.querySelector("[data-studio-empty]");
const formElement = document.querySelector("[data-studio-form]");
const previewImage = document.querySelector("[data-studio-preview]");
const studioTitle = document.querySelector("[data-studio-title]");
const studioKicker = document.querySelector("[data-studio-kicker]");
const assetSummary = document.querySelector("[data-studio-asset-summary]");
const saveState = document.querySelector("[data-studio-save-state]");
const saveRecordButton = document.querySelector("[data-studio-save-record]");
const reloadRecordButton = document.querySelector("[data-studio-reload-record]");
const deleteRecordButton = document.querySelector("[data-studio-delete-record]");
const readinessElement = document.querySelector("[data-studio-readiness]");
const readinessSummary = document.querySelector("[data-studio-readiness-summary]");
const readinessList = document.querySelector("[data-studio-readiness-list]");
const readinessRefreshButton = document.querySelector("[data-studio-readiness-refresh]");
const submitRecordButton = document.querySelector("[data-studio-submit-record]");
const submitRecordLabel = document.querySelector("[data-studio-submit-label]");
const submitDialog = document.querySelector("[data-studio-submit-dialog]");
const submitDialogTitle = document.querySelector("[data-studio-submit-dialog-title]");
const toastElement = document.querySelector("[data-studio-toast]");
const studioGrid = document.querySelector(".upload-studio-grid");
const workspaceViewButtons = [...document.querySelectorAll("[data-studio-view]")];
const draftCountElement = document.querySelector("[data-studio-draft-count]");
const trashCountElement = document.querySelector("[data-studio-trash-count]");
const folderPanelTitle = document.querySelector("[data-folder-panel-title]");
const draftsOnlyElements = [...document.querySelectorAll("[data-studio-drafts-only]")];
const recognizablePeopleSelect = document.querySelector("[data-recognizable-people]");
const modelReleaseField = document.querySelector("[data-model-release-field]");
const copyrightYearInput = document.querySelector("[name=\"copyright_year\"]");

let archiveDb = null;
let folders = [];
let activeFolderId = "inbox";
let records = [];
let trashedRecords = [];
let activeWorkspaceView = new URLSearchParams(window.location.search).get("view") === "trash" ? "trash" : "drafts";
let activeRecordId = null;
let toastTimer = null;
let workspaceOnline = true;
let workspaceLoading = true;
let uploadTasks = [];
let autosaveTimer = null;
let draftEditRevision = 0;
let draftDirty = false;
let draftConflict = false;
let draftSaveInFlight = false;
let pendingAutosave = false;
let activeSavePromise = null;
let formRecordId = null;
let readinessRequestId = 0;
let readinessPollTimer = null;
let submissionPreparing = false;
let submissionInFlight = false;
let activeSubmissionPromise = null;
let trashLoading = false;
let trashLoaded = false;
let trashError = null;
const taskByRecordId = new Map();
const submissionIdempotencyKeys = new Map();
const objectUrls = new Set();
const restoringTrashIds = new Set();
const trashRestoreErrors = new Map();

function cleanText(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function nullableBoolean(value) {
  if (value === true || value === "true") return true;
  if (value === false || value === "false") return false;
  return null;
}

const READINESS_CHECK_DEFAULTS = [
  {
    code: "work_details",
    label: "Work details",
    message: "Title, alt text and content category are required.",
  },
  {
    code: "rights_disclosures",
    label: "Rights & disclosures",
    message: "Complete the rights, releases and disclosure fields.",
  },
  {
    code: "image_assets",
    label: "Image assets",
    message: "Original, display and thumbnail assets are required.",
  },
  {
    code: "security_scan",
    label: "Security scan",
    message: "All image assets must pass security scanning.",
  },
  {
    code: "submission_state",
    label: "Submission state",
    message: "This image must remain an editable Draft.",
  },
];

function readinessCheckState(check = {}) {
  const rawState = cleanText(check.state || check.status).toLowerCase();
  if (check.ready === true || check.passed === true || check.complete === true
    || ["pass", "passed", "ready", "complete", "completed", "ok", "clean"].includes(rawState)) {
    return "pass";
  }
  if (["pending", "checking", "running", "queued", "stale"].includes(rawState)) {
    return "pending";
  }
  return "blocked";
}

function normalizeReadiness(payload, record = null) {
  if (!payload || typeof payload !== "object") return null;
  const rawChecks = Array.isArray(payload.checks) ? payload.checks : [];
  const checksByCode = new Map();
  rawChecks.forEach((check) => {
    if (!check || typeof check !== "object") return;
    const code = cleanText(check.code || check.key);
    if (READINESS_CHECK_DEFAULTS.some((fallback) => fallback.code === code) && !checksByCode.has(code)) {
      checksByCode.set(code, check);
    }
  });
  const contractComplete = checksByCode.size === READINESS_CHECK_DEFAULTS.length;
  const checks = READINESS_CHECK_DEFAULTS.map((fallback) => {
    const check = checksByCode.get(fallback.code) || {};
    return {
      ...check,
      code: fallback.code,
      label: cleanText(check.label || check.title || fallback.label),
      message: cleanText(check.message || check.detail || check.description || fallback.message),
      state: readinessCheckState(check),
    };
  });
  const workflowStatus = cleanText(payload.workflow_status || record?.workflow_status || "draft").toLowerCase();
  const ready = payload.ready === true && contractComplete && checks.every((check) => check.state === "pass");
  const hasPendingCheck = checks.some((check) => check.state === "pending");
  const rawStatus = cleanText(payload.status).toLowerCase();
  let status = ready ? "ready" : hasPendingCheck ? "pending" : "blocked";
  if (["checking", "blocked", "pending", "ready", "error", "stale", "submitted"].includes(rawStatus)) {
    status = rawStatus;
  }
  if (!["draft", "changes_requested"].includes(workflowStatus)) {
    status = "submitted";
  }
  return {
    ...payload,
    image_id: cleanText(payload.image_id || record?.id),
    lock_version: Number.isInteger(payload.lock_version) ? payload.lock_version : record?.lock_version,
    workflow_status: workflowStatus,
    status,
    ready: ready && status === "ready",
    blocker_count: Number.isInteger(payload.blocker_count)
      ? payload.blocker_count
      : checks.filter((check) => check.state === "blocked").length,
    checks,
    field_errors: payload.field_errors && typeof payload.field_errors === "object" ? payload.field_errors : {},
  };
}

function slugify(value, fallback = "item") {
  const slug = cleanText(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || fallback;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function contentTypeCode(type) {
  const value = cleanText(type).toLowerCase();
  return value === "abstract" || value === "black_white" ? "abstract" : "concrete";
}

function contentTypeLabel(type) {
  return contentTypeCode(type) === "abstract" ? "Abstract" : "Concrete";
}

function displayModeForType(type) {
  return contentTypeCode(type) === "abstract" ? "black_white" : "color";
}

function ratioCategoryCode(label) {
  const codes = {
    "1:1": "one_to_one",
    "4:3": "four_to_three",
    "4:5": "four_to_five",
    "2:3": "two_to_three",
    "3:2": "three_to_two",
    "16:9": "sixteen_to_nine",
    Panorama: "panorama",
  };
  return codes[label] || "one_to_one";
}

function ratioLabelFromCode(code) {
  const labels = {
    one_to_one: "1:1",
    four_to_three: "4:3",
    four_to_five: "4:5",
    two_to_three: "2:3",
    three_to_two: "3:2",
    sixteen_to_nine: "16:9",
    panorama: "Panorama",
  };
  return labels[code] || "";
}

function nowIso() {
  return new Date().toISOString();
}

function createdAtIso(value) {
  if (!value) {
    return nowIso();
  }
  if (typeof value === "number") {
    return new Date(value).toISOString();
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? nowIso() : date.toISOString();
}

function numberOrFallback(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) {
    return "0 B";
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 1 : 2)} MB`;
}

function formatTrashDate(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "Recently moved";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function uniqueTextList(values = []) {
  const seen = new Set();
  const result = [];
  values.forEach((value) => {
    const text = cleanText(value);
    if (!text) {
      return;
    }
    const key = text.toLowerCase();
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    result.push(text);
  });
  return result;
}

function splitTags(value) {
  return uniqueTextList(cleanText(value).split(/[\n,;|]/));
}

function titleCase(value) {
  return cleanText(value)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function defaultFolders() {
  return [
    { id: "offline-inbox", name: "Offline cache", is_system: true, created_at: nowIso() },
  ];
}

async function loadFolders() {
  const result = await workspaceRequest(WORKSPACE_FOLDERS_API);
  folders = Array.isArray(result.folders) ? result.folders : [];
  if (!folders.length) {
    throw new Error("Your Workspace does not have an Inbox.");
  }
  const requestedFolder = new URLSearchParams(window.location.search).get("folder");
  activeFolderId = requestedFolder || folders.find((folder) => folder.is_system)?.id || folders[0].id;
  if (!folders.some((folder) => folder.id === activeFolderId)) {
    activeFolderId = folders.find((folder) => folder.is_system)?.id || folders[0].id;
  }
  saveActiveFolder();
}

function saveActiveFolder() {
  const url = new URL(window.location.href);
  url.searchParams.set("folder", activeFolderId);
  if (activeWorkspaceView === "trash") {
    url.searchParams.set("view", "trash");
  } else {
    url.searchParams.delete("view");
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function activeFolder() {
  return folders.find((folder) => folder.id === activeFolderId) || folders[0] || { id: "inbox", name: "Inbox" };
}

function folderById(id) {
  return folders.find((folder) => folder.id === id) || activeFolder();
}

function createObjectUrl(asset) {
  if (!asset?.blob) {
    return "";
  }
  if (!asset.objectUrl) {
    asset.objectUrl = URL.createObjectURL(asset.blob);
    objectUrls.add(asset.objectUrl);
  }
  return asset.objectUrl;
}

function publicAssetUrl(asset) {
  if (!asset) {
    return "";
  }
  return asset.public_url || asset.signed_url || createObjectUrl(asset) || "";
}

function preferredAsset(record, kinds) {
  return (record.assets || []).find((asset) => kinds.includes(asset.kind)) || null;
}

function displayUrl(record) {
  const imageRecord = record.imageRecord || {};
  return (
    publicAssetUrl(preferredAsset(record, ["display"])) ||
    record.image_url ||
    imageRecord.image_url ||
    imageRecord.display_url ||
    publicAssetUrl(preferredAsset(record, ["original"])) ||
    record.src ||
    ""
  );
}

function thumbnailUrl(record) {
  return publicAssetUrl(preferredAsset(record, ["thumbnail", "display"])) || record.thumbnail_url || displayUrl(record);
}

function openArchiveDatabase() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("IndexedDB is not available."));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(DB_STORE)) {
        database.createObjectStore(DB_STORE, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains("site_settings")) {
        database.createObjectStore("site_settings", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open local archive database."));
  });
}

function transactionStore(mode = "readonly") {
  return archiveDb.transaction(DB_STORE, mode).objectStore(DB_STORE);
}

function getStoredItems() {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve([]);
      return;
    }
    const request = transactionStore().getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error || new Error("Unable to read local records."));
  });
}

function stripRuntimeUrls(item) {
  return {
    ...item,
    assets: (item.assets || []).map(({ objectUrl, ...asset }) => asset),
  };
}

function putStoredItem(item) {
  return new Promise((resolve, reject) => {
    const request = transactionStore("readwrite").put(stripRuntimeUrls(item));
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("Unable to save local record."));
  });
}

function deleteStoredItem(id) {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve();
      return;
    }
    const request = transactionStore("readwrite").delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("Unable to delete local record."));
  });
}

function normalizeAsset(asset, imageId, index = 0) {
  const kind = asset.kind || "original";
  const id = asset.id || `${imageId}-${kind}-${index}`;
  const extension = kind === "original" ? "original" : "jpg";
  return {
    ...asset,
    id,
    image_id: asset.image_id || imageId,
    kind,
    storage_bucket: asset.storage_bucket || LOCAL_STORAGE_BUCKET,
    storage_path: asset.storage_path || `uploads/${imageId}/${kind}-${index}.${extension}`,
    public_url: asset.public_url || null,
    url_expires_at: asset.url_expires_at || null,
    mime_type: asset.mime_type || asset.blob?.type || "image/jpeg",
    byte_size: asset.byte_size || asset.blob?.size || null,
    width: asset.width || 1,
    height: asset.height || 1,
    checksum_sha256: asset.checksum_sha256 || null,
    source_asset_id: asset.source_asset_id || asset.sourceAssetId || null,
  };
}

function normalizeAssets(item, imageId) {
  return Array.isArray(item.assets) ? item.assets.map((asset, index) => normalizeAsset(asset, imageId, index)) : [];
}

function normalizeSquareSlices(item, imageId) {
  const slices = Array.isArray(item.squareSlices) ? item.squareSlices : [];
  return slices.map((slice, index) => ({
    id: slice.id || `${imageId}-slice-${index}`,
    image_id: slice.image_id || imageId,
    asset_id: slice.asset_id || `${imageId}-square_slice-${index}`,
    slice_index: Number.isFinite(slice.slice_index) ? slice.slice_index : index,
    source_x: slice.source_x || 0,
    source_y: slice.source_y || 0,
    source_size: slice.source_size || Math.min(item.width || 1, item.height || 1),
    width: slice.width || 1,
    height: slice.height || slice.width || 1,
    created_at: slice.created_at || createdAtIso(item.createdAt),
  }));
}

function tagsFromGroups(groups = []) {
  return uniqueTextList(groups.flatMap((group) => group.tags || []));
}

function tagRowsFromGroups(imageId, groups = []) {
  const rows = [];
  groups.forEach((group, groupIndex) => {
    (group.tags || []).forEach((tagName, tagIndex) => {
      rows.push({
        id: `tag-${slugify(group.label, "group")}-${slugify(tagName, "tag")}`,
        name: tagName,
        slug: slugify(tagName, "tag"),
        group_name: group.label,
        sort_order: groupIndex * 100 + tagIndex,
        image_id: imageId,
      });
    });
  });
  return rows;
}

function buildTagGroups({ series, contentType, ratio, displayMode, customTags }) {
  const typeLabel = contentTypeLabel(contentType);
  const palette = displayMode === "black_white" || contentTypeCode(contentType) === "abstract" ? ["Black and white", "Monochrome"] : ["Color"];
  return [
    { label: "Subject", tags: uniqueTextList([typeLabel, ...customTags]) },
    { label: "Form / Ratio", tags: uniqueTextList([ratio]) },
    { label: "Mood", tags: ["Quiet Observation"] },
    { label: "Palette / Tone", tags: palette },
    { label: "Series / Collection", tags: uniqueTextList([series]) },
  ].filter((group) => group.tags.length);
}

function normalizeRecord(item, folder = activeFolder()) {
  const imageId = item.imageRecord?.id || item.id;
  const rawRecord = item.imageRecord || {};
  const ratio = item.ratio || item.ratio_label || ratioLabelFromCode(rawRecord.ratio_category_code) || "1:1";
  const contentType = contentTypeCode(rawRecord.content_type || item.content_type || item.type);
  const displayMode = rawRecord.display_mode || item.display_mode || displayModeForType(contentType);
  const originalWidth = rawRecord.original_width || item.original_width || item.width || 1;
  const originalHeight = rawRecord.original_height || item.original_height || item.height || 1;
  const titleSource = Object.prototype.hasOwnProperty.call(item, "title") ? item.title : rawRecord.title;
  const title = item.allowEmptyTitle
    ? cleanText(titleSource)
    : cleanText(titleSource || "Untitled Work") || "Untitled Work";
  const requestedFolderId = cleanText(item.folder_id || rawRecord.folder_id);
  const requestedFolderName = cleanText(item.folder_name || rawRecord.folder_name);
  const ensuredFolder = folders.find((candidate) => candidate.id === requestedFolderId)
    || folders.find((candidate) => requestedFolderName && candidate.name.toLowerCase() === requestedFolderName.toLowerCase())
    || folder
    || activeFolder();
  const customTags = uniqueTextList([...(item.customTags || []), ...(Array.isArray(item.tags) ? item.tags : [])]);
  const series = cleanText(item.series || rawRecord.series);
  const tagGroups = buildTagGroups({
    series,
    contentType,
    ratio,
    displayMode,
    customTags,
  });
  const flatTags = tagsFromGroups(tagGroups);
  const createdAt = item.createdAt || Date.parse(rawRecord.created_at || rawRecord.uploaded_at || "") || Date.now();
  const imageRecord = {
    ...rawRecord,
    id: imageId,
    title,
    slug: rawRecord.slug || slugify(title, imageId),
    description: cleanText(item.description || rawRecord.description),
    curatorial_note: cleanText(item.curatorial_note || rawRecord.curatorial_note),
    artist_statement: cleanText(item.artist_statement || rawRecord.artist_statement),
    series,
    folder_name: ensuredFolder.name,
    folder_id: ensuredFolder.id,
    source_type: rawRecord.source_type || "upload",
    visibility: cleanText(rawRecord.visibility || item.visibility || "draft"),
    visibility_manually_set: true,
    original_filename: rawRecord.original_filename || item.original_filename || title,
    original_width: originalWidth,
    original_height: originalHeight,
    ratio_category_code: rawRecord.ratio_category_code || ratioCategoryCode(ratio),
    display_ratio_override: rawRecord.display_ratio_override || null,
    content_type: contentType,
    display_mode: displayMode,
    ai_model: rawRecord.ai_model || null,
    ai_confidence: rawRecord.ai_confidence || null,
    ai_analysis: rawRecord.ai_analysis || {},
    exif: rawRecord.exif || item.exif || {},
    sort_order: numberOrFallback(rawRecord.sort_order, item.sortOrder || 0),
    captured_at: cleanText(item.captured_at || rawRecord.captured_at),
    uploaded_at: rawRecord.uploaded_at || createdAtIso(createdAt),
    created_at: rawRecord.created_at || createdAtIso(createdAt),
    updated_at: rawRecord.updated_at || createdAtIso(createdAt),
    tags: flatTags,
    tag_groups: tagGroups,
  };
  const assets = normalizeAssets(item, imageId);
  const imageTags = tagRowsFromGroups(imageId, tagGroups);
  return {
    ...item,
    id: imageId,
    title,
    width: originalWidth,
    height: originalHeight,
    type: contentTypeLabel(contentType),
    ratio,
    source: item.source || "Uploaded",
    createdAt,
    sortOrder: item.sortOrder || imageRecord.sort_order || 0,
    description: imageRecord.description,
    curatorial_note: imageRecord.curatorial_note,
    artist_statement: imageRecord.artist_statement,
    series,
    captured_at: imageRecord.captured_at,
    display_mode: imageRecord.display_mode,
    visibility: imageRecord.visibility,
    folder_id: ensuredFolder.id,
    folder_name: ensuredFolder.name,
    tags: flatTags,
    customTags,
    tag_groups: tagGroups,
    imageRecord,
    assets,
    imageTags,
    imageTaggings: imageTags.map((tag, index) => ({
      image_id: imageId,
      tag_id: tag.id,
      sort_order: index,
    })),
    squareSlices: normalizeSquareSlices(item, imageId),
    squareSliceCount: item.squareSliceCount || item.squareSlices?.length || 0,
  };
}

function ratioFromDimensions(width, height) {
  const ratio = Number(width || 1) / Number(height || 1);
  const candidates = [
    ["1:1", 1],
    ["4:3", 4 / 3],
    ["4:5", 4 / 5],
    ["2:3", 2 / 3],
    ["3:2", 3 / 2],
    ["16:9", 16 / 9],
  ];
  if (ratio >= 2.05 || ratio <= 0.49) return "Panorama";
  return candidates.sort((left, right) => Math.abs(ratio - left[1]) - Math.abs(ratio - right[1]))[0][0];
}

function normalizeWorkspaceDraft(draft) {
  const version = draft.version || {};
  const folder = folders.find((candidate) => candidate.id === draft.folder_id) || activeFolder();
  const contentType = contentTypeCode(version.content_category || "concrete");
  const assets = (draft.assets || []).map((asset) => ({
    ...asset,
    image_id: draft.id,
    storage_path: asset.storage_key,
    signed_url: asset.signed_url || null,
    public_url: null,
  }));
  const record = normalizeRecord({
    id: draft.id,
    title: version.title ?? "",
    allowEmptyTitle: true,
    description: version.description || "",
    curatorial_note: version.caption || "",
    captured_at: version.captured_at || "",
    location_name: version.location_name || "",
    alt_text: version.alt_text || "",
    copyright_holder: version.copyright_holder || "",
    copyright_year: Number.isInteger(version.copyright_year) ? version.copyright_year : null,
    contains_recognizable_people: nullableBoolean(version.contains_recognizable_people),
    model_release_status: version.model_release_status || null,
    property_release_status: version.property_release_status || null,
    rights_declared: version.rights_declared === true,
    ai_disclosure: version.ai_disclosure || null,
    sensitive_content_disclosure: version.sensitive_content_disclosure || null,
    customTags: Array.isArray(version.tags) ? version.tags : [],
    folder_id: draft.folder_id,
    folder_name: folder.name,
    width: draft.original_width,
    height: draft.original_height,
    ratio: ratioFromDimensions(draft.original_width, draft.original_height),
    type: contentType,
    source: "Uploaded",
    createdAt: Date.parse(draft.created_at || "") || Date.now(),
    visibility: "draft",
    assets,
    imageRecord: {
      id: draft.id,
      title: version.title ?? "",
      description: version.description || "",
      curatorial_note: version.caption || "",
      captured_at: version.captured_at || "",
      folder_id: draft.folder_id,
      folder_name: folder.name,
      source_type: "upload",
      visibility: "draft",
      original_filename: draft.original_filename,
      original_width: draft.original_width,
      original_height: draft.original_height,
      content_type: contentType,
      display_mode: displayModeForType(contentType),
      created_at: draft.created_at,
      updated_at: draft.updated_at,
      tags: Array.isArray(version.tags) ? version.tags : [],
    },
  }, folder);
  return {
    ...record,
    serverBacked: true,
    processing_status: draft.processing_status,
    workflow_status: draft.workflow_status,
    publication_status: draft.publication_status,
    deleted_at: draft.deleted_at || null,
    lock_version: Number.isInteger(draft.lock_version) ? draft.lock_version : 1,
    readiness: normalizeReadiness(draft.readiness, {
      id: draft.id,
      workflow_status: draft.workflow_status,
      lock_version: Number.isInteger(draft.lock_version) ? draft.lock_version : 1,
    }),
    version_id: version.id,
    alt_text: version.alt_text || "",
    location_name: version.location_name || "",
    copyright_holder: version.copyright_holder || "",
    copyright_year: Number.isInteger(version.copyright_year) ? version.copyright_year : null,
    contains_recognizable_people: nullableBoolean(version.contains_recognizable_people),
    model_release_status: version.model_release_status || null,
    property_release_status: version.property_release_status || null,
    rights_declared: version.rights_declared === true,
    ai_disclosure: version.ai_disclosure || null,
    sensitive_content_disclosure: version.sensitive_content_disclosure || null,
  };
}

function workspaceDraftPayload(record, { includeCompliance = true } = {}) {
  const payload = {
    folder_id: record.folder_id,
    title: cleanText(record.title),
    caption: cleanText(record.curatorial_note),
    description: cleanText(record.description),
    tags: uniqueTextList(record.customTags || []),
    content_category: contentTypeCode(record.imageRecord?.content_type || record.type),
    captured_at: cleanText(record.captured_at) || null,
    location_name: cleanText(record.location_name),
  };
  if (includeCompliance) {
    Object.assign(payload, {
      alt_text: cleanText(record.alt_text),
      copyright_holder: cleanText(record.copyright_holder),
      copyright_year: Number.isInteger(record.copyright_year) ? record.copyright_year : null,
      contains_recognizable_people: nullableBoolean(record.contains_recognizable_people),
      model_release_status: cleanText(record.model_release_status) || null,
      property_release_status: cleanText(record.property_release_status) || null,
      rights_declared: record.rights_declared === true,
      ai_disclosure: cleanText(record.ai_disclosure) || null,
      sensitive_content_disclosure: cleanText(record.sensitive_content_disclosure) || null,
    });
  }
  return payload;
}

function phase2UploadAssets(record) {
  const original = preferredAsset(record, ["original"]);
  if (!original?.blob) throw new Error("The original image is no longer available for upload.");
  const sources = {
    original,
    display: preferredAsset(record, ["display"]) || original,
    thumbnail: preferredAsset(record, ["thumbnail"]) || preferredAsset(record, ["display"]) || original,
  };
  return ["original", "display", "thumbnail"].map((kind) => {
    const source = sources[kind];
    return {
      kind,
      blob: source.blob,
      mime_type: source.mime_type || source.blob.type || "image/jpeg",
      byte_size: source.byte_size || source.blob.size,
      width: source.width || record.width,
      height: source.height || record.height,
      checksum_sha256: source.checksum_sha256 || original.checksum_sha256,
    };
  });
}

async function createWorkspaceUploadIntent(record, uploadAssets, signal) {
  const original = uploadAssets.find((asset) => asset.kind === "original");
  return workspaceRequest(WORKSPACE_UPLOAD_INTENTS_API, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      folder_id: record.folder_id,
      original_filename: record.imageRecord?.original_filename || record.title,
      original_width: record.width,
      original_height: record.height,
      checksum_sha256: original.checksum_sha256,
      assets: uploadAssets.map(({ blob, ...asset }) => asset),
    }),
  });
}

async function uploadAssetToSignedUrl(destination, asset, signal) {
  const formData = new FormData();
  formData.append("cacheControl", "3600");
  formData.append("", asset.blob, `${destination.kind}.${asset.mime_type.split("/")[1] || "jpg"}`);
  const response = await fetch(destination.signed_url, {
    method: "PUT",
    credentials: "omit",
    headers: { "x-upsert": "false" },
    body: formData,
    signal,
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.message || result.error || `Unable to upload the ${destination.kind} asset.`);
  }
}

async function completeWorkspaceUpload(intent, record, signal) {
  const result = await workspaceRequest(`/api/uploads/${encodeURIComponent(intent.upload_id)}/complete`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({ draft: workspaceDraftPayload(record, { includeCompliance: false }) }),
  });
  return normalizeWorkspaceDraft(result.draft);
}

async function cancelWorkspaceUpload(uploadId) {
  return workspaceRequest(`/api/uploads/${encodeURIComponent(uploadId)}`, {
    method: "DELETE",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation: "cancel-upload" }),
  });
}

async function saveWorkspaceDraft(record) {
  const result = await workspaceRequest(`${WORKSPACE_IMAGES_API}/${encodeURIComponent(record.id)}/draft`, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_version: record.lock_version,
      draft: workspaceDraftPayload(record),
    }),
  });
  return normalizeWorkspaceDraft({
    ...result.draft,
    readiness: record.readiness,
    assets: (record.assets || []).map((asset) => ({
      ...asset,
      storage_key: asset.storage_key || asset.storage_path,
    })),
  });
}

async function getWorkspaceDraftReadiness(recordId) {
  const result = await workspaceRequest(`${WORKSPACE_IMAGES_API}/${encodeURIComponent(recordId)}/readiness`);
  return result.readiness;
}

async function submitWorkspaceDraft(record, idempotencyKey) {
  return workspaceRequest(`${WORKSPACE_IMAGES_API}/${encodeURIComponent(record.id)}/submit`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      confirmation: "submit-for-review",
      expected_version: record.lock_version,
      idempotency_key: idempotencyKey,
    }),
  });
}

async function trashWorkspaceDraft(record) {
  return workspaceRequest(`${WORKSPACE_IMAGES_API}/${encodeURIComponent(record.id)}`, {
    method: "DELETE",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation: "move-to-trash", expected_version: record.lock_version }),
  });
}

async function restoreWorkspaceDraft(recordId) {
  const result = await workspaceRequest(`${WORKSPACE_IMAGES_API}/${encodeURIComponent(recordId)}/restore`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return normalizeWorkspaceDraft(result.draft);
}

async function createWorkspaceFolder(name) {
  return workspaceRequest(WORKSPACE_FOLDERS_API, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

async function renameWorkspaceFolder(folderId, name) {
  return workspaceRequest(`${WORKSPACE_FOLDERS_API}/${encodeURIComponent(folderId)}`, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

async function deleteWorkspaceFolder(folderId) {
  return workspaceRequest(`${WORKSPACE_FOLDERS_API}/${encodeURIComponent(folderId)}`, {
    method: "DELETE",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ non_empty_policy: "move_to_inbox" }),
  });
}

function showToast(message, state = "info") {
  if (!toastElement) {
    return;
  }
  clearTimeout(toastTimer);
  toastElement.textContent = message;
  toastElement.dataset.state = state;
  toastElement.hidden = false;
  toastTimer = window.setTimeout(() => {
    toastElement.hidden = true;
  }, 3600);
}

function setSaveState(message = "", state = "") {
  if (!saveState) {
    return;
  }
  saveState.textContent = message;
  saveState.dataset.state = state;
}

function setGlobalStatus(message) {
  if (statusElement) {
    statusElement.textContent = message;
  }
}

function clearReadinessPoll() {
  if (readinessPollTimer !== null) {
    window.clearTimeout(readinessPollTimer);
    readinessPollTimer = null;
  }
}

function replaceRecordReadiness(recordId, readiness) {
  records = records.map((record) => (record.id === recordId ? { ...record, readiness } : record));
}

function readinessIsPending(readiness) {
  return readiness?.status === "pending" || readiness?.checks?.some((check) => check.state === "pending");
}

function scheduleReadinessPoll(recordId) {
  clearReadinessPoll();
  const record = records.find((item) => item.id === recordId);
  if (
    !record
    || recordId !== activeRecordId
    || document.visibilityState !== "visible"
    || !workspaceOnline
    || draftDirty
    || draftSaveInFlight
    || draftConflict
    || submissionPreparing
    || submissionInFlight
    || !readinessIsPending(record.readiness)
  ) {
    return;
  }
  readinessPollTimer = window.setTimeout(() => {
    readinessPollTimer = null;
    refreshActiveReadiness({ silent: true });
  }, READINESS_POLL_DELAY);
}

function applyReadinessFieldErrors(readiness) {
  if (!formElement) return;
  formElement.querySelectorAll("input[aria-invalid='true'], select[aria-invalid='true'], textarea[aria-invalid='true']")
    .forEach((control) => control.removeAttribute("aria-invalid"));
  if (!readiness || ["ready", "checking", "pending", "stale"].includes(readiness.status)) return;
  const aliases = {
    caption: "curatorial_note",
    content_category: "content_type",
  };
  Object.keys(readiness.field_errors || {}).forEach((field) => {
    const control = formElement.elements.namedItem(aliases[field] || field);
    if (control instanceof HTMLElement) control.setAttribute("aria-invalid", "true");
  });
}

function readinessSummaryText(readiness) {
  if (!workspaceOnline) return "Readiness is unavailable while this Workspace is offline.";
  if (!readiness || readiness.status === "checking") return "Checking submission requirements...";
  if (readiness.status === "submitting") return "Creating the review submission...";
  if (readiness.status === "stale") return "Save the latest changes to refresh readiness.";
  if (readiness.status === "error") return readiness.message || "Readiness could not be checked. Try again.";
  if (readiness.status === "submitted") return "This version has been submitted for review.";
  if (readiness.ready) return "Ready to submit for review.";
  if (readinessIsPending(readiness)) return "Automated checks are still in progress.";
  const blockers = Number.isInteger(readiness.blocker_count) ? readiness.blocker_count : 0;
  return blockers === 1 ? "1 requirement needs attention." : `${blockers || "Some"} requirements need attention.`;
}

function renderReadiness() {
  if (!readinessElement || !readinessList) return;
  const record = records.find((item) => item.id === activeRecordId);
  const readiness = record?.readiness || null;
  const displayStatus = !workspaceOnline ? "error" : readiness?.status || "checking";
  readinessElement.dataset.state = displayStatus;
  readinessElement.setAttribute("aria-busy", String(["checking", "submitting"].includes(displayStatus)));
  if (readinessSummary) readinessSummary.textContent = readinessSummaryText(readiness);
  const checks = readiness?.checks?.length === READINESS_CHECK_DEFAULTS.length
    ? readiness.checks
    : READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "pending" }));
  readinessList.innerHTML = checks.map((check) => {
    const state = ["pass", "pending", "blocked"].includes(check.state) ? check.state : "blocked";
    const icon = state === "pass" ? "icon-check" : state === "pending" ? "icon-retry" : "icon-alert";
    return `
      <li data-state="${state}">
        <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#${icon}"></use></svg>
        <span>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.message)}</small>
        </span>
      </li>`;
  }).join("");
  applyReadinessFieldErrors(readiness);
}

async function refreshActiveReadiness({ silent = false, allowWhileSubmitting = false } = {}) {
  const recordId = activeRecordId;
  const record = records.find((item) => item.id === recordId);
  if (!record || !workspaceOnline) return null;
  if (
    draftDirty
    || draftSaveInFlight
    || draftConflict
    || (submissionPreparing && !allowWhileSubmitting)
    || (submissionInFlight && !allowWhileSubmitting)
  ) {
    return record.readiness || null;
  }
  clearReadinessPoll();
  const requestId = ++readinessRequestId;
  if (!silent) {
    replaceRecordReadiness(recordId, {
      ...(record.readiness || {}),
      image_id: recordId,
      status: "checking",
      ready: false,
      checks: record.readiness?.checks || READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "pending" })),
    });
    renderReadiness();
    setWorkspaceControls();
  }
  try {
    const result = await getWorkspaceDraftReadiness(recordId);
    if (requestId !== readinessRequestId || recordId !== activeRecordId) return null;
    const currentRecord = records.find((item) => item.id === recordId);
    if (!currentRecord) return null;
    const readiness = normalizeReadiness(result, currentRecord);
    if (!readiness || (readiness.image_id && readiness.image_id !== recordId)) {
      throw new Error("The readiness response did not match this Draft.");
    }
    if (Number.isInteger(readiness.lock_version) && readiness.lock_version !== currentRecord.lock_version) {
      draftConflict = true;
      readiness.ready = false;
      readiness.status = "blocked";
      readiness.message = "A newer server Draft exists. Reload it before submitting.";
      readiness.blocker_count = Math.max(readiness.blocker_count || 0, 1);
      setSaveState("A newer server Draft exists. Reload before saving or submitting.", "conflict");
    }
    replaceRecordReadiness(recordId, readiness);
    renderReadiness();
    setWorkspaceControls();
    scheduleReadinessPoll(recordId);
    return readiness;
  } catch (error) {
    if (requestId !== readinessRequestId || recordId !== activeRecordId) return null;
    const currentRecord = records.find((item) => item.id === recordId);
    const errorReadiness = {
      ...(currentRecord?.readiness || {}),
      image_id: recordId,
      status: "error",
      ready: false,
      message: error?.message || "Readiness could not be checked. Try again.",
      checks: currentRecord?.readiness?.checks || READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "blocked" })),
    };
    replaceRecordReadiness(recordId, errorReadiness);
    renderReadiness();
    setWorkspaceControls();
    return errorReadiness;
  }
}

function taskLabel(stage) {
  const labels = {
    queued: "Queued",
    reading: "Reading",
    compressing: "Compressing",
    slicing: "Slicing",
    analyzing: "Analyzing",
    uploading: "Uploading",
    canceling: "Canceling",
    canceled: "Canceled",
    complete: "Draft ready",
    warning: "Offline cache",
    failed: "Failed",
  };
  return labels[stage] || "Working";
}

function createTask(file, index, folder) {
  const task = {
    id: crypto.randomUUID ? `studio-task-${crypto.randomUUID()}` : `studio-task-${Date.now()}-${index}`,
    name: file.name || `Image ${index + 1}`,
    file,
    folder_id: folder.id,
    folder_name: folder.name,
    stage: "queued",
    progress: 0,
    message: "Waiting to start.",
    attempt: 0,
    inFlight: false,
    cancelRequested: false,
    retryable: false,
    recordId: null,
    localRecord: null,
    uploadAssets: null,
    intent: null,
    cleanupStatus: null,
    cleanupPromise: null,
    abortController: null,
    update(stage, progress, message) {
      this.stage = stage;
      this.progress = progress;
      this.message = message;
      renderAll();
    },
  };
  if (WORKSPACE_IMAGE_MIME_TYPES.has(file.type)) {
    task.previewUrl = URL.createObjectURL(file);
    objectUrls.add(task.previewUrl);
  }
  return task;
}

function updateRecordTask(recordId, stage, progress, message) {
  const task = taskByRecordId.get(recordId);
  if (!task) {
    return;
  }
  task.stage = stage;
  task.progress = progress;
  task.message = message;
  renderAll();
}

function recordsForActiveFolder() {
  return records.filter((record) => record.folder_id === activeFolderId);
}

function tasksForActiveFolder() {
  return uploadTasks.filter((task) => task.folder_id === activeFolderId && !task.recordId);
}

function taskIsActive(task) {
  return !["complete", "failed", "canceled"].includes(task.stage);
}

function taskPreviewUrl(task) {
  return task.localRecord ? thumbnailUrl(task.localRecord) : task.previewUrl || "";
}

function releaseTaskRuntime(task) {
  const urls = new Set([task.previewUrl]);
  (task.localRecord?.assets || []).forEach((asset) => urls.add(asset.objectUrl));
  urls.forEach((url) => {
    if (!url) return;
    URL.revokeObjectURL(url);
    objectUrls.delete(url);
  });
  task.previewUrl = "";
  task.localRecord = null;
  task.uploadAssets = null;
  task.file = null;
}

function renderFolders() {
  workspaceViewButtons.forEach((button) => {
    const selected = button.dataset.studioView === activeWorkspaceView;
    button.setAttribute("aria-pressed", String(selected));
    button.classList.toggle("is-active", selected);
  });
  if (draftCountElement) draftCountElement.textContent = String(records.length);
  if (trashCountElement) {
    trashCountElement.hidden = !trashLoaded;
    trashCountElement.textContent = String(trashedRecords.length);
  }
  if (workspaceLoading) {
    if (folderSummary) folderSummary.textContent = "Loading folders";
    if (folderList) {
      folderList.innerHTML = '<div class="upload-studio-folder-loading" aria-hidden="true"><span></span><span></span></div>';
    }
    if (folderSelect) {
      folderSelect.innerHTML = "";
      folderSelect.disabled = true;
    }
    return;
  }
  const showingTrash = activeWorkspaceView === "trash";
  if (folderPanelTitle) folderPanelTitle.textContent = showingTrash ? "Trash" : "Folders";
  if (folderForm) folderForm.hidden = showingTrash;
  if (folderList) folderList.hidden = showingTrash;
  if (showingTrash) {
    if (folderSummary) {
      folderSummary.textContent = trashLoading
        ? "Loading items"
        : trashError
          ? "Unavailable"
          : `${trashedRecords.length} item${trashedRecords.length === 1 ? "" : "s"}`;
    }
  } else if (folderSummary) {
    folderSummary.textContent = `${folders.length} folder${folders.length === 1 ? "" : "s"}`;
  }
  if (folderList && !showingTrash) {
    folderList.innerHTML = folders
      .map((folder) => {
        const recordCount = records.filter((record) => record.folder_id === folder.id).length;
        const pendingCount = uploadTasks.filter((task) => task.folder_id === folder.id && !task.recordId).length;
        const count = recordCount + pendingCount;
        return `
          <div class="upload-studio-folder-row">
            <button class="upload-studio-folder ${folder.id === activeFolderId ? "is-active" : ""}" type="button" data-folder-id="${escapeHtml(folder.id)}">
              <span>
                <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#icon-folder"></use></svg>
                ${escapeHtml(folder.name)}
              </span>
              <small>${count}</small>
            </button>
            ${folder.is_system || !workspaceOnline ? "" : `
              <span class="upload-studio-folder-actions">
                <button type="button" data-folder-rename="${escapeHtml(folder.id)}" aria-label="Rename ${escapeHtml(folder.name)}" data-tooltip="Rename folder">
                  <svg class="ui-icon" aria-hidden="true"><use href="#icon-pen"></use></svg>
                </button>
                <button type="button" data-folder-delete="${escapeHtml(folder.id)}" aria-label="Delete ${escapeHtml(folder.name)}" data-tooltip="Delete folder">
                  <svg class="ui-icon" aria-hidden="true"><use href="#icon-trash"></use></svg>
                </button>
              </span>
            `}
          </div>
        `;
      })
      .join("");
  }
  if (folderSelect) {
    const selectedFolderId = folderSelect.value;
    folderSelect.innerHTML = folders.map((folder) => `<option value="${escapeHtml(folder.id)}">${escapeHtml(folder.name)}</option>`).join("");
    if (folders.some((folder) => folder.id === selectedFolderId)) {
      folderSelect.value = selectedFolderId;
    }
    folderSelect.disabled = !workspaceOnline;
  }
}

function renderTrashQueue() {
  if (!queueElement) return;
  queueElement.setAttribute("aria-busy", String(workspaceLoading || trashLoading));
  if (workspaceLoading || trashLoading) {
    queueElement.innerHTML = `
      <article class="upload-studio-empty upload-studio-loading" aria-label="Loading Trash">
        <span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>
      </article>`;
    return;
  }
  if (trashError) {
    const permissionError = trashError.status === 403;
    queueElement.innerHTML = `
      <article class="upload-studio-empty upload-studio-trash-message" data-state="error">
        <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#icon-alert"></use></svg>
        <h2>${permissionError ? "Trash access unavailable" : "Trash could not be loaded"}</h2>
        <p>${escapeHtml(permissionError ? "Your account cannot read or restore these Drafts." : trashError.message || "Try loading Trash again.")}</p>
        ${permissionError ? "" : `<button class="upload-studio-secondary" type="button" data-trash-retry>
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-retry"></use></svg>
          Retry
        </button>`}
      </article>`;
    return;
  }
  if (!trashedRecords.length) {
    queueElement.innerHTML = `
      <article class="upload-studio-empty">
        <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#icon-trash"></use></svg>
        <h2>Trash is empty</h2>
      </article>`;
    return;
  }
  queueElement.innerHTML = trashedRecords.map((record) => {
    const restoring = restoringTrashIds.has(record.id);
    const restoreError = trashRestoreErrors.get(record.id);
    return `
      <article class="upload-studio-card upload-studio-trash-card" aria-busy="${restoring}" data-state="${restoreError ? "failed" : "trashed"}">
        <div class="upload-studio-card-main">
          <img src="${escapeHtml(thumbnailUrl(record))}" alt="" loading="lazy" decoding="async" />
          <span class="upload-studio-card-copy">
            <strong>${escapeHtml(record.title || "Untitled Work")}</strong>
            <small>Moved ${escapeHtml(formatTrashDate(record.deleted_at))}</small>
            ${restoreError ? `<small class="upload-studio-trash-error" role="alert">${escapeHtml(restoreError)}</small>` : ""}
          </span>
          <span class="upload-studio-card-state" data-state="${restoring ? "canceling" : "canceled"}">${restoring ? "Restoring" : "Trashed"}</span>
        </div>
        <span class="upload-studio-task-actions">
          <button type="button" data-trash-restore="${escapeHtml(record.id)}" aria-label="Restore ${escapeHtml(record.title || "Untitled Work")}" data-tooltip="Restore Draft" ${restoring || !workspaceOnline ? "disabled" : ""}>
            <svg class="ui-icon" aria-hidden="true"><use href="#icon-retry"></use></svg>
          </button>
        </span>
      </article>`;
  }).join("");
}

function renderQueue() {
  if (activeWorkspaceView === "trash") {
    renderTrashQueue();
    return;
  }
  if (queueElement) queueElement.setAttribute("aria-busy", String(workspaceLoading));
  if (workspaceLoading) {
    if (countElement) countElement.textContent = "–";
    if (statusElement) statusElement.textContent = "Loading";
    if (queueElement) {
      queueElement.innerHTML = `
        <article class="upload-studio-empty upload-studio-loading" aria-label="Loading workspace">
          <span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>
        </article>`;
    }
    return;
  }
  const activeRecords = recordsForActiveFolder();
  const activeTasks = tasksForActiveFolder();
  const itemCount = activeRecords.length + activeTasks.length;
  if (countElement) {
    countElement.textContent = String(itemCount);
  }
  if (statusElement) {
    const workingCount = activeTasks.filter(taskIsActive).length;
    const failedCount = activeTasks.filter((task) => task.stage === "failed").length;
    const canceledCount = activeTasks.filter((task) => task.stage === "canceled").length;
    statusElement.textContent = !workspaceOnline
      ? "Offline"
      : workingCount
        ? `${workingCount} active`
        : failedCount
          ? `${failedCount} failed`
          : canceledCount
            ? `${canceledCount} canceled`
            : "Ready";
  }
  if (!queueElement) {
    return;
  }
  if (!itemCount) {
    queueElement.innerHTML = `
      <article class="upload-studio-empty">
        <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#icon-image"></use></svg>
        <h2>No image in ${escapeHtml(activeFolder().name)}</h2>
      </article>
    `;
    return;
  }
  const taskCards = activeTasks.map((task) => {
    const preview = taskPreviewUrl(task);
    const canRetry = !task.inFlight && ["failed", "canceled"].includes(task.stage);
    const canCancel = !task.cancelRequested && (task.inFlight || task.stage === "queued");
    const canDismiss = !task.inFlight && ["failed", "canceled"].includes(task.stage);
    const actions = [
      canRetry ? `
        <button type="button" data-task-retry="${escapeHtml(task.id)}" aria-label="Retry ${escapeHtml(task.name)}" data-tooltip="Retry upload">
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-retry"></use></svg>
        </button>` : "",
      canCancel ? `
        <button type="button" data-task-cancel="${escapeHtml(task.id)}" aria-label="Cancel ${escapeHtml(task.name)}" data-tooltip="Cancel upload">
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-x"></use></svg>
        </button>` : "",
      canDismiss ? `
        <button type="button" data-task-dismiss="${escapeHtml(task.id)}" aria-label="Remove ${escapeHtml(task.name)}" data-tooltip="Remove from queue">
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-trash"></use></svg>
        </button>` : "",
    ].join("");
    return `
      <article class="upload-studio-card upload-studio-task" data-state="${escapeHtml(task.stage)}">
        <div class="upload-studio-card-main">
          ${preview
            ? `<img src="${escapeHtml(preview)}" alt="" />`
            : `<span class="upload-studio-task-placeholder"><svg class="ui-icon" aria-hidden="true"><use href="#icon-image"></use></svg></span>`}
          <span class="upload-studio-card-copy">
            <strong>${escapeHtml(task.name)}</strong>
            <small>${escapeHtml(task.message)}</small>
            <small>Attempt ${task.attempt || 1}</small>
          </span>
          <span class="upload-studio-card-state" data-state="${escapeHtml(task.stage)}">${escapeHtml(taskLabel(task.stage))}</span>
        </div>
        <span class="upload-studio-task-actions">${actions}</span>
        <span class="upload-studio-progress" aria-hidden="true"><span style="width:${Math.min(Math.max(task.progress, 0), 100)}%;"></span></span>
      </article>`;
  });
  const recordCards = activeRecords
    .map((record) => {
      const task = taskByRecordId.get(record.id);
      const stage = task?.stage || "complete";
      const progress = task?.progress ?? 100;
      const original = preferredAsset(record, ["original"]);
      const display = preferredAsset(record, ["display"]);
      return `
        <article class="upload-studio-card ${record.id === activeRecordId ? "is-active" : ""}">
          <button class="upload-studio-card-main" type="button" data-record-id="${escapeHtml(record.id)}">
            <img src="${escapeHtml(thumbnailUrl(record))}" alt="${escapeHtml(record.title || "Uploaded image preview")}" loading="lazy" decoding="async" />
            <span class="upload-studio-card-copy">
              <strong>${escapeHtml(record.title || "Untitled Work")}</strong>
              <small>${escapeHtml(contentTypeLabel(record.imageRecord?.content_type || record.type))} / ${escapeHtml(record.ratio || "1:1")}</small>
              <small>${escapeHtml(formatBytes(original?.byte_size))} -> ${escapeHtml(formatBytes(display?.byte_size || original?.byte_size))}</small>
            </span>
            <span class="upload-studio-card-state" data-state="${escapeHtml(stage)}">${escapeHtml(taskLabel(stage))}</span>
          </button>
          <span class="upload-studio-progress" aria-hidden="true"><span style="width:${Math.min(Math.max(progress, 0), 100)}%;"></span></span>
        </article>`;
    });
  queueElement.innerHTML = [...taskCards, ...recordCards].join("");
}

function renderEditor() {
  const record = activeWorkspaceView === "drafts" ? records.find((item) => item.id === activeRecordId) : null;
  if (!record) {
    formRecordId = null;
    if (studioGrid) studioGrid.dataset.editorState = "empty";
    if (emptyElement) {
      emptyElement.hidden = false;
    }
    if (formElement) {
      formElement.hidden = true;
    }
    if (deleteRecordButton) {
      deleteRecordButton.disabled = true;
    }
    return;
  }
  if (studioGrid) studioGrid.dataset.editorState = "active";
  if (emptyElement) {
    emptyElement.hidden = true;
  }
  if (formElement) {
    const elements = formElement.elements;
    const shouldHydrateForm = formRecordId !== record.id || (!draftDirty && !draftSaveInFlight);
    formRecordId = record.id;
    formElement.hidden = false;
    if (shouldHydrateForm) {
      elements.namedItem("title").value = record.title || "";
      const seriesField = elements.namedItem("series");
      if (seriesField) seriesField.value = record.series || "";
      elements.namedItem("captured_at").value = cleanText(record.captured_at).slice(0, 10);
      elements.namedItem("location_name").value = record.location_name || "";
      elements.namedItem("content_type").value = contentTypeCode(record.imageRecord?.content_type || record.type);
      elements.namedItem("curatorial_note").value = record.curatorial_note || "";
      elements.namedItem("description").value = record.description || "";
      elements.namedItem("tags").value = uniqueTextList(record.customTags || []).join(", ");
      elements.namedItem("alt_text").value = record.alt_text || "";
      elements.namedItem("copyright_holder").value = record.copyright_holder || "";
      elements.namedItem("copyright_year").value = Number.isInteger(record.copyright_year) ? String(record.copyright_year) : "";
      elements.namedItem("contains_recognizable_people").value = record.contains_recognizable_people === true
        ? "true"
        : record.contains_recognizable_people === false ? "false" : "";
      elements.namedItem("model_release_status").value = record.model_release_status === "not_applicable"
        ? ""
        : record.model_release_status || "";
      elements.namedItem("property_release_status").value = record.property_release_status || "";
      elements.namedItem("rights_declared").checked = record.rights_declared === true;
      elements.namedItem("ai_disclosure").value = record.ai_disclosure || "";
      elements.namedItem("sensitive_content_disclosure").value = record.sensitive_content_disclosure || "";
      syncComplianceFieldVisibility();
      if (folderSelect) {
        folderSelect.value = record.folder_id || activeFolderId;
      }
    }
  }
  if (previewImage) {
    previewImage.src = displayUrl(record);
    previewImage.alt = record.title || "Uploaded image preview";
  }
  if (studioTitle) {
    studioTitle.textContent = record.title || "Untitled Work";
  }
  if (studioKicker) {
    studioKicker.textContent = `${record.folder_name || activeFolder().name} / ${taskLabel(taskByRecordId.get(record.id)?.stage || "complete")}`;
  }
  if (assetSummary) {
    const original = preferredAsset(record, ["original"]);
    const display = preferredAsset(record, ["display"]);
    const thumbnail = preferredAsset(record, ["thumbnail"]);
    assetSummary.innerHTML = [
      ["Original", `${record.width} x ${record.height} / ${formatBytes(original?.byte_size)}`],
      ["Display", display ? `${display.width} x ${display.height} / ${formatBytes(display.byte_size)}` : "Original fallback"],
      ["Thumbnail", thumbnail ? `${thumbnail.width} x ${thumbnail.height} / ${formatBytes(thumbnail.byte_size)}` : "Not generated"],
      ["Status", titleCase(record.visibility || "draft")],
    ]
      .map(([term, value]) => `<div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>`)
      .join("");
  }
  if (deleteRecordButton) {
    deleteRecordButton.disabled = false;
  }
}

function renderAll() {
  if (studioGrid) studioGrid.dataset.view = activeWorkspaceView;
  draftsOnlyElements.forEach((element) => { element.hidden = activeWorkspaceView !== "drafts"; });
  renderFolders();
  renderQueue();
  renderEditor();
  renderReadiness();
  setWorkspaceControls();
}

function setWorkspaceControls() {
  const record = activeWorkspaceView === "drafts" ? records.find((item) => item.id === activeRecordId) : null;
  const workspaceBusy = submissionPreparing || submissionInFlight || restoringTrashIds.size > 0;
  const importDisabled = workspaceLoading || activeWorkspaceView !== "drafts" || !workspaceOnline || workspaceBusy;
  if (uploadInput) uploadInput.disabled = importDisabled;
  if (primaryImport) primaryImport.setAttribute("aria-disabled", String(importDisabled));
  if (dropzone) dropzone.setAttribute("aria-disabled", String(importDisabled));
  folderForm?.querySelectorAll("input, button").forEach((control) => { control.disabled = importDisabled; });
  folderList?.querySelectorAll("button").forEach((control) => { control.disabled = workspaceBusy; });
  queueElement?.querySelectorAll("button").forEach((control) => {
    if (control.matches("[data-trash-restore]")) {
      control.disabled = workspaceBusy || !workspaceOnline || restoringTrashIds.has(control.dataset.trashRestore);
    } else if (control.matches("[data-trash-retry]")) {
      control.disabled = workspaceBusy || !workspaceOnline || trashLoading;
    } else {
      control.disabled = workspaceBusy;
    }
  });
  workspaceViewButtons.forEach((button) => {
    button.disabled = workspaceLoading || workspaceBusy || (button.dataset.studioView === "trash" && !workspaceOnline);
  });
  formElement?.querySelectorAll("input, select, textarea").forEach((control) => {
    control.disabled = activeWorkspaceView !== "drafts" || !workspaceOnline || submissionInFlight;
  });
  if (saveRecordButton) {
    saveRecordButton.disabled = !workspaceOnline || !activeRecordId || draftSaveInFlight || draftConflict || workspaceBusy;
  }
  if (reloadRecordButton) {
    reloadRecordButton.hidden = !draftConflict;
    reloadRecordButton.disabled = !workspaceOnline || draftSaveInFlight || workspaceBusy;
  }
  if (deleteRecordButton) {
    deleteRecordButton.disabled = !workspaceOnline || !activeRecordId || draftSaveInFlight || draftConflict || workspaceBusy;
  }
  if (readinessRefreshButton) {
    readinessRefreshButton.disabled = !workspaceOnline
      || !activeRecordId
      || draftDirty
      || draftSaveInFlight
      || draftConflict
      || workspaceBusy
      || record?.readiness?.status === "checking";
  }
  if (submitRecordLabel) {
    submitRecordLabel.textContent = submissionInFlight
      ? (record?.readiness?.status === "submitting" ? "Submitting..." : "Checking...")
      : record?.workflow_status === "changes_requested" ? "Resubmit for Review" : "Submit for Review";
  }
  if (submitRecordButton) {
    submitRecordButton.disabled = !workspaceOnline
      || !activeRecordId
      || draftDirty
      || draftSaveInFlight
      || draftConflict
      || workspaceBusy
      || record?.readiness?.status !== "ready"
      || record?.readiness?.ready !== true
      || !["draft", "changes_requested"].includes(record?.workflow_status || "draft");
  }
}

function recordFromForm(record) {
  const formData = new FormData(formElement);
  const folder = folderById(formData.get("folder_id"));
  const contentType = contentTypeCode(formData.get("content_type"));
  const displayMode = displayModeForType(contentType);
  const customTags = splitTags(formData.get("tags"));
  const title = cleanText(formData.get("title"));
  const containsRecognizablePeople = nullableBoolean(formData.get("contains_recognizable_people"));
  const copyrightYearText = cleanText(formData.get("copyright_year"));
  const modelReleaseStatus = containsRecognizablePeople === false
    ? "not_applicable"
    : cleanText(formData.get("model_release_status")) || null;
  const next = {
    ...record,
    title,
    series: cleanText(formData.get("series")),
    captured_at: cleanText(formData.get("captured_at")),
    location_name: cleanText(formData.get("location_name")),
    curatorial_note: cleanText(formData.get("curatorial_note")),
    description: cleanText(formData.get("description")),
    alt_text: cleanText(formData.get("alt_text")),
    copyright_holder: cleanText(formData.get("copyright_holder")),
    copyright_year: copyrightYearText ? Number.parseInt(copyrightYearText, 10) : null,
    contains_recognizable_people: containsRecognizablePeople,
    model_release_status: modelReleaseStatus,
    property_release_status: cleanText(formData.get("property_release_status")) || null,
    rights_declared: formElement.elements.namedItem("rights_declared").checked,
    ai_disclosure: cleanText(formData.get("ai_disclosure")) || null,
    sensitive_content_disclosure: cleanText(formData.get("sensitive_content_disclosure")) || null,
    visibility: "draft",
    folder_id: folder.id,
    folder_name: folder.name,
    customTags,
    imageRecord: {
      ...(record.imageRecord || {}),
      title,
      series: cleanText(formData.get("series")),
      captured_at: cleanText(formData.get("captured_at")),
      curatorial_note: cleanText(formData.get("curatorial_note")),
      description: cleanText(formData.get("description")),
      visibility: "draft",
      content_type: contentType,
      display_mode: displayMode,
      folder_id: folder.id,
      folder_name: folder.name,
      updated_at: nowIso(),
    },
  };
  return normalizeRecord(next, folder);
}

function syncComplianceFieldVisibility() {
  if (!modelReleaseField || !recognizablePeopleSelect) return;
  modelReleaseField.hidden = recognizablePeopleSelect.value !== "true";
}

function clearAutosaveTimer() {
  if (autosaveTimer !== null) {
    window.clearTimeout(autosaveTimer);
    autosaveTimer = null;
  }
}

function resetDraftEditState(message = "") {
  clearAutosaveTimer();
  clearReadinessPoll();
  readinessRequestId += 1;
  draftEditRevision = 0;
  draftDirty = false;
  draftConflict = false;
  pendingAutosave = false;
  formRecordId = null;
  setSaveState(message, message ? "saved" : "");
  setWorkspaceControls();
}

function scheduleAutosave(delay = DRAFT_AUTOSAVE_DELAY) {
  clearAutosaveTimer();
  if (!draftDirty || draftConflict || submissionInFlight || !workspaceOnline || !activeRecordId) return;
  autosaveTimer = window.setTimeout(() => {
    autosaveTimer = null;
    saveActiveRecord({ source: "autosave" });
  }, delay);
}

function markDraftDirty() {
  if (!activeRecordId || formRecordId !== activeRecordId || submissionInFlight) return;
  clearReadinessPoll();
  readinessRequestId += 1;
  draftEditRevision += 1;
  draftDirty = true;
  if (draftConflict) {
    setSaveState("A newer server Draft exists. Reload before saving.", "conflict");
    setWorkspaceControls();
    return;
  }
  const record = records.find((item) => item.id === activeRecordId);
  replaceRecordReadiness(activeRecordId, {
    ...(record?.readiness || {}),
    image_id: activeRecordId,
    status: "stale",
    ready: false,
    checks: record?.readiness?.checks || READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "pending" })),
  });
  renderReadiness();
  setSaveState("Unsaved changes. Saving automatically...", "dirty");
  setWorkspaceControls();
  if (draftSaveInFlight) {
    pendingAutosave = true;
    return;
  }
  scheduleAutosave();
}

async function persistRecord(record) {
  const savedRecord = await saveWorkspaceDraft(record);
  records = records.map((item) => (item.id === record.id ? savedRecord : item));
  if (!records.some((item) => item.id === savedRecord.id)) {
    records = [savedRecord, ...records];
  }
  let cacheSaved = true;
  try {
    await putStoredItem(savedRecord);
  } catch (_error) {
    cacheSaved = false;
  }
  return { savedRecord, cacheSaved };
}

async function performDraftSave(source) {
  const record = records.find((item) => item.id === activeRecordId);
  if (!record || !formElement) {
    return false;
  }
  if (!workspaceOnline) {
    setSaveState("Offline cache is read-only. Reconnect before saving.", "warning");
    return false;
  }
  if (!draftDirty) {
    setSaveState("All changes saved.", "saved");
    return true;
  }
  const valid = source === "manual" ? formElement.reportValidity() : formElement.checkValidity();
  if (!valid) {
    setSaveState("Fix the invalid fields before this Draft can be saved.", "error");
    return false;
  }
  const savingRecordId = record.id;
  const savingRevision = draftEditRevision;
  const nextRecord = recordFromForm(record);
  let refreshReadinessAfterSave = false;
  draftSaveInFlight = true;
  setSaveState(source === "autosave" ? "Saving changes..." : "Saving Draft...", "saving");
  setWorkspaceControls();
  try {
    const { savedRecord, cacheSaved } = await persistRecord(nextRecord);
    activeFolderId = savedRecord.folder_id;
    saveActiveFolder();
    renderFolders();
    renderQueue();
    renderEditor();
    if (activeRecordId === savingRecordId && draftEditRevision === savingRevision) {
      draftDirty = false;
      pendingAutosave = false;
      refreshReadinessAfterSave = true;
      const successMessage = cacheSaved
        ? (source === "autosave" ? "Saved automatically." : "Saved to your secure Workspace.")
        : "Saved to the server. Offline cache is unavailable.";
      setSaveState(successMessage, cacheSaved ? "saved" : "warning");
      if (source === "manual") showToast("Draft information saved.");
    } else {
      draftDirty = true;
      pendingAutosave = true;
      setSaveState("Unsaved changes. Saving automatically...", "dirty");
    }
    return true;
  } catch (error) {
    draftDirty = true;
    if (error?.code === "DRAFT_VERSION_CONFLICT") {
      clearAutosaveTimer();
      pendingAutosave = false;
      draftConflict = true;
      setSaveState("A newer server Draft exists. Reload before saving.", "conflict");
      showToast("Draft changed elsewhere. Reload the server version before continuing.", "error");
    } else {
      setSaveState(error?.message || "Save failed. Your changes remain in this form.", "error");
      showToast("Draft save failed. Your changes remain in this form.", "error");
    }
    return false;
  } finally {
    draftSaveInFlight = false;
    setWorkspaceControls();
    if (refreshReadinessAfterSave && activeRecordId === savingRecordId && !draftDirty && !draftConflict) {
      refreshActiveReadiness();
    }
  }
}

async function saveActiveRecord({ source = "manual" } = {}) {
  clearAutosaveTimer();
  if (draftConflict || submissionInFlight) return false;
  if (activeSavePromise) {
    pendingAutosave = true;
    return activeSavePromise;
  }
  activeSavePromise = performDraftSave(source);
  const saved = await activeSavePromise;
  activeSavePromise = null;
  if (pendingAutosave && draftDirty && !draftConflict) {
    pendingAutosave = false;
    scheduleAutosave(0);
  }
  return saved;
}

async function flushDraftBeforeNavigation() {
  clearAutosaveTimer();
  if (activeSavePromise) await activeSavePromise;
  if (draftDirty && !draftConflict) {
    const saved = await saveActiveRecord({ source: "navigation" });
    if (!saved) return false;
  }
  return !draftDirty && !draftConflict;
}

async function reloadActiveRecord() {
  const recordId = activeRecordId;
  if (!recordId || draftSaveInFlight || submissionPreparing || submissionInFlight || !workspaceOnline) return;
  clearAutosaveTimer();
  setSaveState("Reloading server Draft...", "saving");
  setWorkspaceControls();
  try {
    await loadExistingUploadRecords();
    if (!records.some((record) => record.id === recordId)) {
      throw new Error("This Draft is no longer available.");
    }
    activeRecordId = recordId;
    activeFolderId = records.find((record) => record.id === recordId).folder_id;
    saveActiveFolder();
    resetDraftEditState("Server Draft loaded.");
    renderAll();
    refreshActiveReadiness();
  } catch (error) {
    setSaveState(error?.message || "Unable to reload the server Draft.", "error");
    showToast("Unable to reload the server Draft.", "error");
  }
}

function confirmDraftSubmission(record) {
  const title = record?.title || "Untitled Work";
  if (!submitDialog || typeof submitDialog.showModal !== "function") {
    return Promise.resolve(window.confirm(`Submit "${title}" for review?`));
  }
  if (submitDialogTitle) submitDialogTitle.textContent = `Submit "${title}"?`;
  submitDialog.returnValue = "";
  submitDialog.showModal();
  return new Promise((resolve) => {
    submitDialog.addEventListener("close", () => resolve(submitDialog.returnValue === "confirm"), { once: true });
  });
}

function createSubmissionIdempotencyKey(recordId) {
  const existing = submissionIdempotencyKeys.get(recordId);
  if (existing) return existing;
  const key = crypto.randomUUID();
  submissionIdempotencyKeys.set(recordId, key);
  return key;
}

function focusReadiness() {
  readinessElement?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  readinessRefreshButton?.focus({ preventScroll: true });
}

async function performActiveRecordSubmission() {
  const recordId = activeRecordId;
  if (!recordId || !workspaceOnline || submissionPreparing || submissionInFlight) return false;
  submissionPreparing = true;
  setWorkspaceControls();
  let submitted = false;
  let nextRecordId = null;
  try {
    const saved = await flushDraftBeforeNavigation();
    if (!saved || activeRecordId !== recordId) {
      showToast("Save the latest Draft changes before submitting.", "error");
      return false;
    }
    submissionInFlight = true;
    clearReadinessPoll();
    setWorkspaceControls();
    const readiness = await refreshActiveReadiness({ allowWhileSubmitting: true });
    const currentRecord = records.find((item) => item.id === recordId);
    if (!currentRecord || !readiness?.ready || readiness.status !== "ready" || draftConflict) {
      showToast(readiness?.message || "This Draft is not ready to submit.", "error");
      focusReadiness();
      return false;
    }
    const confirmed = await confirmDraftSubmission(currentRecord);
    if (!confirmed) return false;

    replaceRecordReadiness(recordId, { ...readiness, status: "submitting", ready: false });
    renderReadiness();
    setWorkspaceControls();
    const idempotencyKey = createSubmissionIdempotencyKey(recordId);
    const result = await submitWorkspaceDraft(currentRecord, idempotencyKey);
    submissionIdempotencyKeys.delete(recordId);
    let cacheDeleted = true;
    try {
      await deleteStoredItem(recordId);
    } catch (_error) {
      cacheDeleted = false;
    }
    (currentRecord.assets || []).forEach((asset) => {
      if (asset.objectUrl) {
        URL.revokeObjectURL(asset.objectUrl);
        objectUrls.delete(asset.objectUrl);
      }
    });
    records = records.filter((item) => item.id !== recordId);
    const completedTask = taskByRecordId.get(recordId);
    taskByRecordId.delete(recordId);
    uploadTasks = uploadTasks.filter((task) => task !== completedTask);
    activeRecordId = recordsForActiveFolder()[0]?.id || null;
    nextRecordId = activeRecordId;
    submitted = true;
    resetDraftEditState(activeRecordId ? "All changes saved." : "");
    const submissionStatus = cleanText(result.submission?.status || "submitted").replaceAll("_", " ");
    showToast(cacheDeleted
      ? `Draft submitted for review (${submissionStatus}).`
      : `Draft submitted for review (${submissionStatus}); offline cache cleanup is pending.`);
    return true;
  } catch (error) {
    if (error?.status && error.status < 500) submissionIdempotencyKeys.delete(recordId);
    const currentRecord = records.find((item) => item.id === recordId);
    if (error?.readiness && currentRecord) {
      replaceRecordReadiness(recordId, normalizeReadiness(error.readiness, currentRecord));
    }
    if (error?.code === "DRAFT_VERSION_CONFLICT") {
      draftConflict = true;
      clearReadinessPoll();
      setSaveState("A newer server Draft exists. Reload before submitting.", "conflict");
      showToast("Draft changed elsewhere. Reload the server version before submitting.", "error");
    } else {
      const record = records.find((item) => item.id === recordId);
      const currentReadiness = record?.readiness;
      replaceRecordReadiness(recordId, {
        ...(currentReadiness || {}),
        image_id: recordId,
        status: error?.readiness ? currentReadiness?.status || "blocked" : "error",
        ready: false,
        message: error?.message || "Submission failed. Try again.",
        checks: currentReadiness?.checks || READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "blocked" })),
      });
      showToast(error?.message || "Submission failed. The Draft remains available.", "error");
    }
    return false;
  } finally {
    submissionPreparing = false;
    submissionInFlight = false;
    renderAll();
    if (submitted && nextRecordId) {
      refreshActiveReadiness();
    } else {
      const activeRecord = records.find((item) => item.id === activeRecordId);
      if (activeRecord && readinessIsPending(activeRecord.readiness)) scheduleReadinessPoll(activeRecord.id);
    }
  }
}

async function submitActiveRecord() {
  if (activeSubmissionPromise) return activeSubmissionPromise;
  activeSubmissionPromise = performActiveRecordSubmission();
  try {
    return await activeSubmissionPromise;
  } finally {
    activeSubmissionPromise = null;
  }
}

async function deleteActiveRecord() {
  if (submissionPreparing || submissionInFlight) return;
  const recordId = activeRecordId;
  let record = records.find((item) => item.id === recordId);
  if (!record) {
    return;
  }
  if (!workspaceOnline) {
    showToast("Offline cache is read-only.", "error");
    return;
  }
  if (!(await flushDraftBeforeNavigation())) return;
  if (activeRecordId !== recordId) return;
  record = records.find((item) => item.id === recordId);
  if (!record) return;
  const confirmed = window.confirm(`Move "${record.title || "Untitled Work"}" to Trash?`);
  if (!confirmed) {
    return;
  }
  setSaveState("Deleting image...", "saving");
  if (deleteRecordButton) {
    deleteRecordButton.disabled = true;
  }
  try {
    await trashWorkspaceDraft(record);
    let cacheDeleted = true;
    try {
      await deleteStoredItem(record.id);
    } catch (_error) {
      cacheDeleted = false;
    }
    (record.assets || []).forEach((asset) => {
      if (asset.objectUrl) {
        URL.revokeObjectURL(asset.objectUrl);
        objectUrls.delete(asset.objectUrl);
      }
    });
    records = records.filter((item) => item.id !== record.id);
    if (trashLoaded) {
      trashedRecords = [{ ...record, deleted_at: nowIso(), publication_status: "deleted" }, ...trashedRecords];
    }
    const completedTask = taskByRecordId.get(record.id);
    taskByRecordId.delete(record.id);
    uploadTasks = uploadTasks.filter((task) => task !== completedTask);
    activeRecordId = recordsForActiveFolder()[0]?.id || null;
    resetDraftEditState(cacheDeleted ? "Draft moved to Trash." : "Draft moved to Trash. Offline cache cleanup is pending.");
    showToast(cacheDeleted ? "Draft moved to Trash." : "Draft moved to Trash; offline cache cleanup is pending.");
    renderAll();
    if (activeRecordId) refreshActiveReadiness();
  } catch (error) {
    if (error?.code === "DRAFT_VERSION_CONFLICT") {
      draftConflict = true;
      setSaveState("A newer server Draft exists. Reload before moving it to Trash.", "conflict");
      showToast("Draft changed elsewhere. Reload the server version before continuing.", "error");
    } else {
      setSaveState(error?.message || "Unable to delete image.", "error");
      showToast("Unable to delete image.", "error");
    }
  } finally {
    setWorkspaceControls();
  }
}

function throwIfTaskCanceled(task) {
  if (task.cancelRequested) {
    throw new DOMException("Upload canceled.", "AbortError");
  }
}

async function cleanupTaskIntent(task) {
  if (!task.intent?.upload_id) return null;
  if (task.cleanupPromise) return task.cleanupPromise;
  task.cleanupPromise = cancelWorkspaceUpload(task.intent.upload_id)
    .then((result) => {
      task.cleanupStatus = result.cleanup_status || "failed";
      return result;
    })
    .catch(() => {
      task.cleanupStatus = "failed";
      return null;
    })
    .finally(() => {
      task.cleanupPromise = null;
    });
  return task.cleanupPromise;
}

async function prepareUploadTask(task) {
  if (task.localRecord && task.uploadAssets) return;
  if (!WORKSPACE_IMAGE_MIME_TYPES.has(task.file?.type)) {
    throw new Error("Use a JPEG, PNG, or WebP image.");
  }
  const folder = folderById(task.folder_id);
  const { item } = await window.MTArchiveUpload.buildUploadedItem(task.file, task, task.attempt - 1);
  throwIfTaskCanceled(task);
  task.localRecord = normalizeRecord(
    {
      ...item,
      folder_id: folder.id,
      folder_name: folder.name,
      series: "",
      visibility: "draft",
      imageRecord: {
        ...(item.imageRecord || {}),
        folder_id: folder.id,
        folder_name: folder.name,
        series: "",
        visibility: "draft",
        visibility_manually_set: true,
      },
    },
    folder,
  );
  task.uploadAssets = phase2UploadAssets(task.localRecord);
}

async function processUploadTask(task) {
  if (task.inFlight || task.recordId || (task.cancelRequested && task.stage === "canceled")) return;
  task.attempt += 1;
  task.inFlight = true;
  task.cancelRequested = false;
  task.retryable = false;
  task.intent = null;
  task.cleanupStatus = null;
  task.abortController = new AbortController();
  task.update("queued", 2, task.attempt > 1 ? "Preparing retry." : "Waiting to start.");

  try {
    await prepareUploadTask(task);
    throwIfTaskCanceled(task);
    if (task.attempt > 1) {
      task.update("uploading", 80, "Reusing prepared image assets.");
    }
    task.update("uploading", 82, "Creating secure upload destinations.");
    task.intent = await createWorkspaceUploadIntent(task.localRecord, task.uploadAssets, task.abortController.signal);
    throwIfTaskCanceled(task);
    for (const [assetIndex, destination] of task.intent.assets.entries()) {
      const source = task.uploadAssets.find((asset) => asset.kind === destination.kind);
      task.update("uploading", 84 + assetIndex * 4, `Uploading ${destination.kind} asset.`);
      await uploadAssetToSignedUrl(destination, source, task.abortController.signal);
      throwIfTaskCanceled(task);
    }
    task.update("uploading", 97, "Verifying assets and creating the server Draft.");
    const record = await completeWorkspaceUpload(task.intent, task.localRecord, task.abortController.signal);
    task.recordId = record.id;
    taskByRecordId.set(record.id, task);
    records = [record, ...records.filter((existing) => existing.id !== record.id)];
    if (!draftDirty && !draftSaveInFlight && !draftConflict && !submissionPreparing && !submissionInFlight) {
      activeRecordId = record.id;
      resetDraftEditState("All changes saved.");
    }
    let cacheSaved = true;
    try {
      await putStoredItem(record);
    } catch (_error) {
      cacheSaved = false;
    }
    releaseTaskRuntime(task);
    task.inFlight = false;
    task.update("complete", 100, "Server Draft ready.");
    if (activeRecordId === record.id) refreshActiveReadiness();
    showToast(cacheSaved
      ? "Image uploaded as a private Draft."
      : "Image uploaded as a private Draft; offline cache is unavailable.");
  } catch (error) {
    if (task.intent?.upload_id) {
      await cleanupTaskIntent(task);
    }
    const canceled = task.cancelRequested || error?.name === "AbortError";
    const cleanupWarning = task.cleanupStatus === "failed"
      ? " Temporary object cleanup requires another attempt."
      : "";
    task.inFlight = false;
    task.retryable = true;
    task.stage = canceled ? "canceled" : "failed";
    task.progress = canceled ? Math.min(task.progress, 99) : 100;
    task.message = canceled
      ? `Upload canceled.${cleanupWarning}`
      : `${error?.message || "Upload failed."}${cleanupWarning}`;
    showToast(task.message, canceled ? "info" : "error");
    renderAll();
  } finally {
    task.abortController = null;
  }
}

async function cancelUploadTask(taskId) {
  const task = uploadTasks.find((item) => item.id === taskId);
  if (!task || task.cancelRequested || (!task.inFlight && task.stage !== "queued")) return;
  task.cancelRequested = true;
  if (!task.inFlight) {
    task.retryable = true;
    task.stage = "canceled";
    task.message = "Queued upload canceled before processing.";
    renderAll();
    return;
  }
  task.stage = "canceling";
  task.message = "Stopping upload and removing temporary objects.";
  task.abortController?.abort();
  renderAll();
  await cleanupTaskIntent(task);
  if (task.inFlight) {
    task.stage = "canceling";
    task.message = "Waiting for local image processing to stop.";
  }
  renderAll();
}

async function retryUploadTask(taskId) {
  const task = uploadTasks.find((item) => item.id === taskId);
  if (!task || task.inFlight || !["failed", "canceled"].includes(task.stage)) return;
  task.cancelRequested = false;
  await processUploadTask(task);
}

function dismissUploadTask(taskId) {
  const task = uploadTasks.find((item) => item.id === taskId);
  if (!task || task.inFlight || !["failed", "canceled"].includes(task.stage)) return;
  releaseTaskRuntime(task);
  uploadTasks = uploadTasks.filter((item) => item.id !== task.id);
  renderAll();
}

async function processTasksWithLimit(tasks, limit) {
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < tasks.length) {
      const task = tasks[nextIndex];
      nextIndex += 1;
      await processUploadTask(task);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, () => worker()));
}

async function handleFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean);
  if (!files.length) {
    return;
  }
  if (activeWorkspaceView !== "drafts" || !workspaceOnline || submissionPreparing || submissionInFlight) {
    showToast(workspaceOnline ? "Wait for the current submission to finish." : "Reconnect before importing images.", "error");
    return;
  }
  if (!window.MTArchiveUpload) {
    showToast("Upload module is not available.", "error");
    return;
  }
  if (!archiveDb) {
    archiveDb = await openArchiveDatabase();
  }
  const folder = activeFolder();
  const tasks = files.map((file, index) => createTask(file, index, folder));
  uploadTasks = [...tasks, ...uploadTasks];
  renderAll();
  await processTasksWithLimit(tasks, UPLOAD_CONCURRENCY);
}

async function selectRecord(recordId) {
  if (activeWorkspaceView !== "drafts" || submissionPreparing || submissionInFlight) return false;
  if (recordId === activeRecordId) return true;
  if (!(await flushDraftBeforeNavigation())) return false;
  activeRecordId = recordId;
  activeFolderId = records.find((record) => record.id === recordId)?.folder_id || activeFolderId;
  saveActiveFolder();
  resetDraftEditState("All changes saved.");
  renderAll();
  refreshActiveReadiness();
  return true;
}

async function loadExistingUploadRecords() {
  const result = await workspaceRequest(`${WORKSPACE_IMAGES_API}?workflow_status=draft`);
  records = (result.images || []).map(normalizeWorkspaceDraft);
  if (!archiveDb) archiveDb = await openArchiveDatabase();
  await Promise.all(records.map((record) => putStoredItem(record).catch(() => undefined)));
  if (!activeRecordId && recordsForActiveFolder()[0]) {
    activeRecordId = recordsForActiveFolder()[0].id;
  }
}

async function loadTrashRecords({ force = false } = {}) {
  if (!workspaceOnline || trashLoading || (trashLoaded && !force)) return;
  trashLoading = true;
  trashError = null;
  renderAll();
  try {
    const result = await workspaceRequest(`${WORKSPACE_IMAGES_API}?workflow_status=trashed`);
    trashedRecords = (result.images || []).map(normalizeWorkspaceDraft);
    trashLoaded = true;
  } catch (error) {
    trashError = error;
  } finally {
    trashLoading = false;
    renderAll();
  }
}

async function switchWorkspaceView(nextView) {
  const next = nextView === "trash" ? "trash" : "drafts";
  if (next === activeWorkspaceView) {
    if (next === "trash" && trashError) await loadTrashRecords({ force: true });
    return;
  }
  if (activeWorkspaceView === "drafts" && !(await flushDraftBeforeNavigation())) return;
  clearReadinessPoll();
  activeWorkspaceView = next;
  activeRecordId = next === "drafts" ? recordsForActiveFolder()[0]?.id || null : null;
  resetDraftEditState(activeRecordId ? "All changes saved." : "");
  saveActiveFolder();
  renderAll();
  if (next === "trash") {
    await loadTrashRecords();
  } else if (activeRecordId) {
    refreshActiveReadiness();
  }
}

async function restoreTrashedRecord(recordId) {
  if (!workspaceOnline || restoringTrashIds.has(recordId)) return;
  const record = trashedRecords.find((item) => item.id === recordId);
  if (!record) return;
  let restoredSuccessfully = false;
  restoringTrashIds.add(recordId);
  trashRestoreErrors.delete(recordId);
  renderAll();
  try {
    const restored = await restoreWorkspaceDraft(recordId);
    trashedRecords = trashedRecords.filter((item) => item.id !== recordId);
    records = [restored, ...records.filter((item) => item.id !== restored.id)];
    activeFolderId = restored.folder_id || activeFolderId;
    saveActiveFolder();
    if (!archiveDb) archiveDb = await openArchiveDatabase();
    await putStoredItem(restored).catch(() => undefined);
    showToast(`Draft restored to ${restored.folder_name || "Inbox"}.`, "success");
    restoredSuccessfully = true;
  } catch (error) {
    const message = error?.status === 403
      ? "Your account cannot restore this Draft."
      : error?.status === 409
        ? "This Draft changed elsewhere. Refresh Trash before retrying."
        : error?.status === 404
          ? "This Draft is no longer in Trash. Refresh the list."
          : error?.message || "The Draft could not be restored.";
    trashRestoreErrors.set(recordId, message);
    showToast(message, "error");
  } finally {
    restoringTrashIds.delete(recordId);
    renderAll();
    const focusTarget = restoredSuccessfully
      ? workspaceViewButtons.find((button) => button.dataset.studioView === "trash")
      : [...(queueElement?.querySelectorAll("[data-trash-restore]") || [])]
        .find((button) => button.dataset.trashRestore === recordId);
    focusTarget?.focus({ preventScroll: true });
  }
}

async function loadOfflineCache() {
  folders = defaultFolders();
  activeFolderId = folders[0].id;
  if (!archiveDb) archiveDb = await openArchiveDatabase();
  const stored = await getStoredItems();
  records = stored
    .filter((item) => item?.serverBacked || item?.imageRecord?.source_type === "upload" || item?.source === "Uploaded")
    .map((item) => normalizeRecord({ ...item, folder_id: activeFolderId, folder_name: folders[0].name }, folders[0]))
    .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
  activeRecordId = records[0]?.id || null;
}

folderForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!workspaceOnline || submissionPreparing || submissionInFlight) {
    showToast("Reconnect before creating folders.", "error");
    return;
  }
  const formData = new FormData(folderForm);
  const folderName = cleanText(formData.get("folder_name"));
  if (!folderName) {
    return;
  }
  const submit = folderForm.querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    const result = await createWorkspaceFolder(folderName);
    folders = [...folders, result.folder];
    activeFolderId = result.folder.id;
    saveActiveFolder();
    folderForm.reset();
    renderAll();
    showToast(`Folder created: ${result.folder.name}`);
  } catch (error) {
    showToast(error.message || "Unable to create folder.", "error");
  } finally {
    submit.disabled = false;
  }
});

workspaceViewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchWorkspaceView(button.dataset.studioView);
  });
});

folderList?.addEventListener("click", async (event) => {
  if (submissionPreparing || submissionInFlight) return;
  const renameButton = event.target.closest("[data-folder-rename]");
  if (renameButton) {
    const folder = folders.find((item) => item.id === renameButton.dataset.folderRename);
    const nextName = window.prompt("Rename folder", folder?.name || "");
    if (!folder || nextName === null || !cleanText(nextName) || cleanText(nextName) === folder.name) return;
    try {
      const result = await renameWorkspaceFolder(folder.id, cleanText(nextName));
      folders = folders.map((item) => (item.id === folder.id ? result.folder : item));
      records = records.map((record) => (record.folder_id === folder.id ? { ...record, folder_name: result.folder.name } : record));
      renderAll();
      showToast("Folder renamed.");
    } catch (error) {
      showToast(error.message || "Unable to rename folder.", "error");
    }
    return;
  }
  const deleteButton = event.target.closest("[data-folder-delete]");
  if (deleteButton) {
    if (!(await flushDraftBeforeNavigation())) return;
    const folder = folders.find((item) => item.id === deleteButton.dataset.folderDelete);
    const folderTasks = uploadTasks.filter((task) => task.folder_id === folder?.id && !task.recordId);
    if (folderTasks.length) {
      showToast("Finish or remove this folder's upload tasks before deleting it.", "error");
      return;
    }
    if (!folder || !window.confirm(`Delete "${folder.name}"? Images in this folder will move to Inbox.`)) return;
    try {
      await deleteWorkspaceFolder(folder.id);
      await loadFolders();
      await loadExistingUploadRecords();
      renderAll();
      if (activeRecordId) refreshActiveReadiness();
      showToast("Folder deleted. Its images are in Inbox.");
    } catch (error) {
      showToast(error.message || "Unable to delete folder.", "error");
    }
    return;
  }
  const button = event.target.closest("[data-folder-id]");
  if (!button) {
    return;
  }
  if (!(await flushDraftBeforeNavigation())) return;
  activeFolderId = button.dataset.folderId;
  saveActiveFolder();
  activeRecordId = recordsForActiveFolder()[0]?.id || null;
  resetDraftEditState(activeRecordId ? "All changes saved." : "");
  renderAll();
  if (activeRecordId) refreshActiveReadiness();
});

queueElement?.addEventListener("click", async (event) => {
  if (submissionPreparing || submissionInFlight) return;
  const trashRetryButton = event.target.closest("[data-trash-retry]");
  if (trashRetryButton) {
    await loadTrashRecords({ force: true });
    return;
  }
  const restoreButton = event.target.closest("[data-trash-restore]");
  if (restoreButton) {
    await restoreTrashedRecord(restoreButton.dataset.trashRestore);
    return;
  }
  const retryButton = event.target.closest("[data-task-retry]");
  if (retryButton) {
    await retryUploadTask(retryButton.dataset.taskRetry);
    return;
  }
  const cancelButton = event.target.closest("[data-task-cancel]");
  if (cancelButton) {
    await cancelUploadTask(cancelButton.dataset.taskCancel);
    return;
  }
  const dismissButton = event.target.closest("[data-task-dismiss]");
  if (dismissButton) {
    dismissUploadTask(dismissButton.dataset.taskDismiss);
    return;
  }
  const card = event.target.closest("[data-record-id]");
  if (!card) {
    return;
  }
  await selectRecord(card.dataset.recordId);
});

uploadInput?.addEventListener("change", async (event) => {
  await handleFiles(event.target.files);
  uploadInput.value = "";
});

dropzone?.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (activeWorkspaceView !== "drafts" || submissionPreparing || submissionInFlight || !workspaceOnline) return;
  dropzone.classList.add("is-dragging");
});

dropzone?.addEventListener("dragleave", () => {
  dropzone.classList.remove("is-dragging");
});

dropzone?.addEventListener("drop", async (event) => {
  event.preventDefault();
  dropzone.classList.remove("is-dragging");
  await handleFiles(event.dataTransfer?.files);
});

formElement?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveActiveRecord({ source: "manual" });
});

formElement?.addEventListener("input", markDraftDirty);

recognizablePeopleSelect?.addEventListener("change", syncComplianceFieldVisibility);

reloadRecordButton?.addEventListener("click", reloadActiveRecord);

readinessRefreshButton?.addEventListener("click", () => {
  refreshActiveReadiness();
});

submitRecordButton?.addEventListener("click", () => {
  submitActiveRecord();
});

submitDialog?.addEventListener("click", (event) => {
  if (event.target === submitDialog) submitDialog.close("cancel");
});

deleteRecordButton?.addEventListener("click", () => {
  deleteActiveRecord();
});

window.addEventListener("beforeunload", (event) => {
  if (draftDirty || draftSaveInFlight || submissionPreparing || submissionInFlight) {
    event.preventDefault();
    event.returnValue = "";
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") {
    clearReadinessPoll();
    return;
  }
  const record = records.find((item) => item.id === activeRecordId);
  if (record && readinessIsPending(record.readiness)) refreshActiveReadiness({ silent: true });
});

window.addEventListener("pagehide", (event) => {
  if (event.persisted) return;
  clearReadinessPoll();
  objectUrls.forEach((url) => URL.revokeObjectURL(url));
});

async function initUploadStudio() {
  if (copyrightYearInput) {
    copyrightYearInput.max = String(new Date().getFullYear() + 1);
  }
  workspaceLoading = true;
  renderAll();
  try {
    workspaceOnline = true;
    await loadFolders();
    await loadExistingUploadRecords();
    if (activeWorkspaceView === "trash") {
      activeRecordId = null;
      await loadTrashRecords();
    }
    setGlobalStatus("Ready");
    resetDraftEditState(activeRecordId ? "All changes saved." : "");
  } catch (error) {
    workspaceOnline = false;
    activeWorkspaceView = "drafts";
    await loadOfflineCache().catch(() => {
      folders = defaultFolders();
      records = [];
      activeRecordId = null;
    });
    setGlobalStatus("Offline read-only");
    saveActiveFolder();
    showToast(error?.message || "Workspace unavailable. Showing a read-only local cache.", "error");
  }
  workspaceLoading = false;
  renderAll();
  if (workspaceOnline && activeRecordId) refreshActiveReadiness();
}

initUploadStudio();
