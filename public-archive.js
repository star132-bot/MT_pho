(function initPublicArchive(global) {
  const archiveSeedData = global.MTPresenceArchiveData || {};
  const ARCHIVE_API_URL = "/api/archive/images";
  const DB_NAME = "mt-cijian-archive";
  const DB_VERSION = 4;
  const DB_STORE = "images";
  const LIGHTBOX_STORAGE_KEY = "mt-presence-lightbox-v1";
  const LEGACY_LIGHTBOX_KEYS = ["mt-presence-collection-works-v1", "mt-presence-saved-works-v1"];

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
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

  function ratioCssValue(label) {
    const match = (archiveSeedData.ratioProfiles || []).find((item) => item.label === label);
    return match ? `${match.ratio}` : "1";
  }

  function contentTypeLabel(type) {
    return cleanText(type).toLowerCase() === "abstract" ? "Abstract" : "Concrete";
  }

  function displayUrl(record) {
    const assets = Array.isArray(record.assets) ? record.assets : [];
    const display = assets.find((asset) => asset.kind === "display") || assets.find((asset) => asset.kind === "original");
    return display?.objectUrl || display?.public_url || record.image_url || record.src || "";
  }

  function normalizeApiWork(row) {
    return {
      id: cleanText(row.id),
      title: cleanText(row.title) || "Untitled Work",
      src: displayUrl(row),
      width: Number(row.original_width || row.width || 1),
      height: Number(row.original_height || row.height || 1),
      type: contentTypeLabel(row.content_type || row.type),
      ratio: cleanText(row.ratio_label || ratioLabelFromCode(row.ratio_category_code) || row.ratio) || "1:1",
      series: cleanText(row.series),
      capturedAt: cleanText(row.captured_at),
      description: cleanText(row.description),
      curatorialNote: cleanText(row.curatorial_note),
      tags: Array.isArray(row.tags) ? row.tags : [],
      tagGroups: Array.isArray(row.tag_groups) ? row.tag_groups : [],
      visibility: cleanText(row.visibility) || "published",
      sortOrder: Number.isFinite(Number(row.sort_order)) ? Number(row.sort_order) : 0,
    };
  }

  function normalizeStoredWork(record) {
    const imageRecord = record.imageRecord || {};
    return normalizeApiWork({
      ...record,
      ...imageRecord,
      assets: record.assets || imageRecord.assets,
      image_url: displayUrl(record),
      title: imageRecord.title || record.title,
      original_width: imageRecord.original_width || record.width,
      original_height: imageRecord.original_height || record.height,
      content_type: imageRecord.content_type || record.type,
      ratio: record.ratio,
      series: imageRecord.series || record.series,
      visibility: imageRecord.visibility || record.visibility || "draft",
      sort_order: imageRecord.sort_order ?? record.sortOrder,
      tag_groups: imageRecord.tag_groups || record.tag_groups,
      tags: imageRecord.tags || record.tags,
    });
  }

  function normalizeSampleWork(item, index) {
    return {
      ...normalizeApiWork({ ...item, visibility: "published", sort_order: index }),
      source: "sample",
    };
  }

  async function fetchArchiveWorks() {
    const response = await fetch(ARCHIVE_API_URL, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Archive API returned ${response.status}.`);
    }
    const payload = await response.json();
    return (Array.isArray(payload.items) ? payload.items : []).map(normalizeApiWork).filter((item) => item.id && item.src);
  }

  function openArchiveDatabase() {
    return new Promise((resolve, reject) => {
      if (!("indexedDB" in global)) {
        resolve(null);
        return;
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(DB_STORE)) {
          database.createObjectStore(DB_STORE, { keyPath: "id" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error("Unable to open the local archive."));
    });
  }

  async function readStoredWorks() {
    const database = await openArchiveDatabase();
    if (!database) {
      return [];
    }
    return new Promise((resolve, reject) => {
      const request = database.transaction(DB_STORE).objectStore(DB_STORE).getAll();
      request.onsuccess = () => resolve((request.result || []).map(normalizeStoredWork));
      request.onerror = () => reject(request.error || new Error("Unable to read the local archive."));
    });
  }

  async function loadPublishedWorks() {
    let source = "api";
    let status = "Archive loaded.";
    let works;
    try {
      works = await fetchArchiveWorks();
      if (!works.length) {
        throw new Error("The archive contains no published works.");
      }
    } catch (error) {
      source = "sample";
      status = `${error?.message || "Archive unavailable"} Showing local preview works.`;
      works = (archiveSeedData.sampleItems || []).map(normalizeSampleWork);
    }

    try {
      const storedUploads = (await readStoredWorks()).filter((item) => item.visibility === "published" && item.id && item.src);
      const merged = new Map(works.map((item) => [item.id, item]));
      storedUploads.forEach((item) => merged.set(item.id, item));
      works = [...merged.values()];
    } catch {
      // API or sample works remain available when browser storage cannot be read.
    }

    works.sort((a, b) => a.sortOrder - b.sortOrder || a.title.localeCompare(b.title));
    return { works, source, status };
  }

  function readIdArray(key) {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string" && id) : [];
    } catch {
      return [];
    }
  }

  function readLightboxIds() {
    const current = readIdArray(LIGHTBOX_STORAGE_KEY);
    if (current.length || localStorage.getItem(LIGHTBOX_STORAGE_KEY) !== null) {
      return current;
    }
    const migrated = [...new Set(LEGACY_LIGHTBOX_KEYS.flatMap(readIdArray))];
    if (migrated.length) {
      writeLightboxIds(migrated);
    }
    return migrated;
  }

  function writeLightboxIds(ids) {
    const normalized = [...new Set((ids || []).filter((id) => typeof id === "string" && id))];
    localStorage.setItem(LIGHTBOX_STORAGE_KEY, JSON.stringify(normalized));
    global.dispatchEvent(new CustomEvent("mt:lightbox-change", { detail: { ids: normalized } }));
    return normalized;
  }

  function toggleLightboxId(id) {
    const ids = readLightboxIds();
    const next = ids.includes(id) ? ids.filter((itemId) => itemId !== id) : [...ids, id];
    writeLightboxIds(next);
    return { ids: next, added: next.includes(id) };
  }

  global.MTPresencePublicArchive = {
    LIGHTBOX_STORAGE_KEY,
    cleanText,
    escapeHtml,
    loadPublishedWorks,
    ratioCssValue,
    readLightboxIds,
    writeLightboxIds,
    toggleLightboxId,
  };
})(window);
