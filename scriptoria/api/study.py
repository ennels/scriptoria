"""Study: cross-references, interlinear with parsing and variants, word study + concordance."""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..importers.originals import describe_alt_ref, describe_text_type
from ..morph import expand_many
from ..text import display_form, dstrong as norm_dstrong, reading_form, strongs_base
from .deps import BOOK, content, placeholders, ref_label

router = APIRouter(prefix="/api")


def _translation_id(con: sqlite3.Connection, code: str | None) -> int | None:
    if not code:
        return None
    r = con.execute("SELECT id FROM translation WHERE code=?", (code.upper(),)).fetchone()
    return r[0] if r else None


@router.get("/verse/{osis}/crossrefs")
def crossrefs(osis: str, translation: str = "KJV", limit: int = Query(40, le=200),
              con: sqlite3.Connection = Depends(content)):
    tid = _translation_id(con, translation)
    rows = con.execute(
        "SELECT tv.osis AS osis, te.osis AS end_osis, x.votes AS votes, vt.text AS text "
        "FROM cross_ref x JOIN verse fv ON fv.id = x.from_verse_id "
        "JOIN verse tv ON tv.id = x.to_verse_id LEFT JOIN verse te ON te.id = x.to_end_id "
        "LEFT JOIN verse_text vt ON vt.verse_id = x.to_verse_id AND vt.translation_id = ? "
        "WHERE fv.osis = ? ORDER BY x.votes DESC, tv.id LIMIT ?", (tid, osis, limit)).fetchall()
    return {"osis": osis, "ref": ref_label(osis), "translation": translation.upper(),
            "crossrefs": [{"osis": r["osis"], "end": r["end_osis"], "votes": r["votes"],
                           "ref": ref_label(r["osis"], r["end_osis"]), "text": r["text"]} for r in rows]}


def _lexicon_for(con: sqlite3.Connection, ids: set[str]) -> dict[str, sqlite3.Row]:
    if not ids:
        return {}
    rows = con.execute(f"SELECT dstrong, strongs, lemma, translit, gloss FROM lexicon "
                       f"WHERE dstrong IN ({placeholders(len(ids))})", list(ids)).fetchall()
    out = {r["dstrong"]: r for r in rows}
    missing = {strongs_base(i) for i in ids if i not in out}
    if missing:
        for r in con.execute(f"SELECT dstrong, strongs, lemma, translit, gloss FROM lexicon "
                             f"WHERE strongs IN ({placeholders(len(missing))}) ORDER BY dstrong", list(missing)):
            out.setdefault(r["strongs"], r)
    return out


@router.get("/verse/{osis}/interlinear")
def interlinear(osis: str, con: sqlite3.Connection = Depends(content)):
    rows = con.execute(
        "SELECT w.* FROM original_word w JOIN verse v ON v.id = w.verse_id WHERE v.osis = ? "
        "ORDER BY w.position", (osis,)).fetchall()
    parsing = expand_many(con, [(r["morph"], r["language"]) for r in rows])
    lex = _lexicon_for(con, {r["dstrong"] for r in rows if r["dstrong"]})
    numbering: list[str] = []
    words = []
    for r in rows:
        alt = describe_alt_ref(r["alt_ref"], r["language"])
        for a in alt:
            if a not in numbering:
                numbering.append(a)
        lx = lex.get(r["dstrong"]) or lex.get(r["strongs"])
        words.append({
            "position": r["position"], "language": r["language"], "text": r["text"],
            "display": reading_form(r["text"]),
            "translit": r["translit"], "gloss": r["gloss"], "meaning": r["meaning"],
            "lemma": r["lemma"] or (lx["lemma"] if lx else None),
            "lemma_gloss": lx["gloss"] if lx else None,
            "strongs": r["strongs"], "dstrong": r["dstrong"], "strongs_raw": r["strongs_raw"],
            "morph": r["morph"], "parsing": parsing.get(r["morph"]),
            "variant": describe_text_type(r["text_type"], r["language"]),
            "variant_text": r["variants"], "editions": r["editions"],
        })
    note = None
    if not rows:
        note = ("No Hebrew or Greek words are numbered as this verse. This translation numbers verses "
                "differently here; the original words appear under a neighbouring verse.")
    elif numbering:
        note = "Numbering differs here — " + "; ".join(numbering) + "."
    return {"osis": osis, "ref": ref_label(osis), "aligned": bool(rows), "note": note,
            "language": rows[0]["language"] if rows else None, "words": words}


@router.get("/morph/{code:path}")
def morph(code: str, language: str = "greek", con: sqlite3.Connection = Depends(content)):
    out = expand_many(con, [(code, language)])
    if code not in out:
        raise HTTPException(404, f"Unknown morphology code: {code}")
    return out[code]


# --------------------------------------------------------------------- word study
def _word_filter(wid: str) -> tuple[str, str, str | None]:
    """'H7225G' -> ('strongs','H7225','H7225G'); 'g26' -> ('strongs','G26',None)."""
    ds = norm_dstrong(wid)
    base = strongs_base(wid)
    if not base:
        raise HTTPException(404, f"Not a Strong's number: {wid}")
    return "strongs", base, (ds if ds and ds != base else None)


@router.get("/word/{wid}")
def word_study(wid: str, con: sqlite3.Connection = Depends(content)):
    _, base, ds = _word_filter(wid)
    entries = [dict(r) for r in con.execute(
        "SELECT dstrong, strongs, language, lemma, translit, pos, gloss, definition, relation "
        "FROM lexicon WHERE strongs = ? ORDER BY dstrong", (base,))]
    strongs = con.execute("SELECT * FROM strongs WHERE id = ?", (base,)).fetchone()
    occ = con.execute("SELECT text, morph, gloss, dstrong, language FROM original_word WHERE strongs = ?",
                      (base,)).fetchall()
    if not entries and not strongs and not occ:
        raise HTTPException(404, f"No lexicon entry for {wid}")
    language = (entries[0]["language"] if entries else occ[0]["language"] if occ else
                ("greek" if base.startswith("G") else "hebrew"))

    forms: dict[str, Counter] = defaultdict(Counter)
    form_count: Counter = Counter()
    glosses: Counter = Counter()
    senses: Counter = Counter()
    for r in occ:
        f = display_form(r["text"], language)
        form_count[f] += 1
        forms[f][r["morph"]] += 1
        g = (r["gloss"] or "").replace("/", " ").replace("<", "").replace(">", "")
        g = " ".join(g.split()).strip(" .,;:!?·—")
        if g:
            glosses[g] += 1
        senses[r["dstrong"]] += 1
    top_forms = form_count.most_common(40)
    parsing = expand_many(con, [(forms[f].most_common(1)[0][0], language) for f, _ in top_forms])
    by_book = [{"osis": r[0], "name": BOOK[r[0]]["name"], "testament": BOOK[r[0]]["testament"], "count": r[1]}
               for r in con.execute(
                   "SELECT b.osis, COUNT(*) FROM original_word w JOIN verse v ON v.id = w.verse_id "
                   "JOIN book b ON b.id = v.book_id WHERE w.strongs = ? GROUP BY b.id ORDER BY b.id", (base,))]
    verses = con.execute("SELECT COUNT(DISTINCT verse_id) FROM original_word WHERE strongs = ?", (base,)).fetchone()[0]
    primary = next((e for e in entries if e["dstrong"] == ds), entries[0] if entries else None)
    return {
        "id": ds or base, "strongs": base, "language": language,
        "lemma": (primary or {}).get("lemma") or (strongs["lemma"] if strongs else None),
        "translit": (primary or {}).get("translit") or (strongs["translit"] if strongs else None),
        "gloss": (primary or {}).get("gloss"), "pos": (primary or {}).get("pos"),
        "pronounce": strongs["pronounce"] if strongs else None,
        "senses": [{**e, "count": senses.get(e["dstrong"], 0)} for e in entries],
        "strongs_entry": dict(strongs) if strongs else None,
        "occurrences": len(occ), "verses": verses,
        "forms": [{"form": f, "count": n, "morph": forms[f].most_common(1)[0][0],
                   "parsing": (parsing.get(forms[f].most_common(1)[0][0]) or {}).get("label")}
                  for f, n in top_forms],
        "glosses": [{"gloss": g, "count": n} for g, n in glosses.most_common(25)],
        "by_book": by_book,
    }


@router.get("/word/{wid}/occurrences")
def occurrences(wid: str, translation: str = "KJV", book: str | None = None, sense: str | None = None,
                offset: int = 0, limit: int = Query(40, le=200), con: sqlite3.Connection = Depends(content)):
    _, base, _ = _word_filter(wid)
    where, args = ["w.strongs = ?"], [base]
    if book:
        if book not in BOOK:
            raise HTTPException(404, f"Unknown book: {book}")
        where.append("v.book_id = ?")
        args.append(BOOK[book]["position"])
    if sense:
        where.append("w.dstrong = ?")
        args.append(norm_dstrong(sense))
    w_sql = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(DISTINCT w.verse_id) FROM original_word w JOIN verse v ON v.id = w.verse_id "
                        f"WHERE {w_sql}", args).fetchone()[0]
    vrows = con.execute(f"SELECT v.id, v.osis FROM original_word w JOIN verse v ON v.id = w.verse_id WHERE {w_sql} "
                        f"GROUP BY v.id ORDER BY v.id LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
    ids = [r["id"] for r in vrows]
    tid = _translation_id(con, translation)
    texts, hits = {}, defaultdict(list)
    if ids:
        ph = placeholders(len(ids))
        if tid:
            texts = {r[0]: r[1] for r in con.execute(
                f"SELECT verse_id, text FROM verse_text WHERE translation_id = ? AND verse_id IN ({ph})", (tid, *ids))}
        for r in con.execute(f"SELECT verse_id, text, gloss, morph FROM original_word WHERE strongs = ? "
                             f"AND verse_id IN ({ph}) ORDER BY verse_id, position", (base, *ids)):
            hits[r[0]].append({"text": reading_form(r[1]), "gloss": r[2], "morph": r[3]})
    return {"strongs": base, "total": total, "offset": offset, "limit": limit,
            "results": [{"osis": r["osis"], "ref": ref_label(r["osis"]), "text": texts.get(r["id"]),
                         "words": hits.get(r["id"], [])} for r in vrows]}
