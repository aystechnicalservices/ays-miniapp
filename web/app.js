const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const headingEl = document.getElementById("heading");
const listEl = document.getElementById("list");
const progressEl = document.getElementById("progress");
const bannerEl = document.getElementById("banner");
const fileInput = document.getElementById("file-input");
const cameraViewEl = document.getElementById("camera-view");
const cameraVideoEl = document.getElementById("camera-video");
const cameraCanvasEl = document.getElementById("camera-canvas");
const cameraShutterBtn = document.getElementById("camera-shutter-btn");
const cameraCancelBtn = document.getElementById("camera-cancel-btn");
const cameraVideoBtn = document.getElementById("camera-video-btn");
const viewerEl = document.getElementById("viewer");
const viewerContentEl = document.getElementById("viewer-content");
const viewerCloseEl = document.getElementById("viewer-close");

const initData = tg ? tg.initData : "";
const POLL_MS = 4000;
let viewerObjectUrl = null;

let uploadingItemId = null;
let uploadPercent = 0;
let pendingPickItemId = null;
let latestData = null;
let cameraStream = null;

function showBanner(text, allDone) {
  bannerEl.textContent = text;
  bannerEl.classList.remove("hidden");
  bannerEl.classList.toggle("all-done", !!allDone);
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

function render(data) {
  latestData = data;
  const items = data.items;
  const doneCount = items.filter((i) => i.done).length;
  progressEl.textContent = `${doneCount} / ${items.length} finished`;

  const heading = data.plan_date ? `Work Plan ${data.plan_date}` : "Work Plan";
  headingEl.textContent = heading;
  document.title = heading;

  if (data.all_done) {
    showBanner("All items finished. Nice work!", true);
  } else {
    hideBanner();
  }

  const villas = [];
  const byVilla = new Map();
  for (const item of items) {
    if (!byVilla.has(item.villa)) {
      byVilla.set(item.villa, []);
      villas.push(item.villa);
    }
    byVilla.get(item.villa).push(item);
  }

  listEl.innerHTML = "";
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
        sectionEl.appendChild(renderItem(item));
      }
      villaEl.appendChild(sectionEl);
    }

    listEl.appendChild(villaEl);
  }
}

function renderItem(item) {
  const row = document.createElement("div");
  row.className = "item";
  const isUploading = item.id === uploadingItemId;
  if (item.done) row.classList.add("done");
  if (isUploading) row.classList.add("uploading");

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
  } else if (isUploading) {
    const meta = document.createElement("div");
    meta.className = "item-meta";
    meta.textContent =
      uploadPercent > 0 && uploadPercent < 100
        ? `Sending... ${uploadPercent}%`
        : "Sending...";
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
  } else if (!isUploading) {
    row.addEventListener("click", () => startAttach(item.id));
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

// iOS maps <input capture> straight to the camera, with no permission
// prompt — so leave it alone there. Only Android needs the getUserMedia
// path, because Telegram's Android WebView ignores `capture` and opens
// the gallery instead (Telegram bug #681; getUserMedia is their own
// recommended workaround).
const useInAppCamera =
  tg &&
  tg.platform === "android" &&
  navigator.mediaDevices &&
  navigator.mediaDevices.getUserMedia;

async function startAttach(itemId) {
  if (uploadingItemId) return;
  pendingPickItemId = itemId;

  if (!useInAppCamera) {
    openFilePicker("image/*,video/*");
    return;
  }

  // Order matters: the video element must be laid out and visible BEFORE
  // srcObject is assigned, and play() has to be called explicitly —
  // attaching a stream to a hidden element and relying on autoplay is
  // what renders a black preview in this WebView.
  cameraViewEl.classList.remove("hidden");

  // Reuse an existing stream where possible: re-requesting re-prompts for
  // permission every time, since this WebView doesn't persist the grant
  // (Telegram Android bug — see README). Android may still have ended the
  // track behind our back while the app was backgrounded, so check it's
  // actually alive rather than trusting the reference.
  if (cameraStream && !cameraStream.getVideoTracks().some((t) => t.readyState === "live")) {
    cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
  }

  if (!cameraStream) {
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
    } catch (err) {
      // No camera, or permission refused — fall back to the OS picker.
      cameraViewEl.classList.add("hidden");
      openFilePicker("image/*,video/*");
      return;
    }
  }

  cameraVideoEl.srcObject = cameraStream;
  try {
    await cameraVideoEl.play();
  } catch (err) {
    // Some WebViews reject the promise but still start playing; the
    // preview is already visible either way, so carry on.
  }
}

function openFilePicker(accept) {
  fileInput.setAttribute("accept", accept);
  fileInput.value = "";
  fileInput.click();
}

// Hide the camera but keep the stream, so the next photo in this visit
// opens instantly and without another permission prompt.
function closeCameraView() {
  cameraViewEl.classList.add("hidden");
}

// Actually release the hardware — on leaving the app, or when switching
// to the OS picker for a video.
function releaseCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((t) => t.stop());
    cameraStream = null;
  }
  cameraVideoEl.srcObject = null;
  cameraViewEl.classList.add("hidden");
}

// Deliberately NOT released on visibilitychange: Telegram's Android client
// re-prompts for permission on every getUserMedia call, so dropping the
// stream when the user briefly switches apps means a fresh prompt when they
// come back. Held until the page actually goes away instead. If the camera
// view is still open on return, the preview needs nudging back to life.
document.addEventListener("visibilitychange", () => {
  if (document.hidden || cameraViewEl.classList.contains("hidden")) return;
  if (cameraStream && cameraStream.getVideoTracks().some((t) => t.readyState === "live")) {
    cameraVideoEl.play().catch(() => {});
  }
});
window.addEventListener("pagehide", releaseCamera);

cameraCancelBtn.addEventListener("click", () => {
  if (mediaRecorder) {
    discardRecording = true;
    stopRecording();
    return;
  }
  closeCameraView();
  pendingPickItemId = null;
});

// In-page video recording, from the stream that's already open. Telegram's
// player wants MP4, so prefer it and only fall back to WebM; the backend
// falls back to sending as a document if Telegram rejects the format.
// Capped in length and bitrate to stay under Telegram's 20 MB *download*
// limit, or the finished video couldn't be replayed in the app.
// 45s at 1.2 Mbps lands around 7 MB — small enough to upload over a phone
// connection without a long wait, and well inside Telegram's 20 MB limit
// for downloading it back for playback.
const MAX_RECORD_SECONDS = 45;
const VIDEO_BITS_PER_SECOND = 1200000;
let mediaRecorder = null;
let recordedChunks = [];
let recordAudioStream = null;
let recordTicker = null;
let recordSeconds = 0;
let discardRecording = false;

function pickVideoMimeType() {
  const candidates = [
    "video/mp4;codecs=avc1.42E01E,mp4a.40.2",
    "video/mp4;codecs=avc1",
    "video/mp4",
    "video/webm;codecs=vp8,opus",
    "video/webm",
  ];
  for (const type of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

async function startRecording() {
  if (!cameraStream || !window.MediaRecorder) return;

  // Drop the track to 720p/24fps while recording. videoBitsPerSecond is only
  // a hint and gets overshot badly at 1080p (a 60s clip came out 24 MB against
  // a 15 MB budget, past Telegram's 20 MB playback limit), so constrain the
  // source too rather than trusting the encoder to behave. Photos still use
  // the full-resolution track — this is reverted when recording ends.
  const videoTrack = cameraStream.getVideoTracks()[0];
  if (videoTrack) {
    try {
      await videoTrack.applyConstraints({
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 24 },
      });
    } catch (err) {
      // Constraints unsupported — recording still works, just larger.
    }
  }

  // Mic is requested only now, so photo-only users never see a mic prompt.
  // Recording silently is better than not recording at all if it's denied.
  recordAudioStream = null;
  try {
    recordAudioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    // No mic access — carry on with a silent video.
  }

  const tracks = [
    ...cameraStream.getVideoTracks(),
    ...(recordAudioStream ? recordAudioStream.getAudioTracks() : []),
  ];
  const mimeType = pickVideoMimeType();
  try {
    mediaRecorder = new MediaRecorder(new MediaStream(tracks), {
      ...(mimeType ? { mimeType } : {}),
      videoBitsPerSecond: VIDEO_BITS_PER_SECOND,
      audioBitsPerSecond: 64000,
    });
  } catch (err) {
    stopAudioStream();
    showBanner("Can't record video on this device. Take a photo instead.");
    return;
  }

  recordedChunks = [];
  discardRecording = false;
  mediaRecorder.addEventListener("dataavailable", (e) => {
    if (e.data && e.data.size) recordedChunks.push(e.data);
  });
  mediaRecorder.addEventListener("stop", finishRecording);
  mediaRecorder.start();

  recordSeconds = 0;
  cameraViewEl.classList.add("recording");
  updateRecordLabel();
  recordTicker = setInterval(() => {
    recordSeconds += 1;
    updateRecordLabel();
    if (recordSeconds >= MAX_RECORD_SECONDS) stopRecording();
  }, 1000);
}

function updateRecordLabel() {
  const remaining = MAX_RECORD_SECONDS - recordSeconds;
  cameraVideoBtn.textContent = `Stop ${remaining}s`;
}

function stopRecording() {
  if (!mediaRecorder) return;
  if (recordTicker) {
    clearInterval(recordTicker);
    recordTicker = null;
  }
  if (mediaRecorder.state !== "inactive") mediaRecorder.stop();
}

function stopAudioStream() {
  if (recordAudioStream) {
    recordAudioStream.getTracks().forEach((t) => t.stop());
    recordAudioStream = null;
  }
}

// Telegram will accept an upload up to 50 MB but only ever hand back 20 MB,
// so anything above that uploads slowly and then can't be played. Refuse it
// up front rather than after a long wait.
const MAX_VIDEO_BYTES = 19 * 1024 * 1024;

function finishRecording() {
  const itemId = pendingPickItemId;
  const type = mediaRecorder.mimeType || "video/mp4";
  const chunks = recordedChunks;
  const discarded = discardRecording;

  mediaRecorder = null;
  recordedChunks = [];
  stopAudioStream();
  cameraViewEl.classList.remove("recording");
  cameraVideoBtn.textContent = "Video";
  closeCameraView();
  pendingPickItemId = null;

  // Put the track back to full resolution for photos.
  const videoTrack = cameraStream && cameraStream.getVideoTracks()[0];
  if (videoTrack) {
    videoTrack
      .applyConstraints({ width: { ideal: 1920 }, height: { ideal: 1080 } })
      .catch(() => {});
  }

  if (discarded || !chunks.length || !itemId) return;
  const blob = new Blob(chunks, { type });
  if (blob.size > MAX_VIDEO_BYTES) {
    const mb = (blob.size / 1024 / 1024).toFixed(1);
    showBanner(`That video is too big to send (${mb} MB). Record a shorter one.`);
    return;
  }
  const ext = type.includes("mp4") ? "mp4" : "webm";
  uploadAndAttach(itemId, new File([blob], `video.${ext}`, { type }));
}

cameraVideoBtn.addEventListener("click", () => {
  if (mediaRecorder) {
    stopRecording();
  } else {
    startRecording();
  }
});

// Fire on touch-down, not click: `click` only lands on release, and this
// WebView drops quick tap/release pairs — which made the shutter feel
// like it needed holding down.
let capturing = false;

function capturePhoto() {
  const itemId = pendingPickItemId;
  if (capturing || !itemId || !cameraVideoEl.videoWidth) return;
  capturing = true;

  cameraCanvasEl.width = cameraVideoEl.videoWidth;
  cameraCanvasEl.height = cameraVideoEl.videoHeight;
  cameraCanvasEl.getContext("2d").drawImage(cameraVideoEl, 0, 0);
  cameraCanvasEl.toBlob(
    (blob) => {
      capturing = false;
      closeCameraView();
      pendingPickItemId = null;
      if (!blob) return;
      uploadAndAttach(itemId, new File([blob], "photo.jpg", { type: "image/jpeg" }));
    },
    "image/jpeg",
    0.9
  );
}

cameraShutterBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  capturePhoto();
});
// Fallback for anything that doesn't deliver pointer events; `capturing`
// keeps the two paths from double-firing.
cameraShutterBtn.addEventListener("click", capturePhoto);

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  const itemId = pendingPickItemId;
  pendingPickItemId = null;
  if (!file || !itemId) return;
  uploadAndAttach(itemId, file);
});

async function uploadAndAttach(itemId, file) {
  uploadingItemId = itemId;
  uploadPercent = 0;
  if (latestData) render(latestData);
  hideBanner();

  const form = new FormData();
  form.append("init_data", initData);
  form.append("item_id", String(itemId));
  form.append("file", file);

  try {
    const data = await postWithProgress("/api/attach", form, (percent) => {
      // A video takes a while: the file crosses the network twice (phone to
      // this server, then this server to Telegram), so show real progress
      // rather than a "Sending..." that looks stuck.
      uploadPercent = percent;
      if (latestData) render(latestData);
    });
    uploadingItemId = null;
    render(data);
  } catch (err) {
    showBanner(err.message || "Network error sending the photo/video. Try again.");
  } finally {
    uploadingItemId = null;
    uploadPercent = 0;
  }
}

// fetch() can't report upload progress; XHR can.
function postWithProgress(url, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });
    xhr.addEventListener("load", () => {
      let body = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch (err) {
        // Non-JSON response — fall through to the generic error below.
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.detail || "Could not send that. Try again."));
    });
    xhr.addEventListener("error", () => reject(new Error("Network error. Try again.")));
    xhr.addEventListener("timeout", () => reject(new Error("That took too long. Try again.")));
    xhr.timeout = 300000;
    xhr.send(form);
  });
}

async function loadChecklist() {
  if (!initData) {
    showBanner("Open this from the checklist button in Telegram.");
    return;
  }
  try {
    const res = await fetch("/api/checklist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      showBanner(body.detail || "Could not load the checklist.");
      return;
    }
    const data = await res.json();
    render(data);
  } catch (err) {
    showBanner("Network error loading the checklist.");
  }
}

// Telegram's blue menu button points at one fixed URL for the whole bot, so
// send bosses on to the library from here. `?checklist=1` opts out, which is
// what /start's "Open checklist" button uses so a boss can still get here.
async function routeBossToLibrary() {
  if (!initData || new URLSearchParams(location.search).has("checklist")) return false;
  try {
    const res = await fetch("/api/whoami", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
    });
    if (!res.ok) return false;
    if ((await res.json()).is_boss) {
      location.replace("/boss");
      return true;
    }
  } catch (err) {
    // Can't tell — just show the checklist.
  }
  return false;
}

(async () => {
  if (await routeBossToLibrary()) return;
  loadChecklist();
  setInterval(() => {
    if (!uploadingItemId) loadChecklist();
  }, POLL_MS);
})();
