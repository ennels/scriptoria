"""Turn morphology codes into plain English using STEPBible's expansion tables.

Greek codes are single (V-AAI-3S). Hebrew codes chain morphemes after a language
letter: 'HR/Ncfsa' = Hebrew + preposition + noun, so each part is looked up as
'HR' and 'HNcfsa'. Aramaic portions start with 'A'."""
from __future__ import annotations

import json
import sqlite3

from .api.deps import placeholders


def parts_of(code: str, language: str) -> list[str]:
    if not code:
        return []
    if language == "hebrew" and code[0] in "HA" and len(code) > 1:
        return [code[0] + p for p in code[1:].split("/") if p]
    return [code]


def _greek_fallbacks(code: str) -> list[str]:
    out, c = [code], code
    while "-" in c:
        c = c.rsplit("-", 1)[0]
        out.append(c)
    return out


def expand_many(con: sqlite3.Connection, items: list[tuple[str, str]]) -> dict[str, dict]:
    """[(code, language)] -> {code: {label, parts:[{code,label,explanation,example,fields}]}}."""
    wanted: set[str] = set()
    for code, lang in items:
        for p in parts_of(code, lang):
            wanted.update(_greek_fallbacks(p) if lang == "greek" else [p])
    rows = {}
    if wanted:
        for r in con.execute(f"SELECT * FROM morph_code WHERE code IN ({placeholders(len(wanted))})",
                             list(wanted)):
            rows[r["code"]] = r
    out = {}
    for code, lang in items:
        if not code or code in out:
            continue
        parts = []
        for p in parts_of(code, lang):
            r = next((rows[c] for c in (_greek_fallbacks(p) if lang == "greek" else [p]) if c in rows), None)
            if r:
                parts.append({"code": p, "label": (r["label"] or "").replace("Verb : ", "Verb · "),
                              "explanation": r["explanation"], "example": r["example"],
                              "fields": json.loads(r["fields"] or "{}")})
            else:
                parts.append({"code": p, "label": p, "explanation": None, "example": None, "fields": {}})
        out[code] = {"code": code, "label": " + ".join(x["label"] for x in parts), "parts": parts}
    return out
