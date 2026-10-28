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
    const error = new Error(result.error?.message || result.error || "操作没有完成，请重试。");
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
const primaryImport = document.querySelector('label[for="upload-studio-input"]');
const quickUploadOpen = document.querySelector("[data-quick-upload-open]");
const quickUploadInput = document.querySelector("[data-quick-upload-input]");
const quickUploadDialog = document.querySelector("[data-quick-upload-dialog]");
const quickUploadForm = document.querySelector("[data-quick-upload-form]");
const quickUploadCancel = document.querySelector("[data-quick-upload-cancel]");
const quickRecognizablePeople = document.querySelector("[data-quick-recognizable-people]");
const quickModelReleaseField = document.querySelector("[data-quick-model-release]");
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
const submitDialogDescription = document.querySelector("[data-studio-submit-dialog-description]");
const submitDialogConfirm = document.querySelector("[data-studio-submit-dialog-confirm]");
const submitDialogLabel = document.querySelector("[data-studio-submit-dialog-label]");
const submitReadyButton = document.querySelector("[data-studio-submit-ready]");
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
let pendingQuickUploadDefaults = null;
let rememberedQuickUploadDefaults = null;
let bulkSubmissionInFlight = false;

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
    label: "作品信息",
    message: "需要填写标题，并选择系列。",
  },
  {
    code: "rights_disclosures",
    label: "版权声明",
    message: "需要完成版权声明。",
  },
  {
    code: "image_assets",
    label: "图片文件",
    message: "需要原图、展示图和缩略图。",
  },
  {
    code: "security_scan",
    label: "安全扫描",
    message: "所有图片文件都要通过安全扫描。",
  },
  {
    code: "submission_state",
    label: "发布状态",
    message: "这张图片必须还是可编辑的草稿。",
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
  if (Number.isNaN(date.getTime())) return "刚刚移入";
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

function hydrateQuickUploadForm() {
  if (!quickUploadForm) return;
  const stored = rememberedQuickUploadDefaults || {};
  const elements = quickUploadForm.elements;
  elements.namedItem("copyright_holder").value = cleanText(stored.copyright_holder) || staffCopyrightHolder();
  elements.namedItem("copyright_year").value = String(stored.copyright_year || new Date().getFullYear());
  elements.namedItem("content_category").value = ["concrete", "abstract"].includes(stored.content_category)
    ? stored.content_category
    : "auto";
  elements.namedItem("alt_text_template").value = cleanText(stored.alt_text_template) || "Photograph titled “{title}”.";
  elements.namedItem("tags").value = uniqueTextList(stored.tags || []).join(", ");
  elements.namedItem("location_name").value = cleanText(stored.location_name);
  elements.namedItem("contains_recognizable_people").value = "false";
  elements.namedItem("model_release_status").value = cleanText(stored.model_release_status) || "available";
  elements.namedItem("property_release_status").value = cleanText(stored.property_release_status) || "not_applicable";
  elements.namedItem("ai_disclosure").value = cleanText(stored.ai_disclosure) || "none";
  elements.namedItem("sensitive_content_disclosure").value = cleanText(stored.sensitive_content_disclosure) || "none";
  elements.namedItem("rights_declared").checked = false;
  syncQuickModelReleaseVisibility();
}

function quickUploadDefaultsFromForm() {
  const formData = new FormData(quickUploadForm);
  const containsRecognizablePeople = formData.get("contains_recognizable_people") === "true";
  return {
    copyright_holder: cleanText(formData.get("copyright_holder")),
    copyright_year: Number.parseInt(formData.get("copyright_year"), 10),
    content_category: cleanText(formData.get("content_category")) || "auto",
    alt_text_template: cleanText(formData.get("alt_text_template")),
    tags: splitTags(formData.get("tags")),
    location_name: cleanText(formData.get("location_name")),
    contains_recognizable_people: containsRecognizablePeople,
    model_release_status: containsRecognizablePeople
      ? cleanText(formData.get("model_release_status")) || null
      : "not_applicable",
    property_release_status: cleanText(formData.get("property_release_status")) || null,
    rights_declared: formData.get("rights_declared") === "on",
    ai_disclosure: cleanText(formData.get("ai_disclosure")) || null,
    sensitive_content_disclosure: cleanText(formData.get("sensitive_content_disclosure")) || null,
  };
}

function syncQuickModelReleaseVisibility() {
  if (!quickRecognizablePeople || !quickModelReleaseField) return;
  quickModelReleaseField.hidden = quickRecognizablePeople.value !== "true";
  const select = quickModelReleaseField.querySelector("select");
  if (select) select.required = quickRecognizablePeople.value === "true";
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
  // `tags` holds the generated display groups (type, ratio, mood...). Only fall
  // back to it for legacy records without photographer tags; otherwise those
  // generated labels would be saved and published as the photographer's tags.
  const customTags = uniqueTextList(
    Array.isArray(item.customTags) ? item.customTags : (Array.isArray(item.tags) ? item.tags : []),
  );
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

function applyQuickUploadDefaults(record, defaults) {
  if (!defaults) return record;
  const folder = folderById(record.folder_id);
  const title = cleanText(record.title) || "Untitled Work";
  const altText = cleanText(defaults.alt_text_template).replaceAll("{title}", title);
  const contentCategory = ["concrete", "abstract"].includes(defaults.content_category)
    ? defaults.content_category
    : contentTypeCode(record.imageRecord?.content_type || record.type);
  return normalizeRecord({
    ...record,
    type: contentCategory,
    imageRecord: {
      ...(record.imageRecord || {}),
      content_type: contentCategory,
      display_mode: displayModeForType(contentCategory),
    },
    alt_text: altText,
    location_name: cleanText(defaults.location_name) || record.location_name || "",
    copyright_holder: defaults.copyright_holder,
    copyright_year: defaults.copyright_year,
    contains_recognizable_people: defaults.contains_recognizable_people,
    model_release_status: defaults.model_release_status,
    property_release_status: defaults.property_release_status,
    rights_declared: defaults.rights_declared === true,
    ai_disclosure: defaults.ai_disclosure,
    sensitive_content_disclosure: defaults.sensitive_content_disclosure,
    customTags: uniqueTextList([...(record.customTags || []), ...(defaults.tags || [])]),
  }, folder);
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
    tags: uniqueTextList(record.customTags || []).slice(0, 30),
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

// The site owner publishes their own work directly: the submitted version goes
// straight through the audited Super Admin self-publish action. The ten review
// checks are the owner's own declaration, confirmed in the publish dialog.
const SELF_PUBLISH_CHECKLIST = Object.freeze(Object.fromEntries([
  "file_integrity", "rights", "privacy", "minors", "sensitive_content",
  "hate_illegal", "property_release", "third_party_ip", "ai_disclosure", "public_metadata",
].map((code) => [code, true])));

async function selfPublishSubmission(submissionId) {
  const submissionPath = `/api/admin/review-submissions/${encodeURIComponent(submissionId)}`;
  const detail = await workspaceRequest(submissionPath);
  return workspaceRequest(`${submissionPath}/super-admin-self-publish`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      confirmation: "review-super-admin-self-publish",
      expected_version: detail?.submission?.lock_version,
      idempotency_key: crypto.randomUUID(),
      reason_codes: ["policy_complete"],
      user_message: "Published by the photographer from the staff upload page.",
      internal_note: "",
      checklist_result: { ...SELF_PUBLISH_CHECKLIST },
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

function showToast(message, state = "info", link = null) {
  if (!toastElement) {
    return;
  }
  clearTimeout(toastTimer);
  toastElement.textContent = message;
  if (link?.href) {
    const anchor = document.createElement("a");
    anchor.className = "upload-studio-toast-link";
    anchor.href = link.href;
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.textContent = link.label;
    toastElement.append(" ", anchor);
  }
  toastElement.dataset.state = state;
  toastElement.hidden = false;
  toastTimer = window.setTimeout(() => {
    toastElement.hidden = true;
  }, link?.href ? 9000 : 3600);
}

function publicWorkLink(imageId) {
  return { href: `/work.html?id=${encodeURIComponent(imageId)}`, label: "在网站中查看" };
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
  if (!workspaceOnline) return "离线时无法检查。";
  if (!readiness || readiness.status === "checking") return "正在检查发布条件…";
  if (readiness.status === "submitting") return "正在发布…";
  if (readiness.status === "stale") return "保存最新修改后会重新检查。";
  if (readiness.status === "error") return readiness.message || "检查失败，请重试。";
  if (readiness.status === "submitted") return "这个版本已经提交。";
  if (readiness.ready) return "可以发布。";
  if (readinessIsPending(readiness)) return "自动检查还在进行中。";
  const blockers = Number.isInteger(readiness.blocker_count) ? readiness.blocker_count : 0;
  return blockers === 1 ? "有 1 项需要处理。" : `有 ${blockers || "几"} 项需要处理。`;
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
      setSaveState("这张草稿刚在别处被修改过，请先重新读取。", "conflict");
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
      message: error?.message || "检查失败，请重试。",
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
    queued: "排队中",
    reading: "读取中",
    compressing: "压缩中",
    slicing: "生成展示图",
    analyzing: "分析中",
    uploading: "上传中",
    canceling: "正在取消",
    canceled: "已取消",
    complete: "已就绪",
    warning: "离线缓存",
    failed: "失败",
  };
  return labels[stage] || "处理中";
}

// Upload → security scan → display images → publishable (design/admin-mockups-v4).
const UPLOAD_STEP_LABELS = ["上传", "安全扫描", "生成展示图", "可发布"];

function uploadStepsHtml(index, { failed = false, done = false } = {}) {
  const items = UPLOAD_STEP_LABELS.map((label, step) => {
    let state = "";
    if (step < index || (step === index && done)) state = "done";
    else if (step === index) state = failed ? "failed" : "current";
    return `<li${state ? ` data-state="${state}"` : ""}>${label}</li>`;
  }).join("");
  return `<ol class="admin-steps" aria-label="进度：${UPLOAD_STEP_LABELS[index]}${failed ? "失败" : ""}">${items}</ol>`;
}

function taskStepIndex(stage) {
  if (stage === "uploading") return 0;
  if (["compressing", "slicing", "analyzing"].includes(stage)) return 2;
  if (stage === "complete") return 1;
  return 0;
}

function recordStepsHtml(record) {
  const processing = record.processing_status;
  if (processing === "failed" || processing === "canceled") return uploadStepsHtml(1, { failed: true });
  if (!record.serverBacked || processing === "pending" || processing === "uploading") return uploadStepsHtml(0);
  if (processing === "processing") return uploadStepsHtml(1);
  return uploadStepsHtml(3, { done: record.publication_status === "published" });
}

function createTask(file, index, folder, quickDefaults = null) {
  const task = {
    id: crypto.randomUUID ? `studio-task-${crypto.randomUUID()}` : `studio-task-${Date.now()}-${index}`,
    name: file.name || `Image ${index + 1}`,
    file,
    folder_id: folder.id,
    folder_name: folder.name,
    quickDefaults,
    stage: "queued",
    progress: 0,
    message: "等待开始。",
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
    if (folderSummary) folderSummary.textContent = "正在读取文件夹";
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
  if (folderPanelTitle) folderPanelTitle.textContent = showingTrash ? "回收站" : "文件夹";
  if (folderForm) folderForm.hidden = showingTrash;
  if (folderList) folderList.hidden = showingTrash;
  if (showingTrash) {
    if (folderSummary) {
      folderSummary.textContent = trashLoading
        ? "正在读取"
        : trashError
          ? "暂不可用"
          : `${trashedRecords.length} 张`;
    }
  } else if (folderSummary) {
    folderSummary.textContent = `${folders.length} 个文件夹`;
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
                <button type="button" data-folder-rename="${escapeHtml(folder.id)}" aria-label="Rename ${escapeHtml(folder.name)}" data-tooltip="重命名文件夹">
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
        <h2>${permissionError ? "无法打开回收站" : "回收站读取失败"}</h2>
        <p>${escapeHtml(permissionError ? "你的账号不能查看或恢复这些草稿。" : trashError.message || "请重新打开回收站。")}</p>
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
    if (statusElement) statusElement.textContent = "读取中";
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
      ? "离线"
      : workingCount
        ? `${workingCount} 张处理中`
        : failedCount
          ? `${failedCount} 张失败`
          : canceledCount
            ? `${canceledCount} 张已取消`
            : "就绪";
  }
  if (!queueElement) {
    return;
  }
  if (!itemCount) {
    queueElement.innerHTML = `
      <article class="upload-studio-empty">
        <svg class="ui-icon" aria-hidden="true" focusable="false"><use href="#icon-image"></use></svg>
        <h2>「${escapeHtml(activeFolder().name)}」里还没有图片</h2>
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
        <button type="button" data-task-retry="${escapeHtml(task.id)}" aria-label="重试 ${escapeHtml(task.name)}" data-tooltip="重试">
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-retry"></use></svg>
        </button>` : "",
      canCancel ? `
        <button type="button" data-task-cancel="${escapeHtml(task.id)}" aria-label="取消 ${escapeHtml(task.name)}" data-tooltip="取消上传">
          <svg class="ui-icon" aria-hidden="true"><use href="#icon-x"></use></svg>
        </button>` : "",
      canDismiss ? `
        <button type="button" data-task-dismiss="${escapeHtml(task.id)}" aria-label="移除 ${escapeHtml(task.name)}" data-tooltip="从列表移除">
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
            <small>${task.attempt > 1 ? `第 ${task.attempt} 次尝试` : ""}</small>
          </span>
          <span class="upload-studio-card-state" data-state="${escapeHtml(task.stage)}">${escapeHtml(taskLabel(task.stage))}</span>
        </div>
        ${uploadStepsHtml(taskStepIndex(task.stage), { failed: task.stage === "failed" })}
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
            <img src="${escapeHtml(thumbnailUrl(record))}" alt="${escapeHtml(record.title || "图片预览")}" loading="lazy" decoding="async" />
            <span class="upload-studio-card-copy">
              <strong>${escapeHtml(record.title || "未命名作品")}</strong>
              <small>${contentTypeCode(record.imageRecord?.content_type || record.type) === "abstract" ? "此间留灰" : "此间留彩"} · ${escapeHtml(record.ratio || "1:1")}</small>
              <small>原图 ${escapeHtml(formatBytes(original?.byte_size))} · 展示图 ${escapeHtml(formatBytes(display?.byte_size || original?.byte_size))}</small>
            </span>
            <span class="upload-studio-card-state" data-state="${escapeHtml(stage)}">${escapeHtml(record.publication_status === "published" ? "已发布" : taskLabel(stage))}</span>
          </button>
          ${recordStepsHtml(record)}
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
    previewImage.alt = record.title || "图片预览";
  }
  // The exhibition display preview (studio-exhibition.js) follows the Draft.
  document.dispatchEvent(new CustomEvent("mt:studio-record", {
    detail: { id: record.id, src: displayUrl(record), width: record.width, height: record.height },
  }));
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
      ["原图", `${record.width} × ${record.height} · ${formatBytes(original?.byte_size)}`],
      ["展示图", display ? `${display.width} × ${display.height} · ${formatBytes(display.byte_size)}` : "使用原图"],
      ["缩略图", thumbnail ? `${thumbnail.width} × ${thumbnail.height} · ${formatBytes(thumbnail.byte_size)}` : "未生成"],
      ["状态", record.publication_status === "published" ? "已发布" : "草稿"],
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
  if (quickUploadInput) quickUploadInput.disabled = importDisabled;
  if (primaryImport) primaryImport.setAttribute("aria-disabled", String(importDisabled));
  if (quickUploadOpen) quickUploadOpen.disabled = importDisabled;
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
      ? (record?.readiness?.status === "submitting" ? "正在发布…" : "正在检查…")
      : "发布到网站";
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
  if (submitReadyButton) {
    submitReadyButton.disabled = importDisabled || !recordsForActiveFolder().length;
    submitReadyButton.textContent = bulkSubmissionInFlight
      ? (submissionInFlight ? "正在发布…" : "正在检查…")
      : "检查并发布";
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
  return normalizeRecord(staffUploadDefaults(next), folder);
}

// Staff only edit title, series, introduction and tags. The other readiness
// fields describe the owner's own photography, so they are filled with the
// declaration stated on the form ("Uploading confirms you own the rights").
function staffCopyrightHolder() {
  return cleanText(window.MTPresenceHeaderIdentity?.display_name) || "MT Presence";
}

function staffUploadDefaults(record) {
  const title = cleanText(record.title);
  return {
    ...record,
    alt_text: cleanText(record.alt_text) || (title ? `Photograph titled “${title}”.` : ""),
    copyright_holder: cleanText(record.copyright_holder) || staffCopyrightHolder(),
    copyright_year: Number.isInteger(record.copyright_year) ? record.copyright_year : new Date().getFullYear(),
    contains_recognizable_people: record.contains_recognizable_people ?? false,
    model_release_status: record.model_release_status || "not_applicable",
    property_release_status: record.property_release_status || "not_applicable",
    rights_declared: true,
    ai_disclosure: record.ai_disclosure || "none",
    sensitive_content_disclosure: record.sensitive_content_disclosure || "none",
  };
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
    setSaveState("这张草稿刚在别处被修改过，请先重新读取。", "conflict");
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
  setSaveState("有未保存的修改，正在自动保存…", "dirty");
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
    setSaveState("离线缓存只能查看，请联网后再保存。", "warning");
    return false;
  }
  if (!draftDirty) {
    setSaveState("已保存。", "saved");
    return true;
  }
  const valid = source === "manual" ? formElement.reportValidity() : formElement.checkValidity();
  if (!valid) {
    setSaveState("请先修正标红的内容再保存。", "error");
    return false;
  }
  const savingRecordId = record.id;
  const savingRevision = draftEditRevision;
  const nextRecord = recordFromForm(record);
  let refreshReadinessAfterSave = false;
  draftSaveInFlight = true;
  setSaveState(source === "autosave" ? "正在保存…" : "正在保存草稿…", "saving");
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
        ? (source === "autosave" ? "已自动保存。" : "已保存。")
        : "已保存到服务器（本地缓存不可用）。";
      setSaveState(successMessage, cacheSaved ? "saved" : "warning");
      if (source === "manual") showToast("草稿已保存。");
    } else {
      draftDirty = true;
      pendingAutosave = true;
      setSaveState("有未保存的修改，正在自动保存…", "dirty");
    }
    return true;
  } catch (error) {
    draftDirty = true;
    if (error?.code === "DRAFT_VERSION_CONFLICT") {
      clearAutosaveTimer();
      pendingAutosave = false;
      draftConflict = true;
      setSaveState("这张草稿刚在别处被修改过，请先重新读取。", "conflict");
      showToast("这张草稿刚在别处被修改过，请先重新读取。", "error");
    } else {
      setSaveState(error?.message || "保存失败，修改仍保留在表单里。", "error");
      showToast("保存失败，修改仍保留在表单里。", "error");
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
  setSaveState("正在重新读取草稿…", "saving");
  setWorkspaceControls();
  try {
    await loadExistingUploadRecords();
    if (!records.some((record) => record.id === recordId)) {
      throw new Error("This Draft is no longer available.");
    }
    activeRecordId = recordId;
    activeFolderId = records.find((record) => record.id === recordId).folder_id;
    saveActiveFolder();
    resetDraftEditState("已重新读取草稿。");
    renderAll();
    refreshActiveReadiness();
  } catch (error) {
    setSaveState(error?.message || "重新读取失败。", "error");
    showToast("重新读取失败。", "error");
  }
}

function confirmSubmission({ title, message, confirmLabel }) {
  if (!submitDialog || typeof submitDialog.showModal !== "function") {
    return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  }
  if (submitDialogTitle) submitDialogTitle.textContent = title;
  if (submitDialogDescription) submitDialogDescription.textContent = message;
  if (submitDialogLabel) submitDialogLabel.textContent = confirmLabel;
  submitDialog.returnValue = "";
  submitDialog.showModal();
  return new Promise((resolve) => {
    submitDialog.addEventListener("close", () => resolve(submitDialog.returnValue === "confirm"), { once: true });
  });
}

function confirmDraftSubmission(record) {
  const title = record?.title || "Untitled Work";
  return confirmSubmission({
    title: `Publish "${title}"?`,
    message: "已保存的版本会立即出现在网站上。发布即表示你拥有这张照片的版权，并且它适合公开展示。",
    confirmLabel: "发布到网站",
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
      showToast("请先保存最新修改再发布。", "error");
      return false;
    }
    submissionInFlight = true;
    clearReadinessPoll();
    setWorkspaceControls();
    const readiness = await refreshActiveReadiness({ allowWhileSubmitting: true });
    const currentRecord = records.find((item) => item.id === recordId);
    if (!currentRecord || !readiness?.ready || readiness.status !== "ready" || draftConflict) {
      showToast(readiness?.message || "这张草稿还不能发布。", "error");
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
    let publishError = null;
    try {
      await selfPublishSubmission(result.submission.id);
    } catch (error) {
      // The work stays safely submitted; it simply is not public yet.
      publishError = error;
    }
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
    resetDraftEditState(activeRecordId ? "已保存。" : "");
    if (publishError) {
      const reason = publishError.code === "REVIEW_SELF_PUBLISH_FORBIDDEN"
        ? "发布需要超级管理员账号。"
        : publishError.message || "发布失败。";
      showToast(`已保存并提交，但还没公开：${reason}`, "error");
      return true;
    }
    showToast(cacheDeleted
      ? "已发布到网站。"
      : "已发布到网站。", "info", publicWorkLink(recordId));
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
      setSaveState("这张草稿刚在别处被修改过，请先重新读取。", "conflict");
      showToast("这张草稿刚在别处被修改过，请先重新读取。", "error");
    } else {
      const record = records.find((item) => item.id === recordId);
      const currentReadiness = record?.readiness;
      replaceRecordReadiness(recordId, {
        ...(currentReadiness || {}),
        image_id: recordId,
        status: error?.readiness ? currentReadiness?.status || "blocked" : "error",
        ready: false,
        message: error?.message || "发布失败，请重试。",
        checks: currentReadiness?.checks || READINESS_CHECK_DEFAULTS.map((check) => ({ ...check, state: "blocked" })),
      });
      showToast(error?.message || "发布失败，草稿仍然保留。", "error");
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

async function mapWithConcurrency(items, limit, operation) {
  const results = new Array(items.length);
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await operation(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

async function removeSubmittedWorkspaceRecord(record) {
  let cacheDeleted = true;
  try {
    await deleteStoredItem(record.id);
  } catch (_error) {
    cacheDeleted = false;
  }
  (record.assets || []).forEach((asset) => {
    if (!asset.objectUrl) return;
    URL.revokeObjectURL(asset.objectUrl);
    objectUrls.delete(asset.objectUrl);
  });
  const completedTask = taskByRecordId.get(record.id);
  taskByRecordId.delete(record.id);
  uploadTasks = uploadTasks.filter((task) => task !== completedTask);
  records = records.filter((item) => item.id !== record.id);
  return cacheDeleted;
}

async function submitReadyRecordsInFolder() {
  if (
    bulkSubmissionInFlight
    || submissionPreparing
    || submissionInFlight
    || !workspaceOnline
    || activeWorkspaceView !== "drafts"
  ) return;
  if (!(await flushDraftBeforeNavigation())) {
    showToast("请先保存当前草稿再批量发布。", "error");
    return;
  }
  const folder = activeFolder();
  const candidates = [...recordsForActiveFolder()];
  if (!candidates.length) {
    showToast(`「${folder.name}」里没有草稿。`, "error");
    return;
  }

  bulkSubmissionInFlight = true;
  submissionPreparing = true;
  setWorkspaceControls();
  try {
    const readinessResults = await mapWithConcurrency(candidates, 4, async (record) => {
      try {
        const readiness = normalizeReadiness(await getWorkspaceDraftReadiness(record.id), record);
        replaceRecordReadiness(record.id, readiness);
        return { record, readiness, error: null };
      } catch (error) {
        return { record, readiness: null, error };
      }
    });
    renderAll();
    const ready = readinessResults
      .filter((result) => result.readiness?.ready === true && result.readiness.status === "ready")
      .map((result) => records.find((record) => record.id === result.record.id) || result.record);
    const checkingFailed = readinessResults.filter((result) => result.error).length;
    if (!ready.length) {
      const pending = readinessResults.length - checkingFailed;
      showToast(
        checkingFailed
          ? `没有可以发布的草稿，其中 ${checkingFailed} 张检查失败。`
          : `${pending} 张草稿还在等待填写信息或安全扫描。`,
        "error",
      );
      return;
    }

    const confirmed = await confirmSubmission({
      title: `发布 ${ready.length} 张已就绪的草稿？`,
      message: `只发布「${folder.name}」里已通过检查的草稿，其余的留在这里。发布即表示你拥有这些照片的版权，并且它们适合公开展示。`,
      confirmLabel: `发布 ${ready.length} 张`,
    });
    if (!confirmed) return;

    submissionInFlight = true;
    setWorkspaceControls();
    const submittedResults = await mapWithConcurrency(ready, 2, async (record) => {
      const idempotencyKey = createSubmissionIdempotencyKey(record.id);
      try {
        const result = await submitWorkspaceDraft(record, idempotencyKey);
        submissionIdempotencyKeys.delete(record.id);
        let publishError = null;
        try {
          await selfPublishSubmission(result.submission.id);
        } catch (error) {
          publishError = error;
        }
        const cacheDeleted = await removeSubmittedWorkspaceRecord(record);
        return { record, result, cacheDeleted, publishError, error: null };
      } catch (error) {
        if (error?.status && error.status < 500) submissionIdempotencyKeys.delete(record.id);
        if (error?.readiness) replaceRecordReadiness(record.id, normalizeReadiness(error.readiness, record));
        return { record, result: null, cacheDeleted: true, error };
      }
    });
    const submitted = submittedResults.filter((result) => !result.error);
    const published = submitted.filter((result) => !result.publishError).length;
    const notPublic = submitted.length - published;
    const failed = submittedResults.length - submitted.length;
    const cacheWarnings = submitted.filter((result) => !result.cacheDeleted).length;
    activeRecordId = recordsForActiveFolder()[0]?.id || null;
    resetDraftEditState(activeRecordId ? "已保存。" : "");
    const problems = [
      notPublic ? `${notPublic} 张已提交但还没公开` : "",
      failed ? `${failed} 张留在草稿里需要处理` : "",
    ].filter(Boolean);
    showToast(
      problems.length
        ? `已发布 ${published} 张；${problems.join("；")}。`
        : cacheWarnings
          ? `已发布 ${published} 张。`
          : `已发布 ${published} 张到网站。`,
      problems.length ? "error" : "info",
      published ? { href: "/works.html", label: "作品管理" } : null,
    );
  } finally {
    bulkSubmissionInFlight = false;
    submissionPreparing = false;
    submissionInFlight = false;
    renderAll();
    if (activeRecordId) refreshActiveReadiness({ silent: true });
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
    showToast("离线缓存只能查看。", "error");
    return;
  }
  if (!(await flushDraftBeforeNavigation())) return;
  if (activeRecordId !== recordId) return;
  record = records.find((item) => item.id === recordId);
  if (!record) return;
  const confirmed = window.confirm(`把《${record.title || "未命名作品"}》移到回收站？`);
  if (!confirmed) {
    return;
  }
  setSaveState("正在删除…", "saving");
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
    resetDraftEditState(cacheDeleted ? "已移到回收站。" : "已移到回收站。");
    showToast(cacheDeleted ? "已移到回收站。" : "已移到回收站。");
    renderAll();
    if (activeRecordId) refreshActiveReadiness();
  } catch (error) {
    if (error?.code === "DRAFT_VERSION_CONFLICT") {
      draftConflict = true;
      setSaveState("这张草稿刚在别处被修改过，请先重新读取。", "conflict");
      showToast("这张草稿刚在别处被修改过，请先重新读取。", "error");
    } else {
      setSaveState(error?.message || "删除失败。", "error");
      showToast("删除失败。", "error");
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
  task.localRecord = applyQuickUploadDefaults(task.localRecord, task.quickDefaults);
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
  task.update("queued", 2, task.attempt > 1 ? "准备重试。" : "等待开始。");

  try {
    await prepareUploadTask(task);
    throwIfTaskCanceled(task);
    if (task.attempt > 1) {
      task.update("uploading", 80, "使用已生成的图片文件。");
    }
    task.update("uploading", 82, "正在准备上传。");
    task.intent = await createWorkspaceUploadIntent(task.localRecord, task.uploadAssets, task.abortController.signal);
    throwIfTaskCanceled(task);
    for (const [assetIndex, destination] of task.intent.assets.entries()) {
      const source = task.uploadAssets.find((asset) => asset.kind === destination.kind);
      task.update("uploading", 84 + assetIndex * 4, `Uploading ${destination.kind} asset.`);
      await uploadAssetToSignedUrl(destination, source, task.abortController.signal);
      throwIfTaskCanceled(task);
    }
    task.update("uploading", 97, "正在校验文件并创建草稿。");
    let record = await completeWorkspaceUpload(task.intent, task.localRecord, task.abortController.signal);
    task.intent = null;
    let quickDefaultsApplied = false;
    if (task.quickDefaults) {
      task.update("uploading", 99, "正在应用共用设置。");
      try {
        record = await saveWorkspaceDraft(applyQuickUploadDefaults(record, task.quickDefaults));
        quickDefaultsApplied = true;
      } catch (error) {
        task.message = error?.message || "共用设置没有保存，草稿仍可编辑。";
      }
    }
    task.recordId = record.id;
    taskByRecordId.set(record.id, task);
    records = [record, ...records.filter((existing) => existing.id !== record.id)];
    if (!draftDirty && !draftSaveInFlight && !draftConflict && !submissionPreparing && !submissionInFlight) {
      activeRecordId = record.id;
      resetDraftEditState("已保存。");
    }
    let cacheSaved = true;
    try {
      await putStoredItem(record);
    } catch (_error) {
      cacheSaved = false;
    }
    releaseTaskRuntime(task);
    task.inFlight = false;
    task.update(
      "complete",
      100,
      quickDefaultsApplied
        ? "草稿已创建，安全扫描进行中。"
        : task.quickDefaults
          ? "草稿已创建，发布前请检查共用设置。"
          : "草稿已创建。",
    );
    if (activeRecordId === record.id) refreshActiveReadiness();
    showToast(
      task.quickDefaults && !quickDefaultsApplied
        ? "图片已存为草稿，共用设置需要检查。"
        : cacheSaved
          ? "图片已上传为草稿。"
          : "图片已上传为草稿。",
      task.quickDefaults && !quickDefaultsApplied ? "error" : "info",
    );
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
      : `${error?.message || "上传失败。"}${cleanupWarning}`;
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
    task.message = "已取消。";
    renderAll();
    return;
  }
  task.stage = "canceling";
  task.message = "正在停止上传并清理临时文件。";
  task.abortController?.abort();
  renderAll();
  await cleanupTaskIntent(task);
  if (task.inFlight) {
    task.stage = "canceling";
    task.message = "等待本地处理停止。";
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

function uploadDuplicateKey(name, size) {
  return `${String(name || "").trim().toLowerCase()}|${Number(size) || 0}`;
}

// Same filename and byte size as a Draft or an active upload is almost always
// the same photograph picked twice.
function duplicateUploadFiles(files) {
  const known = new Set();
  records.forEach((record) => {
    const original = (record.assets || []).find((asset) => asset.kind === "original");
    const name = record.imageRecord?.original_filename || record.original_filename;
    if (name && original?.byte_size) known.add(uploadDuplicateKey(name, original.byte_size));
  });
  uploadTasks.forEach((task) => {
    if (task.file && task.stage !== "failed" && task.stage !== "canceled") {
      known.add(uploadDuplicateKey(task.file.name, task.file.size));
    }
  });
  return files.filter((file) => known.has(uploadDuplicateKey(file.name, file.size)));
}

function confirmDuplicateUploads(files) {
  const duplicates = duplicateUploadFiles(files);
  if (!duplicates.length) return files;
  const names = duplicates.slice(0, 3).map((file) => file.name).join(", ");
  const more = duplicates.length > 3 ? ` and ${duplicates.length - 3} more` : "";
  const uploadAgain = window.confirm(
    `${names}${more} ${duplicates.length === 1 ? "is" : "are"} already in your Drafts or uploading.\n\n`
      + "OK uploads again. Cancel skips the duplicates.",
  );
  return uploadAgain ? files : files.filter((file) => !duplicates.includes(file));
}

async function handleFiles(fileList, { quickDefaults = null } = {}) {
  const chosenFiles = Array.from(fileList || []).filter(Boolean);
  if (!chosenFiles.length) {
    return;
  }
  if (activeWorkspaceView !== "drafts" || !workspaceOnline || submissionPreparing || submissionInFlight) {
    showToast(workspaceOnline ? "请等当前发布完成。" : "请联网后再上传。", "error");
    return;
  }
  if (!window.MTArchiveUpload) {
    showToast("上传组件不可用，请刷新页面。", "error");
    return;
  }
  const files = confirmDuplicateUploads(chosenFiles);
  if (!files.length) {
    showToast("已跳过草稿中已有的照片。");
    return;
  }
  if (!archiveDb) {
    archiveDb = await openArchiveDatabase();
  }
  const folder = activeFolder();
  const tasks = files.map((file, index) => createTask(file, index, folder, quickDefaults));
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
  resetDraftEditState("已保存。");
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
  resetDraftEditState(activeRecordId ? "已保存。" : "");
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
    showToast(`草稿已恢复到「${restored.folder_name || "Inbox"}」。`, "success");
    restoredSuccessfully = true;
  } catch (error) {
    const message = error?.status === 403
      ? "你的账号不能恢复这张草稿。"
      : error?.status === 409
        ? "这张草稿刚在别处被修改过，请刷新回收站后重试。"
        : error?.status === 404
          ? "这张草稿已不在回收站，请刷新列表。"
          : error?.message || "恢复失败。";
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
    showToast("请联网后再新建文件夹。", "error");
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
    showToast(`已新建文件夹「${result.folder.name}」`);
  } catch (error) {
    showToast(error.message || "新建文件夹失败。", "error");
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
    const nextName = window.prompt("重命名文件夹", folder?.name || "");
    if (!folder || nextName === null || !cleanText(nextName) || cleanText(nextName) === folder.name) return;
    try {
      const result = await renameWorkspaceFolder(folder.id, cleanText(nextName));
      folders = folders.map((item) => (item.id === folder.id ? result.folder : item));
      records = records.map((record) => (record.folder_id === folder.id ? { ...record, folder_name: result.folder.name } : record));
      renderAll();
      showToast("文件夹已重命名。");
    } catch (error) {
      showToast(error.message || "重命名失败。", "error");
    }
    return;
  }
  const deleteButton = event.target.closest("[data-folder-delete]");
  if (deleteButton) {
    if (!(await flushDraftBeforeNavigation())) return;
    const folder = folders.find((item) => item.id === deleteButton.dataset.folderDelete);
    const folderTasks = uploadTasks.filter((task) => task.folder_id === folder?.id && !task.recordId);
    if (folderTasks.length) {
      showToast("请先完成或移除这个文件夹里的上传任务，再删除文件夹。", "error");
      return;
    }
    if (!folder || !window.confirm(`Delete "${folder.name}"? Images in this folder will move to Inbox.`)) return;
    try {
      await deleteWorkspaceFolder(folder.id);
      await loadFolders();
      await loadExistingUploadRecords();
      renderAll();
      if (activeRecordId) refreshActiveReadiness();
      showToast("文件夹已删除，里面的图片移到了 Inbox。");
    } catch (error) {
      showToast(error.message || "删除文件夹失败。", "error");
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
  resetDraftEditState(activeRecordId ? "已保存。" : "");
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

quickUploadOpen?.addEventListener("click", () => {
  if (quickUploadOpen.disabled) return;
  hydrateQuickUploadForm();
  if (typeof quickUploadDialog?.showModal === "function") quickUploadDialog.showModal();
  else quickUploadDialog?.setAttribute("open", "");
  window.requestAnimationFrame(() => quickUploadForm?.elements.namedItem("content_category")?.focus());
});

quickUploadCancel?.addEventListener("click", () => {
  pendingQuickUploadDefaults = null;
  if (typeof quickUploadDialog?.close === "function") quickUploadDialog.close();
  else quickUploadDialog?.removeAttribute("open");
});

quickRecognizablePeople?.addEventListener("change", syncQuickModelReleaseVisibility);

quickUploadForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!quickUploadForm.reportValidity()) return;
  pendingQuickUploadDefaults = quickUploadDefaultsFromForm();
  rememberedQuickUploadDefaults = pendingQuickUploadDefaults;
  if (typeof quickUploadDialog?.close === "function") quickUploadDialog.close();
  else quickUploadDialog?.removeAttribute("open");
  quickUploadInput?.click();
});

quickUploadInput?.addEventListener("change", async (event) => {
  const defaults = pendingQuickUploadDefaults;
  pendingQuickUploadDefaults = null;
  await handleFiles(event.target.files, { quickDefaults: defaults });
  quickUploadInput.value = "";
});

submitReadyButton?.addEventListener("click", submitReadyRecordsInFolder);

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

// Ctrl/⌘+S saves the open Draft; Ctrl/⌘+Enter publishes it. Ignored while a
// dialog is open so the shortcuts never act behind a confirmation.
document.addEventListener("keydown", (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
  if (document.querySelector("dialog[open]")) return;
  const key = event.key.toLowerCase();
  if (key === "s") {
    event.preventDefault();
    if (saveRecordButton && !saveRecordButton.disabled) formElement?.requestSubmit(saveRecordButton);
  } else if (key === "enter") {
    event.preventDefault();
    if (submitRecordButton && !submitRecordButton.disabled) submitActiveRecord();
  }
});

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
  const quickCopyrightYear = quickUploadForm?.elements.namedItem("copyright_year");
  if (quickCopyrightYear) quickCopyrightYear.max = String(new Date().getFullYear() + 1);
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
    setGlobalStatus("就绪");
    resetDraftEditState(activeRecordId ? "已保存。" : "");
  } catch (error) {
    workspaceOnline = false;
    activeWorkspaceView = "drafts";
    await loadOfflineCache().catch(() => {
      folders = defaultFolders();
      records = [];
      activeRecordId = null;
    });
    setGlobalStatus("离线只读");
    saveActiveFolder();
    showToast(error?.message || "无法连接后台，正在显示本地缓存（只能查看）。", "error");
  }
  workspaceLoading = false;
  renderAll();
  if (workspaceOnline && activeRecordId) refreshActiveReadiness();
}

initUploadStudio();
