const archiveSeedData = window.MTPresenceArchiveData || {};
const ratioProfiles = archiveSeedData.ratioProfiles || [
  { label: "1:1", ratio: 1 / 1 },
  { label: "4:3", ratio: 4 / 3 },
  { label: "4:5", ratio: 4 / 5 },
  { label: "2:3", ratio: 2 / 3 },
  { label: "3:2", ratio: 3 / 2 },
  { label: "16:9", ratio: 16 / 9 },
  { label: "Panorama", ratio: 2 / 1 },
];
const ratioFilterGroups = {
  Square: new Set(["1:1"]),
  Portrait: new Set(["4:5", "2:3"]),
  Landscape: new Set(["4:3", "3:2", "16:9"]),
  Panorama: new Set(["Panorama"]),
};

function ratioFilterGroupFor(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const group = Object.keys(ratioFilterGroups).find((label) => label.toLowerCase() === normalized);
  if (group) return group;
  return Object.entries(ratioFilterGroups).find(([, ratios]) => (
    [...ratios].some((ratio) => ratio.toLowerCase() === normalized)
  ))?.[0] || "All";
}

function itemMatchesRatioFilter(item) {
  return activeRatio === "All" || ratioFilterGroups[activeRatio]?.has(item.ratio) === true;
}

const abstractKeywords = [
  "abstract",
  "texture",
  "shadow",
  "light",
  "pattern",
  "geometry",
  "minimal",
  "detail",
  "surface",
  "reflection",
];

const concreteKeywords = [
  "people",
  "person",
  "portrait",
  "architecture",
  "building",
  "landscape",
  "mountain",
  "animal",
  "object",
  "forest",
  "river",
  "street",
];

const DB_NAME = "mt-cijian-archive";
const DB_VERSION = 4;
const DB_STORE = "images";
const SETTINGS_STORE = "site_settings";
const ARCHIVE_API_URL = "/api/archive/images";
const LOCAL_STORAGE_BUCKET = "indexeddb-local";
const DISPLAY_MAX_LONG_EDGE = 2300;
const DISPLAY_FORCE_RESIZE_RATIO = 1.12;
const DISPLAY_QUALITY = 0.86;
const THUMBNAIL_MAX_LONG_EDGE = 640;
const THUMBNAIL_QUALITY = 0.78;
const SQUARE_SLICE_MAX_EDGE = 1400;
const SQUARE_SLICE_QUALITY = 0.84;
const DERIVATIVE_MIME_TYPE = "image/jpeg";

const sampleItems = archiveSeedData.sampleItems || [
  {
    id: "sample-1",
    title: "Square Shadow Field",
    src: "assets/archive/abstract-square-01.jpg",
    width: 1600,
    height: 1600,
    type: "Abstract",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-2",
    title: "Vertical Light Pattern",
    src: "assets/archive/abstract-4x5-01.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-26",
    title: "Balanced Abstract Field",
    src: "assets/archive/abstract-4x3-01.jpg",
    width: 2000,
    height: 1500,
    type: "Abstract",
    ratio: "4:3",
    source: "Local sample",
  },
  {
    id: "sample-27",
    title: "Concrete Four Thirds Study",
    src: "assets/archive/concrete-4x3-01.jpg",
    width: 2000,
    height: 1500,
    type: "Concrete",
    ratio: "4:3",
    source: "Local sample",
  },
  {
    id: "sample-3",
    title: "Concrete Valley",
    src: "assets/archive/concrete-2x3-01.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-4",
    title: "Architectural Plane",
    src: "assets/archive/concrete-3x2-01.jpg",
    width: 2400,
    height: 1600,
    type: "Concrete",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-5",
    title: "Wide Weather",
    src: "assets/archive/concrete-16x9-01.jpg",
    width: 1920,
    height: 1080,
    type: "Concrete",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-6",
    title: "Panorama Surface",
    src: "assets/archive/abstract-panorama-01.jpg",
    width: 2400,
    height: 1200,
    type: "Abstract",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-7",
    title: "Minimal Stone Detail",
    src: "assets/archive/abstract-4x5-02.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-8",
    title: "Identifiable Coast",
    src: "assets/archive/concrete-2x3-02.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-9",
    title: "Horizontal Silence",
    src: "assets/archive/abstract-3x2-01.jpg",
    width: 2400,
    height: 1600,
    type: "Abstract",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-10",
    title: "Color Object Study",
    src: "assets/archive/concrete-square-01.jpg",
    width: 1600,
    height: 1600,
    type: "Concrete",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-11",
    title: "Abstract Wide Interval",
    src: "assets/archive/abstract-16x9-01.jpg",
    width: 1920,
    height: 1080,
    type: "Abstract",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-12",
    title: "Concrete Animal Study",
    src: "assets/archive/concrete-4x5-01.jpg",
    width: 1600,
    height: 2000,
    type: "Concrete",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-13",
    title: "Concrete Panorama",
    src: "assets/archive/concrete-panorama-01.jpg",
    width: 2400,
    height: 1200,
    type: "Concrete",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-14",
    title: "Square Abstract Interval",
    src: "assets/archive/abstract-square-02.jpg",
    width: 1600,
    height: 1600,
    type: "Abstract",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-15",
    title: "Concrete Square Study",
    src: "assets/archive/concrete-square-02.jpg",
    width: 1600,
    height: 1600,
    type: "Concrete",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-16",
    title: "Vertical Abstract Surface",
    src: "assets/archive/abstract-4x5-03.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-17",
    title: "Concrete Vertical Field",
    src: "assets/archive/concrete-4x5-02.jpg",
    width: 1600,
    height: 2000,
    type: "Concrete",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-18",
    title: "Tall Abstract Study",
    src: "assets/archive/abstract-2x3-01.jpg",
    width: 1600,
    height: 2400,
    type: "Abstract",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-19",
    title: "Tall Concrete Study",
    src: "assets/archive/concrete-2x3-03.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-20",
    title: "Abstract Horizontal Plane",
    src: "assets/archive/abstract-3x2-02.jpg",
    width: 2400,
    height: 1600,
    type: "Abstract",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-21",
    title: "Concrete Horizontal Plane",
    src: "assets/archive/concrete-3x2-02.jpg",
    width: 2400,
    height: 1600,
    type: "Concrete",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-22",
    title: "Abstract Wide Field",
    src: "assets/archive/abstract-16x9-02.jpg",
    width: 1920,
    height: 1080,
    type: "Abstract",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-23",
    title: "Concrete Wide Field",
    src: "assets/archive/concrete-16x9-02.jpg",
    width: 1920,
    height: 1080,
    type: "Concrete",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-24",
    title: "Abstract Long Horizon",
    src: "assets/archive/abstract-panorama-02.jpg",
    width: 2400,
    height: 1200,
    type: "Abstract",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-25",
    title: "Concrete Long Horizon",
    src: "assets/archive/concrete-panorama-02.jpg",
    width: 2400,
    height: 1200,
    type: "Concrete",
    ratio: "Panorama",
    source: "Local sample",
  },
];

const gallery = document.querySelector("[data-archive-gallery]");
const count = document.querySelector("[data-archive-count]");
const uploadInput = document.querySelector("[data-upload-input]");
const uploadStatusList = document.querySelector("[data-upload-status-list]");
const searchInput = document.querySelector("[data-global-search-input]");
const clearSearchButton = document.querySelector("[data-clear-search]");
const typeFilters = document.querySelector("[data-type-filters]");
const ratioFilters = document.querySelector("[data-ratio-filters]");
const emptyState = document.querySelector("[data-archive-empty]");
const dataStatus = document.querySelector("[data-archive-data-status]");
const arrangeToggle = document.querySelector("[data-arrange-toggle]");
const saveOrderButton = document.querySelector("[data-save-order]");
const arrangeDoneButton = document.querySelector("[data-arrange-done]");
const arrangeStatus = document.querySelector("[data-arrange-status]");
const arrangeLive = document.querySelector("[data-arrange-live]");
const savedFilterButton = document.querySelector("[data-saved-filter]");
const downloadVisibleButton = document.querySelector("[data-download-visible]");
const archiveToast = document.querySelector("[data-archive-toast]");
const workViewer = document.querySelector("[data-work-viewer]");
const workViewerDialog = document.querySelector("[data-work-viewer-dialog]");
const viewerStage = document.querySelector("[data-viewer-stage]");
const viewerImage = document.querySelector("[data-viewer-image]");
const viewerTitle = document.querySelector("[data-viewer-title]");
const viewerNote = document.querySelector("[data-viewer-note]");
const viewerDialogLabel = document.querySelector("[data-viewer-dialog-label]");
const viewerMetadata = document.querySelector("[data-viewer-metadata]");
const viewerPosition = document.querySelector("[data-viewer-position]");
const viewerMode = document.querySelector("[data-viewer-mode]");
const viewerTagsSection = document.querySelector("[data-viewer-tags-section]");
const viewerTags = document.querySelector("[data-viewer-tags]");
const viewerStatementSection = document.querySelector("[data-viewer-statement-section]");
const viewerStatementHeading = document.querySelector("[data-viewer-statement-heading]");
const viewerStatement = document.querySelector("[data-viewer-statement]");
const viewerRelatedSection = document.querySelector("[data-viewer-related-section]");
const viewerRelated = document.querySelector("[data-viewer-related]");
const viewerZoomButton = document.querySelector("[data-viewer-zoom]");
const viewerInfoButton = document.querySelector("[data-viewer-info-toggle]");
const viewerInfoPanel = document.querySelector("[data-viewer-info]");
const viewerPrevButton = document.querySelector("[data-viewer-prev]");
const viewerNextButton = document.querySelector("[data-viewer-next]");
const viewerCloseButton = document.querySelector("[data-viewer-close-button]");
const viewerInquireLink = document.querySelector("[data-viewer-inquire]");
const viewerCreator = document.querySelector("[data-viewer-creator]");
const lightboxCount = document.querySelector("[data-lightbox-count]");

const ORDER_STORAGE_KEY = "mt-cijian-archive-order-v1";
const publicArchive = window.MTPresencePublicArchive;
let activeType = "All";
let activeRatio = "All";
let activeSearch = "";
let showSavedOnly = false;
let archiveItems = [...sampleItems];
let archiveDataSource = "local";
let archiveDb = null;
let isArrangeMode = false;
let hasOrderChanges = false;
let draggedArchiveItemId = null;
let uploadTasks = [];
let viewerCurrentId = null;
let viewerTriggerElement = null;
let viewerSequenceIds = [];
let viewerScrollY = 0;
let viewerCloseTimer = null;
let viewerOriginalBodyOverflow = "";
let viewerOriginalHtmlOverflow = "";
let viewerOriginalBodyPaddingRight = "";
let isViewerZoomed = false;
let archiveToastTimer = null;
const pendingLightboxWorkIds = new Set();
const pendingLightboxTimers = new Map();

function replaceArchiveUrl(changes = {}) {
  const url = new URL(window.location.href);
  Object.entries(changes).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  });
  history.replaceState(history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function hydrateArchiveUrlState() {
  const params = new URLSearchParams(window.location.search);
  const requestedType = cleanText(params.get("type")).toLowerCase();
  const requestedRatio = cleanText(params.get("ratio"));
  const requestedQuery = cleanText(params.get("q"));
  const typeMatch = ["Abstract", "Concrete"].find((value) => value.toLowerCase() === requestedType);
  activeType = typeMatch || "All";
  activeRatio = ratioFilterGroupFor(requestedRatio);
  activeSearch = requestedQuery;
  if (searchInput) {
    searchInput.value = activeSearch;
  }
}

function readStoredIdSet(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

function writeStoredIdSet(key, ids) {
  try {
    localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    // Local viewing can continue even when storage is unavailable.
  }
}

let lightboxWorkIds = new Set(publicArchive?.readLightboxIds?.() || []);

function readSavedOrder() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ORDER_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function writeSavedOrder(ids) {
  try {
    localStorage.setItem(ORDER_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Local viewing can continue even when storage is unavailable.
  }
}

function applySavedSortOrders(items) {
  const savedOrder = readSavedOrder();
  const savedOrderIndex = new Map(savedOrder.map((id, index) => [id, index]));
  let fallbackIndex = savedOrder.length;

  return items.map((item) => {
    if (savedOrderIndex.has(item.id)) {
      return { ...item, sortOrder: savedOrderIndex.get(item.id) };
    }

    if (Number.isFinite(item.sortOrder)) {
      return { ...item };
    }

    const nextItem = { ...item, sortOrder: fallbackIndex };
    fallbackIndex += 1;
    return nextItem;
  });
}

function orderedItems() {
  return [...archiveItems].sort((a, b) => {
    const aOrder = Number.isFinite(a.sortOrder) ? a.sortOrder : 0;
    const bOrder = Number.isFinite(b.sortOrder) ? b.sortOrder : 0;
    return aOrder - bOrder;
  });
}

function normalizeSortOrders(items = orderedItems()) {
  items.forEach((item, index) => {
    item.sortOrder = index;
  });
  archiveItems = items;
}

function announceArrange(message) {
  if (arrangeLive) {
    arrangeLive.textContent = message;
  }
}

function classifyRatio(width, height) {
  const imageRatio = width / height;
  const closest = ratioProfiles.reduce(
    (best, item) => {
      const distance = Math.abs(imageRatio - item.ratio);
      return distance < best.distance ? { ...item, distance } : best;
    },
    { label: "1:1", distance: Number.POSITIVE_INFINITY },
  );

  return closest.label;
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

function contentTypeCode(type) {
  return type === "Abstract" ? "abstract" : "concrete";
}

function displayModeForType(type) {
  return type === "Abstract" ? "black_white" : "color";
}

function setArchiveDataStatus(message = "", state = "ready") {
  if (!dataStatus) {
    return;
  }
  dataStatus.textContent = message;
  dataStatus.hidden = !message;
  dataStatus.dataset.state = state;
}

function showArchiveToast(message, type = "default") {
  if (!archiveToast) {
    return;
  }
  window.clearTimeout(archiveToastTimer);
  archiveToast.textContent = message;
  archiveToast.dataset.type = type;
  archiveToast.hidden = false;
  archiveToast.classList.add("is-visible");
  archiveToastTimer = window.setTimeout(() => {
    archiveToast.classList.remove("is-visible");
    archiveToast.hidden = true;
  }, 2400);
}

function ratioCssValue(label) {
  const match = ratioProfiles.find((item) => item.label === label);
  return match ? `${match.ratio}` : "1";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function iconSvg(name) {
  return `
    <svg class="ui-icon" aria-hidden="true" focusable="false">
      <use href="#icon-${name}"></use>
    </svg>
  `;
}

function setButtonLabel(button, label) {
  const labelElement = button?.querySelector("[data-button-label]");
  if (labelElement) {
    labelElement.textContent = label;
  }
}

function stageLabel(stage) {
  const labels = {
    queued: "Queued",
    reading: "Reading",
    compressing: "Compressing",
    slicing: "Slicing",
    analyzing: "Analyzing",
    uploading: "Saving",
    complete: "Complete",
    failed: "Failed",
    warning: "Saved with fallback",
  };
  return labels[stage] || "Working";
}

function renderUploadTasks() {
  if (!uploadStatusList) {
    return;
  }

  uploadStatusList.hidden = uploadTasks.length === 0;
  uploadStatusList.innerHTML = uploadTasks
    .map(
      (task) => `
        <article class="upload-status-item" data-state="${escapeHtml(task.stage)}">
          <div class="upload-status-heading">
            <strong>${escapeHtml(task.name)}</strong>
            <span>${escapeHtml(stageLabel(task.stage))}</span>
          </div>
          <div class="upload-progress" aria-hidden="true">
            <span style="width: ${Math.min(Math.max(task.progress || 0, 0), 100)}%;"></span>
          </div>
          <p>${escapeHtml(task.message || "")}</p>
        </article>
      `,
    )
    .join("");
}

function updateUploadTask(task, stage, progress, message) {
  task.stage = stage;
  task.progress = progress;
  task.message = message;
  renderUploadTasks();
}

function createUploadTask(file, index) {
  return {
    id: `upload-task-${Date.now()}-${index}`,
    name: file.name || `Image ${index + 1}`,
    stage: "queued",
    progress: 0,
    message: "Waiting to start.",
  };
}

function yieldToMain() {
  return new Promise((resolve) => {
    window.setTimeout(resolve, 0);
  });
}

function isSquareRatio(width, height) {
  return Math.abs(width - height) <= Math.max(width, height) * 0.01;
}

function classifyContent(fileName = "") {
  // Replace this function with a vision-model call when the archive has a backend.
  const name = fileName.toLowerCase();
  if (abstractKeywords.some((keyword) => name.includes(keyword))) {
    return "Abstract";
  }
  if (concreteKeywords.some((keyword) => name.includes(keyword))) {
    return "Concrete";
  }

  return "Concrete";
}

async function analyzeImageContent(file) {
  return classifyContent(file.name);
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
      if (!database.objectStoreNames.contains(SETTINGS_STORE)) {
        database.createObjectStore(SETTINGS_STORE, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
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
    request.onerror = () => reject(request.error);
  });
}

function saveStoredItem(item) {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve();
      return;
    }

    const storedItem = {
      id: item.id,
      title: item.title,
      width: item.width,
      height: item.height,
      type: item.type,
      ratio: item.ratio,
      source: item.source,
      createdAt: item.createdAt,
      sortOrder: item.sortOrder,
      description: item.description || item.imageRecord?.description || "",
      curatorial_note: item.curatorial_note || item.imageRecord?.curatorial_note || "",
      artist_statement: item.artist_statement || item.imageRecord?.artist_statement || "",
      captured_at: item.captured_at || item.imageRecord?.captured_at || "",
      series: item.series || item.imageRecord?.series || "",
      tags: item.tags || item.imageRecord?.tags || [],
      tag_groups: item.tag_groups || item.imageRecord?.tag_groups || [],
      imageTags: item.imageTags || [],
      imageTaggings: item.imageTaggings || [],
      image_url: item.image_url || "",
      thumbnail_url: item.thumbnail_url || "",
      display_mode: item.display_mode || item.imageRecord?.display_mode || "",
      imageRecord: item.imageRecord || null,
      assets: (item.assets || []).map(({ objectUrl, ...asset }) => asset),
      squareSliceCount: item.squareSliceCount || 0,
      squareSlices: item.squareSlices || [],
    };

    const request = transactionStore("readwrite").put(storedItem);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

function assetObjectUrl(asset) {
  if (!asset?.blob) {
    return null;
  }
  if (!asset.objectUrl) {
    asset.objectUrl = URL.createObjectURL(asset.blob);
  }
  return asset.objectUrl;
}

function preferredDisplayAsset(assets = []) {
  return (
    assets.find((asset) => asset.kind === "display") ||
    assets.find((asset) => asset.kind === "original") ||
    null
  );
}

function displayAsset(assets = []) {
  return assets.find((asset) => asset.kind === "display") || null;
}

function originalAsset(assets = []) {
  return assets.find((asset) => asset.kind === "original") || null;
}

function preferredThumbnailAsset(assets = []) {
  return assets.find((asset) => asset.kind === "thumbnail") || null;
}

function publicAssetUrl(asset) {
  if (!asset) {
    return null;
  }
  return asset.url || asset.public_url || asset.signed_url || assetObjectUrl(asset);
}

function detailImageUrl(item) {
  const record = item.imageRecord || {};
  const assets = item.assets || [];
  return (
    publicAssetUrl(displayAsset(assets)) ||
    item.image_url ||
    record.image_url ||
    record.display_url ||
    record.public_url ||
    item.src ||
    publicAssetUrl(originalAsset(assets)) ||
    publicAssetUrl(preferredThumbnailAsset(assets)) ||
    record.original_url ||
    record.thumbnail_url ||
    ""
  );
}

function thumbnailImageUrl(item) {
  const record = item.imageRecord || {};
  return publicAssetUrl(preferredThumbnailAsset(item.assets || [])) || item.thumbnail_url || record.thumbnail_url || item.src || "";
}

function archiveApiRowToItem(row, deliverySource = "") {
  const normalized = publicArchive?.normalizeApiWork?.(row, deliverySource) || {};
  const type = normalized.type || contentTypeLabelFromCode(row.content_type || row.content_category) || "Concrete";
  const width = Number(normalized.width || row.original_width || 0);
  const height = Number(normalized.height || row.original_height || 0);
  const ratio = normalized.ratio || row.ratio_label || ratioLabelFromCode(row.ratio_category_code) || classifyRatio(width, height);
  const tagGroups = normalizeTagGroupList(normalized.tag_groups || row.tag_groups);
  const tags = tagsFromValue(normalized.tags || row.tags);
  const imageUrl = normalized.src || row.image_url || row.display_url || "";

  return {
    ...normalized,
    id: normalized.id || row.id,
    title: normalized.title || row.title || "Untitled Work",
    src: imageUrl,
    width,
    height,
    type,
    ratio,
    ratio_label: normalized.ratio_label || row.ratio_label,
    source: row.source_type === "local_sample" ? "Local sample" : "Archive database",
    createdAt: row.uploaded_at ? Date.parse(row.uploaded_at) || 0 : 0,
    sortOrder: Number.isFinite(Number(row.sort_order)) ? Number(row.sort_order) : 0,
    description: normalized.description || row.description || "",
    curatorial_note: normalized.curatorial_note || row.curatorial_note || row.caption || "",
    artist_statement: normalized.artist_statement || row.artist_statement || "",
    alt_text: normalized.alt_text || row.alt_text || "",
    captured_at: normalized.captured_at || row.captured_at || "",
    series: normalized.series || row.series || "",
    tags,
    tag_groups: tagGroups,
    image_url: imageUrl,
    thumbnail_url: normalized.thumbnail_url || row.thumbnail_url || "",
    original_url: publicArchive?.isAuthoritativeSource?.(deliverySource) ? "" : row.original_url || "",
    display_mode: normalized.display_mode || row.display_mode || displayModeForType(type),
    original_width: width,
    original_height: height,
    original_filename: normalized.original_filename || row.original_filename || "",
    visibility: normalized.visibility || row.visibility || "published",
    creator: normalized.creator || null,
    deliverySource,
    imageRecord: {
      ...row,
      tags,
      tag_groups: tagGroups,
      original_width: width,
      original_height: height,
      ratio_category_code: row.ratio_category_code || ratioCategoryCode(ratio),
      content_type: row.content_type || row.content_category || contentTypeCode(type),
      display_mode: normalized.display_mode || row.display_mode || displayModeForType(type),
      visibility: normalized.visibility || row.visibility || "published",
    },
    assets: [],
    squareSliceCount: Number(row.square_slice_count || 0),
    squareSlices: [],
  };
}

async function fetchArchiveApiItems() {
  const response = await fetch(ARCHIVE_API_URL, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  const source = cleanText(payload.source) || "api";
  if (!response.ok) {
    const message = cleanText(
      payload?.error?.message
      || (typeof payload?.error === "string" ? payload.error : "")
      || payload?.hint,
    ) || `Archive API returned ${response.status}.`;
    const error = new Error(message);
    error.source = source;
    error.authoritative = publicArchive?.isAuthoritativeSource?.(source) === true;
    throw error;
  }

  const rows = Array.isArray(payload.items) ? payload.items : [];
  const items = rows.map((row) => archiveApiRowToItem(row, source)).filter((item) => item.id && item.src);
  return {
    items,
    source,
    authoritative: publicArchive?.isAuthoritativeSource?.(source) === true,
    count: Number.isFinite(Number(payload.count)) ? Number(payload.count) : items.length,
  };
}

function cleanText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function slugify(value, fallback = "item") {
  return (
    cleanText(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 96) || fallback
  );
}

function humanizeToken(value) {
  return cleanText(value)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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

function contentTypeLabelFromCode(code) {
  const labels = {
    abstract: "Abstract",
    concrete: "Concrete",
  };
  return labels[code] || humanizeToken(code);
}

function normalizeCapturedDate(value) {
  const text = cleanText(value);
  if (!text) {
    return "";
  }

  const exifMatch = text.match(/^(\d{4}):(\d{2}):(\d{2})(?:\s+(.+))?$/);
  if (exifMatch) {
    return `${exifMatch[1]}-${exifMatch[2]}-${exifMatch[3]}`;
  }

  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) {
    return date.toISOString().slice(0, 10);
  }

  return text;
}

function flattenSearchValues(value, results = []) {
  if (value === null || value === undefined) {
    return results;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => flattenSearchValues(item, results));
    return results;
  }
  if (typeof value === "object") {
    Object.values(value).forEach((item) => flattenSearchValues(item, results));
    return results;
  }
  const text = cleanText(value);
  if (text) {
    results.push(text);
  }
  return results;
}

function ratioKeywordText(item, ratioLabel) {
  const width = Number(item.width || item.original_width || item.imageRecord?.original_width || 0);
  const height = Number(item.height || item.original_height || item.imageRecord?.original_height || 0);
  const label = cleanText(ratioLabel).toLowerCase();
  const keywords = [label];
  if (label === "panorama") {
    keywords.push("wide", "horizontal");
  }
  if (label === "4:5" || label === "2:3") {
    keywords.push("vertical", "portrait");
  }
  if (label === "4:3" || label === "3:2" || label === "16:9") {
    keywords.push("horizontal", "landscape");
  }
  if (width && height) {
    if (width > height) {
      keywords.push("horizontal", "landscape");
    } else if (height > width) {
      keywords.push("vertical", "portrait");
    } else {
      keywords.push("square");
    }
  }
  return uniqueTextList(keywords).join(" ");
}

function parsedTagValue(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text || !["[", "{"].includes(text[0])) {
    return value;
  }

  try {
    return JSON.parse(text);
  } catch {
    return value;
  }
}

function tagsFromValue(value) {
  const parsed = parsedTagValue(value);
  if (parsed === null || parsed === undefined) {
    return [];
  }
  if (Array.isArray(parsed)) {
    return uniqueTextList(parsed.flatMap((item) => tagsFromValue(item)));
  }
  if (typeof parsed === "object") {
    const directName = parsed.name || parsed.tag_name || parsed.tagName || parsed.title;
    if (directName) {
      return [directName];
    }
    if (parsed.tags || parsed.items || parsed.values) {
      return tagsFromValue(parsed.tags || parsed.items || parsed.values);
    }
    return [];
  }

  return uniqueTextList(String(parsed).split(/[,;|]/));
}

function normalizeTagGroupList(value) {
  const parsed = parsedTagValue(value);
  const source = Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
  const groups = [];

  source.forEach((group) => {
    if (!group || typeof group !== "object") {
      return;
    }

    const label = cleanText(group.label || group.group_name || group.groupName || group.name);
    const tags = tagsFromValue(group.tags || group.items || group.values);
    if (!label || !tags.length) {
      return;
    }
    groups.push({ label, tags });
  });

  return normalizeTagGroups(groups);
}

function normalizeTagGroups(groups = []) {
  const byLabel = new Map();

  groups.forEach((group) => {
    const label = cleanText(group.label || group.group_name || group.groupName);
    const tags = uniqueTextList(group.tags || []);
    if (!label || !tags.length) {
      return;
    }

    const existing = byLabel.get(label.toLowerCase());
    if (existing) {
      existing.tags = uniqueTextList([...existing.tags, ...tags]);
    } else {
      byLabel.set(label.toLowerCase(), { label, tags });
    }
  });

  return Array.from(byLabel.values());
}

function existingTagGroupsForItem(item) {
  const record = item.imageRecord || {};
  const explicitGroups = normalizeTagGroups([
    ...normalizeTagGroupList(item.tag_groups),
    ...normalizeTagGroupList(record.tag_groups),
  ]);
  if (explicitGroups.length) {
    return explicitGroups;
  }

  const groupedTags = new Map();
  const collectTagRows = (rows) => {
    const source = parsedTagValue(rows);
    if (!Array.isArray(source)) {
      return;
    }

    source.forEach((row) => {
      if (!row || typeof row !== "object") {
        return;
      }
      const label = cleanText(row.group_name || row.groupName || row.group || "Subject");
      const name = cleanText(row.name || row.tag_name || row.tagName || row.label);
      if (!label || !name) {
        return;
      }
      const key = label.toLowerCase();
      const current = groupedTags.get(key) || { label, tags: [] };
      current.tags.push(name);
      groupedTags.set(key, current);
    });
  };

  collectTagRows(item.imageTags);
  collectTagRows(record.imageTags);
  const imageTagGroups = normalizeTagGroups(Array.from(groupedTags.values()));
  if (imageTagGroups.length) {
    return imageTagGroups;
  }

  const flatTags = uniqueTextList([
    ...tagsFromValue(item.tags),
    ...tagsFromValue(record.tags),
  ]);
  return flatTags.length ? [{ label: "Subject", tags: flatTags }] : [];
}

function titleContains(title, tokens) {
  const lower = cleanText(title).toLowerCase();
  return tokens.some((token) => lower.includes(token));
}

function orientationTag(ratioLabel, width, height) {
  if (ratioLabel === "Panorama") {
    return "Panorama";
  }
  if (Number(width) && Number(height)) {
    if (Number(width) === Number(height)) {
      return "Square";
    }
    return Number(height) > Number(width) ? "Vertical" : "Horizontal";
  }
  if (["4:5", "2:3"].includes(ratioLabel)) {
    return "Vertical";
  }
  if (["4:3", "3:2", "16:9"].includes(ratioLabel)) {
    return "Horizontal";
  }
  return "";
}

function deriveTagGroupsForItem(item, detail = {}) {
  const title = detail.title || item.title || item.imageRecord?.title || "";
  const type = detail.type || item.type || contentTypeLabelFromCode(item.imageRecord?.content_type) || "Concrete";
  const ratioLabel = detail.ratioLabel || item.ratio_label || item.ratio || ratioLabelFromCode(item.imageRecord?.ratio_category_code);
  const width = detail.originalWidth || item.original_width || item.imageRecord?.original_width || item.width;
  const height = detail.originalHeight || item.original_height || item.imageRecord?.original_height || item.height;
  const displayMode = detail.displayMode || item.display_mode || item.imageRecord?.display_mode || displayModeForType(type);
  const subjectTags = [type];
  const placeTags = [];
  const moodTags = [];
  const surfaceTags = [];

  if (type === "Abstract") {
    subjectTags.push("Abstract Study");
  }

  if (titleContains(title, ["landscape", "valley", "coast", "weather", "horizon", "panorama", "field", "mountain", "snow", "sky", "wide"])) {
    subjectTags.push("Landscape");
    placeTags.push("Natural Landscape");
  }
  if (titleContains(title, ["architect", "building", "house", "home", "room", "interior", "facade", "roof", "wall", "window"])) {
    subjectTags.push("House / Building", "Architecture");
    placeTags.push("Built Environment");
  }
  if (titleContains(title, ["coast", "water", "sea", "shore", "ocean"])) {
    subjectTags.push("Coast / Water");
    placeTags.push("Coast");
  }
  if (titleContains(title, ["valley", "mountain", "snow"])) {
    subjectTags.push("Mountain / Valley");
    placeTags.push("Valley");
  }
  if (titleContains(title, ["animal"])) {
    subjectTags.push("Animal");
  }
  if (titleContains(title, ["object"])) {
    subjectTags.push("Object");
  }
  if (titleContains(title, ["stone", "rock"])) {
    subjectTags.push("Stone");
    surfaceTags.push("Stone");
  }
  if (titleContains(title, ["surface", "pattern", "plane", "shadow", "light", "interval"])) {
    subjectTags.push("Surface / Pattern");
  }
  if (!subjectTags.some((tag) => tag !== type)) {
    subjectTags.push(type === "Abstract" ? "Surface / Pattern" : "Observed World");
  }

  [
    ["shadow", "Shadow"],
    ["light", "Light"],
    ["minimal", "Minimal"],
    ["silence", "Silence"],
    ["weather", "Weather"],
    ["balanced", "Balance"],
    ["wide", "Open Space"],
    ["long", "Open Horizon"],
    ["horizon", "Open Horizon"],
    ["vertical", "Vertical Stillness"],
    ["tall", "Vertical Stillness"],
    ["field", "Field"],
    ["plane", "Plane"],
    ["surface", "Surface"],
  ].forEach(([token, label]) => {
    if (titleContains(title, [token])) {
      moodTags.push(label);
    }
  });

  const toneTags =
    displayMode === "black_white" || type === "Abstract"
      ? ["Black and white", "Monochrome"]
      : ["Color"];

  return normalizeTagGroups([
    { label: "Subject", tags: subjectTags },
    { label: "Place", tags: placeTags },
    { label: "Form / Ratio", tags: [ratioLabel, orientationTag(ratioLabel, width, height)] },
    { label: "Mood", tags: moodTags.length ? moodTags : ["Quiet Observation"] },
    { label: "Material / Surface", tags: surfaceTags },
    { label: "Palette / Tone", tags: toneTags },
    { label: "Series / Collection", tags: [item.source || item.imageRecord?.source_type || "Local Sample", `${type} Archive`] },
  ]);
}

function tagGroupsForItem(item, detail = {}) {
  const existingGroups = existingTagGroupsForItem(item);
  return existingGroups.length ? existingGroups : deriveTagGroupsForItem(item, detail);
}

function flatTagsFromGroups(groups = []) {
  return uniqueTextList(groups.flatMap((group) => group.tags || []));
}

function searchableTextForItem(item) {
  const record = item.imageRecord || {};
  const ratioLabel = item.ratio_label || item.ratio || ratioLabelFromCode(record.ratio_category_code);
  const type = item.type || contentTypeLabelFromCode(record.content_type) || "Concrete";
  const tagGroups = tagGroupsForItem(item, {
    title: item.title || record.title,
    type,
    ratioLabel,
    displayMode: item.display_mode || record.display_mode || displayModeForType(type),
    originalWidth: item.original_width || record.original_width || item.width,
    originalHeight: item.original_height || record.original_height || item.height,
  });
  const values = [
    item.title,
    record.title,
    item.series,
    record.series,
    item.description,
    record.description,
    item.curatorial_note,
    record.curatorial_note,
    item.artist_statement,
    record.artist_statement,
    item.content_type,
    record.content_type,
    item.type,
    item.ratio,
    item.ratio_label,
    ratioLabel,
    record.ratio_label,
    record.ratio_category_code,
    item.original_filename,
    record.original_filename,
    item.source,
    record.source_type,
    ratioKeywordText(item, ratioLabel),
    flattenSearchValues(item.tags || record.tags),
    flattenSearchValues(item.tag_groups || record.tag_groups),
    flattenSearchValues(item.imageTags),
    flattenSearchValues(tagGroups),
  ];

  return flattenSearchValues(values).join(" ").toLowerCase();
}

function searchTokens() {
  return cleanText(activeSearch)
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
}

function itemMatchesSearch(item) {
  const tokens = searchTokens();
  if (!tokens.length) {
    return true;
  }
  const haystack = searchableTextForItem(item);
  return tokens.every((token) => haystack.includes(token));
}

function normalizeWorkDetail(item) {
  const record = item.imageRecord || {};
  const exif = record.exif || item.exif || {};
  const type = item.type || contentTypeLabelFromCode(record.content_type) || "Concrete";
  const ratioLabel = item.ratio_label || item.ratio || ratioLabelFromCode(record.ratio_category_code) || "Unclassified";
  const displayMode = item.display_mode || record.display_mode || displayModeForType(type);
  const originalWidth = item.original_width || record.original_width || item.width;
  const originalHeight = item.original_height || record.original_height || item.height;
  const series = cleanText(item.series || record.series || item.collection);
  const capturedAt = normalizeCapturedDate(item.captured_at || record.captured_at || exif.datetime_original || exif.datetime);
  const description = cleanText(item.description || record.description);
  const curatorialNote = cleanText(item.curatorial_note || item.curatorialNote || record.curatorial_note);
  const artistStatement = cleanText(item.artist_statement || item.artistStatement || record.artist_statement);
  const defaultNote =
    type === "Abstract"
      ? "The frame withholds immediate recognition, allowing surface, rhythm, and light to lead the encounter."
      : "The image stays close to the visible world while leaving space for distance, weather, and duration.";
  const detail = {
    title: cleanText(item.title || record.title || "Untitled Work"),
    type,
    typeLabel: contentTypeLabelFromCode(record.content_type) || type,
    ratioLabel,
    displayMode,
    originalWidth,
    originalHeight,
    capturedAt,
    capturedLabel: capturedAt || "Undated",
    series,
    note: curatorialNote || description || defaultNote,
    statement: artistStatement || (curatorialNote && description ? description : ""),
    altText: cleanText(item.alt_text || record.alt_text) || cleanText(item.title || record.title || "Untitled Work"),
    imageUrl: detailImageUrl(item),
    thumbnailUrl: thumbnailImageUrl(item),
  };
  detail.tagGroups = tagGroupsForItem(item, detail);
  detail.tags = flatTagsFromGroups(detail.tagGroups);

  return detail;
}

function reviveStoredItem(item) {
  const visibility = effectiveArchiveVisibility(item);
  const restoredDetailFields = {
    description: item.description || item.imageRecord?.description || "",
    curatorial_note: item.curatorial_note || item.imageRecord?.curatorial_note || "",
    artist_statement: item.artist_statement || item.imageRecord?.artist_statement || "",
    captured_at: item.captured_at || item.imageRecord?.captured_at || "",
    series: item.series || item.imageRecord?.series || "",
    tags: item.tags || item.imageRecord?.tags || [],
    tag_groups: item.tag_groups || item.imageRecord?.tag_groups || [],
    imageTags: item.imageTags || [],
    imageTaggings: item.imageTaggings || [],
    image_url: item.image_url || "",
    thumbnail_url: item.thumbnail_url || "",
    display_mode: item.display_mode || item.imageRecord?.display_mode || "",
    visibility,
  };

  if (Array.isArray(item.assets) && item.assets.length) {
    const assets = item.assets.map((asset) => ({ ...asset }));
    const displayAsset = preferredDisplayAsset(assets);
    const imageRecord = item.imageRecord ? { ...item.imageRecord, visibility } : null;
    return {
      id: item.id,
      title: item.title,
      src: assetObjectUrl(displayAsset),
      width: item.width,
      height: item.height,
      type: item.type,
      ratio: item.ratio,
      source: item.source || "Uploaded",
      createdAt: item.createdAt || 0,
      sortOrder: item.sortOrder,
      imageRecord,
      assets,
      squareSliceCount: item.squareSliceCount || 0,
      squareSlices: item.squareSlices || [],
      ...restoredDetailFields,
    };
  }

  if (!item.blob) {
    const imageRecord = item.imageRecord ? { ...item.imageRecord, visibility } : null;
    return {
      id: item.id,
      title: item.title,
      src: item.src || item.image_url || item.imageRecord?.image_url || "",
      width: item.width || item.imageRecord?.original_width,
      height: item.height || item.imageRecord?.original_height,
      type: item.type || contentTypeLabelFromCode(item.imageRecord?.content_type),
      ratio: item.ratio || ratioLabelFromCode(item.imageRecord?.ratio_category_code),
      source: item.source || "Local sample",
      createdAt: item.createdAt || 0,
      sortOrder: item.sortOrder,
      imageRecord,
      assets: [],
      squareSliceCount: item.squareSliceCount || 0,
      squareSlices: item.squareSlices || [],
      ...restoredDetailFields,
    };
  }

  return {
    id: item.id,
    title: item.title,
    src: URL.createObjectURL(item.blob),
    width: item.width,
    height: item.height,
    type: item.type,
    ratio: item.ratio,
    source: item.source || "Uploaded",
    createdAt: item.createdAt || 0,
    sortOrder: item.sortOrder,
    squareSliceCount: item.squareSliceCount || 0,
    squareSlices: item.squareSlices || [],
    ...restoredDetailFields,
  };
}

function isStoredUpload(item) {
  return item?.blob || item?.source === "Uploaded" || item?.imageRecord?.source_type === "upload";
}

function effectiveArchiveVisibility(item) {
  const record = item?.imageRecord || {};
  return cleanText(record.visibility || item?.visibility);
}

function isPublishedArchiveItem(item) {
  const visibility = effectiveArchiveVisibility(item);
  if (visibility) {
    return visibility === "published";
  }
  return item?.source === "Local sample" || item?.imageRecord?.source_type === "local_sample";
}

function mergeStoredWorkDetail(baseItem, storedItem) {
  if (!storedItem) {
    return { ...baseItem };
  }

  const revived = reviveStoredItem(storedItem);
  const baseRecord = baseItem.imageRecord || {};
  const savedRecord = revived.imageRecord || {};
  return {
    ...baseItem,
    title: revived.title || baseItem.title,
    type: contentTypeLabelFromCode(savedRecord.content_type) || baseItem.type,
    sortOrder: Number.isFinite(savedRecord.sort_order) ? savedRecord.sort_order : revived.sortOrder ?? baseItem.sortOrder,
    description: revived.description || "",
    curatorial_note: revived.curatorial_note || "",
    artist_statement: revived.artist_statement || "",
    captured_at: revived.captured_at || "",
    series: revived.series || "",
    tags: revived.tags || [],
    tag_groups: revived.tag_groups || [],
    imageTags: revived.imageTags || [],
    imageTaggings: revived.imageTaggings || [],
    display_mode: revived.display_mode || baseItem.display_mode,
    visibility: savedRecord.visibility || revived.visibility || baseItem.visibility,
    imageRecord: {
      ...baseRecord,
      ...savedRecord,
      id: baseItem.id,
      original_width: baseItem.width,
      original_height: baseItem.height,
      ratio_category_code: ratioCategoryCode(baseItem.ratio),
      content_type: savedRecord.content_type || contentTypeCode(baseItem.type),
      display_mode: savedRecord.display_mode || displayModeForType(baseItem.type),
    },
  };
}

function canvasToBlob(canvas, type = DERIVATIVE_MIME_TYPE, quality = DISPLAY_QUALITY) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Could not create square slice."));
        }
      },
      type,
      quality,
    );
  });
}

function hasCanvasExportSupport() {
  const canvas = document.createElement("canvas");
  return Boolean(canvas.getContext && canvas.toBlob);
}

function imageExtension(mimeType, fallback = "jpg") {
  if (mimeType === "image/png") {
    return "png";
  }
  if (mimeType === "image/webp") {
    return "webp";
  }
  if (mimeType === "image/gif") {
    return "gif";
  }
  return fallback;
}

function sanitizePathPart(value) {
  return String(value || "image")
    .toLowerCase()
    .replace(/\.[^.]+$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72) || "image";
}

function buildStoragePath(imageId, kind, fileName, extension = "jpg", index = null) {
  const stem = sanitizePathPart(fileName);
  const suffix = index === null ? "" : `-${String(index + 1).padStart(2, "0")}`;
  return `draft/${imageId}/${kind}${suffix}-${stem}.${extension}`;
}

async function sha256HexFromBuffer(buffer) {
  if (!crypto?.subtle) {
    return null;
  }

  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256HexFromBlob(blob) {
  return sha256HexFromBuffer(await blob.arrayBuffer());
}

function readAscii(view, offset, length) {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    const code = view.getUint8(offset + index);
    if (code === 0) {
      break;
    }
    value += String.fromCharCode(code);
  }
  return value.trim();
}

function parseExifValue(view, tiffStart, valueOffset, type, count, littleEndian) {
  const typeSize = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1 }[type] || 1;
  const byteLength = typeSize * count;
  const dataOffset = byteLength <= 4 ? valueOffset : tiffStart + view.getUint32(valueOffset, littleEndian);

  if (type === 2) {
    return readAscii(view, dataOffset, count);
  }

  if (type === 3) {
    return count === 1
      ? view.getUint16(dataOffset, littleEndian)
      : Array.from({ length: count }, (_, index) => view.getUint16(dataOffset + index * 2, littleEndian));
  }

  if (type === 4) {
    return count === 1
      ? view.getUint32(dataOffset, littleEndian)
      : Array.from({ length: count }, (_, index) => view.getUint32(dataOffset + index * 4, littleEndian));
  }

  if (type === 5) {
    const readRational = (offset) => {
      const numerator = view.getUint32(offset, littleEndian);
      const denominator = view.getUint32(offset + 4, littleEndian);
      return denominator ? numerator / denominator : null;
    };
    return count === 1
      ? readRational(dataOffset)
      : Array.from({ length: count }, (_, index) => readRational(dataOffset + index * 8));
  }

  return null;
}

function readExifIfd(view, tiffStart, ifdOffset, littleEndian, tagMap) {
  const values = {};
  const absoluteOffset = tiffStart + ifdOffset;
  if (absoluteOffset <= 0 || absoluteOffset + 2 > view.byteLength) {
    return values;
  }

  const entryCount = view.getUint16(absoluteOffset, littleEndian);
  for (let index = 0; index < entryCount; index += 1) {
    const entryOffset = absoluteOffset + 2 + index * 12;
    if (entryOffset + 12 > view.byteLength) {
      break;
    }

    const tag = view.getUint16(entryOffset, littleEndian);
    const key = tagMap[tag];
    if (!key) {
      continue;
    }

    const type = view.getUint16(entryOffset + 2, littleEndian);
    const count = view.getUint32(entryOffset + 4, littleEndian);
    values[key] = parseExifValue(view, tiffStart, entryOffset + 8, type, count, littleEndian);
  }

  return values;
}

function extractExif(buffer, mimeType) {
  if (mimeType !== "image/jpeg") {
    return { status: "unsupported_mime" };
  }

  const view = new DataView(buffer);
  let offset = 2;
  while (offset + 4 < view.byteLength) {
    if (view.getUint8(offset) !== 0xff) {
      break;
    }

    const marker = view.getUint8(offset + 1);
    const segmentLength = view.getUint16(offset + 2, false);
    if (marker === 0xe1 && readAscii(view, offset + 4, 6) === "Exif") {
      const tiffStart = offset + 10;
      const endian = readAscii(view, tiffStart, 2);
      const littleEndian = endian === "II";
      if (!littleEndian && endian !== "MM") {
        return { status: "invalid_endian" };
      }

      const firstIfdOffset = view.getUint32(tiffStart + 4, littleEndian);
      const ifd0Tags = {
        0x010f: "camera_make",
        0x0110: "camera_model",
        0x0112: "orientation",
        0x0131: "software",
        0x0132: "datetime",
        0x013b: "artist",
        0x8298: "copyright",
        0x8769: "exif_ifd_offset",
      };
      const exifTags = {
        0x829a: "exposure_time",
        0x829d: "f_number",
        0x8827: "iso",
        0x9003: "datetime_original",
        0x9004: "datetime_digitized",
        0x920a: "focal_length",
        0xa434: "lens_model",
      };
      const ifd0 = readExifIfd(view, tiffStart, firstIfdOffset, littleEndian, ifd0Tags);
      const exif =
        Number.isFinite(ifd0.exif_ifd_offset) && ifd0.exif_ifd_offset > 0
          ? readExifIfd(view, tiffStart, ifd0.exif_ifd_offset, littleEndian, exifTags)
          : {};
      delete ifd0.exif_ifd_offset;
      return { status: "parsed", ...ifd0, ...exif };
    }

    offset += 2 + segmentLength;
  }

  return { status: "not_found" };
}

async function createImageSource(blob) {
  if ("createImageBitmap" in window) {
    const bitmap = await createImageBitmap(blob);
    return {
      source: bitmap,
      width: bitmap.width,
      height: bitmap.height,
      close: () => bitmap.close(),
    };
  }

  const url = URL.createObjectURL(blob);
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve({
        source: image,
        width: image.naturalWidth,
        height: image.naturalHeight,
        close: () => {},
      });
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read image dimensions."));
    };
    image.src = url;
  });
}

function targetDimensions(width, height, maxLongEdge) {
  const longest = Math.max(width, height);
  const scale = longest > maxLongEdge ? maxLongEdge / longest : 1;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

async function drawImageVersion(source, sourceRect, outputSize, type, quality) {
  const canvas = document.createElement("canvas");
  canvas.width = outputSize.width;
  canvas.height = outputSize.height;

  const context = canvas.getContext("2d", { alpha: false });
  if (!context) {
    throw new Error("Canvas is not available for image processing.");
  }

  context.drawImage(
    source,
    sourceRect.x,
    sourceRect.y,
    sourceRect.width,
    sourceRect.height,
    0,
    0,
    outputSize.width,
    outputSize.height,
  );
  return canvasToBlob(canvas, type, quality);
}

function createAsset({ imageId, kind, fileName, blob, width, height, checksum, index = null, sourceAssetId = null }) {
  const extension = kind === "original" ? imageExtension(blob.type) : "jpg";
  return {
    id: `${imageId}-${kind}${index === null ? "" : `-${index}`}`,
    image_id: imageId,
    kind,
    storage_bucket: LOCAL_STORAGE_BUCKET,
    storage_path: buildStoragePath(imageId, kind, fileName, extension, index),
    public_url: null,
    mime_type: blob.type || DERIVATIVE_MIME_TYPE,
    byte_size: blob.size,
    width,
    height,
    checksum_sha256: checksum,
    source_asset_id: sourceAssetId,
    blob,
  };
}

async function createDerivativeAsset({ imageId, kind, fileName, imageSource, maxLongEdge, quality, sourceAssetId }) {
  const size = targetDimensions(imageSource.width, imageSource.height, maxLongEdge);
  const blob = await drawImageVersion(
    imageSource.source,
    { x: 0, y: 0, width: imageSource.width, height: imageSource.height },
    size,
    DERIVATIVE_MIME_TYPE,
    quality,
  );
  return createAsset({
    imageId,
    kind,
    fileName,
    blob,
    width: size.width,
    height: size.height,
    checksum: await sha256HexFromBlob(blob),
    sourceAssetId,
  });
}

async function createSquareSlices(imageId, imageSource, fileName, sourceAssetId) {
  const { width, height } = imageSource;
  if (isSquareRatio(width, height)) {
    return { assets: [], squareSlices: [] };
  }

  const tileSize = Math.min(width, height);
  const longSide = Math.max(width, height);
  const tileCount = Math.ceil(longSide / tileSize);
  const assets = [];
  const squareSlices = [];
  const outputSize = Math.min(tileSize, SQUARE_SLICE_MAX_EDGE);

  for (let index = 0; index < tileCount; index += 1) {
    await yieldToMain();
    const offset = tileCount === 1 ? 0 : Math.round((longSide - tileSize) * (index / (tileCount - 1)));
    const sourceX = width >= height ? offset : 0;
    const sourceY = height > width ? offset : 0;

    const blob = await drawImageVersion(
      imageSource.source,
      { x: sourceX, y: sourceY, width: tileSize, height: tileSize },
      { width: outputSize, height: outputSize },
      DERIVATIVE_MIME_TYPE,
      SQUARE_SLICE_QUALITY,
    );
    const asset = createAsset({
      imageId,
      kind: "square_slice",
      fileName,
      blob,
      width: outputSize,
      height: outputSize,
      checksum: await sha256HexFromBlob(blob),
      index,
      sourceAssetId,
    });
    assets.push(asset);
    squareSlices.push({
      id: `${imageId}-slice-${index}`,
      image_id: imageId,
      asset_id: asset.id,
      slice_index: index,
      source_x: sourceX,
      source_y: sourceY,
      source_size: tileSize,
      width: outputSize,
      height: outputSize,
    });
  }

  return { assets, squareSlices };
}

function filteredItems() {
  return orderedItems().filter((item) => {
    const typeMatch = activeType === "All" || item.type === activeType;
    const ratioMatch = itemMatchesRatioFilter(item);
    const savedMatch = !showSavedOnly || lightboxWorkIds.has(item.id);
    return savedMatch && typeMatch && ratioMatch && itemMatchesSearch(item);
  });
}

function itemMatchesActiveFilters(item) {
  const typeMatch = activeType === "All" || item.type === activeType;
  const ratioMatch = itemMatchesRatioFilter(item);
  const savedMatch = !showSavedOnly || lightboxWorkIds.has(item.id);
  return savedMatch && typeMatch && ratioMatch && itemMatchesSearch(item);
}

function markOrderChanged(message = "Order changed.") {
  hasOrderChanges = true;
  announceArrange(message);
  updateArrangeControls();
}

function applyFilteredOrder(nextFilteredIds, message) {
  const itemById = new Map(orderedItems().map((item) => [item.id, item]));
  const reorderedFilteredItems = nextFilteredIds.map((id) => itemById.get(id)).filter(Boolean);
  let filteredCursor = 0;
  const nextItems = orderedItems().map((item) => {
    if (!itemMatchesActiveFilters(item)) {
      return item;
    }

    const nextItem = reorderedFilteredItems[filteredCursor] || item;
    filteredCursor += 1;
    return nextItem;
  });

  normalizeSortOrders(nextItems);
  markOrderChanged(message);
  renderGallery();
}

function moveArchiveItem(sourceId, targetId, placement = "before") {
  if (!sourceId || !targetId || sourceId === targetId) {
    return;
  }

  const currentIds = filteredItems().map((item) => item.id);
  if (!currentIds.includes(sourceId) || !currentIds.includes(targetId)) {
    return;
  }

  const nextIds = currentIds.filter((id) => id !== sourceId);
  let insertionIndex = nextIds.indexOf(targetId);
  if (placement === "after") {
    insertionIndex += 1;
  }

  nextIds.splice(insertionIndex, 0, sourceId);
  const movedItem = archiveItems.find((item) => item.id === sourceId);
  const targetItem = archiveItems.find((item) => item.id === targetId);
  applyFilteredOrder(nextIds, `Moved ${movedItem?.title || "work"} ${placement} ${targetItem?.title || "selected work"}.`);
}

function moveArchiveItemByOffset(itemId, offset) {
  const currentIds = filteredItems().map((item) => item.id);
  const currentIndex = currentIds.indexOf(itemId);
  const nextIndex = currentIndex + offset;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= currentIds.length) {
    return;
  }

  const nextIds = [...currentIds];
  const [movedId] = nextIds.splice(currentIndex, 1);
  nextIds.splice(nextIndex, 0, movedId);
  const movedItem = archiveItems.find((item) => item.id === itemId);
  applyFilteredOrder(nextIds, `Moved ${movedItem?.title || "work"} ${offset < 0 ? "earlier" : "later"}.`);
}

function updateArrangeControls() {
  gallery.classList.toggle("is-arranging", isArrangeMode);
  if (arrangeToggle) {
    arrangeToggle.hidden = isArrangeMode;
  }
  if (saveOrderButton) {
    saveOrderButton.hidden = !isArrangeMode;
    saveOrderButton.disabled = !hasOrderChanges;
  }
  if (arrangeDoneButton) {
    arrangeDoneButton.hidden = !isArrangeMode;
  }
  if (arrangeStatus) {
    if (!isArrangeMode) {
      arrangeStatus.textContent = "";
    } else if (hasOrderChanges) {
      arrangeStatus.textContent = "Unsaved order";
    } else if (activeType !== "All" || activeRatio !== "All" || activeSearch) {
      arrangeStatus.textContent = "Arranging current view";
    } else {
      arrangeStatus.textContent = "Arrange mode";
    }
  }
}

function clearDropMarkers() {
  gallery.querySelectorAll(".is-drop-before, .is-drop-after").forEach((item) => {
    item.classList.remove("is-drop-before", "is-drop-after");
  });
}

async function persistStoredSortOrders() {
  if (!archiveDb) {
    return;
  }

  const storedItems = await getStoredItems();
  const sortOrderById = new Map(archiveItems.map((item) => [item.id, item.sortOrder]));
  await Promise.all(
    storedItems.map(
      (item) =>
        new Promise((resolve, reject) => {
          if (!sortOrderById.has(item.id)) {
            resolve();
            return;
          }

          const request = transactionStore("readwrite").put({
            ...item,
            sortOrder: sortOrderById.get(item.id),
          });
          request.onsuccess = () => resolve();
          request.onerror = () => reject(request.error);
        }),
    ),
  );
}

async function saveCurrentOrder() {
  normalizeSortOrders();
  writeSavedOrder(orderedItems().map((item) => item.id));
  await persistStoredSortOrders();
  hasOrderChanges = false;
  announceArrange("Order saved.");
  updateArrangeControls();
}

function viewerItems() {
  return filteredItems();
}

function setViewerSequence(items) {
  viewerSequenceIds = items.map((item) => item.id);
}

function viewerSequenceItems() {
  const itemsById = new Map(
    orderedItems()
      .filter((item) => isPublishedArchiveItem(item) && item.src)
      .map((item) => [item.id, item]),
  );
  return viewerSequenceIds.map((id) => itemsById.get(id)).filter(Boolean);
}

function currentViewerIndex(items = viewerItems()) {
  return items.findIndex((item) => item.id === viewerCurrentId);
}

function metadataTerm(label, value) {
  const text = cleanText(value);
  if (!text) {
    return "";
  }

  return `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(text)}</dd>
    </div>
  `;
}

function renderViewerTags(groups = []) {
  if (!viewerTagsSection || !viewerTags) {
    return;
  }

  const visibleGroups = normalizeTagGroups(groups);
  if (!visibleGroups.length) {
    viewerTagsSection.hidden = true;
    viewerTags.innerHTML = "";
    return;
  }

  viewerTagsSection.hidden = false;
  viewerTags.innerHTML = visibleGroups
    .map(
      (group) => `
        <div class="work-viewer-tag-group">
          <p>${escapeHtml(group.label)}</p>
          <div class="work-viewer-tag-list">
            ${group.tags.map((tag) => `<span class="work-viewer-tag">${escapeHtml(tag)}</span>`).join("")}
          </div>
        </div>
      `,
    )
    .join("");
}

function flatGroupTags(groups = []) {
  return normalizeTagGroups(groups).flatMap((group) => group.tags.map((tag) => cleanText(tag).toLowerCase()).filter(Boolean));
}

function relatedWorksFor(item, detail, limit = 4) {
  const currentTags = new Set(flatGroupTags(detail.tagGroups));
  return orderedItems()
    .filter((candidate) => candidate.id !== item.id && isPublishedArchiveItem(candidate) && candidate.src)
    .map((candidate) => {
      const candidateDetail = normalizeWorkDetail(candidate);
      const candidateTags = flatGroupTags(candidateDetail.tagGroups);
      const tagScore = candidateTags.reduce((score, tag) => score + (currentTags.has(tag) ? 1 : 0), 0);
      const score =
        (candidate.type === item.type ? 4 : 0) +
        (candidate.ratio === item.ratio ? 3 : 0) +
        (cleanText(candidate.series) && cleanText(candidate.series) === cleanText(item.series) ? 3 : 0) +
        tagScore;
      return { candidate, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || (a.candidate.sortOrder || 0) - (b.candidate.sortOrder || 0))
    .slice(0, limit)
    .map((entry) => entry.candidate);
}

function renderViewerRelated(item, detail) {
  if (!viewerRelatedSection || !viewerRelated) {
    return;
  }
  const related = relatedWorksFor(item, detail);
  if (!related.length) {
    viewerRelatedSection.hidden = true;
    viewerRelated.innerHTML = "";
    return;
  }
  viewerRelatedSection.hidden = false;
  viewerRelated.innerHTML = related
    .map(
      (work) => `
        <button class="work-viewer-related-item" type="button" data-related-work-id="${escapeHtml(work.id)}">
          <img src="${escapeHtml(work.src)}" alt="" loading="lazy" decoding="async" />
          <span>
            <strong>${escapeHtml(work.title)}</strong>
            <small>${escapeHtml(work.type)} / ${escapeHtml(work.ratio)}</small>
          </span>
        </button>
      `,
    )
    .join("");
}

function updateViewerActionStates(itemId) {
  workViewerDialog?.querySelectorAll("[data-viewer-action]").forEach((button) => {
    const action = button.dataset.viewerAction;
    const active = action === "lightbox" && lightboxWorkIds.has(itemId);
    button.classList.toggle("is-active", active);
    if (action === "lightbox") {
      const command = active ? "Remove from Lightbox" : "Add to Lightbox";
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("aria-label", command);
      button.dataset.tooltip = command;
      const label = button.querySelector("span");
      if (label) {
        label.textContent = command;
      }
    }
  });
}

function renderViewerCreator(item) {
  if (!viewerCreator) {
    return;
  }
  const creator = item?.creator;
  const slug = cleanText(creator?.slug);
  const displayName = cleanText(creator?.displayName || creator?.display_name);
  viewerCreator.replaceChildren();
  if (!slug || !displayName) {
    viewerCreator.hidden = true;
    return;
  }
  const prefix = document.createElement("span");
  prefix.textContent = "By ";
  const link = document.createElement("a");
  link.href = `/creators/${encodeURIComponent(slug)}`;
  link.textContent = displayName;
  link.setAttribute("aria-label", `Open ${displayName}'s public profile`);
  viewerCreator.append(prefix, link);
  viewerCreator.hidden = false;
}

function setViewerZoom(zoomed) {
  isViewerZoomed = Boolean(zoomed);
  workViewerDialog?.classList.toggle("is-zoomed", isViewerZoomed);
  if (viewerZoomButton) {
    const label = isViewerZoomed ? "Fit image to screen" : "View actual size";
    viewerZoomButton.setAttribute("aria-label", label);
    viewerZoomButton.dataset.tooltip = isViewerZoomed ? "Fit to window" : "View actual size";
    viewerZoomButton.setAttribute("aria-pressed", String(isViewerZoomed));
    const useElement = viewerZoomButton.querySelector("use");
    if (useElement) {
      useElement.setAttribute("href", `#icon-${isViewerZoomed ? "zoom-out" : "zoom-in"}`);
    }
  }
  if (viewerMode) {
    viewerMode.textContent = isViewerZoomed ? "Actual size" : "Fit";
  }
  window.requestAnimationFrame(() => {
    if (!viewerStage) return;
    if (isViewerZoomed) {
      viewerStage.scrollLeft = Math.max(0, (viewerStage.scrollWidth - viewerStage.clientWidth) / 2);
      viewerStage.scrollTop = Math.max(0, (viewerStage.scrollHeight - viewerStage.clientHeight) / 2);
    } else {
      viewerStage.scrollTo(0, 0);
    }
  });
}

function setViewerInfoOpen(open) {
  const isOpen = Boolean(open);
  workViewerDialog?.classList.toggle("is-info-open", isOpen);
  if (viewerInfoButton) {
    const label = isOpen ? "Hide work details" : "Show work details";
    viewerInfoButton.setAttribute("aria-label", label);
    viewerInfoButton.dataset.tooltip = isOpen ? "Hide details" : "Show details";
    viewerInfoButton.setAttribute("aria-expanded", String(isOpen));
    viewerInfoButton.classList.toggle("is-active", isOpen);
  }
  if (viewerInfoPanel) {
    if (!isOpen && viewerInfoPanel.contains(document.activeElement)) {
      viewerInfoButton?.focus({ preventScroll: true });
    }
    viewerInfoPanel.setAttribute("aria-hidden", String(!isOpen));
    viewerInfoPanel.toggleAttribute("inert", !isOpen);
  }
}

function renderWorkViewer(item, index, items, { resetView = false } = {}) {
  const detail = normalizeWorkDetail(item);
  setViewerZoom(false);
  if (resetView) {
    setViewerInfoOpen(false);
  }
  if (workViewerDialog) {
    workViewerDialog.dataset.displayMode = detail.displayMode;
    workViewerDialog.dataset.workType = detail.type;
  }
  if (viewerDialogLabel) {
    viewerDialogLabel.textContent = `${detail.title} work viewer`;
  }
  if (viewerImage) {
    viewerImage.src = detail.imageUrl;
    viewerImage.alt = detail.altText;
  }
  if (viewerTitle) {
    viewerTitle.textContent = detail.title;
  }
  if (viewerNote) {
    viewerNote.textContent = detail.note;
  }
  renderViewerCreator(item);
  if (viewerMetadata) {
    viewerMetadata.innerHTML = [
      metadataTerm("Type", detail.typeLabel),
      metadataTerm("Ratio", detail.ratioLabel),
      metadataTerm("Size", `${detail.originalWidth || "Unknown"} x ${detail.originalHeight || "Unknown"}`),
      metadataTerm("Captured", detail.capturedLabel),
    ].join("");
  }
  renderViewerTags(detail.tagGroups);
  if (viewerStatementSection && viewerStatement && viewerStatementHeading) {
    if (detail.statement) {
      viewerStatementSection.hidden = false;
      viewerStatementHeading.textContent = detail.statement === detail.note ? "Description" : "Artist Statement";
      viewerStatement.textContent = detail.statement;
    } else {
      viewerStatementSection.hidden = true;
      viewerStatement.textContent = "";
    }
  }
  if (viewerPosition) {
    viewerPosition.textContent = `${index + 1} / ${items.length}`;
  }
  updateViewerActionStates(item.id);
  if (viewerInquireLink) {
    viewerInquireLink.href = `contact.html?source=work&work=${encodeURIComponent(item.id)}`;
  }
  renderViewerRelated(item, detail);
  if (viewerPrevButton) {
    viewerPrevButton.disabled = items.length <= 1;
  }
  if (viewerNextButton) {
    viewerNextButton.disabled = items.length <= 1;
  }
}

function lockViewerScroll() {
  if (document.body.classList.contains("is-work-viewer-open")) {
    return;
  }

  viewerScrollY = window.scrollY || document.documentElement.scrollTop || 0;
  viewerOriginalBodyOverflow = document.body.style.overflow;
  viewerOriginalHtmlOverflow = document.documentElement.style.overflow;
  viewerOriginalBodyPaddingRight = document.body.style.paddingRight;
  const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

  document.body.classList.add("is-work-viewer-open");
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
  if (scrollbarWidth > 0) {
    document.body.style.paddingRight = `${scrollbarWidth}px`;
  }
}

function unlockViewerScroll() {
  document.body.classList.remove("is-work-viewer-open");
  document.body.style.overflow = viewerOriginalBodyOverflow;
  document.documentElement.style.overflow = viewerOriginalHtmlOverflow;
  document.body.style.paddingRight = viewerOriginalBodyPaddingRight;
  if (Math.abs((window.scrollY || document.documentElement.scrollTop || 0) - viewerScrollY) > 2) {
    window.scrollTo(0, viewerScrollY);
  }
}

function openWorkViewer(itemId, triggerElement = null) {
  if (!workViewer || !workViewerDialog || isArrangeMode) {
    return;
  }

  const items = viewerItems();
  const index = items.findIndex((item) => item.id === itemId);
  if (index < 0) {
    return;
  }

  clearTimeout(viewerCloseTimer);
  viewerCurrentId = itemId;
  setViewerSequence(items);
  viewerTriggerElement =
    triggerElement || Array.from(gallery.querySelectorAll("[data-item-id]")).find((element) => element.dataset.itemId === itemId);
  renderWorkViewer(items[index], index, items, { resetView: true });
  replaceArchiveUrl({ work: itemId });

  if (workViewer.hidden) {
    workViewer.hidden = false;
    lockViewerScroll();
    window.requestAnimationFrame(() => {
      workViewer.classList.add("is-open");
      workViewerDialog.focus({ preventScroll: true });
    });
  } else {
    workViewer.classList.add("is-open");
    workViewerDialog.focus({ preventScroll: true });
  }
}

function closeWorkViewer({ restoreFocus = true } = {}) {
  if (!workViewer || workViewer.hidden) {
    return;
  }

  workViewer.classList.remove("is-open");
  replaceArchiveUrl({ work: "" });
  clearTimeout(viewerCloseTimer);
  const finishClose = () => {
    const focusTarget = viewerTriggerElement?.isConnected
      ? viewerTriggerElement
      : Array.from(gallery.querySelectorAll("[data-item-id]")).find((element) => element.dataset.itemId === viewerCurrentId);
    workViewer.hidden = true;
    viewerCurrentId = null;
    viewerSequenceIds = [];
    if (viewerImage) {
      viewerImage.removeAttribute("src");
      viewerImage.alt = "";
    }
    unlockViewerScroll();
    if (restoreFocus && focusTarget?.isConnected) {
      focusTarget.focus({ preventScroll: true });
    }
    viewerTriggerElement = null;
  };

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  viewerCloseTimer = window.setTimeout(finishClose, reducedMotion ? 0 : 260);
}

function moveViewer(direction) {
  if (!workViewer || workViewer.hidden || !viewerCurrentId) {
    return;
  }

  let items = viewerSequenceItems();
  if (!items.length) {
    items = viewerItems();
    setViewerSequence(items);
  }
  if (items.length <= 1) {
    return;
  }

  const currentIndex = currentViewerIndex(items);
  if (currentIndex < 0) {
    return;
  }

  const nextIndex = (currentIndex + direction + items.length) % items.length;
  viewerCurrentId = items[nextIndex].id;
  renderWorkViewer(items[nextIndex], nextIndex, items);
  replaceArchiveUrl({ work: viewerCurrentId });
}

function isInteractiveTarget(target) {
  return Boolean(target.closest("button, a, input, textarea, select, label, [draggable='true']"));
}

function focusableViewerElements() {
  if (!workViewerDialog) {
    return [];
  }

  return Array.from(
    workViewerDialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("hidden") && !element.closest('[aria-hidden="true"]') && element.offsetParent !== null);
}

function trapViewerFocus(event) {
  if (event.key !== "Tab" || !workViewer || workViewer.hidden) {
    return;
  }

  const focusable = focusableViewerElements();
  if (!focusable.length) {
    event.preventDefault();
    workViewerDialog.focus({ preventScroll: true });
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (document.activeElement === workViewerDialog) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function updateSavedFilterButton() {
  if (savedFilterButton) {
    savedFilterButton.classList.toggle("is-active", showSavedOnly);
    savedFilterButton.setAttribute("aria-pressed", String(showSavedOnly));
    savedFilterButton.setAttribute(
      "aria-label",
      showSavedOnly ? `Showing ${lightboxWorkIds.size} lightbox works` : `Lightbox works, ${lightboxWorkIds.size} saved`,
    );
  }
  if (lightboxCount) {
    lightboxCount.textContent = String(lightboxWorkIds.size);
  }
}

function archiveCardForWork(id) {
  return Array.from(gallery.querySelectorAll("[data-item-id]")).find((item) => item.dataset.itemId === id) || null;
}

function setLightboxButtonState(button, active) {
  if (!button) {
    return;
  }
  const isCardAction = button.matches('[data-card-action="lightbox"]');
  const command = active ? "Remove from Lightbox" : "Add to Lightbox";
  button.classList.toggle("is-active", active);
  button.setAttribute("aria-pressed", String(active));
  button.setAttribute("aria-label", command);
  button.dataset.tooltip = command;
  if (!isCardAction) {
    const label = button.querySelector("span");
    if (label) {
      label.textContent = command;
    }
  }
}

function lightboxButtonsForWork(id) {
  const buttons = [];
  const cardButton = archiveCardForWork(id)?.querySelector('[data-card-action="lightbox"]');
  if (cardButton) {
    buttons.push(cardButton);
  }
  if (viewerCurrentId === id) {
    const viewerButton = workViewerDialog?.querySelector('[data-viewer-action="lightbox"]');
    if (viewerButton) {
      buttons.push(viewerButton);
    }
  }
  return buttons;
}

function setLightboxPendingState(id, pending) {
  lightboxButtonsForWork(id).forEach((button) => {
    if (pending) {
      button.setAttribute("aria-busy", "true");
      button.setAttribute("aria-disabled", "true");
    } else {
      button.removeAttribute("aria-busy");
      button.removeAttribute("aria-disabled");
    }
  });
}

function cancelBookmarkAnimation(button) {
  button?.querySelector(".ui-icon")?.classList.remove("is-bookmark-popping");
}

function animateBookmarkButton(button) {
  const icon = button?.querySelector(".ui-icon");
  if (!icon || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }
  icon.classList.remove("is-bookmark-popping");
  void icon.offsetWidth;
  icon.classList.add("is-bookmark-popping");
  icon.addEventListener("animationend", () => icon.classList.remove("is-bookmark-popping"), { once: true });
}

function updateSavedGallerySummary() {
  if (!showSavedOnly) {
    return;
  }
  const visibleCount = gallery.querySelectorAll(":scope > [data-item-id]").length;
  const filterParts = [];
  if (activeType !== "All") {
    filterParts.push(activeType);
  }
  if (activeRatio !== "All") {
    filterParts.push(activeRatio);
  }
  if (activeSearch) {
    filterParts.push(`"${activeSearch}"`);
  }
  filterParts.push("Saved");
  count.textContent = `${visibleCount} of ${archiveItems.length} work${archiveItems.length === 1 ? "" : "s"} / ${filterParts.join(" + ")}`;
  if (emptyState) {
    emptyState.textContent = "No saved works match this view.";
    emptyState.hidden = visibleCount > 0;
  }
}

function patchLightboxWorkState(id, active, { removeFromSavedView = true } = {}) {
  const card = archiveCardForWork(id);
  if (card) {
    card.dataset.lightbox = String(active);
    setLightboxButtonState(card.querySelector('[data-card-action="lightbox"]'), active);
    if (showSavedOnly && !active && removeFromSavedView) {
      const focusWasInside = card.contains(document.activeElement);
      const focusTarget = card.nextElementSibling?.querySelector?.('[data-card-action="lightbox"]')
        || card.previousElementSibling?.querySelector?.('[data-card-action="lightbox"]')
        || savedFilterButton;
      card.remove();
      if (focusWasInside) {
        focusTarget?.focus({ preventScroll: true });
      }
    }
  }
  if (viewerCurrentId === id) {
    updateViewerActionStates(id);
  }
}

function reconcileLightboxWorkIds(ids, { changedId = "" } = {}) {
  const previousIds = lightboxWorkIds;
  const nextIds = new Set(Array.isArray(ids) ? ids : []);
  const changedIds = new Set(changedId ? [changedId] : []);
  previousIds.forEach((id) => {
    if (!nextIds.has(id)) {
      changedIds.add(id);
    }
  });
  nextIds.forEach((id) => {
    if (!previousIds.has(id)) {
      changedIds.add(id);
    }
  });
  lightboxWorkIds = nextIds;
  changedIds.forEach((id) => patchLightboxWorkState(id, nextIds.has(id)));
  updateSavedFilterButton();
  updateSavedGallerySummary();
  if (viewerCurrentId) {
    updateViewerActionStates(viewerCurrentId);
  }
}

function releaseLightboxPendingState(id, immediate = false) {
  window.clearTimeout(pendingLightboxTimers.get(id));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const release = () => {
    pendingLightboxTimers.delete(id);
    pendingLightboxWorkIds.delete(id);
    setLightboxPendingState(id, false);
  };
  if (immediate || reducedMotion) {
    release();
    return;
  }
  pendingLightboxTimers.set(id, window.setTimeout(release, 240));
}

function toggleLightboxWork(id, { sourceButton = null } = {}) {
  if (!id) {
    return false;
  }
  if (pendingLightboxWorkIds.has(id)) {
    return lightboxWorkIds.has(id);
  }

  const wasAdded = lightboxWorkIds.has(id);
  const optimisticIds = new Set(lightboxWorkIds);
  if (wasAdded) {
    optimisticIds.delete(id);
  } else {
    optimisticIds.add(id);
  }
  const optimisticAdded = !wasAdded;
  pendingLightboxWorkIds.add(id);
  lightboxWorkIds = optimisticIds;
  patchLightboxWorkState(id, optimisticAdded, { removeFromSavedView: false });
  updateSavedFilterButton();
  setLightboxPendingState(id, true);
  if (optimisticAdded) {
    animateBookmarkButton(sourceButton);
  }

  try {
    const result = publicArchive.toggleLightboxId(id);
    reconcileLightboxWorkIds(result.ids, { changedId: id });
    showArchiveToast(result.added ? "Saved to Lightbox" : "Removed from Lightbox");
    releaseLightboxPendingState(id);
    return result.added;
  } catch {
    const rollbackIds = new Set(lightboxWorkIds);
    if (wasAdded) {
      rollbackIds.add(id);
    } else {
      rollbackIds.delete(id);
    }
    lightboxWorkIds = rollbackIds;
    cancelBookmarkAnimation(sourceButton);
    patchLightboxWorkState(id, wasAdded, { removeFromSavedView: false });
    updateSavedFilterButton();
    showArchiveToast("Unable to update your lightbox. Your previous selection was restored.", "error");
    releaseLightboxPendingState(id, true);
    return wasAdded;
  }
}

function downloadWork(item) {
  if (!item?.src) {
    showArchiveToast("This work does not have a downloadable image.", "error");
    return;
  }
  const link = document.createElement("a");
  link.href = item.src;
  link.download = `${slugify(item.title || item.id || "mt-presence-work", "mt-presence-work")}.jpg`;
  document.body.append(link);
  link.click();
  link.remove();
  showArchiveToast("Download started.");
}

function handleWorkAction(action, itemId, { sourceButton = null } = {}) {
  const item = archiveItems.find((entry) => entry.id === itemId);
  if (!item) {
    return;
  }
  if (action === "lightbox") {
    toggleLightboxWork(itemId, { sourceButton });
    return;
  }
  if (action === "download") {
    downloadWork(item);
  }
}

function renderGallery() {
  gallery.setAttribute("aria-busy", "true");
  const items = filteredItems();
  const total = archiveItems.length;
  const filterParts = [];
  if (activeType !== "All") {
    filterParts.push(activeType);
  }
  if (activeRatio !== "All") {
    filterParts.push(activeRatio);
  }
  if (activeSearch) {
    filterParts.push(`"${activeSearch}"`);
  }
  if (showSavedOnly) {
    filterParts.push("Saved");
  }
  count.textContent = `${items.length} of ${total} work${total === 1 ? "" : "s"}${filterParts.length ? ` / ${filterParts.join(" + ")}` : ""}`;
  gallery.classList.toggle("is-ratio-filtered", activeRatio !== "All");
  gallery.classList.toggle("is-arranging", isArrangeMode);
  gallery.dataset.activeRatio = activeRatio;
  if (clearSearchButton) {
    clearSearchButton.hidden = !activeSearch;
  }
  if (searchInput && searchInput.value !== activeSearch) {
    searchInput.value = activeSearch;
  }
  if (emptyState) {
    emptyState.textContent = total === 0
      ? "The archive is being prepared. New work will appear here soon."
      : showSavedOnly
        ? "No saved works match this view."
        : "No works match this search.";
    emptyState.hidden = items.length > 0;
  }
  updateSavedFilterButton();

  gallery.innerHTML = items
    .map((item, index) => {
      const typeLabel = escapeHtml(item.type || "Work");
      const ratioLabel = escapeHtml(item.ratio || "");
      const isInLightbox = lightboxWorkIds.has(item.id);
      return `
        <article
          class="archive-item"
          style="--item-delay: ${Math.min(index, 14) * 24}ms;"
          data-item-id="${escapeHtml(item.id)}"
          data-type="${escapeHtml(item.type)}"
          data-ratio="${escapeHtml(item.ratio)}"
          data-lightbox="${String(isInLightbox)}"
          ${isArrangeMode ? 'draggable="true"' : 'role="button" tabindex="0" aria-label="Open work viewer for ' + escapeHtml(item.title) + '"'}
        >
          ${
            isArrangeMode
              ? `
                <div class="archive-arrange-panel">
                  <button class="archive-icon-button archive-drag-handle" type="button" aria-label="Drag ${escapeHtml(item.title)} to arrange" data-tooltip="Drag">
                    ${iconSvg("grip")}
                  </button>
                  <span class="archive-order-number">${index + 1}</span>
                  <button class="archive-icon-button archive-move-button" type="button" data-move-offset="-1" aria-label="Move ${escapeHtml(item.title)} earlier" data-tooltip="Move earlier">
                    ${iconSvg("arrow-up")}
                  </button>
                  <button class="archive-icon-button archive-move-button" type="button" data-move-offset="1" aria-label="Move ${escapeHtml(item.title)} later" data-tooltip="Move later">
                    ${iconSvg("arrow-down")}
                  </button>
                </div>
              `
              : ""
          }
          <figure class="archive-image-frame" style="--display-ratio: ${ratioCssValue(item.ratio)};">
            <img src="${escapeHtml(item.src)}" alt="${escapeHtml(item.alt_text || item.title)}" loading="lazy" decoding="async" />
            ${
              isArrangeMode
                ? ""
                : `
                  <div class="archive-hover-layer">
                    <div class="archive-hover-brand">MT</div>
                    <div class="archive-hover-actions">
                      <button class="archive-hover-icon ${isInLightbox ? "is-active" : ""}" type="button" data-card-action="lightbox" aria-pressed="${String(isInLightbox)}" aria-label="${isInLightbox ? "Remove from Lightbox" : "Add to Lightbox"}" data-tooltip="${isInLightbox ? "Remove from Lightbox" : "Add to Lightbox"}">
                        ${iconSvg("bookmark")}
                      </button>
                      <button class="archive-hover-icon" type="button" data-card-action="download" aria-label="Download display image" data-tooltip="Download">
                        ${iconSvg("download")}
                      </button>
                    </div>
                  </div>
                `
            }
          </figure>
          <div class="archive-item-meta">
            <h3>${escapeHtml(item.title)}</h3>
            <dl>
              <div>
                <dt>Type</dt>
                <dd>${typeLabel}</dd>
              </div>
              <div>
                <dt>Ratio</dt>
                <dd>${ratioLabel}</dd>
              </div>
            </dl>
          </div>
        </article>
      `;
    })
    .join("");
  window.requestAnimationFrame(() => {
    gallery.setAttribute("aria-busy", "false");
  });
  updateArrangeControls();
}

function setActiveButton(container, selector, value) {
  container.querySelectorAll("button").forEach((button) => {
    const isActive = button.matches(`[${selector}="${value}"]`);
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

typeFilters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter-type]");
  if (!button) {
    return;
  }

  activeType = button.dataset.filterType;
  setActiveButton(typeFilters, "data-filter-type", activeType);
  replaceArchiveUrl({ type: activeType === "All" ? "" : activeType.toLowerCase() });
  renderGallery();
});

ratioFilters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter-ratio]");
  if (!button) {
    return;
  }

  activeRatio = activeRatio === button.dataset.filterRatio ? "All" : button.dataset.filterRatio;
  setActiveButton(ratioFilters, "data-filter-ratio", activeRatio);
  replaceArchiveUrl({ ratio: activeRatio === "All" ? "" : activeRatio });
  renderGallery();
});

window.addEventListener("mt:global-search-change", (event) => {
  activeSearch = cleanText(event.detail?.query);
  replaceArchiveUrl({ q: activeSearch });
  renderGallery();
});

clearSearchButton?.addEventListener("click", () => {
  activeSearch = "";
  if (searchInput) {
    searchInput.value = "";
    searchInput.focus();
  }
  replaceArchiveUrl({ q: "" });
  renderGallery();
});

arrangeToggle?.addEventListener("click", () => {
  isArrangeMode = true;
  announceArrange("Arrange mode enabled.");
  renderGallery();
});

arrangeDoneButton?.addEventListener("click", () => {
  isArrangeMode = false;
  draggedArchiveItemId = null;
  clearDropMarkers();
  announceArrange("Arrange mode closed.");
  renderGallery();
});

saveOrderButton?.addEventListener("click", async () => {
  saveOrderButton.disabled = true;
  setButtonLabel(saveOrderButton, "Saving");

  try {
    await saveCurrentOrder();
    setButtonLabel(saveOrderButton, "Save Order");
  } catch {
    hasOrderChanges = true;
    setButtonLabel(saveOrderButton, "Save Order");
    announceArrange("Unable to save order.");
    updateArrangeControls();
  }
});

savedFilterButton?.addEventListener("click", () => {
  showSavedOnly = !showSavedOnly;
  showArchiveToast(showSavedOnly ? "Showing lightbox works." : "Showing all works.");
  renderGallery();
});

downloadVisibleButton?.addEventListener("click", () => {
  const [firstVisible] = filteredItems();
  if (!firstVisible) {
    showArchiveToast("No visible work is available to download.", "error");
    return;
  }
  downloadWork(firstVisible);
});

gallery.addEventListener("click", (event) => {
  if (isArrangeMode) {
    const moveButton = event.target.closest("[data-move-offset]");
    if (!moveButton) {
      return;
    }

    const item = moveButton.closest("[data-item-id]");
    moveArchiveItemByOffset(item?.dataset.itemId, Number(moveButton.dataset.moveOffset));
    return;
  }

  const actionButton = event.target.closest("[data-card-action]");
  if (actionButton) {
    event.preventDefault();
    event.stopPropagation();
    const item = actionButton.closest("[data-item-id]");
    handleWorkAction(actionButton.dataset.cardAction, item?.dataset.itemId, { sourceButton: actionButton });
    return;
  }

  if (isInteractiveTarget(event.target)) {
    return;
  }

  const item = event.target.closest("[data-item-id]");
  if (item) {
    openWorkViewer(item.dataset.itemId, item);
  }
});

gallery.addEventListener("keydown", (event) => {
  if (isArrangeMode || isInteractiveTarget(event.target) || !["Enter", " "].includes(event.key)) {
    return;
  }

  const item = event.target.closest("[data-item-id]");
  if (!item) {
    return;
  }

  event.preventDefault();
  openWorkViewer(item.dataset.itemId, item);
});

workViewer?.addEventListener("click", (event) => {
  if (event.target.closest("[data-viewer-close]")) {
    closeWorkViewer();
    return;
  }

  const actionButton = event.target.closest("[data-viewer-action]");
  if (actionButton && viewerCurrentId) {
    event.preventDefault();
    event.stopPropagation();
    handleWorkAction(actionButton.dataset.viewerAction, viewerCurrentId, { sourceButton: actionButton });
    updateViewerActionStates(viewerCurrentId);
    return;
  }

  const relatedButton = event.target.closest("[data-related-work-id]");
  if (relatedButton) {
    const nextId = relatedButton.dataset.relatedWorkId;
    let items = viewerSequenceItems();
    const nextIndex = items.findIndex((item) => item.id === nextId);
    if (nextIndex >= 0) {
      viewerCurrentId = nextId;
      renderWorkViewer(items[nextIndex], nextIndex, items);
      replaceArchiveUrl({ work: nextId });
      return;
    }
    items = orderedItems().filter((item) => isPublishedArchiveItem(item) && item.src);
    const allIndex = items.findIndex((item) => item.id === nextId);
    if (allIndex >= 0) {
      setViewerSequence(items);
      viewerCurrentId = nextId;
      renderWorkViewer(items[allIndex], allIndex, items);
      replaceArchiveUrl({ work: nextId });
    }
  }
});

viewerCloseButton?.addEventListener("click", () => closeWorkViewer());
viewerPrevButton?.addEventListener("click", () => moveViewer(-1));
viewerNextButton?.addEventListener("click", () => moveViewer(1));
viewerZoomButton?.addEventListener("click", () => setViewerZoom(!isViewerZoomed));
viewerInfoButton?.addEventListener("click", () => setViewerInfoOpen(!workViewerDialog?.classList.contains("is-info-open")));
viewerImage?.addEventListener("click", () => setViewerInfoOpen(false));

document.addEventListener("keydown", (event) => {
  if (!workViewer || workViewer.hidden) {
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeWorkViewer();
    return;
  }

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    moveViewer(-1);
    return;
  }

  if (event.key === "ArrowRight") {
    event.preventDefault();
    moveViewer(1);
    return;
  }

  if (event.key.toLowerCase() === "i") {
    event.preventDefault();
    setViewerInfoOpen(!workViewerDialog?.classList.contains("is-info-open"));
    return;
  }

  trapViewerFocus(event);
});

gallery.addEventListener("dragstart", (event) => {
  if (!isArrangeMode) {
    event.preventDefault();
    return;
  }

  const item = event.target.closest("[data-item-id]");
  if (!item) {
    return;
  }

  draggedArchiveItemId = item.dataset.itemId;
  item.classList.add("is-dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", draggedArchiveItemId);
});

gallery.addEventListener("dragover", (event) => {
  if (!isArrangeMode || !draggedArchiveItemId) {
    return;
  }

  const item = event.target.closest("[data-item-id]");
  if (!item || item.dataset.itemId === draggedArchiveItemId) {
    return;
  }

  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  clearDropMarkers();
  const rect = item.getBoundingClientRect();
  const placement = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  item.classList.add(placement === "before" ? "is-drop-before" : "is-drop-after");
});

gallery.addEventListener("dragleave", (event) => {
  const item = event.target.closest("[data-item-id]");
  if (item && !item.contains(event.relatedTarget)) {
    item.classList.remove("is-drop-before", "is-drop-after");
  }
});

gallery.addEventListener("drop", (event) => {
  if (!isArrangeMode || !draggedArchiveItemId) {
    return;
  }

  const item = event.target.closest("[data-item-id]");
  if (!item) {
    return;
  }

  event.preventDefault();
  const rect = item.getBoundingClientRect();
  const placement = event.clientY < rect.top + rect.height / 2 ? "before" : "after";
  moveArchiveItem(draggedArchiveItemId, item.dataset.itemId, placement);
  draggedArchiveItemId = null;
  clearDropMarkers();
});

gallery.addEventListener("dragend", () => {
  draggedArchiveItemId = null;
  gallery.querySelectorAll(".is-dragging").forEach((item) => item.classList.remove("is-dragging"));
  clearDropMarkers();
});

async function buildUploadedItem(file, task, index) {
  const imageId = `upload-${Date.now()}-${index}`;
  updateUploadTask(task, "reading", 10, "Reading original file, dimensions, checksum, and metadata.");
  const originalBuffer = await file.arrayBuffer();
  const originalChecksum = await sha256HexFromBuffer(originalBuffer);
  const exif = extractExif(originalBuffer, file.type);
  const imageSource = await createImageSource(file);
  await yieldToMain();

  const ratio = classifyRatio(imageSource.width, imageSource.height);
  const type = await analyzeImageContent(file, imageSource);
  const title = file.name.replace(/\.[^.]+$/, "") || "Uploaded Image";
  const originalAsset = createAsset({
    imageId,
    kind: "original",
    fileName: file.name,
    blob: file,
    width: imageSource.width,
    height: imageSource.height,
    checksum: originalChecksum,
  });
  const assets = [originalAsset];
  let squareSlices = [];
  let fallbackMessage = "";
  let displayAsset = originalAsset;

  if (hasCanvasExportSupport()) {
    updateUploadTask(task, "compressing", 32, "Creating display version for the archive.");
    const candidateDisplayAsset = await createDerivativeAsset({
      imageId,
      kind: "display",
      fileName: file.name,
      imageSource,
      maxLongEdge: DISPLAY_MAX_LONG_EDGE,
      quality: DISPLAY_QUALITY,
      sourceAssetId: originalAsset.id,
    });
    if (candidateDisplayAsset.byte_size < originalAsset.byte_size) {
      displayAsset = candidateDisplayAsset;
      assets.push(candidateDisplayAsset);
    } else if (Math.max(imageSource.width, imageSource.height) > DISPLAY_MAX_LONG_EDGE * DISPLAY_FORCE_RESIZE_RATIO) {
      displayAsset = candidateDisplayAsset;
      assets.push(candidateDisplayAsset);
      fallbackMessage = "Display version is dimension-optimized but not smaller than the original file.";
    } else {
      displayAsset = originalAsset;
      fallbackMessage = "Original is already smaller than the display version. Using original as display fallback.";
    }
    await yieldToMain();

    updateUploadTask(task, "compressing", 50, "Creating thumbnail for fast lists.");
    assets.push(
      await createDerivativeAsset({
        imageId,
        kind: "thumbnail",
        fileName: file.name,
        imageSource,
        maxLongEdge: THUMBNAIL_MAX_LONG_EDGE,
        quality: THUMBNAIL_QUALITY,
        sourceAssetId: originalAsset.id,
      }),
    );
    await yieldToMain();

    updateUploadTask(task, "slicing", 68, "Preparing square archive slices when needed.");
    const sliceResult = await createSquareSlices(imageId, imageSource, file.name, originalAsset.id);
    assets.push(...sliceResult.assets);
    squareSlices = sliceResult.squareSlices;
  } else {
    fallbackMessage = "Browser image compression is unavailable. Original saved and used as fallback.";
  }

  updateUploadTask(task, "analyzing", 78, "Applying local type and ratio classification.");
  await yieldToMain();

  const imageRecord = {
    id: imageId,
    title,
    description: "",
    curatorial_note: "",
    artist_statement: "",
    series: "",
    source_type: "upload",
    original_filename: file.name,
    original_width: imageSource.width,
    original_height: imageSource.height,
    ratio_category_code: ratioCategoryCode(ratio),
    content_type: contentTypeCode(type),
    display_mode: displayModeForType(type),
    exif,
    visibility: "draft",
    visibility_manually_set: false,
    sort_order: 0,
    captured_at: normalizeCapturedDate(exif.datetime_original || exif.datetime),
    tags: [],
    tag_groups: [],
  };

  const item = {
    id: imageId,
    title,
    src: assetObjectUrl(displayAsset),
    width: imageSource.width,
    height: imageSource.height,
    type,
    ratio,
    source: "Uploaded",
    createdAt: Date.now() + index,
    imageRecord,
    assets,
    squareSliceCount: squareSlices.length,
    squareSlices,
  };

  imageSource.close();
  return { item, fallbackMessage };
}

async function processUploadFile(file, task, index) {
  try {
    if (!file.type.startsWith("image/")) {
      throw new Error("Only image files can be imported.");
    }

    const { item, fallbackMessage } = await buildUploadedItem(file, task, index);
    normalizeSortOrders([item, ...orderedItems()]);
    const sortedItem = archiveItems.find((archiveItem) => archiveItem.id === item.id);
    item.sortOrder = sortedItem?.sortOrder ?? 0;

    updateUploadTask(task, "uploading", 88, "Saving local asset records.");
    await saveStoredItem(item);
    writeSavedOrder(orderedItems().map((archiveItem) => archiveItem.id));
    renderGallery();

    updateUploadTask(
      task,
      fallbackMessage ? "warning" : "complete",
      100,
      fallbackMessage || "Display, thumbnail, original, and slice records are ready.",
    );
  } catch (error) {
    updateUploadTask(task, "failed", 100, error?.message || "Unable to import this image.");
  }
}

uploadInput?.addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    return;
  }

  const tasks = files.map(createUploadTask);
  uploadTasks = [...tasks, ...uploadTasks];
  renderUploadTasks();
  uploadInput.disabled = true;

  for (const [index, file] of files.entries()) {
    await processUploadFile(file, tasks[index], index);
  }

  uploadInput.value = "";
  uploadInput.disabled = false;
  renderGallery();
});

async function initArchive() {
  setArchiveDataStatus("Loading archive.", "loading");
  hydrateArchiveUrlState();
  let apiResult = null;
  let apiError = null;

  try {
    apiResult = await fetchArchiveApiItems();
  } catch (error) {
    apiError = error;
    if (apiError && typeof apiError.authoritative !== "boolean") {
      apiError.authoritative = true;
    }
  }

  const authoritative = apiResult?.authoritative === true || apiError?.authoritative === true;
  if (authoritative) {
    archiveDb = null;
    archiveDataSource = apiResult?.source || apiError?.source || "supabase";
    archiveItems = (apiResult?.items || []).filter(isPublishedArchiveItem);
    normalizeSortOrders(archiveItems);
    if (apiError) {
      setArchiveDataStatus(apiError.message || "Published works are temporarily unavailable.", "error");
    } else {
      setArchiveDataStatus(archiveItems.length ? "Published works loaded." : "No published works yet.", "ready");
    }
  } else {
    let storedItems = [];

    try {
      archiveDb = await openArchiveDatabase();
      storedItems = await getStoredItems();
    } catch {
      archiveDb = null;
    }

    let baseItems = sampleItems;
    if (apiResult?.items.length) {
      baseItems = apiResult.items;
      archiveDataSource = "api";
      setArchiveDataStatus("Archive loaded from local SQLite database.", "ready");
    } else if (apiResult) {
      archiveDataSource = "local";
      setArchiveDataStatus("Archive database returned no published works. Showing local samples.", "warning");
    } else {
      archiveDataSource = "local";
      setArchiveDataStatus(`${apiError?.message || "Archive database is unavailable."} Showing local samples.`, "warning");
    }

    if (!archiveDb && archiveDataSource === "api") {
      setArchiveDataStatus("Archive loaded from local SQLite database. Browser edits are unavailable.", "warning");
    }

    const storedById = new Map(storedItems.map((item) => [item.id, item]));
    const baseIds = new Set(baseItems.map((item) => item.id));
    const mergedBaseItems = baseItems.map((item) => mergeStoredWorkDetail(item, storedById.get(item.id)));
    const uploadedItems = storedItems
      .filter((item) => !baseIds.has(item.id) && isStoredUpload(item))
      .map(reviveStoredItem)
      .sort((a, b) => b.createdAt - a.createdAt);

    archiveItems = applySavedSortOrders([...mergedBaseItems, ...uploadedItems].filter(isPublishedArchiveItem));
    normalizeSortOrders();
  }

  setActiveButton(typeFilters, "data-filter-type", activeType);
  setActiveButton(ratioFilters, "data-filter-ratio", activeRatio);
  renderGallery();
  const requestedWorkId = new URLSearchParams(window.location.search).get("work");
  if (requestedWorkId) {
    openWorkViewer(requestedWorkId);
  }
}

window.addEventListener("mt:lightbox-change", (event) => {
  reconcileLightboxWorkIds(event.detail?.ids || publicArchive.readLightboxIds(), {
    changedId: event.detail?.changedId || "",
  });
});

window.addEventListener("storage", (event) => {
  if (event.key !== publicArchive.LIGHTBOX_STORAGE_KEY) {
    return;
  }
  reconcileLightboxWorkIds(publicArchive.readLightboxIds());
});

initArchive();
