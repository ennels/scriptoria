"""Import OpenBible cross-references (TSV: From Verse / To Verse / Votes).

The To Verse may be a single verse (Ps.115.15) or a range (Gen.1.1-Gen.1.5).
We store the start verse_id and, for ranges, the end verse_id, plus the vote weight.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import VerseResolver


def import_crossrefs(con: sqlite3.Connection, path: str | Path) -> dict:
    vr = VerseResolver(con)
    con.execute("DELETE FROM cross_ref")
    added, skipped = 0, 0
    batch = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("From Verse") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            frm, to, votes = parts[0], parts[1], parts[2]
            from_id = vr.resolve(frm)
            if "-" in to:
                start, end = to.split("-", 1)
                to_id, end_id = vr.resolve(start), vr.resolve(end)
            else:
                to_id, end_id = vr.resolve(to), None
            if from_id is None or to_id is None:
                skipped += 1
                continue
            try:
                v = int(votes)
            except ValueError:
                v = 0
            batch.append((from_id, to_id, end_id, v))
            if len(batch) >= 5000:
                con.executemany(
                    "INSERT INTO cross_ref(from_verse_id,to_verse_id,to_end_id,votes) VALUES(?,?,?,?)", batch)
                added += len(batch)
                batch = []
    if batch:
        con.executemany(
            "INSERT INTO cross_ref(from_verse_id,to_verse_id,to_end_id,votes) VALUES(?,?,?,?)", batch)
        added += len(batch)
    con.commit()
    return {"cross_refs": added, "skipped": skipped}
