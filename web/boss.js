const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const headingEl = document.getElementById("heading");
const listEl = document.getElementById("list");
const progressEl = document.getElementById("progress");
const bannerEl = document.getElementById("banner");
const toastEl = document.getElementById("toast");
const aiDraftForm = document.getElementById("ai-draft-form");
const aiDraftTextEl = document.getElementById("ai-draft-text");
const aiAddForm = document.getElementById("ai-add-form");
const aiAddTextEl = document.getElementById("ai-add-text");
const addForm = document.getElementById("add-form");
const addTextEl = document.getElementById("add-text");
const addVillaEl = document.getElementById("add-villa");
const villaListEl = document.getElementById("villa-list");
const addSectionEl = document.getElementById("add-section");
const sectionListEl = document.getElementById("section-list");
const sendCountEl = document.getElementById("send-count");
const sendNowBtn = document.getElementById("send-now-btn");

const initData = tg ? tg.initData : "";

let selectedIds = new Set();
let selectedNotes = new Map(); // library_item_id -> note text, for this send only
let latestLibrary = [];
let latestBossState = null;
let selectedTarget = "today"; // "today" | "tomorrow" — which date we're editing
let busy = false;
let toastTimer = null;

function showBanner(text) {
  bannerEl.textContent = text;
  bannerEl.classList.remove("hidden");
}

function hideBanner() {
  bannerEl.classList.add("hidden");
}

function showToast(text) {
  toastEl.textContent = text;
  toastEl.classList.remove("hidden");
  toastEl.classList.add("show");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.remove("show");
    setTimeout(() => toastEl.classList.add("hidden"), 300);
  }, 3000);
}

function render(library) {
  latestLibrary = library;
  progressEl.textContent = `${library.length} items in library`;

  const villas = [];
  const byVilla = new Map();
  const sectionSet = new Set();
  for (const item of library) {
    sectionSet.add(item.section);
    if (!byVilla.has(item.villa)) {
      byVilla.set(item.villa, []);
      villas.push(item.villa);
    }
    byVilla.get(item.villa).push(item);
  }

  sectionListEl.innerHTML = "";
  for (const section of sectionSet) {
    const opt = document.createElement("option");
    opt.value = section;
    sectionListEl.appendChild(opt);
  }

  villaListEl.innerHTML = "";
  for (const villa of villas) {
    const opt = document.createElement("option");
    opt.value = villa;
    villaListEl.appendChild(opt);
  }

  listEl.innerHTML = "";
  for (const villa of villas) {
    const villaEl = document.createElement("div");
    villaEl.className = "villa";

    const villaHeader = document.createElement("div");
    villaHeader.className = "villa-header";

    const villaTitle = document.createElement("div");
    villaTitle.className = "villa-title";
    villaTitle.textContent = `Villa ${villa}`;
    villaHeader.appendChild(villaTitle);

    const villaActions = document.createElement("div");
    villaActions.className = "villa-actions";

    const villaIds = byVilla.get(villa).map((i) => i.id);

    const selectBtn = document.createElement("button");
    selectBtn.type = "button";
    selectBtn.className = "villa-select-btn";
    selectBtn.textContent = "Select all";
    selectBtn.addEventListener("click", () => {
      for (const id of villaIds) selectedIds.add(id);
      render(latestLibrary);
    });
    villaActions.appendChild(selectBtn);

    const deselectBtn = document.createElement("button");
    deselectBtn.type = "button";
    deselectBtn.className = "villa-select-btn";
    deselectBtn.textContent = "Deselect all";
    deselectBtn.addEventListener("click", () => {
      for (const id of villaIds) selectedIds.delete(id);
      render(latestLibrary);
    });
    villaActions.appendChild(deselectBtn);

    villaHeader.appendChild(villaActions);
    villaEl.appendChild(villaHeader);

    const sections = [];
    const bySection = new Map();
    for (const item of byVilla.get(villa)) {
      if (!bySection.has(item.section)) {
        bySection.set(item.section, []);
        sections.push(item.section);
      }
      bySection.get(item.section).push(item);
    }

    for (const section of sections) {
      const sectionEl = document.createElement("div");
      sectionEl.className = "section";

      const title = document.createElement("div");
      title.className = "section-title";
      title.textContent = section;
      sectionEl.appendChild(title);

      for (const item of bySection.get(section)) {
        sectionEl.appendChild(renderItem(item));
      }
      villaEl.appendChild(sectionEl);
    }

    listEl.appendChild(villaEl);
  }

  sendCountEl.textContent = `${selectedIds.size} selected`;
}

function renderItem(item) {
  const row = document.createElement("div");
  row.className = "item";
  if (selectedIds.has(item.id)) row.classList.add("selected");

  const box = document.createElement("div");
  box.className = "checkbox";
  box.textContent = selectedIds.has(item.id) ? "✓" : "";
  row.appendChild(box);

  const body = document.createElement("div");
  body.className = "item-body";
  const text = document.createElement("div");
  text.className = "item-text";
  text.textContent = item.text;
  body.appendChild(text);
  const note = selectedNotes.get(item.id);
  if (note) {
    const noteEl = document.createElement("div");
    noteEl.className = "item-note";
    noteEl.textContent = `📝 ${note}`;
    body.appendChild(noteEl);
  }
  row.appendChild(body);

  const noteBtn = document.createElement("button");
  noteBtn.type = "button";
  noteBtn.className = "rename-btn";
  noteBtn.textContent = note ? "Note ✓" : "Note";
  noteBtn.setAttribute("aria-label", "Add a note for this send");
  noteBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    editNote(item.id);
  });
  row.appendChild(noteBtn);

  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "rename-btn";
  renameBtn.textContent = "Change";
  renameBtn.setAttribute("aria-label", "Change task name");
  renameBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    renameItem(item.id, item.text);
  });
  row.appendChild(renameBtn);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "media-icon";
  removeBtn.textContent = "×";
  removeBtn.setAttribute("aria-label", "Delete from library");
  removeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    removeItem(item.id);
  });
  row.appendChild(removeBtn);

  row.addEventListener("click", () => toggleSelect(item.id));

  return row;
}

function editNote(itemId) {
  const current = selectedNotes.get(itemId) || "";
  const text = window.prompt(
    "Note for this send only (e.g. \"assigned to Yadvinder, budget 2 hours\") — leave blank to remove:",
    current
  );
  if (text === null) return;
  const trimmed = text.trim();
  if (trimmed) {
    selectedNotes.set(itemId, trimmed);
    selectedIds.add(itemId); // a note only matters if the item is actually being sent
  } else {
    selectedNotes.delete(itemId);
  }
  render(latestLibrary);
}

function toggleSelect(itemId) {
  if (selectedIds.has(itemId)) {
    selectedIds.delete(itemId);
  } else {
    selectedIds.add(itemId);
  }
  render(latestLibrary);
}

function targetLabel(target) {
  return target === "tomorrow" ? "Tomorrow" : "Today";
}

function targetDate(data, target) {
  return target === "tomorrow" ? data.tomorrow_date : data.today_date;
}

function updateHeading() {
  if (!latestBossState) return;
  headingEl.textContent = `${targetLabel(selectedTarget)}: ${targetDate(latestBossState, selectedTarget)}`;
}

function applySelectionForTarget(data, target) {
  const items = target === "tomorrow" ? data.tomorrow_active_items : data.today_active_items;
  selectedIds = new Set(items.map((i) => i.id));
  selectedNotes = new Map(items.filter((i) => i.note).map((i) => [i.id, i.note]));
}

function applyBossState(data, resetSelection) {
  latestBossState = data;
  if (resetSelection) {
    applySelectionForTarget(data, selectedTarget);
  } else {
    const validIds = new Set(data.library.map((i) => i.id));
    selectedIds = new Set([...selectedIds].filter((id) => validIds.has(id)));
    for (const id of [...selectedNotes.keys()]) {
      if (!selectedIds.has(id)) selectedNotes.delete(id);
    }
  }
  updateHeading();
  render(data.library);
}

headingEl.addEventListener("click", () => {
  if (!latestBossState) return;
  selectedTarget = selectedTarget === "today" ? "tomorrow" : "today";
  applySelectionForTarget(latestBossState, selectedTarget);
  updateHeading();
  render(latestBossState.library);
});

async function loadLibrary(resetSelection) {
  if (!initData) {
    showBanner("Open this from the library button in Telegram.");
    return;
  }
  try {
    const res = await fetch("/api/boss/library", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not load the library.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, resetSelection);
  } catch (err) {
    showBanner("Network error loading the library.");
  }
}

aiDraftForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy) return;
  const text = aiDraftTextEl.value.trim();
  if (!text) return;

  const submitBtn = aiDraftForm.querySelector("button");
  const originalLabel = submitBtn.textContent;
  busy = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Thinking... (up to 1 min)";
  try {
    const res = await fetch("/api/boss/library/ai-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, text }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not draft a plan.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
    // Adds to whatever's already selected rather than replacing it, so
    // this never silently discards items the boss picked by hand first.
    for (const id of data.draft_ids) selectedIds.add(id);
    render(latestLibrary);
    aiDraftTextEl.value = "";
    if (!data.ai_used) {
      showToast("AI wasn't available — compose the plan manually");
    } else {
      const total = data.draft_ids.length;
      const newCount = data.new_ids.length;
      showToast(
        `✅ Drafted ${total} item${total === 1 ? "" : "s"}` +
          `${newCount ? ` (${newCount} new)` : ""} — review before sending`
      );
    }
  } catch (err) {
    showBanner("Network error drafting the plan.");
  } finally {
    busy = false;
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;
  }
});

aiAddForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy) return;
  const text = aiAddTextEl.value.trim();
  if (!text) return;

  const submitBtn = aiAddForm.querySelector("button");
  const originalLabel = submitBtn.textContent;
  busy = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Thinking... (up to 1 min)";
  try {
    const res = await fetch("/api/boss/library/ai-add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, text }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not add that item.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
    selectedIds.add(data.selected_id);
    render(latestLibrary);
    aiAddTextEl.value = "";
    if (!data.ai_used) {
      showToast("Added as typed — AI wasn't available");
    } else if (data.was_new) {
      showToast("✅ Added a new item");
    } else {
      showToast("✅ Matched an existing item");
    }
  } catch (err) {
    showBanner("Network error adding the item.");
  } finally {
    busy = false;
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;
  }
});

addForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy) return;
  const text = addTextEl.value.trim();
  if (!text) return;
  const villa = addVillaEl.value.trim();
  const section = addSectionEl.value.trim();

  busy = true;
  try {
    const res = await fetch("/api/boss/library/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, villa, section, text }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not add that item.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
    selectedIds.add(data.added_id);
    render(latestLibrary);
    addTextEl.value = "";
    addSectionEl.value = "";
    addVillaEl.value = "";
  } catch (err) {
    showBanner("Network error adding the item.");
  } finally {
    busy = false;
  }
});

async function removeItem(itemId) {
  if (busy) return;
  busy = true;
  try {
    const res = await fetch("/api/boss/library/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_id: itemId }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not remove that item.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
  } catch (err) {
    showBanner("Network error removing the item.");
  } finally {
    busy = false;
  }
}

async function renameItem(itemId, currentText) {
  if (busy) return;
  const text = window.prompt("Change task name:", currentText);
  if (text === null) return;
  const trimmed = text.trim();
  if (!trimmed || trimmed === currentText) return;

  busy = true;
  try {
    const res = await fetch("/api/boss/library/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_id: itemId, text: trimmed }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not rename that item.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
  } catch (err) {
    showBanner("Network error renaming the item.");
  } finally {
    busy = false;
  }
}

async function sendPlan() {
  if (busy) return;
  busy = true;
  try {
    const notes = Object.fromEntries([...selectedNotes].map(([id, note]) => [String(id), note]));
    const res = await fetch("/api/boss/send-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_ids: [...selectedIds], notes, target: selectedTarget }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not send the plan.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
    const label = targetLabel(data.target);
    showToast(data.is_fresh ? `✅ ${label}'s plan sent — workers can see it now` : `✅ ${label}'s plan updated`);
  } catch (err) {
    showBanner("Network error sending the plan.");
  } finally {
    busy = false;
  }
}

sendNowBtn.addEventListener("click", () => sendPlan());

loadLibrary(true);
