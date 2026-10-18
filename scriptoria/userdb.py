"""User database: profiles, highlights, notes, tags and per-profile settings.

Kept apart from the content database so rebuilding or updating scripture data never
touches anyone's notes, and so it's one small file to back up. Notes and highlights
are keyed by OSIS reference ("John.3.16"), which stays stable across content rebuilds.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from . import config

# Append-only list; index + 1 is the schema version (PRAGMA user_version).
MIGRATIONS = [
    """
    CREATE TABLE profile (
      id       INTEGER PRIMARY KEY,
      name     TEXT NOT NULL,
      color    TEXT NOT NULL DEFAULT 'lapis',
      created  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE highlight (
      profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
      osis        TEXT NOT NULL,
      color       TEXT NOT NULL,
      updated     TEXT NOT NULL DEFAULT (datetime('now')),
      PRIMARY KEY (profile_id, osis)
    );
    CREATE TABLE note (
      id          INTEGER PRIMARY KEY,
      profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
      osis        TEXT NOT NULL,
      osis_end    TEXT,
      body        TEXT NOT NULL DEFAULT '',
      created     TEXT NOT NULL DEFAULT (datetime('now')),
      updated     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX note_profile_osis ON note(profile_id, osis);
    CREATE TABLE note_tag (
      note_id  INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
      tag      TEXT NOT NULL,
      PRIMARY KEY (note_id, tag)
    );
    CREATE INDEX note_tag_tag ON note_tag(tag);
    CREATE TABLE setting (
      profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
      key         TEXT NOT NULL,
      value       TEXT,
      PRIMARY KEY (profile_id, key)
    );
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """,
]

PROFILE_COLORS = ["lapis", "rubric", "gold", "sage", "plum", "teal"]
_migrated: set[str] = set()
_lock = threading.Lock()


def migrate(con: sqlite3.Connection) -> int:
    version = con.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        con.executescript(f"BEGIN; {sql}; PRAGMA user_version = {i}; COMMIT;")
    return len(MIGRATIONS)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or config.user_db())
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    key = str(p.resolve())
    if key not in _migrated:
        with _lock:
            con.execute("PRAGMA journal_mode = WAL")
            migrate(con)
            ensure_default_profile(con)
            _migrated.add(key)
    return con


def ensure_default_profile(con: sqlite3.Connection) -> int:
    r = con.execute("SELECT id FROM profile ORDER BY id LIMIT 1").fetchone()
    if r:
        return r["id"]
    pid = con.execute("INSERT INTO profile(name, color) VALUES('Reader', 'lapis')").lastrowid
    con.commit()
    return pid


def default_profile(con: sqlite3.Connection) -> int:
    return ensure_default_profile(con)


def import_legacy_notes(user: sqlite3.Connection, content_path: str | Path) -> int:
    """Carry notes/highlights from a first-release database (notes lived in the content DB)
    into the first profile. Runs once per content file."""
    content_path = Path(content_path)
    if not content_path.exists():
        return 0
    marker = f"legacy_import:{content_path.resolve()}"
    if user.execute("SELECT 1 FROM meta WHERE key=?", (marker,)).fetchone():
        return 0
    from .db import uri_for
    try:
        src = sqlite3.connect(uri_for(content_path, "ro"), uri=True)
    except sqlite3.Error:
        return 0                                   # unreadable now; try again next start
    try:
        has_notes = src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='note'").fetchone()
        rows = src.execute("SELECT v.osis, n.color, n.body, n.created, n.updated FROM note n "
                           "JOIN verse v ON v.id = n.verse_id").fetchall() if has_notes else []
    except sqlite3.Error:
        return 0
    finally:
        src.close()
    pid = default_profile(user)
    for osis, color, body, created, updated in rows:
        if color:
            user.execute("INSERT OR REPLACE INTO highlight(profile_id, osis, color) VALUES(?,?,?)",
                         (pid, osis, color))
        if body and body.strip():
            user.execute("INSERT INTO note(profile_id, osis, body, created, updated) VALUES(?,?,?,?,?)",
                         (pid, osis, body, created, updated))
    user.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (marker, str(len(rows))))
    user.commit()
    return len(rows)
