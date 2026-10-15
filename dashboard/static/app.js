// Client-side behavior for the dashboard: search/filters, queue/timeline
// views, the triage form, the runbook viewer, and small UI touches.
// Plain JavaScript, no frameworks.

const rows = Array.from(document.querySelectorAll("details.alert"));
// Everything the filters apply to: queue rows *and* timeline entries.
const filterables = Array.from(document.querySelectorAll(".filterable"));

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Browser storage can throw (private mode, blocked cookies), so wrap it.
function storageGet(store, key) {
  try { return store.getItem(key); } catch (e) { return null; }
}
function storageSet(store, key, value) {
  try { store.setItem(key, value); } catch (e) {}
}

// ---------- Search and filters ----------

const searchBox = document.getElementById("search");
const priorityFilter = document.getElementById("filter-priority");
const runbookFilter = document.getElementById("filter-runbook");
const triageFilter = document.getElementById("filter-triage");
const priorityCards = document.querySelectorAll(".stat-priority");

function matchesFilters(el, query) {
  return (
    (!query || el.dataset.search.includes(query)) &&
    (!priorityFilter.value || el.dataset.priority === priorityFilter.value) &&
    (!runbookFilter.value || el.dataset.runbook === runbookFilter.value) &&
    (!triageFilter.value || el.dataset.triaged === triageFilter.value)
  );
}

function applyFilters() {
  if (!searchBox) return;
  const query = searchBox.value.trim().toLowerCase();

  filterables.forEach((el) => { el.hidden = !matchesFilters(el, query); });

  // Hide timeline days that have nothing left in them.
  document.querySelectorAll(".tl-day").forEach((day) => {
    day.hidden = !day.querySelector(".tl-item:not([hidden])");
  });

  const shown = rows.filter((row) => !row.hidden).length;
  document.getElementById("shown-count").textContent =
    shown === rows.length ? "" : `(${shown} of ${rows.length} shown)`;
  document.getElementById("no-results").hidden = shown > 0;

  // Keep the priority stat cards in sync with the dropdown.
  priorityCards.forEach((card) => {
    card.setAttribute("aria-pressed", String(card.dataset.priority === priorityFilter.value));
  });
}

if (searchBox) {
  searchBox.addEventListener("input", applyFilters);
  [priorityFilter, runbookFilter, triageFilter].forEach((el) =>
    el.addEventListener("change", applyFilters)
  );
}

// Clicking a priority card filters to that priority; clicking it again clears it.
priorityCards.forEach((card) => {
  card.addEventListener("click", () => {
    priorityFilter.value = priorityFilter.value === card.dataset.priority ? "" : card.dataset.priority;
    applyFilters();
  });
});

// ---------- Queue / timeline toggle ----------

const viewButtons = document.querySelectorAll(".segmented [data-view]");

function setView(view) {
  const queue = document.getElementById("view-queue");
  const timeline = document.getElementById("view-timeline");
  if (!queue || !timeline) return;

  queue.hidden = view !== "queue";
  timeline.hidden = view !== "timeline";
  document.getElementById("view-title").textContent = view === "queue" ? "Alert queue" : "Detection timeline";
  viewButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
  storageSet(localStorage, "view", view);
}

viewButtons.forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
setView(storageGet(localStorage, "view") === "timeline" ? "timeline" : "queue");

// Clicking a timeline entry jumps to that alert, expanded, in the queue view.
document.querySelectorAll("[data-open-alert]").forEach((card) => {
  card.addEventListener("click", () => {
    const row = document.getElementById(`alert-${card.dataset.openAlert}`);
    setView("queue");
    row.open = true;
    row.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  });
});

// ---------- Stats bar animation ----------

// Bars and the coverage ring start empty in CSS. Adding .is-ready on the
// next frame lets the CSS transitions animate them up to their real values.
requestAnimationFrame(() => {
  document.body.classList.add("is-ready");
});

// Count the coverage number up from 0 so it moves with the ring.
const coverageValue = document.getElementById("coverage-value");
if (coverageValue && !reduceMotion) {
  const target = Number(coverageValue.dataset.target);
  const duration = 1200;
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3); // ease-out, matches the CSS curve
    coverageValue.textContent = Math.round(target * eased);
    if (t < 1) requestAnimationFrame(tick);
  };
  coverageValue.textContent = "0";
  requestAnimationFrame(tick);
}

// ---------- Stale runbook banner ----------

const banner = document.getElementById("stale-banner");
if (banner) {
  // The key includes each stale runbook's review date, so if a different
  // runbook goes stale later, the banner comes back even if this one was dismissed.
  const key = `stale-dismissed:${banner.dataset.key}`;
  if (storageGet(sessionStorage, key)) banner.hidden = true;
  document.getElementById("stale-dismiss").addEventListener("click", () => {
    banner.hidden = true;
    storageSet(sessionStorage, key, "1");
  });
}

// ---------- Export menu ----------

const exportMenu = document.getElementById("export-menu");
if (exportMenu) {
  // Close the dropdown when clicking anywhere else, or after picking an option.
  document.addEventListener("click", (event) => {
    if (!exportMenu.contains(event.target)) exportMenu.open = false;
  });
  exportMenu.querySelectorAll("a").forEach((a) =>
    a.addEventListener("click", () => { exportMenu.open = false; })
  );
}

// ---------- Triage form ----------

function updateTriagedStats() {
  // The stats bar only exists on the Dashboard page.
  const countEl = document.getElementById("triaged-count");
  if (!countEl) return;
  const count = rows.filter((row) => row.dataset.triaged === "triaged").length;
  countEl.textContent = count;
  document.getElementById("triaged-bar").style.setProperty("--pct", (100 * count) / rows.length);
}

// Update the queue row *and* the matching timeline entry after a save.
function showTriageState(form, entry) {
  document.querySelectorAll(`.filterable[data-alert-id="${CSS.escape(form.dataset.alertId)}"]`).forEach((el) => {
    el.dataset.triaged = entry.triaged ? "triaged" : "open";
    el.classList.toggle("is-triaged", entry.triaged);
  });

  form.querySelector(".triage-status").textContent = entry.triaged
    ? `Triaged by ${entry.analyst} at ${entry.triaged_at}`
    : "Reopened, not triaged";
  form.querySelector("button[type=submit]").textContent = entry.triaged
    ? "Update notes"
    : "Mark as triaged";
  form.querySelector(".reopen").hidden = !entry.triaged;

  updateTriagedStats();
  applyFilters();
}

async function postTriage(form, action, body) {
  const message = form.querySelector(".form-message");
  message.textContent = "Saving…";
  try {
    const response = await fetch(`/api/alerts/${encodeURIComponent(form.dataset.alertId)}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    showTriageState(form, await response.json());
    message.textContent = "Saved";
  } catch (err) {
    message.textContent = `Could not save: ${err.message}`;
  }
}

document.querySelectorAll(".triage-form").forEach((form) => {
  // Remember the analyst name between alerts so it doesn't need retyping.
  const analystInput = form.elements.analyst;
  if (!analystInput.value) analystInput.value = storageGet(localStorage, "analyst") || "";

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    storageSet(localStorage, "analyst", analystInput.value);
    postTriage(form, "triage", { analyst: analystInput.value, notes: form.elements.notes.value });
  });

  form.querySelector(".reopen").addEventListener("click", () => postTriage(form, "reopen"));
});

// ---------- Runbook viewer ----------

const dialog = document.getElementById("runbook-dialog");

async function openRunbook(alertType) {
  const title = document.getElementById("runbook-title");
  const meta = document.getElementById("runbook-meta");
  const body = document.getElementById("runbook-body");

  title.textContent = "Loading…";
  meta.textContent = "";
  body.innerHTML = "";
  dialog.showModal();

  try {
    const response = await fetch(`/api/runbooks/${encodeURIComponent(alertType)}`);
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const runbook = await response.json();
    title.textContent = runbook.title;
    meta.textContent = `runbooks/${runbook.file} · owner ${runbook.owner} · last reviewed ${runbook.last_reviewed}`;
    // Safe to insert: the server HTML-escapes the Markdown before formatting it.
    body.innerHTML = runbook.html;
  } catch (err) {
    title.textContent = "Runbook unavailable";
    body.textContent = err.message;
  }
}

document.querySelectorAll(".runbook-link").forEach((button) => {
  button.addEventListener("click", (event) => {
    // Some runbook tags sit inside <summary>, so stop the click from
    // also expanding or collapsing the alert row.
    event.preventDefault();
    event.stopPropagation();
    openRunbook(button.dataset.alertType);
  });
});

document.getElementById("runbook-close").addEventListener("click", () => dialog.close());
// Clicking the dimmed backdrop (outside the dialog box) also closes it.
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

// Links from the Runbooks page arrive as /alerts?type=SG_OPEN_SSH, which
// pre-fills the search box so only that alert type is shown.
const typeParam = new URLSearchParams(window.location.search).get("type");
if (searchBox && typeParam) searchBox.value = typeParam;

applyFilters();
