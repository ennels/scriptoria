"""Per-profile data: profiles, settings, highlights, notes with tags, export.

The active profile comes from the X-Profile header (the browser remembers which
profile is reading). No passwords: profiles keep people's notes apart on a shared PC."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..userdb import PROFILE_COLORS
from .deps import BOOK, canon_key, profile_id, ref_label, user

router = APIRouter(prefix="/api")

HIGHLIGHT_COLORS = ("amber", "rose", "sky", "sage", "lilac")
_OSIS = re.compile(r"^[1-3]?[A-Za-z]+\.\d+\.\d+$")


def _check_osis(osis: str) -> str:
    if not _OSIS.match(osis) or osis.rsplit(".", 2)[0] not in BOOK:
        raise HTTPException(400, f"Not a verse reference: {osis}")
    return osis


def _chapter_range(book: str, chapter: int) -> tuple[str, str]:
    """All OSIS keys of one chapter sort between 'John.3.' and 'John.3/' ('/' follows '.')."""
    return f"{book}.{chapter}.", f"{book}.{chapter}/"


# --------------------------------------------------------------------- profiles
class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = "lapis"


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None


def _profile_row(u, pid):
    r = u.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM note n WHERE n.profile_id = p.id) AS notes, "
        "(SELECT COUNT(*) FROM highlight h WHERE h.profile_id = p.id) AS highlights "
        "FROM profile p WHERE p.id = ?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "No such profile")
    return dict(r)


@router.get("/profiles")
def list_profiles(u: sqlite3.Connection = Depends(user), current: int = Depends(profile_id)):
    ids = [r[0] for r in u.execute("SELECT id FROM profile ORDER BY id")]
    return {"current": current, "colors": PROFILE_COLORS, "profiles": [_profile_row(u, i) for i in ids]}


@router.post("/profiles")
def create_profile(p: ProfileIn, u: sqlite3.Connection = Depends(user)):
    color = p.color if p.color in PROFILE_COLORS else "lapis"
    pid = u.execute("INSERT INTO profile(name, color) VALUES(?, ?)", (p.name.strip(), color)).lastrowid
    u.commit()
    return _profile_row(u, pid)


@router.patch("/profiles/{pid}")
def update_profile(pid: int, p: ProfilePatch, u: sqlite3.Connection = Depends(user)):
    _profile_row(u, pid)
    if p.name is not None:
        u.execute("UPDATE profile SET name = ? WHERE id = ?", (p.name.strip(), pid))
    if p.color is not None and p.color in PROFILE_COLORS:
        u.execute("UPDATE profile SET color = ? WHERE id = ?", (p.color, pid))
    u.commit()
    return _profile_row(u, pid)


@router.delete("/profiles/{pid}")
def delete_profile(pid: int, u: sqlite3.Connection = Depends(user)):
    _profile_row(u, pid)
    if u.execute("SELECT COUNT(*) FROM profile").fetchone()[0] <= 1:
        raise HTTPException(400, "Keep at least one profile.")
    u.execute("DELETE FROM profile WHERE id = ?", (pid,))
    u.commit()
    return {"deleted": pid}


# --------------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    out = {}
    for r in u.execute("SELECT key, value FROM setting WHERE profile_id = ?", (pid,)):
        try:
            out[r["key"]] = json.loads(r["value"])
        except (TypeError, ValueError):
            out[r["key"]] = r["value"]
    return out


@router.put("/settings")
def put_settings(values: dict = Body(...), u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    for k, v in values.items():
        if len(k) > 64:
            raise HTTPException(400, "Setting names are limited to 64 characters")
        u.execute("INSERT OR REPLACE INTO setting(profile_id, key, value) VALUES(?, ?, ?)",
                  (pid, k, json.dumps(v)))
    u.commit()
    return get_settings(u, pid)


# --------------------------------------------------------------------- highlights
class HighlightIn(BaseModel):
    color: str


@router.get("/annotations")
def annotations(book: str, chapter: int, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    lo, hi = _chapter_range(book, chapter)
    hl = {r[0]: r[1] for r in u.execute(
        "SELECT osis, color FROM highlight WHERE profile_id = ? AND osis >= ? AND osis < ?", (pid, lo, hi))}
    notes = {r[0]: r[1] for r in u.execute(
        "SELECT osis, COUNT(*) FROM note WHERE profile_id = ? AND osis >= ? AND osis < ? GROUP BY osis",
        (pid, lo, hi))}
    return {"highlights": hl, "notes": notes}


@router.put("/highlights/{osis}")
def set_highlight(osis: str, h: HighlightIn, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    _check_osis(osis)
    if h.color not in HIGHLIGHT_COLORS:
        raise HTTPException(400, f"color must be one of {', '.join(HIGHLIGHT_COLORS)}")
    u.execute("INSERT OR REPLACE INTO highlight(profile_id, osis, color, updated) VALUES(?, ?, ?, datetime('now'))",
              (pid, osis, h.color))
    u.commit()
    return {"osis": osis, "color": h.color}


@router.delete("/highlights/{osis}")
def clear_highlight(osis: str, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    u.execute("DELETE FROM highlight WHERE profile_id = ? AND osis = ?", (pid, osis))
    u.commit()
    return {"osis": osis, "color": None}


# --------------------------------------------------------------------- notes
class NoteIn(BaseModel):
    osis: str
    body: str = Field(default="", max_length=20000)
    tags: list[str] = []


class NotePatch(BaseModel):
    body: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = re.sub(r"\s+", " ", t.strip().lstrip("#"))[:40]
        if t and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:20]


def _note(u, nid, pid) -> dict:
    r = u.execute("SELECT * FROM note WHERE id = ? AND profile_id = ?", (nid, pid)).fetchone()
    if not r:
        raise HTTPException(404, "No such note")
    tags = [t[0] for t in u.execute("SELECT tag FROM note_tag WHERE note_id = ? ORDER BY tag", (nid,))]
    return {"id": r["id"], "osis": r["osis"], "ref": ref_label(r["osis"]), "body": r["body"], "tags": tags,
            "created": r["created"], "updated": r["updated"]}


def _set_tags(u, nid, tags):
    u.execute("DELETE FROM note_tag WHERE note_id = ?", (nid,))
    u.executemany("INSERT INTO note_tag(note_id, tag) VALUES(?, ?)", [(nid, t) for t in _clean_tags(tags)])


def _query_notes(u, pid, osis=None, book=None, chapter=None, tag=None, q=None) -> list[dict]:
    where, args = ["n.profile_id = ?"], [pid]
    if osis:
        where.append("n.osis = ?")
        args.append(osis)
    elif book and chapter:
        lo, hi = _chapter_range(book, chapter)
        where.append("n.osis >= ? AND n.osis < ?")
        args += [lo, hi]
    elif book:
        where.append("n.osis >= ? AND n.osis < ?")
        args += [f"{book}.", f"{book}/"]
    if tag:
        where.append("EXISTS (SELECT 1 FROM note_tag t WHERE t.note_id = n.id AND t.tag = ? COLLATE NOCASE)")
        args.append(tag)
    if q:
        where.append("(n.body LIKE ? OR EXISTS (SELECT 1 FROM note_tag t WHERE t.note_id = n.id AND t.tag LIKE ?))")
        args += [f"%{q}%", f"%{q}%"]
    ids = [r[0] for r in u.execute(f"SELECT n.id FROM note n WHERE {' AND '.join(where)}", args)]
    notes = [_note(u, i, pid) for i in ids]
    notes.sort(key=lambda n: (canon_key(n["osis"]), n["created"]))
    return notes


@router.get("/notes")
def list_notes(osis: str | None = None, book: str | None = None, chapter: int | None = None,
               tag: str | None = None, q: str | None = None,
               offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
               u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    notes = _query_notes(u, pid, osis, book, chapter, tag, q)
    return {"total": len(notes), "notes": notes[offset:offset + limit]}


@router.post("/notes")
def create_note(n: NoteIn, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    _check_osis(n.osis)
    if not n.body.strip():
        raise HTTPException(400, "Write something in the note first.")
    nid = u.execute("INSERT INTO note(profile_id, osis, body) VALUES(?, ?, ?)", (pid, n.osis, n.body.strip())).lastrowid
    _set_tags(u, nid, n.tags)
    u.commit()
    return _note(u, nid, pid)


@router.patch("/notes/{nid}")
def update_note(nid: int, p: NotePatch, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    _note(u, nid, pid)
    if p.body is not None:
        if not p.body.strip():
            raise HTTPException(400, "A note can't be empty — delete it instead.")
        u.execute("UPDATE note SET body = ?, updated = datetime('now') WHERE id = ?", (p.body.strip(), nid))
    if p.tags is not None:
        _set_tags(u, nid, p.tags)
        u.execute("UPDATE note SET updated = datetime('now') WHERE id = ?", (nid,))
    u.commit()
    return _note(u, nid, pid)


@router.delete("/notes/{nid}")
def delete_note(nid: int, u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    _note(u, nid, pid)
    u.execute("DELETE FROM note WHERE id = ?", (nid,))
    u.commit()
    return {"deleted": nid}


@router.get("/notes/tags")
def tags(u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    rows = u.execute("SELECT t.tag, COUNT(*) AS count FROM note_tag t JOIN note n ON n.id = t.note_id "
                     "WHERE n.profile_id = ? GROUP BY t.tag COLLATE NOCASE ORDER BY count DESC, t.tag", (pid,))
    return [dict(r) for r in rows]


@router.get("/notes/export")
def export(format: str = "md", u: sqlite3.Connection = Depends(user), pid: int = Depends(profile_id)):
    prof = u.execute("SELECT name FROM profile WHERE id = ?", (pid,)).fetchone()["name"]
    notes = _query_notes(u, pid)
    hl = {r[0]: r[1] for r in u.execute("SELECT osis, color FROM highlight WHERE profile_id = ?", (pid,))}
    stamp = date.today().isoformat()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", prof).strip("-") or "notes"
    if format == "json":
        body = json.dumps({"profile": prof, "exported": stamp, "notes": notes,
                           "highlights": [{"osis": k, "ref": ref_label(k), "color": v}
                                          for k, v in sorted(hl.items(), key=lambda kv: canon_key(kv[0]))]},
                          ensure_ascii=False, indent=2)
        media, ext = "application/json", "json"
    elif format == "md":
        lines = [f"# Scriptoria notes — {prof}", f"_Exported {stamp}_", ""]
        current_book = None
        for n in notes:
            book = n["osis"].split(".")[0]
            if book != current_book:
                lines += [f"## {BOOK[book]['name']}", ""]
                current_book = book
            tags_s = "  " + " ".join(f"#{t.replace(' ', '-')}" for t in n["tags"]) if n["tags"] else ""
            lines += [f"### {n['ref']}{tags_s}", "", n["body"], ""]
        body, media, ext = "\n".join(lines), "text/markdown", "md"
    else:
        raise HTTPException(400, "format must be md or json")
    return Response(body, media_type=f"{media}; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="scriptoria-{safe}-{stamp}.{ext}"'})
