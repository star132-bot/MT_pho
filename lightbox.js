const publicArchive = window.MTPresencePublicArchive;
const lightboxGallery = document.querySelector("[data-lightbox-gallery]");
const lightboxEmpty = document.querySelector("[data-lightbox-empty]");
const lightboxSummary = document.querySelector("[data-lightbox-summary]");
const lightboxStatus = document.querySelector("[data-lightbox-status]");
const lightboxActions = document.querySelector("[data-lightbox-actions]");
const lightboxToast = document.querySelector("[data-lightbox-toast]");
let allWorks = [];
let toastTimer = null;

function showLightboxToast(message, type = "default") {
  if (!lightboxToast) {
    return;
  }
  window.clearTimeout(toastTimer);
  lightboxToast.textContent = message;
  lightboxToast.dataset.type = type;
  lightboxToast.hidden = false;
  lightboxToast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    lightboxToast.classList.remove("is-visible");
    lightboxToast.hidden = true;
  }, 2400);
}

function selectedWorks() {
  const byId = new Map(allWorks.map((work) => [work.id, work]));
  return publicArchive.readLightboxIds().map((id) => byId.get(id)).filter(Boolean);
}

function renderLightbox() {
  const works = selectedWorks();
  const count = works.length;
  lightboxSummary.textContent = `${count} selected work${count === 1 ? "" : "s"}.`;
  lightboxActions.hidden = count === 0;
  lightboxEmpty.hidden = count > 0;
  lightboxGallery.hidden = count === 0;
  lightboxGallery.innerHTML = works
    .map(
      (work, index) => `
        <article class="lightbox-item" style="--item-delay: ${Math.min(index, 14) * 24}ms;" data-lightbox-work-id="${publicArchive.escapeHtml(work.id)}">
          <a class="lightbox-image-link" href="works.html?work=${encodeURIComponent(work.id)}&from=lightbox" aria-label="View ${publicArchive.escapeHtml(work.title)} in Works">
            <figure style="--display-ratio: ${publicArchive.ratioCssValue(work.ratio)};">
              <img src="${publicArchive.escapeHtml(work.src)}" alt="${publicArchive.escapeHtml(work.title)}" loading="lazy" decoding="async" />
            </figure>
          </a>
          <div class="lightbox-item-copy">
            <div><h2>${publicArchive.escapeHtml(work.title)}</h2><p>${publicArchive.escapeHtml(work.series || `${work.type} / ${work.ratio}`)}</p></div>
            <button type="button" data-remove-lightbox-work aria-label="Remove ${publicArchive.escapeHtml(work.title)} from lightbox">Remove</button>
          </div>
        </article>`,
    )
    .join("");
  lightboxGallery.setAttribute("aria-busy", "false");
}

async function initLightbox() {
  try {
    const result = await publicArchive.loadPublishedWorks();
    allWorks = result.works;
    lightboxStatus.textContent = result.source === "api" ? "" : result.status;
    lightboxStatus.hidden = result.source === "api";
  } catch {
    lightboxStatus.textContent = "Unable to load the archive. Try again from Works.";
    lightboxStatus.dataset.state = "error";
  }
  renderLightbox();
}

lightboxGallery?.addEventListener("click", (event) => {
  const removeButton = event.target.closest("[data-remove-lightbox-work]");
  if (!removeButton) {
    return;
  }
  const item = removeButton.closest("[data-lightbox-work-id]");
  const id = item?.dataset.lightboxWorkId;
  publicArchive.writeLightboxIds(publicArchive.readLightboxIds().filter((workId) => workId !== id));
  renderLightbox();
  showLightboxToast("Removed from your lightbox.");
});

document.querySelector("[data-clear-lightbox]")?.addEventListener("click", () => {
  if (!window.confirm("Clear every work from this browser's lightbox?")) {
    return;
  }
  publicArchive.writeLightboxIds([]);
  renderLightbox();
  showLightboxToast("Lightbox cleared.");
});

initLightbox();
