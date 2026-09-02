const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const bannerEl = document.getElementById("banner");
const historyListEl = document.getElementById("history-list");

const viewerEl = document.getElementById("viewer");
const viewerContentEl = document.getElementById("viewer-content");
const viewerCloseEl = document.getElementById("viewer-close");
let viewerObjectUrl = null;

const initData = tg ? tg.initData : "";

function showBanner(text) {
  bannerEl.textContent = text;
  bannerEl.classList.remove("hidden");
}

function hideBanner() {
  bannerEl.classList.add("hidden");
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function loadHistoryList() {
  if (!initData) {
    showBanner("Open this from the archive button in Telegram.");
    return;
  }
  historyListEl.innerHTML = '<div class="item-meta">Loading...</div>';
  try {
    const res = await fetch("/api/boss/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      historyListEl.innerHTML = "";
      showBanner(body.detail || "Could not load the archive.");
      return;
    }
    const data = await res.json();
    hideBanner();
    renderHistoryList(data.plans);
  } catch (err) {
    historyListEl.innerHTML = "";
    showBanner("Network error loading the archive.");
  }
}

let expandedPlanId = null;

function renderHistoryList(plans) {
  historyListEl.innerHTML = "";
  if (plans.length === 0) {
    historyListEl.innerHTML = '<div class="item-meta">No plans sent yet.</div>';
    return;
  }
  for (const plan of plans) {
    const entry = document.createElement("div");
    entry.className = "history-entry";

    const row = document.createElement("div");
    row.className = "item";

    const body = document.createElement("div");
    body.className = "item-body";
    const text = document.createElement("div");
    text.className = "item-text";
    text.textContent = `${plan.date} at ${plan.time}${plan.current ? " (current)" : ""}`;
    body.appendChild(text);
    const meta = document.createElement("div");
    meta.className = "item-meta";
    meta.textContent = `${plan.done} / ${plan.total} finished`;
    body.appendChild(meta);
    row.appendChild(body);

    const detail = document.createElement("div");
    detail.className = "history-detail hidden";

    row.addEventListener("click", () => togglePlanDetail(plan, detail));

    entry.appendChild(row);
    entry.appendChild(detail);
    historyListEl.appendChild(entry);
  }
}

async function togglePlanDetail(plan, detailEl) {
  const isOpen = expandedPlanId === plan.id;

  for (const other of historyListEl.querySelectorAll(".history-detail")) {
    other.classList.add("hidden");
    other.innerHTML = "";
  }
  expandedPlanId = null;

  if (isOpen) return;

  expandedPlanId = plan.id;
  detailEl.classList.remove("hidden");
  detailEl.innerHTML = '<div class="item-meta">Loading...</div>';

  try {
    const res = await fetch("/api/boss/history/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, plan_id: plan.id }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      detailEl.innerHTML = "";
      showBanner(body.detail || "Could not load that plan.");
      return;
    }
    const data = await res.json();
    renderHistoryItems(data.items, detailEl);
  } catch (err) {
    detailEl.innerHTML = "";
    showBanner("Network error loading that plan.");
  }
}

function renderHistoryItems(items, container) {
  const villas = [];
  const byVilla = new Map();
  for (const item of items) {
    if (!byVilla.has(item.villa)) {
      byVilla.set(item.villa, []);
      villas.push(item.villa);
    }
    byVilla.get(item.villa).push(item);
  }

  container.innerHTML = "";
  for (const villa of villas) {
    const villaEl = document.createElement("div");
    villaEl.className = "villa";
    const villaTitle = document.createElement("div");
    villaTitle.className = "villa-title";
    villaTitle.textContent = `Villa ${villa}`;
    villaEl.appendChild(villaTitle);

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
        sectionEl.appendChild(renderHistoryItem(item));
      }
      villaEl.appendChild(sectionEl);
    }

    container.appendChild(villaEl);
  }
}

function renderHistoryItem(item) {
  const row = document.createElement("div");
  row.className = "item";
  if (item.done) row.classList.add("done");

  const box = document.createElement("div");
  box.className = "checkbox";
  box.textContent = item.done ? "✓" : "";
  row.appendChild(box);

  const body = document.createElement("div");
  body.className = "item-body";
  const text = document.createElement("div");
  text.className = "item-text";
  text.textContent = item.text;
  body.appendChild(text);
  if (item.done) {
    const meta = document.createElement("div");
    meta.className = "item-meta";
    const time = formatTime(item.done_at);
    meta.textContent = `Finished by ${item.done_by || "someone"}${time ? ` at ${time}` : ""}`;
    body.appendChild(meta);
  }
  row.appendChild(body);

  if (item.done) {
    const icon = document.createElement("button");
    icon.type = "button";
    icon.className = "media-icon";
    icon.textContent = item.media_type === "video" ? "🎬" : "📷";
    icon.setAttribute("aria-label", "View photo/video");
    icon.addEventListener("click", (e) => {
      e.stopPropagation();
      openViewer(item.id, item.media_type);
    });
    row.appendChild(icon);
  }

  return row;
}

async function openViewer(itemId, mediaType) {
  viewerContentEl.innerHTML = '<div class="viewer-message">Loading...</div>';
  viewerEl.classList.remove("hidden");

  try {
    const res = await fetch("/api/media", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData, item_id: itemId }),
    });
    if (!res.ok) {
      viewerContentEl.innerHTML = '<div class="viewer-message">Could not load this.</div>';
      return;
    }
    const blob = await res.blob();
    if (viewerObjectUrl) URL.revokeObjectURL(viewerObjectUrl);
    viewerObjectUrl = URL.createObjectURL(blob);

    viewerContentEl.innerHTML = "";
    if (mediaType === "video") {
      const video = document.createElement("video");
      video.src = viewerObjectUrl;
      video.controls = true;
      video.autoplay = true;
      viewerContentEl.appendChild(video);
    } else {
      const img = document.createElement("img");
      img.src = viewerObjectUrl;
      viewerContentEl.appendChild(img);
    }
  } catch (err) {
    viewerContentEl.innerHTML = '<div class="viewer-message">Network error loading this.</div>';
  }
}

function closeViewer() {
  viewerEl.classList.add("hidden");
  viewerContentEl.innerHTML = "";
  if (viewerObjectUrl) {
    URL.revokeObjectURL(viewerObjectUrl);
    viewerObjectUrl = null;
  }
}

viewerEl.addEventListener("click", closeViewer);
viewerContentEl.addEventListener("click", (e) => e.stopPropagation());
viewerCloseEl.addEventListener("click", (e) => {
  e.stopPropagation();
  closeViewer();
});

loadHistoryList();
