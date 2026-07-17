const contactForm = document.querySelector("[data-contact-form]");
const contactToast = document.querySelector("[data-contact-toast]");
const publicArchive = window.MTPresencePublicArchive;
const contactEmailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const contactRecipientEmail = "3986254985@qq.com";
const contactParams = new URLSearchParams(window.location.search);
const contactSource = contactParams.get("source") || "general";
const requestedSeriesSlug = contactParams.get("series") || "";
let selectedContextWorks = [];

function contactFieldElement(fieldName) {
  return contactForm?.elements?.[fieldName] || null;
}

function syncContactFieldState(field) {
  const fieldWrapper = field?.closest?.(".form-field");
  if (fieldWrapper) {
    fieldWrapper.classList.toggle("is-filled", Boolean(String(field.value || "").trim()));
  }
}

function setContactToast(message, type = "success") {
  if (!contactToast) {
    return;
  }
  contactToast.textContent = message;
  contactToast.dataset.type = type;
  contactToast.classList.add("is-visible");
  window.setTimeout(() => contactToast.classList.remove("is-visible"), 3800);
}

function setContactError(fieldName, message) {
  const error = document.querySelector(`[data-error-for="${fieldName}"]`);
  const field = contactFieldElement(fieldName);
  const wrapper = field?.closest?.(".form-field");
  if (error) {
    error.textContent = message;
  }
  field?.setAttribute("aria-invalid", message ? "true" : "false");
  wrapper?.classList.toggle("has-error", Boolean(message));
}

function clearContactErrors() {
  document.querySelectorAll("[data-error-for]").forEach((error) => {
    error.textContent = "";
  });
  contactForm?.querySelectorAll("[aria-invalid]").forEach((field) => {
    field.setAttribute("aria-invalid", "false");
    field.closest(".form-field")?.classList.remove("has-error");
  });
}

function contactPayloadFromForm(form) {
  const formData = new FormData(form);
  return {
    sender_name: String(formData.get("sender_name") || "").trim(),
    sender_email: String(formData.get("sender_email") || "").trim(),
    inquiry_type: String(formData.get("inquiry_type") || "").trim(),
    organization: String(formData.get("organization") || "").trim(),
    project_use: String(formData.get("project_use") || "").trim(),
    timeline: String(formData.get("timeline") || "").trim(),
    budget_range: String(formData.get("budget_range") || "").trim(),
    message: String(formData.get("message") || "").trim(),
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
  if (!payload.sender_email) {
    setContactError("sender_email", "Email is required.");
    isValid = false;
  } else if (!contactEmailPattern.test(payload.sender_email)) {
    setContactError("sender_email", "Enter a valid email address.");
    isValid = false;
  }
  return isValid;
}

function titleCase(value) {
  return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : "General";
}

function contextLabel() {
  if (contactSource === "series") {
    const series = (window.MTPresenceSeriesData || []).find((item) => item.slug === requestedSeriesSlug);
    return series ? `Series / ${series.title}` : "Series inquiry";
  }
  if (contactSource === "lightbox") {
    return "Your Lightbox";
  }
  if (contactSource === "work") {
    return "Selected Work";
  }
  return "";
}

function renderContactContext() {
  const contextSection = document.querySelector("[data-contact-context]");
  const contextList = document.querySelector("[data-contact-context-list]");
  const contextSource = document.querySelector("[data-contact-context-source]");
  const hasContext = selectedContextWorks.length > 0 || contactSource === "series";
  contextSection.hidden = !hasContext;
  if (!hasContext) {
    return;
  }
  contextSource.textContent = contextLabel();
  contextList.innerHTML = selectedContextWorks
    .map(
      (work) => `
        <article class="contact-context-item" data-context-work-id="${publicArchive.escapeHtml(work.id)}">
          <img src="${publicArchive.escapeHtml(work.src)}" alt="" />
          <div><strong>${publicArchive.escapeHtml(work.title)}</strong><span>${publicArchive.escapeHtml(work.series || `${work.type} / ${work.ratio}`)}</span></div>
          <button type="button" data-remove-context-work aria-label="Remove ${publicArchive.escapeHtml(work.title)} from this inquiry">Remove</button>
        </article>`,
    )
    .join("");
}

async function hydrateContactContext() {
  const requestedWorkId = contactParams.get("work");
  let ids = [];
  if (contactSource === "lightbox") {
    ids = publicArchive.readLightboxIds();
  } else if (contactSource === "work" && requestedWorkId) {
    ids = [requestedWorkId];
  } else if (contactSource === "series" && requestedSeriesSlug) {
    ids = (window.MTPresenceSeriesData || []).find((item) => item.slug === requestedSeriesSlug)?.workIds || [];
  }
  if (ids.length) {
    try {
      const result = await publicArchive.loadPublishedWorks();
      const byId = new Map(result.works.map((work) => [work.id, work]));
      selectedContextWorks = ids.map((id) => byId.get(id)).filter(Boolean);
    } catch {
      selectedContextWorks = [];
    }
  }
  renderContactContext();
}

function buildMailtoHref(payload) {
  const inquiryLabel = titleCase(payload.inquiry_type);
  const subjectContext = selectedContextWorks.length ? ` / ${selectedContextWorks.length} selected work${selectedContextWorks.length === 1 ? "" : "s"}` : "";
  const subject = `MT Presence ${inquiryLabel} inquiry${subjectContext}`;
  const selectedLines = selectedContextWorks.map((work) => `- ${work.title} (${work.id})${work.series ? ` / ${work.series}` : ""}`);
  const bodyLines = [
    `Name: ${payload.sender_name}`,
    `Email: ${payload.sender_email}`,
    payload.organization ? `Organization: ${payload.organization}` : "",
    `Inquiry type: ${inquiryLabel}`,
    `Project / intended use: ${payload.project_use}`,
    payload.timeline ? `Timeline: ${payload.timeline}` : "",
    payload.budget_range ? `Budget range: ${payload.budget_range}` : "",
    requestedSeriesSlug ? `Series: ${contextLabel().replace("Series / ", "")}` : "",
    selectedLines.length ? "" : "",
    selectedLines.length ? "Selected works:" : "",
    ...selectedLines,
    "",
    payload.message,
  ].filter((line, index, lines) => line || lines[index - 1]);
  return `mailto:${contactRecipientEmail}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(bodyLines.join("\n"))}`;
}

async function submitContactForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector("[data-contact-submit]");
  const payload = contactPayloadFromForm(form);
  if (!validateContactPayload(payload)) {
    form.querySelector('[aria-invalid="true"]')?.focus();
    return;
  }
  submitButton.disabled = true;
  submitButton.classList.add("is-loading");
  submitButton.setAttribute("aria-busy", "true");
  submitButton.textContent = "Opening email...";
  try {
    window.location.href = buildMailtoHref(payload);
    setContactToast(`Opening email draft for ${contactRecipientEmail}.`);
  } catch {
    setContactToast("Unable to open your email app. Please email the artist directly.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.classList.remove("is-loading");
    submitButton.setAttribute("aria-busy", "false");
    submitButton.textContent = "Open Email Draft";
  }
}

function updateConditionalFields() {
  const inquiryType = contactFieldElement("inquiry_type")?.value || "";
  document.querySelector("[data-budget-field]").hidden = !["commission", "licensing"].includes(inquiryType);
}

contactForm?.querySelectorAll("input, textarea, select").forEach((field) => {
  syncContactFieldState(field);
  field.setAttribute("aria-invalid", "false");
  field.addEventListener("focus", () => field.closest(".form-field")?.classList.add("is-focused"));
  field.addEventListener("blur", () => {
    field.closest(".form-field")?.classList.remove("is-focused");
    syncContactFieldState(field);
  });
  field.addEventListener("input", () => {
    syncContactFieldState(field);
    if (field.getAttribute("aria-invalid") === "true") {
      setContactError(field.name, "");
    }
  });
});

contactFieldElement("inquiry_type")?.addEventListener("change", updateConditionalFields);
document.querySelector("[data-contact-context-list]")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-context-work]");
  if (!button) {
    return;
  }
  const id = button.closest("[data-context-work-id]")?.dataset.contextWorkId;
  selectedContextWorks = selectedContextWorks.filter((work) => work.id !== id);
  renderContactContext();
});

const requestedType = contactParams.get("type");
if (requestedType && contactFieldElement("inquiry_type")) {
  const supportedType = ["exhibition", "editorial", "licensing", "print", "commission", "other"].includes(requestedType)
    ? requestedType
    : "other";
  contactFieldElement("inquiry_type").value = supportedType;
}
updateConditionalFields();
contactForm?.addEventListener("submit", submitContactForm);
hydrateContactContext();
