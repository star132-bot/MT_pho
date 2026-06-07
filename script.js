const root = document.documentElement;
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function easeInOutCubic(value) {
  return value < 0.5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function updateHeroTransition() {
  const hero = document.querySelector(".hero");
  const stage = document.querySelector(".hero-stage");
  if (!hero) {
    return;
  }

  const stageRect = stage ? stage.getBoundingClientRect() : hero.getBoundingClientRect();
  const stageTravel = Math.max((stage?.offsetHeight || hero.offsetHeight) - window.innerHeight, 1);
  const progress = Math.min(Math.max(-stageRect.top / stageTravel, 0), 1);
  const coverProgress = Math.min(Math.max((progress - 0.08) / 0.82, 0), 1);
  const scale = 1 + progress * 0.012;
  const abstractScale = 1 + progress * 0.095;
  const concreteScale = 1.045 - coverProgress * 0.025;
  const copyOpacity = 1 - progress * 0.36;
  const copyShift = progress * -44;
  const overlayOpacity = 1 - progress * 0.52;

  root.style.setProperty("--hero-scale", scale.toFixed(3));
  root.style.setProperty("--hero-cover-progress", coverProgress.toFixed(3));
  root.style.setProperty("--hero-abstract-scale", abstractScale.toFixed(3));
  root.style.setProperty("--hero-concrete-scale", concreteScale.toFixed(3));
  root.style.setProperty("--hero-copy-opacity", copyOpacity.toFixed(3));
  root.style.setProperty("--hero-copy-shift", `${copyShift.toFixed(1)}px`);
  root.style.setProperty("--hero-overlay-opacity", overlayOpacity.toFixed(3));
  document.body.classList.toggle("is-scrolled", progress > 0.08);
}

function scrollToTarget(target) {
  const startY = window.scrollY;
  const targetY = target.getBoundingClientRect().top + startY;
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

window.addEventListener("scroll", updateHeroTransition, { passive: true });
window.addEventListener("resize", updateHeroTransition);
updateHeroTransition();
