# AYS Checklist — Slices 1–2

See `spec.md` section 9. So far:

- **Slice 1** — worker checklist Mini App: tick + photo/video → item marked
  done → boss gets the media.
- **Slice 2** — boss library + block-builder: a **Library** view (boss only)
  to add/remove reusable items and assemble+send a plan, which becomes what
  workers see. No foreman routing or scheduling yet.

## What's here

- `app/` — the Python backend (FastAPI web API + serves both Mini App pages,
  plus the Telegram bot running in polling mode in the same process).
- `web/` — three plain HTML/CSS/JS Mini App pages, all using
  `telegram-web-app.js`: `index.html`/`app.js` (worker checklist, `/`),
  `boss.html`/`boss.js` (library/block-builder, `/boss`), and
  `archive.html`/`archive.js` (past plans, `/archive`).
- `ays.db` — SQLite file, created automatically on first run.

## Access control

Only Telegram IDs in `BOSS_ID` + `EXTRA_BOSS_IDS` + `CREW_IDS` (together,
`ALLOWED_IDS`) can use the bot or the Mini App at all — everyone else gets
"You're not registered yet. Your Telegram ID is `<id>`." on `/start` and on
every API call, so the admin can copy that ID straight into `.env`. Within
that, "boss" is specifically `BOSS_ID` + `EXTRA_BOSS_IDS` — checked again on
every `/api/boss/...` call — which is what gates **Open library**/**Open
archive** and their APIs. `/start` gives bosses all three buttons (Open
checklist / Open library / Open archive); everyone else only gets Open
checklist. None of the three pages link to each other — `/start` is the only
way to switch between them, by design (there's no in-app "Library" or
"Archive" button on the checklist, etc.).

Telegram's blue Menu Button is a single fixed URL for the whole bot, so it
can't point somewhere different per role. `/` handles that itself: on load
it asks `/api/whoami` and sends bosses on to `/boss`, so the blue button
lands bosses in the library and everyone else on the checklist. Adding
`?checklist=1` opts out of that redirect — which is why `/start`'s "Open
checklist" button and the "plan sent" confirmation both use it, so a boss
can still reach the checklist.

## Villas

Every library item is tagged with a **villa** (a short label like `908` or
`1002`), in addition to its section. The boss's add-item form has a Villa
field (autocompletes from villas already in use; defaults to `908` if left
blank), and both the library and the worker checklist group items by villa
first, then section within each villa — so a plan can freely mix items from
several villas and everyone still sees them clearly separated.

## Sending a plan: now or scheduled

The **Send** row in the library has a time picker plus **Send now** /
**Schedule** buttons. Scheduling parses the time as HH:MM in `TIMEZONE`; if
that time has already passed today it's scheduled for tomorrow instead. Only
one scheduled send is kept at a time — scheduling a new one (or sending now)
replaces/cancels whatever was pending, and there's a **Cancel** control shown
while one is pending. This is a simple in-process `asyncio` timer, not a
persisted job: **if the server restarts, a pending scheduled send is lost**
(the real "clean" scheduling — a Render Cron Job — is spec section 9's
slice 4, not built yet).

Whenever a plan actually goes out (immediately or once a schedule fires):
- everyone in `CREW_IDS` gets **"WORK PLAN FOR DD/MM/YYYY"** with a **WORK**
  button that opens the checklist Mini App;
- every boss (`BOSS_ID` + `EXTRA_BOSS_IDS`) gets a confirmation too —
  **"Work Plan DD/MM/YYYY"** with an **Open checklist** button;
- the library itself shows a "✅ Plan sent / Plan scheduled" confirmation
  toast, not just the small status box.

`CREW_IDS` is empty by default — until you fill it in, plans still send
correctly, they just don't proactively notify anyone (workers can still
open the checklist manually any time).

Separately, the moment every item on the live plan is finished, each ID in
`BOSS_ID` + `EXTRA_BOSS_IDS` gets a plain "All tasks for DD/MM/YYYY are
finished." message.

## Editing today's plan vs. starting a new one

Two different actions, and the distinction matters:

- **Update today** (`/api/boss/update-plan` → `db.update_plan()`) edits the
  plan that's already live. Items still on it keep their tick, photo,
  timestamp and who-did-it; only newly selected items are added and
  deselected *unfinished* items removed. **A finished item is never removed
  even if deselected** — that would throw away the photo and the record of
  who did the work — so those are kept and reported back as `kept_finished`
  for the UI to mention. No new archive entry, and the plan's date is
  unchanged.
- **New plan / Schedule** (`db.send_plan()`) starts a fresh generation and
  everything reverts to unfinished. Right first thing in the morning;
  destructive mid-day, so the button is styled as secondary and asks for
  confirmation once anything is finished.

The button only appears once a plan is actually live (`plan_total > 0`).

## Archive — what happens to past plans

Sending a new plan does **not** delete the old one. Every "send" creates a
new row in the `plans` table; each plan's items and their tick/finished
state stay in `plan_items`/`item_state` tied to that row forever. Only the
most recent plan is "current" — that's what the worker checklist shows, what
the library highlights as active, and what blocks a library item from being
deleted.

**Where the data actually lives, and limits:** `ays.db` (SQLite, plain text
+ numbers only — item text, timestamps, names, `file_id`s) holds everything
except the media itself; at this scale it has no meaningful size limit.
Photos/videos live on **Telegram's servers**, in the `STORAGE_CHAT_ID`
channel — `ays.db` only stores a reference (`file_id`) to each one.
Telegram keeps channel media indefinitely (no storage quota for normal use)
as long as the channel exists, the bot stays admin, and the message isn't
deleted — but delete the channel or remove the bot and every `file_id` in it
breaks. Two real Bot API limits worth knowing: **uploading** a photo/video
via the bot is capped at **50 MB**; **downloading** one back out (which is
what viewing it in the checklist/archive does) is capped at **20 MB** — a
video over that will still send fine but won't be viewable through the app
afterward. If large videos become common, that 20 MB download cap is the
one to watch.

Browse it at `/archive` — reachable **only** via `/start`'s **Open archive**
button (deliberately not linked from the checklist or library pages, so it
stays a distinct destination rather than something bolted onto the other
two). It's a list of every past plan (date, time, X/Y finished, marked if
it's the current one). Tap one to see its items read-only, grouped by
villa/section, with who finished each and when — tap the 📷/🎬 icon to view
the actual photo/video, same as the live checklist.

## How the media loop works

Tapping an unfinished item opens the camera. **How** depends on the
platform, routed on `tg.platform` in [`web/app.js`](web/app.js):

- **iOS / desktop** — a hidden
  `<input type="file" accept="image/*,video/*" capture="environment">`.
  iOS maps `capture` straight to the camera, so this is native and needs
  no permission prompt at all.
- **Android** — an in-page camera via `getUserMedia`, drawn to a
  `<canvas>` on capture. Necessary because Telegram's Android WebView
  ignores `capture` and opens the gallery instead — a
  [known, unresolved Telegram bug](https://github.com/Telegram-Mini-Apps/telegram-apps/issues/681);
  `getUserMedia` is Telegram's own recommended workaround for it. The
  **Video** button records in-page with `MediaRecorder` from the same
  stream (the OS picker was no use here — it hits the identical `capture`
  bug and just opens the gallery).

Video recording specifics: it prefers MP4/H.264 (`pickVideoMimeType()`) and
only falls back to WebM, because Telegram's player wants MP4. The mic is
requested only when recording actually starts, so photo-only users never
see a microphone prompt; if it's denied the video is recorded silently
rather than not at all.

**Keeping video under Telegram's 20 MB playback ceiling takes three
separate measures, because any one alone isn't enough:** a 45s duration
cap, a 1.2 Mbps bitrate hint, *and* dropping the track to 720p/24fps for
the duration of the recording (restored to 1080p afterwards, so photos stay
full resolution). The resolution constraint matters because
`videoBitsPerSecond` is only a hint that encoders overshoot — a 60s clip at
a 2 Mbps hint came out at **24.3 MB**, over a 15 MB budget and past the
point Telegram will hand it back for playback. `finishRecording()` also
rejects anything over 19 MB outright, so an oversized clip fails instantly
instead of after a long upload.

**python-telegram-bot's default timeouts are ~5 seconds, which is nowhere
near enough to upload a video.** `build_application()` raises them to 300s.
Before that, a 60s clip produced a confusing failure: the upload actually
*succeeded* on Telegram's side, but timed out locally, so the app reported
"could not send", left the item unfinished, and the document fallback
uploaded the same file a second time — two copies in the channel for one
recording. `api_attach` now also refuses to retry after a `TimedOut`
specifically, since the file has probably landed already.

**Four things about the Android path are load-bearing — each fixed a real
bug found on actual Galaxy devices. Don't "simplify" them away:**

1. **Reveal the `<video>` element before assigning `srcObject`, and call
   `play()` explicitly.** Attaching a stream to a `display:none` element
   and relying on `autoplay` renders a permanently black preview. This
   was the single cause of the black screen, and it masqueraded for a
   long time as "Android just can't do this" — an earlier workaround did
   a full `location.reload()` to shake it loose, which worked but forced
   a permission prompt on every open.
2. **Keep the stream alive between shots** (`closeCameraView()` hides the
   UI; only `releaseCamera()` stops tracks). Stopping tracks after each
   photo makes the next tap re-request the camera, and this WebView
   re-prompts for permission every time it does.
3. **Fire the shutter on `pointerdown`, not `click`.** `click` only lands
   on release and this WebView drops quick tap/release pairs, so the
   shutter appeared to require holding it down. `touch-action:
   manipulation` on the button matters too (kills the double-tap-zoom
   delay).
4. **Do *not* release the camera when the app is backgrounded** — only on
   `pagehide`. Releasing on `visibilitychange` looks like good hygiene but
   causes a fresh permission prompt every time the worker flicks to
   another app and back. Android may end the track itself anyway, so
   `startAttach()` checks `readyState === "live"` before reusing a stream
   and re-acquires if it's dead.

**The permission prompt on every app open is a Telegram Android client bug
and cannot be fixed from here.** Telegram shows its own dialog from the
WebView's `onPermissionRequest` and doesn't persist the grant; Android's
permission system never sees it, so there's no phone setting for it.
Desktop Telegram *does* remember. Telegram closed the tracking issue
([#43](https://github.com/Telegram-Mini-Apps/issues/issues/43)) as **not
planned**; a community fix
([DrKLO/Telegram#1947](https://github.com/DrKLO/Telegram/pull/1947)) has
sat open and unmerged, and even that only covers repeats *within* a
session. Keeping the stream alive (points 2 and 4) is the only lever on
our side.

Note there is **no** `tg.requestCameraAccess()` in the Telegram WebApp
API, despite what some AI-generated snippets suggest — the standard
`getUserMedia` call is what triggers the permission prompt.

On the backend, don't assume `send_video` gives back a video. Telegram
decides for itself how to classify an upload, and it can **accept the call
but reclassify the file**, leaving `msg.video` as `None` — which is not an
exception, so it isn't caught by a `try/except TelegramError`. That's what
`_extract_file_id()` in [`app/main.py`](app/main.py) is for: read the
`file_id` off whichever attribute Telegram actually populated, and only
fall back to `send_document` when nothing is there. `/api/media` likewise
derives the content type from the extension in Telegram's `file_path`,
since a WebM served as `video/mp4` won't play.

Fetched media is cached on disk in `$DATA_DIR/media_cache/` (gitignored,
400 MB cap by default via `MEDIA_CACHE_MAX_MB`, oldest evicted first) and
served with a long `Cache-Control`. Telegram `file_id`s are immutable, so a
file only ever needs fetching once — without this, every tap on a 📷/🎬 icon
re-downloaded the whole thing from Telegram, which was slow for videos.

**Why uploads feel slow, and what would actually fix it:** every file
crosses the network *twice, in sequence* — phone → this server, then this
server → Telegram. Running the server on a home connection means both legs
are limited by that connection's (usually slow) upload speed, so a 20 MB
video costs 40 MB of uploading before the worker sees it succeed. Shrinking
the file helps, but the structural fix is hosting the backend somewhere
with real bandwidth (Render, per `spec.md` section 8): the phone's upload
becomes a normal internet transfer and the server → Telegram leg runs at
datacenter speed. Uploads show a live percentage
(`postWithProgress()` via XHR, since `fetch` can't report upload progress)
so a long transfer doesn't look frozen.

Once a photo/video is taken, the app uploads it straight to the backend
(`POST /api/attach`), which relays it into `STORAGE_CHAT_ID` via the bot API
— that relay is also how we get a Telegram `file_id` to store, so the
backend never keeps the raw file. The item flips to done as soon as the
upload succeeds, and the boss (or anyone) views the photo/video from inside
the checklist itself (the 📷/🎬 icon), not as a separate forwarded message —
Telegram's Bot API has no way to register a file without sending it
somewhere, so it goes to a dedicated private channel instead of anyone's DM.

## 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure

```bash
copy .env.example .env
```

Fill in `.env`:

- `BOT_TOKEN` — from [@BotFather](https://t.me/BotFather) (`/newbot` if you
  don't have one yet).
- `BOSS_ID` — your numeric Telegram user ID. Get it from
  [@userinfobot](https://t.me/userinfobot).
- `STORAGE_CHAT_ID` — chat ID of a private channel the bot relays media into
  (see below).
- `EXTRA_BOSS_IDS` — other Telegram IDs also allowed into the library
  (comma-separated, optional).
- `CREW_IDS` — worker Telegram IDs: get the "WORK PLAN FOR ..." message when
  a plan sends, and (together with `BOSS_ID`/`EXTRA_BOSS_IDS`) are the only
  IDs allowed to use the bot/Mini App at all (comma-separated). Get IDs from
  [@userinfobot](https://t.me/userinfobot), or from the "You're not
  registered... Your Telegram ID is ..." message someone gets if they try
  without being added yet.
- `TIMEZONE` — IANA name (default `Asia/Dubai`), used for the notification
  date and for resolving scheduled send times.
- `PUBLIC_URL` — fill this in after step 4 below.

## 3. Set up the media storage channel

1. In Telegram, create a new **Channel**, set it **Private**.
2. Open it → **Administrators** → **Add Admin** → add your bot (needs "Post
   Messages").
3. Post any message in the channel.
4. Start the server (step 5) and check its console output for a line like
   `CHANNEL POST seen — chat_id=-100... title='...'` — that ID (including
   the `-`) is your `STORAGE_CHAT_ID`. (If you don't see it, temporarily
   re-add a `MessageHandler(filters.UpdateType.CHANNEL_POST, ...)` in
   [`app/bot.py`](app/bot.py) that logs `update.channel_post.chat.id`.)

## 4. Expose the app over HTTPS (dev)

Telegram requires the Mini App page to be served over HTTPS. Easiest for
testing is a [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
(`cloudflared`) — no account needed, and unlike ngrok's free tier it doesn't
show a "visit site" warning page first (which would otherwise break the
Mini App, since Telegram's WebView can't click through it):

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the `https://...trycloudflare.com` URL it prints, put it in `.env` as
`PUBLIC_URL`. This URL is temporary — it changes every time you restart the
tunnel, so you'll need to update `PUBLIC_URL` and BotFather's Mini App URL
(step 5) again after a restart. For real use, deploy to Render instead
(below): the URL stops changing, and uploads stop crossing a home
connection twice.

## 5. Register the Mini App URL with BotFather

In [@BotFather](https://t.me/BotFather): `/mybots` → your bot → **Bot
Settings** → **Configure Mini App** (older BotFather versions call this
**Menu Button** → **Configure menu button**) → set it to your `PUBLIC_URL`.

## 6. Run

```bash
python run.py
```

This starts the web server and the bot (polling) together. Leave it running.

## 7. Try it

1. Open your bot in Telegram, send `/start` (from an ID in `ALLOWED_IDS` —
   see Access control above) — it replies with an **Open checklist** button.
2. Tap it → the checklist opens as "Work Plan DD/MM/YYYY", grouped by villa
   then section.
3. Tap an item → the camera opens. On Android this is an in-app camera
   (allow the permission once per visit); on iOS it's the native camera.
   Tap the shutter, or **Video** to record instead.
4. It uploads to `STORAGE_CHAT_ID`, and the item flips to ✅ with who did it
   and when — all without leaving the app. Tap the 📷/🎬 icon on a finished
   item to view what was attached. Once every item is ✅, the boss(es) get
   an "All tasks for DD/MM/YYYY are finished." message.

## 8. Try the boss library (slice 2)

1. As the boss (your `.env` `BOSS_ID`), send `/start` — you get **Open
   checklist**, **Open library**, and **Open archive** buttons.
2. Tap **Open library** → see every library item, grouped by villa then
   section, with items in the *current* plan pre-selected (highlighted).
3. Type new item text, a **Villa** (autocompletes; defaults to `908`), and
   optionally a section → **Add to library** — it's saved and auto-selected.
4. Tap any item to toggle it in/out of the plan you're assembling, or use
   **Select all** / **Deselect all**. Tap the **×** to delete an item from
   the library entirely (blocked if it's in today's live plan).
5. Tap **Send now**, or tap **Schedule** to open an hour/minute picker
   (**Confirm** sends it, **Back** cancels), to replace the live worker
   checklist (and reset all tick/finished state) with whatever's selected —
   a "✅ Plan sent/scheduled" toast confirms it.
6. Reopen the worker checklist — it now shows "Work Plan DD/MM/YYYY" with
   exactly that set of items. If `CREW_IDS` is set, everyone in it also gets
   a "WORK PLAN FOR DD/MM/YYYY" message with a WORK button.

## Deploying to Render

Worth doing for real use: the URL stops changing on every restart, and
uploads stop crossing a home connection twice (see "Why uploads feel slow"
above). [`render.yaml`](render.yaml) describes the service.

1. **Push this repo to GitHub** (it isn't a git repo yet — `git init`, commit,
   push). Check `.env` is *not* committed — `.gitignore` covers it, but
   confirm with `git status` before the first push.
2. In Render: **New → Blueprint**, point it at the repo. It reads
   `render.yaml` and creates the web service with its persistent disk.
3. Fill in the secrets it asks for (marked `sync: false`, so they're never
   in the repo): `BOT_TOKEN`, `BOSS_ID`, `STORAGE_CHAT_ID`,
   `EXTRA_BOSS_IDS`, `CREW_IDS`. Leave `PUBLIC_URL` blank for now.
4. Deploy. Render assigns `https://<service>.onrender.com` — set that as
   `PUBLIC_URL` in the dashboard and **redeploy**, since the bot builds its
   Mini App buttons from it.
5. Point BotFather's Mini App URL at the same address (step 5 above). This
   is the last time you'll have to: the URL is now stable.

Three things that will bite if changed:

- **Use the `starter` plan, not `free`.** Free instances sleep when idle,
  which stops the bot polling for updates and silently kills any scheduled
  send. The scheduler is an in-process timer, so it only exists while the
  process does.
- **Keep the persistent disk.** Render wipes the container filesystem on
  every deploy. `DATA_DIR=/var/data` puts `ays.db` (the whole library, every
  plan, all history) and the media cache on the mounted disk instead. Without
  it, every deploy silently resets the app to a fresh seeded library.
- **Back up `ays.db`.** A Render disk is not a backup. The photos themselves
  live in Telegram, but the database is the only record of which photo
  belongs to which task, who did it and when.

Still on polling rather than webhooks. Polling works fine on an
always-on instance and avoids a config mode; webhook support is the
tidier long-term option (`spec.md` section 8) but isn't built.

## Notes / assumptions made

- Fixed set of items seeded from `spec.md` section 11, tagged villa `908`,
  hardcoded in [`app/db.py`](app/db.py) as the initial library. The live
  plan starts **empty** until the boss sends one — no auto-fill.
- Sending a plan **replaces** what workers see and resets tick/finished
  state for the new generation, but the old generation's rows stay in the
  database (see Archive above) — nothing is actually deleted.
- `initData` is verified with the HMAC check Telegram documents, and is
  accepted for 24h from `auth_date` (a shared day-checklist should stay
  usable all day).
- No polling→webhook switch yet; always uses polling, per the spec's stated
  default.
