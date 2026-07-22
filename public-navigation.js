(function initializePublicNavigation() {
  const mobileNavigation = window.matchMedia("(max-width: 760px)");

  document.querySelectorAll("[data-public-header]").forEach((header) => {
    const navigation = header.querySelector("[data-public-nav]");
    const trigger = header.querySelector("[data-public-nav-toggle]");
    if (!navigation || !trigger) return;

    function navigationLinks() {
      return Array.from(navigation.querySelectorAll("a[href]"));
    }

    function setOpen(open, options = {}) {
      const isOpen = Boolean(open && mobileNavigation.matches);
      header.classList.toggle("is-menu-open", isOpen);
      header.dataset.publicNavOpen = String(isOpen);
      trigger.setAttribute("aria-expanded", String(isOpen));
      trigger.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
      trigger.title = isOpen ? "Close navigation" : "Open navigation";

      if (mobileNavigation.matches) {
        navigation.toggleAttribute("inert", !isOpen);
        navigation.setAttribute("aria-hidden", String(!isOpen));
      } else {
        navigation.removeAttribute("inert");
        navigation.removeAttribute("aria-hidden");
      }

      if (isOpen && options.focusFirst) navigationLinks()[0]?.focus();
      if (!isOpen && options.restoreFocus) trigger.focus();
    }

    function isOpen() {
      return trigger.getAttribute("aria-expanded") === "true";
    }

    trigger.addEventListener("click", (event) => {
      setOpen(!isOpen(), { focusFirst: event.detail === 0 });
    });

    trigger.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown") return;
      event.preventDefault();
      setOpen(true, { focusFirst: true });
    });

    navigation.addEventListener("click", (event) => {
      if (event.target.closest("a[href]") && mobileNavigation.matches) setOpen(false);
    });

    header.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !isOpen()) return;
      event.preventDefault();
      setOpen(false, { restoreFocus: true });
    });

    header.addEventListener("focusout", () => {
      window.setTimeout(() => {
        if (isOpen() && !header.contains(document.activeElement)) setOpen(false);
      }, 0);
    });

    document.addEventListener("pointerdown", (event) => {
      if (isOpen() && !header.contains(event.target)) setOpen(false);
    });

    const synchronizeNavigation = () => setOpen(false);
    if (typeof mobileNavigation.addEventListener === "function") {
      mobileNavigation.addEventListener("change", synchronizeNavigation);
    } else {
      mobileNavigation.addListener(synchronizeNavigation);
    }
    synchronizeNavigation();
  });
})();
