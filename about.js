(function initializeAboutProfile() {
  const publicArchive = window.MTPresencePublicArchive;
  const name = document.querySelector("[data-about-name]");
  const headline = document.querySelector("[data-about-headline]");
  const bio = document.querySelector("[data-about-bio]");
  const location = document.querySelector("[data-about-location]");
  const availability = document.querySelector("[data-about-availability]");
  const avatar = document.querySelector("[data-about-avatar]");
  const statementLink = document.querySelector("[data-about-statement-link]");

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function initials(value) {
    const parts = cleanText(value || "MT").split(/\s+/).filter(Boolean);
    if (parts[0]?.toUpperCase() === "MT") return "MT";
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "MT";
  }

  function applyProfile(profile) {
    const displayName = cleanText(profile.display_name) || "MT Presence";
    name.textContent = displayName;
    if (cleanText(profile.professional_headline)) headline.textContent = profile.professional_headline;
    if (cleanText(profile.bio)) bio.textContent = profile.bio;
    const place = [cleanText(profile.city), cleanText(profile.country_code)].filter(Boolean).join(", ");
    if (place) location.textContent = `Based in ${place}`;
    if (cleanText(profile.availability_status)) availability.textContent = profile.availability_status;
    avatar.textContent = initials(displayName);
    const avatarUrl = cleanText(profile.avatar_url);
    if (avatarUrl) {
      const image = document.createElement("img");
      image.src = avatarUrl;
      image.alt = "";
      image.decoding = "async";
      image.addEventListener("load", () => avatar.classList.add("is-image-ready"), { once: true });
      avatar.append(image);
    }
    const slug = cleanText(profile.slug);
    if (slug) statementLink.href = `/creators/${encodeURIComponent(slug)}#about`;
  }

  async function loadPublicProfile() {
    if (!publicArchive) return;
    try {
      const archive = await publicArchive.loadPublishedWorks();
      if (!archive.authoritative) return;
      const creator = archive.works.find((work) => cleanText(work.creator?.slug))?.creator;
      if (!creator?.slug) return;
      const response = await fetch(`/api/public/creators/${encodeURIComponent(creator.slug)}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      const profile = await response.json().catch(() => ({}));
      if (response.ok && profile && typeof profile === "object") applyProfile(profile);
    } catch (_error) {
      // Editorial defaults remain visible when no public creator exists yet.
    }
  }

  loadPublicProfile();
})();
