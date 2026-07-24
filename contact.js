const contactForm = document.querySelector("[data-contact-form]");
const contactToast = document.querySelector("[data-contact-toast]");
const contactSuccess = document.querySelector("[data-contact-success]");
const publicArchive = window.MTPresencePublicArchive;
const contactEmailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const contactParams = new URLSearchParams(window.location.search);
const supportedContactSources = new Set(["general", "work", "series", "lightbox"]);
const rawContactSource = String(contactParams.get("source") || "general").trim();
const contactSource = supportedContactSources.has(rawContactSource) ? rawContactSource : "general";
const requestedSeriesSlug = String(contactParams.get("series") || "").trim();
const requestedContextWorkIds = [...new Set(contactParams.getAll("work").map((id) => id.trim()).filter(Boolean))];
let selectedContextWorks = [];
let contactContextState = "ready";
let contactSubmitting = false;
let contactSubmitted = false;
let contactIdempotencyKey = "";
let contactCsrfPromise = null;
let contactToastTimer = null;

function contactText(value, maxLength = 5000) {
  if (value === null || value === undefined) return "";
  return String(value).trim().slice(0, maxLength);
}

function contactUuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function safeContactImageUrl(value) {
  const source = contactText(value, 4000);
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

function updateContactSubmit() {
  const submitButton = contactForm?.querySelector("[data-contact-submit]");
  if (!submitButton) return;
  const contextBlocked = contactContextState === "loading" || contactContextState === "error";
  submitButton.disabled = contextBlocked || contactSubmitting || contactSubmitted;
  submitButton.dataset.contextState = contactContextState;
  submitButton.setAttribute("aria-busy", String(contactSubmitting || contactContextState === "loading"));
  submitButton.classList.toggle("is-loading", contactSubmitting);
  submitButton.textContent = contactSubmitting
    ? "Recording inquiry..."
    : contactContextState === "loading"
      ? "Loading selection..."
      : contactContextState === "error"
        ? "Selection unavailable"
        : "Submit Inquiry";
}

function setContactContextState(state) {
  contactContextState = state;
  updateContactSubmit();
}

function replaceLightboxContextUrl(ids) {
  if (contactSource !== "lightbox") return;
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.delete("work");
  ids.forEach((id) => nextUrl.searchParams.append("work", id));
  if (!ids.length) nextUrl.searchParams.delete("source");
  window.history.replaceState(window.history.state, "", `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
}

function contactFieldElement(fieldName) {
  return contactForm?.elements?.[fieldName] || null;
}

function syncContactFieldState(field) {
  const fieldWrapper = field?.closest?.(".form-field");
  if (fieldWrapper) fieldWrapper.classList.toggle("is-filled", Boolean(contactText(field.value)));
}

function setContactToast(message, type = "success") {
  if (!contactToast) return;
  window.clearTimeout(contactToastTimer);
  contactToast.textContent = message;
  contactToast.dataset.type = type;
  contactToast.classList.add("is-visible");
  contactToastTimer = window.setTimeout(() => contactToast.classList.remove("is-visible"), 4200);
}

function setContactError(fieldName, message) {
  const error = document.querySelector(`[data-error-for="${fieldName}"]`);
  const field = contactFieldElement(fieldName);
  const wrapper = field?.closest?.(".form-field");
  if (error) error.textContent = message;
  field?.setAttribute("aria-invalid", message ? "true" : "false");
  wrapper?.classList.toggle("has-error", Boolean(message));
}

function clearContactErrors() {
  document.querySelectorAll("[data-error-for]").forEach((error) => { error.textContent = ""; });
  contactForm?.querySelectorAll("[aria-invalid]").forEach((field) => {
    field.setAttribute("aria-invalid", "false");
    field.closest(".form-field")?.classList.remove("has-error");
  });
}

function contactPayloadFromForm(form) {
  const formData = new FormData(form);
  return {
    sender_name: contactText(formData.get("sender_name"), 120),
    sender_email: contactText(formData.get("sender_email"), 180).toLowerCase(),
    inquiry_type: contactText(formData.get("inquiry_type"), 40),
    organization: contactText(formData.get("organization"), 180),
    project_use: contactText(formData.get("project_use"), 280),
    timeline: contactText(formData.get("timeline"), 120),
    budget_range: contactText(formData.get("budget_range"), 120),
    message: contactText(formData.get("message"), 5000),
    work_ids: selectedContextWorks.map((work) => contactText(work.id, 120)).filter(Boolean),
    idempotency_key: contactIdempotencyKey || contactUuid(),
    website: contactText(formData.get("website"), 500),
  };
}

function validateContactPayload(payload) {
  clearContactErrors();
  let isValid = true;
  const required = [
    ["sender_name", "Name is required."],
    ["inquiry_type", "Select an inquiry type."],
    ["project_use", "Project or intended use is required."],
    ["message", "Message is required."],
  ];
  required.forEach(([field, message]) => {
    if (!payload[field]) {
      setContactError(field, message);
      isValid = false;
    }
  });
  if (payload.project_use && payload.project_use.length < 5) {
    setContactError("project_use", "Enter at least 5 characters.");
    isValid = false;
  }
  if (!payload.sender_email) {
    setContactError("sender_email", "Email is required.");
    isValid = false;
  } else if (!contactEmailPattern.test(payload.sender_email)) {
    setContactError("sender_email", "Enter a valid email address.");
    isValid = false;
  }
  if (payload.work_ids.length > 10) {
    setContactToast("Limit the inquiry selection to 10 works.", "error");
    document.querySelector("[data-contact-context]")?.scrollIntoView({ behavior: "smooth", block: "center" });
    isValid = false;
  }
  return isValid;
}

function contextLabel() {
  if (contactSource === "series") {
    const series = (window.MTPresenceSeriesData || []).find((item) => item.slug === requestedSeriesSlug);
    return series ? `Series / ${series.title}` : "Series inquiry";
  }
  if (contactSource === "lightbox") return "Inquiry Selection";
  if (contactSource === "work") return "Selected Work";
  return "";
}

function createContactContextItem(work) {
  const item = document.createElement("article");
  item.className = "contact-context-item";
  item.dataset.contextWorkId = contactText(work.id, 120);
  const image = document.createElement("img");
  image.alt = "";
  image.loading = "lazy";
  const source = safeContactImageUrl(work.src);
  if (source) image.src = source;
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = contactText(work.title, 240) || "Selected work";
  const details = document.createElement("span");
  details.textContent = contactText(work.series || `${work.type || "Work"} / ${work.ratio || "Format"}`, 300);
  copy.append(title, details);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.dataset.removeContextWork = "";
  remove.textContent = "Remove";
  remove.setAttribute("aria-label", `Remove ${title.textContent} from this inquiry`);
  item.append(image, copy, remove);
  return item;
}

function renderContactContext() {
  const contextSection = document.querySelector("[data-contact-context]");
  const contextList = document.querySelector("[data-contact-context-list]");
  const contextSource = document.querySelector("[data-contact-context-source]");
  const hasContext = selectedContextWorks.length > 0 || contactSource === "series";
  contextSection.hidden = !hasContext;
  contextSource.textContent = hasContext ? contextLabel() : "";
  contextList.replaceChildren(...selectedContextWorks.map(createContactContextItem));
}

async function hydrateContactContext() {
  const requestedWorkId = requestedContextWorkIds[0];
  let ids = [];
  if (contactSource === "lightbox") {
    const selectedIds = new Set(publicArchive.readInquirySelectionIds());
    ids = requestedContextWorkIds.filter((id) => selectedIds.has(id));
    replaceLightboxContextUrl(ids);
  } else if (contactSource === "work" && requestedWorkId) {
    ids = [requestedWorkId];
  } else if (contactSource === "series" && requestedSeriesSlug) {
    ids = (window.MTPresenceSeriesData || []).find((item) => item.slug === requestedSeriesSlug)?.workIds || [];
  }
  if (ids.length) {
    setContactContextState("loading");
    try {
      const result = await publicArchive.loadPublishedWorks();
      if (result.error === true) throw new Error(result.status || "Selected works are unavailable.");
      const byId = new Map(result.works.map((work) => [work.id, work]));
      selectedContextWorks = ids.map((id) => byId.get(id)).filter(Boolean);
      if (!selectedContextWorks.length) throw new Error("The selected works are no longer available.");
      if (contactSource === "lightbox") replaceLightboxContextUrl(selectedContextWorks.map((work) => work.id));
      setContactContextState("ready");
    } catch (_error) {
      selectedContextWorks = [];
      setContactContextState("error");
      setContactToast("Unable to load the selected works. Return to Lightbox and try again.", "error");
    }
  } else {
    setContactContextState("ready");
  }
  renderContactContext();
}

async function contactCsrfToken(force = false) {
  if (force) contactCsrfPromise = null;
  if (!contactCsrfPromise) {
    const request = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
      return payload.csrf_token;
    });
    contactCsrfPromise = request;
    request.catch(() => {
      if (contactCsrfPromise === request) contactCsrfPromise = null;
    });
  }
  return contactCsrfPromise;
}

async function submitInquiry(payload, retryCsrf = true) {
  const response = await fetch("/api/inquiries", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": await contactCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const responsePayload = await response.json().catch(() => ({}));
  if (response.status === 403 && responsePayload.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await contactCsrfToken(true);
    return submitInquiry(payload, false);
  }
  if (!response.ok) {
    const error = new Error(responsePayload.error?.message || "The inquiry could not be recorded.");
    error.status = response.status;
    error.code = responsePayload.error?.code || "INQUIRY_REQUEST_FAILED";
    error.fieldErrors = responsePayload.error?.field_errors
      || responsePayload.error?.details?.field_errors
      || responsePayload.field_errors
      || {};
    throw error;
  }
  return responsePayload;
}

function applyContactFieldErrors(fieldErrors) {
  const allowed = new Set([
    "sender_name", "sender_email", "inquiry_type", "organization",
    "project_use", "timeline", "budget_range", "message",
  ]);
  Object.entries(fieldErrors && typeof fieldErrors === "object" ? fieldErrors : {}).forEach(([field, message]) => {
    if (allowed.has(field)) setContactError(field, contactText(message, 300));
  });
}

function showContactSuccess(payload) {
  const inquiry = payload?.inquiry && typeof payload.inquiry === "object" ? payload.inquiry : {};
  const reference = contactText(payload.reference || payload.public_reference || inquiry.public_reference || inquiry.reference, 80) || "Pending";
  const status = contactText(payload.status || inquiry.status, 40) || "open";
  document.querySelector("[data-contact-reference]").textContent = reference;
  document.querySelector("[data-contact-success-message]").textContent =
    `Your inquiry is recorded with status ${status}. This confirms storage in MT Presence; it does not confirm email delivery.`;
  contactSubmitted = true;
  contactForm.dataset.submitted = "true";
  contactSuccess.hidden = false;
  updateContactSubmit();
  contactSuccess.focus();
  setContactToast(`Inquiry ${reference} recorded.`);
}

async function submitContactForm(event) {
  event.preventDefault();
  if (contactSubmitting || contactSubmitted) return;
  if (contactContextState !== "ready") {
    setContactToast("Wait for the selected works to load before continuing.", "error");
    return;
  }
  const payload = contactPayloadFromForm(event.currentTarget);
  if (!validateContactPayload(payload)) {
    contactForm.querySelector('[aria-invalid="true"]')?.focus();
    return;
  }
  contactIdempotencyKey = payload.idempotency_key;
  contactSubmitting = true;
  updateContactSubmit();
  try {
    const result = await submitInquiry(payload);
    contactIdempotencyKey = "";
    showContactSuccess(result);
  } catch (error) {
    applyContactFieldErrors(error.fieldErrors);
    const invalidField = contactForm.querySelector('[aria-invalid="true"]');
    if (invalidField) invalidField.focus();
    setContactToast(error.message || "The inquiry could not be recorded.", "error");
  } finally {
    contactSubmitting = false;
    updateContactSubmit();
  }
}

function updateConditionalFields() {
  const inquiryType = contactFieldElement("inquiry_type")?.value || "";
  document.querySelector("[data-budget-field]").hidden = !["commission", "licensing"].includes(inquiryType);
}

function restoreRequestedInquiryType() {
  const requestedType = contactParams.get("type");
  if (!requestedType || !contactFieldElement("inquiry_type")) return;
  contactFieldElement("inquiry_type").value = ["exhibition", "editorial", "licensing", "print", "commission", "other"].includes(requestedType)
    ? requestedType
    : "other";
}

contactForm?.querySelectorAll("input, textarea, select").forEach((field) => {
  syncContactFieldState(field);
  if (field.name !== "website") field.setAttribute("aria-invalid", "false");
  field.addEventListener("focus", () => field.closest(".form-field")?.classList.add("is-focused"));
  field.addEventListener("blur", () => {
    field.closest(".form-field")?.classList.remove("is-focused");
    syncContactFieldState(field);
  });
  field.addEventListener("input", () => {
    syncContactFieldState(field);
    if (field.getAttribute("aria-invalid") === "true") setContactError(field.name, "");
    if (!contactSubmitting) contactIdempotencyKey = "";
  });
});

contactFieldElement("inquiry_type")?.addEventListener("change", updateConditionalFields);
document.querySelector("[data-contact-context-list]")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-context-work]");
  if (!button) return;
  event.preventDefault();
  const id = button.closest("[data-context-work-id]")?.dataset.contextWorkId;
  if (!id) return;
  selectedContextWorks = selectedContextWorks.filter((work) => work.id !== id);
  contactIdempotencyKey = "";
  if (contactSource === "lightbox") {
    try {
      publicArchive.writeInquirySelectionIds(publicArchive.readInquirySelectionIds().filter((workId) => workId !== id));
    } catch (_error) {
      setContactToast("This work was removed here, but the temporary selection could not be updated.", "error");
    }
    replaceLightboxContextUrl(selectedContextWorks.map((work) => work.id));
  }
  renderContactContext();
});
document.querySelector("[data-contact-another]")?.addEventListener("click", () => {
  contactForm.reset();
  contactSubmitted = false;
  contactForm.dataset.submitted = "false";
  contactSuccess.hidden = true;
  restoreRequestedInquiryType();
  updateConditionalFields();
  contactForm.querySelectorAll("input, textarea, select").forEach(syncContactFieldState);
  clearContactErrors();
  updateContactSubmit();
  contactFieldElement("sender_name")?.focus();
});

restoreRequestedInquiryType();
updateConditionalFields();
contactForm?.addEventListener("submit", submitContactForm);
hydrateContactContext();
