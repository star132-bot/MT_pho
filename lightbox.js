const publicArchive = window.MTPresencePublicArchive;
const lightboxGallery = document.querySelector("[data-lightbox-gallery]");
const lightboxEmpty = document.querySelector("[data-lightbox-empty]");
const lightboxSummary = document.querySelector("[data-lightbox-summary]");
const lightboxStatus = document.querySelector("[data-lightbox-status]");
const lightboxActions = document.querySelector("[data-lightbox-actions]");
const lightboxToast = document.querySelector("[data-lightbox-toast]");
const inquirySelectionCount = document.querySelector("[data-inquiry-selection-count]");
const selectAllButton = document.querySelector("[data-select-all]");
const clearInquirySelectionButton = document.querySelector("[data-clear-inquiry-selection]");
const contactSelectedButton = document.querySelector("[data-contact-selected]");
const removeAllLightboxButton = document.querySelector("[data-remove-all-lightbox]");
let allWorks = [];
let lightboxWorks = [];
let inquirySelectionIds = new Set();
let toastTimer = null;
let lightboxInitialized = false;
let localLightboxMutation = false;

function showLightboxToast(message, type = "default") {
  if (!lightboxToast) {
    return;
  }
  window.clearTimeout(toastTimer);
  lightboxToast.textContent = message;
  lightboxToast.dataset.type = type;
  lightboxToast.hidden = false;
  lightboxToast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    lightboxToast.classList.remove("is-visible");
    lightboxToast.hidden = true;
  }, 2400);
}

function savedWorks() {
  const byId = new Map(allWorks.map((work) => [work.id, work]));
  return publicArchive.readLightboxIds().map((id) => byId.get(id)).filter(Boolean);
}

function writeLightboxIdsFromThisPage(ids) {
  localLightboxMutation = true;
  try {
    return publicArchive.writeLightboxIds(ids);
  } finally {
    localLightboxMutation = false;
  }
}

function currentInquiryIds() {
  return lightboxWorks.filter((work) => inquirySelectionIds.has(work.id)).map((work) => work.id);
}

function updateLightboxCollectionUi() {
  const count = lightboxWorks.length;
  lightboxSummary.textContent = `${count} saved work${count === 1 ? "" : "s"}.`;
  lightboxActions.hidden = count === 0;
  lightboxEmpty.hidden = count > 0;
  lightboxGallery.hidden = count === 0;
}

function updateInquirySelectionUi() {
  const selectedIds = new Set(currentInquiryIds());
  const count = selectedIds.size;
  const workById = new Map(lightboxWorks.map((work) => [work.id, work]));
  inquirySelectionIds = selectedIds;

  lightboxGallery?.querySelectorAll("[data-lightbox-work-id]").forEach((item) => {
    const id = item.dataset.lightboxWorkId;
    const isSelected = selectedIds.has(id);
    const work = workById.get(id);
    const selectButton = item.querySelector("[data-toggle-inquiry-work]");
    if (item.classList.contains("is-inquiry-selected") !== isSelected) {
      item.classList.toggle("is-inquiry-selected", isSelected);
    }
    const pressedValue = String(isSelected);
    if (selectButton?.getAttribute("aria-pressed") !== pressedValue) {
      selectButton?.setAttribute("aria-pressed", pressedValue);
    }
    const label = `${isSelected ? "Remove" : "Select"} ${work?.title || "this work"} ${isSelected ? "from" : "for"} this inquiry`;
    if (selectButton?.getAttribute("aria-label") !== label) {
      selectButton?.setAttribute("aria-label", label);
    }
  });

  if (inquirySelectionCount) {
    inquirySelectionCount.textContent = `${count} selected`;
  }
  if (selectAllButton) {
    selectAllButton.disabled = lightboxWorks.length === 0 || count === lightboxWorks.length;
  }
  if (clearInquirySelectionButton) {
    clearInquirySelectionButton.disabled = count === 0;
  }
  if (contactSelectedButton) {
    contactSelectedButton.disabled = count === 0;
    contactSelectedButton.textContent = `Contact Artist (${count})`;
  }
}

function persistInquirySelection(ids, { reportError = true } = {}) {
  const allowedIds = new Set(lightboxWorks.map((work) => work.id));
  const normalized = [...new Set(ids)].filter((id) => allowedIds.has(id));
  try {
    const storedIds = publicArchive.writeInquirySelectionIds(normalized);
    inquirySelectionIds = new Set(Array.isArray(storedIds) ? storedIds : normalized);
    updateInquirySelectionUi();
    return true;
  } catch {
    if (reportError) {
      showLightboxToast("Unable to update this inquiry selection.", "error");
    }
    return false;
  }
}

function renderLightbox({ reconcileSelection = true } = {}) {
  lightboxWorks = savedWorks();
  const allowedIds = new Set(lightboxWorks.map((work) => work.id));
  const storedSelection = publicArchive.readInquirySelectionIds();
  inquirySelectionIds = new Set(storedSelection.filter((id) => allowedIds.has(id)));
  if (reconcileSelection && inquirySelectionIds.size !== new Set(storedSelection).size) {
    persistInquirySelection(inquirySelectionIds, { reportError: false });
  }

  lightboxGallery.innerHTML = lightboxWorks
    .map(
      (work, index) => `
        <article class="lightbox-item${inquirySelectionIds.has(work.id) ? " is-inquiry-selected" : ""}" style="--item-delay: ${Math.min(index, 14) * 24}ms;" data-lightbox-work-id="${publicArchive.escapeHtml(work.id)}">
          <button class="lightbox-inquiry-toggle" type="button" data-toggle-inquiry-work aria-pressed="${String(inquirySelectionIds.has(work.id))}" aria-label="${inquirySelectionIds.has(work.id) ? "Remove" : "Select"} ${publicArchive.escapeHtml(work.title)} ${inquirySelectionIds.has(work.id) ? "from" : "for"} this inquiry">
            <span aria-hidden="true"></span>
          </button>
          <a class="lightbox-image-link" href="works.html?work=${encodeURIComponent(work.id)}&from=lightbox" aria-label="View ${publicArchive.escapeHtml(work.title)} in Works">
            <figure style="--display-ratio: ${publicArchive.ratioCssValue(work.ratio)};">
              <img src="${publicArchive.escapeHtml(work.src)}" alt="${publicArchive.escapeHtml(work.title)}" loading="lazy" decoding="async" />
            </figure>
          </a>
          <div class="lightbox-item-copy">
            <div><h2>${publicArchive.escapeHtml(work.title)}</h2><p>${publicArchive.escapeHtml(work.series || `${work.type} / ${work.ratio}`)}</p></div>
            <button type="button" data-remove-lightbox-work aria-label="Remove ${publicArchive.escapeHtml(work.title)} from lightbox">Remove</button>
          </div>
        </article>`,
    )
    .join("");
  lightboxGallery.setAttribute("aria-busy", "false");
  updateLightboxCollectionUi();
  updateInquirySelectionUi();
}

async function initLightbox() {
  let archiveLoaded = false;
  try {
    const result = await publicArchive.loadPublishedWorks();
    allWorks = result.works;
    archiveLoaded = result.error !== true;
    lightboxStatus.textContent = result.source === "api" ? "" : result.status;
    lightboxStatus.hidden = result.source === "api";
  } catch {
    lightboxStatus.textContent = "Unable to load the archive. Try again from Works.";
    lightboxStatus.dataset.state = "error";
  }
  renderLightbox({ reconcileSelection: archiveLoaded });
  lightboxInitialized = true;
}

lightboxGallery?.addEventListener("click", (event) => {
  const selectionButton = event.target.closest("[data-toggle-inquiry-work]");
  if (selectionButton) {
    event.preventDefault();
    event.stopPropagation();
    const id = selectionButton.closest("[data-lightbox-work-id]")?.dataset.lightboxWorkId;
    if (!id) {
      return;
    }
    const nextIds = new Set(inquirySelectionIds);
    if (nextIds.has(id)) {
      nextIds.delete(id);
    } else {
      nextIds.add(id);
    }
    persistInquirySelection(nextIds);
    return;
  }

  const removeButton = event.target.closest("[data-remove-lightbox-work]");
  if (!removeButton) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  const item = removeButton.closest("[data-lightbox-work-id]");
  const id = item?.dataset.lightboxWorkId;
  if (!id) {
    return;
  }
  try {
    writeLightboxIdsFromThisPage(publicArchive.readLightboxIds().filter((workId) => workId !== id));
  } catch {
    showLightboxToast("Unable to remove this work from your lightbox.", "error");
    return;
  }
  lightboxWorks = lightboxWorks.filter((work) => work.id !== id);
  inquirySelectionIds.delete(id);
  item.remove();
  updateLightboxCollectionUi();
  updateInquirySelectionUi();
  showLightboxToast("Removed from your lightbox.");
});

selectAllButton?.addEventListener("click", (event) => {
  event.preventDefault();
  persistInquirySelection(lightboxWorks.map((work) => work.id));
});

clearInquirySelectionButton?.addEventListener("click", (event) => {
  event.preventDefault();
  if (persistInquirySelection([])) {
    showLightboxToast("Inquiry selection cleared.");
  }
});

contactSelectedButton?.addEventListener("click", (event) => {
  event.preventDefault();
  const ids = currentInquiryIds();
  if (!ids.length) {
    return;
  }
  const params = new URLSearchParams({ source: "lightbox" });
  ids.forEach((id) => params.append("work", id));
  window.location.assign(`/contact.html?${params.toString()}`);
});

removeAllLightboxButton?.addEventListener("click", (event) => {
  event.preventDefault();
  if (!window.confirm("Remove every saved work from this browser's lightbox? This cannot be undone.")) {
    return;
  }
  try {
    writeLightboxIdsFromThisPage([]);
  } catch {
    showLightboxToast("Unable to remove all works from your lightbox.", "error");
    return;
  }
  lightboxWorks = [];
  inquirySelectionIds = new Set();
  lightboxGallery.replaceChildren();
  updateLightboxCollectionUi();
  updateInquirySelectionUi();
  showLightboxToast("All works removed from your lightbox.");
});

function reconcileInquirySelectionFromSession(ids = publicArchive.readInquirySelectionIds()) {
  const allowedIds = new Set(lightboxWorks.map((work) => work.id));
  inquirySelectionIds = new Set(ids.filter((id) => allowedIds.has(id)));
  updateInquirySelectionUi();
}

function reconcileLightboxCollection({ announce = false } = {}) {
  if (!lightboxInitialized) {
    return;
  }
  const availableIds = new Set(allWorks.map((work) => work.id));
  const nextIds = publicArchive.readLightboxIds().filter((id) => availableIds.has(id));
  const currentIds = lightboxWorks.map((work) => work.id);
  const unchanged = nextIds.length === currentIds.length
    && nextIds.every((id, index) => id === currentIds[index]);
  if (unchanged) {
    reconcileInquirySelectionFromSession();
    return;
  }
  renderLightbox();
  persistInquirySelection(inquirySelectionIds, { reportError: false });
  if (announce) {
    showLightboxToast("Lightbox updated in another tab.");
  }
}

window.addEventListener("mt:lightbox-change", () => {
  if (!localLightboxMutation) {
    reconcileLightboxCollection();
  }
});

window.addEventListener("storage", (event) => {
  if (event.key === publicArchive.LIGHTBOX_STORAGE_KEY) {
    reconcileLightboxCollection({ announce: true });
  }
});

window.addEventListener("mt:inquiry-selection-change", (event) => {
  const ids = Array.isArray(event.detail?.ids) ? event.detail.ids : publicArchive.readInquirySelectionIds();
  reconcileInquirySelectionFromSession(ids);
});

window.addEventListener("pageshow", () => {
  reconcileLightboxCollection();
  reconcileInquirySelectionFromSession();
});

initLightbox();
