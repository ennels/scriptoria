"""Scriptoria backend: a small FastAPI app over the SQLite study database,
plus the static browser UI. Read-only for scripture data; notes are read/write."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .books import to_osis
from .db import DEFAULT_DB

WEB = Path(__file__).resolve().parent / "web"
app = FastAPI(title="Scriptoria")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DEFAULT_DB}?mode=rwc", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def ref_label(con, osis: str) -> str:
    r = con.execute(
        "SELECT b.name, v.chapter, v.verse FROM verse v JOIN book b ON b.id=v.book_id WHERE v.osis=?",
        (osis,)).fetchone()
    return f"{r['name']} {r['chapter']}:{r['verse']}" if r else osis


# --------------------------------------------------------------------- metadata
@app.get("/api/translations")
def translations():
    con = db()
    rows = con.execute(
        "SELECT t.code, t.name, t.language, COUNT(vt.verse_id) AS verses "
        "FROM translation t LEFT JOIN verse_text vt ON vt.translation_id=t.id "
        "GROUP BY t.id ORDER BY t.language, t.code").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/books")
def books():
    con = db()
    return [dict(r) for r in con.execute(
        "SELECT osis, name, testament, chapters FROM book ORDER BY id")]


# --------------------------------------------------------------------- reading
@app.get("/api/chapter")
def chapter(book: str, chapter: int, translations: str = "KJV"):
    """Parallel verses for one chapter. `translations` is a comma list of codes.
    Each verse carries flags so the UI can show, transparently, where
    original-language words and cross-references exist."""
    osis = to_osis(book)
    if not osis:
        raise HTTPException(404, f"Unknown book: {book}")
    codes = [c.strip().upper() for c in translations.split(",") if c.strip()]
    con = db()
    tmap = {r["code"]: r["id"] for r in con.execute("SELECT id, code FROM translation")}
    codes = [c for c in codes if c in tmap] or [next(iter(tmap), "KJV")]

    verses = con.execute(
        "SELECT v.id, v.osis, v.verse FROM verse v JOIN book b ON b.id=v.book_id "
        "WHERE b.osis=? AND v.chapter=? ORDER BY v.verse", (osis, chapter)).fetchall()
    if not verses:
        raise HTTPException(404, f"No such chapter: {book} {chapter}")
    ids = [v["id"] for v in verses]
    q = ",".join("?" * len(ids))

    texts: dict[int, dict[str, str]] = {v["id"]: {} for v in verses}
    for code in codes:
        for r in con.execute(
            f"SELECT verse_id, text FROM verse_text WHERE translation_id=? AND verse_id IN ({q})",
            (tmap[code], *ids)):
            texts[r["verse_id"]][code] = r["text"]
    with_orig = {r[0] for r in con.execute(
        f"SELECT DISTINCT verse_id FROM original_word WHERE verse_id IN ({q})", ids)}
    with_xref = {r[0] for r in con.execute(
        f"SELECT DISTINCT from_verse_id FROM cross_ref WHERE from_verse_id IN ({q})", ids)}

    return {
        "book": osis, "book_name": ref_label(con, verses[0]["osis"]).rsplit(" ", 1)[0],
        "chapter": chapter, "translations": codes,
        "verses": [{
            "osis": v["osis"], "verse": v["verse"],
            "texts": texts[v["id"]],
            "has_originals": v["id"] in with_orig,
            "has_xrefs": v["id"] in with_xref,
        } for v in verses],
    }


# --------------------------------------------------------------------- study
@app.get("/api/verse/{osis}/crossrefs")
def crossrefs(osis: str, translation: str = "KJV", limit: int = 40):
    con = db()
    tid_row = con.execute("SELECT id FROM translation WHERE code=?", (translation.upper(),)).fetchone()
    tid = tid_row["id"] if tid_row else None
    rows = con.execute(
        "SELECT tv.osis AS osis, x.votes AS votes FROM cross_ref x "
        "JOIN verse fv ON fv.id=x.from_verse_id JOIN verse tv ON tv.id=x.to_verse_id "
        "WHERE fv.osis=? ORDER BY x.votes DESC, tv.id LIMIT ?", (osis, limit)).fetchall()
    out = []
    for r in rows:
        text = None
        if tid:
            t = con.execute(
                "SELECT text FROM verse_text WHERE translation_id=? AND verse_id=(SELECT id FROM verse WHERE osis=?)",
                (tid, r["osis"])).fetchone()
            text = t["text"] if t else None
        out.append({"osis": r["osis"], "ref": ref_label(con, r["osis"]), "votes": r["votes"], "text": text})
    return {"osis": osis, "ref": ref_label(con, osis), "crossrefs": out}


@app.get("/api/verse/{osis}/interlinear")
def interlinear(osis: str):
    """Original-language words for a verse. If none map to this English verse
    number (OT versification differences), say so plainly."""
    con = db()
    rows = con.execute(
        "SELECT w.position, w.language, w.text, w.translit, w.gloss, w.strongs, w.strongs_raw, w.morph "
        "FROM original_word w JOIN verse v ON v.id=w.verse_id WHERE v.osis=? ORDER BY w.position",
        (osis,)).fetchall()
    return {
        "osis": osis, "ref": ref_label(con, osis),
        "words": [dict(r) for r in rows],
        "aligned": bool(rows),
        "note": None if rows else
            "No original-language words map to this verse number. Hebrew (Masoretic) "
            "versification differs from English here, mainly in Psalms, Malachi and a "
            "few other passages.",
    }


@app.get("/api/strongs/{sid}")
def strongs(sid: str):
    con = db()
    r = con.execute("SELECT * FROM strongs WHERE id=?", (sid.upper(),)).fetchone()
    if not r:
        raise HTTPException(404, f"No lexicon entry: {sid}")
    count = con.execute("SELECT COUNT(*) FROM original_word WHERE strongs=?", (sid.upper(),)).fetchone()[0]
    return {**dict(r), "occurrences": count}


@app.get("/api/search")
def search(q: str, translation: str = "KJV", limit: int = 100):
    con = db()
    tid = con.execute("SELECT id FROM translation WHERE code=?", (translation.upper(),)).fetchone()
    if not tid:
        raise HTTPException(404, f"Unknown translation: {translation}")
    try:
        rows = con.execute(
            "SELECT v.osis AS osis, snippet(verse_fts, 0, '<mark>', '</mark>', ' … ', 12) AS snip "
            "FROM verse_fts f JOIN verse v ON v.id=f.verse_id "
            "WHERE verse_fts MATCH ? AND f.translation_id=? ORDER BY v.id LIMIT ?",
            (q, tid["id"], limit)).fetchall()
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad search query: {e}")
    return {"query": q, "translation": translation.upper(),
            "count": len(rows),
            "results": [{"osis": r["osis"], "ref": ref_label(con, r["osis"]), "snippet": r["snip"]} for r in rows]}


# --------------------------------------------------------------------- notes
class NoteIn(BaseModel):
    osis: str
    color: str = ""
    body: str = ""


@app.get("/api/notes")
def list_notes():
    con = db()
    rows = con.execute(
        "SELECT n.id, v.osis, n.color, n.body, n.updated FROM note n JOIN verse v ON v.id=n.verse_id "
        "ORDER BY n.updated DESC").fetchall()
    return [{**dict(r), "ref": ref_label(con, r["osis"])} for r in rows]


@app.get("/api/notes/chapter")
def notes_for_chapter(book: str, chapter: int):
    """Notes/highlights for a chapter, keyed by osis — so the reader can tint verses."""
    osis = to_osis(book)
    con = db()
    rows = con.execute(
        "SELECT n.id, v.osis, n.color, n.body FROM note n JOIN verse v ON v.id=n.verse_id "
        "JOIN book b ON b.id=v.book_id WHERE b.osis=? AND v.chapter=?", (osis, chapter)).fetchall()
    return {r["osis"]: dict(r) for r in rows}


@app.post("/api/notes")
def upsert_note(note: NoteIn):
    con = db()
    v = con.execute("SELECT id FROM verse WHERE osis=?", (note.osis,)).fetchone()
    if not v:
        raise HTTPException(404, f"Unknown verse: {note.osis}")
    existing = con.execute("SELECT id FROM note WHERE verse_id=?", (v["id"],)).fetchone()
    if existing:
        if not note.color and not note.body:
            con.execute("DELETE FROM note WHERE id=?", (existing["id"],))
            con.commit()
            return {"deleted": existing["id"]}
        con.execute("UPDATE note SET color=?, body=?, updated=datetime('now') WHERE id=?",
                    (note.color, note.body, existing["id"]))
        con.commit()
        return {"id": existing["id"], "updated": True}
    cur = con.execute("INSERT INTO note(verse_id, color, body) VALUES(?,?,?)",
                      (v["id"], note.color, note.body))
    con.commit()
    return {"id": cur.lastrowid, "created": True}


# --------------------------------------------------------------------- static UI
if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")


def run():
    import uvicorn
    import webbrowser
    import threading
    url = "http://127.0.0.1:8701"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Scriptoria running at {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=8701, log_level="warning")


if __name__ == "__main__":
    run()
