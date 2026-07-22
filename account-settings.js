const pageLoading = document.querySelector("[data-account-loading]");
const pageContent = document.querySelector("[data-account-content]");
const pageNotice = document.querySelector("[data-account-notice]");
const liveRegion = document.querySelector("[data-account-live]");
const accountSummary = document.querySelector("[data-account-summary]");
const profileForm = document.querySelector("[data-profile-form]");
const preferencesForm = document.querySelector("[data-preferences-form]");
const profileSubmit = document.querySelector("[data-profile-submit]");
const preferencesSubmit = document.querySelector("[data-preferences-submit]");
const profileSaveState = document.querySelector("[data-profile-save-state]");
const preferencesSaveState = document.querySelector("[data-preferences-save-state]");
const sessionLoading = document.querySelector("[data-session-loading]");
const sessionList = document.querySelector("[data-session-list]");
const sessionNote = document.querySelector("[data-session-note]");
const sessionActions = document.querySelector("[data-session-actions]");
const signOutCurrent = document.querySelector("[data-sign-out-current]");
const dialog = document.querySelector("[data-account-dialog]");
const dialogForm = document.querySelector("[data-dialog-form]");
const dialogTitle = document.querySelector("[data-dialog-title]");
const dialogDescription = document.querySelector("[data-dialog-description]");
const dialogNotice = document.querySelector("[data-dialog-notice]");
const dialogCancel = document.querySelector("[data-dialog-cancel]");
const dialogConfirm = document.querySelector("[data-dialog-confirm]");
const sectionIndex = document.querySelector(".account-settings-index");
const sectionLinks = Array.from(document.querySelectorAll(".account-settings-index a"));
const accountSections = sectionLinks
  .map((link) => document.querySelector(link.getAttribute("href")))
  .filter(Boolean);

const PROFILE_NAMES = [
  "display_name",
  "professional_headline",
  "company",
  "country_code",
  "city",
  "bio",
  "website_url",
  "instagram_url",
  "linkedin_url",
  "availability_status",
];
const PREFERENCE_NAMES = ["preferred_locale", "timezone", "copyright_name", "default_license_preference"];

let csrfTokenPromise = null;
let accountData = null;
let sessionAction = "";
let dialogTrigger = null;
let dialogBusy = false;
let suppressBeforeUnload = false;
const formSnapshots = new WeakMap();

function navigateWithoutDirtyPrompt(path, hideAccount = false) {
  suppressBeforeUnload = true;
  if (hideAccount) {
    accountSummary.hidden = true;
    pageContent.hidden = true;
    pageLoading.hidden = false;
  }
  window.location.assign(path);
}

function redirectForAuth(error) {
  if (error.status === 401) {
    navigateWithoutDirtyPrompt("/auth/sign-in?next=%2Fsettings%2Faccount", true);
    return true;
  }
  if (error.status === 403 && error.code === "MFA_REQUIRED") {
    navigateWithoutDirtyPrompt("/auth/mfa?next=%2Fsettings%2Faccount", true);
    return true;
  }
  if (error.status === 403 && error.code === "RECOVERY_SESSION_RESTRICTED") {
    navigateWithoutDirtyPrompt("/auth/reset-password", true);
    return true;
  }
  return false;
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
    }).catch((error) => {
      csrfTokenPromise = null;
      throw error;
    });
  }
  return csrfTokenPromise;
}

async function accountRequest(path, options = {}, retryCsrf = true) {
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
    return accountRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || "Unable to complete this account request.");
    error.status = response.status;
    error.code = result.error?.code || "ACCOUNT_REQUEST_FAILED";
    error.fieldErrors = result.error?.field_errors || {};
    throw error;
  }
  return result;
}

function showNotice(message, kind = "error", retry = null) {
  pageNotice.replaceChildren(document.createTextNode(message));
  pageNotice.className = `account-page-notice is-${kind}`;
  pageNotice.hidden = false;
  if (retry) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Retry";
    button.addEventListener("click", retry, { once: true });
    pageNotice.append(" ", button);
  }
  pageNotice.focus();
}

function hideNotice() {
  pageNotice.hidden = true;
  pageNotice.replaceChildren();
}

function announce(message) {
  liveRegion.textContent = "";
  window.setTimeout(() => { liveRegion.textContent = message; }, 20);
}

function initials(value) {
  const words = String(value || "MT").trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase() || "").join("") || "MT";
}

function addSelectValue(select, value) {
  if (!value || Array.from(select.options).some((option) => option.value === value)) return;
  select.add(new Option(value, value));
}

function renderAccountChrome(result) {
  const profile = result.profile || {};
  const account = result.account || {};
  const avatarInitials = initials(profile.display_name);
  document.querySelectorAll("[data-account-initials], [data-profile-initials]")
    .forEach((element) => { element.textContent = avatarInitials; });
  document.querySelector("[data-account-display-name]").textContent = profile.display_name || "Member";
  document.querySelector("[data-profile-summary-name]").textContent = profile.display_name || "Member";
  document.querySelector("[data-account-email]").textContent = account.email || "";
  document.querySelector("[data-account-status]").textContent = `${String(account.account_status || "active").replaceAll("_", " ")} account`;

  document.querySelector("[data-security-email]").textContent = account.email || "";
  document.querySelector("[data-security-email-state]").textContent = account.email_verified ? "Verified email" : "Verification pending";
  const roles = Array.isArray(account.roles) ? account.roles : [];
  const primaryRole = roles.includes("super_admin") ? "Super Admin" : roles.includes("admin") ? "Administrator" : roles.includes("reviewer") ? "Reviewer" : "Member";
  document.querySelector("[data-security-role]").textContent = primaryRole;
  document.querySelector("[data-security-status]").textContent = `${String(account.account_status || "active").replaceAll("_", " ")} account`;
  const isAal2 = account.aal === "aal2";
  document.querySelector("[data-security-aal]").textContent = isAal2 ? "MFA-verified session" : "Standard session";
  document.querySelector("[data-security-aal-detail]").textContent = isAal2 ? "Authenticator verification is active" : "Password-protected access";

  const showAdmin = roles.some((role) => ["reviewer", "admin", "super_admin"].includes(role));
  document.querySelectorAll("[data-admin-only]").forEach((link) => { link.hidden = !showAdmin; });
}

function populateAccount(result) {
  accountData = result;
  const profile = result.profile || {};

  profileForm.elements.display_name.value = profile.display_name || "";
  profileForm.elements.professional_headline.value = profile.professional_headline || "";
  profileForm.elements.company.value = profile.company || "";
  profileForm.elements.country_code.value = profile.country_code || "";
  profileForm.elements.city.value = profile.city || "";
  profileForm.elements.bio.value = profile.bio || "";
  profileForm.elements.website_url.value = profile.website_url || "";
  profileForm.elements.instagram_url.value = profile.instagram_url || "";
  profileForm.elements.linkedin_url.value = profile.linkedin_url || "";
  profileForm.elements.availability_status.value = profile.availability_status || "unavailable";

  preferencesForm.elements.preferred_locale.value = profile.preferred_locale || "en";
  addSelectValue(preferencesForm.elements.timezone, profile.timezone);
  preferencesForm.elements.timezone.value = profile.timezone || "UTC";
  preferencesForm.elements.copyright_name.value = profile.copyright_name || "";
  preferencesForm.elements.default_license_preference.value = profile.default_license_preference || "";

  renderAccountChrome(result);

  accountSummary.hidden = false;
  pageContent.hidden = false;
  pageLoading.hidden = true;
  rememberForm(profileForm, PROFILE_NAMES);
  rememberForm(preferencesForm, PREFERENCE_NAMES);
  scheduleSectionSync();
}

function normalizeFieldValue(name, value) {
  let normalized = String(value ?? "").trim();
  if (name === "country_code") normalized = normalized.toUpperCase();
  return normalized;
}

function valuesPayload(values, names) {
  const payload = {};
  names.forEach((name) => {
    payload[name] = normalizeFieldValue(name, values?.[name]);
  });
  return payload;
}

function formPayload(form, names) {
  const values = {};
  names.forEach((name) => { values[name] = form.elements[name].value; });
  return valuesPayload(values, names);
}

function signature(form, names) {
  return JSON.stringify(formPayload(form, names));
}

function formStateElements(form) {
  return form === profileForm
    ? { names: PROFILE_NAMES, submit: profileSubmit, status: profileSaveState, label: "profile" }
    : { names: PREFERENCE_NAMES, submit: preferencesSubmit, status: preferencesSaveState, label: "preferences" };
}

function rememberForm(form, names) {
  formSnapshots.set(form, signature(form, names));
  updateFormDirtyState(form);
}

function isFormDirty(form) {
  const { names } = formStateElements(form);
  const snapshot = formSnapshots.get(form);
  return snapshot !== undefined && signature(form, names) !== snapshot;
}

function setFormStatus(status, state, message) {
  status.dataset.state = state;
  status.textContent = message;
}

function updateFormDirtyState(form) {
  const { submit, status } = formStateElements(form);
  const dirty = isFormDirty(form);
  submit.disabled = !dirty;
  setFormStatus(status, dirty ? "dirty" : "clean", dirty ? "Unsaved changes" : "No unsaved changes");
}

function clearFieldErrors(form) {
  form.querySelectorAll("[aria-invalid='true']").forEach((field) => field.removeAttribute("aria-invalid"));
  form.querySelectorAll("[data-field-error]").forEach((element) => { element.textContent = ""; });
}

function applyFieldErrors(form, fieldErrors) {
  Object.entries(fieldErrors || {}).forEach(([name, message]) => {
    const field = form.elements[name];
    const error = form.querySelector(`[data-field-error="${CSS.escape(name)}"]`);
    if (field) field.setAttribute("aria-invalid", "true");
    if (error) error.textContent = message;
  });
  const firstInvalid = form.querySelector("[aria-invalid='true']");
  if (firstInvalid) firstInvalid.focus();
}

async function saveForm(form) {
  const { names, submit, status, label } = formStateElements(form);
  if (form.getAttribute("aria-busy") === "true") return;
  clearFieldErrors(form);
  if (!form.reportValidity()) return;
  const submittedPayload = formPayload(form, names);
  submit.disabled = true;
  submit.textContent = "Saving…";
  form.setAttribute("aria-busy", "true");
  setFormStatus(status, "saving", "Saving");
  hideNotice();
  let saved = false;
  let failed = false;
  try {
    const result = await accountRequest("/api/me/profile", {
      method: "PATCH",
      body: JSON.stringify(submittedPayload),
    });
    accountData.profile = { ...accountData.profile, ...(result.profile || {}) };
    const currentPayload = formPayload(form, names);
    const savedPayload = valuesPayload(accountData.profile, names);
    names.forEach((name) => {
      if (currentPayload[name] === submittedPayload[name]) {
        form.elements[name].value = savedPayload[name];
      }
    });
    renderAccountChrome(accountData);
    formSnapshots.set(form, JSON.stringify(savedPayload));
    saved = true;
    announce(
      isFormDirty(form)
        ? `${label === "profile" ? "Profile" : "Preferences"} saved. Newer edits remain unsaved.`
        : `${label === "profile" ? "Profile" : "Preferences"} saved.`,
    );
  } catch (error) {
    if (redirectForAuth(error)) return;
    failed = true;
    applyFieldErrors(form, error.fieldErrors);
    if (!Object.keys(error.fieldErrors || {}).length) showNotice(error.message);
  } finally {
    form.removeAttribute("aria-busy");
    submit.textContent = label === "profile" ? "Save profile" : "Save preferences";
    updateFormDirtyState(form);
    if (saved) {
      setFormStatus(
        status,
        isFormDirty(form) ? "dirty" : "saved",
        isFormDirty(form) ? "Saved submitted changes. New edits remain unsaved." : "Saved just now",
      );
    } else if (failed) {
      setFormStatus(status, "error", "Error. Changes were not saved");
    }
  }
}

function formatExpiry(value) {
  if (!value) return "Expiry managed by your authentication provider";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Expiry managed by your authentication provider";
  return `Access renews before ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)}`;
}

function renderSessions(result) {
  sessionList.replaceChildren();
  const sessions = Array.isArray(result.sessions) ? result.sessions : [];
  sessions.forEach((session) => {
    const item = document.createElement("li");
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("class", "ui-icon");
    icon.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#icon-monitor");
    icon.append(use);

    const copy = document.createElement("span");
    copy.className = "account-session-copy";
    const title = document.createElement("strong");
    title.textContent = `${session.browser || "Browser"} on ${session.operating_system || session.device || "this device"}`;
    const detail = document.createElement("span");
    detail.textContent = `${session.device || "Current device"} · Active now · ${String(session.aal || "aal1").toUpperCase()}`;
    const expiry = document.createElement("small");
    expiry.textContent = formatExpiry(session.expires_at);
    copy.append(title, detail, expiry);

    const current = document.createElement("span");
    current.className = "account-session-current";
    current.textContent = "Current session";
    item.append(icon, copy, current);
    sessionList.append(item);
  });
  if (!sessions.length) {
    const item = document.createElement("li");
    item.className = "account-session-empty";
    item.textContent = "The current session could not be described.";
    sessionList.append(item);
  }
  sessionLoading.hidden = true;
  sessionList.hidden = false;
  sessionNote.hidden = false;
  sessionActions.hidden = false;
}

async function loadSessions() {
  sessionLoading.hidden = false;
  sessionList.hidden = true;
  sessionNote.hidden = true;
  sessionActions.hidden = true;
  try {
    renderSessions(await accountRequest("/api/me/sessions"));
  } catch (error) {
    if (redirectForAuth(error)) return;
    sessionLoading.hidden = true;
    sessionList.hidden = false;
    sessionList.replaceChildren();
    const item = document.createElement("li");
    item.className = "account-session-empty";
    item.textContent = error.message;
    sessionList.append(item);
  }
}

async function loadAccount() {
  hideNotice();
  pageLoading.hidden = false;
  pageContent.hidden = true;
  accountSummary.hidden = true;
  try {
    const result = await accountRequest("/api/me/profile");
    populateAccount(result);
    await loadSessions();
  } catch (error) {
    if (redirectForAuth(error)) return;
    pageLoading.hidden = true;
    showNotice(error.message, "error", loadAccount);
  }
}

function dialogCopy(target) {
  if (target === "all") {
    return {
      title: "Sign out all devices?",
      description: "This browser and every other device will lose refresh access. You will need to sign in again before opening your Workspace.",
      confirm: "Sign out all devices",
    };
  }
  return {
    title: "Sign out other devices?",
    description: "Every other device will lose refresh access. This current browser will remain signed in.",
    confirm: "Sign out other devices",
  };
}

function openSessionDialog(target, trigger) {
  sessionAction = target;
  dialogTrigger = trigger;
  const copy = dialogCopy(target);
  dialogTitle.textContent = copy.title;
  dialogDescription.textContent = copy.description;
  dialogConfirm.textContent = copy.confirm;
  dialogNotice.hidden = true;
  dialogNotice.textContent = "";
  dialog.showModal();
  window.setTimeout(() => dialogCancel.focus(), 0);
}

async function revokeSessions() {
  if (!sessionAction || dialogBusy) return;
  dialogBusy = true;
  dialogCancel.disabled = true;
  dialogConfirm.disabled = true;
  const originalLabel = dialogConfirm.textContent;
  dialogConfirm.textContent = "Signing out…";
  dialogNotice.hidden = true;
  try {
    const result = await accountRequest(`/api/me/sessions/${sessionAction}`, {
      method: "DELETE",
      body: JSON.stringify({ confirmation: `sign-out-${sessionAction}` }),
    });
    dialog.close();
    if (result.signed_out) {
      navigateWithoutDirtyPrompt("/auth/sign-in", true);
      return;
    }
    showNotice(result.message || "Other device sessions were revoked.", "success");
    announce("Other devices signed out.");
    await loadSessions();
  } catch (error) {
    if (redirectForAuth(error)) return;
    dialogNotice.textContent = error.message;
    dialogNotice.hidden = false;
    dialogNotice.focus();
  } finally {
    dialogBusy = false;
    dialogCancel.disabled = false;
    dialogConfirm.disabled = false;
    dialogConfirm.textContent = originalLabel;
  }
}

profileForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(profileForm);
});

preferencesForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(preferencesForm);
});

[profileForm, preferencesForm].forEach((form) => {
  form.addEventListener("input", () => updateFormDirtyState(form));
  form.addEventListener("change", () => updateFormDirtyState(form));
});

profileForm.elements.country_code.addEventListener("input", (event) => {
  event.target.value = event.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2);
});

document.querySelectorAll("[data-session-action]").forEach((button) => {
  button.addEventListener("click", () => openSessionDialog(button.dataset.sessionAction, button));
});

signOutCurrent.addEventListener("click", async () => {
  const originalLabel = signOutCurrent.textContent;
  signOutCurrent.disabled = true;
  signOutCurrent.textContent = "Signing out…";
  hideNotice();
  try {
    await accountRequest("/api/auth/sign-out", { method: "POST", body: JSON.stringify({}) });
    navigateWithoutDirtyPrompt("/auth/sign-in", true);
  } catch (error) {
    if (redirectForAuth(error)) return;
    signOutCurrent.disabled = false;
    signOutCurrent.textContent = originalLabel;
    showNotice(error.message || "This device could not be signed out. Please retry.");
    announce("Sign out failed. Your session remains active.");
  }
});

dialogForm.addEventListener("submit", (event) => {
  event.preventDefault();
  revokeSessions();
});

dialogCancel.addEventListener("click", () => {
  if (!dialogBusy) dialog.close();
});

dialog.addEventListener("cancel", (event) => {
  if (dialogBusy) event.preventDefault();
});

dialog.addEventListener("close", () => {
  sessionAction = "";
  const trigger = dialogTrigger;
  dialogTrigger = null;
  if (trigger && document.contains(trigger)) trigger.focus();
});

let sectionSyncFrame = 0;

function setActiveSection(sectionId) {
  sectionLinks.forEach((link) => {
    if (link.getAttribute("href") === `#${sectionId}`) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  });
}

function syncSectionIndex() {
  sectionSyncFrame = 0;
  if (!accountSections.length || pageContent.hidden) return;
  const headerHeight = document.querySelector(".account-settings-header")?.getBoundingClientRect().height || 0;
  const indexHeight = window.matchMedia("(max-width: 760px)").matches
    ? sectionIndex.getBoundingClientRect().height
    : 0;
  const activationLine = headerHeight + indexHeight + 24;
  let activeSection = accountSections[0];
  accountSections.forEach((section) => {
    if (section.getBoundingClientRect().top <= activationLine) activeSection = section;
  });
  const atPageEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
  if (atPageEnd) activeSection = accountSections.at(-1);
  setActiveSection(activeSection.id);
}

function scheduleSectionSync() {
  if (sectionSyncFrame) return;
  sectionSyncFrame = window.requestAnimationFrame(syncSectionIndex);
}

sectionLinks.forEach((link) => {
  link.addEventListener("click", () => setActiveSection(link.getAttribute("href").slice(1)));
});

window.addEventListener("scroll", scheduleSectionSync, { passive: true });
window.addEventListener("resize", scheduleSectionSync);
window.addEventListener("hashchange", scheduleSectionSync);

window.addEventListener("beforeunload", (event) => {
  if (suppressBeforeUnload) return;
  if (!isFormDirty(profileForm) && !isFormDirty(preferencesForm)) return;
  event.preventDefault();
  event.returnValue = "";
});

loadAccount();
