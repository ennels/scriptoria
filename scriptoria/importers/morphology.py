"""Import STEPBible's morphology code expansions (TEGMC Greek, TEHMC Hebrew).

Each entry is a code line followed by indented lines:
  V-AAI-3S <tab> Function=Verb; Tense=Aorist; Voice=Active; Mood=Indicative; Person=3rd; Number=Singular
           <tab> Verb Aorist Active Indicative 3rd Singular
           <tab> an ACTION that happened - by a person or thing being discussed
           <tab> "_he/she/it taught _"
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


def _clean(s: str) -> str:
    s = s.strip().strip('"').strip().replace("\u201a", ",")
    s = re.sub(r"^Example:\s*", "", s)
    if '": "' in s:                       # 'giving to, rich and poor": "and' -> 'and'
        s = s.rsplit('": "', 1)[1]
    return re.sub(r"\s+", " ", s.replace("_", " ")).strip(' "')


def parse_morph_file(path: str | Path, language: str) -> list[tuple]:
    entries, cur = [], None
    with open(path, encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line and not line.startswith(("\t", " ")):
                parts = line.split("\t", 1)
                if len(parts) == 2 and parts[1].strip().startswith("Function="):
                    fields = {}
                    for kv in parts[1].split(";"):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            fields[k.strip()] = v.strip()
                    cur = {"code": parts[0].strip(), "fields": fields, "lines": []}
                    entries.append(cur)
                else:
                    cur = None
            elif cur is not None and line.strip():
                cur["lines"].append(_clean(line))
    out = []
    for e in entries:
        ln = e["lines"] + ["", "", ""]
        out.append((e["code"], language, ln[0] or None, json.dumps(e["fields"], ensure_ascii=False),
                    ln[1] or None, ln[2] or None))
    return out


def import_morphology(con: sqlite3.Connection, greek_path: str | Path, hebrew_path: str | Path) -> dict:
    con.execute("DELETE FROM morph_code")
    counts = {}
    for path, lang in ((greek_path, "greek"), (hebrew_path, "hebrew")):
        rows = parse_morph_file(path, lang)
        con.executemany("INSERT OR REPLACE INTO morph_code(code,language,label,fields,explanation,example)"
                        " VALUES(?,?,?,?,?,?)", rows)
        counts[lang] = len(rows)
    con.commit()
    return {"morph_codes": counts}
