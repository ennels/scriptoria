"""The translation library: 120+ versions in 67 languages that can be installed on
demand — from a local copy of the thiagobodruk bible zip/folder if one is found,
otherwise downloaded (one small JSON file per translation)."""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

from . import config
from .importers.verses import install_rows, remove_translation, rows_from_json

_lock = threading.Lock()


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    return json.loads((config.PACKAGE / "catalog.json").read_text(encoding="utf-8"))


def entry(code_or_abbr: str) -> dict | None:
    key = code_or_abbr.strip()
    for e in catalog():
        if e["code"].lower() == key.lower() or e["abbr"].lower() == key.lower():
            return e
    return None


def local_source() -> Path | None:
    for p in config.bibles_source_candidates():
        if p.exists():
            return p
    return None


def _read_local(src: Path, abbr: str) -> bytes | None:
    if src.is_dir():
        f = src / f"{abbr}.json"
        return f.read_bytes() if f.exists() else None
    try:
        with zipfile.ZipFile(src) as z:
            name = next((n for n in z.namelist() if n.endswith(f"/json/{abbr}.json")
                         or n == f"json/{abbr}.json" or n == f"{abbr}.json"), None)
            return z.read(name) if name else None
    except zipfile.BadZipFile:
        return None


def fetch(abbr: str) -> tuple[bytes, str]:
    src = local_source()
    if src:
        data = _read_local(src, abbr)
        if data:
            return data, f"local:{src.name}"
    url = config.LIBRARY_RAW_URL.format(abbr=abbr)
    with urllib.request.urlopen(url, timeout=60) as r:       # noqa: S310 (fixed https host)
        return r.read(), "download:thiagobodruk/bible"


def install(con: sqlite3.Connection, code: str) -> dict:
    e = entry(code)
    if not e:
        raise KeyError(code)
    raw, origin = fetch(e["abbr"])                  # download/parse outside the lock
    rows = rows_from_json(json.loads(raw.decode("utf-8-sig")))
    with _lock:                                     # one writer at a time
        result = install_rows(con, rows, code=e["code"], name=e["name"], language=e["language"],
                              language_name=e["language_name"], direction=e["direction"],
                              fts=e["fts"], source=f"thiagobodruk:{e['abbr']}")
    result["from"] = origin
    return result


def remove(con: sqlite3.Connection, code: str) -> bool:
    """Remove a translation, refusing to remove the last readable one (checked under the lock)."""
    with _lock:
        n = con.execute("SELECT COUNT(*) FROM translation WHERE kind = 'text' AND code <> ?", (code,)).fetchone()[0]
        if n < 1:
            raise ValueError("Keep at least one translation installed.")
        return remove_translation(con, code)
