(function initializeSiteImages(global) {
  // Site image places chosen in the admin (网站图片位). Each marked image keeps
  // its built-in artwork until the chosen work's image has loaded, so a slow
  // or failing request never leaves a gap or a broken image.
  const targets = document.querySelectorAll("[data-site-image]");
  if (!targets.length || !global.fetch) return;

  function apply(item) {
    const position = String(item.position || 1);
    const image = document.querySelector(
      `[data-site-image="${item.slot_key}"][data-site-image-position="${position}"], [data-site-image="${item.slot_key}"]:not([data-site-image-position])`,
    );
    const work = item.work || {};
    const source = work.display_url || work.image_url;
    if (!image || !source) return;
    const preload = new Image();
    preload.decoding = "async";
    preload.onload = () => {
      image.removeAttribute("srcset");
      image.src = source;
      image.width = work.original_width || image.width;
      image.height = work.original_height || image.height;
      image.alt = work.alt_text || work.title || image.alt;
      image.dataset.siteImageWork = work.id || "";
      // Selected works carry their own caption: title and year.
      const caption = image.closest("figure")?.querySelector("figcaption[data-site-image-caption]");
      if (caption && work.title) {
        const year = String(work.captured_at || work.published_at || "").slice(0, 4);
        caption.replaceChildren(document.createTextNode(work.title));
        if (/^\d{4}$/.test(year)) {
          const span = document.createElement("span");
          span.textContent = year;
          caption.append(span);
        }
      }
    };
    preload.src = source;
  }

  fetch("/api/public/site-images", { headers: { Accept: "application/json" }, cache: "no-store" })
    .then((response) => (response.ok ? response.json() : { items: [] }))
    .then((payload) => (Array.isArray(payload.items) ? payload.items : []).forEach(apply))
    .catch(() => {});
})(window);
