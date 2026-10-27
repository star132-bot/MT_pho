(function initializeGlobalHeader() {
  // Visitor header (docs/product/implementation-plan-2026-10-21.md, design in
  // design/site-mockups-v2): a letter-spaced wordmark, four small text links,
  // a search icon that opens a quiet search line, and a plain "中 / EN"
  // language toggle. Visitors never sign in, so there are no account controls.
  const header = document.querySelector("[data-global-header]");
  if (!header || header.dataset.globalHeaderReady === "true") return;

  const SEARCH_DELAY_MS = 260;
  const SEARCH_LIMIT = 6;
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const i18n = window.MTPresenceI18n;
  const t = (text) => (i18n ? i18n.t(text) : text);
  let searchTimer = null;
  let searchRequest = null;
  let searchItems = null;
  let activeSuggestion = -1;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function element(tag, className, attributes = {}) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    return node;
  }

  function icon(paths) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    paths.forEach(([tag, attributes]) => {
      const shape = document.createElementNS(svg.namespaceURI, tag);
      Object.entries(attributes).forEach(([name, value]) => shape.setAttribute(name, value));
      svg.append(shape);
    });
    return svg;
  }

  function routeIsCurrent(route) {
    if (route === "home") return path === "/" || path === "/index.html";
    if (route === "works") return path === "/works.html";
    if (route === "contact") return path === "/contact.html";
    return false;
  }

  // ----- Markup -------------------------------------------------------------

  const brand = element("a", "mt-brand", { href: "/", "aria-label": "MT Presence home" });
  brand.textContent = "MT Presence";

  const navigation = element("nav", "mt-nav", { id: "public-site-navigation", "aria-label": "Primary" });
  navigation.dataset.publicNav = "";
  const links = element("div", "mt-nav-links");
  // About is part of the homepage (requirement 05).
  [["home", "Home", "/"], ["works", "Works", "/works.html"], ["about", "About", "/#about"], ["contact", "Contact", "/contact.html"]]
    .forEach(([route, label, href]) => {
      const link = element("a", "mt-nav-link", { href });
      link.dataset.globalRoute = route;
      link.textContent = label;
      if (routeIsCurrent(route)) link.setAttribute("aria-current", "page");
      links.append(link);
    });

  const searchToggle = element("button", "mt-icon-button", {
    type: "button",
    "aria-label": "Search works",
    "aria-expanded": "false",
    "aria-controls": "global-header-search",
  });
  searchToggle.dataset.globalSearchToggle = "";
  searchToggle.append(icon([["circle", { cx: "11", cy: "11", r: "6.5" }], ["path", { d: "m16 16 4 4" }]]));

  const language = element("div", "mt-language", { role: "group", "aria-label": "Language" });
  language.dataset.i18nSkip = "";
  [["zh", "中"], ["en", "EN"]].forEach(([code, label], index) => {
    if (index) {
      const divider = element("span", "mt-language-divider", { "aria-hidden": "true" });
      divider.textContent = "/";
      language.append(divider);
    }
    const button = element("button", "mt-language-option", {
      type: "button",
      lang: code === "zh" ? "zh-CN" : "en",
      "aria-label": code === "zh" ? "中文" : "English",
      "aria-pressed": String((i18n?.language || "en") === code),
    });
    button.textContent = label;
    button.addEventListener("click", () => i18n?.setLanguage(code));
    language.append(button);
  });

  const tools = element("div", "mt-nav-tools");
  tools.append(searchToggle, language);
  navigation.append(links, tools);

  const menuToggle = element("button", "mt-menu-toggle", {
    type: "button",
    "aria-label": "Open navigation",
    "aria-controls": "public-site-navigation",
    "aria-expanded": "false",
  });
  menuToggle.dataset.publicNavToggle = "";
  menuToggle.append(element("span", "mt-menu-toggle-line"), element("span", "mt-menu-toggle-line"));

  const search = element("form", "mt-search", { id: "global-header-search", role: "search" });
  search.noValidate = true;
  search.hidden = true;
  search.dataset.globalSearch = "";
  const searchLabel = element("label", "visually-hidden", { for: "global-header-search-input" });
  searchLabel.textContent = "Search works, artists, and tags";
  const input = element("input", "mt-search-input", {
    id: "global-header-search-input",
    type: "search",
    inputmode: "search",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: "Search works, artists, tags",
    "aria-autocomplete": "list",
    "aria-controls": "global-header-search-results",
    "aria-expanded": "false",
  });
  input.dataset.globalSearchInput = "";
  const results = element("div", "mt-search-results", {
    id: "global-header-search-results",
    role: "listbox",
    "aria-label": "Search suggestions",
  });
  results.dataset.globalSearchResults = "";
  results.hidden = true;
  search.append(searchLabel, input, results);

  header.classList.add("mt-header");
  header.replaceChildren(brand, navigation, menuToggle, search);
  header.dataset.globalHeaderReady = "true";

  // Over a full-bleed photograph the header is transparent until the visitor
  // scrolls past the first screen.
  if (header.dataset.globalHeaderTheme === "overlay") {
    const syncScrolled = () => header.classList.toggle("is-scrolled", window.scrollY > window.innerHeight * 0.82);
    window.addEventListener("scroll", syncScrolled, { passive: true });
    window.addEventListener("resize", syncScrolled);
    syncScrolled();
  }

  // ----- Search -------------------------------------------------------------

  function openSearch() {
    search.hidden = false;
    header.classList.add("is-search-open");
    searchToggle.setAttribute("aria-expanded", "true");
    searchToggle.setAttribute("aria-label", t("Close search"));
    input.focus();
  }

  function closeSearch({ restoreFocus = false } = {}) {
    closeSearchResults();
    search.hidden = true;
    header.classList.remove("is-search-open");
    searchToggle.setAttribute("aria-expanded", "false");
    searchToggle.setAttribute("aria-label", t("Search works"));
    if (restoreFocus) searchToggle.focus();
  }

  function closeSearchResults() {
    activeSuggestion = -1;
    results.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function setSearchMessage(message, tone = "default") {
    results.replaceChildren();
    const status = element("p", "mt-search-status");
    status.dataset.tone = tone;
    status.textContent = message;
    results.append(status);
    results.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function flattenedTags(item) {
    const direct = Array.isArray(item.tags) ? item.tags : [];
    const grouped = Array.isArray(item.tag_groups)
      ? item.tag_groups.flatMap((group) => (Array.isArray(group?.tags) ? group.tags : []))
      : [];
    return [...direct, ...grouped].map(cleanText).filter(Boolean);
  }

  function itemSearchText(item) {
    return [item.title, item.series, item.content_type, item.type, item.ratio_label, item.ratio, item.creator?.display_name, ...flattenedTags(item)]
      .map(cleanText).join(" ").toLocaleLowerCase();
  }

  async function loadSearchItems() {
    if (searchItems) return searchItems;
    if (searchRequest) return searchRequest;
    searchRequest = fetch("/api/archive/images", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error?.message || payload.error || "Search is unavailable.");
      searchItems = Array.isArray(payload.items) ? payload.items : [];
      return searchItems;
    }).finally(() => {
      searchRequest = null;
    });
    return searchRequest;
  }

  // Works are viewed one at a time in the exhibition (requirement 07).
  function suggestionHref(item) {
    const category = cleanText(item.content_type || item.content_category || item.type).toLowerCase();
    const params = new URLSearchParams({ series: category === "abstract" ? "grey" : "colour", work: cleanText(item.id) });
    return `/exhibition.html?${params.toString()}`;
  }

  function seriesName(item) {
    const category = cleanText(item.content_type || item.content_category || item.type).toLowerCase();
    return category === "abstract" ? "此间留灰" : "此间留彩";
  }

  function setActiveSuggestion(index) {
    const options = [...results.querySelectorAll("[role='option']")];
    if (!options.length) return;
    activeSuggestion = (index + options.length) % options.length;
    options.forEach((option, optionIndex) => option.classList.toggle("is-active", optionIndex === activeSuggestion));
    input.setAttribute("aria-activedescendant", options[activeSuggestion].id);
    options[activeSuggestion].scrollIntoView({ block: "nearest" });
  }

  function renderSearchSuggestions(items) {
    results.replaceChildren();
    activeSuggestion = -1;
    if (!items.length) {
      setSearchMessage("No matching works.", "empty");
      return;
    }
    items.forEach((item, index) => {
      const link = element("a", "mt-search-result", { id: `global-search-option-${index}`, role: "option", href: suggestionHref(item) });
      link.dataset.i18nSkip = "";
      const title = element("strong");
      title.textContent = cleanText(item.title) || "Untitled work";
      const details = element("span");
      details.textContent = seriesName(item);
      link.append(title, details);
      results.append(link);
    });
    results.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  async function updateSearch(query) {
    if (!query) {
      closeSearchResults();
      return;
    }
    setSearchMessage("Searching archive…", "loading");
    try {
      const normalized = query.toLocaleLowerCase();
      const items = (await loadSearchItems())
        .filter((item) => item?.id && itemSearchText(item).includes(normalized))
        .slice(0, SEARCH_LIMIT);
      if (cleanText(input.value) !== query) return;
      renderSearchSuggestions(items);
    } catch (_error) {
      if (cleanText(input.value) === query) setSearchMessage("Search is temporarily unavailable.", "error");
    }
  }

  function scheduleSearch(immediate = false) {
    window.clearTimeout(searchTimer);
    const query = cleanText(input.value);
    if (immediate) updateSearch(query);
    else searchTimer = window.setTimeout(() => updateSearch(query), SEARCH_DELAY_MS);
  }

  searchToggle.addEventListener("click", () => (search.hidden ? openSearch() : closeSearch({ restoreFocus: true })));
  input.addEventListener("input", () => scheduleSearch());
  input.addEventListener("keydown", (event) => {
    const options = [...results.querySelectorAll("[role='option']")];
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && options.length && !results.hidden) {
      event.preventDefault();
      setActiveSuggestion(activeSuggestion + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeSearch({ restoreFocus: true });
    }
  });

  search.addEventListener("submit", (event) => {
    event.preventDefault();
    const options = [...results.querySelectorAll("[role='option']")];
    const chosen = options[activeSuggestion] || options[0];
    if (chosen && !results.hidden) window.location.assign(chosen.href);
    else scheduleSearch(true);
  });

  document.addEventListener("pointerdown", (event) => {
    if (!search.hidden && !header.contains(event.target)) closeSearch();
  });
})();
