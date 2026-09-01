"""SQLite storage.

Model:
- library_items: the boss's persistent, reusable task bank, each tagged with
  a villa.
- plans: one row per "send" — each plan generation has its own sent_at.
- plan_items: a generation's assembled checklist — references library_items
  by id, tagged with the plan generation (plan_id) it belongs to. Sending a
  new plan does NOT delete old plan_items/item_state: those stay in the
  database as the archive for past days. Only the latest plan generation
  (MAX(plans.id)) is "current" — that's what the worker checklist, the
  library's "active" highlighting, and library-item deletion all look at.
- item_state: tick/done state per plan_item (1 row per plan_item, keyed by
  its id — never reused across generations, so history stays intact).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DEFAULT_VILLA = "908"

SEED_ITEMS = [
    # (section, text)
    ("Full Area Cleaning", "blow the entire yard"),
    ("Full Area Cleaning", "remove leaves and plant debris"),
    ("Full Area Cleaning", "clean the areas under the bushes"),
    ("Full Area Cleaning", "remove rubbish from corners and hard-to-reach areas"),
    ("Full Area Cleaning", "collect and dispose of all rubbish"),
    ("Washing", "wash the main entrance"),
    ("Washing", "wash dirty pathways"),
    ("Washing", "clean the area around the swimming pool"),
    ("Washing", "wash the BBQ area and the work surface"),
    ("Swimming Pool", "vacuum the swimming pool"),
    ("Swimming Pool", "brush the pool walls and floor"),
    ("Swimming Pool", "test the pool water and send the results"),
    ("Swimming Pool", "remove debris from the water surface"),
    ("Swimming Pool", "clean and arrange the area around the swimming pool"),
    ("Plant Trimming", "trim bushes that have lost their shape"),
    ("Plant Trimming", "level the edges of the plants"),
    ("Plant Trimming", "remove unnecessary and protruding branches"),
    ("Plant Trimming", "tidy the bonsai garden"),
    ("Plant Trimming", "remove weeds"),
    ("Inspection", "inspect the entrance area"),
    ("Inspection", "inspect the BBQ area"),
    ("Inspection", "check lights, covers, grilles, and visible damage"),
    ("Inspection", "check for dry, damaged, or dying plants"),
    ("Final Cleaning", "blow the entire area again"),
    ("Final Cleaning", "remove all tools and materials"),
    ("Final Cleaning", "make sure the pathways and entrance are clean"),
    ("Final Cleaning", "record and send a final video overview"),
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
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT NOT NULL
            )
            """
        )
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
            for i, (section, text) in enumerate(SEED_ITEMS):
                conn.execute(
                    "INSERT INTO library_items (villa, section, text, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (DEFAULT_VILLA, section, text, i, now),
                )


def _replace_plan(conn, library_item_ids: list[int]) -> None:
    cur = conn.execute("INSERT INTO plans (sent_at) VALUES (?)", (_now(),))
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


def send_plan(library_item_ids: list[int]) -> None:
    with get_conn() as conn:
        _replace_plan(conn, library_item_ids)


def update_plan(library_item_ids: list[int]) -> dict:
    """Edit the plan that's already live, instead of starting a new one.

    Items already on the plan keep their tick state and media — the whole
    point, so the boss can adjust the day's work without wiping out what the
    crew has already finished. Finished items are never removed, even if
    deselected, since that would discard the photo and the record of who did
    it; those are reported back as `kept_finished` so the UI can say so.
    """
    wanted = list(dict.fromkeys(library_item_ids))
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(id) AS id FROM plans").fetchone()
        plan_id = row["id"] if row else None
        if plan_id is None:
            _replace_plan(conn, wanted)
            return {"added": len(wanted), "removed": 0, "kept_finished": 0}

        current = conn.execute(
            """
            SELECT plan_items.id, plan_items.library_item_id, item_state.done
            FROM plan_items
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.plan_id = ?
            """,
            (plan_id,),
        ).fetchall()
        by_library_id = {r["library_item_id"]: r for r in current}

        added = removed = kept_finished = 0

        for library_item_id, item in by_library_id.items():
            if library_item_id in wanted:
                continue
            if item["done"]:
                kept_finished += 1
                continue
            conn.execute("DELETE FROM item_state WHERE item_id = ?", (item["id"],))
            conn.execute("DELETE FROM plan_items WHERE id = ?", (item["id"],))
            removed += 1

        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM plan_items WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()["m"]
        for library_item_id in wanted:
            if library_item_id in by_library_id:
                continue
            next_order += 1
            cur = conn.execute(
                "INSERT INTO plan_items (plan_id, library_item_id, sort_order) VALUES (?, ?, ?)",
                (plan_id, library_item_id, next_order),
            )
            conn.execute("INSERT INTO item_state (item_id, done) VALUES (?, 0)", (cur.lastrowid,))
            added += 1

        return {"added": added, "removed": removed, "kept_finished": kept_finished}


def get_current_plan_progress():
    """(total, finished) for the live plan — lets the boss UI warn before a
    replace-everything send throws away finished work."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total, COALESCE(SUM(item_state.done), 0) AS done
            FROM plan_items
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.plan_id = (SELECT MAX(id) FROM plans)
            """
        ).fetchone()
        return row["total"], row["done"]


def get_plan_sent_at():
    with get_conn() as conn:
        row = conn.execute("SELECT sent_at FROM plans ORDER BY id DESC LIMIT 1").fetchone()
        return row["sent_at"] if row else None


def list_plans():
    """All plan generations, most recent first, with a simple finished/total count."""
    with get_conn() as conn:
        plan_rows = conn.execute("SELECT id, sent_at FROM plans ORDER BY id DESC").fetchall()
        current_id_row = conn.execute("SELECT MAX(id) AS m FROM plans").fetchone()
        current_id = current_id_row["m"] if current_id_row else None

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
                    "total": counts["total"],
                    "done": counts["done"],
                    "current": p["id"] == current_id,
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


def get_checklist():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT plan_items.id, library_items.villa, library_items.section,
                   library_items.text, plan_items.sort_order, item_state.done,
                   item_state.user_name, item_state.done_at, item_state.media_type
            FROM plan_items
            JOIN library_items ON library_items.id = plan_items.library_item_id
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.plan_id = (SELECT MAX(id) FROM plans)
            ORDER BY plan_items.sort_order
            """
        ).fetchall()

    items = [
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
    all_done = bool(items) and all(i["done"] for i in items)
    return items, all_done


def is_active_and_pending(item_id: int) -> bool:
    """True if item_id belongs to the current (latest) plan and isn't done yet."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT item_state.done
            FROM plan_items
            JOIN item_state ON item_state.item_id = plan_items.id
            WHERE plan_items.id = ? AND plan_items.plan_id = (SELECT MAX(id) FROM plans)
            """,
            (item_id,),
        ).fetchone()
        return row is not None and not row["done"]


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
    """All library items, plus which ones are in the current plan generation."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, villa, section, text, sort_order FROM library_items ORDER BY sort_order"
        ).fetchall()
        active_rows = conn.execute(
            "SELECT DISTINCT library_item_id FROM plan_items "
            "WHERE plan_id = (SELECT MAX(id) FROM plans)"
        ).fetchall()
        active_ids = {r["library_item_id"] for r in active_rows}

    return [
        {
            "id": r["id"],
            "villa": r["villa"],
            "section": r["section"],
            "text": r["text"],
            "active": r["id"] in active_ids,
        }
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
    """Returns (ok, error_message)."""
    with get_conn() as conn:
        in_use = conn.execute(
            "SELECT 1 FROM plan_items WHERE library_item_id = ? "
            "AND plan_id = (SELECT MAX(id) FROM plans) LIMIT 1",
            (item_id,),
        ).fetchone()
        if in_use:
            return False, "This item is in today's plan — send a new plan without it first."
        cur = conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))
        if cur.rowcount == 0:
            return False, "Item not found."
        return True, ""
