(function initializeSeriesPosters(global) {
  // Requirement 06: the Works page shows two posters, 此间留彩 and 此间留灰.
  // The poster images are fixed site artwork (assets/art/poster-*.jpg) until the
  // photographer supplies finished posters (question 2); only the counts are live.
  const archive = global.MTPresencePublicArchive;
  const i18n = global.MTPresenceI18n;
  const t = (text) => (i18n ? i18n.t(text) : text);
  const statusBox = document.querySelector("[data-series-status-box]");
  const status = document.querySelector("[data-series-status]");
  const retry = document.querySelector("[data-series-retry]");
  const SERIES_TYPES = { colour: "Concrete", grey: "Abstract" };

  function countLabel(count) {
    if (i18n?.language === "zh") return `${count} 件作品`;
    return `${count} ${count === 1 ? "work" : "works"}`;
  }

  // States: loading, ready, empty (no published works) and error (with retry);
  // an error is never presented as an empty archive.
  function setState(state, message = "") {
    statusBox.dataset.seriesState = state;
    statusBox.hidden = state === "ready";
    status.textContent = message;
    retry.hidden = state !== "error";
  }

  async function start() {
    setState("loading", t("Loading works"));
    const result = archive ? await archive.loadPublishedWorks() : { error: true };
    if (result.error) {
      document.querySelectorAll("[data-series-poster]").forEach((poster) => {
        poster.hidden = true;
      });
      setState("error", t(result.status || "Works are temporarily unavailable."));
      return;
    }
    let shown = 0;
    document.querySelectorAll("[data-series-poster]").forEach((poster) => {
      const works = result.works.filter((work) => work.type === SERIES_TYPES[poster.dataset.series]);
      poster.hidden = !works.length;
      if (!works.length) return;
      poster.querySelector("[data-series-count]").textContent = countLabel(works.length);
      shown += 1;
    });
    if (shown) setState("ready");
    else setState("empty", t("No works in this series yet."));
  }

  retry.addEventListener("click", start);
  start();
})(window);
