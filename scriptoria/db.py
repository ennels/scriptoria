"""Content database: connection, schema, metadata."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config
from .books import BOOKS

SCHEMA_VERSION = 2
SCHEMA = config.PACKAGE / "schema.sql"


def connect(db_path: str | Path | None = None, *, must_exist: bool = False) -> sqlite3.Connection:
    path = Path(db_path or config.content_db())
    if must_exist:
        con = sqlite3.connect(f"file:{path}?mode=rw", uri=True, check_same_thread=False)
    else:
        con = sqlite3.connect(str(path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text())
    if con.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 0:
        con.executemany(
            "INSERT INTO book(id, osis, name, testament, chapters) VALUES(?,?,?,?,?)",
            [(b["position"], b["osis"], b["name"], b["testament"], b["chapters"]) for b in BOOKS])
    set_meta(con, "schema_version", SCHEMA_VERSION)
    con.commit()


def set_meta(con: sqlite3.Connection, key: str, value) -> None:
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, str(value)))


def get_meta(con: sqlite3.Connection, key: str, default=None):
    try:
        r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return r[0] if r else default


def schema_version(con: sqlite3.Connection) -> int:
    """2+ for current databases, 1 for the first release (no meta table), 0 if empty."""
    v = get_meta(con, "schema_version")
    if v is not None:
        return int(v)
    has_verse = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='verse'").fetchone()
    return 1 if has_verse else 0


def book_id_by_osis(con: sqlite3.Connection) -> dict[str, int]:
    return {r["osis"]: r["id"] for r in con.execute("SELECT id, osis FROM book")}
