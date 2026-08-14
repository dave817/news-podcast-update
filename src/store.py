"""SQLite persistence: episodes (dedup by GUID), transcript/memo status, run log.

Pattern borrowed from the last30days skill's store.py: WAL mode for cron+user
concurrency, a UNIQUE key for dedup, and status columns to drive the pipeline.

CLI:
    python3 src/store.py init          # create schema
    python3 src/store.py stats         # counts by status
    python3 src/store.py list [--status new] [--limit N]
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional

from common import DB_PATH, episode_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id            TEXT PRIMARY KEY,      -- episode_id(source, guid)
    source        TEXT NOT NULL,
    lang          TEXT,
    guid          TEXT NOT NULL,         -- RSS guid or youtube video id
    title         TEXT,
    url           TEXT,                  -- page/watch url
    audio_url     TEXT,                  -- enclosure / stream to download
    native_transcript_url TEXT,          -- Podcasting 2.0 <podcast:transcript>, if any
    published     TEXT,                  -- ISO date
    duration_sec  INTEGER,
    transcript_path TEXT,
    transcript_source TEXT,              -- 'captions' | 'rss' | 'azure-asr' | 'local-asr'
    memo_path     TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    -- new -> transcribed -> memo_done -> delivered ; or 'error'
    error         TEXT,
    first_seen    REAL NOT NULL,
    updated       REAL NOT NULL,
    UNIQUE(source, guid)
);
CREATE INDEX IF NOT EXISTS idx_status   ON episodes(status);
CREATE INDEX IF NOT EXISTS idx_source   ON episodes(source);
CREATE INDEX IF NOT EXISTS idx_published ON episodes(published);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT,                     -- 'daily' | 'backfill'
    started    REAL,
    finished   REAL,
    new_count  INTEGER DEFAULT 0,
    notes      TEXT
);
"""

VALID_STATUS = {"new", "transcribed", "memo_done", "delivered", "error"}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)


def upsert_episode(
    *,
    source: str,
    guid: str,
    lang: str = "",
    title: str = "",
    url: str = "",
    audio_url: str = "",
    native_transcript_url: str = "",
    published: str = "",
    duration_sec: Optional[int] = None,
) -> tuple[str, bool]:
    """Insert if unseen. Returns (episode_id, is_new)."""
    eid = episode_id(source, guid)
    now = time.time()
    with connect() as c:
        cur = c.execute("SELECT id FROM episodes WHERE id=?", (eid,))
        if cur.fetchone():
            return eid, False
        c.execute(
            """INSERT INTO episodes
               (id, source, lang, guid, title, url, audio_url,
                native_transcript_url, published, duration_sec, status,
                first_seen, updated)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'new', ?, ?)""",
            (eid, source, lang, guid, title, url, audio_url,
             native_transcript_url, published, duration_sec, now, now),
        )
    return eid, True


def mark(eid: str, **fields) -> None:
    if not fields:
        return
    fields["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE episodes SET {cols} WHERE id=?", (*fields.values(), eid))


def get(eid: str) -> Optional[sqlite3.Row]:
    with connect() as c:
        return c.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()


def by_status(status: str, limit: Optional[int] = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM episodes WHERE status=? ORDER BY published DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    with connect() as c:
        return list(c.execute(q, (status,)).fetchall())


def start_run(kind: str) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO runs (kind, started) VALUES (?,?)", (kind, time.time()))
        return cur.lastrowid


def finish_run(run_id: int, new_count: int, notes: str = "") -> None:
    with connect() as c:
        c.execute(
            "UPDATE runs SET finished=?, new_count=?, notes=? WHERE id=?",
            (time.time(), new_count, notes, run_id),
        )


def stats() -> dict[str, int]:
    with connect() as c:
        rows = c.execute("SELECT status, COUNT(*) n FROM episodes GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


# --- CLI ---------------------------------------------------------------------
def _main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="episodes store")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("stats")
    pl = sub.add_parser("list")
    pl.add_argument("--status", default=None)
    pl.add_argument("--limit", type=int, default=20)
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "init":
        init()
        print(f"initialized {DB_PATH}")
    elif args.cmd == "stats":
        init()
        print(stats() or "(empty)")
    elif args.cmd == "list":
        init()
        rows = by_status(args.status, args.limit) if args.status else []
        if not args.status:
            with connect() as c:
                q = "SELECT * FROM episodes ORDER BY published DESC LIMIT ?"
                rows = list(c.execute(q, (args.limit,)).fetchall())
        for r in rows:
            print(f"[{r['status']:<11}] {r['source']:<16} {r['published'][:10]}  {r['title'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
