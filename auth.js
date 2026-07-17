const form = document.querySelector("[data-auth-form]");
const submitButton = document.querySelector("[data-auth-submit]");
const notice = document.querySelector("[data-auth-notice]");
const openBrowserLink = document.querySelector("[data-auth-open-browser]");
const title = document.querySelector("#auth-title");
const intro = document.querySelector("[data-auth-intro]");
const loading = document.querySelector("[data-auth-loading]");
const loadingCopy = document.querySelector("[data-auth-loading-copy]");
const switchCopy = document.querySelector("[data-auth-switch-copy]");
const switchLink = document.querySelector("[data-auth-switch-link]");
const switchRow = document.querySelector(".auth-switch");
const forgotLink = document.querySelector("[data-auth-forgot-link]");
const nextLink = document.querySelector("[data-auth-next-link]");
const passwordLabel = document.querySelector("[data-password-label]");
const passwordHint = document.querySelector("[data-password-hint]");
const fieldGroups = new Map(
  [...document.querySelectorAll("[data-auth-field]")].map((element) => [element.dataset.authField, element]),
);

const MODE_BY_PATH = {
  "/auth/sign-in": "signIn",
  "/auth/register": "register",
  "/auth/forgot-password": "forgotPassword",
  "/auth/reset-password": "resetPassword",
  "/auth/verify-email": "verifyEmail",
};

const MODES = {
  signIn: {
    documentTitle: "Sign In",
    eyebrow: "Private Workspace",
    title: "Sign in",
    intro: "Continue to your images, drafts, and review activity.",
    fields: ["email", "password"],
    endpoint: "/api/auth/sign-in",
    submit: "Sign in",
    pending: "Signing in…",
    switchCopy: "New to MT Presence?",
    switchLabel: "Create an account",
    switchHref: "/auth/register",
  },
  register: {
    documentTitle: "Create Account",
    eyebrow: "Private Workspace",
    title: "Create account",
    intro: "Create a verified account to upload images and submit work for review.",
    fields: ["display_name", "email", "password", "terms_accepted"],
    endpoint: "/api/auth/register",
    submit: "Create account",
    pending: "Creating account…",
    switchCopy: "Already have an account?",
    switchLabel: "Sign in",
    switchHref: "/auth/sign-in",
  },
  forgotPassword: {
    documentTitle: "Reset Password",
    eyebrow: "Account Recovery",
    title: "Reset your password",
    intro: "Enter your email and we’ll send a secure, time-limited reset link.",
    fields: ["email"],
    endpoint: "/api/auth/forgot-password",
    submit: "Send reset link",
    pending: "Sending secure link…",
    switchCopy: "Remembered your password?",
    switchLabel: "Return to sign in",
    switchHref: "/auth/sign-in",
  },
  resetPassword: {
    documentTitle: "Choose New Password",
    eyebrow: "Security Checkpoint",
    title: "Choose a new password",
    intro: "Use a strong password that you do not use for another account.",
    fields: ["password", "password_confirmation"],
    endpoint: "/api/auth/reset-password",
    submit: "Update password",
    pending: "Updating password…",
    switchCopy: "Need a new recovery link?",
    switchLabel: "Request another link",
    switchHref: "/auth/forgot-password",
    callbackType: "recovery",
    callbackEndpoint: "/api/auth/recovery-session",
  },
  verifyEmail: {
    documentTitle: "Verify Email",
    eyebrow: "Email Verification",
    title: "Verify your email",
    intro: "We’re confirming your secure email link.",
    fields: [],
    switchCopy: "Already verified?",
    switchLabel: "Return to sign in",
    switchHref: "/auth/sign-in",
    callbackType: "signup",
    callbackEndpoint: "/api/auth/verify-email",
  },
};

const mode = MODE_BY_PATH[window.location.pathname] || "signIn";
const config = MODES[mode];
const BLOCKED_NEXT_PATHS = new Set([
  "/auth/sign-in",
  "/auth/register",
  "/auth/forgot-password",
  "/auth/reset-password",
  "/auth/verify-email",
  "/auth/mfa",
]);
let csrfTokenPromise = null;

function safeInternalPath(value, fallback = "/workspace/images") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return fallback;
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin || BLOCKED_NEXT_PATHS.has(url.pathname)) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}

function setFieldVisibility(name, visible) {
  const group = fieldGroups.get(name);
  if (!group) return;
  group.hidden = !visible;
  group.querySelectorAll("input").forEach((input) => {
    input.disabled = !visible;
    input.required = visible;
  });
}

function configureMode() {
  document.body.dataset.authMode = mode;
  document.title = `${config.documentTitle} | MT Presence`;
  document.querySelector(".auth-eyebrow").textContent = config.eyebrow;
  title.textContent = config.title;
  intro.textContent = config.intro;
  submitButton.textContent = config.submit || "Continue";
  switchCopy.textContent = config.switchCopy;
  switchLink.textContent = config.switchLabel;
  switchLink.href = config.switchHref;
  switchRow.hidden = false;
  forgotLink.hidden = mode !== "signIn";
  nextLink.hidden = true;

  fieldGroups.forEach((_, name) => setFieldVisibility(name, config.fields.includes(name)));
  const password = form.elements.password;
  if (password) {
    password.autocomplete = mode === "signIn" ? "current-password" : "new-password";
    passwordLabel.textContent = mode === "resetPassword" ? "New password" : "Password";
    passwordHint.hidden = !["register", "resetPassword"].includes(mode);
  }

  if (config.callbackType) {
    form.hidden = true;
    loading.hidden = false;
    loadingCopy.textContent = config.callbackType === "recovery"
      ? "Validating your recovery link…"
      : "Confirming your email…";
  }
}

function clearErrors() {
  notice.hidden = true;
  notice.className = "auth-notice";
  notice.setAttribute("role", "status");
  openBrowserLink.hidden = true;
  form.querySelectorAll("[aria-invalid]").forEach((input) => input.removeAttribute("aria-invalid"));
  form.querySelectorAll("[data-field-error]").forEach((error) => {
    error.textContent = "";
  });
  form.elements.password_confirmation?.setCustomValidity("");
}

function showNotice(message, kind = "error") {
  notice.textContent = message;
  notice.className = `auth-notice is-${kind}`;
  notice.setAttribute("role", kind === "error" ? "alert" : "status");
  notice.hidden = false;
  notice.focus();
}

function applyFieldErrors(errors = {}) {
  let firstInvalid = null;
  Object.entries(errors).forEach(([name, message]) => {
    const input = form.elements.namedItem(name);
    const error = form.querySelector(`[data-field-error="${CSS.escape(name)}"]`);
    if (input) {
      input.setAttribute("aria-invalid", "true");
      firstInvalid ||= input;
    }
    if (error) error.textContent = message;
  });
  firstInvalid?.focus();
}

function setBusy(busy) {
  form.setAttribute("aria-busy", String(busy));
  submitButton.disabled = busy;
  submitButton.textContent = busy ? config.pending : config.submit;
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
      if (!response.ok || !result.csrf_token) throw new Error("Unable to initialize the secure form.");
      return result.csrf_token;
    });
  }
  return csrfTokenPromise;
}

async function authRequest(path, options = {}, retryCsrf = true) {
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
    return authRequest(path, options, false);
  }
  return { response, result };
}

function callbackParameters() {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const query = new URLSearchParams(window.location.search);
  const params = hash.has("token_hash") || hash.has("refresh_token") || hash.has("error_code") ? hash : query;
  const payload = {
    type: String(params.get("type") || "").toLowerCase(),
    token_hash: String(params.get("token_hash") || ""),
    refresh_token: String(params.get("refresh_token") || ""),
    hasError: Boolean(params.get("error") || params.get("error_code")),
  };
  if (window.location.hash || query.has("token_hash") || query.has("refresh_token") || query.has("code")) {
    window.history.replaceState({}, document.title, window.location.pathname);
  }
  return payload;
}

function showCompletion(message, label = "Return to sign in", href = "/auth/sign-in") {
  loading.hidden = true;
  form.hidden = true;
  forgotLink.hidden = true;
  switchRow.hidden = true;
  showNotice(message, "success");
  nextLink.textContent = label;
  nextLink.href = href;
  nextLink.hidden = false;
}

function showInvalidCallback(message) {
  loading.hidden = true;
  form.hidden = true;
  switchRow.hidden = true;
  showNotice(message);
  nextLink.textContent = mode === "resetPassword" ? "Request a new link" : "Return to sign in";
  nextLink.href = mode === "resetPassword" ? "/auth/forgot-password" : "/auth/sign-in";
  nextLink.hidden = false;
}

async function prepareCallbackMode() {
  const callback = callbackParameters();
  if (callback.hasError) {
    showInvalidCallback("This secure link is invalid or has expired.");
    return;
  }

  try {
    if (callback.type || callback.token_hash || callback.refresh_token) {
      if (callback.type !== config.callbackType || (!callback.token_hash && !callback.refresh_token)) {
        showInvalidCallback("This secure link is invalid or has expired.");
        return;
      }
      const { response, result } = await authRequest(config.callbackEndpoint, {
        method: "POST",
        body: JSON.stringify({
          type: callback.type,
          token_hash: callback.token_hash,
          refresh_token: callback.refresh_token,
        }),
      });
      if (!response.ok) {
        showInvalidCallback(result.error?.message || "This secure link is invalid or has expired.");
        return;
      }
    } else {
      const statusPath = mode === "resetPassword" ? "/api/auth/recovery-status" : "/api/auth/verification-status";
      const { response, result } = await authRequest(statusPath);
      const ready = mode === "resetPassword" ? result.recovery_ready === true : result.email_verified === true;
      if (!response.ok || !ready) {
        showInvalidCallback("This secure link is invalid or has expired.");
        return;
      }
    }

    loading.hidden = true;
    if (mode === "verifyEmail") {
      showCompletion("Email verified. Your secure Workspace is ready.", "Enter your workspace", "/workspace/images");
      return;
    }
    form.hidden = false;
    window.setTimeout(() => form.elements.password?.focus(), 0);
  } catch {
    loading.hidden = true;
    showInvalidCallback("Unable to validate this secure link. Check your connection and try again.");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors();
  if (mode === "resetPassword") {
    const password = form.elements.password.value;
    const confirmation = form.elements.password_confirmation.value;
    if (password !== confirmation) {
      form.elements.password_confirmation.setCustomValidity("Passwords do not match.");
      applyFieldErrors({ password_confirmation: "Passwords do not match." });
      return;
    }
  }
  if (!form.reportValidity()) return;
  setBusy(true);

  const data = new FormData(form);
  const payload = {};
  config.fields.forEach((field) => {
    if (field === "terms_accepted") {
      payload[field] = data.get(field) === "on";
    } else {
      const value = String(data.get(field) || "");
      payload[field] = ["password", "password_confirmation"].includes(field) ? value : value.trim();
    }
  });

  try {
    const { response, result } = await authRequest(config.endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      showNotice(result.error?.message || "Unable to continue. Try again.");
      applyFieldErrors(result.error?.field_errors);
      return;
    }

    if (mode === "register") {
      form.reset();
      showCompletion(result.message || "Check your email to verify your account.");
      return;
    }
    if (mode === "forgotPassword") {
      form.reset();
      showCompletion(result.message || "If an account exists for this email, a reset link has been sent.");
      return;
    }
    if (mode === "resetPassword") {
      form.reset();
      showCompletion(result.message || "Password updated. Sign in with your new password.");
      return;
    }

    const sessionCheck = await authRequest("/api/me");
    if (!sessionCheck.response.ok) {
      const next = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
      const browserUrl = new URL("/auth/sign-in", window.location.origin);
      browserUrl.searchParams.set("next", next);
      openBrowserLink.href = browserUrl.href;
      openBrowserLink.hidden = false;
      if (sessionCheck.response.status === 401) {
        showNotice("This embedded preview did not retain the secure session. Open sign-in in a full browser and try again.");
      } else {
        openBrowserLink.hidden = true;
        showNotice("Authentication is temporarily unavailable. Please try again shortly.");
      }
      return;
    }
    const next = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
    if (result.next_action === "mfa") {
      window.location.assign(`/auth/mfa?next=${encodeURIComponent(next)}`);
      return;
    }
    window.location.assign(next);
  } catch {
    showNotice("Unable to reach the server. Check your connection and try again.");
  } finally {
    setBusy(false);
  }
});

configureMode();
if (config.callbackType) prepareCallbackMode();
