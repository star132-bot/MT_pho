(function initializeAdminShell(global) {
  // One navigation for every staff page (design/admin-mockups-v4). The page
  // names itself with <body data-admin-page="…">; the sidebar markup holds the
  // brand and the account slot, and this script fills in the links.
  const ICONS = {
    overview: '<path d="m3 10.5 9-7.5 9 7.5" /><path d="M5 9v12h14V9" /><path d="M10 21v-6h4v6" />',
    upload: '<path d="M7 18H6a4 4 0 0 1-.5-7.97A6 6 0 0 1 17.3 8.6 4.5 4.5 0 0 1 18 18h-1" /><path d="M12 12v8" /><path d="m8.5 15.5 3.5-3.5 3.5 3.5" />',
    "site-images": '<rect x="3" y="4" width="18" height="16" rx="1.5" /><path d="m3 16 5-5 4 4 3-3 6 6" /><circle cx="15.5" cy="8.5" r="1.4" />',
    works: '<rect x="3" y="3" width="7.5" height="7.5" rx="1" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="1" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="1" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1" />',
    inquiries: '<path d="M4 5h16v11H9l-5 4z" /><path d="M8 9.5h8M8 12.5h5" />',
    account: '<circle cx="12" cy="8" r="3.6" /><path d="M5 20a7 7 0 0 1 14 0" />',
  };
  const LINKS = [
    ["overview", "/admin", "总览"],
    ["upload", "/workspace/images", "上传图片"],
    ["site-images", "/admin/site-images", "网站图片位"],
    ["works", "/admin/works", "作品管理"],
    ["inquiries", "/inbox", "询价"],
    ["account", "/settings/account", "账号"],
  ];

  const page = document.body.dataset.adminPage || "";
  const nav = document.querySelector("[data-admin-nav]");
  if (nav) {
    nav.replaceChildren(...LINKS.map(([key, href, label]) => {
      const link = document.createElement("a");
      link.href = href;
      if (key === page) link.setAttribute("aria-current", "page");
      link.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[key]}</svg>`;
      const text = document.createElement("span");
      text.textContent = label;
      link.append(text);
      if (key === "inquiries") {
        const badge = document.createElement("span");
        badge.className = "admin-nav-badge";
        badge.hidden = true;
        badge.dataset.adminUnread = "";
        link.append(badge);
      }
      return link;
    }));
  }

  async function getJson(path) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error?.message || "Request failed");
      error.status = response.status;
      error.code = payload.error?.code || "";
      throw error;
    }
    return payload;
  }

  async function showUnread() {
    const badge = document.querySelector("[data-admin-unread]");
    if (!badge) return;
    try {
      const payload = await getJson("/api/inbox?status=open&limit=50");
      const unread = (payload.items || []).reduce((sum, item) => sum + (Number(item.unread_count) > 0 ? 1 : 0), 0);
      badge.textContent = String(unread);
      badge.hidden = unread === 0;
      document.dispatchEvent(new CustomEvent("mt:admin-unread", { detail: { unread } }));
    } catch (_error) {
      badge.hidden = true;
    }
  }

  async function showConnection() {
    const element = document.querySelector("[data-admin-connection]");
    if (!element) return;
    const dot = element.querySelector(".admin-dot");
    const label = element.querySelector("[data-admin-connection-label]");
    try {
      const payload = await getJson("/readyz");
      const ok = payload.status === "ready";
      dot.dataset.tone = ok ? "ok" : "bad";
      label.textContent = ok ? "数据连接 · 正常" : "数据连接 · 异常";
    } catch (_error) {
      dot.dataset.tone = "bad";
      label.textContent = "数据连接 · 异常";
    }
  }

  // ----- Shared helpers for the staff pages ---------------------------------

  // The two series of the site (stored as content_category).
  const SERIES = { concrete: "此间留彩", abstract: "此间留灰" };
  const SLOT_LABELS = {
    home_hero: "首页大图",
    home_selected: "首页精选作品",
    home_about: "关于照片",
    works_poster_colour: "作品页海报 · 此间留彩",
    works_poster_grey: "作品页海报 · 此间留灰",
    contact: "联系页配图",
  };
  const STEP_LABELS = ["上传", "安全扫描", "生成展示图", "可发布"];

  // Where an image is in upload → scan → derivatives → publishable.
  // Returns { index, failed } with index of the current step (0-3).
  function imageStage(work) {
    const summary = work.asset_summary || {};
    const derivatives = work.derivatives || {};
    if (Number(summary.flagged_count) > 0 || Number(summary.failed_count) > 0) return { index: 1, failed: true };
    if (work.processing_status === "failed" || work.processing_status === "canceled") return { index: 0, failed: true };
    if (work.processing_status === "pending" || work.processing_status === "uploading") return { index: 0, failed: false };
    if (Number(summary.pending_count) > 0) return { index: 1, failed: false };
    if (work.processing_status === "processing" || !derivatives.display || !derivatives.thumbnail) return { index: 2, failed: false };
    return { index: 3, failed: false, done: work.publication_status === "published" };
  }

  function stepsElement(work) {
    const stage = imageStage(work);
    const list = document.createElement("ol");
    list.className = "admin-steps";
    list.setAttribute("aria-label", `进度：${STEP_LABELS[stage.index]}${stage.failed ? "失败" : ""}`);
    STEP_LABELS.forEach((label, index) => {
      const item = document.createElement("li");
      item.textContent = label;
      if (index < stage.index || (index === stage.index && stage.done)) item.dataset.state = "done";
      else if (index === stage.index) item.dataset.state = stage.failed ? "failed" : "current";
      list.append(item);
    });
    return list;
  }

  function formatBytes(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) return "—";
    if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(value, { withDate = "auto" } = {}) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    const today = new Date();
    const sameDay = date.toDateString() === today.toDateString();
    const pad = (number) => String(number).padStart(2, "0");
    const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    if (withDate === false || (withDate === "auto" && sameDay)) return time;
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${time}`;
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    const pad = (number) => String(number).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  // Signed-out, unverified or recovery sessions go where they can continue.
  function redirectForAuth(error) {
    const next = `${global.location.pathname}${global.location.search}`;
    if (error?.status === 401) {
      global.location.assign(`/auth/sign-in?next=${encodeURIComponent(next)}`);
      return true;
    }
    if (error?.status === 403 && error.code === "MFA_REQUIRED") {
      global.location.assign(`/auth/mfa?next=${encodeURIComponent(next)}`);
      return true;
    }
    if (error?.status === 403 && error.code === "RECOVERY_SESSION_RESTRICTED") {
      global.location.assign("/auth/reset-password");
      return true;
    }
    return false;
  }

  global.MTAdminShell = {
    getJson,
    refreshUnread: showUnread,
    SERIES,
    SLOT_LABELS,
    STEP_LABELS,
    imageStage,
    stepsElement,
    formatBytes,
    formatTime,
    formatDate,
    redirectForAuth,
  };
  showUnread();
  showConnection();
})(window);
