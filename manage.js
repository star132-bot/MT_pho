const DB_NAME = "mt-cijian-archive";
const DB_VERSION = 4;
const DB_STORE = "images";
const SETTINGS_STORE = "site_settings";
const ARCHIVE_API_URL = "/api/archive/images";
const LOCAL_STORAGE_BUCKET = "indexeddb-local";
const ORDER_STORAGE_KEY = "mt-cijian-archive-order-v1";
const HOME_SETTINGS_ID = "homepage";
const archiveSeedData = window.MTPresenceArchiveData || {};
const baseArchiveItems = Array.isArray(archiveSeedData.sampleItems) ? archiveSeedData.sampleItems : [];

const listElement = document.querySelector("[data-manage-list]");
const countElement = document.querySelector("[data-manage-count]");
const listStateElement = document.querySelector("[data-list-state]");
const refreshButton = document.querySelector("[data-refresh-records]");
const uploadInput = document.querySelector("[data-upload-input]");
const uploadStatusList = document.querySelector("[data-upload-status-list]");
const emptyElement = document.querySelector("[data-manage-empty]");
const formElement = document.querySelector("[data-manage-form]");
const homeForm = document.querySelector("[data-home-form]");
const homeSaveLabel = document.querySelector("[data-home-save-label]");
const homeLastSaved = document.querySelector("[data-home-last-saved]");
const homeSaveState = document.querySelector("[data-home-save-state]");
const homeMomentsElement = document.querySelector("[data-home-moments]");
const homeSaveButton = document.querySelector("[data-save-home-settings]");
const homeSaveAllButton = document.querySelector("[data-save-all-home-settings]");
const homeRevertButton = document.querySelector("[data-revert-home-settings]");
const homePreviewImages = new Map(
  Array.from(document.querySelectorAll("[data-home-preview]"), (element) => [element.dataset.homePreview, element]),
);
const homePreviewCaptions = new Map(
  Array.from(document.querySelectorAll("[data-home-preview-caption]"), (element) => [element.dataset.homePreviewCaption, element]),
);
const previewImage = document.querySelector("[data-manage-preview]");
const editorTitle = document.querySelector("[data-editor-title]");
const recordSource = document.querySelector("[data-record-source]");
const editorMeta = document.querySelector("[data-editor-meta]");
const recordSchema = document.querySelector("[data-record-schema]");
const editorStatus = document.querySelector("[data-editor-status]");
const saveState = document.querySelector("[data-save-state]");
const errorElement = document.querySelector("[data-manage-error]");
const clearContentButton = document.querySelector("[data-clear-content]");
const deleteImageButton = document.querySelector("[data-delete-image]");
const saveButton = document.querySelector("[data-save-record]");
const saveAllButton = document.querySelector("[data-save-all-records]");
const revertButton = document.querySelector("[data-revert-record]");
const tagGroupsEditor = document.querySelector("[data-tag-groups-editor]");
const liveRegion = document.querySelector("[data-manage-live]");
const confirmDialog = document.querySelector("[data-confirm-dialog]");
const confirmTitle = document.querySelector("[data-confirm-title]");
const confirmMessage = document.querySelector("[data-confirm-message]");
const confirmCancel = document.querySelector("[data-confirm-cancel]");
const confirmSubmit = document.querySelector("[data-confirm-submit]");

let archiveDb = null;
let records = [];
let activeRecordId = null;
let currentConfirm = null;
let isRenderingForm = false;
let isRenderingHomeForm = false;
let uploadTasks = [];
let homeSettings = null;
let savedHomeSettings = null;
let homeSettingsSignature = "";
let isHomeDirty = false;
let lastSavedAt = "";
const dirtyRecordIds = new Set();
const savedRecords = new Map();
const savedSignatures = new Map();
const objectUrls = new Set();
const TAG_GROUP_LABELS = ["Subject", "Place", "Form / Ratio", "Mood", "Material / Surface", "Palette / Tone", "Series / Collection"];

function cleanText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function titleCase(value) {
  return cleanText(value)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function slugify(value, fallback = "tag") {
  const slug = cleanText(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || fallback;
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function numberOrFallback(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

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
    // Editing can continue even if localStorage is unavailable.
  }
}

function applySavedSortOrders(items) {
  const savedOrder = readSavedOrder();
  if (!savedOrder.length) {
    return [...items];
  }

  const savedOrderIndex = new Map(savedOrder.map((id, index) => [id, index]));
  let fallbackIndex = savedOrder.length;
  const withSortOrder = (item, sortOrder) => ({
    ...item,
    sortOrder,
    imageRecord: item.imageRecord
      ? {
          ...item.imageRecord,
          sort_order: sortOrder,
        }
      : item.imageRecord,
  });
  return items.map((item) => {
    if (savedOrderIndex.has(item.id)) {
      return withSortOrder(item, savedOrderIndex.get(item.id));
    }
    if (Number.isFinite(item.sortOrder)) {
      return withSortOrder(item, item.sortOrder);
    }
    const nextItem = withSortOrder(item, fallbackIndex);
    fallbackIndex += 1;
    return nextItem;
  });
}

function sortRecordsCollection(items) {
  return [...items].sort((a, b) => {
    const aOrder = numberOrFallback(a.imageRecord?.sort_order, a.sortOrder || 0);
    const bOrder = numberOrFallback(b.imageRecord?.sort_order, b.sortOrder || 0);
    if (aOrder !== bOrder) {
      return aOrder - bOrder;
    }
    return String(a.title || "").localeCompare(String(b.title || ""));
  });
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
  const value = cleanText(type).toLowerCase();
  return value === "abstract" || value === "black_white" ? "abstract" : "concrete";
}

function contentTypeLabel(code) {
  return contentTypeCode(code) === "abstract" ? "Abstract" : "Concrete";
}

function displayModeForType(type) {
  return contentTypeCode(type) === "abstract" ? "black_white" : "color";
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
  return uniqueTextList(String(parsed).split(/[\n,;|]/));
}

function normalizeTagGroups(groups = []) {
  const byLabel = new Map();
  groups.forEach((group) => {
    const label = cleanText(group?.label || group?.group_name || group?.groupName);
    const tags = uniqueTextList(group?.tags || []);
    if (!label || !tags.length) {
      return;
    }
    const key = label.toLowerCase();
    const existing = byLabel.get(key);
    if (existing) {
      existing.tags = uniqueTextList([...existing.tags, ...tags]);
    } else {
      byLabel.set(key, { label, tags });
    }
  });
  return Array.from(byLabel.values());
}

function normalizeTagGroupList(value) {
  const parsed = parsedTagValue(value);
  const source = Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
  return normalizeTagGroups(
    source
      .filter((group) => group && typeof group === "object")
      .map((group) => ({
        label: group.label || group.group_name || group.groupName || group.name,
        tags: tagsFromValue(group.tags || group.items || group.values),
      })),
  );
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

function deriveTagGroupsForRecord(record) {
  const imageRecord = record.imageRecord || {};
  const title = imageRecord.title || record.title || "";
  const type = contentTypeLabel(imageRecord.content_type || record.type);
  const contentType = contentTypeCode(imageRecord.content_type || record.type);
  const ratioLabel = record.ratio || ratioLabelFromCode(imageRecord.ratio_category_code);
  const width = imageRecord.original_width || record.width;
  const height = imageRecord.original_height || record.height;
  const displayMode = imageRecord.display_mode || record.display_mode || displayModeForType(contentType);
  const subjectTags = [type];
  const placeTags = [];
  const moodTags = [];
  const surfaceTags = [];

  if (contentType === "abstract") {
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
    subjectTags.push(contentType === "abstract" ? "Surface / Pattern" : "Observed World");
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

  return normalizeTagGroups([
    { label: "Subject", tags: subjectTags },
    { label: "Place", tags: placeTags },
    { label: "Form / Ratio", tags: [ratioLabel, orientationTag(ratioLabel, width, height)] },
    { label: "Mood", tags: moodTags.length ? moodTags : ["Quiet Observation"] },
    { label: "Material / Surface", tags: surfaceTags },
    {
      label: "Palette / Tone",
      tags: displayMode === "black_white" || contentType === "abstract" ? ["Black and white", "Monochrome"] : ["Color"],
    },
    { label: "Series / Collection", tags: [record.source || imageRecord.source_type || "Local Sample", `${type} Archive`] },
  ]);
}

function tagGroupsForRecord(record) {
  const imageRecord = record.imageRecord || {};
  const explicitGroups = normalizeTagGroups([
    ...normalizeTagGroupList(record.tag_groups),
    ...normalizeTagGroupList(imageRecord.tag_groups),
  ]);
  if (explicitGroups.length) {
    return explicitGroups;
  }
  const flatTags = uniqueTextList([...tagsFromValue(record.tags), ...tagsFromValue(imageRecord.tags)]);
  if (flatTags.length) {
    return [{ label: "Subject", tags: flatTags }];
  }
  return deriveTagGroupsForRecord(record);
}

function flatTagsFromGroups(groups = []) {
  return uniqueTextList(groups.flatMap((group) => group.tags || []));
}

function tagRowsFromGroups(imageId, groups = []) {
  const rows = [];
  groups.forEach((group, groupIndex) => {
    group.tags.forEach((tagName, tagIndex) => {
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

function visibilityLabel(value) {
  return titleCase(value || "draft");
}

function isUploadRecordShape(item, rawRecord = item?.imageRecord || {}) {
  return item?.source === "Uploaded" || rawRecord.source_type === "upload" || Boolean(item?.blob) || (Array.isArray(item?.assets) && item.assets.length > 0);
}

function effectiveVisibility(item, rawRecord = item?.imageRecord || {}) {
  const visibility = cleanText(rawRecord.visibility || item?.visibility);
  if (visibility === "draft" && isUploadRecordShape(item, rawRecord) && rawRecord.visibility_manually_set !== true) {
    return "published";
  }
  return visibility || (isUploadRecordShape(item, rawRecord) ? "published" : "draft");
}

function nowIso() {
  return new Date().toISOString();
}

function latestIsoValue(values = []) {
  return values
    .map((value) => {
      const time = Date.parse(value);
      return Number.isFinite(time) ? { value, time } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.time - a.time)[0]?.value || "";
}

function formatSavedTime(value) {
  if (!value) {
    return "Not yet";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Not yet";
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function defaultHomepageSettings() {
  return {
    id: HOME_SETTINGS_ID,
    updated_at: nowIso(),
    database_shape: {
      page_settings: "homepage",
      collections: ["homepage-selected"],
      collection_images: [
        { collection_slug: "homepage-selected", role: "hero_abstract", image_id: "", sort_order: 0 },
        { collection_slug: "homepage-selected", role: "hero_concrete", image_id: "", sort_order: 1 },
      ],
    },
    hero: {
      abstract: {
        image_id: "",
        fallback_url: "assets/art/hero-ci-jian.jpg",
        eyebrow: "Abstract Field",
        title: "A Quiet Field for Images",
        statement:
          "Images are not records of the world. They are encounters held in the present space between the artist and the viewer.",
      },
      concrete: {
        image_id: "",
        fallback_url: "assets/art/hero-concrete.jpg",
        eyebrow: "Concrete Field",
        title: "Where Looking Becomes Presence",
        statement: "Light, weather, and distance settle into form. Each photograph opens a quiet place for the viewer to stay.",
      },
    },
    statement: {
      title: "MT Presence",
      moments: [
        {
          image_id: "",
          fallback_url: "assets/art/abstract-02.jpg",
          text:
            "MT Presence is a fine art photography practice by MT, shaped around quiet images, long looking, and the space between abstraction and the visible world.",
        },
        {
          image_id: "",
          fallback_url: "assets/art/concrete-01.jpg",
          text:
            "The work does not treat photography as simple documentation. It uses landscape, weather, surface, and distance to hold a moment before it becomes explanation.",
        },
        {
          image_id: "",
          fallback_url: "assets/art/abstract-03.jpg",
          text: "Each image is made as an encounter: something to return to, collect, live with, and see differently over time.",
        },
        {
          image_id: "",
          fallback_url: "assets/art/concrete-03.jpg",
          text: "Enter the archive and spend time with the work.",
        },
      ],
    },
  };
}

function normalizeHomepageSettings(raw = null) {
  const defaults = defaultHomepageSettings();
  const rawHero = raw?.hero || {};
  const rawStatement = raw?.statement || {};
  const statementMoments = Array.from({ length: 4 }, (_, index) => {
    const defaultMoment = defaults.statement.moments[index];
    const rawMoment = Array.isArray(rawStatement.moments) ? rawStatement.moments[index] : null;
    return {
      image_id: cleanText(rawMoment?.image_id || defaultMoment.image_id),
      fallback_url: cleanText(rawMoment?.fallback_url || defaultMoment.fallback_url),
      text: cleanText(rawMoment?.text || defaultMoment.text),
    };
  });

  return {
    ...defaults,
    ...raw,
    id: HOME_SETTINGS_ID,
    updated_at: raw?.updated_at || defaults.updated_at,
    hero: {
      abstract: {
        ...defaults.hero.abstract,
        ...(rawHero.abstract || {}),
        image_id: cleanText(rawHero.abstract?.image_id || defaults.hero.abstract.image_id),
        eyebrow: cleanText(rawHero.abstract?.eyebrow || defaults.hero.abstract.eyebrow),
        title: cleanText(rawHero.abstract?.title || defaults.hero.abstract.title),
        statement: cleanText(rawHero.abstract?.statement || defaults.hero.abstract.statement),
      },
      concrete: {
        ...defaults.hero.concrete,
        ...(rawHero.concrete || {}),
        image_id: cleanText(rawHero.concrete?.image_id || defaults.hero.concrete.image_id),
        eyebrow: cleanText(rawHero.concrete?.eyebrow || defaults.hero.concrete.eyebrow),
        title: cleanText(rawHero.concrete?.title || defaults.hero.concrete.title),
        statement: cleanText(rawHero.concrete?.statement || defaults.hero.concrete.statement),
      },
    },
    statement: {
      ...defaults.statement,
      ...rawStatement,
      title: cleanText(rawStatement.title || defaults.statement.title),
      moments: statementMoments,
    },
  };
}

function homepageSignature(settings) {
  const normalized = normalizeHomepageSettings(settings);
  return stableStringify({
    hero: normalized.hero,
    statement: normalized.statement,
    database_shape: normalized.database_shape,
  });
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

function formatDateInput(value) {
  const text = cleanText(value);
  if (!text) {
    return "";
  }
  const exifMatch = text.match(/^(\d{4}):(\d{2}):(\d{2})/);
  if (exifMatch) {
    return `${exifMatch[1]}-${exifMatch[2]}-${exifMatch[3]}`;
  }
  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) {
    return date.toISOString().slice(0, 10);
  }
  return text.slice(0, 10);
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
    request.onerror = () => reject(request.error || new Error("Unable to open local archive database."));
  });
}

function transactionStore(mode = "readonly") {
  return archiveDb.transaction(DB_STORE, mode).objectStore(DB_STORE);
}

function settingsStore(mode = "readonly") {
  return archiveDb.transaction(SETTINGS_STORE, mode).objectStore(SETTINGS_STORE);
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

function shouldSyncRecordToArchiveApi(record) {
  return record?.imageRecord?.source_type === "local_sample" || record?.imageRecord?.source_type === "upload";
}

function archiveApiUpdatePayload(record) {
  const imageRecord = record.imageRecord || {};
  const contentType = contentTypeCode(imageRecord.content_type || record.type);
  return {
    title: cleanText(imageRecord.title || record.title),
    description: cleanText(imageRecord.description),
    curatorial_note: cleanText(imageRecord.curatorial_note),
    artist_statement: cleanText(imageRecord.artist_statement),
    series: cleanText(imageRecord.series || record.series),
    captured_at: cleanText(imageRecord.captured_at),
    content_type: contentType,
    display_mode: cleanText(imageRecord.display_mode || displayModeForType(contentType)),
    visibility: cleanText(imageRecord.visibility || "draft"),
    sort_order: numberOrFallback(imageRecord.sort_order, record.sortOrder || 0),
    tag_groups: tagGroupsForRecord(record),
  };
}

function archiveApiCreatePayload(record) {
  const imageRecord = record.imageRecord || {};
  const payload = archiveApiUpdatePayload(record);
  return {
    ...payload,
    id: record.id,
    original_width: imageRecord.original_width || record.width,
    original_height: imageRecord.original_height || record.height,
    ratio_category_code: imageRecord.ratio_category_code || ratioCategoryCode(record.ratio),
    original_filename: imageRecord.original_filename || record.title,
    exif: imageRecord.exif || {},
  };
}

async function syncArchiveApiRecord(record, isNewUpload = false) {
  if (!shouldSyncRecordToArchiveApi(record)) {
    return { synced: false, skipped: true };
  }

  const isUploadRecord = record?.imageRecord?.source_type === "upload";
  const method = isNewUpload && isUploadRecord ? "POST" : "PATCH";
  const url = method === "POST" ? ARCHIVE_API_URL : `${ARCHIVE_API_URL}/${encodeURIComponent(record.id)}`;
  const payload = method === "POST" ? archiveApiCreatePayload(record) : archiveApiUpdatePayload(record);

  const response = await fetch(url, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (response.status === 404 || response.status === 503) {
    let warning = "Saved locally. Local archive database sync unavailable.";
    try {
      const payload = await response.json();
      warning = payload?.hint || payload?.error || warning;
    } catch {
      // Keep the generic warning if the response is not JSON.
    }
    return { synced: false, warning };
  }

  if (response.status === 409 && method === "POST") {
    // Conflict: record already exists, try updating instead
    return syncArchiveApiRecord(record, false);
  }

  if (!response.ok) {
    let message = method === "POST" ? "Unable to create image in local archive database." : "Unable to update local archive database.";
    try {
      const payload = await response.json();
      message = payload?.error || message;
    } catch {
      // Keep the generic message if the response is not JSON.
    }
    throw new Error(message);
  }

  return { synced: true, payload: await response.json() };
}

function deleteStoredItem(id) {
  return new Promise((resolve, reject) => {
    const request = transactionStore("readwrite").delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("Unable to delete local record."));
  });
}

function getHomeSettingsRecord() {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve(null);
      return;
    }
    const request = settingsStore().get(HOME_SETTINGS_ID);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error || new Error("Unable to read homepage settings."));
  });
}

function putHomeSettingsRecord(record) {
  return new Promise((resolve, reject) => {
    const request = settingsStore("readwrite").put(record);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("Unable to save homepage settings."));
  });
}

function createObjectUrl(asset) {
  if (!asset?.blob) {
    return null;
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
  const imageRecord = record.imageRecord || {};
  return (
    publicAssetUrl(preferredAsset(record, ["thumbnail", "display"])) ||
    record.thumbnail_url ||
    imageRecord.thumbnail_url ||
    displayUrl(record)
  );
}

function isUploadedRecord(item) {
  return isUploadRecordShape(item, item?.imageRecord || {});
}

function isBaseRecord(record) {
  return record?.source === "Local sample" || record?.imageRecord?.source_type === "local_sample";
}

function baseAsset(item, kind, index = 0, sourceAssetId = null) {
  return {
    id: `${item.id}-${kind}`,
    image_id: item.id,
    kind,
    storage_bucket: "local-sample",
    storage_path: item.src || "",
    public_url: item.src || "",
    url_expires_at: null,
    mime_type: "image/jpeg",
    byte_size: null,
    width: item.width || 1,
    height: item.height || 1,
    checksum_sha256: null,
    source_asset_id: sourceAssetId,
    sort_order: index,
  };
}

function baseRecordFromArchiveItem(item, index = 0) {
  const contentType = contentTypeCode(item.content_type || item.type);
  const createdAt = createdAtIso(Date.UTC(2026, 5, 6, 0, 0, index));
  const original = baseAsset(item, "original", 0);
  const display = baseAsset(item, "display", 1, original.id);
  const thumbnail = baseAsset(item, "thumbnail", 2, original.id);
  const imageRecord = {
    id: item.id,
    title: item.title || "Untitled Work",
    slug: slugify(item.title, item.id),
    description: "",
    curatorial_note: "",
    artist_statement: "",
    series: "",
    source_type: "local_sample",
    visibility: "published",
    original_filename: item.src || item.title || item.id,
    original_width: item.width || 1,
    original_height: item.height || 1,
    ratio_category_code: ratioCategoryCode(item.ratio),
    display_ratio_override: null,
    content_type: contentType,
    display_mode: displayModeForType(contentType),
    ai_model: null,
    ai_confidence: null,
    ai_analysis: {},
    exif: {},
    sort_order: index,
    captured_at: "",
    uploaded_at: createdAt,
    created_at: createdAt,
    updated_at: createdAt,
    tags: [],
    tag_groups: [],
  };
  const tagGroups = deriveTagGroupsForRecord({
    ...item,
    source: item.source || "Local sample",
    imageRecord,
  });
  const flatTags = flatTagsFromGroups(tagGroups);
  const imageTags = tagRowsFromGroups(item.id, tagGroups);
  imageRecord.tags = flatTags;
  imageRecord.tag_groups = tagGroups;

  return {
    ...item,
    createdAt: Date.UTC(2026, 5, 6, 0, 0, index),
    sortOrder: index,
    image_url: item.src || "",
    thumbnail_url: item.src || "",
    imageRecord,
    assets: [original, display, thumbnail],
    squareSlices: [],
    squareSliceCount: 0,
    tags: flatTags,
    tag_groups: tagGroups,
    imageTags,
    imageTaggings: imageTags.map((tag, tagIndex) => ({
      image_id: item.id,
      tag_id: tag.id,
      sort_order: tagIndex,
    })),
    isSeedRecord: true,
  };
}

function mergeBaseAndStoredRecord(baseRecord, storedRecord) {
  if (!storedRecord) {
    return normalizeRecord(baseRecord);
  }

  const storedImage = storedRecord.imageRecord || {};
  const baseImage = baseRecord.imageRecord || {};
  return normalizeRecord({
    ...baseRecord,
    ...storedRecord,
    src: baseRecord.src,
    width: baseRecord.width,
    height: baseRecord.height,
    ratio: baseRecord.ratio,
    source: baseRecord.source,
    image_url: baseRecord.image_url,
    thumbnail_url: baseRecord.thumbnail_url,
    assets: baseRecord.assets,
    squareSlices: baseRecord.squareSlices,
    squareSliceCount: baseRecord.squareSliceCount,
    imageRecord: {
      ...baseImage,
      ...storedImage,
      id: baseImage.id,
      source_type: "local_sample",
      original_filename: baseImage.original_filename,
      original_width: baseImage.original_width,
      original_height: baseImage.original_height,
      ratio_category_code: baseImage.ratio_category_code,
    },
  });
}

function editableSnapshot(record) {
  const imageRecord = record.imageRecord || {};
  const tagGroups = tagGroupsForRecord(record);
  return {
    title: cleanText(imageRecord.title),
    curatorial_note: cleanText(imageRecord.curatorial_note),
    description: cleanText(imageRecord.description),
    artist_statement: cleanText(imageRecord.artist_statement),
    captured_at: cleanText(imageRecord.captured_at),
    content_type: contentTypeCode(imageRecord.content_type),
    display_mode: cleanText(imageRecord.display_mode || displayModeForType(imageRecord.content_type)),
    visibility: cleanText(imageRecord.visibility || "draft"),
    sort_order: numberOrFallback(imageRecord.sort_order, record.sortOrder || 0),
    tag_groups: tagGroups,
  };
}

function recordSignature(record) {
  return stableStringify(editableSnapshot(record));
}

function cloneRecord(record) {
  const stripped = stripRuntimeUrls(record);
  if (typeof structuredClone === "function") {
    return structuredClone(stripped);
  }
  return JSON.parse(JSON.stringify(stripped));
}

function rememberSavedRecord(record) {
  savedRecords.set(record.id, cloneRecord(record));
  savedSignatures.set(record.id, recordSignature(record));
  dirtyRecordIds.delete(record.id);
}

function updateLastSavedAt(value) {
  if (value) {
    lastSavedAt = value;
  }
  updateHomeActions();
}

function sortedRecordIds() {
  return [...records]
    .sort((a, b) => {
      const aOrder = numberOrFallback(a.imageRecord?.sort_order, a.sortOrder || 0);
      const bOrder = numberOrFallback(b.imageRecord?.sort_order, b.sortOrder || 0);
      return aOrder - bOrder || String(a.id).localeCompare(String(b.id));
    })
    .map((record) => record.id);
}

function updateSavedOrder() {
  writeSavedOrder(sortedRecordIds());
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
  const assets = Array.isArray(item.assets) ? item.assets.map((asset, index) => normalizeAsset(asset, imageId, index)) : [];
  if (!assets.length && item.blob) {
    assets.push(
      normalizeAsset(
        {
          id: `${imageId}-original`,
          kind: "original",
          blob: item.blob,
          mime_type: item.blob.type,
          byte_size: item.blob.size,
          width: item.width || item.imageRecord?.original_width || 1,
          height: item.height || item.imageRecord?.original_height || 1,
        },
        imageId,
      ),
    );
  }
  return assets;
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

function normalizeRecord(item) {
  const imageId = item.imageRecord?.id || item.id;
  const rawRecord = item.imageRecord || {};
  const ratio = item.ratio || item.ratio_label || ratioLabelFromCode(rawRecord.ratio_category_code) || "1:1";
  const contentType = contentTypeCode(rawRecord.content_type || item.content_type || item.type);
  const displayMode = rawRecord.display_mode || item.display_mode || displayModeForType(contentType);
  const originalWidth = rawRecord.original_width || item.original_width || item.width || 1;
  const originalHeight = rawRecord.original_height || item.original_height || item.height || 1;
  const title = cleanText(item.title || rawRecord.title || "Untitled Work") || "Untitled Work";
  const visibility = effectiveVisibility(item, rawRecord);
  const createdAt = item.createdAt || Date.parse(rawRecord.created_at || rawRecord.uploaded_at || "") || Date.now();
  const imageRecord = {
    ...rawRecord,
    id: imageId,
    title,
    slug: rawRecord.slug || slugify(title, imageId),
    description: cleanText(item.description || rawRecord.description),
    curatorial_note: cleanText(item.curatorial_note || rawRecord.curatorial_note),
    artist_statement: cleanText(item.artist_statement || rawRecord.artist_statement),
    series: cleanText(item.series || rawRecord.series),
    source_type: rawRecord.source_type || "upload",
    visibility,
    visibility_manually_set: rawRecord.visibility_manually_set === true,
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
    sort_order: Number.isFinite(rawRecord.sort_order) ? rawRecord.sort_order : item.sortOrder || 0,
    captured_at: cleanText(item.captured_at || rawRecord.captured_at),
    uploaded_at: rawRecord.uploaded_at || createdAtIso(createdAt),
    created_at: rawRecord.created_at || createdAtIso(createdAt),
    updated_at: rawRecord.updated_at || createdAtIso(createdAt),
    tags: [],
    tag_groups: [],
  };

  const assets = normalizeAssets(item, imageId);
  const squareSlices = normalizeSquareSlices(item, imageId);
  const tagGroups = normalizeTagGroups([
    ...normalizeTagGroupList(item.tag_groups),
    ...normalizeTagGroupList(rawRecord.tag_groups),
  ]);
  const effectiveTagGroups = tagGroups.length ? tagGroups : deriveTagGroupsForRecord({ ...item, imageRecord });
  const flatTags = flatTagsFromGroups(effectiveTagGroups);
  const imageTags = tagRowsFromGroups(imageId, effectiveTagGroups);

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
    series: imageRecord.series,
    captured_at: imageRecord.captured_at,
    display_mode: imageRecord.display_mode,
    visibility: imageRecord.visibility,
    tags: flatTags,
    tag_groups: effectiveTagGroups,
    imageRecord,
    assets,
    imageTags,
    imageTaggings: imageTags.map((tag, index) => ({
      image_id: imageId,
      tag_id: tag.id,
      sort_order: index,
    })),
    squareSlices,
    squareSliceCount: squareSlices.length || item.squareSliceCount || 0,
  };
}

function activeRecord() {
  return records.find((record) => record.id === activeRecordId) || null;
}

function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message, type = "success") {
  if (!liveRegion) {
    return;
  }
  liveRegion.textContent = message;
  liveRegion.dataset.type = type;
  liveRegion.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    liveRegion.classList.remove("is-visible");
  }, 2600);
}

function uploadStageLabel(stage) {
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
            <span>${escapeHtml(uploadStageLabel(task.stage))}</span>
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
    id: `manage-upload-task-${Date.now()}-${index}`,
    name: file.name || `Image ${index + 1}`,
    stage: "queued",
    progress: 0,
    message: "Waiting to start.",
    update(stage, progress, message) {
      updateUploadTask(this, stage, progress, message);
    },
  };
}

function setEditorState(message = "", state = "") {
  if (editorStatus) {
    editorStatus.textContent = message;
    editorStatus.dataset.state = state;
  }
  if (saveState) {
    saveState.textContent = message;
    saveState.dataset.state = state;
  }
}

function setListState(message = "", state = "") {
  if (listStateElement) {
    listStateElement.textContent = message;
    listStateElement.dataset.state = state;
  }
}

function setHomeState(message = "", state = "") {
  if (homeSaveState) {
    homeSaveState.textContent = message;
    homeSaveState.dataset.state = state;
  }
}

function homepagePreviewDetails(imageId, fallbackUrl, fallbackCaption = "Current default asset") {
  const record = records.find((item) => item.id === imageId) || null;
  return {
    record,
    src: (record ? displayUrl(record) : "") || cleanText(fallbackUrl),
    caption: record ? `${record.title} / ${record.type} / ${record.ratio}` : fallbackCaption,
  };
}

function setBusy(isBusy, state = "") {
  if (!isBusy) {
    [refreshButton, homeSaveButton, homeSaveAllButton, homeRevertButton].forEach((button) => {
      if (button) {
        button.disabled = false;
      }
    });
    if (formElement) {
      formElement.dataset.state = state;
    }
    updateEditorActions();
    return;
  }

  [
    saveButton,
    saveAllButton,
    revertButton,
    clearContentButton,
    deleteImageButton,
    refreshButton,
    homeSaveButton,
    homeSaveAllButton,
    homeRevertButton,
  ].forEach((button) => {
    if (button) {
      button.disabled = isBusy;
    }
  });
  if (formElement) {
    formElement.dataset.state = state;
  }
}

function updateCount() {
  const dirtyCount = dirtyRecordIds.size;
  countElement.textContent = `${records.length} work${records.length === 1 ? "" : "s"}${dirtyCount ? ` / ${dirtyCount} unsaved` : ""}`;
}

function updateHomePreview(settings = homeSettings) {
  if (!settings) {
    return;
  }
  const normalized = normalizeHomepageSettings(settings);
  const heroEntries = [
    ["abstract", normalized.hero.abstract],
    ["concrete", normalized.hero.concrete],
  ];

  heroEntries.forEach(([key, hero]) => {
    const imageElement = homePreviewImages.get(key);
    const captionElement = homePreviewCaptions.get(key);
    const preview = homepagePreviewDetails(hero.image_id, hero.fallback_url);
    if (imageElement) {
      imageElement.src = preview.src || "";
      imageElement.alt = `${titleCase(key)} hero preview`;
    }
    if (captionElement) {
      captionElement.textContent = preview.caption;
    }
  });

  normalized.statement.moments.forEach((moment, index) => {
    const imageElement = homeMomentsElement?.querySelector(`[data-home-moment-preview="${index}"]`);
    const captionElement = homeMomentsElement?.querySelector(`[data-home-moment-caption="${index}"]`);
    const preview = homepagePreviewDetails(moment.image_id, moment.fallback_url);
    if (imageElement) {
      imageElement.src = preview.src || "";
      imageElement.alt = `Statement moment ${index + 1} preview`;
    }
    if (captionElement) {
      captionElement.textContent = preview.caption;
    }
  });
}

function updateHomeActions() {
  const homeDirty = Boolean(isHomeDirty);
  const pageDirty = homeDirty || dirtyRecordIds.size > 0;
  if (homeSaveButton) {
    homeSaveButton.disabled = !homeDirty;
  }
  if (homeSaveAllButton) {
    homeSaveAllButton.disabled = !pageDirty;
  }
  if (homeRevertButton) {
    homeRevertButton.disabled = !homeDirty;
  }
  if (homeSaveLabel) {
    homeSaveLabel.textContent = pageDirty ? "Unsaved changes" : "Saved";
    homeSaveLabel.dataset.state = pageDirty ? "dirty" : "saved";
  }
  if (homeLastSaved) {
    homeLastSaved.textContent = `Last saved: ${formatSavedTime(lastSavedAt)}`;
  }
}

function statusHasContent(record) {
  const imageRecord = record.imageRecord || {};
  return Boolean(
    imageRecord.description ||
      imageRecord.curatorial_note ||
      imageRecord.artist_statement ||
      imageRecord.captured_at,
  );
}

function renderListItem(record) {
  const button = document.createElement("button");
  button.className = "manage-list-item";
  button.type = "button";
  button.dataset.recordId = record.id;
  button.dataset.visibility = record.imageRecord.visibility || "draft";
  button.classList.toggle("is-active", record.id === activeRecordId);
  button.classList.toggle("is-dirty", dirtyRecordIds.has(record.id));
  button.setAttribute("aria-pressed", String(record.id === activeRecordId));

  const thumb = document.createElement("img");
  thumb.src = thumbnailUrl(record);
  thumb.alt = "";
  thumb.loading = "lazy";
  thumb.decoding = "async";

  const copy = createElement("div", "manage-list-copy");
  copy.append(createElement("strong", "", record.title));

  const meta = createElement("dl", "manage-list-meta");
  [
    ["Type", record.type],
    ["Ratio", record.ratio],
    ["Size", `${record.width} x ${record.height}`],
    [
      "Status",
      `${visibilityLabel(record.imageRecord.visibility)} / ${statusHasContent(record) ? "Content" : "No content"}${
        dirtyRecordIds.has(record.id) ? " / Unsaved" : ""
      }`,
    ],
  ].forEach(([label, value]) => {
    const wrapper = document.createElement("div");
    const term = createElement("dt", "", label);
    const detail = createElement("dd", "", value);
    detail.dataset.meta = label.toLowerCase();
    wrapper.append(term, detail);
    meta.append(wrapper);
  });
  copy.append(meta);

  button.append(thumb, copy);
  button.addEventListener("click", () => selectRecord(record.id));
  return button;
}

function renderList() {
  listElement.replaceChildren();
  updateCount();

  if (!records.length) {
    const empty = createElement("div", "manage-list-empty");
    empty.append(
      createElement("strong", "", "No works available."),
      createElement("p", "", "Works Viewer metadata uses the local archive base data plus uploaded records from the Works page."),
    );
    listElement.append(empty);
    return;
  }

  records.forEach((record) => {
    listElement.append(renderListItem(record));
  });
}

function homepageImageOptions() {
  return records.map((record) => ({
    id: record.id,
    label: `${record.title} / ${record.type} / ${record.ratio}`,
  }));
}

function setSelectOptions(select, selectedId) {
  if (!select) {
    return;
  }
  const options = homepageImageOptions();
  select.replaceChildren();
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "Use current default asset";
  select.append(defaultOption);
  options.forEach((option) => {
    const element = document.createElement("option");
    element.value = option.id;
    element.textContent = option.label;
    select.append(element);
  });
  if (selectedId && options.some((option) => option.id === selectedId)) {
    select.value = selectedId;
  } else {
    select.value = "";
  }
}

function setHomeDirty(isDirty) {
  isHomeDirty = Boolean(isDirty);
  setHomeState(isHomeDirty ? "Unsaved changes." : "", isHomeDirty ? "dirty" : "");
  updateHomeActions();
}

function renderHomeMoments(moments = []) {
  if (!homeMomentsElement) {
    return;
  }
  homeMomentsElement.replaceChildren();
  moments.forEach((moment, index) => {
    const row = createElement("div", "manage-home-moment");
    const previewFigure = createElement("figure", "manage-home-preview manage-moment-preview");
    const previewImage = document.createElement("img");
    previewImage.alt = `Statement moment ${index + 1} preview`;
    previewImage.decoding = "async";
    previewImage.dataset.homeMomentPreview = String(index);
    const previewCaption = document.createElement("figcaption");
    previewCaption.dataset.homeMomentCaption = String(index);
    previewCaption.textContent = "Current default asset";
    previewFigure.append(previewImage, previewCaption);

    const imageLabel = document.createElement("label");
    imageLabel.className = "form-field";
    imageLabel.htmlFor = `home-statement-image-${index}`;
    imageLabel.append(createElement("span", "", `Moment ${index + 1} Image`));
    const select = document.createElement("select");
    select.id = `home-statement-image-${index}`;
    select.name = `statement_moment_${index}_image_id`;
    setSelectOptions(select, moment.image_id);
    imageLabel.append(select);

    const textLabel = document.createElement("label");
    textLabel.className = "form-field";
    textLabel.htmlFor = `home-statement-text-${index}`;
    textLabel.append(createElement("span", "", `Moment ${index + 1} Text`));
    const textarea = document.createElement("textarea");
    textarea.id = `home-statement-text-${index}`;
    textarea.name = `statement_moment_${index}_text`;
    textarea.rows = 3;
    textarea.maxLength = 900;
    textarea.value = moment.text || "";
    textLabel.append(textarea);

    row.append(previewFigure, imageLabel, textLabel);
    homeMomentsElement.append(row);
  });
}

function renderHomepageSettings() {
  if (!homeForm || !homeSettings) {
    return;
  }
  isRenderingHomeForm = true;
  const settings = normalizeHomepageSettings(homeSettings);
  setSelectOptions(homeForm.elements.abstract_image_id, settings.hero.abstract.image_id);
  setSelectOptions(homeForm.elements.concrete_image_id, settings.hero.concrete.image_id);
  homeForm.elements.abstract_eyebrow.value = settings.hero.abstract.eyebrow;
  homeForm.elements.abstract_title.value = settings.hero.abstract.title;
  homeForm.elements.abstract_statement.value = settings.hero.abstract.statement;
  homeForm.elements.concrete_eyebrow.value = settings.hero.concrete.eyebrow;
  homeForm.elements.concrete_title.value = settings.hero.concrete.title;
  homeForm.elements.concrete_statement.value = settings.hero.concrete.statement;
  homeForm.elements.statement_title.value = settings.statement.title;
  renderHomeMoments(settings.statement.moments);
  updateHomePreview(settings);
  isRenderingHomeForm = false;
  updateHomeActions();
}

function homepageSettingsFromForm() {
  const formData = new FormData(homeForm);
  const defaults = normalizeHomepageSettings(homeSettings || savedHomeSettings);
  const moments = Array.from({ length: 4 }, (_, index) => ({
    image_id: cleanText(formData.get(`statement_moment_${index}_image_id`)),
    fallback_url: defaults.statement.moments[index].fallback_url,
    text: cleanText(formData.get(`statement_moment_${index}_text`)) || defaults.statement.moments[index].text,
  }));
  const abstractImageId = cleanText(formData.get("abstract_image_id"));
  const concreteImageId = cleanText(formData.get("concrete_image_id"));
  return normalizeHomepageSettings({
    id: HOME_SETTINGS_ID,
    updated_at: nowIso(),
    database_shape: {
      page_settings: "homepage",
      collections: ["homepage-selected"],
      collection_images: [
        { collection_slug: "homepage-selected", role: "hero_abstract", image_id: abstractImageId, sort_order: 0 },
        { collection_slug: "homepage-selected", role: "hero_concrete", image_id: concreteImageId, sort_order: 1 },
        ...moments.map((moment, index) => ({
          collection_slug: "homepage-selected",
          role: `statement_moment_${index + 1}`,
          image_id: moment.image_id,
          sort_order: index + 2,
        })),
      ],
    },
    hero: {
      abstract: {
        ...defaults.hero.abstract,
        image_id: abstractImageId,
        eyebrow: cleanText(formData.get("abstract_eyebrow")) || defaults.hero.abstract.eyebrow,
        title: cleanText(formData.get("abstract_title")) || defaults.hero.abstract.title,
        statement: cleanText(formData.get("abstract_statement")) || defaults.hero.abstract.statement,
      },
      concrete: {
        ...defaults.hero.concrete,
        image_id: concreteImageId,
        eyebrow: cleanText(formData.get("concrete_eyebrow")) || defaults.hero.concrete.eyebrow,
        title: cleanText(formData.get("concrete_title")) || defaults.hero.concrete.title,
        statement: cleanText(formData.get("concrete_statement")) || defaults.hero.concrete.statement,
      },
    },
    statement: {
      title: cleanText(formData.get("statement_title")) || defaults.statement.title,
      moments,
    },
  });
}

function syncHomepageForm({ markDirty = true } = {}) {
  if (!homeForm || isRenderingHomeForm) {
    return homeSettings;
  }
  homeSettings = homepageSettingsFromForm();
  updateHomePreview(homeSettings);
  if (markDirty) {
    setHomeDirty(homepageSignature(homeSettings) !== homeSettingsSignature);
  }
  return homeSettings;
}

function updateActiveListState() {
  listElement.querySelectorAll(".manage-list-item").forEach((item) => {
    const isActive = item.dataset.recordId === activeRecordId;
    item.classList.toggle("is-active", isActive);
    item.setAttribute("aria-pressed", String(isActive));
  });
}

function updateListItem(record) {
  if (!record) {
    renderList();
    return;
  }
  const currentItem = listElement.querySelector(`[data-record-id="${CSS.escape(record.id)}"]`);
  if (!currentItem) {
    renderList();
    return;
  }
  currentItem.replaceWith(renderListItem(record));
  updateActiveListState();
}

function removeListItem(id) {
  const item = listElement.querySelector(`[data-record-id="${CSS.escape(id)}"]`);
  if (item) {
    item.remove();
  }
  updateCount();
  if (!records.length) {
    renderList();
  } else {
    updateActiveListState();
  }
}

function metaTerm(label, value) {
  const wrapper = document.createElement("div");
  wrapper.append(createElement("dt", "", label), createElement("dd", "", value || "Not set"));
  return wrapper;
}

function renderSchemaSummary(record) {
  recordSchema.replaceChildren();
  [
    ["images", 1],
    ["image_assets", record.assets.length],
    ["image_square_slices", record.squareSlices.length],
  ].forEach(([label, value]) => {
    const chip = createElement("span", "", `${label}: ${value}`);
    recordSchema.append(chip);
  });
}

function renderTagGroupsEditor(record) {
  if (!tagGroupsEditor) {
    return;
  }

  const groupsByLabel = new Map(tagGroupsForRecord(record).map((group) => [group.label.toLowerCase(), group]));
  tagGroupsEditor.replaceChildren(
    ...TAG_GROUP_LABELS.map((label) => {
      const field = document.createElement("label");
      field.className = "form-field manage-tag-field";
      field.dataset.tagGroupField = label;
      field.innerHTML = `
        <span>${escapeHtml(label)}</span>
        <textarea name="tag_group_${escapeHtml(slugify(label, "group"))}" rows="2" data-tag-group="${escapeHtml(label)}"></textarea>
      `;
      const textarea = field.querySelector("textarea");
      textarea.value = (groupsByLabel.get(label.toLowerCase())?.tags || []).join(", ");
      return field;
    }),
  );
}

function tagGroupsFromForm() {
  if (!tagGroupsEditor) {
    return [];
  }

  return normalizeTagGroups(
    Array.from(tagGroupsEditor.querySelectorAll("[data-tag-group]")).map((textarea) => ({
      label: textarea.dataset.tagGroup,
      tags: tagsFromValue(textarea.value),
    })),
  );
}

function updateEditorActions() {
  const record = activeRecord();
  const isDirty = Boolean(record && dirtyRecordIds.has(record.id));
  if (revertButton) {
    revertButton.disabled = !record || !isDirty;
  }
  if (saveButton) {
    saveButton.disabled = !record;
  }
  if (saveAllButton) {
    saveAllButton.disabled = dirtyRecordIds.size === 0;
  }
  if (clearContentButton) {
    clearContentButton.disabled = !record;
  }
  if (deleteImageButton) {
    deleteImageButton.disabled = !record || isBaseRecord(record);
    deleteImageButton.title = record && isBaseRecord(record) ? "Local sample image rows are base data; clear metadata instead." : "";
  }
  updateCount();
  updateHomeActions();
}

function setDirty(recordId, isDirty = true) {
  if (!recordId) {
    return;
  }
  if (isDirty) {
    dirtyRecordIds.add(recordId);
  } else {
    dirtyRecordIds.delete(recordId);
  }
  updateListItem(activeRecord() || records.find((record) => record.id === recordId));
  updateEditorActions();
}

function syncActiveFormToRecord({ markDirty = true } = {}) {
  const record = activeRecord();
  if (!record || isRenderingForm) {
    return record;
  }

  const nextRecord = normalizeRecord(recordFromForm(record));
  records = records.map((item) => (item.id === nextRecord.id ? nextRecord : item));
  if (markDirty) {
    setDirty(nextRecord.id, recordSignature(nextRecord) !== savedSignatures.get(nextRecord.id));
  }
  return nextRecord;
}

function renderEditor() {
  const record = activeRecord();
  emptyElement.hidden = Boolean(record);
  formElement.hidden = !record;

  if (!record) {
    updateEditorActions();
    return;
  }

  isRenderingForm = true;
  const imageRecord = record.imageRecord || {};
  previewImage.src = displayUrl(record);
  previewImage.alt = record.title;
  editorTitle.textContent = record.title;
  recordSource.textContent = imageRecord.original_filename || "Uploaded record";
  editorMeta.replaceChildren(
    metaTerm("Type", contentTypeLabel(imageRecord.content_type)),
    metaTerm("Ratio", record.ratio),
    metaTerm("Size", `${imageRecord.original_width || record.width} x ${imageRecord.original_height || record.height}`),
    metaTerm("Visibility", visibilityLabel(imageRecord.visibility)),
    metaTerm("Assets", `${record.assets.length} versions`),
    metaTerm("Slices", `${record.squareSlices.length}`),
  );
  renderSchemaSummary(record);

  formElement.elements.title.value = imageRecord.title || "";
  formElement.elements.description.value = imageRecord.description || "";
  formElement.elements.curatorial_note.value = imageRecord.curatorial_note || "";
  formElement.elements.artist_statement.value = imageRecord.artist_statement || "";
  formElement.elements.captured_at.value = formatDateInput(imageRecord.captured_at);
  formElement.elements.content_type.value = contentTypeCode(imageRecord.content_type);
  formElement.elements.visibility.value = imageRecord.visibility || "draft";
  formElement.elements.sort_order.value = Number.isFinite(imageRecord.sort_order) ? imageRecord.sort_order : record.sortOrder || 0;
  renderTagGroupsEditor(record);
  errorElement.textContent = "";
  setEditorState(dirtyRecordIds.has(record.id) ? "Unsaved changes." : "", dirtyRecordIds.has(record.id) ? "dirty" : "");
  isRenderingForm = false;
  updateEditorActions();
}

function validateRecordPayload(payload) {
  if (!payload.title) {
    return "Title is required before saving.";
  }
  if (payload.content_type === "abstract" && payload.display_mode !== "black_white") {
    return "Schema rule: abstract works must use black and white display mode.";
  }
  if (payload.content_type === "concrete" && payload.display_mode !== "color") {
    return "Schema rule: concrete works must use color display mode.";
  }
  return "";
}

function recordFromForm(record) {
  const formData = new FormData(formElement);
  const contentType = contentTypeCode(formData.get("content_type"));
  const displayMode = displayModeForType(contentType);
  const updatedAt = nowIso();
  const sortOrder = numberOrFallback(formData.get("sort_order"), record.imageRecord?.sort_order || record.sortOrder || 0);
  const formTagGroups = tagGroupsFromForm();
  const tagGroups = formTagGroups.length ? formTagGroups : deriveTagGroupsForRecord(record);
  const flatTags = flatTagsFromGroups(tagGroups);
  const imageTags = tagRowsFromGroups(record.id, tagGroups);
  const nextImageRecord = {
    ...(record.imageRecord || {}),
    id: record.id,
    title: cleanText(formData.get("title")),
    description: cleanText(formData.get("description")),
    curatorial_note: cleanText(formData.get("curatorial_note")),
    artist_statement: cleanText(formData.get("artist_statement")),
    captured_at: cleanText(formData.get("captured_at")),
    content_type: contentType,
    display_mode: displayMode,
    visibility: cleanText(formData.get("visibility")) || "draft",
    visibility_manually_set: true,
    sort_order: sortOrder,
    original_width: record.imageRecord?.original_width || record.width,
    original_height: record.imageRecord?.original_height || record.height,
    ratio_category_code: record.imageRecord?.ratio_category_code || ratioCategoryCode(record.ratio),
    updated_at: updatedAt,
    tag_groups: tagGroups,
    tags: flatTags,
  };

  return {
    ...record,
    title: nextImageRecord.title,
    type: contentTypeLabel(nextImageRecord.content_type),
    description: nextImageRecord.description,
    curatorial_note: nextImageRecord.curatorial_note,
    artist_statement: nextImageRecord.artist_statement,
    series: nextImageRecord.series,
    captured_at: nextImageRecord.captured_at,
    display_mode: nextImageRecord.display_mode,
    visibility: nextImageRecord.visibility,
    sortOrder,
    tag_groups: tagGroups,
    tags: flatTags,
    imageTags,
    imageTaggings: imageTags.map((tag, index) => ({
      image_id: record.id,
      tag_id: tag.id,
      sort_order: index,
    })),
    imageRecord: nextImageRecord,
  };
}

async function persistRecord(record, message = "Image record saved.", { rerenderEditor = false, isNewUpload = false } = {}) {
  const syncResult = await syncArchiveApiRecord(record, isNewUpload);
  await putStoredItem(record);
  records = records.map((item) => (item.id === record.id ? record : item));
  rememberSavedRecord(record);
  updateLastSavedAt(nowIso());
  updateListItem(record);
  if (rerenderEditor || record.id === activeRecordId) {
    renderEditor();
  }
  updateSavedOrder();
  const savedMessage = syncResult.synced ? "Work saved to local archive database." : syncResult.warning || message;
  setEditorState(savedMessage, syncResult.warning ? "warning" : "saved");
}

async function saveRecordById(recordId, { silent = false } = {}) {
  if (recordId === activeRecordId) {
    syncActiveFormToRecord({ markDirty: false });
  }
  const record = records.find((item) => item.id === recordId);
  if (!record) {
    return null;
  }

  const nextRecord = normalizeRecord(record);
  const validationError = validateRecordPayload(nextRecord.imageRecord);
  if (validationError) {
    errorElement.textContent = validationError;
    setEditorState("Error: unable to save.", "error");
    showToast(validationError, "error");
    return null;
  }

  setEditorState(silent ? "Saving changes..." : "Saving current work...", "saving");
  setBusy(true, "saving");

  try {
    await persistRecord(nextRecord, silent ? "Changes saved." : "Work saved.", { rerenderEditor: recordId === activeRecordId });
    if (!silent) {
      showToast("Work saved.");
    }
    return nextRecord;
  } catch (error) {
    errorElement.textContent = error?.message || "Unable to save this record.";
    setEditorState("Error: save failed.", "error");
    showToast("Unable to save this record.", "error");
    return null;
  } finally {
    setBusy(false, "");
  }
}

async function saveActiveRecord() {
  const record = activeRecord();
  if (!record) {
    return;
  }
  await saveRecordById(record.id);
}

async function saveAllDirtyRecords() {
  syncActiveFormToRecord();
  const ids = [...dirtyRecordIds];
  if (!ids.length) {
    return;
  }

  setBusy(true, "saving");
  setEditorState(`Saving ${ids.length} changed work${ids.length === 1 ? "" : "s"}...`, "saving");

  try {
    for (const id of ids) {
      const saved = await saveRecordById(id, { silent: true });
      if (!saved) {
        break;
      }
    }
    renderEditor();
    setEditorState("All changes saved.", "saved");
    showToast("All changes saved.");
  } finally {
    setBusy(false, "");
  }
}

function revertActiveRecord() {
  const record = activeRecord();
  if (!record || !dirtyRecordIds.has(record.id)) {
    return;
  }
  const savedRecord = savedRecords.get(record.id);
  if (!savedRecord) {
    return;
  }
  records = records.map((item) => (item.id === record.id ? normalizeRecord(cloneRecord(savedRecord)) : item));
  dirtyRecordIds.delete(record.id);
  renderEditor();
  updateListItem(activeRecord() || record);
  setEditorState("Current work reverted.", "");
  showToast("Current work reverted.");
}

function clearContentRecord(record) {
  const tagGroups = deriveTagGroupsForRecord(record);
  const flatTags = flatTagsFromGroups(tagGroups);
  const imageTags = tagRowsFromGroups(record.id, tagGroups);
  const nextImageRecord = {
    ...(record.imageRecord || {}),
    description: "",
    curatorial_note: "",
    artist_statement: "",
    series: "",
    captured_at: "",
    tags: flatTags,
    tag_groups: tagGroups,
    updated_at: nowIso(),
  };
  return {
    ...record,
    description: "",
    curatorial_note: "",
    artist_statement: "",
    series: "",
    captured_at: "",
    tags: flatTags,
    tag_groups: tagGroups,
    imageTags,
    imageTaggings: imageTags.map((tag, index) => ({
      image_id: record.id,
      tag_id: tag.id,
      sort_order: index,
    })),
    imageRecord: nextImageRecord,
  };
}

async function clearActiveContent() {
  const record = activeRecord();
  if (!record) {
    return;
  }
  setEditorState("Deleting content data...", "deleting");
  setBusy(true, "deleting");

  try {
    const nextRecord = normalizeRecord(clearContentRecord(record));
    await putStoredItem(nextRecord);
    records = records.map((item) => (item.id === record.id ? nextRecord : item));
    rememberSavedRecord(nextRecord);
    updateLastSavedAt(nowIso());
    updateListItem(nextRecord);
    renderEditor();
    setEditorState("Content data deleted. Assets preserved.", "deleted");
    showToast("Content data deleted. Image assets were preserved.");
  } finally {
    setBusy(false, "");
  }
}

function revokeRecordUrls(record) {
  (record.assets || []).forEach((asset) => {
    if (asset.objectUrl) {
      URL.revokeObjectURL(asset.objectUrl);
      objectUrls.delete(asset.objectUrl);
      delete asset.objectUrl;
    }
  });
}

async function deleteActiveImage() {
  const record = activeRecord();
  if (!record) {
    return;
  }
  setEditorState("Deleting image record and related local data...", "deleting");
  setBusy(true, "deleting");

  try {
    await deleteStoredItem(record.id);
    revokeRecordUrls(record);
    records = records.filter((item) => item.id !== record.id);
    dirtyRecordIds.delete(record.id);
    savedRecords.delete(record.id);
    savedSignatures.delete(record.id);
    updateLastSavedAt(nowIso());
    removeListItem(record.id);
    activeRecordId = records[0]?.id || null;
    updateActiveListState();
    renderEditor();
    setListState("Deleted image record, related assets, slices, and content data.", "deleted");
    showToast("Image record and related local data deleted.");
  } finally {
    setBusy(false, "");
  }
}

async function importUploadedFiles(files) {
  if (!files.length) {
    return;
  }
  if (!window.MTArchiveUpload) {
    showToast("Upload module is not available.", "error");
    return;
  }
  if (!archiveDb) {
    archiveDb = await openArchiveDatabase();
  }

  const tasks = files.map(createUploadTask);
  uploadTasks = [...tasks, ...uploadTasks];
  renderUploadTasks();
  if (uploadInput) {
    uploadInput.disabled = true;
  }

  const importedRecords = [];
  for (const [index, file] of files.entries()) {
    const task = tasks[index];
    try {
      if (!file.type.startsWith("image/")) {
        throw new Error("Only image files can be imported.");
      }
      const { item, fallbackMessage } = await window.MTArchiveUpload.buildUploadedItem(file, task, index);
      const record = normalizeRecord({
        ...item,
        sortOrder: 0,
        imageRecord: {
          ...(item.imageRecord || {}),
          sort_order: 0,
        },
      });
      const shiftedRecords = sortRecordsCollection(
        records.map((existing) => ({
          ...existing,
          sortOrder: (existing.sortOrder || 0) + 1,
          imageRecord: {
            ...(existing.imageRecord || {}),
            sort_order: numberOrFallback(existing.imageRecord?.sort_order, existing.sortOrder || 0) + 1,
          },
        })),
      );
      records = sortRecordsCollection([record, ...shiftedRecords]);
      updateUploadTask(task, "uploading", 88, "Saving local images, image_assets, and square slice records.");

      // Try to sync to SQLite database
      try {
        const syncResult = await syncArchiveApiRecord(record, true);
        if (syncResult.synced) {
          await putStoredItem(record);
          updateUploadTask(task, "complete", 100, "Saved to local archive database and IndexedDB.");
        } else if (syncResult.warning) {
          await putStoredItem(record);
          updateUploadTask(task, "warning", 100, syncResult.warning);
        } else {
          await putStoredItem(record);
          updateUploadTask(task, "complete", 100, "Display, thumbnail, original, and slice records are ready.");
        }
      } catch (syncError) {
        // If database sync fails, still save to IndexedDB
        await putStoredItem(record);
        updateUploadTask(task, "warning", 100, `Saved to IndexedDB only: ${syncError?.message || "Database sync failed."}`);
      }

      importedRecords.push(record);
      rememberSavedRecord(record);
    } catch (error) {
      updateUploadTask(task, "failed", 100, error?.message || "Unable to import this image.");
    }
  }

  if (importedRecords.length) {
    activeRecordId = importedRecords[0].id;
    updateSavedOrder();
    renderAll();
    renderHomepageSettings();
    showToast(`${importedRecords.length} work${importedRecords.length === 1 ? "" : "s"} imported.`);
  }
  if (uploadInput) {
    uploadInput.value = "";
    uploadInput.disabled = false;
  }
}

async function saveHomepageSettings() {
  if (!homeForm) {
    return;
  }
  syncHomepageForm({ markDirty: false });
  const nextSettings = normalizeHomepageSettings({
    ...homeSettings,
    updated_at: nowIso(),
  });
  setHomeState("Saving homepage...", "saving");
  if (homeSaveButton) {
    homeSaveButton.disabled = true;
  }
  try {
    await putHomeSettingsRecord(nextSettings);
    homeSettings = nextSettings;
    savedHomeSettings = cloneRecord(nextSettings);
    homeSettingsSignature = homepageSignature(nextSettings);
    updateLastSavedAt(nextSettings.updated_at);
    setHomeDirty(false);
    setHomeState("Saved.", "saved");
    showToast("Homepage settings saved.");
  } catch (error) {
    setHomeState(error?.message || "Unable to save homepage.", "error");
    showToast("Unable to save homepage settings.", "error");
  }
}

function revertHomepageSettings() {
  if (!savedHomeSettings) {
    return;
  }
  homeSettings = cloneRecord(savedHomeSettings);
  renderHomepageSettings();
  setHomeDirty(false);
  setHomeState("Homepage reverted.", "");
  showToast("Homepage settings reverted.");
}

async function saveAllChanges() {
  const shouldSaveHome = Boolean(isHomeDirty);
  if (shouldSaveHome) {
    await saveHomepageSettings();
  }
  if (dirtyRecordIds.size) {
    await saveAllDirtyRecords();
  }
  updateHomeActions();
}

function openConfirm({ title, message, confirmText, onConfirm }) {
  currentConfirm = onConfirm;
  confirmTitle.textContent = title;
  confirmMessage.textContent = message;
  confirmSubmit.textContent = confirmText;
  if (typeof confirmDialog.showModal === "function") {
    confirmDialog.showModal();
  } else {
    confirmDialog.setAttribute("open", "");
  }
  confirmCancel.focus();
}

function closeConfirm() {
  currentConfirm = null;
  if (confirmDialog.open && typeof confirmDialog.close === "function") {
    confirmDialog.close();
  } else {
    confirmDialog.removeAttribute("open");
  }
}

function hasUnsavedChanges() {
  return dirtyRecordIds.size > 0;
}

function confirmUnsavedAction(message = "You have unsaved changes. Continue without saving?") {
  if (!hasAnyUnsavedChanges()) {
    return true;
  }
  return window.confirm(message);
}

function hasAnyUnsavedChanges() {
  return hasUnsavedChanges() || isHomeDirty;
}

function selectRecord(id) {
  if (id === activeRecordId) {
    return;
  }
  syncActiveFormToRecord();
  if (activeRecordId && hasAnyUnsavedChanges() && !confirmUnsavedAction("There are unsaved changes. Switch to another work?")) {
    return;
  }
  activeRecordId = id;
  updateActiveListState();
  renderEditor();
}

function renderAll() {
  renderList();
  renderEditor();
}

async function loadRecords() {
  if (hasAnyUnsavedChanges() && !window.confirm("Refresh will discard unsaved metadata or homepage changes. Continue?")) {
    return;
  }

  setListState("Loading records...", "loading");
  refreshButton.disabled = true;
  countElement.textContent = "Loading records";

  try {
    if (!archiveDb) {
      archiveDb = await openArchiveDatabase();
    }
    const storedItems = await getStoredItems();
    const storedById = new Map(storedItems.map((item) => [item.id, item]));
    const baseRecords = baseArchiveItems.map(baseRecordFromArchiveItem);
    const baseIds = new Set(baseRecords.map((record) => record.id));
    const mergedBaseRecords = baseRecords.map((baseRecord) => mergeBaseAndStoredRecord(baseRecord, storedById.get(baseRecord.id)));
    const uploadedRecords = storedItems
      .filter((item) => !baseIds.has(item.id) && isUploadedRecord(item))
      .map(normalizeRecord);
    records = sortRecordsCollection(applySavedSortOrders([...mergedBaseRecords, ...uploadedRecords]));
    dirtyRecordIds.clear();
    savedRecords.clear();
    savedSignatures.clear();
    records.forEach(rememberSavedRecord);
    const storedHomeSettings = await getHomeSettingsRecord();
    homeSettings = normalizeHomepageSettings(storedHomeSettings);
    savedHomeSettings = cloneRecord(homeSettings);
    homeSettingsSignature = homepageSignature(homeSettings);
    isHomeDirty = false;
    lastSavedAt = latestIsoValue([
      storedHomeSettings?.updated_at,
      ...storedItems.map((item) => item.imageRecord?.updated_at || item.updated_at),
    ]);

    if (activeRecordId && !records.some((record) => record.id === activeRecordId)) {
      activeRecordId = null;
    }
    if (!activeRecordId && records.length) {
      activeRecordId = records[0].id;
    }

    renderAll();
    renderHomepageSettings();
    setHomeState("", "");
    setListState(records.length ? "" : "Empty: no works are available.", records.length ? "" : "empty");
  } catch (error) {
    listElement.replaceChildren(
      createElement("p", "manage-list-state", error?.message || "Unable to load local image records."),
    );
    countElement.textContent = "Unable to load";
    setListState("Error: unable to load local image records.", "error");
    showToast("Unable to load local image records.", "error");
  } finally {
    refreshButton.disabled = false;
  }
}

uploadInput?.addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  await importUploadedFiles(files);
});

formElement.addEventListener("submit", (event) => {
  event.preventDefault();
  saveActiveRecord();
});

homeForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  saveHomepageSettings();
});

homeForm?.addEventListener("input", () => {
  syncHomepageForm();
});

homeForm?.addEventListener("change", () => {
  syncHomepageForm();
});

homeRevertButton?.addEventListener("click", revertHomepageSettings);
homeSaveAllButton?.addEventListener("click", saveAllChanges);

formElement.addEventListener("input", () => {
  syncActiveFormToRecord();
  const record = activeRecord();
  if (record) {
    editorTitle.textContent = record.title;
  }
});

formElement.addEventListener("change", () => {
  syncActiveFormToRecord();
});

formElement.elements.content_type.addEventListener("change", () => {
  syncActiveFormToRecord();
});

saveAllButton?.addEventListener("click", saveAllDirtyRecords);
revertButton?.addEventListener("click", revertActiveRecord);

clearContentButton.addEventListener("click", () => {
  const record = activeRecord();
  if (!record) {
    return;
  }
  openConfirm({
    title: "Delete content data?",
    message:
      "This clears description, curatorial note, artist statement, series, and captured date for this image. It keeps original, display, thumbnail, and square slice assets.",
    confirmText: "Delete Content",
    onConfirm: clearActiveContent,
  });
});

deleteImageButton.addEventListener("click", () => {
  const record = activeRecord();
  if (!record) {
    return;
  }
  if (isBaseRecord(record)) {
    showToast("Local sample image rows are base data. Use Delete Content Data to clear manual metadata.", "error");
    return;
  }
  openConfirm({
    title: "Delete image record?",
    message:
      "This removes the images row equivalent, image_assets records, image_square_slices records, local image blobs, and all manually entered content for this image. This cannot be undone.",
    confirmText: "Delete Image",
    onConfirm: deleteActiveImage,
  });
});

confirmCancel.addEventListener("click", closeConfirm);
confirmDialog.addEventListener("cancel", () => {
  currentConfirm = null;
});
confirmSubmit.addEventListener("click", async () => {
  const action = currentConfirm;
  closeConfirm();
  if (!action) {
    return;
  }
  try {
    await action();
  } catch (error) {
    setEditorState(error?.message || "Error: delete failed.", "error");
    setListState(error?.message || "Error: delete failed.", "error");
    showToast(error?.message || "Delete failed.", "error");
  }
});

refreshButton.addEventListener("click", loadRecords);
window.addEventListener("beforeunload", (event) => {
  syncActiveFormToRecord();
  syncHomepageForm();
  if (!hasAnyUnsavedChanges()) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});
window.addEventListener("pagehide", () => {
  objectUrls.forEach((url) => URL.revokeObjectURL(url));
  objectUrls.clear();
});

loadRecords();
