(function initializeGlobalHeader() {
  const header = document.querySelector("[data-global-header]");
  if (!header || header.dataset.globalHeaderReady === "true") return;

  const SEARCH_DELAY_MS = 260;
  const SEARCH_LIMIT = 6;
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const worksPage = path === "/works.html";
  // Visitors never sign in, so public pages carry no account controls and the
  // server renders them without an identity slot. Staff pages (/admin,
  // settings) keep the slot for the account menu and sign-out.
  const VISITOR_PATHS = new Set([
    "/", "/index.html", "/works.html", "/work.html", "/about.html",
    "/contact.html", "/privacy.html", "/terms.html",
  ]);
  const visitorPage = VISITOR_PATHS.has(path);
  const identitySlot = header.querySelector("[data-header-identity-slot]");
  if (!identitySlot && !visitorPage) return;
  let searchTimer = null;
  let searchRequest = null;
  let searchItems = null;
  let activeSuggestion = -1;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function routeIsCurrent(route) {
    if (route === "home") return path === "/" || path === "/index.html";
    if (route === "works") return worksPage || path === "/work.html";
    if (route === "about") return path === "/about.html";
    if (route === "contact") return path === "/contact.html";
    return false;
  }

  function createBrand() {
    const brand = document.createElement("a");
    brand.className = "brand-mark global-header-brand";
    brand.href = "/";
    brand.setAttribute("aria-label", "MT Presence home");
    const mark = document.createElement("span");
    mark.textContent = "MT";
    const name = document.createElement("span");
    name.textContent = "Presence";
    brand.append(mark, name);
    return brand;
  }

  function searchIcon() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("global-header-search-icon");
    const circle = document.createElementNS(svg.namespaceURI, "circle");
    circle.setAttribute("cx", "11");
    circle.setAttribute("cy", "11");
    circle.setAttribute("r", "6.5");
    const line = document.createElementNS(svg.namespaceURI, "path");
    line.setAttribute("d", "m16 16 4 4");
    svg.append(circle, line);
    return svg;
  }

  function createSearch() {
    const form = document.createElement("form");
    form.className = "global-header-search";
    form.dataset.globalSearch = "";
    form.setAttribute("role", "search");
    form.noValidate = true;

    const label = document.createElement("label");
    label.className = "visually-hidden";
    label.htmlFor = "global-header-search-input";
    label.textContent = "Search works, artists, and tags";

    const input = document.createElement("input");
    input.id = "global-header-search-input";
    input.className = "global-header-search-input";
    input.type = "search";
    input.inputMode = "search";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "Search works, artists, tags";
    input.dataset.globalSearchInput = "";
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "global-header-search-results");
    input.setAttribute("aria-expanded", "false");
    if (worksPage) input.value = cleanText(new URLSearchParams(window.location.search).get("q"));

    const submit = document.createElement("button");
    submit.className = "global-header-search-submit";
    submit.type = "submit";
    submit.dataset.globalSearchSubmit = "";
    submit.setAttribute("aria-label", "Search the archive");
    submit.append(searchIcon());

    const results = document.createElement("div");
    results.id = "global-header-search-results";
    results.className = "global-header-search-results";
    results.dataset.globalSearchResults = "";
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-label", "Search suggestions");
    results.hidden = true;

    form.append(label, input, submit, results);
    return form;
  }

  function createNavigation() {
    const nav = document.createElement("nav");
    nav.id = "public-site-navigation";
    nav.className = "site-nav public-site-nav global-header-nav";
    nav.dataset.publicNav = "";
    nav.setAttribute("aria-label", "Primary");
    const routes = [
      ["home", "Home", "/"],
      ["works", "Works", "/works.html"],
      ["about", "About", "/about.html"],
      ["contact", "Contact", "/contact.html"],
    ];
    routes.forEach(([route, label, href]) => {
      const link = document.createElement("a");
      link.href = href;
      link.dataset.globalRoute = route;
      if (routeIsCurrent(route)) link.setAttribute("aria-current", "page");
      link.textContent = label;
      nav.append(link);
    });
    const languageSwitch = createLanguageSwitch();
    if (languageSwitch) nav.append(languageSwitch);
    return nav;
  }

  // English / 中文 switch for visitors. The choice is remembered and applied
  // by i18n.js, which translates the page on load.
  function createLanguageSwitch() {
    const i18n = window.MTPresenceI18n;
    if (!visitorPage || !i18n) return null;
    const select = document.createElement("select");
    select.className = "global-header-language";
    select.dataset.languageSwitch = "";
    select.setAttribute("aria-label", "Language");
    [["en", "English"], ["zh", "中文"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === i18n.language;
      select.append(option);
    });
    select.addEventListener("change", () => i18n.setLanguage(select.value));
    return select;
  }

  function createNavigationToggle() {
    const button = document.createElement("button");
    button.className = "public-nav-toggle";
    button.type = "button";
    button.dataset.publicNavToggle = "";
    button.setAttribute("aria-label", "Open navigation");
    button.setAttribute("aria-controls", "public-site-navigation");
    button.setAttribute("aria-expanded", "false");
    button.title = "Open navigation";
    const icon = document.createElement("span");
    icon.className = "public-nav-toggle-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    button.append(icon);
    return button;
  }

  const brand = createBrand();
  const search = createSearch();
  const navigation = createNavigation();
  const divider = document.createElement("span");
  divider.className = "global-header-account-divider";
  divider.setAttribute("aria-hidden", "true");
  const navigationToggle = createNavigationToggle();
  if (visitorPage) {
    header.replaceChildren(brand, search, navigation, navigationToggle);
  } else {
    header.replaceChildren(brand, search, navigation, divider, identitySlot, navigationToggle);
  }
  header.dataset.globalHeaderReady = "true";

  const input = search.querySelector("[data-global-search-input]");
  const results = search.querySelector("[data-global-search-results]");

  function closeSearchResults() {
    activeSuggestion = -1;
    results.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function setSearchMessage(message, tone = "default") {
    results.replaceChildren();
    const status = document.createElement("p");
    status.className = "global-header-search-status";
    status.dataset.tone = tone;
    status.textContent = message;
    results.append(status);
    results.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function flattenedTags(item) {
    const direct = Array.isArray(item.tags) ? item.tags : [];
    const grouped = Array.isArray(item.tag_groups)
      ? item.tag_groups.flatMap((group) => Array.isArray(group?.tags) ? group.tags : [])
      : [];
    return [...direct, ...grouped].map(cleanText).filter(Boolean);
  }

  function itemSearchText(item) {
    const creator = item.creator && typeof item.creator === "object" ? item.creator : {};
    return [
      item.title,
      item.series,
      item.content_type,
      item.type,
      item.ratio_label,
      item.ratio,
      creator.display_name,
      ...flattenedTags(item),
    ].map(cleanText).join(" ").toLocaleLowerCase();
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

  function suggestionHref(item, query) {
    const params = new URLSearchParams();
    if (item.id) params.set("id", cleanText(item.id));
    if (query) params.set("q", query);
    return `/work.html?${params.toString()}`;
  }

  function setActiveSuggestion(index) {
    const options = [...results.querySelectorAll("[role='option']")];
    if (!options.length) return;
    activeSuggestion = (index + options.length) % options.length;
    options.forEach((option, optionIndex) => option.classList.toggle("is-active", optionIndex === activeSuggestion));
    const active = options[activeSuggestion];
    input.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  }

  function renderSearchSuggestions(items, query) {
    results.replaceChildren();
    activeSuggestion = -1;
    if (!items.length) {
      setSearchMessage("No matching works.", "empty");
      return;
    }
    items.forEach((item, index) => {
      const link = document.createElement("a");
      link.id = `global-search-option-${index}`;
      link.className = "global-header-search-result";
      link.dataset.i18nSkip = "";
      link.href = suggestionHref(item, query);
      link.setAttribute("role", "option");
      const title = document.createElement("strong");
      title.textContent = cleanText(item.title) || "Untitled work";
      const creator = cleanText(item.creator?.display_name);
      const details = document.createElement("span");
      details.textContent = creator || cleanText(item.content_type || item.type || item.ratio_label || item.ratio) || "Published work";
      link.append(title, details);
      results.append(link);
    });
    results.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function dispatchWorksSearch(query) {
    window.dispatchEvent(new CustomEvent("mt:global-search-change", { detail: { query } }));
  }

  async function updateSearch(query) {
    if (worksPage) {
      closeSearchResults();
      dispatchWorksSearch(query);
      return;
    }
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
      renderSearchSuggestions(items, query);
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

  input.addEventListener("input", () => scheduleSearch());
  input.addEventListener("focus", () => {
    if (!worksPage && cleanText(input.value)) scheduleSearch();
  });
  input.addEventListener("keydown", (event) => {
    const options = [...results.querySelectorAll("[role='option']")];
    if ((event.key === "ArrowDown" || event.key === "ArrowUp") && options.length && !results.hidden) {
      event.preventDefault();
      setActiveSuggestion(activeSuggestion + (event.key === "ArrowDown" ? 1 : -1));
      return;
    }
    if (event.key === "Escape") {
      if (!results.hidden) {
        event.preventDefault();
        closeSearchResults();
      } else if (input.value) {
        event.preventDefault();
        input.value = "";
        scheduleSearch(true);
      } else {
        search.classList.remove("is-search-open");
      }
    }
  });

  search.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = cleanText(input.value);
    const active = results.querySelectorAll("[role='option']")[activeSuggestion];
    if (active && !results.hidden) {
      window.location.assign(active.href);
      return;
    }
    if (!query && window.matchMedia("(max-width: 760px)").matches) {
      search.classList.add("is-search-open");
      input.focus();
      return;
    }
    if (worksPage) {
      scheduleSearch(true);
      return;
    }
    const target = new URL("/works.html", window.location.origin);
    if (query) target.searchParams.set("q", query);
    window.location.assign(`${target.pathname}${target.search}`);
  });

  document.addEventListener("pointerdown", (event) => {
    if (!search.contains(event.target)) closeSearchResults();
  });
  window.addEventListener("popstate", () => {
    if (!worksPage) return;
    input.value = cleanText(new URLSearchParams(window.location.search).get("q"));
  });
})();
