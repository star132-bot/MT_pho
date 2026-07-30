(function initializePublicCreator() {
  const main = document.querySelector("[data-creator-profile]")?.closest("main");
  const loading = document.querySelector("[data-creator-loading]");
  const errorPanel = document.querySelector("[data-creator-error]");
  const profilePanel = document.querySelector("[data-creator-profile]");
  const retryButton = document.querySelector("[data-creator-retry]");
  const coverImage = document.querySelector("[data-creator-cover]");
  const avatarImage = document.querySelector("[data-creator-avatar-image]");
  const initialsElement = document.querySelector("[data-creator-initials]");
  const workGallery = document.querySelector("[data-creator-work-gallery]");
  const emptyState = document.querySelector("[data-creator-empty]");
  const fallbackCover = "/assets/art/hero-concrete.jpg";
  let requestController = null;

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function creatorSlug() {
    const match = window.location.pathname.match(/^\/creators\/([^/]+)\/?$/);
    if (!match) return cleanText(new URLSearchParams(window.location.search).get("slug"));
    try {
      return cleanText(decodeURIComponent(match[1]));
    } catch {
      return "";
    }
  }

  function safeUrl(value, { httpsOnly = false } = {}) {
    const text = cleanText(value);
    if (!text) return "";
    try {
      const url = new URL(text, window.location.origin);
      if (!["http:", "https:"].includes(url.protocol)) return "";
      if (httpsOnly && url.protocol !== "https:") return "";
      return url.href;
    } catch {
      return "";
    }
  }

  function mediaUrl(value) {
    const href = safeUrl(value);
    if (!href) return "";
    const url = new URL(href);
    return url.origin === window.location.origin || url.protocol === "https:" ? url.href : "";
  }

  function assetUrl(asset) {
    return mediaUrl(asset?.url || asset?.public_url || asset?.signed_url);
  }

  function workImageUrl(work) {
    const assets = work?.assets;
    if (Array.isArray(assets)) {
      return assetUrl(assets.find((asset) => asset.kind === "display"));
    }
    return assetUrl(assets?.display) || assetUrl(work?.display) || mediaUrl(work?.image_url || work?.display_url);
  }

  function responseErrorMessage(payload, fallback) {
    const message = payload?.error?.message
      || (typeof payload?.error === "string" ? payload.error : "")
      || payload?.message;
    return cleanText(message) || fallback;
  }

  function ratioLabel(work) {
    const direct = cleanText(work.ratio_label || work.ratio);
    if (direct) return direct;
    const labels = {
      one_to_one: "1:1",
      four_to_three: "4:3",
      four_to_five: "4:5",
      two_to_three: "2:3",
      three_to_two: "3:2",
      sixteen_to_nine: "16:9",
      panorama: "Panorama",
    };
    return labels[work.ratio_category_code] || "";
  }

  function workType(work) {
    const value = cleanText(work.content_type || work.content_category || work.type).toLowerCase();
    if (value === "abstract") return "Abstract";
    if (value === "concrete") return "Concrete";
    return value ? value.replace(/(^|[_-])\w/g, (token) => token.replace(/[_-]/, " ").toUpperCase()) : "Work";
  }

  function normalizeWork(work) {
    const id = cleanText(work?.id);
    const imageUrl = workImageUrl(work);
    if (!id || !imageUrl) return null;
    const width = Number(work.original_width || work.width || 0);
    const height = Number(work.original_height || work.height || 0);
    return {
      id,
      title: cleanText(work.title) || "Untitled Work",
      altText: cleanText(work.alt_text) || cleanText(work.title) || "Published work",
      imageUrl,
      width: Number.isFinite(width) && width > 0 ? width : null,
      height: Number.isFinite(height) && height > 0 ? height : null,
      type: workType(work),
      ratio: ratioLabel(work),
    };
  }

  function initials(value) {
    const parts = cleanText(value).split(/\s+/).filter(Boolean);
    if (parts[0]?.toUpperCase() === "MT") return "MT";
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
  }

  function setOptionalText(selector, value) {
    const element = document.querySelector(selector);
    const text = cleanText(value);
    element.textContent = text;
    element.hidden = !text;
  }

  function locationLabel(creator) {
    return [cleanText(creator.city), cleanText(creator.country_code)].filter(Boolean).join(", ");
  }

  function availabilityLabel(value) {
    return {
      open: "Available for commissions",
      limited: "Limited availability",
      unavailable: "Not currently available",
    }[cleanText(value).toLowerCase()] || "";
  }

  function renderLinks(creator) {
    const container = document.querySelector("[data-creator-links]");
    container.replaceChildren();
    [
      ["Website", creator.website_url],
      ["Instagram", creator.instagram_url],
      ["LinkedIn", creator.linkedin_url],
    ].forEach(([label, value]) => {
      const href = safeUrl(value, { httpsOnly: true });
      if (!href) return;
      const link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = label;
      link.setAttribute("aria-label", `${label} for ${cleanText(creator.display_name) || "creator"} (opens in a new tab)`);
      container.append(link);
    });
    container.hidden = container.childElementCount === 0;
  }

  function renderIdentity(creator) {
    const displayName = cleanText(creator.display_name) || "Creator";
    document.querySelector("[data-creator-name]").textContent = displayName;
    initialsElement.textContent = initials(displayName);
    setOptionalText("[data-creator-headline]", creator.professional_headline);
    setOptionalText("[data-creator-company]", creator.company);
    setOptionalText("[data-creator-availability]", availabilityLabel(creator.availability_status));
    setOptionalText("[data-creator-bio]", creator.bio);

    const location = locationLabel(creator);
    const locationElement = document.querySelector("[data-creator-location]");
    locationElement.querySelector("span").textContent = location;
    locationElement.hidden = !location;

    const avatarUrl = safeUrl(creator.avatar_url, { httpsOnly: true });
    if (avatarUrl) {
      avatarImage.src = avatarUrl;
      avatarImage.alt = "";
      avatarImage.hidden = false;
      initialsElement.hidden = true;
    } else {
      avatarImage.hidden = true;
      initialsElement.hidden = false;
    }

    const coverUrl = mediaUrl(
      creator.cover_url
      || creator.cover?.url
      || creator.cover?.public_url
      || creator.cover?.signed_url
      || creator.cover?.image_url,
    );
    coverImage.src = coverUrl || fallbackCover;
    document.title = `${displayName} | MT Presence`;
    const description = document.querySelector("[data-creator-description]");
    description.content = cleanText(creator.bio) || `Published work by ${displayName} on MT Presence.`;
    renderLinks(creator);
  }

  function renderWorks(rawWorks, declaredCount) {
    const works = (Array.isArray(rawWorks) ? rawWorks : []).map(normalizeWork).filter(Boolean);
    workGallery.replaceChildren();
    works.forEach((work) => {
      const card = document.createElement("article");
      card.className = "creator-work-card";
      const link = document.createElement("a");
      link.href = `/works.html?work=${encodeURIComponent(work.id)}`;
      link.setAttribute("aria-label", `View ${work.title} in Works`);
      const figure = document.createElement("figure");
      const image = document.createElement("img");
      image.src = work.imageUrl;
      image.alt = work.altText;
      image.loading = "lazy";
      image.decoding = "async";
      if (work.width && work.height) {
        image.width = work.width;
        image.height = work.height;
      }
      figure.append(image);
      const copy = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = work.title;
      const meta = document.createElement("small");
      meta.textContent = [work.type, work.ratio].filter(Boolean).join(" / ");
      copy.append(title, meta);
      link.append(figure, copy);
      card.append(link);
      workGallery.append(card);
    });
    const count = Number.isFinite(Number(declaredCount)) ? Number(declaredCount) : works.length;
    document.querySelector("[data-creator-work-count]").textContent = `${count} work${count === 1 ? "" : "s"}`;
    workGallery.hidden = works.length === 0;
    emptyState.hidden = works.length > 0;
  }

  function showError(error) {
    loading.hidden = true;
    profilePanel.hidden = true;
    errorPanel.hidden = false;
    document.querySelector("[data-creator-error-title]").textContent = error.status === 404
      ? "This creator profile is not available."
      : "This creator profile could not be loaded.";
    document.querySelector("[data-creator-error-message]").textContent = error.message || "Try the request again.";
    retryButton.hidden = error.status === 404;
    main.removeAttribute("aria-busy");
    errorPanel.focus();
  }

  async function loadCreator() {
    const slug = creatorSlug();
    if (!slug) {
      showError({ status: 404, message: "The creator address is invalid." });
      return;
    }
    requestController?.abort();
    requestController = new AbortController();
    loading.hidden = false;
    errorPanel.hidden = true;
    profilePanel.hidden = true;
    main.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`/api/public/creators/${encodeURIComponent(slug)}`, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: requestController.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const failure = new Error(responseErrorMessage(payload, "The creator profile is unavailable."));
        failure.status = response.status;
        throw failure;
      }
      if (!payload.creator || typeof payload.creator !== "object") {
        const failure = new Error("The public creator response could not be verified.");
        failure.status = 502;
        throw failure;
      }
      renderIdentity(payload.creator);
      renderWorks(payload.creator.works, payload.creator.work_count);
      document.querySelector("[data-creator-status]").textContent = "";
      loading.hidden = true;
      profilePanel.hidden = false;
      main.removeAttribute("aria-busy");
    } catch (error) {
      if (error.name === "AbortError") return;
      showError(error);
    }
  }

  retryButton.addEventListener("click", loadCreator);
  coverImage.addEventListener("error", () => {
    if (!coverImage.src.endsWith(fallbackCover)) coverImage.src = fallbackCover;
  });
  avatarImage.addEventListener("error", () => {
    avatarImage.hidden = true;
    initialsElement.hidden = false;
  });
  window.addEventListener("pagehide", () => requestController?.abort(), { once: true });
  loadCreator();
})();
