"""Build readable original-language texts from the tagged words, so Hebrew/Greek can
sit beside any translation as an ordinary column (and be searched):

  ORIG     Hebrew OT (Leningrad, following the Qere) + Greek NT as in Nestle-Aland
  ORIG-TR  Hebrew OT + Greek NT as in the Textus Receptus (the Greek behind the KJV)
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict

from ..text import fold
from .verses import remove_translation

EDITIONS = {
    "ORIG": ("Hebrew & Greek (Nestle-Aland NT)", "N"),
    "ORIG-TR": ("Hebrew & Greek (Textus Receptus NT)", "K"),
}


def in_edition(text_type: str | None, edition: str) -> bool:
    """Greek words carry N (Nestle-Aland) / K (Textus Receptus) / O (other) markers.
    A letter outside brackets means the edition has this word; a lowercase letter
    anywhere means it has it with a difference too small to affect translation."""
    t = text_type or ""
    outside = re.sub(r"\([^)]*\)", "", t)
    return edition.upper() in outside or edition.lower() in t


def _join(words: list[str]) -> str:
    out = ""
    for w in words:
        w = w.replace("/", "").replace("\\", "")
        if not w:
            continue
        out += w if (not out or out.endswith("־")) else " " + w   # no space after maqaf
    return unicodedata.normalize("NFC", out.strip())


def build_original_texts(con: sqlite3.Connection) -> dict:
    by_verse: dict[int, list[tuple]] = defaultdict(list)
    for vid, pos, lang, text, ttype in con.execute(
            "SELECT verse_id, position, language, text, text_type FROM original_word ORDER BY verse_id, position"):
        by_verse[vid].append((lang, text, ttype))
    out = {}
    for code, (name, ed) in EDITIONS.items():
        remove_translation(con, code)
        tid = con.execute(
            "INSERT INTO translation(code,name,language,language_name,direction,kind,fts,source,license)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (code, name, "hbo+grc", "Hebrew & Greek", "mixed", "original", "orig",
             "stepbible:TAHOT+TAGNT", "CC BY 4.0 STEPBible.org")).lastrowid
        rows = []
        for vid, words in by_verse.items():
            kept = [t for lang, t, tt in words if lang == "hebrew" or in_edition(tt, ed)]
            text = _join(kept)
            if text:
                rows.append((tid, vid, text))
        con.executemany("INSERT INTO verse_text(translation_id, verse_id, text) VALUES(?,?,?)", rows)
        con.executemany("INSERT INTO fts_orig(rowid, text) VALUES(?, ?)",
                        [(i, fold(t)) for i, t in con.execute(
                            "SELECT id, text FROM verse_text WHERE translation_id=?", (tid,))])
        con.execute("UPDATE translation SET verses=? WHERE id=?", (len(rows), tid))
        out[code] = len(rows)
    con.commit()
    return out
