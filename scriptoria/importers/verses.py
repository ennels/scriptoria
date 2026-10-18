"""Import a translation's verses from JSON.

Handles the common shapes so your downloaded multi-translation file, or a
single-translation file, both work:

  A) scrollmapper:  {"translation": "...", "books":[{"name":"Genesis",
                     "chapters":[{"chapter":1,"verses":[{"verse":1,"text":"..."}]}]}]}
  B) aruljohn:      {"book":"Genesis","chapters":[{"chapter":"1",
                     "verses":[{"verse":"1","text":"..."}]}]}   (one book per file)
  C) nested dict:   {"Genesis": {"1": {"1": "In the beginning..."}}}
  D) flat rows:     [{"book":"Genesis","chapter":1,"verse":1,"text":"..."}, ...]

Pass the translation code/name explicitly; book names are normalized via books.to_osis,
so unrecognized books are reported rather than silently dropped.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..books import to_osis
from . import VerseResolver


def _rows_from_json(data) -> list[tuple[str, int, int, str]]:
    """Return (book_name, chapter, verse, text) rows from any supported shape."""
    rows: list[tuple[str, int, int, str]] = []

    def add(book, ch, vs, text):
        if text is None:
            return
        rows.append((str(book), int(ch), int(vs), str(text)))

    if isinstance(data, list):  # D) flat rows
        for r in data:
            add(r["book"], r["chapter"], r["verse"], r.get("text"))
        return rows

    if isinstance(data, dict) and "books" in data:  # A) scrollmapper
        for bk in data["books"]:
            for cp in bk["chapters"]:
                for v in cp["verses"]:
                    add(bk["name"], cp["chapter"], v["verse"], v.get("text"))
        return rows

    if isinstance(data, dict) and "book" in data and "chapters" in data:  # B) aruljohn
        for cp in data["chapters"]:
            for v in cp["verses"]:
                add(data["book"], cp["chapter"], v["verse"], v.get("text"))
        return rows

    if isinstance(data, dict):  # C) nested dict book->chapter->verse->text
        for book, chapters in data.items():
            if not isinstance(chapters, dict):
                continue
            for ch, verses in chapters.items():
                if not isinstance(verses, dict):
                    continue
                for vs, text in verses.items():
                    add(book, ch, vs, text)
        return rows

    raise ValueError("Unrecognized verse-JSON shape")


def import_translation(
    con: sqlite3.Connection, path: str | Path, code: str, name: str,
    language: str = "en", license: str = "",
) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = _rows_from_json(data)
    if not rows:
        raise ValueError(f"No verses parsed from {path}")

    con.execute(
        "INSERT OR IGNORE INTO translation(code, name, language, license) VALUES(?,?,?,?)",
        (code, name, language, license),
    )
    tid = con.execute("SELECT id FROM translation WHERE code=?", (code,)).fetchone()["id"]
    con.execute("DELETE FROM verse_text WHERE translation_id=?", (tid,))  # re-import = replace

    vr = VerseResolver(con)
    inserted, unknown = 0, set()
    for book, ch, vs, text in rows:
        if to_osis(book) is None:
            unknown.add(book)
            continue
        vid = vr.resolve(f"{to_osis(book)}.{ch}.{vs}")
        if vid is None:
            continue
        con.execute(
            "INSERT OR REPLACE INTO verse_text(translation_id, verse_id, text) VALUES(?,?,?)",
            (tid, vid, text),
        )
        con.execute(
            "INSERT INTO verse_fts(text, translation_id, verse_id) VALUES(?,?,?)",
            (text, tid, vid),
        )
        inserted += 1
    con.commit()
    return {"translation": code, "verses": inserted, "unknown_books": sorted(unknown)}
