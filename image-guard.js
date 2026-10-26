(function initializeImageGuard(global) {
  // Requirement 04: visitors cannot save the photographs. Public pages load
  // this script; staff pages do not, so the admin keeps normal access.
  // Screenshots cannot be prevented by any web page; this removes the
  // ordinary ways to save an image (context menu, drag, long press).
  const documentRef = global.document;
  const root = documentRef.documentElement;
  const PROTECTED_SELECTOR = "img, picture, figure, canvas, video, [data-protected-media]";

  root.setAttribute("data-image-guard", "");

  function isProtectedTarget(target) {
    return target instanceof Element && Boolean(target.closest(PROTECTED_SELECTOR));
  }

  function lockImage(image) {
    image.setAttribute("draggable", "false");
  }

  function lockImagesWithin(node) {
    if (!(node instanceof Element)) return;
    if (node.tagName === "IMG") {
      lockImage(node);
      return;
    }
    node.querySelectorAll("img").forEach(lockImage);
  }

  // Capture phase so page scripts cannot re-enable the menu by accident.
  documentRef.addEventListener(
    "contextmenu",
    (event) => {
      if (isProtectedTarget(event.target)) event.preventDefault();
    },
    true,
  );

  documentRef.addEventListener(
    "dragstart",
    (event) => {
      // Arrange-mode cards are draggable on purpose; only image drags stop.
      const target = event.target;
      if (target instanceof Element && (target.tagName === "IMG" || target.closest("[data-protected-media]"))) {
        event.preventDefault();
      }
    },
    true,
  );

  function start() {
    lockImagesWithin(documentRef.body);
    new MutationObserver((records) => {
      records.forEach((record) => record.addedNodes.forEach(lockImagesWithin));
    }).observe(documentRef.body, { childList: true, subtree: true });
  }

  if (documentRef.body) {
    start();
  } else {
    documentRef.addEventListener("DOMContentLoaded", start, { once: true });
  }
})(window);
