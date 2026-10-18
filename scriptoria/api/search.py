"""Search.

Text modes (any installed translations, grouped by their search index):
  all       every word must appear            love neighbour
  phrase    exact phrase                       "love your neighbour"
  any       any of the words                   grace mercy
  advanced  SQLite FTS5 syntax: AND OR NOT NEAR(), prefix*, ^start
Original-language mode (auto-detected for Strong's numbers and Greek/Hebrew script):
  G26 / H7225G       a Strong's number (a lettered one narrows to one sense)
  ἀγάπη / אהב        a dictionary form -> every inflection; otherwise that exact form
  agape / reshit     a transliterated dictionary form
Scope: all | ot | nt | a book (Rom) | a range (Matt-John).
A query that is a Bible reference ('jn 3:16') returns {"reference": ...} instead.
"""
from __future__ import annotations

import html
import re
import unicodedata
import sqlite3
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query

from ..references import parse_reference
from ..text import dstrong as norm_dstrong, fold, is_original_script, reading_form
from .deps import BOOK, book_or_404, content, placeholders, ref_label

router = APIRouter(prefix="/api")

FTS = {"en": "fts_en", "intl": "fts_intl", "cjk": "fts_cjk", "orig": "fts_orig"}
MODES = ("auto", "all", "phrase", "any", "advanced", "original")
_OPEN, _CLOSE = "\x01", "\x02"
_STRONGS = re.compile(r"^([GHgh])0*(\d+)([A-Za-z]?)$")
_TOKEN = re.compile(r"[\w'’\u0300-\u036f\u0591-\u05c7\u1dc0-\u1dff]+\*?")
_OPERATORS = {"AND", "OR", "NOT"}


def tokens(q: str) -> list[str]:
    return _TOKEN.findall(q)


def _quote(t: str) -> str:
    star = t.endswith("*")
    t = t.rstrip("*").replace('"', '""')
    return f'"{t}"' + ("*" if star else "")


def fts_expression(q: str, mode: str) -> str:
    if mode == "advanced":
        if not q.strip():
            raise HTTPException(400, "Type something to search for.")
        return q.strip()
    toks = tokens(q)
    if not toks:
        raise HTTPException(400, "Type at least one word to search for.")
    if mode == "phrase":
        return '"' + " ".join(t.rstrip("*") for t in toks).replace('"', '""') + '"'
    if mode == "any":
        return " OR ".join(_quote(t) for t in toks)
    return " ".join(_quote(t) for t in toks)


def scope_range(scope: str | None) -> tuple[int, int, str]:
    s = (scope or "all").strip()
    low = s.lower()
    if low in ("", "all"):
        return 1, 66, "Whole Bible"
    if low == "ot":
        return 1, 39, "Old Testament"
    if low == "nt":
        return 40, 66, "New Testament"
    if "-" in s:
        a, b = (book_or_404(x) for x in s.split("-", 1))
        lo, hi = sorted((a["position"], b["position"]))
        return lo, hi, f"{BOOK_BY_POS[lo]['name']} – {BOOK_BY_POS[hi]['name']}"
    b = book_or_404(s)
    return b["position"], b["position"], b["name"]


BOOK_BY_POS = {b["position"]: b for b in BOOK.values()}


def snippet_html(s: str | None) -> str:
    s = html.escape(s or "", quote=False)
    return s.replace(_OPEN, "<mark>").replace(_CLOSE, "</mark>")


def _like_snippet(text: str, toks: list[str]) -> str:
    out = text
    for t in toks:
        t = t.rstrip("*")
        if t:
            out = out.replace(t, f"{_OPEN}{t}{_CLOSE}")
    return out


def _orig_terms(q: str, mode: str) -> tuple[str, list[tuple[str, bool]]]:
    """Folded FTS expression for the Hebrew/Greek index, plus the terms for highlighting.
    Advanced mode keeps AND/OR/NOT/NEAR and quotes, folding only the words."""
    terms = [(fold(t.rstrip("*")), t.endswith("*")) for t in tokens(q) if t not in _OPERATORS and t != "NEAR"]
    terms = [(t, star) for t, star in terms if t]
    if not terms:
        raise HTTPException(400, "Type at least one Hebrew or Greek word to search for.")
    if mode == "advanced":
        return re.sub(r'[^\s"(),*:^]+', lambda m: m.group(0) if m.group(0) in _OPERATORS or m.group(0) == "NEAR"
                      or m.group(0).isdigit() else fold(m.group(0)) or m.group(0), q), terms
    if mode == "phrase":
        return '"' + " ".join(t for t, _ in terms) + '"', terms
    quoted = [f'"{t}"' + ("*" if star else "") for t, star in terms]
    return (" OR " if mode == "any" else " ").join(quoted), terms


def _highlight_orig(text: str, terms: list[tuple[str, bool]]) -> str:
    out = []
    for part in re.split(r"(\s+)", text):
        words = fold(part).split()
        hit = any(w == t or (star and w.startswith(t)) for w in words for t, star in terms)
        out.append(f"{_OPEN}{part}{_CLOSE}" if hit and part.strip() else part)
    return "".join(out)


def _by_book_list(counter: Counter) -> list[dict]:
    return [{"osis": BOOK_BY_POS[pos]["osis"], "name": BOOK_BY_POS[pos]["name"], "count": n}
            for pos, n in sorted(counter.items())]


def _text_search(con, q, mode, trs, lo, hi, offset, limit):
    expr = fts_expression(q, mode)
    order = {t["id"]: i for i, t in enumerate(trs)}
    groups: dict[str, list[int]] = {}
    for t in trs:
        groups.setdefault(t["fts"], []).append(t["id"])
    by_book: Counter = Counter()
    rows: list[tuple] = []
    toks = tokens(q)
    for fts, tids in groups.items():
        ph = placeholders(len(tids))
        short_cjk = fts == "cjk" and mode != "advanced" and any(len(t.rstrip("*")) < 3 for t in toks)
        try:
            if fts == "orig":   # Hebrew/Greek: folded index, highlight the pointed/accented text
                oexpr, terms = _orig_terms(q, mode)
                base = (f"FROM fts_orig JOIN verse_text vt ON vt.id = fts_orig.rowid "
                        f"JOIN verse v ON v.id = vt.verse_id WHERE fts_orig MATCH ? "
                        f"AND vt.translation_id IN ({ph}) AND v.book_id BETWEEN ? AND ?")
                args = [oexpr, *tids, lo, hi]
                for r in con.execute(f"SELECT v.book_id, COUNT(*) {base} GROUP BY v.book_id", args):
                    by_book[r[0]] += r[1]
                for r in con.execute(f"SELECT v.id, v.osis, vt.translation_id, vt.text {base} "
                                     f"ORDER BY v.id LIMIT ?", [*args, offset + limit]):
                    rows.append((r[0], order[r[2]], r[1], r[2], _highlight_orig(r[3], terms)))
            elif short_cjk:      # trigram index needs 3+ characters; fall back to substring match
                joiner = " OR " if mode == "any" else " AND "
                cond = joiner.join("vt.text LIKE ?" for _ in toks)
                likes = [f"%{t.rstrip('*')}%" for t in toks]
                base = (f"FROM verse_text vt JOIN verse v ON v.id = vt.verse_id WHERE ({cond}) "
                        f"AND vt.translation_id IN ({ph}) AND v.book_id BETWEEN ? AND ?")
                args = [*likes, *tids, lo, hi]
                for r in con.execute(f"SELECT v.book_id, COUNT(*) {base} GROUP BY v.book_id", args):
                    by_book[r[0]] += r[1]
                for r in con.execute(f"SELECT v.id, v.osis, vt.translation_id, vt.text {base} "
                                     f"ORDER BY v.id LIMIT ?", [*args, offset + limit]):
                    rows.append((r[0], order[r[2]], r[1], r[2], _like_snippet(r[3], toks)))
            else:
                table = FTS[fts]
                base = (f"FROM {table} JOIN verse_text vt ON vt.id = {table}.rowid "
                        f"JOIN verse v ON v.id = vt.verse_id WHERE {table} MATCH ? "
                        f"AND vt.translation_id IN ({ph}) AND v.book_id BETWEEN ? AND ?")
                args = [expr, *tids, lo, hi]
                for r in con.execute(f"SELECT v.book_id, COUNT(*) {base} GROUP BY v.book_id", args):
                    by_book[r[0]] += r[1]
                for r in con.execute(
                        f"SELECT v.id, v.osis, vt.translation_id, snippet({table}, 0, ?, ?, ' … ', 28) "
                        f"{base} ORDER BY v.id LIMIT ?", [_OPEN, _CLOSE, *args, offset + limit]):
                    rows.append((r[0], order[r[2]], r[1], r[2], r[3]))
        except sqlite3.OperationalError as e:
            raise HTTPException(400, f"Couldn't read that search: {e}. In advanced mode use words, "
                                     f'"exact phrases", AND / OR / NOT, NEAR(a b, 5) and prefix*.') from e
    rows.sort(key=lambda r: (r[0], r[1]))
    code = {t["id"]: t["code"] for t in trs}
    results = [{"osis": osis, "ref": ref_label(osis), "translation": code[tid], "html": snippet_html(snip)}
               for _, _, osis, tid, snip in rows[offset:offset + limit]]
    return expr, by_book, results


def _original_search(con, q, display_tid, lo, hi, offset, limit):
    raw = q.strip()
    star = raw.endswith("*")
    raw = raw.rstrip("*").strip()
    m = _STRONGS.match(raw)
    if m:
        base = f"{m.group(1).upper()}{int(m.group(2))}"
        if m.group(3):
            ds = norm_dstrong(raw)
            where, args, what = "w.dstrong = ?", [ds], ds
        else:
            where, args, what = "w.strongs = ?", [base], base
        lx = con.execute("SELECT lemma, gloss FROM lexicon WHERE strongs = ? ORDER BY dstrong", (base,)).fetchone()
        label = f"{what}" + (f" {lx['lemma']} “{lx['gloss']}” — every occurrence" if lx else "")
    else:
        f = fold(raw)
        if not f:
            raise HTTPException(400, "Type a Strong's number (G26), a Greek or Hebrew word, or a transliteration.")
        if is_original_script(raw):
            lem = [] if star else con.execute(
                "SELECT DISTINCT strongs, lemma FROM lexicon WHERE lemma_norm = ?", (f,)).fetchall()
        else:
            lem = con.execute("SELECT DISTINCT strongs, lemma FROM lexicon WHERE translit_norm "
                              + ("LIKE ?" if star else "= ?"), (f + "%" if star else f,)).fetchall()
            if not lem:
                return None, Counter(), [], f"No Greek or Hebrew dictionary word is spelled “{raw}”."
        if lem:
            ids = sorted({r["strongs"] for r in lem})
            where, args = f"w.strongs IN ({placeholders(len(ids))})", ids
            label = "all forms of " + ", ".join(sorted({r['lemma'] for r in lem})) + f" ({', '.join(ids)})"
        else:
            where, args = ("w.norm LIKE ?", [f + "%"]) if star else ("w.norm = ?", [f])
            label = f"the form {raw}" + ("…" if star else "")
    scope = "v.book_id BETWEEN ? AND ?"
    by_book = Counter({r[0]: r[1] for r in con.execute(
        f"SELECT v.book_id, COUNT(DISTINCT v.id) FROM original_word w JOIN verse v ON v.id = w.verse_id "
        f"WHERE {where} AND {scope} GROUP BY v.book_id", (*args, lo, hi))})
    vrows = con.execute(
        f"SELECT v.id, v.osis FROM original_word w JOIN verse v ON v.id = w.verse_id WHERE {where} AND {scope} "
        f"GROUP BY v.id ORDER BY v.id LIMIT ? OFFSET ?", (*args, lo, hi, limit, offset)).fetchall()
    ids = [r["id"] for r in vrows]
    texts, hits = {}, {}
    if ids:
        ph = placeholders(len(ids))
        if display_tid:
            texts = {r[0]: r[1] for r in con.execute(
                f"SELECT verse_id, text FROM verse_text WHERE translation_id = ? AND verse_id IN ({ph})",
                (display_tid, *ids))}
        for r in con.execute(f"SELECT w.verse_id, w.text, w.gloss, w.strongs FROM original_word w "
                             f"WHERE {where} AND w.verse_id IN ({ph}) ORDER BY w.verse_id, w.position", (*args, *ids)):
            hits.setdefault(r[0], []).append({"text": reading_form(r[1]), "gloss": r[2], "strongs": r[3]})
    results = [{"osis": r["osis"], "ref": ref_label(r["osis"]), "html": html.escape(texts.get(r["id"]) or "", quote=False),
                "words": hits.get(r["id"], [])} for r in vrows]
    return label, by_book, results, None


@router.get("/search")
def search(q: str, mode: str = "auto", translations: str = "KJV", scope: str = "all",
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
           con: sqlite3.Connection = Depends(content)):
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
    want_orig = False
    q = unicodedata.normalize("NFC", q).strip()
    if not q:
        raise HTTPException(400, "Type something to search for.")
    if mode == "auto":
        ref = parse_reference(q)
        if ref and any(ch.isdigit() for ch in q):
            return {"reference": {"book": ref.book, "chapter": ref.chapter, "verse": ref.verse,
                                  "osis": ref.osis, "label": ref.label()}}
        if is_original_script(q) and len(tokens(q)) > 1:
            mode, want_orig = "all", True          # several Greek/Hebrew words: search the original texts
        else:
            mode = "original" if (_STRONGS.match(q.rstrip("*")) or is_original_script(q)) else "all"

    lo, hi, scope_label = scope_range(scope)
    allrows = con.execute("SELECT id, code, fts, kind FROM translation").fetchall()
    tmap = {r["code"]: r for r in allrows}
    if translations.strip() == "*":
        trs = [r for r in allrows if r["kind"] == "text"]
    else:
        trs = [tmap[c] for c in dict.fromkeys(x.strip().upper() for x in translations.split(",")) if c in tmap]
    if not trs:
        trs = [tmap["KJV"]] if "KJV" in tmap else allrows[:1]
    if want_orig and not any(t["kind"] == "original" for t in trs) and "ORIG" in tmap:
        trs = [tmap["ORIG"]]

    out = {"query": q, "mode": mode, "scope": scope_label, "translations": [t["code"] for t in trs],
           "offset": offset, "limit": limit}
    if mode == "original":
        display = next((t for t in trs if t["kind"] == "text"), trs[0])
        label, by_book, results, msg = _original_search(con, q, display["id"], lo, hi, offset, limit)
        out.update(interpreted=label, message=msg, display_translation=display["code"])
    else:
        expr, by_book, results = _text_search(con, q, mode, trs, lo, hi, offset, limit)
        out.update(interpreted=expr, message=None)
    out.update(total=sum(by_book.values()), by_book=_by_book_list(by_book), results=results,
               unit="verses" if mode == "original" or len(trs) == 1 else "matches")
    return out
