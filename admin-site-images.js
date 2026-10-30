(function initializeSiteImages(global) {
  // 网站图片位: which published works fill the fixed image places of the
  // visitor site. Changes are staged here and saved per place; an empty
  // place shows the site's built-in image.
  const shell = global.MTAdminShell;
  const SLOTS = [
    { key: "home_hero", number: 1, label: "首页大图", where: "首页最上方的整屏大图。", capacity: 1, page: "/", defaults: ["/assets/art/home-hero.jpg"] },
    {
      key: "home_selected",
      number: 2,
      label: "首页精选作品",
      where: "首页「精选作品」一行，最多 5 张，按顺序显示，标题取作品标题。",
      capacity: 5,
      page: "/",
      defaults: [1, 2, 3, 4, 5].map((index) => `/assets/art/selected-0${index}.jpg`),
    },
    { key: "home_about", number: 3, label: "关于照片", where: "首页「关于此间」旁边的照片。", capacity: 1, page: "/#about", defaults: ["/assets/art/about.jpg"] },
    {
      key: "works_poster_colour",
      number: 4,
      label: "作品页海报 · 此间留彩",
      where: "作品页左侧海报，只能使用此间留彩的作品。",
      capacity: 1,
      page: "/works.html",
      series: "concrete",
      defaults: ["/assets/art/poster-colour.jpg"],
    },
    {
      key: "works_poster_grey",
      number: 5,
      label: "作品页海报 · 此间留灰",
      where: "作品页右侧海报，只能使用此间留灰的作品。",
      capacity: 1,
      page: "/works.html",
      series: "abstract",
      defaults: ["/assets/art/poster-grey.jpg"],
    },
    { key: "contact", number: 6, label: "联系页配图", where: "联系页左侧的配图。", capacity: 1, page: "/contact.html", defaults: ["/assets/art/contact.jpg"] },
  ];
  const BY_KEY = Object.fromEntries(SLOTS.map((slot) => [slot.key, slot]));
  const ERRORS = {
    ADMIN_SITE_IMAGE_NOT_LIVE: "只能使用已经发布到网站的作品。",
    ADMIN_SITE_IMAGE_SERIES_MISMATCH: "海报只能使用同一系列的作品。",
    ADMIN_GOVERNANCE_VALIDATION_FAILED: "这个位置放不下这么多作品，或选了重复的作品。",
    ADMIN_SITE_IMAGE_SLOT_INVALID: "这个位置不存在。",
  };

  const errorBox = document.querySelector("[data-site-images-error]");
  const legend = document.querySelector("[data-slot-legend]");
  const titleElement = document.querySelector("[data-slot-title]");
  const descriptionElement = document.querySelector("[data-slot-description]");
  const stateElement = document.querySelector("[data-slot-state]");
  const imagesList = document.querySelector("[data-slot-images]");
  const resetButton = document.querySelector("[data-slot-reset]");
  const viewLink = document.querySelector("[data-slot-view]");
  const dirtyElement = document.querySelector("[data-slot-dirty]");
  const saveButton = document.querySelector("[data-slot-save]");
  const toast = document.querySelector("[data-site-images-toast]");
  const picker = document.querySelector("[data-picker]");
  const pickerHint = document.querySelector("[data-picker-hint]");
  const pickerStatus = document.querySelector("[data-picker-status]");
  const pickerGrid = document.querySelector("[data-picker-grid]");
  const pickerMore = document.querySelector("[data-picker-more]");

  let saved = {};      // slot key -> [item] from the server
  let staged = {};     // slot key -> [work] being edited
  let current = new URLSearchParams(global.location.search).get("slot");
  if (!BY_KEY[current]) current = "home_selected";
  let pickerTarget = null; // index to replace, or null to add
  let pickerSeries = "all";
  let publishedWorks = [];
  let publishedOffset = 0;
  let publishedHasMore = false;
  let saving = false;
  let toastTimer = 0;
  let csrfPromise = null;

  function showToast(message, tone = "") {
    global.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.dataset.type = tone;
    toast.classList.add("is-visible");
    toastTimer = global.setTimeout(() => toast.classList.remove("is-visible"), 3800);
  }

  async function csrfToken(force = false) {
    if (force) csrfPromise = null;
    if (!csrfPromise) {
      csrfPromise = shell.getJson("/api/auth/csrf").then((payload) => payload.csrf_token);
      csrfPromise.catch(() => { csrfPromise = null; });
    }
    return csrfPromise;
  }

  async function postSlot(key, imageIds, retry = true) {
    const response = await fetch(`/api/admin/site-images/${encodeURIComponent(key)}`, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": await csrfToken() },
      body: JSON.stringify({ image_ids: imageIds }),
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retry) {
      await csrfToken(true);
      return postSlot(key, imageIds, false);
    }
    if (!response.ok) {
      const error = new Error(payload.error?.message || "Save failed");
      error.status = response.status;
      error.code = payload.error?.code || "";
      throw error;
    }
    return payload;
  }

  function applyServer(payload) {
    saved = {};
    (payload.items || []).forEach((item) => {
      (saved[item.slot_key] ||= []).push(item);
    });
    Object.values(saved).forEach((items) => items.sort((left, right) => left.position - right.position));
    staged = Object.fromEntries(SLOTS.map((slot) => [slot.key, (saved[slot.key] || []).map((item) => ({ ...item.work, live: item.live }))]));
  }

  function isDirty(key) {
    const before = (saved[key] || []).map((item) => item.image_id).join(",");
    const after = (staged[key] || []).map((work) => work.id).join(",");
    return before !== after;
  }

  // ----- Rendering ----------------------------------------------------------

  function renderLegend() {
    legend.replaceChildren(...SLOTS.map((slot) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.slotButton = slot.key;
      const count = (staged[slot.key] || []).length;
      button.innerHTML = `<b>${slot.number}</b><span></span><small></small>`;
      button.querySelector("span").textContent = slot.label;
      button.querySelector("small").textContent = count ? `${count} 张作品${isDirty(slot.key) ? " · 未保存" : ""}` : "默认图";
      item.append(button);
      return item;
    }));
    document.querySelectorAll("[data-slot-button]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.slotButton === current));
      const slotItems = staged[button.dataset.slotButton] || [];
      button.toggleAttribute("data-assigned", slotItems.length > 0);
      button.toggleAttribute("data-offline", slotItems.some((work) => work.live === false));
    });
  }

  function timedImage(url, onLoad) {
    const image = document.createElement("img");
    const started = performance.now();
    image.alt = "";
    image.decoding = "async";
    image.addEventListener("load", () => onLoad((performance.now() - started) / 1000, image));
    image.addEventListener("error", () => onLoad(null, image));
    image.src = url;
    return image;
  }

  function stateText(tone, text) {
    const wrapper = document.createElement("span");
    wrapper.className = "admin-state";
    const dot = document.createElement("span");
    dot.className = "admin-dot";
    dot.dataset.tone = tone;
    wrapper.append(dot, text);
    return wrapper;
  }

  function numberBadge(number) {
    const badge = document.createElement("b");
    badge.textContent = String(number);
    return badge;
  }

  // The display file of a place should stay small enough for visitors.
  const LARGE_BYTES = 2.5 * 1024 * 1024;

  function loadState(seconds, bytes) {
    if (seconds === null) return stateText("bad", "加载失败");
    const time = seconds < 0.1 ? "<0.1" : seconds.toFixed(1);
    if (bytes && bytes > LARGE_BYTES) return stateText("warn", `文件偏大 · ${time} s`);
    return stateText(seconds > 1.5 ? "warn" : "ok", `加载${seconds > 1.5 ? "偏慢" : "正常"} · ${time} s`);
  }

  function sizeText(width, height, bytes) {
    const parts = [];
    if (width && height) parts.push(`${width} × ${height}`);
    if (bytes) parts.push(shell.formatBytes(bytes));
    return parts.join(" · ");
  }

  // Byte size of a built-in image; the browser does not expose it for images.
  async function fileBytes(url) {
    try {
      const response = await fetch(url, { method: "HEAD", cache: "no-store", credentials: "same-origin" });
      return Number(response.headers.get("content-length")) || null;
    } catch (_error) {
      return null;
    }
  }

  // One image of a place, as in design/admin-mockups-v4/03-site-image-slots.jpg:
  // thumbnail, size and load state, then the actions for this position.
  function slotRow(slot, index, work = null, url = "") {
    const items = staged[slot.key];
    const item = document.createElement("li");
    if (!work) item.className = "is-default";
    const thumb = document.createElement("span");
    thumb.className = "admin-thumb";
    const facts = document.createElement("div");
    facts.className = "site-slot-facts";
    const name = document.createElement("strong");
    const prefix = slot.capacity > 1 ? `${index + 1}. ` : "";
    name.textContent = `${prefix}${work ? work.title || work.original_filename || "未命名作品" : "网站默认图"}`;
    const source = document.createElement("span");
    source.className = "admin-meta";
    source.textContent = work ? shell.SERIES[work.content_category] || "未分类" : url.replace("/assets/art/", "");
    const load = document.createElement("p");
    load.className = "site-slot-load";
    const size = document.createElement("span");
    const status = document.createElement("span");
    status.className = "site-slot-status";
    status.append(stateText("", "检查加载…"));
    load.append(size, status);

    if (work) {
      const display = work.derivatives?.display;
      if (display) size.textContent = sizeText(display.width, display.height, display.byte_size);
      if (work.live === false) {
        status.replaceChildren(stateText("bad", "已不在网站上，正在显示默认图"));
      } else if (!display || !work.derivatives?.thumbnail) {
        status.replaceChildren(stateText("warn", display ? "缺少缩略图" : "缺少展示图"));
      }
      const measured = work.live !== false && display && work.derivatives?.thumbnail;
      if (work.thumbnail?.signed_url) {
        thumb.append(timedImage(work.thumbnail.signed_url, (seconds) => {
          if (measured) status.replaceChildren(loadState(seconds, display.byte_size));
        }));
      } else if (measured) {
        status.replaceChildren(stateText("warn", "缺少缩略图"));
      }
    } else {
      const bytes = fileBytes(url);
      thumb.append(timedImage(url, async (seconds, image) => {
        const byteSize = await bytes;
        size.textContent = seconds === null ? "" : sizeText(image.naturalWidth, image.naturalHeight, byteSize);
        status.replaceChildren(loadState(seconds, byteSize));
      }));
    }

    const actions = document.createElement("div");
    actions.className = "site-slot-row-actions";
    const addAction = (label, handler, { disabled = false, tone = "", href = "" } = {}) => {
      const control = document.createElement(href ? "a" : "button");
      control.className = "admin-link";
      if (href) {
        control.href = href;
        control.target = "_blank";
        control.rel = "noopener";
      } else {
        control.type = "button";
        control.disabled = disabled;
        control.addEventListener("click", handler);
      }
      if (tone) control.dataset.tone = tone;
      control.textContent = label;
      actions.append(control);
    };
    if (work) {
      addAction("更换图片", () => openPicker(index));
      if (slot.capacity > 1) {
        addAction("上移", () => move(index, -1), { disabled: index === 0 });
        addAction("下移", () => move(index, 1), { disabled: index === items.length - 1 });
      }
      addAction("移除", () => {
        items.splice(index, 1);
        render();
      }, { tone: "bad" });
    } else {
      // Positions fill in order, so a default row adds after the chosen works.
      addAction("从作品中选择", () => openPicker(null));
      addAction("上传新图片 ↗", null, { href: "/workspace/images" });
    }
    facts.append(name, source, load, actions);
    item.append(thumb, facts);
    return item;
  }

  function render() {
    const slot = BY_KEY[current];
    const items = staged[slot.key] || [];
    titleElement.replaceChildren(numberBadge(slot.number), document.createTextNode(slot.label));
    descriptionElement.textContent = slot.where;
    viewLink.href = slot.page;
    if (items.length) {
      stateElement.textContent = slot.capacity > 1
        ? `已选 ${items.length} / ${slot.capacity} 张${items.length < slot.capacity ? "，不足的位置继续显示默认图" : ""}。`
        : "使用作品图片。";
    } else {
      stateElement.textContent = "还没有设置，网站正在显示默认图。";
    }
    imagesList.replaceChildren(
      ...items.map((work, index) => slotRow(slot, index, work)),
      ...slot.defaults.slice(items.length).map((url, offset) => slotRow(slot, items.length + offset, null, url)),
    );
    resetButton.disabled = !items.length;
    const dirty = isDirty(slot.key);
    dirtyElement.textContent = dirty ? "有未保存的修改" : (saved[slot.key]?.[0]?.updated_at ? `上次更新 ${shell.formatTime(saved[slot.key][0].updated_at)}` : "");
    saveButton.disabled = !dirty || saving;
    renderLegend();
  }

  function move(index, step) {
    const items = staged[current];
    const target = index + step;
    if (target < 0 || target >= items.length) return;
    [items[index], items[target]] = [items[target], items[index]];
    render();
  }

  function selectSlot(key) {
    if (!BY_KEY[key]) return;
    current = key;
    const params = new URLSearchParams(global.location.search);
    params.set("slot", key);
    global.history.replaceState(null, "", `${global.location.pathname}?${params}`);
    render();
  }

  // ----- Picker ---------------------------------------------------------------

  async function loadPublished({ append = false } = {}) {
    pickerStatus.hidden = false;
    pickerStatus.textContent = "正在读取作品…";
    try {
      const offset = append ? publishedOffset : 0;
      const payload = await shell.getJson(`/api/admin/works?status=published&limit=50&offset=${offset}&sort=published_desc`);
      const next = payload.items || [];
      publishedWorks = append ? [...publishedWorks, ...next] : next;
      publishedOffset = offset + next.length;
      publishedHasMore = Boolean(payload.pagination?.has_more);
      renderPicker();
    } catch (error) {
      if (shell.redirectForAuth(error)) return;
      pickerStatus.textContent = "作品读取失败，请关闭后重试。";
    }
  }

  function renderPicker() {
    const slot = BY_KEY[current];
    const series = slot.series || pickerSeries;
    const chosen = new Set((staged[slot.key] || []).map((work) => work.id));
    const works = publishedWorks.filter((work) => series === "all" || work.content_category === series);
    pickerStatus.hidden = works.length > 0;
    pickerStatus.textContent = "这个系列还没有已发布的作品。";
    pickerMore.hidden = !publishedHasMore;
    pickerGrid.replaceChildren(...works.map((work) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      const usable = Boolean(work.derivatives?.display && work.thumbnail?.signed_url);
      const taken = chosen.has(work.id) && !(pickerTarget !== null && staged[slot.key][pickerTarget]?.id === work.id);
      button.disabled = !usable || taken;
      const frame = document.createElement("span");
      frame.className = "site-picker-thumb";
      if (work.thumbnail?.signed_url) {
        const image = document.createElement("img");
        image.src = work.thumbnail.signed_url;
        image.alt = "";
        image.loading = "lazy";
        frame.append(image);
      }
      const name = document.createElement("strong");
      name.textContent = work.title || work.original_filename;
      const meta = document.createElement("small");
      meta.textContent = taken ? "已在这个位置" : !usable ? "缺少展示图或缩略图" : shell.SERIES[work.content_category] || "未分类";
      button.append(frame, name, meta);
      button.addEventListener("click", () => choose(work));
      item.append(button);
      return item;
    }));
  }

  function openPicker(targetIndex = null) {
    const slot = BY_KEY[current];
    const items = staged[slot.key] || [];
    pickerTarget = targetIndex !== null ? targetIndex : (slot.capacity === 1 && items.length ? 0 : null);
    pickerHint.textContent = slot.series
      ? `${slot.label}只能使用${shell.SERIES[slot.series]}的已发布作品。`
      : "只显示已发布到网站的作品。";
    document.querySelector("[data-picker-tabs]").hidden = Boolean(slot.series);
    if (typeof picker.showModal === "function") picker.showModal();
    else picker.setAttribute("open", "");
    if (publishedWorks.length) renderPicker();
    else loadPublished();
  }

  function choose(work) {
    const slot = BY_KEY[current];
    const items = staged[slot.key] ||= [];
    const entry = { ...work, live: true };
    if (pickerTarget !== null && items[pickerTarget]) items[pickerTarget] = entry;
    else if (items.length < slot.capacity) items.push(entry);
    picker.close();
    render();
  }

  // ----- Save -------------------------------------------------------------------

  async function save() {
    const slot = BY_KEY[current];
    saving = true;
    saveButton.disabled = true;
    saveButton.textContent = "正在保存…";
    try {
      const payload = await postSlot(slot.key, (staged[slot.key] || []).map((work) => work.id));
      const keep = Object.fromEntries(SLOTS.filter((other) => other.key !== slot.key && isDirty(other.key)).map((other) => [other.key, staged[other.key]]));
      applyServer(payload);
      Object.assign(staged, keep);
      showToast(`「${slot.label}」已保存，网站已更新。`);
    } catch (error) {
      if (shell.redirectForAuth(error)) return;
      showToast(ERRORS[error.code] || "保存失败，请重试。", "error");
    } finally {
      saving = false;
      saveButton.textContent = "保存并发布";
      render();
    }
  }

  // ----- Wiring -------------------------------------------------------------------

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-slot-button]");
    if (button) selectSlot(button.dataset.slotButton);
  });
  resetButton.addEventListener("click", () => {
    staged[current] = [];
    render();
  });
  saveButton.addEventListener("click", save);
  pickerMore.addEventListener("click", () => loadPublished({ append: true }));
  document.querySelectorAll("[data-picker-series]").forEach((button) => {
    button.addEventListener("click", () => {
      pickerSeries = button.dataset.pickerSeries;
      document.querySelectorAll("[data-picker-series]").forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      renderPicker();
    });
  });
  global.addEventListener("beforeunload", (event) => {
    if (SLOTS.some((slot) => isDirty(slot.key))) event.preventDefault();
  });

  async function start() {
    try {
      applyServer(await shell.getJson("/api/admin/site-images"));
      errorBox.hidden = true;
    } catch (error) {
      if (shell.redirectForAuth(error)) return;
      applyServer({ items: [] });
      errorBox.hidden = false;
      errorBox.textContent = "网站图片位读取失败。下面显示的是默认图，暂时不能保存；请刷新重试。";
      saveButton.hidden = true;
    }
    render();
  }

  start();
})(window);
