"""
MobeFace storage — SQLite persistence لإعلانات تجمعها الـ scrapers.

الجدول `listings` يحتفظ بكل إعلان مرة واحدة (PK = id). كل scrape يحدّث
`last_seen` للموجود ويضيف الجديد. الـ index على `first_seen` للسرعة.
"""
from __future__ import annotations

import sqlite3
import time
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "listings.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    price        INTEGER,
    condition    TEXT NOT NULL,
    category     TEXT NOT NULL,
    source       TEXT NOT NULL,
    source_label TEXT NOT NULL,
    source_color TEXT NOT NULL,
    image        TEXT,
    url          TEXT NOT NULL,
    fault        TEXT,
    city         TEXT,
    hot          INTEGER NOT NULL DEFAULT 0,
    first_seen   REAL NOT NULL,
    last_seen    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_listings_category   ON listings(category);
CREATE INDEX IF NOT EXISTS idx_listings_source     ON listings(source);
"""


@contextmanager
def _conn():
    with _lock:
        c = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        try:
            yield c
        finally:
            c.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def upsert_many(items: list[dict]) -> tuple[int, int]:
    """يضيف الجديد ويحدّث last_seen للموجود. يرجع (added, updated)."""
    if not items:
        return 0, 0
    now = time.time()
    added = 0
    updated = 0
    with _conn() as c:
        for it in items:
            existing = c.execute("SELECT id FROM listings WHERE id = ?", (it["id"],)).fetchone()
            if existing:
                c.execute(
                    """UPDATE listings SET
                        title=?, price=?, condition=?, category=?, source=?,
                        source_label=?, source_color=?, image=?, url=?, fault=?,
                        city=?, hot=?, last_seen=?
                       WHERE id = ?""",
                    (
                        it["title"], it.get("price"), it["condition"], it["category"],
                        it["source"], it["sourceLabel"], it["sourceColor"], it.get("image"),
                        it["url"], it.get("fault"), it.get("city"), int(bool(it.get("hot"))),
                        now, it["id"],
                    ),
                )
                updated += 1
            else:
                c.execute(
                    """INSERT INTO listings
                       (id, title, price, condition, category, source, source_label,
                        source_color, image, url, fault, city, hot, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        it["id"], it["title"], it.get("price"), it["condition"], it["category"],
                        it["source"], it["sourceLabel"], it["sourceColor"], it.get("image"),
                        it["url"], it.get("fault"), it.get("city"), int(bool(it.get("hot"))),
                        now, now,
                    ),
                )
                added += 1
    return added, updated


def query_listings(
    q: str = "",
    category: str = "all",
    condition: str = "all",
    source: str = "all",
    limit: int = 500,
) -> list[dict]:
    where = ["1=1"]
    params: list = []
    if q:
        where.append("LOWER(title) LIKE ?")
        params.append(f"%{q.lower()}%")
    if category != "all":
        where.append("category = ?")
        params.append(category)
    if condition != "all":
        where.append("condition = ?")
        params.append(condition)
    if source != "all":
        where.append("source = ?")
        params.append(source)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT * FROM listings
        WHERE {where_sql}
        ORDER BY hot DESC, first_seen DESC
        LIMIT ?
    """
    params.append(limit)
    with _conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_listings() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM listings").fetchone()[0]


def cleanup_old(max_age_days: int = 7, max_total: int = 1000) -> int:
    """يحذف الإعلانات الأقدم من max_age_days أو ما يزيد عن max_total."""
    cutoff = time.time() - (max_age_days * 86400)
    with _conn() as c:
        c.execute("DELETE FROM listings WHERE last_seen < ?", (cutoff,))
        deleted_age = c.rowcount or 0
        # احتفظ بأحدث max_total
        c.execute(
            "DELETE FROM listings WHERE id NOT IN (SELECT id FROM listings ORDER BY first_seen DESC LIMIT ?)",
            (max_total,),
        )
        deleted_overflow = c.rowcount or 0
    return deleted_age + deleted_overflow


def stats() -> dict:
    with _conn() as c:
        row = c.execute(
            """SELECT
                COUNT(*) total,
                SUM(CASE WHEN hot=1 THEN 1 ELSE 0 END) hot,
                SUM(CASE WHEN condition='parts' THEN 1 ELSE 0 END) parts,
                MAX(last_seen) last_scrape
               FROM listings"""
        ).fetchone()
    return {
        "total": row["total"] or 0,
        "hot": row["hot"] or 0,
        "parts": row["parts"] or 0,
        "last_scrape": row["last_scrape"],
    }


def _row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "id":          r["id"],
        "title":       r["title"],
        "price":       r["price"],
        "condition":   r["condition"],
        "category":    r["category"],
        "source":      r["source"],
        "sourceLabel": r["source_label"],
        "sourceColor": r["source_color"],
        "image":       r["image"],
        "url":         r["url"],
        "fault":       r["fault"],
        "city":        r["city"],
        "hot":         bool(r["hot"]),
        "firstSeen":   r["first_seen"],
        "lastSeen":    r["last_seen"],
        "postedAgo":   _time_ago(r["first_seen"]),
        "isNew":       (time.time() - r["first_seen"]) < 3600,
    }


def _time_ago(ts: float | None) -> str:
    if not ts:
        return "recently"
    delta = time.time() - ts
    if delta < 60:
        return "الآن"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"
