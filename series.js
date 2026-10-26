(function initializeSeries(global) {
  // Requirement 06 prototype: two posters, 此间留彩 and 此间留灰. Until the
  // photographer supplies finished posters (question 2), each poster uses the
  // first work of its series and is laid out by the page.
  const archive = global.MTPresencePublicArchive;
  const i18n = global.MTPresenceI18n;
  const t = (text) => (i18n ? i18n.t(text) : text);
  const status = document.querySelector("[data-series-status]");
  const SERIES_TYPES = { colour: "Concrete", grey: "Abstract" };

  function countLabel(count) {
    if (i18n?.language === "zh") return `${count} 件作品`;
    return `${count} ${count === 1 ? "work" : "works"}`;
  }

  async function start() {
    const result = archive ? await archive.loadPublishedWorks() : { error: true };
    if (result.error) {
      status.textContent = t("Works are temporarily unavailable.");
      return;
    }
    let shown = 0;
    document.querySelectorAll("[data-series-poster]").forEach((poster) => {
      const key = poster.dataset.series;
      const works = result.works.filter((work) => work.type === SERIES_TYPES[key]);
      if (!works.length) return;
      const cover = works[0];
      const image = poster.querySelector("[data-series-image]");
      image.src = cover.src;
      poster.querySelector("[data-series-count]").textContent = countLabel(works.length);
      poster.hidden = false;
      shown += 1;
    });
    status.hidden = shown > 0;
    if (!shown) status.textContent = t("No works in this series yet.");
  }

  start();
})(window);
