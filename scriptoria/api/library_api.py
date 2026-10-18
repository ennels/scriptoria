"""Translation library: browse 120+ versions by language, install or remove them."""
from __future__ import annotations

import sqlite3
import urllib.error
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException

from .. import config, library
from .deps import content

router = APIRouter(prefix="/api/library")


@router.get("")
def catalog(con: sqlite3.Connection = Depends(content)):
    installed = {r["code"]: dict(r) for r in con.execute(
        "SELECT code, name, language, language_name, direction, kind, verses, source FROM translation")}
    items = []
    for e in library.catalog():
        inst = installed.get(e["code"])
        items.append({**e, "installed": bool(inst), "verses": inst["verses"] if inst else None,
                      "source": inst["source"] if inst else None})
    for code, t in installed.items():          # installed but not in the catalog (originals, custom files)
        if not library.entry(code):
            items.append({"code": code, "abbr": None, "name": t["name"], "language": t["language"],
                          "language_name": t["language_name"], "direction": t["direction"],
                          "fts": None, "size": 0, "installed": True, "verses": t["verses"],
                          "source": t["source"], "builtin": True, "kind": t["kind"]})
    langs = defaultdict(lambda: {"count": 0, "installed": 0})
    for it in items:
        lg = langs[(it["language"], it["language_name"])]
        lg["count"] += 1
        lg["installed"] += it["installed"]
    src = library.local_source()
    return {
        "source": {"local": str(src) if src else None,
                   "online": config.LIBRARY_RAW_URL.split("{")[0]},
        "languages": sorted(({"code": k[0], "name": k[1], **v} for k, v in langs.items()),
                            key=lambda x: (x["name"] != "English", x["name"])),
        "translations": items,
    }


@router.post("/{code}")
def install(code: str, con: sqlite3.Connection = Depends(content)):
    e = library.entry(code)
    if not e:
        raise HTTPException(404, f"{code} isn't in the library catalog.")
    try:
        result = library.install(con, e["code"])
    except urllib.error.URLError as ex:
        raise HTTPException(502, "Couldn't download that translation, and no local copy of the bible zip "
                                 "was found. Connect to the internet once, or put bible.zip in the "
                                 f"Scriptoria data folder ({config.data_dir()}).") from ex
    return result


@router.delete("/{code}")
def remove(code: str, con: sqlite3.Connection = Depends(content)):
    r = con.execute("SELECT kind FROM translation WHERE code = ?", (code.upper(),)).fetchone()
    if not r:
        raise HTTPException(404, f"{code} isn't installed.")
    if r["kind"] == "original":
        raise HTTPException(400, "The Hebrew/Greek texts are part of the study data and can't be removed.")
    n = con.execute("SELECT COUNT(*) FROM translation WHERE kind = 'text'").fetchone()[0]
    if n <= 1:
        raise HTTPException(400, "Keep at least one translation installed.")
    library.remove(con, code.upper())
    return {"removed": code.upper()}
