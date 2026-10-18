"""Request-scoped database connections and the active profile.

One connection per request, always closed (the first release opened a new
connection per request and never closed it)."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException

from .. import config, db as cdb, userdb
from ..books import BOOKS

BOOK = {b["osis"]: b for b in BOOKS}
_status: dict[tuple, tuple[bool, str | None]] = {}


def content_status() -> tuple[bool, str | None]:
    p = config.content_db()
    if not p.exists():
        return False, (f"No scripture database found at {p}. Unzip scriptoria-db.zip into the "
                       "Scriptoria folder, or build one with: uv run python -m scriptoria.build")
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _status:
        con = cdb.connect(p, must_exist=True)
        try:
            v = cdb.schema_version(con)
        finally:
            con.close()
        _status.clear()
        _status[key] = (True, None) if v >= cdb.SCHEMA_VERSION else (False, (
            f"This scripture database is from an older Scriptoria (format {v}; this version needs "
            f"{cdb.SCHEMA_VERSION}). Download the new scriptoria-db.zip, or rebuild with: "
            "uv run python -m scriptoria.build. Notes are stored separately and are not affected."))
    return _status[key]


def content() -> Iterator[sqlite3.Connection]:
    ok, msg = content_status()
    if not ok:
        raise HTTPException(503, msg)
    con = cdb.connect(must_exist=True)
    try:
        yield con
    finally:
        con.close()


def user() -> Iterator[sqlite3.Connection]:
    con = userdb.connect()
    try:
        yield con
    finally:
        con.close()


def profile_id(x_profile: str | None = Header(default=None),
               u: sqlite3.Connection = Depends(user)) -> int:
    if x_profile and x_profile.isdigit():
        if u.execute("SELECT 1 FROM profile WHERE id=?", (int(x_profile),)).fetchone():
            return int(x_profile)
    return userdb.default_profile(u)


def osis_parts(osis: str) -> tuple[str, int, int]:
    b, c, v = osis.rsplit(".", 2)
    return b, int(c), int(v)


def ref_label(osis: str, end: str | None = None) -> str:
    """'John.3.16' -> 'John 3:16'; with end 'John.3.18' -> 'John 3:16–18'."""
    try:
        b, c, v = osis_parts(osis)
    except ValueError:
        return osis
    name = BOOK[b]["name"] if b in BOOK else b
    s = f"{name} {c}" + (":title" if v == 0 else f":{v}")
    if end:
        try:
            eb, ec, ev = osis_parts(end)
        except ValueError:
            return s
        if eb == b and ec == c:
            s += f"–{ev}"
        elif eb == b:
            s += f"–{ec}:{ev}"
        else:
            s += f" – {ref_label(end)}"
    return s


def canon_key(osis: str) -> tuple[int, int, int]:
    try:
        b, c, v = osis_parts(osis)
        return (BOOK[b]["position"] if b in BOOK else 999, c, v)
    except ValueError:
        return (999, 0, 0)


def book_or_404(book: str) -> dict:
    from ..references import resolve_book
    osis = resolve_book(book) if book not in BOOK else book
    if not osis:
        raise HTTPException(404, f"Unknown book: {book}")
    return BOOK[osis]


def placeholders(n: int) -> str:
    return ",".join("?" * n)
