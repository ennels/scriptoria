"""Shared import helpers: verse resolution and Strong's normalization."""
from __future__ import annotations

import re
import sqlite3

from ..books import to_osis
from ..db import book_id_by_osis


class VerseResolver:
    """Maps an OSIS-ish reference ('John.3.16', 'Gen 1:1') to a verse_id,
    creating the verse row on demand so the spine covers every dataset."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self._book_id = book_id_by_osis(con)
        self._cache: dict[str, int | None] = {}
        for r in con.execute("SELECT id, osis FROM verse"):
            self._cache[r["osis"]] = r["id"]

    def resolve(self, ref: str) -> int | None:
        """Return verse_id for a single-verse reference, or None if unparseable."""
        parsed = parse_ref(ref)
        if parsed is None:
            return None
        book_osis, ch, vs = parsed
        key = f"{book_osis}.{ch}.{vs}"
        if key in self._cache:
            return self._cache[key]
        bid = self._book_id.get(book_osis)
        if bid is None:
            self._cache[key] = None
            return None
        cur = self.con.execute(
            "INSERT OR IGNORE INTO verse(osis, book_id, chapter, verse) VALUES(?,?,?,?)",
            (key, bid, ch, vs),
        )
        vid = cur.lastrowid if cur.rowcount else self.con.execute(
            "SELECT id FROM verse WHERE osis=?", (key,)
        ).fetchone()["id"]
        self._cache[key] = vid
        return vid


_REF = re.compile(r"^\s*([0-9]?\s?[A-Za-z][A-Za-z .]*?)[.\s]+(\d+)[.:](\d+)\s*$")


def parse_ref(ref: str) -> tuple[str, int, int] | None:
    """'John.3.16' / 'Gen 1:1' / '1Cor.13.4' -> ('John', 3, 16). None if not a verse ref."""
    m = _REF.match(ref)
    if not m:
        return None
    osis = to_osis(m.group(1))
    if osis is None:
        return None
    return osis, int(m.group(2)), int(m.group(3))


def norm_strongs(raw: str) -> str | None:
    """'G0976' -> 'G976', 'H7225G' -> 'H7225', '{H7225G}' -> 'H7225'. For lexicon linking."""
    m = re.search(r"([GH])0*(\d+)", raw or "")
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)}"
