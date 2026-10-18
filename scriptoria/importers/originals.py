"""Import STEPBible TAHOT (Hebrew OT) + TAGNT (Greek NT) tagged originals.

One row per original-language word, with Strong's number, morphology, gloss and
transliteration — the data behind an interlinear / word-study view.

Column layouts differ by language (confirmed against the files):
  Greek  (TAGNT): [1] Ref#pos=ms  [2] word (translit)  [3] gloss  [4] Strong=Morph  [5] lemma=meaning
  Hebrew (TAHOT): [1] Ref#pos=ms  [2] word  [3] translit  [4] gloss  [5] Strong(s)  [6] morph
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ..books import to_osis
from . import VerseResolver, norm_strongs

_REF = re.compile(r"^([A-Za-z0-9]+)\.(\d+)\.(\d+)#(\d+)")
_STRONG = re.compile(r"([GH])0*(\d+)")

# Which files are Greek vs Hebrew (matched by substring of the filename).
GREEK_FILES = ("TAGNT",)
HEBREW_FILES = ("TAHOT",)


def _main_strongs(raw: str) -> str | None:
    """Pick the content-word Strong's from a (possibly compound) tag for lexicon linking.
    Hebrew prefixes are H9xxx; prefer the first number < 9000, else the first."""
    found = _STRONG.findall(raw or "")
    if not found:
        return None
    for letter, num in found:
        if int(num) < 9000:
            return f"{letter}{int(num)}"
    letter, num = found[0]
    return f"{letter}{int(num)}"


def _greek_word(col: str) -> tuple[str, str]:
    """'Βίβλος (Biblos)' -> ('Βίβλος', 'Biblos')."""
    if col.endswith(")") and " (" in col:
        w, tr = col.rsplit(" (", 1)
        return w.strip(), tr[:-1].strip()
    return col.strip(), ""


def _parse_file(path: Path, lang: str, vr: VerseResolver, unknown: set):
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            m = _REF.match(line)
            if not m:
                continue  # header / comment / blank
            code, ch, vs, pos = m.groups()
            osis = to_osis(code)
            if osis is None:
                unknown.add(code)
                continue
            c = line.rstrip("\n").split("\t")
            if lang == "greek":
                word, translit = _greek_word(c[1]) if len(c) > 1 else ("", "")
                gloss = c[2] if len(c) > 2 else ""
                tag = c[3] if len(c) > 3 else ""
                strongs_raw, _, morph = tag.partition("=")
                lemma = c[4].split("=")[0] if len(c) > 4 else ""
            else:  # hebrew
                word = c[1] if len(c) > 1 else ""
                translit = c[2] if len(c) > 2 else ""
                gloss = c[3] if len(c) > 3 else ""
                strongs_raw = c[4] if len(c) > 4 else ""
                morph = c[5] if len(c) > 5 else ""
                lemma = ""
            vid = vr.resolve(f"{osis}.{ch}.{vs}")
            if vid is None:
                continue
            rows.append((vid, int(pos), lang, word, translit, gloss,
                         _main_strongs(strongs_raw), strongs_raw, morph, lemma))
    return rows


def import_originals(con: sqlite3.Connection, data_dir: str | Path) -> dict:
    data_dir = Path(data_dir)
    vr = VerseResolver(con)
    con.execute("DELETE FROM original_word")
    unknown: set[str] = set()
    total = 0
    files = sorted(data_dir.glob("TA*.txt")) + sorted((data_dir / "stepbible").glob("TA*.txt")) \
        if (data_dir / "stepbible").exists() else sorted(data_dir.glob("TA*.txt"))
    for f in files:
        lang = "greek" if any(t in f.name for t in GREEK_FILES) else \
               "hebrew" if any(t in f.name for t in HEBREW_FILES) else None
        if lang is None:
            continue
        rows = _parse_file(f, lang, vr, unknown)
        con.executemany(
            "INSERT OR REPLACE INTO original_word"
            "(verse_id,position,language,text,translit,gloss,strongs,strongs_raw,morph,lemma)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        total += len(rows)
    con.commit()
    out = {"original_words": total}
    if unknown:
        out["unknown_book_codes"] = sorted(unknown)
    return out
