(function initializeStudioExhibition(global) {
  // Requirement 03 prototype: choose the exhibition wall, the position of the
  // introduction and its style for each work, with a live miniature of the
  // exhibition (exhibition.css). Until the new database exists the choices
  // are kept in this browser; exhibition.js reads the same storage key.
  const STORAGE_KEY = "mt-presence-exhibition-settings-v1";
  const DEFAULTS = { wall: "white", position: "bottom-center", style: "serif" };
  const POSITION_LABELS = {
    "top-left": "左上", "top-center": "上中（作品上方）", "top-right": "右上",
    "middle-left": "左中（作品左侧）", "middle-center": "正中（压在作品上）", "middle-right": "右中（作品右侧）",
    "bottom-left": "左下", "bottom-center": "中下（作品下方）", "bottom-right": "右下",
  };
  // The miniature renders the real exhibition at a fixed size, then scales it.
  const VIRTUAL = { hall: { width: 1280, height: 800 }, screen: { width: 390, height: 844 } };
  const PHONE_FRAME_HEIGHT = 440;
  const WALL_FRACTION = 0.8;

  const section = document.querySelector("[data-studio-exhibit]");
  const form = document.querySelector("[data-studio-form]");
  if (!section || !form) return;
  const frame = section.querySelector("[data-exhibit-frame]");
  const miniature = section.querySelector("[data-exhibit-miniature]");
  const room = section.querySelector("[data-exhibit-room]");
  const image = section.querySelector("[data-exhibit-image]");
  const titleElement = section.querySelector("[data-exhibit-title]");
  const textElement = section.querySelector("[data-exhibit-text]");
  const positionLabel = section.querySelector("[data-exhibit-position-label]");
  const styleSelect = section.querySelector("[name=exhibit_style]");

  let recordId = "";
  let ratio = 1;
  let scene = "hall";

  function readAll() {
    try {
      const parsed = JSON.parse(global.localStorage.getItem(STORAGE_KEY) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function settingsFor(id) {
    return { ...DEFAULTS, ...(readAll()[id] || {}) };
  }

  function save(settings) {
    if (!recordId) return;
    const all = readAll();
    all[recordId] = settings;
    try {
      global.localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    } catch (_error) {
      // Without storage the preview still works for this visit.
    }
  }

  function currentSettings() {
    return {
      wall: form.querySelector("[name=exhibit_wall]:checked")?.value || DEFAULTS.wall,
      position: form.querySelector("[name=exhibit_position]:checked")?.value || DEFAULTS.position,
      style: styleSelect.value || DEFAULTS.style,
    };
  }

  function fillControls(settings) {
    form.querySelectorAll("[name=exhibit_wall]").forEach((input) => {
      input.checked = input.value === settings.wall;
    });
    form.querySelectorAll("[name=exhibit_position]").forEach((input) => {
      input.checked = input.value === settings.position;
    });
    styleSelect.value = settings.style;
  }

  function renderText() {
    const title = form.elements.namedItem("title")?.value.trim() || "Untitled Work";
    const text = form.elements.namedItem("curatorial_note")?.value.trim() || "";
    titleElement.textContent = title;
    textElement.replaceChildren();
    textElement.hidden = !text;
    if (!text) return;
    if (miniature.dataset.captionStyle !== "reveal") {
      textElement.textContent = text;
      return;
    }
    const segmenter = global.Intl?.Segmenter
      ? new Intl.Segmenter(undefined, { granularity: /[㐀-鿿]/.test(text) ? "grapheme" : "word" })
      : null;
    const pieces = segmenter ? [...segmenter.segment(text)].map((part) => part.segment) : text.split(/(\s+)/);
    let order = 0;
    pieces.forEach((piece) => {
      if (/^\s+$/.test(piece)) {
        textElement.append(document.createTextNode(piece));
        return;
      }
      const span = document.createElement("span");
      span.textContent = piece;
      span.style.setProperty("--reveal-index", String(Math.min(order, 80)));
      order += 1;
      textElement.append(span);
    });
  }

  // Restart caption animations so each change is seen as a visitor sees it.
  function replay() {
    miniature.dataset.mode = "view";
    void miniature.offsetWidth;
    miniature.dataset.mode = "info";
  }

  function layout() {
    const size = VIRTUAL[scene];
    const available = frame.clientWidth;
    const scale = scene === "hall" ? available / size.width : Math.min(available / size.width, PHONE_FRAME_HEIGHT / size.height);
    miniature.style.width = `${size.width}px`;
    miniature.style.height = `${size.height}px`;
    miniature.style.transform = `translateX(${Math.max(0, (available - size.width * scale) / 2)}px) scale(${scale})`;
    frame.style.height = `${Math.round(size.height * scale)}px`;

    // Same hanging rules as exhibition.js.
    let maxWidth = size.width;
    let maxHeight = size.height;
    let centerY = size.height / 2;
    if (scene === "hall") {
      const wallHeight = size.height * WALL_FRACTION;
      maxWidth = size.width * (ratio > 2.2 ? 0.8 : 0.62);
      maxHeight = wallHeight * 0.68;
      centerY = wallHeight * 0.47;
    }
    let width = maxWidth;
    let height = width / ratio;
    if (height > maxHeight) {
      height = maxHeight;
      width = height * ratio;
    }
    room.style.setProperty("--art-w", `${Math.round(width)}px`);
    room.style.setProperty("--art-h", `${Math.round(height)}px`);
    room.style.setProperty("--art-y", `${Math.round(centerY)}px`);
  }

  function apply(settings, { animate = true } = {}) {
    miniature.dataset.wall = settings.wall;
    miniature.dataset.captionPosition = settings.position;
    miniature.dataset.captionStyle = settings.style;
    positionLabel.textContent = POSITION_LABELS[settings.position] || "";
    renderText();
    if (animate) replay();
  }

  function setScene(next) {
    scene = next === "screen" ? "screen" : "hall";
    miniature.dataset.scene = scene;
    section.querySelectorAll("[data-exhibit-scene]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.exhibitScene === scene));
    });
    layout();
    replay();
  }

  // These controls describe the display only; keep them out of the Draft's
  // dirty state and autosave.
  ["input", "change"].forEach((type) => {
    section.addEventListener(type, (event) => {
      event.stopPropagation();
      if (!(event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) return;
      const settings = currentSettings();
      save(settings);
      apply(settings);
    });
  });

  section.querySelectorAll("[data-exhibit-scene]").forEach((button) => {
    button.addEventListener("click", () => setScene(button.dataset.exhibitScene));
  });
  section.querySelector("[data-exhibit-replay]")?.addEventListener("click", replay);

  // Title and introduction typed above appear in the preview immediately.
  form.addEventListener("input", (event) => {
    const name = event.target?.name;
    if (name === "title" || name === "curatorial_note") renderText();
  });

  image.addEventListener("load", () => {
    if (image.naturalWidth && image.naturalHeight) ratio = image.naturalWidth / image.naturalHeight;
    layout();
  });

  document.addEventListener("mt:studio-record", (event) => {
    const detail = event.detail || {};
    const changed = detail.id !== recordId;
    recordId = detail.id || "";
    if (detail.width > 0 && detail.height > 0) ratio = detail.width / detail.height;
    if (detail.src && image.getAttribute("src") !== detail.src) image.src = detail.src;
    if (changed) {
      const settings = settingsFor(recordId);
      fillControls(settings);
      apply(settings);
    } else {
      renderText();
    }
    layout();
  });

  global.addEventListener("resize", layout);
  if (global.ResizeObserver) new ResizeObserver(layout).observe(frame);
})(window);
