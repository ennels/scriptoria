"""Parse what people type as a Bible reference: 'jn 3:16', '1 cor 13', 'Ps 23:1-4',
'Romans 8', 'gen1:1', 'Song 2.4'. Returns a structured reference or None."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .books import BOOKS, to_osis

# Common abbreviations not reachable by prefix matching (or ambiguous as prefixes).
_ABBR = {
    "jn": "John", "jhn": "John", "joh": "John", "mt": "Matt", "mtt": "Matt", "mk": "Mark",
    "mr": "Mark", "mrk": "Mark", "lk": "Luke", "lu": "Luke", "luk": "Luke", "ac": "Acts",
    "ro": "Rom", "rm": "Rom", "ga": "Gal", "ep": "Eph", "php": "Phil", "pp": "Phil",
    "phm": "Phlm", "phlm": "Phlm", "philem": "Phlm", "hb": "Heb", "jas": "Jas", "jm": "Jas",
    "jud": "Jude", "jd": "Jude", "re": "Rev", "rv": "Rev", "ge": "Gen", "gn": "Gen",
    "ex": "Exod", "exo": "Exod", "lv": "Lev", "le": "Lev", "nu": "Num", "nm": "Num",
    "dt": "Deut", "de": "Deut", "jos": "Josh", "jsh": "Josh", "jg": "Judg", "jdg": "Judg",
    "jdgs": "Judg", "rt": "Ruth", "ru": "Ruth", "ne": "Neh", "es": "Esth", "est": "Esth",
    "jb": "Job", "ps": "Ps", "psa": "Ps", "psm": "Ps", "pss": "Ps", "pr": "Prov",
    "prv": "Prov", "pro": "Prov", "ec": "Eccl", "ecc": "Eccl", "qoh": "Eccl", "so": "Song",
    "sos": "Song", "ss": "Song", "sng": "Song", "is": "Isa", "je": "Jer", "jr": "Jer",
    "la": "Lam", "lm": "Lam", "ezk": "Ezek", "eze": "Ezek", "ezr": "Ezra", "dn": "Dan",
    "da": "Dan", "ho": "Hos", "jl": "Joel", "jol": "Joel", "am": "Amos", "ob": "Obad",
    "jnh": "Jonah", "jon": "Jonah", "mi": "Mic", "na": "Nah", "nam": "Nah", "hab": "Hab",
    "zp": "Zeph", "zep": "Zeph", "hg": "Hag", "zc": "Zech", "zec": "Zech", "ml": "Mal",
}
for _n in ("1", "2"):
    _ABBR.update({f"{_n}sm": f"{_n}Sam", f"{_n}sa": f"{_n}Sam", f"{_n}ki": f"{_n}Kgs",
                  f"{_n}kg": f"{_n}Kgs", f"{_n}ch": f"{_n}Chr", f"{_n}chr": f"{_n}Chr",
                  f"{_n}co": f"{_n}Cor", f"{_n}cor": f"{_n}Cor", f"{_n}th": f"{_n}Thess",
                  f"{_n}ti": f"{_n}Tim", f"{_n}tm": f"{_n}Tim", f"{_n}pe": f"{_n}Pet",
                  f"{_n}pt": f"{_n}Pet", f"{_n}jn": f"{_n}John", f"{_n}jo": f"{_n}John"})
_ABBR.update({"3jn": "3John", "3jo": "3John"})

_NAMES = [(re.sub(r"[^a-z0-9]", "", b["name"].lower()), b["osis"]) for b in BOOKS]
_BOOK_INFO = {b["osis"]: b for b in BOOKS}

_RE = re.compile(
    r"^\s*(?P<book>(?:[1-3]|i{1,3})?\s*[a-z][a-z .]*?)\.?\s*"
    r"(?P<ch>\d+)(?:\s*[:.]\s*(?P<v1>\d+)(?:\s*[-–]\s*(?P<v2>\d+))?)?\s*$",
    re.I)


@dataclass
class Reference:
    book: str            # OSIS
    chapter: int
    verse: int | None = None
    verse_end: int | None = None

    @property
    def osis(self) -> str | None:
        return f"{self.book}.{self.chapter}.{self.verse}" if self.verse else None

    def label(self) -> str:
        s = f"{_BOOK_INFO[self.book]['name']} {self.chapter}"
        if self.verse:
            s += f":{self.verse}" + (f"-{self.verse_end}" if self.verse_end else "")
        return s


def resolve_book(text: str) -> str | None:
    """Book name/abbreviation -> OSIS. Exact names first, then abbreviations,
    then an unambiguous prefix of a full name ('rom' -> Romans, 'phil' -> Philippians)."""
    t = text.strip().lower()
    t = re.sub(r"^(iii|ii|i)\s+", lambda m: str(len(m.group(1))), t)
    key = re.sub(r"[^a-z0-9]", "", t)
    if not key:
        return None
    hit = to_osis(text) or _ABBR.get(key)
    if hit:
        return hit
    cands = {osis for name, osis in _NAMES if name.startswith(key)}
    if len(cands) == 1:
        return cands.pop()
    if key == "phil":
        return "Phil"
    return None


def parse_reference(text: str) -> Reference | None:
    m = _RE.match(text or "")
    if not m:
        return None
    book = resolve_book(m.group("book"))
    if not book:
        return None
    ch = int(m.group("ch"))
    v1 = int(m.group("v1")) if m.group("v1") else None
    v2 = int(m.group("v2")) if m.group("v2") else None
    if _BOOK_INFO[book]["chapters"] == 1 and v1 is None and ch > 1:
        ch, v1 = 1, ch                       # 'Jude 3' = Jude 1:3
    if not 1 <= ch <= _BOOK_INFO[book]["chapters"]:
        return None
    if v2 is not None and v1 is not None and v2 < v1:
        v2 = None
    return Reference(book, ch, v1, v2)
