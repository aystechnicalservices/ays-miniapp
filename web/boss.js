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
  row.appendChild(body);

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

function selectionForTarget(data, target) {
  const ids = target === "tomorrow" ? data.tomorrow_active_ids : data.today_active_ids;
  return new Set(ids);
}

function applyBossState(data, resetSelection) {
  latestBossState = data;
  if (resetSelection) {
    selectedIds = selectionForTarget(data, selectedTarget);
  } else {
    const validIds = new Set(data.library.map((i) => i.id));
    selectedIds = new Set([...selectedIds].filter((id) => validIds.has(id)));
  }
  updateHeading();
  render(data.library);
}

headingEl.addEventListener("click", () => {
  if (!latestBossState) return;
  selectedTarget = selectedTarget === "today" ? "tomorrow" : "today";
  selectedIds = selectionForTarget(latestBossState, selectedTarget);
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

async function sendPlan() {
  if (busy) return;
  busy = true;
  try {
    const res = await fetch("/api/boss/send-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_ids: [...selectedIds], target: selectedTarget }),
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
