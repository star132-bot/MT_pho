(function initializeWorkDetail() {
  const publicArchive = window.MTPresencePublicArchive;
  const main = document.querySelector("[data-work-detail-main]");
  const state = document.querySelector("[data-work-detail-state]");
  const layout = document.querySelector("[data-work-detail-layout]");
  const image = document.querySelector("[data-work-detail-image]");
  const title = document.querySelector("[data-work-detail-title]");
  const description = document.querySelector("[data-work-detail-description]");
  const position = document.querySelector("[data-work-detail-position]");
  const previous = document.querySelector("[data-work-detail-prev]");
  const next = document.querySelector("[data-work-detail-next]");
  const save = document.querySelector("[data-work-detail-save]");
  const inquire = document.querySelector("[data-work-detail-inquire]");
  const download = document.querySelector("[data-work-detail-download]");
  const metadata = document.querySelector("[data-work-detail-metadata]");
  const tagsSection = document.querySelector("[data-work-detail-tags-section]");
  const tags = document.querySelector("[data-work-detail-tags]");
  const relatedSection = document.querySelector("[data-work-detail-related-section]");
  const related = document.querySelector("[data-work-detail-related]");
  const toast = document.querySelector("[data-work-detail-toast]");
  let works = [];
  let work = null;
  let toastTimer = null;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function showToast(message, tone = "default") {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.dataset.type = tone;
    toast.hidden = false;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
      toast.hidden = true;
    }, 2200);
  }

  function workHref(item) {
    return `/work.html?id=${encodeURIComponent(item.id)}`;
  }

  function flatTags(item) {
    const direct = Array.isArray(item.tags) ? item.tags : [];
    const grouped = Array.isArray(item.tagGroups)
      ? item.tagGroups.flatMap((group) => Array.isArray(group?.tags) ? group.tags : [])
      : Array.isArray(item.tag_groups)
        ? item.tag_groups.flatMap((group) => Array.isArray(group?.tags) ? group.tags : [])
        : [];
    return [...new Set([...direct, ...grouped].map(cleanText).filter(Boolean))].slice(0, 12);
  }

  function metadataEntry(label, value) {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = cleanText(value) || "Undated";
    row.append(term, detail);
    return row;
  }

  function setSavedState() {
    const active = publicArchive.readLightboxIds().includes(work.id);
    save.classList.toggle("is-active", active);
    save.setAttribute("aria-pressed", String(active));
    save.querySelector("span").textContent = active ? "Saved" : "Add to Lightbox";
  }

  function relatedScore(candidate) {
    let score = candidate.type === work.type ? 3 : 0;
    score += candidate.ratio === work.ratio ? 2 : 0;
    const currentTags = new Set(flatTags(work).map((tag) => tag.toLowerCase()));
    score += flatTags(candidate).filter((tag) => currentTags.has(tag.toLowerCase())).length;
    return score;
  }

  function renderRelated() {
    const candidates = works
      .filter((candidate) => candidate.id !== work.id)
      .map((candidate) => ({ candidate, score: relatedScore(candidate) }))
      .sort((left, right) => right.score - left.score)
      .slice(0, 4)
      .map((entry) => entry.candidate);
    related.replaceChildren();
    candidates.forEach((candidate) => {
      const link = document.createElement("a");
      link.href = workHref(candidate);
      link.setAttribute("aria-label", `View ${candidate.title}`);
      const thumbnail = document.createElement("img");
      thumbnail.src = candidate.thumbnail_url || candidate.src;
      thumbnail.alt = "";
      thumbnail.loading = "lazy";
      thumbnail.decoding = "async";
      const label = document.createElement("span");
      label.textContent = candidate.title;
      link.append(thumbnail, label);
      related.append(link);
    });
    relatedSection.hidden = candidates.length === 0;
  }

  function render() {
    const index = works.findIndex((item) => item.id === work.id);
    const previousWork = works[(index - 1 + works.length) % works.length];
    const nextWork = works[(index + 1) % works.length];
    image.src = work.src;
    image.alt = cleanText(work.alt_text) || work.title;
    title.textContent = work.title;
    description.textContent = cleanText(work.description || work.curatorialNote || work.curatorial_note)
      || "A study of surface, light, distance, and the time required to look.";
    position.textContent = `${String(index + 1).padStart(2, "0")} / ${String(works.length).padStart(2, "0")}`;
    previous.href = workHref(previousWork);
    next.href = workHref(nextWork);
    previous.hidden = works.length < 2;
    next.hidden = works.length < 2;
    inquire.href = `/contact.html?source=work&work=${encodeURIComponent(work.id)}`;
    metadata.replaceChildren(
      metadataEntry("Type", work.type),
      metadataEntry("Ratio", work.ratio),
      metadataEntry("Size", `${work.original_width || work.width || "Unknown"} x ${work.original_height || work.height || "Unknown"}`),
      metadataEntry("Captured", cleanText(work.capturedAt || work.captured_at) || "Undated"),
    );
    const workTags = flatTags(work);
    tags.replaceChildren();
    workTags.forEach((value) => {
      const tag = document.createElement("span");
      tag.textContent = value;
      tags.append(tag);
    });
    tagsSection.hidden = workTags.length === 0;
    renderRelated();
    setSavedState();
    document.title = `${work.title} | MT Presence`;
    state.hidden = true;
    layout.hidden = false;
    main.setAttribute("aria-busy", "false");
  }

  save?.addEventListener("click", () => {
    if (!work) return;
    const wasSaved = publicArchive.readLightboxIds().includes(work.id);
    setSavedState();
    try {
      const result = publicArchive.toggleLightboxId(work.id);
      setSavedState();
      showToast(result.added ? "Saved to Lightbox" : "Removed from Lightbox");
    } catch (_error) {
      const ids = publicArchive.readLightboxIds();
      if (wasSaved && !ids.includes(work.id)) publicArchive.writeLightboxIds([...ids, work.id]);
      if (!wasSaved && ids.includes(work.id)) publicArchive.writeLightboxIds(ids.filter((id) => id !== work.id));
      setSavedState();
      showToast("Unable to update your lightbox.", "error");
    }
  });

  download?.addEventListener("click", () => {
    if (!work?.src) return;
    const link = document.createElement("a");
    link.href = work.src;
    link.download = `${cleanText(work.title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "mt-presence-work"}.jpg`;
    document.body.append(link);
    link.click();
    link.remove();
    showToast("Download started.");
  });

  window.addEventListener("mt:lightbox-change", setSavedState);
  window.addEventListener("storage", (event) => {
    if (event.key === publicArchive.LIGHTBOX_STORAGE_KEY && work) setSavedState();
  });

  async function initialize() {
    const requestedId = cleanText(new URLSearchParams(window.location.search).get("id") || new URLSearchParams(window.location.search).get("work"));
    try {
      const result = await publicArchive.loadPublishedWorks();
      works = result.works;
      work = works.find((item) => item.id === requestedId) || (!requestedId ? works[0] : null);
      if (!work) throw new Error(works.length ? "This work is unavailable." : "No published works are available.");
      render();
    } catch (error) {
      state.querySelector("h1").textContent = "Work unavailable";
      const message = document.createElement("p");
      message.textContent = error.message || "This work cannot be loaded.";
      const link = document.createElement("a");
      link.className = "button button-primary";
      link.href = "/works.html";
      link.textContent = "Return to Works";
      state.append(message, link);
      main.setAttribute("aria-busy", "false");
    }
  }

  initialize();
})();
