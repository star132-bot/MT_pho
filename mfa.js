const intro = document.querySelector("[data-mfa-intro]");
const notice = document.querySelector("[data-mfa-notice]");
const loading = document.querySelector("[data-mfa-loading]");
const enrollment = document.querySelector("[data-mfa-enrollment]");
const qrImage = document.querySelector("[data-mfa-qr]");
const secret = document.querySelector("[data-mfa-secret]");
const form = document.querySelector("[data-mfa-form]");
const submit = document.querySelector("[data-mfa-submit]");
const signOut = document.querySelector("[data-mfa-sign-out]");

let factorId = "";
let csrfTokenPromise = null;

function safeInternalPath(value, fallback = "/workspace/images") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return fallback;
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return fallback;
    if (["/auth/sign-in", "/auth/register", "/auth/forgot-password", "/auth/reset-password", "/auth/verify-email", "/auth/mfa"].includes(url.pathname)) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}

function showNotice(message, kind = "error") {
  notice.textContent = message;
  notice.className = `auth-notice is-${kind}`;
  notice.hidden = false;
  notice.focus();
}

async function csrfToken(force = false) {
  if (force) csrfTokenPromise = null;
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetch("/api/auth/csrf", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.csrf_token) throw new Error("Unable to initialize security verification.");
      return result.csrf_token;
    });
  }
  return csrfTokenPromise;
}

async function request(path, options = {}, retryCsrf = true) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (!["GET", "HEAD"].includes(method)) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = await csrfToken();
  }
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    method,
    headers,
  });
  const result = await response.json().catch(() => ({}));
  if (response.status === 403 && result.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await csrfToken(true);
    return request(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || "Unable to complete security verification.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function factorList(result) {
  if (Array.isArray(result)) return result;
  if (Array.isArray(result.all)) return result.all;
  if (Array.isArray(result.totp)) return result.totp;
  if (Array.isArray(result.factors)) return result.factors;
  return [];
}

function showCodeForm(isEnrollment) {
  loading.hidden = true;
  enrollment.hidden = !isEnrollment;
  form.hidden = false;
  intro.textContent = isEnrollment
    ? "Set up a time-based one-time password before entering protected administration."
    : "Enter the current code from your authenticator to continue.";
  window.setTimeout(() => form.elements.code.focus(), 0);
}

function qrSource(value) {
  if (!value) return "";
  const source = value.trim();
  const isSvgMarkup = source.startsWith("<svg") || (source.startsWith("<?xml") && source.includes("<svg"));
  if (isSvgMarkup) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(source)}`;
  }
  if (source.startsWith("data:image/svg+xml") && !source.includes(";base64,")) {
    const separator = source.indexOf(",");
    if (separator > -1) {
      const payload = source.slice(separator + 1);
      let svg = payload;
      try {
        svg = decodeURIComponent(payload);
      } catch {
        // Supabase may return raw SVG after the data URI prefix.
      }
      const normalized = svg.trim();
      if (normalized.startsWith("<svg") || (normalized.startsWith("<?xml") && normalized.includes("<svg"))) {
        return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
      }
    }
  }
  return source.startsWith("data:image/") ? source : "";
}

async function prepare() {
  try {
    const factors = factorList(await request("/api/auth/mfa/factors"));
    const verified = factors.find((factor) => factor.factor_type === "totp" && factor.status === "verified")
      || factors.find((factor) => factor.type === "totp" && factor.status === "verified");
    if (verified) {
      factorId = verified.id;
      showCodeForm(false);
      return;
    }

    const pending = factors.find((factor) => (factor.factor_type === "totp" || factor.type === "totp") && factor.status !== "verified");
    if (pending) {
      intro.textContent = "Resetting the incomplete authenticator setup…";
    }

    const factor = await request("/api/auth/mfa/enroll", { method: "POST", body: JSON.stringify({}) });
    const source = qrSource(factor.totp?.qr_code || factor.totp?.qrCode || "");
    if (!factor.id || !source || !factor.totp?.secret) {
      throw new Error("A complete authenticator setup could not be created. Refresh and try again.");
    }
    factorId = factor.id;
    qrImage.src = source;
    secret.textContent = factor.totp.secret;
    showCodeForm(true);
  } catch (error) {
    loading.hidden = true;
    if (error.status === 401) {
      const next = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
      window.location.assign(`/auth/sign-in?next=${encodeURIComponent(next)}`);
      return;
    }
    showNotice(error.message);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  notice.hidden = true;
  if (!form.reportValidity() || !factorId) return;
  submit.disabled = true;
  submit.textContent = "Verifying…";
  try {
    const challenge = await request("/api/auth/mfa/challenge", {
      method: "POST",
      body: JSON.stringify({ factor_id: factorId }),
    });
    await request("/api/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ factor_id: factorId, challenge_id: challenge.id, code: form.elements.code.value.trim() }),
    });
    const access = await request("/api/admin/access-check");
    if (!access.allowed) throw new Error("Administrator access could not be verified.");
    showNotice("Identity verified. Protected administrator access is active.", "success");
    const next = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
    window.setTimeout(() => window.location.assign(next), 500);
  } catch (error) {
    form.elements.code.select();
    showNotice(error.message);
  } finally {
    submit.disabled = false;
    submit.textContent = "Verify and continue";
  }
});

signOut.addEventListener("click", async () => {
  signOut.disabled = true;
  try {
    await request("/api/auth/sign-out", { method: "POST", body: JSON.stringify({}) });
  } finally {
    window.location.assign("/auth/sign-in");
  }
});

prepare();
