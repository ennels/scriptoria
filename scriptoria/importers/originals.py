"""Import STEPBible TAHOT (Hebrew OT) + TAGNT (Greek NT) — one row per original word.

Verse placement (the part that has to be right for an interlinear):
  * STEPBible references are English (NRSV) numbers, with the other tradition in
    brackets when it differs:  Mal.4.1(3.19)  = English 4:1, Hebrew 3:19
                               Act.2.11[2.10] = NRSV 2:11, KJV 2:10
                               Rom.16.25{14.24}, Act.13.39(13.38) = other editions / NA
  * Our verse spine follows KJV numbering, so a [KJV] number wins when present;
    every other number is kept in alt_ref so the UI can say where traditions differ.
  * Psalm superscriptions are verse 0 (English Bibles leave them unnumbered).
  * Word positions are re-counted per English verse in file order, because one
    English verse can collect words from two Hebrew/Greek verses.

Columns (confirmed against the file headers):
  Greek  TAGNT: 0 ref=type | 1 word (translit) | 2 gloss | 3 dStrong=morph | 4 lemma=gloss |
                5 editions | 6 meaning variants | 7 spelling variants | 8 Spanish | 9 sub-meaning
  Hebrew TAHOT: 0 ref=type | 1 word | 2 translit | 3 gloss | 4 dStrongs | 5 morph |
                6 meaning variants | 7 spelling variants | 8 root dStrong | 9 alt Strongs |
                10 conjoin | 11 expanded tags {H7225G=רֵאשִׁית=: beginning»...}
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

from ..books import to_osis
from ..text import dstrong as norm_dstrong, fold, strongs_base
from . import VerseResolver

STEP_REF = re.compile(
    r"^(?P<book>[1-3]?[A-Za-z]+)\.(?P<ch>\d+)\.(?P<vs>\d+)"
    r"(?P<alts>(?:[\(\[\{]\d+\.\d+[\)\]\}])*)#(?P<pos>\d+)(?:=(?P<type>\S*))?")
_ALT = re.compile(r"([\(\[\{])(\d+)\.(\d+)[\)\]\}]")
_ROOT = re.compile(r"\{([GH]\d+[A-Za-z]?)\}")
_EXPANDED_ROOT = re.compile(r"\{([GH]\d+[A-Za-z]?)=([^=}]*)=([^}]*)\}")
_ANY_STRONG = re.compile(r"[GH]\d+[A-Za-z]?")
_MARKER = re.compile(r"^[\(\[\{]\d+(?:\.\d+)?[\)\]\}]\s*")   # '{14.24} To Him' -> 'To Him'

ALT_KIND = {"hebrew": {"(": "heb"}, "greek": {"(": "na", "[": "kjv", "{": "other"}}


def parse_step_ref(field: str, lang: str):
    """'Mal.4.1(3.19)#01=L' -> dict(book, ch, vs (English/KJV), pos, type, alt_ref) or None."""
    m = STEP_REF.match(field)
    if not m:
        return None
    ch, vs = int(m.group("ch")), int(m.group("vs"))
    alts = [(ALT_KIND[lang].get(b, "other"), int(c), int(v)) for b, c, v in _ALT.findall(m.group("alts"))]
    kjv = next(((c, v) for k, c, v in alts if k == "kjv"), None)
    alt_ref = [f"{k}:{c}.{v}" for k, c, v in alts if k != "kjv"]
    if kjv:                                   # KJV numbering differs from NRSV: follow KJV
        alt_ref.insert(0, f"nrsv:{ch}.{vs}")
        ch, vs = kjv
    return {"book": m.group("book"), "ch": ch, "vs": vs, "pos": int(m.group("pos")),
            "type": m.group("type") or "", "alt_ref": ";".join(alt_ref) or None}


def _root_dstrong(tag: str) -> str | None:
    """Content-word Strong's from a compound Hebrew tag: braces mark the root
    ('H9003/{H7225G}' -> H7225G); else the first non-prefix (< 9000) number."""
    m = _ROOT.search(tag or "")
    if m:
        return norm_dstrong(m.group(1))
    for s in _ANY_STRONG.findall(tag or ""):
        if int(re.sub(r"\D", "", s)) < 9000:
            return norm_dstrong(s)
    found = _ANY_STRONG.findall(tag or "")
    return norm_dstrong(found[0]) if found else None


def _split_greek_word(col: str) -> tuple[str, str]:
    """'Βίβλος (Biblos)' -> ('Βίβλος', 'Biblos')."""
    if col.endswith(")") and " (" in col:
        w, tr = col.rsplit(" (", 1)
        return w.strip(), tr[:-1].strip()
    return col.strip(), ""


def _col(c: list[str], i: int) -> str:
    return c[i].strip() if len(c) > i else ""


def parse_line(line: str, lang: str):
    """One STEPBible data line -> (ref dict, word dict) or None for headers/comments."""
    c = unicodedata.normalize("NFC", line.rstrip("\n")).split("\t")
    ref = parse_step_ref(c[0].strip(), lang)
    if ref is None:
        return None
    if lang == "greek":
        text, translit = _split_greek_word(_col(c, 1))
        gloss = _col(c, 2)
        strong_raw, _, morph = _col(c, 3).partition("=")
        lemma = _col(c, 4).split("=")[0].strip()
        meaning = _col(c, 9)
        word = dict(text=text, translit=translit, gloss=gloss, strongs_raw=strong_raw,
                    dstrong=norm_dstrong(strong_raw), morph=morph, lemma=lemma,
                    meaning=meaning if meaning and meaning.lower() != gloss.lower() else None,
                    editions=_col(c, 5) or None, variants=_col(c, 6) or None)
    else:
        text, translit, gloss = _col(c, 1), _col(c, 2), _col(c, 3)
        strong_raw, morph = _col(c, 4), _col(c, 5)
        ds = _root_dstrong(strong_raw)
        lemma, meaning = "", None
        for m in _EXPANDED_ROOT.finditer(_col(c, 11)):
            if norm_dstrong(m.group(1)) == ds:
                lemma = m.group(2).strip()
                meaning = m.group(3).split("»")[0].replace("_", " ").replace(";", "; ").strip(" :") or None
                break
        word = dict(text=text, translit=translit, gloss=gloss, strongs_raw=strong_raw,
                    dstrong=ds, morph=morph, lemma=lemma, meaning=meaning,
                    editions=None, variants=_col(c, 6) or None)
    word["gloss"] = _MARKER.sub("", word["gloss"]).strip()
    word["strongs"] = strongs_base(word["dstrong"])
    word["norm"] = fold(text)
    return ref, word


def import_originals(con: sqlite3.Connection, data_dir: str | Path) -> dict:
    data_dir = Path(data_dir)
    vr = VerseResolver(con)
    con.execute("DELETE FROM original_word")
    unknown: set[str] = set()
    stats = defaultdict(int)
    files = sorted(data_dir.glob("TAHOT*.txt")) + sorted(data_dir.glob("TAGNT*.txt"))
    for f in files:
        lang = "greek" if f.name.startswith("TAGNT") else "hebrew"
        counter: dict[int, int] = defaultdict(int)
        rows = []
        with open(f, encoding="utf-8-sig") as fh:
            for line in fh:
                if not line[:1].isalnum():
                    continue
                parsed = parse_line(line, lang)
                if parsed is None:
                    continue
                ref, w = parsed
                osis = to_osis(ref["book"])
                if osis is None:
                    unknown.add(ref["book"])
                    continue
                vid = vr.resolve(f"{osis}.{ref['ch']}.{ref['vs']}")
                if vid is None:
                    stats["unresolved"] += 1
                    continue
                counter[vid] += 1
                if ref["alt_ref"]:
                    stats["renumbered_words"] += 1
                rows.append((vid, counter[vid], lang, w["text"], w["norm"], w["translit"], w["gloss"],
                             w["meaning"], w["strongs"], w["dstrong"], w["strongs_raw"], w["morph"],
                             w["lemma"], ref["type"], w["editions"], w["variants"], ref["alt_ref"]))
        con.executemany(
            "INSERT INTO original_word(verse_id,position,language,text,norm,translit,gloss,meaning,"
            "strongs,dstrong,strongs_raw,morph,lemma,text_type,editions,variants,alt_ref)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        stats[lang] += len(rows)
    con.commit()
    out = {"hebrew_words": stats["hebrew"], "greek_words": stats["greek"],
           "renumbered_words": stats["renumbered_words"]}
    if stats["unresolved"]:
        out["unresolved"] = stats["unresolved"]
    if unknown:
        out["unknown_book_codes"] = sorted(unknown)
    return out


# ------------------------------------------------------------------ editions & variants
_HEB_SOURCES = {
    "A": "the Aleppo Codex", "B": "BHS", "C": "the Cairo Codex", "D": "a Dead Sea Scroll",
    "E": "a scholarly emendation", "F": "a different word division", "H": "the Ben Chaim edition",
    "P": "alternate punctuation", "S": "scribal tradition", "V": "other manuscripts",
    "K": "the written text (Ketiv)",
}


def describe_text_type(text_type: str | None, lang: str) -> dict | None:
    """Plain-English note for a word's manuscript tag, or None for the ordinary case."""
    t = (text_type or "").strip()
    if not t:
        return None
    if lang == "greek":
        outside = re.sub(r"\([^)]*\)", "", t)
        in_na = "N" in outside or "n" in t
        in_tr = "K" in outside or "k" in t
        if in_na and in_tr:
            if "(K)" in t:
                return {"kind": "differs", "label": "KJV's Greek differs",
                        "detail": "The Textus Receptus (the Greek behind the KJV) has a different word here."}
            return None
        if in_tr:
            return {"kind": "tr-only", "label": "KJV's Greek only",
                    "detail": "Found in the Textus Receptus (KJV) but not in Nestle-Aland, the text behind most modern translations."}
        if in_na:
            return {"kind": "na-only", "label": "Not in KJV's Greek",
                    "detail": "Found in Nestle-Aland (most modern translations) but not in the Textus Receptus used by the KJV."}
        return {"kind": "other", "label": "Other editions only",
                "detail": "Found only in other Greek editions; rarely translated."}
    head = t[0]
    alts = re.findall(r"\(([^)]*)\)", t)
    letters = [ch for grp in alts for ch in grp if ch.isalpha()]
    if head == "Q":
        major = "K" in letters
        return {"kind": "qere", "label": "Qere (read)",
                "detail": "Follows the scribes' marginal reading (Qere); the written text (Ketiv) "
                          + ("differs in meaning." if major else "differs only in spelling.")}
    if head == "X":
        return {"kind": "lxx", "label": "From the Septuagint",
                "detail": "Missing in the Hebrew manuscripts; restored from the Greek Septuagint as in BHS."}
    if head == "R":
        return {"kind": "restored", "label": "Restored",
                "detail": "Missing from the Leningrad Codex; restored from a parallel passage."}
    srcs = sorted({_HEB_SOURCES[ch.upper()] for ch in letters if ch.upper() in _HEB_SOURCES})
    if srcs:
        major = any(ch.isupper() for ch in letters)
        return {"kind": "variant", "label": "Manuscript variant" if major else "Minor variant",
                "detail": f"Leningrad Codex reading; differs in {', '.join(srcs)}"
                          + ("." if major else " without changing the meaning.")}
    return None


def describe_alt_ref(alt_ref: str | None, lang: str) -> list[str]:
    names = {"heb": "Hebrew", "na": "Nestle-Aland", "other": "some editions", "nrsv": "modern English Bibles"}
    out = []
    for part in (alt_ref or "").split(";"):
        if ":" in part:
            kind, cv = part.split(":", 1)
            c, v = cv.split(".")
            label = f"Psalm title (superscription)" if v == "0" else f"{c}:{v}"
            out.append(f"{names.get(kind, kind)} {label}" if v != "0" else label)
    return out
