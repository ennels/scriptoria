"""User database: migrations, default profile, and carrying notes over from the first release."""
from __future__ import annotations

import sqlite3

from scriptoria import userdb


def test_migrations_idempotent(tmp_path):
    p = tmp_path / "u.db"
    con = userdb.connect(p)
    assert con.execute("PRAGMA user_version").fetchone()[0] == len(userdb.MIGRATIONS)
    assert userdb.migrate(con) == len(userdb.MIGRATIONS)          # second run is a no-op
    assert con.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 1
    con.close()


def test_profile_delete_cascades(tmp_path):
    con = userdb.connect(tmp_path / "u.db")
    pid = con.execute("INSERT INTO profile(name) VALUES('B')").lastrowid
    nid = con.execute("INSERT INTO note(profile_id, osis, body) VALUES(?, 'John.1.1', 'x')", (pid,)).lastrowid
    con.execute("INSERT INTO note_tag(note_id, tag) VALUES(?, 't')", (nid,))
    con.execute("INSERT INTO highlight(profile_id, osis, color) VALUES(?, 'John.1.1', 'amber')", (pid,))
    con.commit()
    con.execute("DELETE FROM profile WHERE id=?", (pid,))
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM note").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM note_tag").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM highlight").fetchone()[0] == 0


def _legacy_db(path):
    c = sqlite3.connect(path)
    c.executescript("""
      CREATE TABLE verse(id INTEGER PRIMARY KEY, osis TEXT, book_id INT, chapter INT, verse INT);
      CREATE TABLE note(id INTEGER PRIMARY KEY, verse_id INT, color TEXT, body TEXT,
                        created TEXT DEFAULT (datetime('now')), updated TEXT DEFAULT (datetime('now')));
      INSERT INTO verse VALUES (1, 'John.3.16', 43, 3, 16), (2, 'Rom.8.28', 45, 8, 28);
      INSERT INTO note(verse_id, color, body) VALUES (1, 'amber', 'hinge of the gospel'), (2, 'sky', '');
    """)
    c.commit()
    c.close()


def test_legacy_notes_import_once(tmp_path):
    legacy = tmp_path / "old.db"
    _legacy_db(legacy)
    con = userdb.connect(tmp_path / "u.db")
    assert userdb.import_legacy_notes(con, legacy) == 2
    assert userdb.import_legacy_notes(con, legacy) == 0                # only once
    hl = dict(con.execute("SELECT osis, color FROM highlight").fetchall())
    assert hl == {"John.3.16": "amber", "Rom.8.28": "sky"}
    assert [r[0] for r in con.execute("SELECT body FROM note")] == ["hinge of the gospel"]


def test_legacy_import_tolerates_new_db(tmp_path):
    p = tmp_path / "new.db"
    sqlite3.connect(p).execute("CREATE TABLE meta(key TEXT, value TEXT)").connection.close()
    con = userdb.connect(tmp_path / "u.db")
    assert userdb.import_legacy_notes(con, p) == 0
    assert userdb.import_legacy_notes(con, tmp_path / "missing.db") == 0
