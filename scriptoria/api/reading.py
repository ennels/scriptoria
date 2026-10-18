"""Reading: books, installed translations, chapters (with optional interlinear words),
and turning typed references into locations."""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import config, db as cdb, library
from ..books import BOOKS
from ..references import parse_reference
from ..text import reading_form
from .deps import BOOK, book_or_404, content, content_status, placeholders

router = APIRouter(prefix="/api")

TRANSLATION_COLS = "id, code, name, language, language_name, direction, kind, verses"


def translations_by_code(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["code"]: r for r in con.execute(f"SELECT {TRANSLATION_COLS} FROM translation")}


@router.get("/meta")
def meta():
    ok, msg = content_status()
    out = {"ready": ok, "message": msg, "content_db": str(config.content_db()),
           "user_db": str(config.user_db()), "library_source": None}
    src = library.local_source()
    out["library_source"] = str(src) if src else None
    if ok:
        con = cdb.connect(must_exist=True)
        try:
            out["built_at"] = cdb.get_meta(con, "built_at")
            out["schema_version"] = int(cdb.get_meta(con, "schema_version", 0))
            out["translations"] = con.execute("SELECT COUNT(*) FROM translation").fetchone()[0]
            out["original_words"] = con.execute("SELECT COUNT(*) FROM original_word").fetchone()[0]
        finally:
            con.close()
    return out


@router.get("/books")
def books():
    return [{"osis": b["osis"], "name": b["name"], "testament": b["testament"],
             "chapters": b["chapters"], "position": b["position"]} for b in BOOKS]


@router.get("/translations")
def translations(con: sqlite3.Connection = Depends(content)):
    rows = con.execute(f"SELECT {TRANSLATION_COLS} FROM translation "
                       "ORDER BY kind='original', language_name<>'English', language_name, code")
    return [dict(r) for r in rows]


@router.get("/resolve")
def resolve(q: str):
    ref = parse_reference(q)
    if not ref:
        return {"found": False, "query": q}
    return {"found": True, "book": ref.book, "chapter": ref.chapter, "verse": ref.verse,
            "verse_end": ref.verse_end, "osis": ref.osis, "label": ref.label()}


def _neighbors(osis: str, chapter: int) -> tuple[dict | None, dict | None]:
    pos = BOOK[osis]["position"]
    prev = nxt = None
    if chapter > 1:
        prev = {"book": osis, "chapter": chapter - 1}
    elif pos > 1:
        pb = BOOKS[pos - 2]
        prev = {"book": pb["osis"], "chapter": pb["chapters"]}
    if chapter < BOOK[osis]["chapters"]:
        nxt = {"book": osis, "chapter": chapter + 1}
    elif pos < len(BOOKS):
        nb = BOOKS[pos]
        nxt = {"book": nb["osis"], "chapter": 1}
    for n in (prev, nxt):
        if n:
            n["label"] = f"{BOOK[n['book']]['name']} {n['chapter']}"
    return prev, nxt


@router.get("/chapter")
def chapter(book: str, chapter: int, translations: str = "KJV",
            words: bool = Query(False, description="include original-language words per verse"),
            con: sqlite3.Connection = Depends(content)):
    b = book_or_404(book)
    if not 1 <= chapter <= b["chapters"]:
        raise HTTPException(404, f"{b['name']} has {b['chapters']} chapters")
    tmap = translations_by_code(con)
    codes = [c for c in dict.fromkeys(x.strip().upper() for x in translations.split(",") if x.strip())
             if c in tmap]
    if not codes:
        codes = ["KJV"] if "KJV" in tmap else [next(iter(tmap))]

    verses = con.execute(
        "SELECT v.id, v.osis, v.verse FROM verse v WHERE v.book_id=? AND v.chapter=? ORDER BY v.verse",
        (b["position"], chapter)).fetchall()
    ids = [v["id"] for v in verses]
    if not ids:
        raise HTTPException(404, f"No verses for {b['name']} {chapter}")
    ph = placeholders(len(ids))
    tids = {tmap[c]["id"]: c for c in codes}

    texts: dict[int, dict[str, str]] = defaultdict(dict)
    for r in con.execute(
            f"SELECT verse_id, translation_id, text FROM verse_text WHERE verse_id IN ({ph}) "
            f"AND translation_id IN ({placeholders(len(tids))})", (*ids, *tids)):
        texts[r["verse_id"]][tids[r["translation_id"]]] = r["text"]
    with_orig = {r[0] for r in con.execute(
        f"SELECT DISTINCT verse_id FROM original_word WHERE verse_id IN ({ph})", ids)}
    with_xref = {r[0] for r in con.execute(
        f"SELECT DISTINCT from_verse_id FROM cross_ref WHERE from_verse_id IN ({ph})", ids)}

    word_rows: dict[int, list] = defaultdict(list)
    if words:
        for r in con.execute(
                f"SELECT verse_id, position, language, text, translit, gloss, strongs, dstrong, morph, "
                f"lemma, text_type FROM original_word WHERE verse_id IN ({ph}) ORDER BY verse_id, position", ids):
            word_rows[r["verse_id"]].append({
                "p": r["position"], "lang": r["language"], "text": reading_form(r["text"]), "translit": r["translit"],
                "gloss": r["gloss"], "strongs": r["strongs"], "dstrong": r["dstrong"], "morph": r["morph"],
                "lemma": r["lemma"], "type": r["text_type"]})

    title_text = {}
    zero = [v["id"] for v in verses if v["verse"] == 0]
    if zero and "ORIG" in tmap:
        for r in con.execute(f"SELECT verse_id, text FROM verse_text WHERE translation_id=? AND verse_id IN "
                             f"({placeholders(len(zero))})", (tmap["ORIG"]["id"], *zero)):
            title_text[r["verse_id"]] = r["text"]

    out_verses = []
    for v in verses:
        vid = v["id"]
        if not texts.get(vid) and vid not in with_orig:
            continue
        item = {"osis": v["osis"], "verse": v["verse"], "texts": texts.get(vid, {}),
                "has_originals": vid in with_orig, "has_xrefs": vid in with_xref}
        if v["verse"] == 0:
            item["superscription"] = True
            item["title"] = title_text.get(vid)
        if words:
            item["words"] = word_rows.get(vid, [])
        out_verses.append(item)

    prev, nxt = _neighbors(b["osis"], chapter)
    return {
        "book": b["osis"], "book_name": b["name"], "testament": b["testament"],
        "chapter": chapter, "chapters": b["chapters"], "prev": prev, "next": nxt,
        "translations": [{k: tmap[c][k] for k in ("code", "name", "language", "language_name",
                                                    "direction", "kind")} for c in codes],
        "verses": out_verses,
    }
