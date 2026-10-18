"""SQLite connection + schema init + the canonical verse spine."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .books import BOOKS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "scriptoria.db"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text())
    # Seed the 66 books once.
    if con.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 0:
        con.executemany(
            "INSERT INTO book(id, osis, name, testament, chapters) VALUES(?,?,?,?,?)",
            [(b["position"], b["osis"], b["name"], b["testament"], b["chapters"]) for b in BOOKS],
        )
    con.commit()


def book_id_by_osis(con: sqlite3.Connection) -> dict[str, int]:
    return {r["osis"]: r["id"] for r in con.execute("SELECT id, osis FROM book")}
