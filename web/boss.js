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
const sendRowEl = document.getElementById("send-row");
const sendNowBtn = document.getElementById("send-now-btn");
const scheduleOpenBtn = document.getElementById("schedule-open-btn");
const schedulePickerEl = document.getElementById("schedule-picker");
const scheduleHourEl = document.getElementById("schedule-hour");
const scheduleMinuteEl = document.getElementById("schedule-minute");
const scheduleConfirmBtn = document.getElementById("schedule-confirm-btn");
const scheduleBackBtn = document.getElementById("schedule-back-btn");
const scheduleStatusEl = document.getElementById("schedule-status");
const scheduleStatusTextEl = document.getElementById("schedule-status-text");
const scheduleCancelBtn = document.getElementById("schedule-cancel-btn");

const initData = tg ? tg.initData : "";

let selectedIds = new Set();
let latestLibrary = [];
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

function renderScheduleStatus(pending) {
  if (!pending) {
    scheduleStatusEl.classList.add("hidden");
    return;
  }
  scheduleStatusTextEl.textContent = `Scheduled for ${pending.time} on ${pending.date}`;
  scheduleStatusEl.classList.remove("hidden");
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

function updateHeading(planDate) {
  headingEl.textContent = planDate ? `Work Plan ${planDate}` : "Library";
}

function applyBossState(data, resetSelection) {
  if (resetSelection) {
    selectedIds = new Set(data.library.filter((i) => i.active).map((i) => i.id));
  } else {
    const validIds = new Set(data.library.map((i) => i.id));
    selectedIds = new Set([...selectedIds].filter((id) => validIds.has(id)));
  }
  updateHeading(data.plan_date);
  renderScheduleStatus(data.pending_schedule);

  render(data.library);
}

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

async function sendPlan(sendAt) {
  if (busy) return;
  if (selectedIds.size === 0) {
    showBanner("Select at least one item first.");
    return;
  }
  busy = true;
  try {
    const res = await fetch("/api/boss/send-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_ids: [...selectedIds], send_at: sendAt || null }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not send the plan.");
      return;
    }
    const data = await res.json();
    hideBanner();
    applyBossState(data, false);
    showToast(sendAt ? `✅ Plan scheduled for ${sendAt}` : "✅ Plan sent — workers can see it now");
  } catch (err) {
    showBanner("Network error sending the plan.");
  } finally {
    busy = false;
  }
}

function populateTimeSelects() {
  for (let h = 0; h < 24; h++) {
    const opt = document.createElement("option");
    opt.value = String(h).padStart(2, "0");
    opt.textContent = String(h).padStart(2, "0");
    scheduleHourEl.appendChild(opt);
  }
  for (let m = 0; m < 60; m++) {
    const opt = document.createElement("option");
    opt.value = String(m).padStart(2, "0");
    opt.textContent = String(m).padStart(2, "0");
    scheduleMinuteEl.appendChild(opt);
  }
  const now = new Date();
  scheduleHourEl.value = String(now.getHours()).padStart(2, "0");
  scheduleMinuteEl.value = String(now.getMinutes()).padStart(2, "0");
}
populateTimeSelects();

function openSchedulePicker() {
  sendRowEl.classList.add("hidden");
  schedulePickerEl.classList.remove("hidden");
}

function closeSchedulePicker() {
  schedulePickerEl.classList.add("hidden");
  sendRowEl.classList.remove("hidden");
}

sendNowBtn.addEventListener("click", () => sendPlan(null));
scheduleOpenBtn.addEventListener("click", openSchedulePicker);
scheduleBackBtn.addEventListener("click", closeSchedulePicker);
scheduleConfirmBtn.addEventListener("click", () => {
  const sendAt = `${scheduleHourEl.value}:${scheduleMinuteEl.value}`;
  sendPlan(sendAt);
  closeSchedulePicker();
});

scheduleCancelBtn.addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  try {
    const res = await fetch("/api/boss/cancel-schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not cancel the schedule.");
      return;
    }
    const data = await res.json();
    hideBanner();
    renderScheduleStatus(data.pending_schedule);
  } catch (err) {
    showBanner("Network error cancelling the schedule.");
  } finally {
    busy = false;
  }
});

loadLibrary(true);
