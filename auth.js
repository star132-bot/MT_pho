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
const resendLink = document.querySelector("[data-auth-resend-link]");
const nextLink = document.querySelector("[data-auth-next-link]");
const passwordLabel = document.querySelector("[data-password-label]");
const passwordConfirmationLabel = document.querySelector("[data-password-confirmation-label]");
const passwordHint = document.querySelector("[data-password-hint]");
const oauthGroup = document.querySelector("[data-auth-oauth]");
const oauthProviderLinks = new Map(
  [...document.querySelectorAll("[data-auth-provider]")].map((link) => [link.dataset.authProvider, link]),
);
const enabledOAuthProviders = new Set(
  (document.querySelector("[data-enabled-oauth-providers]")?.content.textContent || "google")
    .split(",")
    .map((provider) => provider.trim().toLowerCase())
    .filter(Boolean),
);
const fieldGroups = new Map(
  [...document.querySelectorAll("[data-auth-field]")].map((element) => [element.dataset.authField, element]),
);

const MODE_BY_PATH = {
  "/auth/sign-in": "signIn",
  "/auth/forgot-password": "forgotPassword",
  "/auth/reset-password": "resetPassword",
};

const MODES = {
  signIn: {
    documentTitle: "登录",
    eyebrow: "后台",
    title: "登录",
    intro: "仅限网站管理人员。访客浏览网站不需要账号。",
    fields: ["email", "password"],
    endpoint: "/api/auth/sign-in",
    submit: "登录",
    pending: "正在登录…",
  },
  forgotPassword: {
    documentTitle: "找回密码",
    eyebrow: "找回密码",
    title: "找回密码",
    intro: "输入邮箱，我们会发送一个有时效的验证码。",
    fields: ["email", "recovery_code"],
    endpoint: "/api/auth/forgot-password",
    submit: "发送验证码",
    pending: "正在发送…",
    switchCopy: "想起密码了？",
    switchLabel: "返回登录",
    switchHref: "/auth/sign-in",
  },
  resetPassword: {
    documentTitle: "设置新密码",
    eyebrow: "设置新密码",
    title: "设置新密码",
    intro: "请使用一个没有在其他网站用过的密码。",
    fields: ["password", "password_confirmation"],
    endpoint: "/api/auth/reset-password",
    submit: "更新密码",
    pending: "正在更新…",
    switchCopy: "链接失效了？",
    switchLabel: "重新获取",
    switchHref: "/auth/forgot-password",
    callbackType: "recovery",
    callbackEndpoint: "/api/auth/recovery-session",
  },
};

const mode = MODE_BY_PATH[window.location.pathname] || "signIn";
const config = MODES[mode];
const BLOCKED_NEXT_PATHS = new Set([
  "/auth/sign-in",
  "/auth/forgot-password",
  "/auth/reset-password",
  "/auth/mfa",
]);
const DEFAULT_AUTH_DESTINATION = "/works.html";
let csrfTokenPromise = null;
let recoveryCodeStep = false;
let recoveryEmail = "";

function safeInternalPath(value, fallback = DEFAULT_AUTH_DESTINATION) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return fallback;
  try {
    let decoded = value;
    for (let depth = 0; depth < 5; depth += 1) {
      if (/[\u0000-\u001f\u007f\\]/.test(decoded)) return fallback;
      // A decoded literal percent is valid in a query. Escape stray percents
      // before the next pass while still decoding nested encoded controls.
      const next = decodeURIComponent(decoded.replace(/%(?![0-9a-f]{2})/gi, "%25"));
      if (next === decoded) break;
      if (depth === 4) return fallback;
      decoded = next;
    }
    if (decoded.startsWith("//")) return fallback;
    const decodedURL = new URL(decoded, window.location.origin);
    if (decodedURL.origin !== window.location.origin
      || /^\/(?:auth|api)(?:\/|$)/.test(decodedURL.pathname)) return fallback;
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin
      || /^\/(?:auth|api)(?:\/|$)/.test(url.pathname)
      || BLOCKED_NEXT_PATHS.has(url.pathname)) return fallback;
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
  switchRow.hidden = !config.switchHref;
  if (config.switchHref) {
    switchCopy.textContent = config.switchCopy;
    switchLink.textContent = config.switchLabel;
    switchLink.href = config.switchHref;
  }
  forgotLink.hidden = mode !== "signIn";
  resendLink.hidden = true;
  nextLink.hidden = true;
  oauthGroup.hidden = mode !== "signIn";
  const requestedNext = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
  oauthProviderLinks.forEach((link, provider) => {
    link.hidden = !enabledOAuthProviders.has(provider);
    link.href = `/auth/oauth/${provider}?next=${encodeURIComponent(requestedNext)}`;
  });

  fieldGroups.forEach((_, name) => setFieldVisibility(name, config.fields.includes(name)));
  if (mode === "forgotPassword") setFieldVisibility("recovery_code", false);
  const password = form.elements.password;
  if (password) {
    password.autocomplete = mode === "signIn" ? "current-password" : "new-password";
    passwordLabel.textContent = mode === "resetPassword" ? "新密码" : "密码";
    password.minLength = mode === "signIn" ? 1 : 12;
    password.maxLength = mode === "signIn" ? 256 : 128;
    passwordHint.hidden = mode !== "resetPassword";
  }
  if (passwordConfirmationLabel) {
    passwordConfirmationLabel.textContent = mode === "resetPassword" ? "Confirm new password" : "Confirm password";
  }

  if (config.callbackType) {
    form.hidden = true;
    loading.hidden = false;
    loadingCopy.textContent = "正在验证链接…";
  }
}

function showOAuthResult() {
  if (mode !== "signIn") return;
  const url = new URL(window.location.href);
  const code = url.searchParams.get("oauth_error");
  if (!code) return;
  const provider = url.searchParams.get("oauth_provider") === "apple" ? "Apple" : "Google";
  const messages = {
    cancelled: `${provider} sign-in was cancelled.`,
    restricted: `This ${provider} account is not a site staff account.`,
    invalid: `The ${provider} sign-in request is invalid or has expired. Try again.`,
    unavailable: `${provider} sign-in is temporarily unavailable. Try again shortly.`,
  };
  showNotice(messages[code] || messages.invalid);
  url.searchParams.delete("oauth_error");
  url.searchParams.delete("oauth_provider");
  window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`);
}

function clearErrors() {
  notice.hidden = true;
  notice.className = "auth-notice";
  notice.setAttribute("role", "status");
  openBrowserLink.hidden = true;
  resendLink.hidden = true;
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
  submitButton.textContent = busy
    ? (recoveryCodeStep ? "正在验证…" : config.pending)
    : (recoveryCodeStep ? "验证" : config.submit);
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

function showCompletion(message, label = "返回登录", href = "/auth/sign-in") {
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
    showInvalidCallback("这个链接无效或已过期。");
    return;
  }

  try {
    const hasCallback = Boolean(callback.type || callback.token_hash || callback.refresh_token);
    if (hasCallback) {
      if (callback.type !== config.callbackType || (!callback.token_hash && !callback.refresh_token)) {
        showInvalidCallback("这个链接无效或已过期。");
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
        showInvalidCallback(result.error?.message || "这个链接无效或已过期。");
        return;
      }
    } else {
      const { response, result } = await authRequest("/api/auth/recovery-status");
      if (!response.ok || result.recovery_ready !== true) {
        showInvalidCallback("这个链接无效或已过期。");
        return;
      }
    }

    loading.hidden = true;
    form.hidden = false;
    window.setTimeout(() => form.elements.password?.focus(), 0);
  } catch {
    loading.hidden = true;
    showInvalidCallback("无法验证链接，请检查网络后重试。");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors();
  if (mode === "resetPassword") {
    const password = form.elements.password.value;
    const confirmation = form.elements.password_confirmation.value;
    if (password !== confirmation) {
      form.elements.password_confirmation.setCustomValidity("两次输入的密码不一致。");
      applyFieldErrors({ password_confirmation: "两次输入的密码不一致。" });
      return;
    }
  }
  if (!form.reportValidity()) return;
  setBusy(true);

  const data = new FormData(form);
  const payload = {};
  config.fields.forEach((field) => {
    const value = String(data.get(field) || "");
    payload[field] = ["password", "password_confirmation"].includes(field) ? value : value.trim();
  });

  try {
    const requestPath = mode === "forgotPassword" && recoveryCodeStep
      ? "/api/auth/verify-recovery-code"
      : config.endpoint;
    const requestPayload = mode === "forgotPassword" && recoveryCodeStep
      ? { email: recoveryEmail, recovery_code: payload.recovery_code }
      : mode === "forgotPassword"
        ? { email: payload.email }
        : payload;
    const { response, result } = await authRequest(requestPath, {
      method: "POST",
      body: JSON.stringify(requestPayload),
    });
    if (!response.ok) {
      showNotice(result.error?.message || "操作没有完成，请重试。");
      applyFieldErrors(result.error?.field_errors);
      if (mode === "forgotPassword" && recoveryCodeStep) {
        resendLink.textContent = "重新获取验证码";
        resendLink.href = "/auth/forgot-password";
        resendLink.hidden = false;
      }
      return;
    }

    if (mode === "forgotPassword") {
      if (!recoveryCodeStep) {
        recoveryEmail = payload.email;
        recoveryCodeStep = true;
        setFieldVisibility("email", false);
        setFieldVisibility("recovery_code", true);
        resendLink.textContent = "重新获取验证码";
        resendLink.href = "/auth/forgot-password";
        resendLink.hidden = false;
        showNotice("如果这个邮箱有账号，验证码已经发出，请在下面输入。", "success");
        window.setTimeout(() => form.elements.recovery_code?.focus(), 0);
        return;
      }
      form.reset();
      window.location.assign("/auth/reset-password");
      return;
    }
    if (mode === "resetPassword") {
      form.reset();
      showCompletion("密码已更新，请用新密码登录。");
      return;
    }

    const sessionCheck = await authRequest("/api/me");
    const mfaPending = sessionCheck.response.status === 403
      && sessionCheck.result?.error?.code === "MFA_REQUIRED";
    if (!sessionCheck.response.ok && !mfaPending) {
      const next = safeInternalPath(new URLSearchParams(window.location.search).get("next"));
      const browserUrl = new URL("/auth/sign-in", window.location.origin);
      browserUrl.searchParams.set("next", next);
      openBrowserLink.href = browserUrl.href;
      openBrowserLink.hidden = false;
      if (sessionCheck.response.status === 401) {
        showNotice("这个窗口没有保存登录状态，请在完整浏览器中打开登录页再试。");
      } else {
        openBrowserLink.hidden = true;
        showNotice("登录服务暂时不可用，请稍后再试。");
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
    showNotice("连不上服务器，请检查网络后重试。");
  } finally {
    setBusy(false);
  }
});

configureMode();
showOAuthResult();
if (config.callbackType) prepareCallbackMode();
