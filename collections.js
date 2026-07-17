const publicArchive = window.MTPresencePublicArchive;
const seriesDefinitions = Array.isArray(window.MTPresenceSeriesData) ? window.MTPresenceSeriesData : [];
const seriesGrid = document.querySelector("[data-series-grid]");
const seriesStatus = document.querySelector("[data-series-status]");
const seriesCount = document.querySelector("[data-series-count]");
const seriesEmpty = document.querySelector("[data-series-empty]");
const seriesIndex = document.querySelector("[data-series-index]");
const seriesDetail = document.querySelector("[data-series-detail]");
const seriesFilters = document.querySelector("[data-series-filters]");
let seriesModels = [];
let activeSeriesFilter = "all";

function workMatchesSeries(work, definition) {
  const explicit = definition.workIds.includes(work.id);
  const seriesValue = publicArchive.cleanText(work.series).toLowerCase();
  return explicit || seriesValue === definition.title.toLowerCase() || seriesValue === definition.slug;
}

function buildSeriesModels(works) {
  return seriesDefinitions
    .map((definition) => {
      const order = new Map(definition.workIds.map((id, index) => [id, index]));
      const seriesWorks = works
        .filter((work) => workMatchesSeries(work, definition))
        .sort((a, b) => (order.get(a.id) ?? 9999) - (order.get(b.id) ?? 9999) || a.sortOrder - b.sortOrder);
      const cover = seriesWorks.find((work) => work.id === definition.coverId) || seriesWorks[0] || null;
      return { ...definition, works: seriesWorks, cover };
    })
    .filter((series) => series.works.length && series.cover);
}

function filteredSeries() {
  if (activeSeriesFilter === "all") {
    return seriesModels;
  }
  return seriesModels.filter((series) => series.status.toLowerCase() === activeSeriesFilter);
}

function renderSeriesIndex() {
  const visibleSeries = filteredSeries();
  seriesCount.textContent = `${visibleSeries.length} of ${seriesModels.length} series.`;
  seriesEmpty.hidden = visibleSeries.length > 0;
  seriesGrid.hidden = visibleSeries.length === 0;
  seriesGrid.innerHTML = visibleSeries
    .map(
      (series, index) => `
        <a class="series-card" style="--item-delay: ${index * 55}ms;" href="collections.html?series=${encodeURIComponent(series.slug)}" data-series-slug="${publicArchive.escapeHtml(series.slug)}">
          <figure><img src="${publicArchive.escapeHtml(series.cover.src)}" alt="${publicArchive.escapeHtml(series.cover.title)}" loading="${index ? "lazy" : "eager"}" decoding="async" /></figure>
          <div class="series-card-copy">
            <div><p>${publicArchive.escapeHtml(series.years)} / ${publicArchive.escapeHtml(series.status)}</p><h2>${publicArchive.escapeHtml(series.title)}</h2></div>
            <p>${publicArchive.escapeHtml(series.synopsis)}</p>
            <span>${series.works.length} works</span>
          </div>
        </a>`,
    )
    .join("");
  seriesGrid.setAttribute("aria-busy", "false");
}

function renderSeriesDetail(slug, { updateHistory = false } = {}) {
  const series = seriesModels.find((item) => item.slug === slug);
  if (!series) {
    seriesIndex.hidden = false;
    seriesDetail.hidden = true;
    return false;
  }

  seriesIndex.hidden = true;
  seriesDetail.hidden = false;
  document.querySelector("[data-series-detail-title]").textContent = series.title;
  document.querySelector("[data-series-detail-meta]").textContent = `${series.years} / ${series.status} / ${series.location}`;
  document.querySelector("[data-series-detail-synopsis]").textContent = series.synopsis;
  document.querySelector("[data-series-detail-statement]").textContent = series.statement;
  document.querySelector("[data-series-inquire]").href = `contact.html?source=series&series=${encodeURIComponent(series.slug)}`;
  document.querySelector("[data-series-work-grid]").innerHTML = series.works
    .map(
      (work, index) => `
        <a class="series-work" style="--item-delay: ${Math.min(index, 14) * 30}ms;" href="works.html?work=${encodeURIComponent(work.id)}&from=series&series=${encodeURIComponent(series.slug)}">
          <figure style="--display-ratio: ${publicArchive.ratioCssValue(work.ratio)};"><img src="${publicArchive.escapeHtml(work.src)}" alt="${publicArchive.escapeHtml(work.title)}" loading="lazy" decoding="async" /></figure>
          <div><span>${String(index + 1).padStart(2, "0")}</span><h2>${publicArchive.escapeHtml(work.title)}</h2></div>
        </a>`,
    )
    .join("");

  const currentIndex = seriesModels.findIndex((item) => item.slug === series.slug);
  const nextSeries = seriesModels[(currentIndex + 1) % seriesModels.length];
  document.querySelector("[data-series-next]").innerHTML = nextSeries && nextSeries.slug !== series.slug
    ? `<span>Next Series</span><a href="collections.html?series=${encodeURIComponent(nextSeries.slug)}">${publicArchive.escapeHtml(nextSeries.title)}</a>`
    : "";
  if (updateHistory) {
    history.pushState({ series: series.slug }, "", `collections.html?series=${encodeURIComponent(series.slug)}`);
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
  return true;
}

async function initSeries() {
  try {
    const result = await publicArchive.loadPublishedWorks();
    seriesModels = buildSeriesModels(result.works);
    seriesStatus.textContent = result.source === "api" ? "" : result.status;
    seriesStatus.hidden = result.source === "api";
  } catch {
    seriesStatus.textContent = "Unable to load the archive.";
    seriesStatus.dataset.state = "error";
  }
  renderSeriesIndex();
  const slug = new URLSearchParams(window.location.search).get("series");
  if (slug) {
    renderSeriesDetail(slug);
  }
}

seriesFilters?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-series-filter]");
  if (!button) {
    return;
  }
  activeSeriesFilter = button.dataset.seriesFilter;
  seriesFilters.querySelectorAll("button").forEach((item) => {
    const active = item === button;
    item.classList.toggle("is-active", active);
    item.setAttribute("aria-pressed", String(active));
  });
  renderSeriesIndex();
});

seriesGrid?.addEventListener("click", (event) => {
  const link = event.target.closest("[data-series-slug]");
  if (!link) {
    return;
  }
  event.preventDefault();
  renderSeriesDetail(link.dataset.seriesSlug, { updateHistory: true });
});

document.querySelector("[data-series-back]")?.addEventListener("click", (event) => {
  event.preventDefault();
  history.pushState({}, "", "collections.html");
  seriesDetail.hidden = true;
  seriesIndex.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
});

window.addEventListener("popstate", () => {
  const slug = new URLSearchParams(window.location.search).get("series");
  if (!slug || !renderSeriesDetail(slug)) {
    seriesDetail.hidden = true;
    seriesIndex.hidden = false;
  }
});

initSeries();
