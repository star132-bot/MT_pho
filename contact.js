const contactForm = document.querySelector("[data-contact-form]");
const contactToast = document.querySelector("[data-contact-toast]");
const contactEmailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const contactRecipientEmail = "3986254985@qq.com";

function setContactToast(message, type = "success") {
  if (!contactToast) {
    return;
  }

  contactToast.textContent = message;
  contactToast.dataset.type = type;
  contactToast.classList.add("is-visible");
  window.setTimeout(() => {
    contactToast.classList.remove("is-visible");
  }, 3800);
}

function setContactError(fieldName, message) {
  const error = document.querySelector(`[data-error-for="${fieldName}"]`);
  if (error) {
    error.textContent = message;
  }
}

function clearContactErrors() {
  document.querySelectorAll("[data-error-for]").forEach((error) => {
    error.textContent = "";
  });
}

function contactPayloadFromForm(form) {
  const formData = new FormData(form);
  return {
    sender_name: String(formData.get("sender_name") || "").trim(),
    sender_email: String(formData.get("sender_email") || "").trim(),
    subject: String(formData.get("subject") || "").trim(),
    message: String(formData.get("message") || "").trim(),
  };
}

function validateContactPayload(payload) {
  clearContactErrors();
  let isValid = true;

  if (!payload.sender_email) {
    setContactError("sender_email", "Email is required.");
    isValid = false;
  } else if (!contactEmailPattern.test(payload.sender_email)) {
    setContactError("sender_email", "Enter a valid email address.");
    isValid = false;
  }

  if (!payload.message) {
    setContactError("message", "Note is required.");
    isValid = false;
  }

  return isValid;
}

function buildMailtoHref(payload) {
  const subject = payload.subject || "MT Presence inquiry";
  const bodyLines = [
    payload.sender_name ? `Name: ${payload.sender_name}` : "",
    `Email: ${payload.sender_email}`,
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
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Opening email...";

  try {
    clearContactErrors();
    window.location.href = buildMailtoHref(payload);
    setContactToast(`Opening email draft for ${contactRecipientEmail}.`);
  } catch {
    setContactToast("Unable to open your email app. Please email the artist directly.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Open Email Draft";
  }
}

contactForm?.addEventListener("submit", submitContactForm);
