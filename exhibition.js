(function initializeExhibition(global) {
  // Requirement 07 prototype: one photograph at a time. Mouse-driven computers
  // see a virtual gallery room; touch devices see the work full screen.
  // Choices the photographer has not confirmed yet can be compared with
  // ?proto=1 (see docs/product/implementation-plan-2026-10-21.md).
  const archive = global.MTPresencePublicArchive;
  const i18n = global.MTPresenceI18n;
  const t = (text) => (i18n ? i18n.t(text) : text);

  const body = document.body;
  const room = document.querySelector("[data-exhibition]");
  const stage = document.querySelector("[data-exhibition-stage]");
  const figure = document.querySelector("[data-exhibition-work]");
  const image = document.querySelector("[data-exhibition-image]");
  const prevButton = document.querySelector("[data-exhibition-prev]");
  const nextButton = document.querySelector("[data-exhibition-next]");
  const menuToggle = document.querySelector("[data-exhibition-menu-toggle]");
  const menuPanel = document.querySelector("[data-exhibition-menu-panel]");
  const seriesLabel = document.querySelector("[data-exhibition-series]");
  const caption = document.querySelector("[data-exhibition-caption]");
  const captionTitle = document.querySelector("[data-exhibition-title]");
  const captionText = document.querySelector("[data-exhibition-text]");
  const preview = document.querySelector("[data-exhibition-preview]");
  const strip = document.querySelector("[data-exhibition-strip]");
  const ambientLayers = [...document.querySelectorAll("[data-ambient-layer]")];
  const motesCanvas = document.querySelector("[data-room-motes]");
  const hint = document.querySelector("[data-exhibition-hint]");
  const status = document.querySelector("[data-exhibition-status]");
  const statusText = document.querySelector("[data-exhibition-status-text]");
  const retryButton = document.querySelector("[data-exhibition-retry]");
  const announcer = document.querySelector("[data-exhibition-announcer]");

  // 此间留彩 / 此间留灰 reuse the existing category field (v1.7.0).
  const SERIES = {
    colour: { type: "Concrete", name: "此间留彩", english: "Colour" },
    grey: { type: "Abstract", name: "此间留灰", english: "Grey" },
  };
  const PROTOTYPE_OPTIONS = {
    scene: { label: "场景", attribute: "scene", choices: [["hall", "大屏展厅"], ["screen", "手机全屏"]] },
    wall: {
      label: "展墙",
      attribute: "wall",
      choices: [
        ["white", "美术馆白墙"], ["gray", "深灰博物馆墙"], ["concrete", "清水混凝土"],
        ["wood", "深色木饰面"], ["red", "深红墙"], ["green", "墨绿墙"],
      ],
    },
    light: {
      label: "灯光",
      attribute: "light",
      choices: [["wash", "洗墙射灯"], ["spot", "聚光"], ["daylight", "天光"], ["even", "均匀"]],
    },
    position: {
      label: "文字位置",
      attribute: "captionPosition",
      choices: [
        ["top-left", "左上"], ["top-center", "上中"], ["top-right", "右上"],
        ["middle-left", "左中"], ["middle-center", "正中"], ["middle-right", "右中"],
        ["bottom-left", "左下"], ["bottom-center", "中下"], ["bottom-right", "右下"],
      ],
    },
    style: { label: "文字风格", attribute: "captionStyle", choices: [["serif", "衬线淡入"], ["vertical", "竖排"], ["reveal", "逐字浮现"]] },
  };
  // The room's wall occupies the upper part of the viewport; the floor the rest.
  const WALL_FRACTION = 0.8;
  const SWIPE_DISTANCE = 56;
  const WHEEL_DISTANCE = 60;
  const HINT_STORAGE_KEY = "mt-presence-exhibition-hint-v1";
  // Per-work wall and caption settings chosen in the upload studio
  // (studio-exhibition.js). Kept in this browser until the new database.
  const WORK_SETTINGS_KEY = "mt-presence-exhibition-settings-v1";
  const WORK_SETTING_FIELDS = [["wall", "wall", "wall"], ["position", "captionPosition", "position"], ["style", "captionStyle", "style"]];
  const IDLE_CURSOR_MS = 2600;
  // The thumbnail strip (as in Apple Photos) appears with the menu, and in
  // viewing mode briefly whenever the visitor pages or reaches for it.
  const STRIP_AWAKE_MS = 2800;
  const STRIP_NARROW = 0.62;
  const STRIP_CURRENT_MARGIN = 6;
  const CLOSE_DISTANCE = 120;
  const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";
  // Old or very small devices keep the photograph and drop the particles.
  const lowPower = (global.navigator.hardwareConcurrency || 8) <= 2 || (global.navigator.deviceMemory || 8) <= 2;

  const params = new URLSearchParams(global.location.search);
  const prototypeMode = params.get("proto") === "1";
  const reducedMotion = global.matchMedia("(prefers-reduced-motion: reduce)");
  // Requirement 07: mouse-driven computers enter the gallery room, touch
  // devices get the full-screen view, independent of window width.
  const hallQuery = global.matchMedia("(hover: hover) and (pointer: fine)");

  let seriesKey = SERIES[params.get("series")] ? params.get("series") : "";
  let works = [];
  let index = 0;
  let changing = false;
  let queuedStep = 0;
  let queuedIndex = null;
  let refreshedAfterError = false;
  let idleTimer = 0;
  let wheelTotal = 0;
  let wheelTimer = 0;
  let pointerFrame = 0;
  let ambientIndex = 0;
  let stripKey = "";
  let stripAwakeTimer = 0;
  let stripSettleTimer = 0;
  let stripProgrammaticTimer = 0;
  let stripProgrammatic = false;
  let stripUserScrolling = false;
  let motesFrame = 0;
  const imageCache = new Map();
  // The grey series is revealed like ink spreading on paper; the property is
  // registered so the mask edge can be animated smoothly.
  const inkSupported = registerInkProperty();

  function registerInkProperty() {
    if (typeof global.CSS?.registerProperty !== "function") return false;
    try {
      global.CSS.registerProperty({ name: "--ink", syntax: "<percentage>", inherits: false, initialValue: "150%" });
    } catch (_error) {
      // Already registered by an earlier copy of this script.
    }
    return true;
  }

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function seriesForWork(work) {
    return work.type === SERIES.grey.type ? "grey" : "colour";
  }

  function currentWork() {
    return works[index] || null;
  }

  function scene() {
    return body.dataset.scene;
  }

  function setScene(next) {
    body.dataset.scene = next === "hall" ? "hall" : "screen";
    layoutArtwork();
    startMotes();
  }

  function sceneFromDevice() {
    const forced = prototypeMode ? params.get("scene") : "";
    if (forced === "hall" || forced === "screen") return forced;
    return hallQuery.matches ? "hall" : "screen";
  }

  function motionAllowed() {
    return !reducedMotion.matches;
  }

  // ----- Layout -------------------------------------------------------------

  function artworkRatio(work) {
    const fromImage = image.naturalWidth && image.naturalHeight && image.dataset.workId === work.id
      ? image.naturalWidth / image.naturalHeight
      : 0;
    const fromRecord = work.width > 0 && work.height > 0 ? work.width / work.height : 0;
    return fromImage || fromRecord || 1;
  }

  function layoutArtwork() {
    const work = currentWork();
    if (!work) return;
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    const ratio = artworkRatio(work);
    let maxWidth;
    let maxHeight;
    let centerY;
    if (scene() === "hall") {
      // Hung slightly above the wall's centre with generous breathing room,
      // the way a single work is hung in a gallery.
      const wallHeight = height * WALL_FRACTION;
      maxWidth = width * (ratio > 2.2 ? 0.8 : 0.62);
      maxHeight = wallHeight * 0.68;
      centerY = wallHeight * 0.47;
    } else {
      // Full screen, complete and uncropped (question 13 default).
      maxWidth = width;
      maxHeight = height;
      centerY = height / 2;
    }
    let artWidth = maxWidth;
    let artHeight = artWidth / ratio;
    if (artHeight > maxHeight) {
      artHeight = maxHeight;
      artWidth = artHeight * ratio;
    }
    room.style.setProperty("--art-w", `${Math.round(artWidth)}px`);
    room.style.setProperty("--art-h", `${Math.round(artHeight)}px`);
    room.style.setProperty("--art-y", `${Math.round(centerY)}px`);
  }

  // ----- Images -------------------------------------------------------------

  function loadImage(src) {
    if (!src) return Promise.resolve(false);
    if (!imageCache.has(src)) {
      imageCache.set(
        src,
        new Promise((resolve) => {
          const loader = new Image();
          loader.decoding = "async";
          loader.onload = () => {
            // Decoding first avoids a half-drawn frame, but a hidden window may
            // postpone it indefinitely, so it never holds the work back long.
            const decoded = loader.decode ? loader.decode().catch(() => {}) : Promise.resolve();
            Promise.race([decoded, new Promise((done) => global.setTimeout(done, 1500))]).then(() => resolve(true));
          };
          loader.onerror = () => {
            imageCache.delete(src);
            resolve(false);
          };
          loader.src = src;
        }),
      );
    }
    return imageCache.get(src);
  }

  function preloadNeighbours() {
    if (works.length < 2) return;
    [1, -1].forEach((step) => {
      const neighbour = works[(index + step + works.length) % works.length];
      loadImage(neighbour.src);
    });
  }

  // Public image links are signed for ten minutes. After a long visit, reload
  // the list once and continue with fresh links.
  async function refreshWorks() {
    const result = await archive.loadPublishedWorks();
    if (result.error || !result.works.length) return false;
    const currentId = currentWork()?.id;
    const fresh = result.works.filter((work) => seriesForWork(work) === seriesKey);
    if (!fresh.length) return false;
    works = fresh;
    index = Math.max(0, works.findIndex((work) => work.id === currentId));
    imageCache.clear();
    return true;
  }

  // ----- Rendering ----------------------------------------------------------

  function renderCaption(work) {
    captionTitle.textContent = work.title;
    const text = cleanText(work.description || work.curatorialNote || work.curatorial_note);
    captionText.replaceChildren();
    captionText.hidden = !text;
    if (!text) return;
    if (body.dataset.captionStyle !== "reveal") {
      captionText.textContent = text;
      return;
    }
    // Word by word for Latin text, character by character for Chinese.
    const segmenter = global.Intl?.Segmenter
      ? new Intl.Segmenter(undefined, { granularity: /[㐀-鿿]/.test(text) ? "grapheme" : "word" })
      : null;
    const pieces = segmenter ? [...segmenter.segment(text)].map((part) => part.segment) : text.split(/(\s+)/);
    let order = 0;
    pieces.forEach((piece) => {
      if (/^\s+$/.test(piece)) {
        captionText.append(document.createTextNode(piece));
        return;
      }
      const span = document.createElement("span");
      span.textContent = piece;
      span.style.setProperty("--reveal-index", String(Math.min(order, 80)));
      order += 1;
      captionText.append(span);
    });
  }

  function thumbnailButton(work, workIndex) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "exhibition-thumb";
    button.dataset.index = String(workIndex);
    button.setAttribute("aria-label", `${workIndex + 1} / ${works.length}: ${work.title}`);
    // The current work opens to its own shape; the others are narrow slices.
    const ratio = work.width > 0 && work.height > 0 ? work.width / work.height : 1;
    button.style.setProperty("--thumb-ratio", String(Math.min(1.9, Math.max(0.56, ratio))));
    const thumb = document.createElement("img");
    thumb.src = work.thumbnail_url || work.src;
    thumb.alt = "";
    thumb.loading = "lazy";
    thumb.decoding = "async";
    button.append(thumb);
    return button;
  }

  function renderPreview({ smooth = true } = {}) {
    preview.hidden = works.length < 2;
    if (preview.hidden) return;
    const key = works.map((work) => work.id).join("|");
    if (key !== stripKey) {
      stripKey = key;
      strip.replaceChildren(...works.map((work, workIndex) => thumbnailButton(work, workIndex)));
      smooth = false;
    }
    [...strip.children].forEach((button, workIndex) => {
      if (workIndex === index) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
    centerStrip(smooth);
  }

  // Centre the current thumbnail. Widths are animating, so the target is
  // computed from the final layout rather than measured mid-transition.
  function centerStrip(smooth) {
    const current = strip.children[index];
    if (!current) return;
    const style = global.getComputedStyle(strip);
    const height = current.offsetHeight;
    const gap = parseFloat(style.columnGap) || 0;
    const ratio = parseFloat(current.style.getPropertyValue("--thumb-ratio")) || 1;
    const center = (parseFloat(style.paddingLeft) || 0)
      + index * (height * STRIP_NARROW + gap)
      + STRIP_CURRENT_MARGIN
      + (height * ratio) / 2;
    stripProgrammatic = true;
    global.clearTimeout(stripProgrammaticTimer);
    stripProgrammaticTimer = global.setTimeout(() => {
      stripProgrammatic = false;
    }, 700);
    strip.scrollTo({ left: center - strip.clientWidth / 2, behavior: smooth && motionAllowed() ? "smooth" : "auto" });
  }

  function stripCenteredIndex() {
    const middle = strip.scrollLeft + strip.clientWidth / 2;
    let nearest = index;
    let distance = Infinity;
    [...strip.children].forEach((button, workIndex) => {
      const gapToMiddle = Math.abs(button.offsetLeft + button.offsetWidth / 2 - middle);
      if (gapToMiddle < distance) {
        distance = gapToMiddle;
        nearest = workIndex;
      }
    });
    return nearest;
  }

  function wakeStrip() {
    if (works.length < 2) return;
    room.classList.add("is-strip-awake");
    global.clearTimeout(stripAwakeTimer);
    stripAwakeTimer = global.setTimeout(() => {
      if (!preview.matches(":hover, :focus-within")) room.classList.remove("is-strip-awake");
    }, STRIP_AWAKE_MS);
  }

  // A softly blurred, slowly drifting copy of the work fills the screen
  // around it, so the photograph sits in its own light and mist (留白,
  // 虚实相生) instead of between black bars.
  function cssUrl(src) {
    return `url("${String(src).replace(/["\\\n]/g, encodeURIComponent)}")`;
  }

  function setAmbient(work) {
    if (ambientLayers.length < 2) return;
    const src = work.thumbnail_url || work.src;
    const active = ambientLayers[ambientIndex];
    if (active.dataset.src === src) return;
    ambientIndex = (ambientIndex + 1) % ambientLayers.length;
    const next = ambientLayers[ambientIndex];
    next.dataset.src = src;
    next.style.backgroundImage = cssUrl(src);
    next.classList.add("is-active");
    active.classList.remove("is-active");
  }

  function renderSeriesLabel() {
    const series = SERIES[seriesKey];
    // One name per language, as in the approved design: 此间留灰 · 03 / 13.
    const name = i18n?.language === "zh" ? series.name : series.english;
    seriesLabel.textContent = `${name} · ${String(index + 1).padStart(2, "0")} / ${String(works.length).padStart(2, "0")}`;
  }

  function updateUrl(work) {
    const next = new URLSearchParams(global.location.search);
    next.set("series", seriesKey);
    next.set("work", work.id);
    global.history.replaceState(null, "", `${global.location.pathname}?${next.toString()}`);
  }

  const pageDefaults = {
    wall: body.dataset.wall,
    captionPosition: body.dataset.captionPosition,
    captionStyle: body.dataset.captionStyle,
  };

  function applyWorkSettings(work) {
    let stored = {};
    try {
      stored = JSON.parse(global.localStorage.getItem(WORK_SETTINGS_KEY) || "{}")[work.id] || {};
    } catch (_error) {
      stored = {};
    }
    // A choice made in the prototype panel (present in the address) wins.
    const current = new URLSearchParams(global.location.search);
    WORK_SETTING_FIELDS.forEach(([storedKey, attribute, urlKey]) => {
      if (current.has(urlKey)) return;
      body.dataset[attribute] = stored[storedKey] || pageDefaults[attribute];
    });
  }

  function renderWork() {
    const work = currentWork();
    if (!work) return;
    applyWorkSettings(work);
    image.src = work.src;
    image.alt = cleanText(work.alt_text) || work.title;
    image.dataset.workId = work.id;
    layoutArtwork();
    renderCaption(work);
    renderPreview();
    setAmbient(work);
    renderSeriesLabel();
    updateUrl(work);
    document.title = `${work.title} | MT Presence`;
    announcer.textContent = `${index + 1} / ${works.length}: ${work.title}`;
    preloadNeighbours();
  }

  // ----- Navigation ---------------------------------------------------------

  function wait(milliseconds) {
    return new Promise((resolve) => global.setTimeout(resolve, milliseconds));
  }

  // Browsers stop advancing animations when they stop drawing (a hidden
  // tab, power saving). Each one is therefore finished on schedule, so
  // paging can never wait on a frozen animation.
  function settle(animation, duration) {
    return Promise.race([animation.finished.catch(() => {}), wait(duration + 400)]).then(() => {
      if (animation.playState === "running" || animation.playState === "paused") animation.finish();
    });
  }

  function animate(element, keyframes, options) {
    if (!element.animate) return Promise.resolve();
    return settle(element.animate(keyframes, { fill: "forwards", ...options }), options.duration || 0);
  }

  async function ensureLoaded(work) {
    if (await loadImage(work.src)) return true;
    if (refreshedAfterError) return false;
    refreshedAfterError = true;
    return (await refreshWorks()) && loadImage(currentWork().src);
  }

  let revealing = [];

  function clearFigureMotion() {
    figure.getAnimations?.().forEach((animation) => animation.cancel());
    figure.classList.remove("is-ink-reveal");
    figure.style.transform = "";
  }

  // The new work does not simply appear: it surfaces out of mist (colour) or
  // spreads like ink on paper (grey), then settles. Paging again cuts it short.
  function revealWork(direction) {
    if (!motionAllowed() || !figure.animate) return Promise.resolve();
    const grey = seriesKey === "grey";
    const shift = scene() === "hall" ? 0 : direction * Math.min(stage.clientWidth * 0.12, 64);
    const from = `translate(calc(-50% + ${shift}px), -50%) scale(${grey ? 1.02 : 1.035})`;
    const to = "translate(-50%, -50%) scale(1)";
    const frames = grey
      ? [{ transform: from, filter: "blur(9px) contrast(0.82)", opacity: 0.25 }, { transform: to, filter: "blur(0px) contrast(1)", opacity: 1 }]
      : [{ transform: from, filter: "blur(8px) brightness(1.28)", opacity: 0 }, { transform: to, filter: "blur(0px) brightness(1)", opacity: 1 }];
    revealing = [figure.animate(frames, { duration: grey ? 1300 : 950, easing: EASE_OUT, fill: "forwards" })];
    if (grey && inkSupported) {
      figure.classList.add("is-ink-reveal");
      revealing.push(figure.animate([{ "--ink": "0%" }, { "--ink": "150%" }], {
        duration: 1500,
        easing: "cubic-bezier(0.33, 0, 0.2, 1)",
        fill: "forwards",
      }));
    }
    return Promise.all(revealing.map((animation) => settle(animation, 1500))).then(() => {
      revealing = [];
      clearFigureMotion();
    });
  }

  async function changeTo(nextIndex, direction, { dragOffset = 0 } = {}) {
    if (changing || !works.length) return;
    changing = true;
    const motion = motionAllowed();
    const target = works[nextIndex];
    const loaded = loadImage(target.src);
    clearFigureMotion();

    if (scene() === "hall") {
      // The light dims, the work is changed, the light comes back up.
      room.classList.add("is-changing");
      await Promise.all([motion ? wait(420) : Promise.resolve(), loaded]);
      index = nextIndex;
      await ensureLoaded(target);
      renderWork();
      await wait(motion ? 60 : 0);
      room.classList.remove("is-changing");
      await revealWork(direction);
    } else {
      const width = stage.clientWidth;
      if (motion) {
        await animate(
          figure,
          [{ transform: `translate(calc(-50% + ${dragOffset}px), -50%)`, opacity: 1, filter: "blur(0px)" },
            { transform: `translate(calc(-50% + ${-direction * width * 0.22}px), -50%) scale(0.97)`, opacity: 0, filter: "blur(6px)" }],
          { duration: 240, easing: "cubic-bezier(0.4, 0, 1, 1)" },
        );
      }
      index = nextIndex;
      await loaded;
      await ensureLoaded(target);
      renderWork();
      await revealWork(direction);
    }
    clearFigureMotion();

    changing = false;
    refreshedAfterError = false;
    wakeStrip();
    if (queuedIndex !== null) {
      const target = queuedIndex;
      queuedIndex = null;
      goTo(target);
    } else if (queuedStep) {
      const step = queuedStep;
      queuedStep = 0;
      go(step);
    }
  }

  function go(step, options) {
    if (works.length < 2) return;
    if (changing) {
      queuedStep = step;
      // Paging while the work is still surfacing finishes it at once.
      revealing.forEach((animation) => animation.finish?.());
      return;
    }
    // Question 5 default: browse continuously within the series.
    changeTo((index + step + works.length) % works.length, step, options);
  }

  function goTo(nextIndex) {
    if (!works[nextIndex]) return;
    if (changing) {
      queuedIndex = nextIndex;
      queuedStep = 0;
      revealing.forEach((animation) => animation.finish?.());
      return;
    }
    if (nextIndex === index) return;
    changeTo(nextIndex, nextIndex > index ? 1 : -1);
  }

  // ----- Modes --------------------------------------------------------------

  function setMode(mode) {
    body.dataset.mode = mode === "info" ? "info" : "view";
    if (body.dataset.mode === "view") closeMenu();
    if (body.dataset.mode === "info" && body.dataset.captionStyle === "reveal") {
      // Restart the reveal each time the caption appears.
      const work = currentWork();
      if (work) renderCaption(work);
    }
    dismissHint();
  }

  function toggleMode() {
    setMode(body.dataset.mode === "info" ? "view" : "info");
  }

  function openMenu() {
    menuPanel.hidden = false;
    menuToggle.setAttribute("aria-expanded", "true");
    menuToggle.setAttribute("aria-label", t("Close menu"));
    menuToggle.querySelector("use").setAttribute("href", "#exhibition-icon-close");
  }

  function closeMenu() {
    menuPanel.hidden = true;
    menuToggle.setAttribute("aria-expanded", "false");
    menuToggle.setAttribute("aria-label", t("Open menu"));
    menuToggle.querySelector("use").setAttribute("href", "#exhibition-icon-menu");
  }

  function showHint() {
    try {
      if (global.localStorage.getItem(HINT_STORAGE_KEY)) return;
      global.localStorage.setItem(HINT_STORAGE_KEY, "1");
    } catch (_error) {
      // Without storage the hint simply shows on each visit.
    }
    hint.textContent = t(scene() === "hall" ? "Click the artwork to show the menu" : "Tap the image to show the menu");
    hint.hidden = false;
    global.setTimeout(dismissHint, 3200);
  }

  function dismissHint() {
    if (hint.hidden) return;
    hint.classList.add("is-leaving");
    global.setTimeout(() => {
      hint.hidden = true;
      hint.classList.remove("is-leaving");
    }, 500);
  }

  // ----- Input --------------------------------------------------------------

  function isControl(target) {
    return target instanceof Element
      && Boolean(target.closest("button, a, input, select, label, .exhibition-menu-panel, .exhibition-preview, .exhibition-proto"));
  }

  let pointerStart = null;

  room.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || isControl(event.target)) return;
    pointerStart = { x: event.clientX, y: event.clientY, dragging: false, closing: false, id: event.pointerId };
  });

  room.addEventListener("pointermove", (event) => {
    if (scene() === "hall") trackLight(event);
    // Reaching towards the bottom of the screen brings the strip back.
    if (event.pointerType === "mouse" && event.clientY > global.innerHeight * 0.74) wakeStrip();
    if (!pointerStart || event.pointerId !== pointerStart.id || event.pointerType === "mouse") return;
    const dx = event.clientX - pointerStart.x;
    const dy = event.clientY - pointerStart.y;
    if (!pointerStart.dragging && !pointerStart.closing && Math.hypot(dx, dy) > 10) {
      if (Math.abs(dx) > Math.abs(dy)) pointerStart.dragging = true;
      else if (dy > 0 && scene() === "screen") pointerStart.closing = true;
    }
    if (changing || scene() !== "screen") return;
    if (pointerStart.dragging) {
      figure.style.transform = `translate(calc(-50% + ${dx}px), -50%)`;
    } else if (pointerStart.closing) {
      // As in Apple Photos: pull the photograph down to leave.
      const progress = Math.min(1, Math.max(0, dy) / (CLOSE_DISTANCE * 2.5));
      figure.style.transform = `translate(calc(-50% + ${dx * 0.4}px), calc(-50% + ${Math.max(0, dy)}px)) scale(${1 - progress * 0.24})`;
      room.style.setProperty("--close", progress.toFixed(3));
    }
  });

  function settleFigure() {
    room.style.removeProperty("--close");
    if (!figure.style.transform) return;
    animate(figure, [{ transform: figure.style.transform }, { transform: "translate(-50%, -50%)" }], { duration: 260, easing: EASE_OUT })
      .then(() => {
        figure.getAnimations?.().forEach((animation) => animation.cancel());
        figure.style.transform = "";
      });
  }

  async function leaveExhibition() {
    changing = true;
    if (motionAllowed()) {
      await animate(figure, [{ transform: figure.style.transform || "translate(-50%, -50%)", opacity: 1 },
        { transform: "translate(-50%, -30%) scale(0.6)", opacity: 0 }], { duration: 220, easing: "cubic-bezier(0.4, 0, 1, 1)" });
    }
    let cameFromWorks = false;
    try {
      const referrer = new URL(document.referrer);
      cameFromWorks = referrer.origin === global.location.origin && referrer.pathname === "/works.html";
    } catch (_error) {
      cameFromWorks = false;
    }
    if (cameFromWorks && global.history.length > 1) global.history.back();
    else global.location.assign("/works.html");
  }

  function endPointer(event) {
    if (!pointerStart || event.pointerId !== pointerStart.id) return;
    const dx = event.clientX - pointerStart.x;
    const dy = event.clientY - pointerStart.y;
    const { dragging, closing } = pointerStart;
    pointerStart = null;
    if (dragging && Math.abs(dx) > SWIPE_DISTANCE && !changing) {
      go(dx < 0 ? 1 : -1, { dragOffset: scene() === "screen" ? dx : 0 });
      return;
    }
    if (closing && event.type === "pointerup" && dy > CLOSE_DISTANCE && !changing) {
      leaveExhibition();
      return;
    }
    if (scene() === "screen") settleFigure();
    if (event.type === "pointerup" && !dragging && !closing && Math.hypot(dx, dy) < 10 && !isControl(event.target)) {
      toggleMode();
    }
  }

  room.addEventListener("pointerup", endPointer);
  room.addEventListener("pointercancel", endPointer);

  prevButton.addEventListener("click", () => go(-1));
  nextButton.addEventListener("click", () => go(1));

  // The strip: tap a thumbnail to jump, or swipe it and let go to land on
  // the work nearest the middle, as with the scrubber in Apple Photos.
  strip.addEventListener("click", (event) => {
    const button = event.target.closest("[data-index]");
    if (button) goTo(Number(button.dataset.index));
  });

  ["pointerdown", "wheel", "touchstart"].forEach((type) => {
    strip.addEventListener(type, () => {
      stripUserScrolling = true;
      stripProgrammatic = false;
    }, { passive: true });
  });

  strip.addEventListener("scroll", () => {
    wakeStrip();
    if (stripProgrammatic || !stripUserScrolling) return;
    global.clearTimeout(stripSettleTimer);
    stripSettleTimer = global.setTimeout(() => {
      stripUserScrolling = false;
      const nearest = stripCenteredIndex();
      if (nearest !== index) goTo(nearest);
      else centerStrip(true);
    }, 160);
  }, { passive: true });

  preview.addEventListener("pointerenter", wakeStrip);
  preview.addEventListener("pointerleave", wakeStrip);
  preview.addEventListener("focusin", wakeStrip);

  menuToggle.addEventListener("click", () => (menuPanel.hidden ? openMenu() : closeMenu()));

  document.querySelectorAll("[data-language]").forEach((button) => {
    const language = button.dataset.language;
    button.setAttribute("aria-pressed", String((i18n?.language || "en") === language));
    button.addEventListener("click", () => i18n?.setLanguage(language));
  });

  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target instanceof Element && event.target.closest("select, input")) return;
    if (event.key === "ArrowRight" || event.key === "PageDown") {
      event.preventDefault();
      go(1);
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      go(-1);
    } else if (event.key === "Home") {
      goTo(0);
    } else if (event.key === "End") {
      goTo(works.length - 1);
    } else if (event.key === "Escape") {
      if (!menuPanel.hidden) closeMenu();
      else setMode("view");
    } else if ((event.key === "i" || event.key === " " || event.key === "Enter") && !isControl(event.target)) {
      event.preventDefault();
      toggleMode();
    }
  });

  // Trackpad: a horizontal two-finger swipe turns the page.
  room.addEventListener(
    "wheel",
    (event) => {
      if (isControl(event.target) || Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
      event.preventDefault();
      wheelTotal += event.deltaX;
      global.clearTimeout(wheelTimer);
      wheelTimer = global.setTimeout(() => {
        wheelTotal = 0;
      }, 180);
      if (Math.abs(wheelTotal) > WHEEL_DISTANCE && !changing) {
        go(wheelTotal > 0 ? 1 : -1);
        wheelTotal = 0;
      }
    },
    { passive: false },
  );

  // In the room, the light and shadows shift a little as the visitor moves,
  // and the cursor fades away while they simply look.
  function trackLight(event) {
    if (!motionAllowed()) return;
    const x = (event.clientX / global.innerWidth) * 2 - 1;
    const y = (event.clientY / global.innerHeight) * 2 - 1;
    global.cancelAnimationFrame(pointerFrame);
    pointerFrame = global.requestAnimationFrame(() => {
      room.style.setProperty("--mx", x.toFixed(3));
      room.style.setProperty("--my", y.toFixed(3));
    });
  }

  function wakeCursor() {
    room.classList.remove("is-idle");
    global.clearTimeout(idleTimer);
    if (scene() === "hall" && body.dataset.mode === "view") {
      idleTimer = global.setTimeout(() => room.classList.add("is-idle"), IDLE_CURSOR_MS);
    }
  }

  // Fine dust drifting slowly through the spotlight beam: the detail that
  // makes the room read as a real, lit space rather than a picture of one.
  function startMotes() {
    if (motesFrame || !motesCanvas?.getContext || lowPower || !motionAllowed() || scene() !== "hall") return;
    const context = motesCanvas.getContext("2d");
    if (!context) return;
    const motes = Array.from({ length: 46 }, () => newMote(true));
    let last = global.performance.now();

    function newMote(anywhere) {
      return {
        u: Math.random() * 2 - 1,
        v: anywhere ? Math.random() : -0.03,
        size: 0.5 + Math.random() * 1.5,
        drift: (Math.random() - 0.5) * 0.00005,
        fall: 0.000012 + Math.random() * 0.00004,
        phase: Math.random() * Math.PI * 2,
        twinkle: 0.0005 + Math.random() * 0.0011,
      };
    }

    function frame(now) {
      motesFrame = global.requestAnimationFrame(frame);
      const elapsed = Math.min(64, now - last);
      last = now;
      if (document.hidden || scene() !== "hall" || !/^(spot|wash)$/.test(body.dataset.light)) return;
      const ratio = Math.min(2, global.devicePixelRatio || 1);
      const width = motesCanvas.clientWidth;
      const height = motesCanvas.clientHeight;
      if (motesCanvas.width !== Math.round(width * ratio) || motesCanvas.height !== Math.round(height * ratio)) {
        motesCanvas.width = Math.round(width * ratio);
        motesCanvas.height = Math.round(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      context.globalCompositeOperation = "lighter";
      const artWidth = parseFloat(room.style.getPropertyValue("--art-w")) || width * 0.5;
      const artHeight = parseFloat(room.style.getPropertyValue("--art-h")) || height * 0.5;
      const artY = parseFloat(room.style.getPropertyValue("--art-y")) || height * 0.4;
      // A cone from the fixture to just past the top edge of the work.
      const beamHeight = artY - artHeight * 0.25;
      motes.forEach((mote, moteIndex) => {
        mote.u += mote.drift * elapsed;
        mote.v += mote.fall * elapsed;
        mote.phase += mote.twinkle * elapsed;
        if (mote.v > 1 || Math.abs(mote.u) > 1) motes[moteIndex] = newMote(false);
        const spread = 30 + (artWidth * 0.95 - 30) * mote.v;
        const x = width / 2 + mote.u * spread / 2;
        const y = mote.v * beamHeight;
        const edge = 1 - mote.u * mote.u;
        const alpha = (0.18 + 0.42 * (0.5 + 0.5 * Math.sin(mote.phase))) * edge * Math.min(1, mote.v * 6);
        context.fillStyle = `rgba(255, 238, 210, ${alpha.toFixed(3)})`;
        context.beginPath();
        context.arc(x, y, mote.size, 0, Math.PI * 2);
        context.fill();
      });
    }

    motesFrame = global.requestAnimationFrame(frame);
  }

  // Phones that report their tilt without asking: the work and the mist
  // around it shift by different amounts, giving the view depth (like the
  // 3D effect in Apple Photos). iPhones would ask permission, so they skip it.
  function startTilt() {
    const Orientation = global.DeviceOrientationEvent;
    if (!Orientation || typeof Orientation.requestPermission === "function" || !motionAllowed() || hallQuery.matches) return;
    let base = null;
    global.addEventListener("deviceorientation", (event) => {
      if (scene() !== "screen" || event.beta === null || event.gamma === null) return;
      if (!base) base = { beta: event.beta, gamma: event.gamma };
      // Slowly follow the way the phone is held, so only movement shows.
      base.beta += (event.beta - base.beta) * 0.02;
      base.gamma += (event.gamma - base.gamma) * 0.02;
      const x = Math.max(-1, Math.min(1, (event.gamma - base.gamma) / 18));
      const y = Math.max(-1, Math.min(1, (event.beta - base.beta) / 18));
      room.style.setProperty("--tilt-x", x.toFixed(3));
      room.style.setProperty("--tilt-y", y.toFixed(3));
    });
  }

  room.addEventListener("pointermove", wakeCursor);
  global.addEventListener("resize", () => {
    layoutArtwork();
    centerStrip(false);
  });
  image.addEventListener("load", layoutArtwork);
  image.addEventListener("error", async () => {
    if (refreshedAfterError) return;
    refreshedAfterError = true;
    if (await refreshWorks()) renderWork();
  });
  hallQuery.addEventListener?.("change", () => setScene(sceneFromDevice()));

  // ----- Prototype panel ----------------------------------------------------

  function applyOption(attribute, value) {
    if (attribute === "scene") {
      setScene(value);
    } else {
      body.dataset[attribute] = value;
    }
    if (attribute === "captionStyle") {
      const work = currentWork();
      if (work) {
        renderCaption(work);
        renderPreview();
      }
    }
  }

  function buildPrototypePanel() {
    const panel = document.createElement("aside");
    panel.className = "exhibition-proto";
    panel.setAttribute("aria-label", "原型方案");
    const heading = document.createElement("button");
    heading.type = "button";
    heading.className = "exhibition-proto-heading";
    heading.textContent = "原型方案 · 供老板比较";
    heading.setAttribute("aria-expanded", "true");
    heading.addEventListener("click", () => {
      const collapsed = panel.classList.toggle("is-collapsed");
      heading.setAttribute("aria-expanded", String(!collapsed));
    });
    panel.append(heading);
    const fields = document.createElement("div");
    fields.className = "exhibition-proto-fields";
    Object.entries(PROTOTYPE_OPTIONS).forEach(([key, option]) => {
      const label = document.createElement("label");
      const name = document.createElement("span");
      name.textContent = option.label;
      const select = document.createElement("select");
      option.choices.forEach(([value, text]) => select.append(new Option(text, value)));
      const requested = params.get(key);
      if (option.choices.some(([value]) => value === requested)) applyOption(option.attribute, requested);
      select.value = option.attribute === "scene" ? scene() : body.dataset[option.attribute];
      select.addEventListener("change", () => {
        applyOption(option.attribute, select.value);
        const next = new URLSearchParams(global.location.search);
        next.set(key, select.value);
        global.history.replaceState(null, "", `${global.location.pathname}?${next.toString()}`);
      });
      label.append(name, select);
      fields.append(label);
    });
    const note = document.createElement("p");
    note.textContent = "选好后把当前网址发给我们即可，网址里已记录全部选择。";
    fields.append(note);
    panel.append(fields);
    room.append(panel);
    body.dataset.protoOpen = "";
  }

  // ----- Start --------------------------------------------------------------

  function showStatus(message, { retry = false } = {}) {
    status.hidden = false;
    statusText.textContent = t(message);
    retryButton.hidden = !retry;
  }

  async function start() {
    showStatus("Loading works");
    if (!archive) {
      showStatus("Works are temporarily unavailable.", { retry: true });
      return;
    }
    const result = await archive.loadPublishedWorks();
    if (result.error) {
      showStatus(result.status || "Works are temporarily unavailable.", { retry: true });
      return;
    }
    const requestedId = params.get("work");
    const requested = result.works.find((work) => work.id === requestedId);
    if (!seriesKey) seriesKey = requested ? seriesForWork(requested) : "colour";
    works = result.works.filter((work) => seriesForWork(work) === seriesKey);
    if (!works.length) {
      showStatus("No works in this series yet.");
      return;
    }
    index = Math.max(0, works.findIndex((work) => work.id === requestedId));
    body.dataset.series = seriesKey;
    room.classList.add("is-dark");
    await ensureLoaded(currentWork());
    renderWork();
    status.hidden = true;
    // The lights come up once the first work is on the wall. Reading the
    // computed style commits the dark state so the change animates; no
    // animation frame is needed, which background tabs would postpone.
    global.getComputedStyle(figure).opacity;
    global.setTimeout(() => room.classList.remove("is-dark"), 30);
    showHint();
    wakeCursor();
    wakeStrip();
  }

  retryButton.addEventListener("click", start);
  setScene(sceneFromDevice());
  startTilt();
  if (prototypeMode) buildPrototypePanel();
  start();
})(window);
