# AYS Checklist — Telegram Mini App + Backend — Build Spec (v1)

Build from scratch. Do NOT import or merge any old codebase. This spec is
complete; when a detail isn't stated, pick the simplest option consistent with
everything here and note the assumption in code.

**Tone:** plain, simple English everywhere. Short labels, no jargon, no invented
numbers shown to any user.

**Build in THIN SLICES** (section 9). Get each slice working and testable before
starting the next. Do not build all slices at once.

---

## 1. What this is

A Telegram **Mini App** (a fixed-screen web UI opened inside Telegram) backed by
a small Python server. It replaces a chat-message checklist that got confusing
when the feed flooded with photos and bot replies. The Mini App gives a fixed
checklist screen that updates in place.

Core idea: the **boss** assembles tomorrow's work plan by tapping items from a
reusable **library**, sends it to the **foreman**, and the **crew** works off a
shared checklist, ticking items and attaching a photo/video for each.

---

## 2. Roles (v1)

- **Boss** — maintains a library of reusable task items; assembles each day's
  plan by tapping items (plus an "add new item" button that saves a new item to
  the library and adds it to the plan); sends the assembled plan to the foreman.
  Receives live photos/videos and a final report.
- **Foreman** — receives the assembled plan. In v1 the foreman assigns work
  **verbally on-site** (NOT in the app). Oversees; sends interim/final reports
  manually for now. (The fixed "Yadvinder's Responsibility" text is shown as
  reference, not tickable.)
- **Worker (crew)** — sees the shared checklist for the day, ticks items, sends a
  photo or video per item.

Roles are by Telegram user ID (in `.env` or a small table). Unrecognized users
are ignored (reply only with their Telegram ID so they can be added).

**Deferred (do NOT build in v1, but leave room in the data model):** in-app
per-worker assignment (foreman taps each item to a specific worker; named owner;
accountability for un-done items).

---

## 3. The library (boss's block-builder)

- A growing set of **reusable task items** the boss has written.
- Each item is short text (e.g. "vacuum the swimming pool"). Optionally grouped
  under a section/villa header.
- Boss actions: **Add new item** (saves to library), **remove item**, and
  **assemble tomorrow's plan** by tapping items to include them.
- The library persists; assembling a plan is just selecting a subset (+ any new
  items added on the spot).

---

## 4. The daily plan & shared checklist

- The boss assembles a plan (a selected list of items) and **sends it** (to the
  foreman; workers receive the shared checklist).
- Workers open the Mini App → see the day's checklist as a **single fixed screen**
  with tickable items, grouped under their headers, with the fixed
  "Yadvinder's Responsibility" reference text at the bottom (not tickable).
- **One shared checklist** for the crew. Ticking an item → prompt for a **photo
  or video** (either accepted) → once received, item shows done (✅) and records
  **who** ticked it + their media + timestamp.
- The screen reflects **shared state** — if one worker ticks an item, others see
  it done when they open/refresh.
- The **day is complete** when every item is ✅.

---

## 5. What the boss receives

- **Live:** each photo/video forwarded to the boss as it arrives, labelled with
  the item and who sent it.
- **Final report** when all items done: each item, who did it, timestamp, and its
  media. Plain English, readable top to bottom.

---

## 6. Architecture

- **One Python backend** that:
  - runs the Telegram bot (auth, buttons, sending plans, receiving photos),
  - serves the Mini App web page over HTTPS,
  - exposes a small API the Mini App calls (get today's checklist, tick an item,
    attach media),
  - stores data.
- **Mini App front-end:** a single HTML/CSS/JS page using Telegram's
  `telegram-web-app.js` (theme + user context). It calls the backend for all
  data; it holds NO secrets and NO API keys.
- **Security:** verify the Mini App's Telegram initData signature on the backend
  so you can trust which Telegram user is calling. Never trust the client blindly.
- **Storage:** SQLite is fine and simplest (library items, daily plans, tick
  state, media file_ids, who/when). Media = Telegram file_id references, don't
  store bytes.

No user-facing IDs/numbers ever shown.

---

## 7. Config (.env)

- BOT_TOKEN
- BOSS_ID
- FOREMAN_ID
- CREW_IDS (comma-separated) or a small recognized-users table
- TIMEZONE (default Asia/Dubai)
- Daily send time (boss-set; sensible default)
- WEBHOOK_URL / host / port for the web service (see hosting)

Read via python-dotenv (load_dotenv() at startup). `.env.example` provided.
Never print/commit secrets.

---

## 8. Hosting (staged)

The Mini App needs a public HTTPS URL, so hosting matters:

- **PC (dev/testing):** run the backend locally; expose the Mini App via a
  temporary HTTPS tunnel (e.g. ngrok) for testing in Telegram. Register that URL
  with BotFather (`/newapp` or Menu Button → Web App).
- **Phone (Termux):** the bot part runs fine on the phone (proven). The Mini App
  page still needs a public HTTPS URL — a tunnel works for light use but is
  fragile; note this.
- **Render (recommended for real use):** a free/cheap web service serves both the
  backend and the Mini App over HTTPS. Scheduled daily send can run as a **Render
  Cron Job** (fires regardless of sleep) — the clean way to schedule. A wake
  ping (from the phone or a free uptime pinger) can keep the free service warm if
  needed. Keep everything host-portable: read host/port/webhook from `.env`.

Default to polling for the bot when no webhook is set; support webhook mode for a
host.

---

## 9. Build order — THIN SLICES (test each before the next)

1. **Worker shared checklist, backed.** One hardcoded plan in the backend. Worker
   opens the Mini App, sees the checklist, ticks an item → sends photo/video →
   item marks done + attributed → boss gets the photo. Proves backend + Mini App
   + media loop end to end.
2. **Boss library + block-builder.** Boss view: add item (→ library), assemble a
   plan by tapping items, send it → that becomes what workers see.
3. **Foreman in the loop.** Plan routes boss → foreman → workers. Foreman sees the
   plan (assigns verbally in v1). Fixed responsibility text shown.
4. **Scheduling.** "Send this plan for tomorrow at 7am" instead of immediately.
   On Render, use a Cron Job.
5. **Later (not v1):** in-app per-worker assignment; then AI features (Gemini via
   backend: draft a plan, pool-chemical dosing from test results, summarize the
   day). Front-end → backend → Gemini; key server-side only.

---

## 10. Deployment target note

Build/test on a PC. Bot can later run on Android/Termux (polling; keep
`termux-wake-lock` + battery settings). Mini App needs public HTTPS (tunnel for
test, Render for real). tzdata required if running under Termux (Android lacks
system timezone DB). Keep dependencies light. No Windows-only launchers.

---

## 11. Seed content (from operator) — example items for the library

Villa 908 items (Full Area Cleaning): blow the entire yard; remove leaves and
plant debris; clean the areas under the bushes; remove rubbish from corners and
hard-to-reach areas; collect and dispose of all rubbish.
Washing: wash the main entrance; wash dirty pathways; clean the area around the
swimming pool; wash the BBQ area and the work surface.
Swimming Pool: vacuum the swimming pool; brush the pool walls and floor; test the
pool water and send the results; remove debris from the water surface; clean and
arrange the area around the swimming pool.
Plant Trimming: trim bushes that have lost their shape; level the edges of the
plants; remove unnecessary and protruding branches; tidy the bonsai garden;
remove weeds.
Inspection: inspect the entrance area; inspect the BBQ area; check lights, covers,
grilles, and visible damage; check for dry, damaged, or dying plants.
Final Cleaning: blow the entire area again; remove all tools and materials; make
sure the pathways and entrance are clean; record and send a final video overview.

Fixed footer text (not tickable) — "Yadvinder's Responsibility": distribute the
work among the employees; check that all required tools are available before
departure; control the quality of all work; ensure that no regular task is
missed; send an interim report; send the final photo and video report;
separately state what was not completed and why.
