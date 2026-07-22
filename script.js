const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const hero = document.querySelector(".hero");
const header = document.querySelector(".site-header");
const root = document.documentElement;
const HERO_CONCRETE_COMPLETE_PROGRESS = 0.62;
const HERO_NAV_RELEASE_OFFSET = 16;
const HOME_DB_NAME = "mt-cijian-archive";
const HOME_DB_VERSION = 4;
const HOME_IMAGE_STORE = "images";
const HOME_SETTINGS_STORE = "site_settings";
const HOME_SETTINGS_ID = "homepage";
const archiveSeedData = window.MTPresenceArchiveData || {};
const baseArchiveItems = Array.isArray(archiveSeedData.sampleItems) ? archiveSeedData.sampleItems : [];

function easeInOutCubic(value) {
  return value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function lerp(start, end, progress) {
  return start + (end - start) * progress;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function smoothstep(start, end, value) {
  const progress = clamp((value - start) / (end - start), 0, 1);
  return progress * progress * (3 - 2 * progress);
}

function cleanText(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function cssUrl(value) {
  const url = cleanText(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"');
  return url ? `url("${url}")` : "";
}

function displayUrlFromRecord(record) {
  if (!record) {
    return "";
  }
  const assets = Array.isArray(record.assets) ? record.assets : [];
  const display = assets.find((asset) => asset.kind === "display") || assets.find((asset) => asset.kind === "original");
  return display?.public_url || display?.signed_url || (display?.blob ? URL.createObjectURL(display.blob) : "") || record.image_url || record.src || record.imageRecord?.image_url || "";
}

function defaultHomepageSettings() {
  return {
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
  return {
    hero: {
      abstract: { ...defaults.hero.abstract, ...(rawHero.abstract || {}) },
      concrete: { ...defaults.hero.concrete, ...(rawHero.concrete || {}) },
    },
    statement: {
      title: cleanText(rawStatement.title || defaults.statement.title),
      moments: Array.from({ length: 4 }, (_, index) => ({
        ...defaults.statement.moments[index],
        ...((Array.isArray(rawStatement.moments) && rawStatement.moments[index]) || {}),
      })),
    },
  };
}

function openHomepageDatabase() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      resolve(null);
      return;
    }
    const request = indexedDB.open(HOME_DB_NAME, HOME_DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(HOME_IMAGE_STORE)) {
        database.createObjectStore(HOME_IMAGE_STORE, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains(HOME_SETTINGS_STORE)) {
        database.createObjectStore(HOME_SETTINGS_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readHomepageSettings() {
  const database = await openHomepageDatabase();
  if (!database || !database.objectStoreNames.contains(HOME_SETTINGS_STORE)) {
    return { settings: normalizeHomepageSettings(), storedRecords: [] };
  }
  return new Promise((resolve, reject) => {
    const transaction = database.transaction([HOME_SETTINGS_STORE, HOME_IMAGE_STORE], "readonly");
    const settingsRequest = transaction.objectStore(HOME_SETTINGS_STORE).get(HOME_SETTINGS_ID);
    const recordsRequest = transaction.objectStore(HOME_IMAGE_STORE).getAll();
    transaction.oncomplete = () =>
      resolve({
        settings: normalizeHomepageSettings(settingsRequest.result),
        storedRecords: recordsRequest.result || [],
      });
    transaction.onerror = () => reject(transaction.error);
  });
}

function imageRecordById(id, storedById = new Map()) {
  return storedById.get(id) || baseArchiveItems.find((item) => item.id === id) || null;
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element && cleanText(value)) {
    element.textContent = value;
  }
}

function applyHomepageSettings(payload) {
  const normalized = normalizeHomepageSettings(payload?.settings || payload);
  const storedById = new Map((payload?.storedRecords || []).map((record) => [record.id, record]));
  ["abstract", "concrete"].forEach((kind) => {
    const panel = normalized.hero[kind];
    const baseRecord = imageRecordById(panel.image_id, storedById);
    const imageUrl = displayUrlFromRecord(baseRecord) || panel.fallback_url;
    if (imageUrl) {
      root.style.setProperty(`--home-hero-${kind}-image`, cssUrl(imageUrl));
    }
    const panelElement = document.querySelector(`[data-home-hero-panel="${kind}"]`);
    panelElement?.querySelector("[data-home-hero-eyebrow]") && (panelElement.querySelector("[data-home-hero-eyebrow]").textContent = panel.eyebrow);
    panelElement?.querySelector("[data-home-hero-title]") && (panelElement.querySelector("[data-home-hero-title]").textContent = panel.title);
    panelElement?.querySelector("[data-home-hero-statement]") &&
      (panelElement.querySelector("[data-home-hero-statement]").textContent = panel.statement);
  });

  setText("[data-home-statement-title]", normalized.statement.title);
  normalized.statement.moments.forEach((moment, index) => {
    const element = document.querySelector(`[data-home-statement-moment="${index}"]`);
    if (!element) {
      return;
    }
    const baseRecord = imageRecordById(moment.image_id, storedById);
    const imageUrl = displayUrlFromRecord(baseRecord) || moment.fallback_url;
    const image = element.querySelector("[data-home-statement-image]");
    if (image && imageUrl) {
      image.src = imageUrl;
      image.alt = baseRecord?.title || "Homepage statement image.";
    }
    const text = element.querySelector("[data-home-statement-text]");
    if (text && cleanText(moment.text)) {
      text.textContent = moment.text;
    }
  });
}

function updateHeroTransition() {
  const stage = document.querySelector(".hero-stage");
  if (!hero) {
    return;
  }

  const stageRect = stage ? stage.getBoundingClientRect() : hero.getBoundingClientRect();
  const stageTravel = Math.max((stage?.offsetHeight || hero.offsetHeight) * 0.66, 1);
  const progress = Math.min(Math.max(-stageRect.top / stageTravel, 0), 1);
  const concreteProgress = reduceMotion.matches
    ? 1
    : easeInOutCubic(Math.min(Math.max(progress / HERO_CONCRETE_COMPLETE_PROGRESS, 0), 1));
  const headerOffset = (header?.offsetHeight || 84) + HERO_NAV_RELEASE_OFFSET;
  const navReleaseLine = headerOffset + HERO_NAV_RELEASE_OFFSET;
  const shouldUseScrolledHeader = stageRect.bottom <= navReleaseLine;
  const copyProgress = reduceMotion.matches ? 1 : concreteProgress;
  const abstractCopyExit = smoothstep(0.08, 0.44, copyProgress);
  const concreteCopyEntry = smoothstep(0.56, 0.92, copyProgress);

  root.style.setProperty("--hero-concrete-opacity", concreteProgress.toFixed(3));
  root.style.setProperty("--hero-copy-shift", `${Math.round(lerp(0, -18, copyProgress))}px`);
  root.style.setProperty("--hero-copy-abstract-opacity", (1 - abstractCopyExit).toFixed(3));
  root.style.setProperty("--hero-copy-concrete-opacity", concreteCopyEntry.toFixed(3));
  root.style.setProperty("--hero-copy-abstract-panel-shift", `${Math.round(lerp(0, -28, abstractCopyExit))}px`);
  root.style.setProperty("--hero-copy-concrete-panel-shift", `${Math.round(lerp(26, 0, concreteCopyEntry))}px`);
  root.style.setProperty("--hero-title-alpha", lerp(0.88, 0.96, copyProgress).toFixed(3));
  root.style.setProperty("--hero-statement-alpha", lerp(0.74, 0.88, copyProgress).toFixed(3));
  root.style.setProperty("--hero-copy-shadow-alpha", lerp(0.56, 0.24, copyProgress).toFixed(3));
  root.style.setProperty("--hero-copy-shadow-blur", `${Math.round(lerp(24, 12, copyProgress))}px`);
  document.body.classList.toggle("is-scrolled", shouldUseScrolledHeader);
}

function scrollToTarget(target) {
  const startY = window.scrollY;
  const headerOffset = (header?.offsetHeight || 84) + HERO_NAV_RELEASE_OFFSET;
  const targetY = Math.max(0, target.getBoundingClientRect().top + startY - headerOffset);
  const distance = targetY - startY;
  const duration = Math.min(Math.max(Math.abs(distance) * 0.78, 720), 1400);
  const startTime = performance.now();

  function frame(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = easeInOutCubic(progress);

    window.scrollTo(0, startY + distance * eased);
    if (progress < 1) {
      requestAnimationFrame(frame);
    }
  }

  requestAnimationFrame(frame);
}

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener("click", (event) => {
    const target = document.querySelector(link.getAttribute("href"));
    if (!target || reduceMotion.matches) {
      return;
    }

    event.preventDefault();
    scrollToTarget(target);
  });
});

const statementSection = document.querySelector("[data-statement-section]");
if (statementSection) {
  if ("IntersectionObserver" in window && !reduceMotion.matches) {
    statementSection.classList.add("is-animating");

    const statementMoments = statementSection.querySelectorAll("[data-statement-moment]");
    const statementObserver = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }

          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      {
        rootMargin: "0px 0px -18% 0px",
        threshold: 0.18,
      },
    );

    statementObserver.observe(statementSection);
    statementMoments.forEach((moment) => statementObserver.observe(moment));
  } else {
    statementSection.classList.add("is-visible");
    statementSection.querySelectorAll("[data-statement-moment]").forEach((moment) => {
      moment.classList.add("is-visible");
    });
  }
}

window.addEventListener("scroll", updateHeroTransition, { passive: true });
window.addEventListener("resize", updateHeroTransition);
updateHeroTransition();

readHomepageSettings()
  .then(applyHomepageSettings)
  .catch(() => {
    applyHomepageSettings({ settings: defaultHomepageSettings(), storedRecords: [] });
  });

const homeAccountEntry = document.querySelector("[data-home-account-entry]");
if (homeAccountEntry) {
  fetch("/api/me", {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
  }).then(async (response) => {
    if (!response.ok) return null;
    return response.json();
  }).then((payload) => {
    if (!payload) return;
    const displayName = payload.profile?.display_name || payload.user?.display_name || "Member";
    const avatarText = String(displayName)
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() || "")
      .join("") || "MT";
    homeAccountEntry.href = "/settings/account#profile";
    homeAccountEntry.textContent = avatarText;
    homeAccountEntry.classList.add("is-avatar");
    homeAccountEntry.setAttribute("aria-label", `Open personal information for ${displayName}`);
    homeAccountEntry.title = "Personal information";
  }).catch(() => {});
}
