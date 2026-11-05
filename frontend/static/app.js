"use strict";

const form = document.getElementById("ticket-form");
const filter = document.getElementById("filter");
const list = document.getElementById("ticket-list");
const listMessage = document.getElementById("list-message");
const formMessage = document.getElementById("form-message");
const emptyState = document.getElementById("empty-state");
const statusLabels = { open: "Open", in_progress: "In progress", resolved: "Resolved" };
let refreshVersion = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // Never interpret user content as HTML.
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const details = data.details ? " " + Object.values(data.details).join(" ") : "";
    throw new Error((data.error || "The request failed.") + details);
  }
  return data;
}

function buildTicket(ticket) {
  const item = element("li", "ticket");
  const top = element("div", "ticket-top");
  const id = element("span", "ticket-id", `#${String(ticket.id).padStart(4, "0")}`);
  const priority = element("span", `priority priority-${ticket.priority}`, `${ticket.priority} priority`);
  top.append(id, priority);
  const title = element("h3", "ticket-title", ticket.title);
  const description = element("p", "ticket-description", ticket.description);
  const meta = element("p", "ticket-meta");
  const created = new Date(ticket.created_at);
  const date = Number.isNaN(created.valueOf()) ? ticket.created_at : created.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  meta.textContent = `${ticket.requester}  ·  ${ticket.category}  ·  ${date}`;
  const bottom = element("div", "ticket-bottom");
  const label = element("label", "status-label", "STATUS");
  const select = element("select", `status-select status-${ticket.status}`);
  select.setAttribute("aria-label", `Status for ticket ${ticket.id}: ${ticket.title}`);
  for (const [value, text] of Object.entries(statusLabels)) {
    const option = element("option", "", text);
    option.value = value;
    option.selected = value === ticket.status;
    select.append(option);
  }
  select.addEventListener("change", async () => {
    select.disabled = true;
    listMessage.textContent = "";
    try {
      await api(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: select.value }),
      });
      // If refreshing fails, the update still succeeded; do not revert the selection.
      ticket.status = select.value;
      select.className = `status-select status-${ticket.status}`;
      try { await refresh(); } catch (_) { select.disabled = false; }
    } catch (error) {
      listMessage.textContent = error.message;
      select.value = ticket.status;
      select.disabled = false;
    }
  });
  label.append(select);
  bottom.append(label);
  item.append(top, title, description, meta, bottom);
  return item;
}

async function refresh() {
  const version = ++refreshVersion;
  listMessage.textContent = "";
  try {
    const [summary, result] = await Promise.all([
      api("/api/summary"),
      api(`/api/tickets?status=${encodeURIComponent(filter.value)}`),
    ]);
    if (version !== refreshVersion) return;
    document.getElementById("stat-total").textContent = summary.total;
    document.getElementById("stat-open").textContent = summary.open;
    document.getElementById("stat-progress").textContent = summary.in_progress;
    document.getElementById("stat-resolved").textContent = summary.resolved;
    list.replaceChildren(...result.tickets.map(buildTicket));
    emptyState.hidden = result.tickets.length !== 0;
  } catch (error) {
    if (version === refreshVersion) {
      emptyState.hidden = true;
      listMessage.textContent = `Could not load requests. ${error.message}`;
    }
    throw error;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  const fields = new FormData(form);
  const payload = Object.fromEntries(fields.entries());
  submit.disabled = true;
  formMessage.textContent = "";
  try {
    await api("/api/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    form.reset();
    filter.value = "all";
    formMessage.textContent = "Request created.";
    // A refresh failure doesn't mean the already-created ticket failed.
    try { await refresh(); } catch (_) { /* refresh() displays its own message */ }
  } catch (error) {
    formMessage.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

filter.addEventListener("change", () => { refresh().catch(() => {}); });
refresh().catch(() => {});
