const pageLoading = document.querySelector("[data-account-loading]");
const pageContent = document.querySelector("[data-account-content]");
const pageNotice = document.querySelector("[data-account-notice]");
const liveRegion = document.querySelector("[data-account-live]");
const accountSummary = document.querySelector("[data-account-summary]");
const accountAvatarVisual = document.querySelector("[data-account-avatar-visual]");
const accountAvatarImage = document.querySelector("[data-account-avatar-image]");
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
const profileAvatarVisual = document.querySelector("[data-profile-avatar-visual]");
const profileAvatarImage = document.querySelector("[data-profile-avatar-image]");
const profileAvatarInput = document.querySelector("[data-profile-avatar-input]");
const profileAvatarChoose = document.querySelector("[data-profile-avatar-choose]");
const profileAvatarRemove = document.querySelector("[data-profile-avatar-remove]");
const profileAvatarStatus = document.querySelector("[data-profile-avatar-status]");
const professionalRolePicker = document.querySelector("[data-professional-role-picker]");
const professionalRoleOptions = document.querySelector("[data-professional-role-options]");
const professionalRoleCount = document.querySelector("[data-professional-role-count]");
const professionalHeadlineValue = profileForm.elements.professional_headline;

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
const PROFESSIONAL_ROLE_LIMIT = 3;

let csrfTokenPromise = null;
let accountData = null;
let sessionAction = "";
let dialogTrigger = null;
let dialogBusy = false;
let suppressBeforeUnload = false;
let profileAvatarBusy = false;
let profileAvatarGeneration = 0;
let accountAvatarGeneration = 0;
let profileAvatarPreviewUrl = "";
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
  if (words[0]?.toUpperCase() === "MT") return "MT";
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase() || "").join("") || "MT";
}

function setProfileAvatarStatus(message = "", state = "idle") {
  profileAvatarStatus.textContent = message;
  profileAvatarStatus.dataset.state = state;
}

function setProfileAvatarBusy(busy) {
  profileAvatarBusy = busy;
  profileAvatarChoose.disabled = busy;
  profileAvatarRemove.disabled = busy;
  profileAvatarInput.disabled = busy;
  profileAvatarVisual.setAttribute("aria-busy", String(busy));
}

function releaseProfileAvatarPreview() {
  if (!profileAvatarPreviewUrl) return;
  URL.revokeObjectURL(profileAvatarPreviewUrl);
  profileAvatarPreviewUrl = "";
}

function safeProfileAvatarUrl(value) {
  const source = String(value || "").trim();
  if (!source) return "";
  try {
    const url = new URL(source, window.location.origin);
    const loopback = url.protocol === "http:"
      && new Set(["localhost", "127.0.0.1", "[::1]"]).has(url.hostname);
    return url.protocol === "https:" || loopback ? url.href : "";
  } catch (_error) {
    return "";
  }
}

async function showAccountAvatar(source) {
  const url = safeProfileAvatarUrl(source);
  const generation = ++accountAvatarGeneration;
  accountAvatarVisual.classList.remove("is-image-ready");
  accountAvatarImage.hidden = true;
  if (!url) {
    accountAvatarImage.removeAttribute("src");
    return;
  }
  accountAvatarImage.src = url;
  accountAvatarImage.hidden = false;
  try {
    if (typeof accountAvatarImage.decode === "function") await accountAvatarImage.decode();
    else if (!accountAvatarImage.complete || !accountAvatarImage.naturalWidth) {
      await new Promise((resolve, reject) => {
        accountAvatarImage.addEventListener("load", resolve, { once: true });
        accountAvatarImage.addEventListener("error", reject, { once: true });
      });
    }
    if (generation === accountAvatarGeneration && accountAvatarImage.naturalWidth) {
      accountAvatarVisual.classList.add("is-image-ready");
    }
  } catch (_error) {
    if (generation !== accountAvatarGeneration) return;
    accountAvatarVisual.classList.remove("is-image-ready");
    accountAvatarImage.hidden = true;
  }
}

async function showProfileAvatar(source, { persisted = true } = {}) {
  const url = persisted ? safeProfileAvatarUrl(source) : String(source || "");
  const generation = ++profileAvatarGeneration;
  profileAvatarVisual.classList.remove("is-image-ready");
  profileAvatarImage.hidden = true;
  if (persisted) profileAvatarRemove.hidden = !url;
  if (!url) {
    profileAvatarImage.removeAttribute("src");
    return;
  }
  profileAvatarImage.src = url;
  profileAvatarImage.hidden = false;
  try {
    if (typeof profileAvatarImage.decode === "function") await profileAvatarImage.decode();
    else if (!profileAvatarImage.complete || !profileAvatarImage.naturalWidth) {
      await new Promise((resolve, reject) => {
        profileAvatarImage.addEventListener("load", resolve, { once: true });
        profileAvatarImage.addEventListener("error", reject, { once: true });
      });
    }
    if (generation === profileAvatarGeneration && profileAvatarImage.naturalWidth) {
      profileAvatarVisual.classList.add("is-image-ready");
    }
  } catch (_error) {
    if (generation !== profileAvatarGeneration) return;
    profileAvatarVisual.classList.remove("is-image-ready");
    profileAvatarImage.hidden = true;
  }
}

async function decodedAvatarSource(file) {
  if (typeof createImageBitmap === "function") {
    let bitmap;
    try {
      bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch (_error) {
      bitmap = await createImageBitmap(file);
    }
    return {
      image: bitmap,
      width: bitmap.width,
      height: bitmap.height,
      close: () => bitmap.close?.(),
    };
  }
  const objectUrl = URL.createObjectURL(file);
  const image = new Image();
  image.decoding = "async";
  image.src = objectUrl;
  try {
    if (typeof image.decode === "function") await image.decode();
    else {
      await new Promise((resolve, reject) => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", reject, { once: true });
      });
    }
  } catch (error) {
    URL.revokeObjectURL(objectUrl);
    throw error;
  }
  return {
    image,
    width: image.naturalWidth,
    height: image.naturalHeight,
    close: () => URL.revokeObjectURL(objectUrl),
  };
}

function canvasJpeg(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error("This image could not be prepared.")),
      "image/jpeg",
      quality,
    );
  });
}

async function prepareProfileAvatar(file) {
  const acceptedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  if (!(file instanceof File) || !acceptedTypes.has(file.type.toLowerCase())) {
    throw new Error("Choose a JPG, PNG, or WebP image.");
  }
  if (file.size < 1 || file.size > 20 * 1024 * 1024) {
    throw new Error("Choose an image no larger than 20 MB.");
  }
  const decoded = await decodedAvatarSource(file);
  try {
    const { width, height } = decoded;
    if (
      !Number.isInteger(width)
      || !Number.isInteger(height)
      || width < 64
      || height < 64
      || width > 12000
      || height > 12000
      || width * height > 40_000_000
    ) {
      throw new Error("Choose an image between 64 px and 12,000 px with at most 40 megapixels.");
    }
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 512;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Image processing is unavailable in this browser.");
    const cropSize = Math.min(width, height);
    const sourceX = (width - cropSize) / 2;
    const sourceY = (height - cropSize) / 2;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, 512, 512);
    context.drawImage(decoded.image, sourceX, sourceY, cropSize, cropSize, 0, 0, 512, 512);
    let blob = await canvasJpeg(canvas, 0.88);
    if (blob.size > 1024 * 1024) blob = await canvasJpeg(canvas, 0.76);
    if (blob.size < 1 || blob.size > 1024 * 1024) {
      throw new Error("The prepared profile photo is larger than 1 MB. Choose a simpler image.");
    }
    return blob;
  } finally {
    decoded.close();
  }
}

function emitProfileCommitted(profile) {
  window.dispatchEvent(new CustomEvent("mt:profile-committed", {
    detail: { profile },
  }));
}

async function uploadPreparedAvatar(destination, blob) {
  const signedUrl = safeProfileAvatarUrl(destination?.signed_url);
  if (
    !signedUrl
    || destination?.mime_type !== "image/jpeg"
    || destination?.byte_size !== blob.size
    || destination?.width !== 512
    || destination?.height !== 512
  ) {
    throw new Error("The secure profile photo destination was invalid.");
  }
  const formData = new FormData();
  formData.append("cacheControl", "3600");
  formData.append("", blob, "avatar.jpg");
  const response = await fetch(signedUrl, {
    method: "PUT",
    credentials: "omit",
    headers: { "x-upsert": "false" },
    body: formData,
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.message || result.error || "The profile photo could not be uploaded.");
  }
}

async function uploadProfileAvatar(file) {
  if (profileAvatarBusy) return;
  const previousProfile = { ...(accountData?.profile || {}) };
  let uploadId = "";
  setProfileAvatarBusy(true);
  setProfileAvatarStatus("Preparing photo…", "working");
  hideNotice();
  try {
    const blob = await prepareProfileAvatar(file);
    releaseProfileAvatarPreview();
    profileAvatarPreviewUrl = URL.createObjectURL(blob);
    await showProfileAvatar(profileAvatarPreviewUrl, { persisted: false });
    setProfileAvatarStatus("Uploading photo…", "working");
    const intentResult = await accountRequest("/api/me/profile/avatar/intents", {
      method: "POST",
      body: JSON.stringify({ mime_type: "image/jpeg", byte_size: blob.size, width: 512, height: 512 }),
    });
    const destination = intentResult.upload || {};
    uploadId = String(destination.id || "");
    if (!uploadId) throw new Error("The secure profile photo destination was unavailable.");
    await uploadPreparedAvatar(destination, blob);
    setProfileAvatarStatus("Saving photo…", "working");
    const result = await accountRequest(
      `/api/me/profile/avatar/intents/${encodeURIComponent(uploadId)}/complete`,
      { method: "POST", body: JSON.stringify({ confirmation: "complete-profile-avatar" }) },
    );
    accountData.profile = { ...accountData.profile, ...(result.profile || {}) };
    releaseProfileAvatarPreview();
    renderAccountChrome(accountData);
    emitProfileCommitted(accountData.profile);
    setProfileAvatarStatus("Profile photo saved.", "saved");
    announce("Profile photo saved.");
  } catch (error) {
    if (uploadId) {
      accountRequest(
        `/api/me/profile/avatar/intents/${encodeURIComponent(uploadId)}`,
        { method: "DELETE", body: JSON.stringify({ confirmation: "cancel-profile-avatar" }) },
      ).catch(() => {});
    }
    releaseProfileAvatarPreview();
    if (accountData) accountData.profile = previousProfile;
    renderAccountChrome(accountData || { profile: previousProfile, account: {} });
    if (redirectForAuth(error)) return;
    setProfileAvatarStatus(error.message || "Profile photo upload failed.", "error");
    announce("Profile photo upload failed.");
  } finally {
    profileAvatarInput.value = "";
    setProfileAvatarBusy(false);
  }
}

async function removeProfileAvatar() {
  if (profileAvatarBusy || profileAvatarRemove.hidden) return;
  if (!window.confirm("Remove your current profile photo? Your initials will be shown instead.")) return;
  setProfileAvatarBusy(true);
  setProfileAvatarStatus("Removing photo…", "working");
  hideNotice();
  try {
    const result = await accountRequest("/api/me/profile/avatar", {
      method: "DELETE",
      body: JSON.stringify({ confirmation: "remove-profile-avatar" }),
    });
    accountData.profile = { ...accountData.profile, ...(result.profile || {}), avatar_url: null };
    renderAccountChrome(accountData);
    emitProfileCommitted(accountData.profile);
    setProfileAvatarStatus("Profile photo removed.", "saved");
    announce("Profile photo removed. Your initials are now shown.");
  } catch (error) {
    if (redirectForAuth(error)) return;
    setProfileAvatarStatus(error.message || "Profile photo removal failed.", "error");
    announce("Profile photo removal failed.");
  } finally {
    setProfileAvatarBusy(false);
  }
}

function addSelectValue(select, value) {
  if (!value || Array.from(select.options).some((option) => option.value === value)) return;
  select.add(new Option(value, value));
}

function professionalRoleInputs() {
  return Array.from(professionalRoleOptions.querySelectorAll("[data-professional-role]"));
}

function removeLegacyProfessionalRole() {
  professionalRoleOptions.querySelectorAll("label[data-professional-role-legacy]")
    .forEach((option) => option.remove());
}

function addLegacyProfessionalRole(value) {
  const label = document.createElement("label");
  label.className = "account-role-option is-legacy";
  label.dataset.professionalRoleLegacy = "";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.value = value;
  input.checked = true;
  input.dataset.professionalRole = "";
  input.dataset.professionalRoleLegacy = "";
  const copy = document.createElement("span");
  copy.textContent = `Current: ${value}`;
  label.append(input, copy);
  professionalRoleOptions.prepend(label);
}

function syncProfessionalRolePicker() {
  const inputs = professionalRoleInputs();
  const selected = inputs.filter((input) => input.checked);
  const limitReached = selected.length >= PROFESSIONAL_ROLE_LIMIT;
  professionalHeadlineValue.value = selected.map((input) => input.value).join(", ");
  inputs.forEach((input) => {
    input.disabled = !input.checked && limitReached;
  });
  professionalRolePicker.dataset.selectionCount = String(selected.length);
  professionalRolePicker.toggleAttribute("data-limit-reached", limitReached);
  professionalRoleCount.textContent = limitReached
    ? `${selected.length} of ${PROFESSIONAL_ROLE_LIMIT} selected — remove one to choose another`
    : `${selected.length} of ${PROFESSIONAL_ROLE_LIMIT} selected`;
}

function setProfessionalRoles(value) {
  const storedValue = String(value || "").trim();
  removeLegacyProfessionalRole();
  const knownInputs = professionalRoleInputs();
  knownInputs.forEach((input) => { input.checked = false; });
  if (!storedValue) {
    syncProfessionalRolePicker();
    return;
  }

  const aliases = new Map();
  knownInputs.forEach((input) => aliases.set(input.value.toLowerCase(), input));
  aliases.set("artist", aliases.get("visual artist"));
  const tokens = storedValue.split(/\s*[,，;；]\s*/).filter(Boolean);
  const matched = tokens.map((token) => aliases.get(token.toLowerCase()));
  const uniqueMatches = Array.from(new Set(matched.filter(Boolean)));
  if (tokens.length <= PROFESSIONAL_ROLE_LIMIT && matched.every(Boolean)) {
    uniqueMatches.forEach((input) => { input.checked = true; });
  } else {
    addLegacyProfessionalRole(storedValue);
  }
  syncProfessionalRolePicker();
}

function renderAccountChrome(result) {
  const profile = result.profile || {};
  const account = result.account || {};
  const avatarInitials = initials(profile.display_name);
  document.querySelectorAll("[data-account-initials], [data-profile-initials]")
    .forEach((element) => { element.textContent = avatarInitials; });
  document.querySelector("[data-account-display-name]").textContent = profile.display_name || "Member";
  document.querySelector("[data-profile-summary-name]").textContent = profile.display_name || "Member";
  showAccountAvatar(profile.avatar_url);
  showProfileAvatar(profile.avatar_url);
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

}

function populateAccount(result) {
  accountData = result;
  const profile = result.profile || {};

  profileForm.elements.display_name.value = profile.display_name || "";
  setProfessionalRoles(profile.professional_headline || "");
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
    if (name === "professional_headline" && form === profileForm) {
      professionalRolePicker.setAttribute("aria-invalid", "true");
    } else if (field) {
      field.setAttribute("aria-invalid", "true");
    }
    if (error) error.textContent = message;
  });
  const firstInvalid = form.querySelector("[aria-invalid='true']");
  if (firstInvalid) {
    const focusTarget = firstInvalid.matches("[data-professional-role-picker]")
      ? firstInvalid.querySelector("[data-professional-role]:not(:disabled)") || firstInvalid.querySelector("[data-professional-role]")
      : firstInvalid;
    focusTarget?.focus();
  }
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
        if (form === profileForm && name === "professional_headline") {
          setProfessionalRoles(savedPayload[name]);
        } else {
          form.elements[name].value = savedPayload[name];
        }
      }
    });
    renderAccountChrome(accountData);
    emitProfileCommitted(accountData.profile);
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

professionalRoleOptions.addEventListener("change", (event) => {
  if (!event.target.matches("[data-professional-role]")) return;
  const selected = professionalRoleInputs().filter((input) => input.checked);
  if (selected.length > PROFESSIONAL_ROLE_LIMIT) {
    event.target.checked = false;
    announce(`Choose no more than ${PROFESSIONAL_ROLE_LIMIT} professional roles.`);
  }
  professionalRolePicker.removeAttribute("aria-invalid");
  const error = profileForm.querySelector('[data-field-error="professional_headline"]');
  if (error) error.textContent = "";
  syncProfessionalRolePicker();
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

profileAvatarChoose.addEventListener("click", () => profileAvatarInput.click());
profileAvatarInput.addEventListener("change", () => {
  const [file] = profileAvatarInput.files || [];
  if (file) uploadProfileAvatar(file);
});
profileAvatarRemove.addEventListener("click", removeProfileAvatar);

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
  if (!profileAvatarBusy && !isFormDirty(profileForm) && !isFormDirty(preferencesForm)) return;
  event.preventDefault();
  event.returnValue = "";
});
window.addEventListener("pagehide", releaseProfileAvatarPreview);

loadAccount();
