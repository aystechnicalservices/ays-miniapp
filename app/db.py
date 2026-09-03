"""SQLite storage.

Model:
- library_items: the boss's persistent, reusable task bank, each tagged with
  a villa. `retired` items are hidden from the library view but never
  hard-deleted if any plan generation, past or present, ever used them —
  plan_items.library_item_id is a real foreign key, so deleting one referenced
  by archive history would fail outright (or, worse, silently corrupt the
  archive's ability to show what a past task actually was).
- plans: one row per "send" — each plan generation has its own sent_at
  (the real timestamp it was sent) and plan_date (the calendar date it's
  labeled for — "today" or "tomorrow" at send time — independent of
  sent_at, since a boss can send tomorrow's plan tonight).
- plan_items: a generation's assembled checklist — references library_items
  by id, tagged with the plan generation (plan_id) it belongs to. Sending a
  new plan does NOT delete old plan_items/item_state: those stay in the
  database as the archive for past days. Every plan dated today or later
  (plan_date >= today) stays fully live and editable by its own plan_id —
  not just the most recent row — since a boss sending tomorrow's plan
  shouldn't make today's stop working. Anything dated before today is
  archive: read-only, addressed only by plan_id from the Archive page.
- item_state: tick/done state per plan_item (1 row per plan_item, keyed by
  its id — never reused across generations, so history stays intact).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DEFAULT_VILLA = "908"

# (villa, section, text)
SEED_ITEMS = [
    # --- Villa 908 ---
    ("908", "Area Cleaning", "Check the villa area and find any urgent work."),
    ("908", "Area Cleaning", "Remove leaves, plant waste and all rubbish."),
    ("908", "Area Cleaning", "Clean under the bushes."),
    ("908", "Area Cleaning", "Clean all corners and hard-to-reach areas."),
    ("908", "Area Cleaning", "Clean the area in front of the entrance and outside the gate."),
    ("908", "Area Cleaning", "Clean the garden and the full villa area properly."),
    ("908", "Area Cleaning", "Remove weeds."),
    ("908", "Area Cleaning", "Blow the full area."),
    ("908", "Washing", "Wash the yard."),
    ("908", "Washing", "Wash the entrance area."),
    ("908", "Washing", "Wash the walkways."),
    ("908", "Washing", "Wash the BBQ area."),
    ("908", "Washing", "Use the water jet machine where needed."),
    ("908", "Washing", "Wash the roof."),
    ("908", "Washing", "Wash the toilet."),
    ("908", "Washing", "Wash the outdoor furniture."),
    ("908", "Washing", "Wash the staff / service room."),
    ("908", "Washing", "If needed, use Clorox for deep cleaning of the room and toilet."),
    ("908", "Swimming Pool", "Clean the swimming pool."),
    ("908", "Swimming Pool", "Vacuum the pool floor."),
    ("908", "Swimming Pool", "Brush the walls and floor."),
    ("908", "Swimming Pool", "Check the pump room for any water leaks."),
    ("908", "Swimming Pool", "Test the pool water and send the test results."),
    ("908", "Swimming Pool", "Based on the water test, use AI to calculate how much chemical is needed."),
    ("908", "Swimming Pool", "Add chlorine and pH- only if needed."),
    ("908", "Swimming Pool", "After adding chemicals, report what chemical was added and how much."),
    ("908", "Swimming Pool", "Send a photo of the water test result."),
    ("908", "Garden", "Trim the bonsai garden."),
    ("908", "Garden", "Trim plants near the garage."),
    ("908", "Garden", "Cut the grass."),
    ("908", "Garden", "Trim the bushes along the swimming pool."),
    ("908", "Garden", "Cut dry branches."),
    ("908", "Garden", "Remove dead bushes."),
    ("908", "Garden", "Give extra water to plants if needed."),
    ("908", "Garden", "Deep water the plants using the big hose."),
    ("908", "Garden", "Spray pesticide if needed."),
    ("908", "Garden", "Plant new plants as instructed."),
    ("908", "Irrigation", "Check the irrigation system."),
    ("908", "Irrigation", "Check all irrigation zones."),
    ("908", "Irrigation", "Check for water leaks."),
    ("908", "Irrigation", "Check all drippers and emitters."),
    ("908", "Irrigation", "Check that every plant is getting enough water."),
    # --- Villa 1002 ---
    ("1002", "Area Cleaning", "Remove leaves and plant waste."),
    ("1002", "Area Cleaning", "Remove rubbish from under the bushes."),
    ("1002", "Area Cleaning", "Clean all corners and hard-to-reach areas."),
    ("1002", "Area Cleaning", "Collect all rubbish."),
    ("1002", "Area Cleaning", "Throw away all rubbish."),
    ("1002", "Area Cleaning", "Blow the full villa area."),
    ("1002", "Area Cleaning", "After finishing, check the full area carefully and make sure everything is clean."),
    ("1002", "Washing", "Wash the full yard."),
    ("1002", "Washing", "Use the water jet machine / pressure washer."),
    ("1002", "Washing", "If needed, use two water jet machines."),
    ("1002", "Irrigation", "Start and check every irrigation zone."),
    ("1002", "Irrigation", "Check all sprinklers."),
    ("1002", "Irrigation", "Check all drip emitters."),
    ("1002", "Irrigation", "Check for water leaks."),
    ("1002", "Irrigation", "Check for blocked emitters."),
    ("1002", "Irrigation", "Take photos/videos of all problems."),
    ("1002", "Irrigation", "Water each required zone for enough time."),
    ("1002", "Garden", "Trim bushes and trees."),
    ("1002", "Garden", "Shape the plants along the house."),
    ("1002", "Garden", "Shape the plants along the fence."),
    ("1002", "Garden", "Remove dry/dead plants."),
    ("1002", "Garden", "Remove weeds."),
    ("1002", "Garden", "Water the bushes with the hose."),
    ("1002", "Garden", "Plant new plants as instructed."),
    ("1002", "Garden", "Trim the bonsai garden."),
    # --- Living Legends ---
    ("Living Legends", "Swimming Pool", "Clean the swimming pool."),
    ("Living Legends", "Swimming Pool", "Vacuum the pool."),
    ("Living Legends", "Swimming Pool", "Brush the pool walls and floor."),
    ("Living Legends", "Swimming Pool", "Test the pool water."),
    ("Living Legends", "Swimming Pool", "Send the water test results."),
    ("Living Legends", "Villa Yard and Area", "Blow the full area."),
    ("Living Legends", "Villa Yard and Area", "Remove all rubbish."),
    ("Living Legends", "Villa Yard and Area", "Remove weeds."),
    ("Living Legends", "Villa Yard and Area", "Clean all flower beds."),
    ("Living Legends", "Villa Yard and Area", "Wash the yard with the water jet machine / pressure washer."),
    ("Living Legends", "Villa Yard and Area", "Make sure the full villa area is clean and tidy."),
    ("Living Legends", "Desert Area Behind the Fence", "Clean the area."),
    ("Living Legends", "Desert Area Behind the Fence", "Water the trees."),
    ("Living Legends", "Desert Area Behind the Fence", "Water the trees deeply around the roots."),
    ("Living Legends", "Desert Area Behind the Fence", "Remove weeds."),
    ("Living Legends", "Desert Area Behind the Fence", "Spray the trees if needed."),
    ("Living Legends", "Garden", "Water the fruit trees."),
    ("Living Legends", "Garden", "Water the bushes."),
    ("Living Legends", "Garden", "Clean and maintain the flower beds."),
    ("Living Legends", "Garden", "Trim and shape the plants."),
    ("Living Legends", "Garden", "Prepare the area for new planting."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS library_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                villa TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL,
                text TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                retired INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        if not _has_column(conn, "library_items", "retired"):
            conn.execute("ALTER TABLE library_items ADD COLUMN retired INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL,
                plan_date TEXT NOT NULL DEFAULT ''
            )
            """
        )
        if not _has_column(conn, "plans", "plan_date"):
            conn.execute("ALTER TABLE plans ADD COLUMN plan_date TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE plans SET plan_date = date(sent_at) WHERE plan_date = ''")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL REFERENCES plans(id),
                library_item_id INTEGER NOT NULL REFERENCES library_items(id),
                sort_order INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_state (
                item_id INTEGER PRIMARY KEY REFERENCES plan_items(id),
                done INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER,
                user_name TEXT,
                media_file_id TEXT,
                media_type TEXT,
                done_at TEXT
            )
            """
        )

        row = conn.execute("SELECT COUNT(*) AS n FROM library_items").fetchone()
        if row["n"] == 0:
            now = _now()
            for i, (villa, section, text) in enumerate(SEED_ITEMS):
                conn.execute(
                    "INSERT INTO library_items (villa, section, text, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (villa, section, text, i, now),
                )


def _replace_plan(conn, library_item_ids: list[int], plan_date: str) -> int:
    cur = conn.execute(
        "INSERT INTO plans (sent_at, plan_date) VALUES (?, ?)", (_now(), plan_date)
    )
    plan_id = cur.lastrowid
    for i, library_item_id in enumerate(library_item_ids):
        item_cur = conn.execute(
            "INSERT INTO plan_items (plan_id, library_item_id, sort_order) VALUES (?, ?, ?)",
            (plan_id, library_item_id, i),
        )
        conn.execute(
            "INSERT INTO item_state (item_id, done) VALUES (?, 0)",
            (item_cur.lastrowid,),
        )
    return plan_id


def send_plan(library_item_ids: list[int], plan_date: str) -> int:
    """Starts a fresh plan generation labeled for plan_date (an ISO
    YYYY-MM-DD string — "today" or "tomorrow" at the time this is called).
    Returns the new plan's id."""
    with get_conn() as conn:
        return _replace_plan(conn, library_item_ids, plan_date)


def update_plan(plan_id: int, library_item_ids: list[int]) -> None:
    """Applies a new selection to plan_id in place — used when the boss
    re-sends targeting a date that already has a plan (today's or
    tomorrow's), so a tweak doesn't wipe the crew's progress. A finished
    item is never touched, no matter what the new selection says: it keeps
    its tick, photo and timestamp forever, even if deselected or deleted
    from the library entirely. An unfinished item not in the new selection
    is dropped outright. Anything newly selected that isn't already on the
    plan is added as a fresh, unfinished entry. This works on *any* plan,
    not just the most recent one — today's plan stays fully editable even
    after tomorrow's has been sent and become the newer generation."""
    with get_conn() as conn:
        existing = conn.execute(
            """
            SELECT plan_items.id, plan_items.library_item_id, item_state.done
            FROM plan_items
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.plan_id = ?
            """,
            (plan_id,),
        ).fetchall()

        selected = set(library_item_ids)
        existing_lib_ids = {r["library_item_id"] for r in existing}

        for row in existing:
            if not row["done"] and row["library_item_id"] not in selected:
                conn.execute("DELETE FROM item_state WHERE item_id = ?", (row["id"],))
                conn.execute("DELETE FROM plan_items WHERE id = ?", (row["id"],))

        next_sort_row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM plan_items WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        next_sort = next_sort_row["m"] + 1
        for library_item_id in library_item_ids:
            if library_item_id in existing_lib_ids:
                continue
            item_cur = conn.execute(
                "INSERT INTO plan_items (plan_id, library_item_id, sort_order) VALUES (?, ?, ?)",
                (plan_id, library_item_id, next_sort),
            )
            conn.execute(
                "INSERT INTO item_state (item_id, done) VALUES (?, 0)",
                (item_cur.lastrowid,),
            )
            next_sort += 1


def get_plan_id_for_date(date_iso: str):
    """The plan generation labeled for this ISO date, or None. At most one
    plan is ever labeled for a given date — "today"/"tomorrow" are always
    computed relative to the actual calendar date, so a date can't be
    targeted twice once it's passed."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM plans WHERE plan_date = ? ORDER BY id DESC LIMIT 1",
            (date_iso,),
        ).fetchone()
        return row["id"] if row else None


def list_current_or_future_plan_dates(today_iso: str):
    """Every plan generation dated today or later, earliest first. Normally
    just today's; two entries once a plan for tomorrow has been sent."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, plan_date FROM plans WHERE plan_date >= ? ORDER BY plan_date ASC",
            (today_iso,),
        ).fetchall()
        return [{"id": r["id"], "plan_date": r["plan_date"]} for r in rows]


def get_plan_date(plan_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT plan_date FROM plans WHERE id = ?", (plan_id,)).fetchone()
        return row["plan_date"] if row and row["plan_date"] else None


def get_plan_id_for_item(item_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT plan_id FROM plan_items WHERE id = ?", (item_id,)
        ).fetchone()
        return row["plan_id"] if row else None


def get_plan_library_item_ids(plan_id):
    """library_item_ids currently on plan_id, or [] if plan_id is None/has none."""
    if plan_id is None:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT library_item_id FROM plan_items WHERE plan_id = ?", (plan_id,)
        ).fetchall()
        return [r["library_item_id"] for r in rows]


def list_plans(today_iso: str):
    """All plan generations, most recent first, with a simple finished/total
    count. "current" marks any plan dated today or later — not just the
    most recent row — since today's plan stays live even after tomorrow's
    has been sent."""
    with get_conn() as conn:
        plan_rows = conn.execute("SELECT id, sent_at, plan_date FROM plans ORDER BY id DESC").fetchall()

        result = []
        for p in plan_rows:
            counts = conn.execute(
                """
                SELECT COUNT(*) AS total, COALESCE(SUM(item_state.done), 0) AS done
                FROM plan_items
                JOIN item_state ON item_state.item_id = plan_items.id
                WHERE plan_items.plan_id = ?
                """,
                (p["id"],),
            ).fetchone()
            result.append(
                {
                    "id": p["id"],
                    "sent_at": p["sent_at"],
                    "plan_date": p["plan_date"],
                    "total": counts["total"],
                    "done": counts["done"],
                    "current": bool(p["plan_date"]) and p["plan_date"] >= today_iso,
                }
            )
        return result


def get_plan_items(plan_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT plan_items.id, library_items.villa, library_items.section,
                   library_items.text, plan_items.sort_order, item_state.done,
                   item_state.user_name, item_state.done_at, item_state.media_type
            FROM plan_items
            JOIN library_items ON library_items.id = plan_items.library_item_id
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.plan_id = ?
            ORDER BY plan_items.sort_order
            """,
            (plan_id,),
        ).fetchall()

    return [
        {
            "id": r["id"],
            "villa": r["villa"],
            "section": r["section"],
            "text": r["text"],
            "done": bool(r["done"]),
            "done_by": r["user_name"],
            "done_at": r["done_at"],
            "media_type": r["media_type"],
        }
        for r in rows
    ]


def get_checklist(plan_id: int):
    items = get_plan_items(plan_id)
    all_done = bool(items) and all(i["done"] for i in items)
    return items, all_done


def is_active_and_pending(item_id: int, today_iso: str) -> bool:
    """True if item_id belongs to a plan dated today or later (not an
    archived past plan) and isn't done yet."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT item_state.done, plans.plan_date
            FROM plan_items
            JOIN item_state ON item_state.item_id = plan_items.id
            JOIN plans ON plans.id = plan_items.plan_id
            WHERE plan_items.id = ?
            """,
            (item_id,),
        ).fetchone()
        if row is None or row["done"]:
            return False
        return bool(row["plan_date"]) and row["plan_date"] >= today_iso


def get_media(item_id: int):
    """Return (media_file_id, media_type) for a done item, or (None, None)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT media_file_id, media_type FROM item_state WHERE item_id = ? AND done = 1",
            (item_id,),
        ).fetchone()
        if row is None:
            return None, None
        return row["media_file_id"], row["media_type"]


def mark_done(item_id: int, user_id: int, user_name: str, media_file_id: str, media_type: str):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE item_state
            SET done = 1, user_id = ?, user_name = ?, media_file_id = ?,
                media_type = ?, done_at = ?
            WHERE item_id = ?
            """,
            (user_id, user_name, media_file_id, media_type, _now(), item_id),
        )


def get_item_text(item_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT library_items.text, library_items.section, library_items.villa
            FROM plan_items
            JOIN library_items ON library_items.id = plan_items.library_item_id
            WHERE plan_items.id = ?
            """,
            (item_id,),
        ).fetchone()
        return (row["text"], row["section"], row["villa"]) if row else (None, None, None)


def list_library():
    """Non-retired library items. Which ones are selected for today/tomorrow
    is per-target now (see main.py's _boss_state), not a single flag here —
    today's and tomorrow's plans can each have their own selection live at
    once."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, villa, section, text, sort_order FROM library_items "
            "WHERE retired = 0 ORDER BY sort_order"
        ).fetchall()

    return [
        {"id": r["id"], "villa": r["villa"], "section": r["section"], "text": r["text"]}
        for r in rows
    ]


def add_library_item(villa: str, section: str, text: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) AS m FROM library_items").fetchone()
        next_order = row["m"] + 1
        cur = conn.execute(
            "INSERT INTO library_items (villa, section, text, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (villa, section, text, next_order, _now()),
        )
        return cur.lastrowid


def remove_library_item(item_id: int) -> tuple[bool, str]:
    """Returns (ok, error_message). Always allowed, even for an item on
    today's live plan — deleting only removes it from the library going
    forward. A finished plan_item referencing it is untouched (stays done
    on the checklist forever); an unfinished one is only dropped once the
    boss re-sends without it (see update_plan). Hard-deletes if the item
    was never used in any plan; otherwise marks it retired (hidden from the
    library) rather than deleting, since plan_items.library_item_id is a
    real foreign key and a hard delete would fail — or, if it somehow
    didn't, would leave the archive unable to show what a past task
    actually was."""
    with get_conn() as conn:
        ever_used = conn.execute(
            "SELECT 1 FROM plan_items WHERE library_item_id = ? LIMIT 1", (item_id,)
        ).fetchone()
        if ever_used:
            cur = conn.execute("UPDATE library_items SET retired = 1 WHERE id = ?", (item_id,))
        else:
            cur = conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))
        if cur.rowcount == 0:
            return False, "Item not found."
        return True, ""
