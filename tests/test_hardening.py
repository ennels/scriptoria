"""Regression tests for the issues an independent review found before v2 shipped."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import needs_db
from scriptoria import userdb

pytestmark = needs_db


@pytest.fixture
def bare():
    from scriptoria.server import app
    with TestClient(app) as c:
        yield c


def test_writes_need_the_app_header(bare):
    r = bare.post("/api/profiles", json={"name": "Mallory"})
    assert r.status_code == 403
    assert bare.get("/api/translations").status_code == 200            # reads are fine


def test_foreign_origin_and_host_refused(client):
    assert client.post("/api/profiles", json={"name": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/notes/export", headers={"Host": "evil.example"}).status_code == 400   # DNS rebinding
    assert client.get("/api/meta", headers={"Origin": "http://127.0.0.1:8701"}).status_code == 200


def test_stale_profile_is_refused_not_redirected(client):
    pid = client.post("/api/profiles", json={"name": "Carol"}).json()["id"]
    assert client.delete(f"/api/profiles/{pid}").status_code == 200
    r = client.post("/api/notes", json={"osis": "John.1.1", "body": "x"}, headers={"X-Profile": str(pid)})
    assert r.status_code == 409 and "PROFILE_GONE" in r.json()["detail"]
    assert client.get("/api/notes", params={"osis": "John.1.1"}).json()["total"] == 0   # nothing leaked into profile 1
    assert client.get("/api/notes", headers={"X-Profile": "\u00b2".encode("latin-1")}).status_code == 400   # '²'.isdigit()
    assert client.get("/api/profiles", headers={"X-Profile": str(pid)}).status_code == 200   # recovery path works


def test_profile_names_and_note_search(client):
    assert client.post("/api/profiles", json={"name": "   "}).status_code == 422
    assert client.post("/api/profiles", json={"name": "  Ann   Lee "}).json()["name"] == "Ann Lee"
    client.post("/api/notes", json={"osis": "John.1.1", "body": "In the beginning"})
    client.post("/api/notes", json={"osis": "John.1.2", "body": "100% sure"})
    assert client.get("/api/notes", params={"q": "%"}).json()["total"] == 1
    assert client.get("/api/notes", params={"q": "_"}).json()["total"] == 0


def test_limits_are_bounded(client):
    assert client.get("/api/word/G2532/occurrences", params={"limit": -1}).status_code == 422
    assert client.get("/api/verse/John.3.16/crossrefs", params={"limit": 0}).status_code == 422


@pytest.mark.parametrize("params,label", [
    ({"q": "λόγος θεοῦ"}, "smart mode, two Greek words"),
    ({"q": "בְּרֵאשִׁית", "translations": "ORIG", "mode": "all"}, "pointed Hebrew, all words"),
    ({"q": "λογος OR ρημα", "translations": "ORIG", "mode": "advanced"}, "advanced OR on Greek"),
])
def test_original_language_search_gaps(client, params, label):
    d = client.get("/api/search", params=params).json()
    assert d.get("total", 0) > 0, label


def test_lexicon_html_cleaned_when_served(client, content_copy):
    con = sqlite3.connect(content_copy)
    con.execute("UPDATE lexicon SET definition = '<img src=x onerror=alert(1)><script>x()</script><b>ok</b>' "
                "WHERE dstrong = 'G26'")
    con.commit()
    con.close()
    d = client.get("/api/word/G26").json()
    html = next(s for s in d["senses"] if s["dstrong"] == "G26")["definition"]
    assert "<img" not in html and "<script" not in html and "<b>ok</b>" in html


def test_paths_with_hash_and_legacy_import_retry(tmp_path):
    folder = tmp_path / "C#" / "x?y"
    folder.mkdir(parents=True)
    old = folder / "old.db"
    c = sqlite3.connect(old)
    c.executescript("""
      CREATE TABLE verse(id INTEGER PRIMARY KEY, osis TEXT, book_id INT, chapter INT, verse INT);
      CREATE TABLE note(id INTEGER PRIMARY KEY, verse_id INT, color TEXT, body TEXT,
                        created TEXT DEFAULT (datetime('now')), updated TEXT DEFAULT (datetime('now')));
      INSERT INTO verse VALUES (1, 'Rom.8.28', 45, 8, 28);
      INSERT INTO note(verse_id, color, body) VALUES (1, 'sage', 'all things');""")
    c.commit()
    c.close()
    u = userdb.connect(tmp_path / "u.db")
    assert userdb.import_legacy_notes(u, old) == 1
    assert not (tmp_path / "C").exists()                       # no stray file from a truncated URI
    missing = folder / "not-there.db"
    assert userdb.import_legacy_notes(u, missing) == 0
    assert not u.execute("SELECT 1 FROM meta WHERE key LIKE ?", (f"%{missing.name}",)).fetchone()   # not marked done


def test_build_keeps_first_release_notes(tmp_path, monkeypatch):
    """Rebuilding over a first-release database must carry its notes over first."""
    from scriptoria import build
    old = tmp_path / "scriptoria.db"
    c = sqlite3.connect(old)
    c.executescript("""
      CREATE TABLE verse(id INTEGER PRIMARY KEY, osis TEXT, book_id INT, chapter INT, verse INT);
      CREATE TABLE note(id INTEGER PRIMARY KEY, verse_id INT, color TEXT, body TEXT,
                        created TEXT DEFAULT (datetime('now')), updated TEXT DEFAULT (datetime('now')));
      INSERT INTO verse VALUES (1, 'John.3.16', 43, 3, 16);
      INSERT INTO note(verse_id, color, body) VALUES (1, 'amber', 'keep me');""")
    c.commit()
    c.close()
    monkeypatch.setattr(build, "SOURCES", {})
    monkeypatch.setattr(build, "fetch", lambda *a: (_ for _ in ()).throw(SystemExit("stop after the notes step")))
    with pytest.raises((SystemExit, KeyError)):
        build.main(["--db", str(old), "--no-originals"])
    u = userdb.connect()
    assert [r[0] for r in u.execute("SELECT body FROM note")] == ["keep me"]
