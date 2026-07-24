const inboxWorkspace = document.querySelector("[data-inbox-workspace]");
const inboxInventory = document.querySelector("[data-inbox-inventory]");
const inboxListState = document.querySelector("[data-inbox-list-state]");
const inboxList = document.querySelector("[data-inbox-list]");
const inboxTotal = document.querySelector("[data-inbox-total]");
const inboxPagination = document.querySelector("[data-inbox-pagination]");
const inboxMore = document.querySelector("[data-inbox-more]");
const inboxDetailRegion = document.querySelector("[data-inbox-detail-region]");
const inboxDetailState = document.querySelector("[data-inbox-detail-state]");
const inboxDetail = document.querySelector("[data-inbox-detail]");
const inboxFilters = document.querySelector("[data-inbox-filters]");
const inboxClear = document.querySelector("[data-inbox-clear]");
const inboxRefresh = document.querySelector("[data-inbox-refresh]");
const inboxBack = document.querySelector("[data-inbox-back]");
const inboxReplyForm = document.querySelector("[data-inbox-reply-form]");
const inboxReplyMessage = inboxReplyForm?.elements?.message;
const inboxReplySubmit = document.querySelector("[data-inbox-reply-submit]");
const inboxReplyError = document.querySelector("[data-inbox-reply-error]");
const inboxReplyCount = document.querySelector("[data-inbox-reply-count]");
const inboxDetailCommands = document.querySelector("[data-inbox-detail-commands]");
const inboxManualEmail = document.querySelector("[data-inbox-manual-email]");
const inboxCopyEmail = document.querySelector("[data-inbox-copy-email]");
const inboxStatusAction = document.querySelector("[data-inbox-status-action]");
const inboxManualDeliveryNote = document.querySelector("[data-inbox-manual-delivery-note]");
const inboxStatusNotice = document.querySelector("[data-inbox-status-notice]");
const inboxStatusError = document.querySelector("[data-inbox-status-error]");
const inboxStatusReload = document.querySelector("[data-inbox-status-reload]");
const inboxToast = document.querySelector("[data-inbox-toast]");
const inboxLive = document.querySelector("[data-inbox-live]");

const INBOX_LIMIT = 30;
const INBOX_STATUSES = new Set(["all", "open", "replied", "closed"]);
let inboxItems = [];
let inboxNextCursor = null;
let inboxQuery = "";
let inboxStatus = "all";
let inboxSelectedId = "";
let inboxSelectedDetail = null;
let inboxListLoading = false;
let inboxDetailLoading = false;
let inboxReplyBusy = false;
let inboxStatusBusy = false;
let inboxListController = null;
let inboxDetailController = null;
let inboxListSerial = 0;
let inboxDetailSerial = 0;
let inboxCsrfPromise = null;
let inboxReplyIdempotencyKey = "";
let inboxStatusIdempotencyKey = "";
let inboxToastTimer = null;

function inboxText(value, maxLength = 5000) {
  if (value === null || value === undefined) return "";
  return String(value).trim().slice(0, maxLength);
}

function inboxObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function inboxInteger(value, fallback = 0) {
  const result = Number(value);
  return Number.isInteger(result) && result >= 0 ? result : fallback;
}

function safeInboxEmail(value) {
  const email = inboxText(value, 180).toLowerCase();
  if (!email || /[\r\n]/.test(email) || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "";
  return email;
}

function inboxIcon(symbol) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ui-icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${symbol}`);
  svg.append(use);
  return svg;
}

function inboxUuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function inboxDate(value, withTime = true) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en", withTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(parsed);
}

function inboxTitle(item) {
  const direct = inboxText(item.subject || item.title, 240);
  if (direct) return direct;
  const use = inboxText(item.project_use, 240);
  if (use) return use;
  const type = inboxText(item.inquiry_type, 80);
  return type ? `${type.charAt(0).toUpperCase()}${type.slice(1)} inquiry` : "Project inquiry";
}

function normalizeInboxItem(value) {
  const raw = inboxObject(value?.conversation || value?.inquiry || value?.thread || value);
  const sender = inboxObject(raw.sender);
  const recipient = inboxObject(raw.recipient);
  const id = inboxText(raw.id || raw.conversation_id, 120);
  if (!id) return null;
  const status = INBOX_STATUSES.has(inboxText(raw.status, 40)) && raw.status !== "all" ? raw.status : "open";
  const latest = inboxObject(raw.latest_message || raw.last_message);
  return {
    id,
    public_reference: inboxText(raw.reference || raw.public_reference, 80) || "Reference pending",
    sender_name: inboxText(sender.display_name || raw.sender_name || raw.contact_name, 120) || "Contact",
    sender_email: inboxText(sender.email || raw.sender_email || raw.contact_email, 180),
    sender_kind: inboxText(sender.kind || raw.sender_kind, 40) || "member",
    recipient_name: inboxText(recipient.display_name, 120),
    inquiry_type: inboxText(raw.inquiry_type, 80) || "other",
    organization: inboxText(raw.organization, 180),
    project_use: inboxText(raw.project_use, 280),
    timeline: inboxText(raw.timeline, 120),
    budget_range: inboxText(raw.budget_range, 120),
    status,
    version: Math.max(1, inboxInteger(raw.version, 1)),
    participant_role: inboxText(raw.participant_role, 40),
    unread_count: inboxInteger(raw.unread_count, 0),
    message_preview: inboxText(raw.message_preview || raw.preview || latest.body || latest.message, 300),
    message_count: inboxInteger(raw.message_count, 0),
    work_count: inboxInteger(raw.work_count, Array.isArray(raw.works) ? raw.works.length : 0),
    last_message_at: inboxText(raw.last_message_at || raw.updated_at || latest.created_at || raw.created_at, 80),
    created_at: inboxText(raw.created_at, 80),
  };
}

function normalizeInboxMessage(value) {
  const raw = inboxObject(value);
  const sender = inboxObject(raw.sender);
  const id = inboxText(raw.id || raw.message_id, 120) || inboxUuid();
  return {
    id,
    sender_user_id: inboxText(raw.sender_user_id || sender.user_id, 120),
    body: inboxText(raw.body || raw.message, 5000),
    sender_kind: inboxText(sender.kind || raw.sender_kind, 40) || (raw.is_mine ? "member" : "guest"),
    sender_display_name: inboxText(sender.display_name || raw.sender_display_name || raw.sender_name, 120) || "Participant",
    delivery_status: inboxText(raw.delivery_status, 80) || "recorded",
    is_initial: raw.is_initial === true,
    created_at: inboxText(raw.created_at, 80),
    is_mine: raw.is_mine === true || sender.is_current_user === true,
  };
}

function normalizeInboxWork(value) {
  const raw = inboxObject(value);
  const id = inboxText(raw.id || raw.image_id, 120);
  if (!id) return null;
  return {
    id,
    title: inboxText(raw.title, 240) || "Selected work",
  };
}

function normalizeInboxDetail(payload) {
  const rawPayload = inboxObject(payload);
  const rawConversation = inboxObject(
    rawPayload.conversation || rawPayload.inquiry || rawPayload.thread || rawPayload.item || rawPayload,
  );
  const conversation = normalizeInboxItem(rawConversation);
  if (!conversation) return null;
  const rawMessages = Array.isArray(rawPayload.messages)
    ? rawPayload.messages
    : Array.isArray(rawConversation.messages) ? rawConversation.messages : [];
  const rawWorks = Array.isArray(rawPayload.works)
    ? rawPayload.works
    : Array.isArray(rawConversation.works) ? rawConversation.works : [];
  const participants = Array.isArray(rawPayload.participants)
    ? rawPayload.participants
    : Array.isArray(rawConversation.participants) ? rawConversation.participants : [];
  const senderParticipant = participants.map(inboxObject).find((participant) => (
    participant.role === "sender" || participant.participant_role === "sender" || participant.kind === "sender"
  ));
  const viewerId = inboxText(rawPayload.viewer_user_id || rawConversation.viewer_user_id, 120);
  const permissions = inboxObject(rawPayload.permissions || rawConversation.permissions);
  return {
    ...conversation,
    sender_email: inboxText(senderParticipant?.email || senderParticipant?.user?.email || conversation.sender_email, 180),
    permissions: { can_manage: permissions.can_manage === true },
    messages: rawMessages.map(normalizeInboxMessage).filter((message) => message.body).map((message) => ({
      ...message,
      is_mine: message.is_mine || Boolean(viewerId && message.sender_user_id === viewerId),
    })),
    works: rawWorks.map(normalizeInboxWork).filter(Boolean),
  };
}

function announceInbox(message) {
  if (!inboxLive) return;
  inboxLive.textContent = "";
  window.setTimeout(() => { inboxLive.textContent = message; }, 20);
}

function showInboxToast(message, type = "success") {
  if (!inboxToast) return;
  window.clearTimeout(inboxToastTimer);
  inboxToast.textContent = message;
  inboxToast.dataset.type = type;
  inboxToast.classList.add("is-visible");
  inboxToastTimer = window.setTimeout(() => inboxToast.classList.remove("is-visible"), 3800);
}

async function inboxCsrfToken(force = false) {
  if (force) inboxCsrfPromise = null;
  if (!inboxCsrfPromise) {
    const request = fetch("/api/auth/csrf", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.csrf_token) throw new Error("Security verification is unavailable.");
      return payload.csrf_token;
    });
    inboxCsrfPromise = request;
    request.catch(() => {
      if (inboxCsrfPromise === request) inboxCsrfPromise = null;
    });
  }
  return inboxCsrfPromise;
}

async function inboxRequest(path, options = {}, retryCsrf = true) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (!new Set(["GET", "HEAD"]).has(method)) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = await inboxCsrfToken();
  }
  const response = await fetch(path, {
    ...options,
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 403 && payload.error?.code === "CSRF_REJECTED" && retryCsrf) {
    await inboxCsrfToken(true);
    return inboxRequest(path, options, false);
  }
  if (!response.ok) {
    const error = new Error(payload.error?.message || "The inbox request failed.");
    error.status = response.status;
    error.code = payload.error?.code || "INBOX_REQUEST_FAILED";
    error.details = payload.error?.details || null;
    throw error;
  }
  return payload;
}

function handleInboxBoundary(error) {
  const nextPath = `${window.location.pathname}${window.location.search}`;
  if (error?.status === 401) {
    window.location.assign(`/auth/sign-in?next=${encodeURIComponent(nextPath)}`);
    return true;
  }
  return false;
}

function setInboxListState(tone, title, message = "", action = null) {
  inboxListState.dataset.tone = tone;
  inboxListState.replaceChildren();
  if (tone === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "communications-spinner";
    spinner.setAttribute("aria-hidden", "true");
    inboxListState.append(spinner);
  } else {
    inboxListState.append(inboxIcon(tone === "error" ? "icon-alert" : "icon-inbox"));
  }
  const copy = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  copy.append(heading);
  if (message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    copy.append(paragraph);
  }
  inboxListState.append(copy);
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", action.handler, { once: true });
    inboxListState.append(button);
  }
  inboxListState.hidden = false;
}

function setInboxDetailState(tone, title, message = "", action = null) {
  inboxDetailState.dataset.tone = tone;
  inboxDetailState.replaceChildren();
  if (tone === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "communications-spinner";
    spinner.setAttribute("aria-hidden", "true");
    inboxDetailState.append(spinner);
  } else {
    inboxDetailState.append(inboxIcon(tone === "error" ? "icon-alert" : "icon-inbox"));
  }
  const copy = document.createElement("div");
  const heading = document.createElement("h2");
  heading.textContent = title;
  copy.append(heading);
  if (message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    copy.append(paragraph);
  }
  inboxDetailState.append(copy);
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", action.handler, { once: true });
    inboxDetailState.append(button);
  }
  inboxDetailState.hidden = false;
  inboxDetail.hidden = true;
}

function updateInboxUrl(id) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("conversation", id);
  else url.searchParams.delete("conversation");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function createInboxListItem(item) {
  const row = document.createElement("li");
  row.dataset.conversationId = item.id;
  row.className = "inbox-list-item";
  row.classList.toggle("is-active", item.id === inboxSelectedId);
  row.dataset.unread = String(item.unread_count > 0);
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.inboxOpen = item.id;
  button.setAttribute("aria-current", item.id === inboxSelectedId ? "true" : "false");
  button.setAttribute("aria-label", item.unread_count > 0
    ? `${inboxTitle(item)}, ${item.unread_count} unread message${item.unread_count === 1 ? "" : "s"}`
    : inboxTitle(item));

  const top = document.createElement("span");
  top.className = "inbox-list-item-top";
  const contact = document.createElement("strong");
  contact.textContent = item.sender_name;
  const time = document.createElement("time");
  time.dateTime = item.last_message_at;
  time.textContent = inboxDate(item.last_message_at, false);
  top.append(contact, time);

  const title = document.createElement("span");
  title.className = "inbox-list-item-title";
  title.textContent = inboxTitle(item);
  const preview = document.createElement("span");
  preview.className = "inbox-list-item-preview";
  preview.textContent = item.message_preview || `${item.message_count || 1} recorded message${item.message_count === 1 ? "" : "s"}`;

  const bottom = document.createElement("span");
  bottom.className = "inbox-list-item-bottom";
  const status = document.createElement("span");
  status.className = "inbox-status";
  status.dataset.status = item.status;
  status.textContent = item.status;
  const reference = document.createElement("span");
  reference.className = "inbox-list-reference";
  reference.textContent = item.public_reference;
  bottom.append(status, reference);
  if (item.unread_count > 0) {
    const unread = document.createElement("span");
    unread.className = "inbox-unread-count";
    unread.textContent = `${item.unread_count} unread`;
    bottom.append(unread);
  }
  button.append(top, title, preview, bottom);
  row.append(button);
  return row;
}

function renderInboxList() {
  const normalizedQuery = inboxQuery.toLocaleLowerCase("en");
  const visibleItems = inboxItems.filter((item) => {
    if (!normalizedQuery) return true;
    return [
      item.public_reference,
      item.sender_name,
      item.recipient_name,
      item.inquiry_type,
      item.organization,
      item.project_use,
      item.message_preview,
    ].some((value) => value.toLocaleLowerCase("en").includes(normalizedQuery));
  });
  inboxList.replaceChildren(...visibleItems.map(createInboxListItem));
  inboxList.hidden = visibleItems.length === 0;
  inboxListState.hidden = visibleItems.length > 0;
  inboxPagination.hidden = !inboxNextCursor;
  inboxMore.disabled = inboxListLoading;
  inboxTotal.textContent = String(visibleItems.length);
  inboxClear.hidden = !inboxQuery;
  if (!visibleItems.length && !inboxListLoading) {
    const filtered = Boolean(inboxQuery || inboxStatus !== "all");
    setInboxListState(
      "empty",
      filtered ? "No matching conversations" : "No conversations yet",
      filtered ? "Adjust the search or status filter." : "Recorded project inquiries will appear here.",
    );
  }
}

function appendDefinition(list, term, value) {
  if (!value) return;
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = value;
  list.append(dt, dd);
}

function createInboxMessage(message) {
  const item = document.createElement("li");
  item.dataset.senderKind = message.sender_kind;
  if (message.is_mine) item.dataset.mine = "true";
  const header = document.createElement("header");
  const sender = document.createElement("strong");
  sender.textContent = message.sender_display_name;
  const time = document.createElement("time");
  time.dateTime = message.created_at;
  time.textContent = inboxDate(message.created_at);
  header.append(sender, time);
  const body = document.createElement("p");
  body.textContent = message.body;
  const delivery = document.createElement("small");
  delivery.textContent = message.delivery_status === "provider_unavailable"
    ? "Recorded / external delivery unavailable"
    : "Recorded in Inbox";
  item.append(header, body, delivery);
  return item;
}

function setReplyAvailability(detail) {
  const closed = detail.status === "closed";
  inboxReplyMessage.disabled = closed || inboxReplyBusy || inboxStatusBusy;
  inboxReplySubmit.disabled = closed || inboxReplyBusy || inboxStatusBusy;
  inboxReplySubmit.setAttribute("aria-busy", String(inboxReplyBusy));
  inboxReplyMessage.placeholder = closed ? "This conversation is closed" : "Write a reply";
  if (closed) inboxReplyError.textContent = "Closed conversations cannot accept replies.";
  else if (!inboxReplyBusy && inboxReplyError.textContent === "Closed conversations cannot accept replies.") inboxReplyError.textContent = "";
}

function setInboxDetailCommands(detail) {
  const recipientCanManage = detail.participant_role === "recipient" && detail.permissions?.can_manage === true;
  const guestEmail = detail.participant_role === "recipient" && detail.sender_kind === "guest"
    ? safeInboxEmail(detail.sender_email)
    : "";
  inboxStatusAction.hidden = !recipientCanManage;
  inboxStatusAction.disabled = inboxStatusBusy;
  if (recipientCanManage) {
    const closing = detail.status !== "closed";
    inboxStatusAction.replaceChildren(inboxIcon(closing ? "icon-lock" : "icon-unlock"));
    inboxStatusAction.append(document.createTextNode(inboxStatusBusy ? "Updating..." : closing ? "Close conversation" : "Reopen conversation"));
    inboxStatusAction.setAttribute("aria-label", closing ? "Close conversation" : "Reopen conversation");
  }
  inboxManualEmail.hidden = !guestEmail;
  inboxCopyEmail.hidden = !guestEmail;
  inboxManualDeliveryNote.hidden = !guestEmail;
  if (guestEmail) {
    const subject = encodeURIComponent(`Re: ${detail.public_reference}`);
    inboxManualEmail.href = `mailto:${guestEmail}?subject=${subject}`;
    inboxManualEmail.setAttribute("aria-label", `Email ${guestEmail} manually`);
    inboxCopyEmail.dataset.email = guestEmail;
    inboxCopyEmail.setAttribute("aria-label", `Copy email address ${guestEmail}`);
  } else {
    inboxManualEmail.removeAttribute("href");
    inboxCopyEmail.removeAttribute("data-email");
  }
  inboxDetailCommands.hidden = !recipientCanManage && !guestEmail;
}

function renderInboxDetail(detail, { focus = false } = {}) {
  inboxSelectedDetail = detail;
  inboxDetailState.hidden = true;
  inboxDetail.hidden = false;
  const status = document.querySelector("[data-inbox-detail-status]");
  status.dataset.status = detail.status;
  status.textContent = detail.status;
  document.querySelector("[data-inbox-detail-reference]").textContent = detail.public_reference;
  const title = document.querySelector("[data-inbox-detail-title]");
  title.textContent = inboxTitle(detail);
  document.querySelector("[data-inbox-detail-contact]").textContent = detail.organization
    ? `${detail.sender_name} / ${detail.organization}`
    : detail.sender_name;

  const context = document.querySelector("[data-inbox-context]");
  context.replaceChildren();
  appendDefinition(context, "Contact", detail.sender_email || "Email unavailable");
  appendDefinition(context, "Type", detail.inquiry_type);
  appendDefinition(context, "Project / use", detail.project_use);
  appendDefinition(context, "Timeline", detail.timeline);
  appendDefinition(context, "Budget", detail.budget_range);
  appendDefinition(context, "Received", inboxDate(detail.created_at));
  if (detail.works.length) {
    const dt = document.createElement("dt");
    dt.textContent = "Selected works";
    const dd = document.createElement("dd");
    const list = document.createElement("ul");
    detail.works.forEach((work) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = `/workspace/images?${new URLSearchParams({ image: work.id }).toString()}`;
      link.textContent = work.title;
      item.append(link);
      list.append(item);
    });
    dd.append(list);
    context.append(dt, dd);
  }

  const messages = document.querySelector("[data-inbox-messages]");
  messages.replaceChildren(...detail.messages.map(createInboxMessage));
  const messageCount = detail.messages.length;
  document.querySelector("[data-inbox-message-count]").textContent = `${messageCount} message${messageCount === 1 ? "" : "s"}`;
  inboxStatusNotice.hidden = true;
  inboxStatusError.textContent = "";
  setInboxDetailCommands(detail);
  setReplyAvailability(detail);
  if (focus) title.focus({ preventScroll: true });
}

function setInboxBusy() {
  inboxRefresh.disabled = inboxListLoading || inboxDetailLoading || inboxReplyBusy || inboxStatusBusy;
  inboxMore.disabled = inboxListLoading;
  inboxInventory.setAttribute("aria-busy", String(inboxListLoading));
  inboxDetailRegion.setAttribute("aria-busy", String(inboxDetailLoading || inboxReplyBusy || inboxStatusBusy));
}

async function markInboxRead(id) {
  const item = inboxItems.find((entry) => entry.id === id);
  if (!item || item.unread_count <= 0) return;
  try {
    await inboxRequest(`/api/inbox/${encodeURIComponent(id)}/read`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    inboxItems = inboxItems.map((entry) => entry.id === id ? { ...entry, unread_count: 0 } : entry);
    if (inboxSelectedDetail?.id === id) inboxSelectedDetail = { ...inboxSelectedDetail, unread_count: 0 };
    renderInboxList();
  } catch (error) {
    handleInboxBoundary(error);
  }
}

async function loadInbox({ append = false } = {}) {
  if (inboxListLoading || (append && !inboxNextCursor)) return;
  inboxListLoading = true;
  const requestId = ++inboxListSerial;
  if (!append) {
    inboxListController?.abort();
    inboxListController = new AbortController();
    setInboxListState("loading", "Loading conversations...");
    inboxList.hidden = true;
  }
  setInboxBusy();
  try {
    const params = new URLSearchParams({ status: inboxStatus, limit: String(INBOX_LIMIT) });
    if (append && inboxNextCursor) {
      params.set("before", inboxNextCursor.before);
      params.set("before_id", inboxNextCursor.before_id);
    }
    const payload = await inboxRequest(`/api/inbox?${params.toString()}`, {
      signal: inboxListController?.signal,
    });
    if (requestId !== inboxListSerial) return;
    const nextItems = Array.isArray(payload.items) ? payload.items.map(normalizeInboxItem).filter(Boolean) : [];
    const merged = append ? [...inboxItems, ...nextItems] : nextItems;
    inboxItems = Array.from(new Map(merged.map((item) => [item.id, item])).values());
    const rawCursor = inboxObject(payload.next_cursor || payload.pagination?.next_cursor);
    const before = inboxText(rawCursor.before || rawCursor.last_message_at, 80);
    const beforeId = inboxText(rawCursor.before_id || rawCursor.id, 120);
    inboxNextCursor = before && beforeId ? { before, before_id: beforeId } : null;
    inboxListLoading = false;
    renderInboxList();

    const requestedId = inboxText(new URLSearchParams(window.location.search).get("conversation"), 120);
    const selectedStillVisible = inboxItems.some((item) => item.id === inboxSelectedId);
    if (!append && inboxSelectedId && !selectedStillVisible && !requestedId) {
      inboxSelectedId = "";
      inboxSelectedDetail = null;
      setInboxDetailState("empty", "Select a conversation", "Conversation details will appear here.");
    }
    const firstVisibleId = inboxList.querySelector("[data-inbox-open]")?.dataset.inboxOpen || "";
    const initialId = requestedId || (window.matchMedia("(min-width: 761px)").matches ? firstVisibleId : "");
    if (!append && initialId && initialId !== inboxSelectedId) {
      await loadInboxDetail(initialId, { showMobile: Boolean(requestedId), focus: false });
    } else if (!append && initialId && !inboxSelectedDetail) {
      await loadInboxDetail(initialId, { showMobile: Boolean(requestedId), focus: false });
    }
  } catch (error) {
    if (error?.name === "AbortError" || requestId !== inboxListSerial) return;
    if (handleInboxBoundary(error)) return;
    if (!append) {
      inboxItems = [];
      inboxNextCursor = null;
      inboxList.replaceChildren();
      inboxList.hidden = true;
    }
    setInboxListState(
      error?.status === 403 ? "permission" : "error",
      error?.status === 403 ? "Inbox unavailable" : "Inbox could not be loaded",
      error.message || "Try the request again.",
      { label: "Retry", handler: () => loadInbox() },
    );
  } finally {
    if (requestId === inboxListSerial) {
      inboxListLoading = false;
      setInboxBusy();
    }
  }
}

async function loadInboxDetail(id, { showMobile = true, focus = true } = {}) {
  const safeId = inboxText(id, 120);
  if (!safeId || inboxDetailLoading) return;
  inboxSelectedId = safeId;
  inboxDetailLoading = true;
  const requestId = ++inboxDetailSerial;
  inboxDetailController?.abort();
  inboxDetailController = new AbortController();
  updateInboxUrl(safeId);
  if (showMobile) inboxWorkspace.dataset.mobileView = "detail";
  renderInboxList();
  setInboxDetailState("loading", "Loading conversation...");
  setInboxBusy();
  try {
    const payload = await inboxRequest(`/api/inbox/${encodeURIComponent(safeId)}`, {
      signal: inboxDetailController.signal,
    });
    if (requestId !== inboxDetailSerial) return;
    const detail = normalizeInboxDetail(payload);
    if (!detail) throw new Error("The conversation response was incomplete.");
    inboxStatusIdempotencyKey = "";
    renderInboxDetail(detail, { focus });
    markInboxRead(detail.id);
  } catch (error) {
    if (error?.name === "AbortError" || requestId !== inboxDetailSerial) return;
    if (handleInboxBoundary(error)) return;
    setInboxDetailState(
      error?.status === 403 ? "permission" : "error",
      error?.status === 403 ? "Conversation unavailable" : "Conversation could not be loaded",
      error.message || "Try the request again.",
      { label: "Retry", handler: () => loadInboxDetail(safeId, { showMobile, focus }) },
    );
  } finally {
    if (requestId === inboxDetailSerial) {
      inboxDetailLoading = false;
      setInboxBusy();
    }
  }
}

function showInboxStatusError(message) {
  inboxStatusError.textContent = message;
  inboxStatusNotice.hidden = false;
  inboxStatusNotice.focus();
}

async function updateInboxStatus() {
  if (!inboxSelectedDetail || inboxStatusBusy) return;
  if (inboxSelectedDetail.participant_role !== "recipient" || inboxSelectedDetail.permissions?.can_manage !== true) return;
  const nextStatus = inboxSelectedDetail.status === "closed" ? "open" : "closed";
  inboxStatusBusy = true;
  inboxStatusIdempotencyKey ||= inboxUuid();
  inboxStatusNotice.hidden = true;
  setInboxDetailCommands(inboxSelectedDetail);
  setReplyAvailability(inboxSelectedDetail);
  setInboxBusy();
  try {
    const payload = await inboxRequest(`/api/inbox/${encodeURIComponent(inboxSelectedDetail.id)}/status`, {
      method: "POST",
      body: JSON.stringify({
        status: nextStatus,
        expected_version: inboxSelectedDetail.version,
        idempotency_key: inboxStatusIdempotencyKey,
      }),
    });
    const responseConversation = normalizeInboxItem(payload.conversation || payload.inquiry || payload.thread || {});
    const version = responseConversation?.version
      || inboxInteger(payload.conversation_version, inboxInteger(payload.version, inboxSelectedDetail.version + 1));
    const status = responseConversation?.status || inboxText(payload.status, 40) || nextStatus;
    inboxSelectedDetail = { ...inboxSelectedDetail, version, status };
    inboxItems = inboxItems.map((item) => item.id === inboxSelectedDetail.id ? { ...item, version, status } : item);
    inboxStatusIdempotencyKey = "";
    renderInboxList();
    renderInboxDetail(inboxSelectedDetail, { focus: false });
    const message = status === "closed" ? "Conversation closed." : "Conversation reopened.";
    showInboxToast(message);
    announceInbox(message);
  } catch (error) {
    if (!handleInboxBoundary(error)) {
      showInboxStatusError(error.message || "The conversation status could not be updated. Reload and try again.");
    }
  } finally {
    inboxStatusBusy = false;
    if (inboxSelectedDetail) {
      setInboxDetailCommands(inboxSelectedDetail);
      setReplyAvailability(inboxSelectedDetail);
    }
    setInboxBusy();
  }
}

async function copyInboxEmail() {
  const email = safeInboxEmail(inboxCopyEmail.dataset.email);
  if (!email) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(email);
    } else {
      const field = document.createElement("textarea");
      field.value = email;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.append(field);
      field.select();
      if (!document.execCommand("copy")) throw new Error("Copy failed");
      field.remove();
    }
    showInboxToast("Email address copied.");
    announceInbox("Email address copied.");
  } catch (_error) {
    showInboxToast("The email address could not be copied.", "error");
  }
}

function updateReplyCount() {
  const length = String(inboxReplyMessage?.value || "").length;
  inboxReplyCount.textContent = `${length} / 5000`;
}

function replyDeliveryMessage(payload) {
  const delivery = inboxObject(payload.delivery);
  const unavailable = delivery.provider_status === "unavailable"
    || delivery.provider_action_required === true
    || payload.delivery_status === "provider_unavailable";
  return unavailable
    ? "Reply recorded. External email delivery is unavailable."
    : "Reply recorded in this inbox.";
}

async function submitInboxReply(event) {
  event.preventDefault();
  if (inboxReplyBusy || !inboxSelectedDetail) return;
  const message = inboxText(inboxReplyMessage.value, 5000);
  inboxReplyError.textContent = "";
  inboxReplyMessage.setAttribute("aria-invalid", "false");
  if (inboxSelectedDetail.status === "closed") {
    inboxReplyError.textContent = "Closed conversations cannot accept replies.";
    return;
  }
  if (!message) {
    inboxReplyError.textContent = "Enter a reply before recording it.";
    inboxReplyMessage.setAttribute("aria-invalid", "true");
    inboxReplyMessage.focus();
    return;
  }
  inboxReplyBusy = true;
  inboxReplyIdempotencyKey ||= inboxUuid();
  setReplyAvailability(inboxSelectedDetail);
  setInboxBusy();
  try {
    const payload = await inboxRequest(`/api/inbox/${encodeURIComponent(inboxSelectedDetail.id)}/messages`, {
      method: "POST",
      body: JSON.stringify({
        expected_version: inboxSelectedDetail.version,
        message,
        idempotency_key: inboxReplyIdempotencyKey,
      }),
    });
    const responseConversation = normalizeInboxItem(payload.conversation || payload.inquiry || payload.thread || {});
    const nextVersion = responseConversation?.version
      || inboxInteger(payload.conversation_version, inboxInteger(payload.version, inboxSelectedDetail.version + 1));
    const nextStatus = responseConversation?.status || inboxText(payload.status, 40) || "replied";
    inboxSelectedDetail = {
      ...inboxSelectedDetail,
      version: nextVersion,
      status: nextStatus,
    };
    inboxItems = inboxItems.map((item) => item.id === inboxSelectedDetail.id
      ? { ...item, version: nextVersion, status: nextStatus, message_preview: message, last_message_at: new Date().toISOString() }
      : item);
    inboxReplyMessage.value = "";
    inboxReplyIdempotencyKey = "";
    updateReplyCount();
    renderInboxList();
    const recordedMessage = replyDeliveryMessage(payload);
    showInboxToast(recordedMessage);
    announceInbox(recordedMessage);
    await loadInboxDetail(inboxSelectedDetail.id, { showMobile: true, focus: false });
  } catch (error) {
    if (handleInboxBoundary(error)) return;
    if (new Set([
      "CONVERSATION_VERSION_CONFLICT",
      "INBOX_VERSION_CONFLICT",
      "CONVERSATION_CLOSED",
      "CONVERSATION_STATE_CONFLICT",
    ]).has(error.code)) {
      inboxReplyError.textContent = error.message || "The conversation changed. Reload it before replying.";
    } else {
      inboxReplyError.textContent = error.message || "The reply could not be recorded.";
    }
    inboxReplyMessage.setAttribute("aria-invalid", "true");
    inboxReplyMessage.focus();
  } finally {
    inboxReplyBusy = false;
    if (inboxSelectedDetail) setReplyAvailability(inboxSelectedDetail);
    setInboxBusy();
  }
}

inboxFilters?.addEventListener("submit", (event) => {
  event.preventDefault();
  const nextQuery = inboxText(inboxFilters.elements.q.value, 160);
  const nextStatus = INBOX_STATUSES.has(inboxFilters.elements.status.value) ? inboxFilters.elements.status.value : "all";
  const statusChanged = nextStatus !== inboxStatus;
  inboxQuery = nextQuery;
  inboxStatus = nextStatus;
  if (statusChanged) {
    inboxNextCursor = null;
    inboxSelectedId = "";
    inboxSelectedDetail = null;
    updateInboxUrl("");
    inboxWorkspace.dataset.mobileView = "list";
    loadInbox();
    return;
  }
  renderInboxList();
  const selectedVisible = inboxSelectedId && inboxList.querySelector(`[data-inbox-open="${CSS.escape(inboxSelectedId)}"]`);
  if (!selectedVisible && window.matchMedia("(min-width: 761px)").matches) {
    const firstVisible = inboxList.querySelector("[data-inbox-open]")?.dataset.inboxOpen;
    if (firstVisible) loadInboxDetail(firstVisible, { showMobile: false, focus: false });
  }
});
inboxFilters?.elements?.status?.addEventListener("change", () => inboxFilters.requestSubmit());
inboxClear?.addEventListener("click", () => {
  inboxFilters.elements.q.value = "";
  inboxQuery = "";
  inboxFilters.requestSubmit();
});
inboxList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inbox-open]");
  if (!button) return;
  loadInboxDetail(button.dataset.inboxOpen, { showMobile: true, focus: true });
});
inboxMore?.addEventListener("click", () => loadInbox({ append: true }));
inboxRefresh?.addEventListener("click", () => {
  if (inboxSelectedId) loadInboxDetail(inboxSelectedId, { showMobile: false, focus: false });
  loadInbox();
});
inboxBack?.addEventListener("click", () => {
  inboxWorkspace.dataset.mobileView = "list";
  updateInboxUrl("");
  inboxList.querySelector(`[data-inbox-open="${CSS.escape(inboxSelectedId)}"]`)?.focus();
});
inboxReplyMessage?.addEventListener("input", () => {
  updateReplyCount();
  inboxReplyError.textContent = "";
  inboxReplyMessage.setAttribute("aria-invalid", "false");
  if (!inboxReplyBusy) inboxReplyIdempotencyKey = "";
});
inboxReplyForm?.addEventListener("submit", submitInboxReply);
inboxStatusAction?.addEventListener("click", updateInboxStatus);
inboxCopyEmail?.addEventListener("click", copyInboxEmail);
inboxStatusReload?.addEventListener("click", () => {
  if (!inboxSelectedId) return;
  inboxStatusIdempotencyKey = "";
  loadInboxDetail(inboxSelectedId, { showMobile: true, focus: true });
});
window.addEventListener("popstate", () => {
  const id = inboxText(new URLSearchParams(window.location.search).get("conversation"), 120);
  if (id) loadInboxDetail(id, { showMobile: true, focus: false });
  else inboxWorkspace.dataset.mobileView = "list";
});

updateReplyCount();
loadInbox();
