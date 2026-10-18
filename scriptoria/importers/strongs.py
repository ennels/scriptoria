"""Import the OpenScriptures Strong's lexicon (Greek + Hebrew).

Source files are JS modules: a comment header, then a JSON object
(keys 'G26', 'H430', ...). We slice from the first '{' and parse.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path


def _load_js_dict(path: str | Path) -> dict:
    s = unicodedata.normalize("NFC", Path(path).read_text(encoding="utf-8"))
    obj = s[s.index("{"):]
    obj = re.sub(r";\s*(module\.exports.*)?$", "", obj.strip(), flags=re.S)
    return json.loads(obj)


def import_strongs(con: sqlite3.Connection, greek_js: str | Path, hebrew_js: str | Path) -> dict:
    con.execute("DELETE FROM strongs")
    total = 0
    for path, lang in ((greek_js, "greek"), (hebrew_js, "hebrew")):
        d = _load_js_dict(path)
        rows = []
        for sid, e in d.items():
            rows.append((
                sid, lang,
                e.get("lemma"), e.get("translit") or e.get("xlit"), e.get("pronounce") or e.get("pron"),
                (e.get("strongs_def") or "").strip(), (e.get("kjv_def") or "").strip(),
                (e.get("derivation") or "").strip(),
            ))
        con.executemany(
            "INSERT OR REPLACE INTO strongs(id,language,lemma,translit,pronounce,definition,kjv_def,derivation)"
            " VALUES(?,?,?,?,?,?,?,?)", rows)
        total += len(rows)
    con.commit()
    return {"strongs_entries": total}
