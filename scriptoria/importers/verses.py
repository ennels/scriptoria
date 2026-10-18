"""Install / remove translations.

Accepted JSON shapes:
  A) scrollmapper:  {"books":[{"name":"Genesis","chapters":[{"chapter":1,"verses":[{"verse":1,"text":".."}]}]}]}
  B) aruljohn:      {"book":"Genesis","chapters":[{"chapter":"1","verses":[{"verse":"1","text":".."}]}]}
  C) nested dict:   {"Genesis": {"1": {"1": "In the beginning..."}}}
  D) flat rows:     [{"book":"Genesis","chapter":1,"verse":1,"text":".."}, ...]
  E) thiagobodruk:  [{"abbrev":"gn","chapters":[["v1","v2"],...]}, ...]  (66 books, by position)
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path

from ..books import BOOKS, to_osis
from . import VerseResolver

FTS_TABLES = {"en": "fts_en", "intl": "fts_intl", "cjk": "fts_cjk", "orig": "fts_orig"}


def rows_from_json(data) -> list[tuple[str, int, int, str]]:
    """(book OSIS or name, chapter, verse, text) rows from any supported shape."""
    rows: list[tuple[str, int, int, str]] = []

    def add(book, ch, vs, text):
        if text is None:
            return
        text = unicodedata.normalize("NFC", str(text)).strip()   # one spelling per character
        if text:
            rows.append((str(book), int(ch), int(vs), text))

    if (isinstance(data, list) and data and isinstance(data[0], dict)
            and isinstance(data[0].get("chapters"), list) and data[0]["chapters"]
            and isinstance(data[0]["chapters"][0], list)):
        for i, book in enumerate(data[:len(BOOKS)]):          # E) by canonical position
            for ci, chap in enumerate(book["chapters"]):
                for vi, text in enumerate(chap):
                    add(BOOKS[i]["osis"], ci + 1, vi + 1, text)
        return rows
    if isinstance(data, list):                                  # D
        for r in data:
            add(r["book"], r["chapter"], r["verse"], r.get("text"))
        return rows
    if isinstance(data, dict) and "books" in data:              # A
        for bk in data["books"]:
            for cp in bk["chapters"]:
                for v in cp["verses"]:
                    add(bk["name"], cp["chapter"], v["verse"], v.get("text"))
        return rows
    if isinstance(data, dict) and "book" in data and "chapters" in data:   # B
        for cp in data["chapters"]:
            for v in cp["verses"]:
                add(data["book"], cp["chapter"], v["verse"], v.get("text"))
        return rows
    if isinstance(data, dict):                                  # C
        for book, chapters in data.items():
            if isinstance(chapters, dict):
                for ch, verses in chapters.items():
                    if isinstance(verses, dict):
                        for vs, text in verses.items():
                            add(book, ch, vs, text)
        return rows
    raise ValueError("Unrecognized verse-JSON shape")


def remove_translation(con: sqlite3.Connection, code: str) -> bool:
    r = con.execute("SELECT id, fts FROM translation WHERE code=?", (code,)).fetchone()
    if not r:
        return False
    tid, fts = r[0], FTS_TABLES.get(r[1], "fts_en")
    if fts == "fts_orig":           # own-content index: rows are deleted directly
        con.execute("DELETE FROM fts_orig WHERE rowid IN (SELECT id FROM verse_text WHERE translation_id=?)", (tid,))
    else:                           # external-content index: tell FTS which text to remove
        con.execute(f"INSERT INTO {fts}({fts}, rowid, text) "
                    "SELECT 'delete', id, text FROM verse_text WHERE translation_id=?", (tid,))
    con.execute("DELETE FROM verse_text WHERE translation_id=?", (tid,))
    con.execute("DELETE FROM translation WHERE id=?", (tid,))
    con.commit()
    return True


def install_rows(con: sqlite3.Connection, rows, *, code: str, name: str, language: str = "en",
                 language_name: str = "English", direction: str = "ltr", fts: str = "en",
                 kind: str = "text", source: str = "", license: str = "") -> dict:
    """Replace translation `code` with `rows` of (book, chapter, verse, text)."""
    remove_translation(con, code)
    cur = con.execute(
        "INSERT INTO translation(code,name,language,language_name,direction,kind,fts,source,license)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (code, name, language, language_name, direction, kind, fts, source, license))
    tid = cur.lastrowid
    vr = VerseResolver(con)
    batch, unknown = [], set()
    for book, ch, vs, text in rows:
        osis = to_osis(book)
        if osis is None:
            unknown.add(book)
            continue
        vid = vr.resolve(f"{osis}.{ch}.{vs}")
        if vid is not None:
            batch.append((tid, vid, text))
    con.executemany("INSERT OR REPLACE INTO verse_text(translation_id, verse_id, text) VALUES(?,?,?)", batch)
    table = FTS_TABLES.get(fts, "fts_en")
    con.execute(f"INSERT INTO {table}(rowid, text) SELECT id, text FROM verse_text WHERE translation_id=?", (tid,))
    n = con.execute("SELECT COUNT(*) FROM verse_text WHERE translation_id=?", (tid,)).fetchone()[0]
    con.execute("UPDATE translation SET verses=? WHERE id=?", (n, tid))
    con.commit()
    return {"translation": code, "verses": n, "unknown_books": sorted(unknown)}


def import_translation(con: sqlite3.Connection, path: str | Path, code: str, name: str, **meta) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    rows = rows_from_json(data)
    if not rows:
        raise ValueError(f"No verses parsed from {path}")
    return install_rows(con, rows, code=code, name=name, **meta)
