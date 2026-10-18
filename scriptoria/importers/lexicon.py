"""Import the Tyndale House brief lexicons (STEPBible TBESG / TBESH, CC BY 4.0).

Data lines: eStrong | dStrong (= relation) | uStrong | lemma | translit | morph | gloss | definition
  G0026 | G0026 = | G0026 | ἀγάπη | agapē | G:N-F | love | <b>ἀγάπη</b>, -ης, ἡ <BR /> ...
  H7225 | H7225H = a Meaning of | H7225G | רֵאשִׁית | re.shit | H:N-F | first: best | ...
Greek definitions are Abbott-Smith; Hebrew are BDB-based. HTML is sanitized on import.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path

from ..text import dstrong, fold, sanitize_lexicon_html, strongs_base

_LINE = re.compile(r"^[GH]\d{4}[A-Za-z]?\t")


def parse_lexicon_line(line: str, language: str):
    c = unicodedata.normalize("NFC", line.rstrip("\n")).split("\t")
    if len(c) < 7:
        return None
    ds_field, _, relation = c[1].partition("=")
    ds = dstrong(ds_field) or dstrong(c[0])
    if not ds:
        return None
    pos = c[5].split(":", 1)[-1].strip() if c[5] else ""
    return (ds, strongs_base(ds), language, c[3].strip(), fold(c[3]), c[4].strip(), fold(c[4]), pos,
            c[6].strip(), sanitize_lexicon_html(c[7] if len(c) > 7 else ""), relation.strip() or None)


def import_lexicons(con: sqlite3.Connection, greek_path: str | Path, hebrew_path: str | Path) -> dict:
    con.execute("DELETE FROM lexicon")
    counts = {}
    for path, lang in ((greek_path, "greek"), (hebrew_path, "hebrew")):
        rows, seen = [], set()
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                if not _LINE.match(line):
                    continue
                row = parse_lexicon_line(line, lang)
                if row and row[0] not in seen:
                    seen.add(row[0])
                    rows.append(row)
        con.executemany(
            "INSERT INTO lexicon(dstrong,strongs,language,lemma,lemma_norm,translit,translit_norm,pos,gloss,"
            "definition,relation) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        counts[lang] = len(rows)
    con.commit()
    return {"lexicon_entries": counts}
