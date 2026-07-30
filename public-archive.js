(function initPublicArchive(global) {
  const archiveSeedData = global.MTPresenceArchiveData || {};
  const ARCHIVE_API_URL = "/api/archive/images";
  const DB_NAME = "mt-cijian-archive";
  const DB_VERSION = 4;
  const DB_STORE = "images";
  const LIGHTBOX_STORAGE_KEY = "mt-presence-lightbox-v1";
  const INQUIRY_SELECTION_STORAGE_KEY = "mt-presence-inquiry-selection-v1";
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

  function assetUrl(asset) {
    return cleanText(asset?.url || asset?.public_url || asset?.signed_url || asset?.objectUrl);
  }

  function displayUrl(record) {
    const assets = record?.assets;
    if (Array.isArray(assets)) {
      const display = assets.find((asset) => asset.kind === "display");
      const original = assets.find((asset) => asset.kind === "original");
      return assetUrl(display) || assetUrl(original) || cleanText(record.image_url || record.display_url || record.src);
    }
    return assetUrl(assets?.display) || cleanText(record?.image_url || record?.display_url || record?.src);
  }

  function thumbnailUrl(record) {
    const assets = record?.assets;
    if (Array.isArray(assets)) {
      return assetUrl(assets.find((asset) => asset.kind === "thumbnail")) || cleanText(record.thumbnail_url);
    }
    return assetUrl(assets?.thumbnail) || cleanText(record?.thumbnail_url);
  }

  function normalizeCreator(row) {
    const rawCreator = row?.creator && typeof row.creator === "object" ? row.creator : {};
    const slug = cleanText(rawCreator.slug || row?.creator_slug || row?.public_slug);
    const displayName = cleanText(rawCreator.display_name || rawCreator.name || row?.creator_name);
    return slug && displayName ? { slug, displayName } : null;
  }

  function isLocalPreviewSource(source) {
    return ["local-sqlite", "local-sqlite-preview"].includes(cleanText(source).toLowerCase());
  }

  function isAuthoritativeSource(source) {
    return !isLocalPreviewSource(source);
  }

  function responseErrorMessage(payload, fallback) {
    const message = payload?.error?.message
      || (typeof payload?.error === "string" ? payload.error : "")
      || payload?.hint;
    return cleanText(message) || fallback;
  }

  function normalizeApiWork(row, deliverySource = "") {
    const width = Number(row.original_width || row.width || 1);
    const height = Number(row.original_height || row.height || 1);
    const contentType = row.content_type || row.content_category || row.type;
    return {
      id: cleanText(row.id),
      title: cleanText(row.title) || "Untitled Work",
      src: displayUrl(row),
      width,
      height,
      original_width: width,
      original_height: height,
      type: contentTypeLabel(contentType),
      ratio: cleanText(row.ratio_label || ratioLabelFromCode(row.ratio_category_code) || row.ratio) || "1:1",
      ratio_label: cleanText(row.ratio_label),
      series: cleanText(row.series),
      capturedAt: cleanText(row.captured_at),
      captured_at: cleanText(row.captured_at),
      description: cleanText(row.description),
      curatorialNote: cleanText(row.curatorial_note || row.caption),
      curatorial_note: cleanText(row.curatorial_note || row.caption),
      artist_statement: cleanText(row.artist_statement),
      alt_text: cleanText(row.alt_text),
      tags: Array.isArray(row.tags) ? row.tags : [],
      tagGroups: Array.isArray(row.tag_groups) ? row.tag_groups : [],
      tag_groups: Array.isArray(row.tag_groups) ? row.tag_groups : [],
      thumbnail_url: thumbnailUrl(row),
      display_mode: cleanText(row.display_mode),
      original_filename: cleanText(row.original_filename),
      public_exif: row.public_exif && typeof row.public_exif === "object" ? row.public_exif : {},
      visibility: cleanText(row.visibility) || "published",
      sortOrder: Number.isFinite(Number(row.sort_order)) ? Number(row.sort_order) : 0,
      published_at: cleanText(row.published_at),
      creator: normalizeCreator(row),
      deliverySource: cleanText(deliverySource),
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
    const payload = await response.json().catch(() => ({}));
    const source = cleanText(payload.source) || "api";
    if (!response.ok) {
      const error = new Error(responseErrorMessage(payload, `Archive API returned ${response.status}.`));
      error.source = source;
      error.authoritative = isAuthoritativeSource(source);
      throw error;
    }
    const works = (Array.isArray(payload.items) ? payload.items : [])
      .map((row) => normalizeApiWork(row, source))
      .filter((item) => item.id && item.src);
    return {
      works,
      source,
      authoritative: isAuthoritativeSource(source),
      count: Number.isFinite(Number(payload.count)) ? Number(payload.count) : works.length,
    };
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
    let authoritative = false;
    try {
      const result = await fetchArchiveWorks();
      works = result.works;
      source = result.source;
      authoritative = result.authoritative;
      if (authoritative) {
        status = works.length ? "Published works loaded." : "No published works yet.";
      } else if (!works.length) {
        throw new Error("The archive contains no published works.");
      }
    } catch (error) {
      if (error?.authoritative !== false) {
        return {
          works: [],
          source: error.source || "supabase",
          status: error?.message || "Published works are temporarily unavailable.",
          authoritative: true,
          error: true,
        };
      }
      source = "sample";
      status = `${error?.message || "Archive unavailable"} Showing local preview works.`;
      works = (archiveSeedData.sampleItems || []).map(normalizeSampleWork);
    }

    if (!authoritative) {
      try {
        const storedUploads = (await readStoredWorks()).filter((item) => item.visibility === "published" && item.id && item.src);
        const merged = new Map(works.map((item) => [item.id, item]));
        storedUploads.forEach((item) => merged.set(item.id, item));
        works = [...merged.values()];
      } catch {
        // API or sample works remain available when browser storage cannot be read.
      }
    }

    works.sort((a, b) => a.sortOrder - b.sortOrder || a.title.localeCompare(b.title));
    return { works, source, status, authoritative };
  }

  function readIdArray(storage, key) {
    try {
      const parsed = JSON.parse(storage.getItem(key) || "[]");
      return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string" && id) : [];
    } catch {
      return [];
    }
  }

  function readLightboxIds() {
    const current = readIdArray(localStorage, LIGHTBOX_STORAGE_KEY);
    if (current.length || localStorage.getItem(LIGHTBOX_STORAGE_KEY) !== null) {
      return current;
    }
    const migrated = [...new Set(LEGACY_LIGHTBOX_KEYS.flatMap((key) => readIdArray(localStorage, key)))];
    if (migrated.length) {
      writeLightboxIds(migrated);
    }
    return migrated;
  }

  function normalizeIds(ids) {
    return [...new Set((ids || []).filter((id) => typeof id === "string" && id))];
  }

  function readInquirySelectionIds() {
    const lightboxIds = new Set(readLightboxIds());
    return readIdArray(sessionStorage, INQUIRY_SELECTION_STORAGE_KEY).filter((id) => lightboxIds.has(id));
  }

  function writeInquirySelectionIds(ids) {
    const lightboxIds = new Set(readLightboxIds());
    const normalized = normalizeIds(ids).filter((id) => lightboxIds.has(id));
    sessionStorage.setItem(INQUIRY_SELECTION_STORAGE_KEY, JSON.stringify(normalized));
    global.dispatchEvent(new CustomEvent("mt:inquiry-selection-change", { detail: { ids: normalized } }));
    return normalized;
  }

  function pruneInquirySelection(lightboxIds) {
    try {
      const allowed = new Set(lightboxIds);
      const current = readIdArray(sessionStorage, INQUIRY_SELECTION_STORAGE_KEY);
      const next = current.filter((id) => allowed.has(id));
      if (next.length !== current.length) {
        sessionStorage.setItem(INQUIRY_SELECTION_STORAGE_KEY, JSON.stringify(next));
        global.dispatchEvent(new CustomEvent("mt:inquiry-selection-change", { detail: { ids: next } }));
      }
    } catch {
      // Favorite persistence remains available when temporary session storage is blocked.
    }
  }

  function writeLightboxIds(ids, { changedId = "" } = {}) {
    const normalized = normalizeIds(ids);
    localStorage.setItem(LIGHTBOX_STORAGE_KEY, JSON.stringify(normalized));
    pruneInquirySelection(normalized);
    global.dispatchEvent(new CustomEvent("mt:lightbox-change", { detail: { ids: normalized, changedId } }));
    return normalized;
  }

  function toggleLightboxId(id) {
    const ids = readLightboxIds();
    const next = ids.includes(id) ? ids.filter((itemId) => itemId !== id) : [...ids, id];
    writeLightboxIds(next, { changedId: id });
    return { ids: next, added: next.includes(id) };
  }

  function headerIdentity() {
    const current = global.MTPresenceHeaderIdentity;
    if (current && typeof current === "object") return current;
    const bootstrap = document.querySelector("#mt-header-identity");
    try {
      return JSON.parse(bootstrap?.content?.textContent || bootstrap?.textContent || "{}");
    } catch (_error) {
      return {};
    }
  }

  function isAuthenticated() {
    return headerIdentity().authenticated === true;
  }

  function signInHref() {
    const next = `${global.location.pathname}${global.location.search}${global.location.hash}`;
    return `/auth/sign-in?next=${encodeURIComponent(next)}`;
  }

  function requireAuthentication() {
    if (isAuthenticated()) return true;
    global.location.assign(signInHref());
    return false;
  }

  global.MTPresencePublicArchive = {
    LIGHTBOX_STORAGE_KEY,
    INQUIRY_SELECTION_STORAGE_KEY,
    cleanText,
    escapeHtml,
    isAuthoritativeSource,
    isLocalPreviewSource,
    loadPublishedWorks,
    normalizeApiWork,
    ratioCssValue,
    readLightboxIds,
    writeLightboxIds,
    toggleLightboxId,
    isAuthenticated,
    signInHref,
    requireAuthentication,
    readInquirySelectionIds,
    writeInquirySelectionIds,
  };
})(window);
