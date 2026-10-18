import re
"""Canonical 66-book table, the backbone every dataset normalizes to.

Each book has: OSIS code (the join key, as used by the OpenBible cross-references),
the STEPBible 3-letter code (for the Greek/Hebrew originals), a display name,
testament, 1-based canonical position, and chapter count.

STEP codes are verified against the actual STEPBible files at import time
(see importers/originals.py); the ones here are the standard SBL abbreviations.
"""

# osis, step3, name, testament, chapters
_BOOKS = [
    ("Gen", "Gen", "Genesis", "OT", 50), ("Exod", "Exo", "Exodus", "OT", 40),
    ("Lev", "Lev", "Leviticus", "OT", 27), ("Num", "Num", "Numbers", "OT", 36),
    ("Deut", "Deu", "Deuteronomy", "OT", 34), ("Josh", "Jos", "Joshua", "OT", 24),
    ("Judg", "Jdg", "Judges", "OT", 21), ("Ruth", "Rut", "Ruth", "OT", 4),
    ("1Sam", "1Sa", "1 Samuel", "OT", 31), ("2Sam", "2Sa", "2 Samuel", "OT", 24),
    ("1Kgs", "1Ki", "1 Kings", "OT", 22), ("2Kgs", "2Ki", "2 Kings", "OT", 25),
    ("1Chr", "1Ch", "1 Chronicles", "OT", 29), ("2Chr", "2Ch", "2 Chronicles", "OT", 36),
    ("Ezra", "Ezr", "Ezra", "OT", 10), ("Neh", "Neh", "Nehemiah", "OT", 13),
    ("Esth", "Est", "Esther", "OT", 10), ("Job", "Job", "Job", "OT", 42),
    ("Ps", "Psa", "Psalms", "OT", 150), ("Prov", "Pro", "Proverbs", "OT", 31),
    ("Eccl", "Ecc", "Ecclesiastes", "OT", 12), ("Song", "Sng", "Song of Solomon", "OT", 8),
    ("Isa", "Isa", "Isaiah", "OT", 66), ("Jer", "Jer", "Jeremiah", "OT", 52),
    ("Lam", "Lam", "Lamentations", "OT", 5), ("Ezek", "Ezk", "Ezekiel", "OT", 48),
    ("Dan", "Dan", "Daniel", "OT", 12), ("Hos", "Hos", "Hosea", "OT", 14),
    ("Joel", "Jol", "Joel", "OT", 3), ("Amos", "Amo", "Amos", "OT", 9),
    ("Obad", "Oba", "Obadiah", "OT", 1), ("Jonah", "Jon", "Jonah", "OT", 4),
    ("Mic", "Mic", "Micah", "OT", 7), ("Nah", "Nam", "Nahum", "OT", 3),
    ("Hab", "Hab", "Habakkuk", "OT", 3), ("Zeph", "Zep", "Zephaniah", "OT", 3),
    ("Hag", "Hag", "Haggai", "OT", 2), ("Zech", "Zec", "Zechariah", "OT", 14),
    ("Mal", "Mal", "Malachi", "OT", 4),
    ("Matt", "Mat", "Matthew", "NT", 28), ("Mark", "Mrk", "Mark", "NT", 16),
    ("Luke", "Luk", "Luke", "NT", 24), ("John", "Jhn", "John", "NT", 21),
    ("Acts", "Act", "Acts", "NT", 28), ("Rom", "Rom", "Romans", "NT", 16),
    ("1Cor", "1Co", "1 Corinthians", "NT", 16), ("2Cor", "2Co", "2 Corinthians", "NT", 13),
    ("Gal", "Gal", "Galatians", "NT", 6), ("Eph", "Eph", "Ephesians", "NT", 6),
    ("Phil", "Php", "Philippians", "NT", 4), ("Col", "Col", "Colossians", "NT", 4),
    ("1Thess", "1Th", "1 Thessalonians", "NT", 5), ("2Thess", "2Th", "2 Thessalonians", "NT", 3),
    ("1Tim", "1Ti", "1 Timothy", "NT", 6), ("2Tim", "2Ti", "2 Timothy", "NT", 4),
    ("Titus", "Tit", "Titus", "NT", 3), ("Phlm", "Phm", "Philemon", "NT", 1),
    ("Heb", "Heb", "Hebrews", "NT", 13), ("Jas", "Jas", "James", "NT", 5),
    ("1Pet", "1Pe", "1 Peter", "NT", 5), ("2Pet", "2Pe", "2 Peter", "NT", 3),
    ("1John", "1Jn", "1 John", "NT", 5), ("2John", "2Jn", "2 John", "NT", 1),
    ("3John", "3Jn", "3 John", "NT", 1), ("Jude", "Jud", "Jude", "NT", 1),
    ("Rev", "Rev", "Revelation", "NT", 22),
]

BOOKS = [
    {"osis": o, "step": s, "name": n, "testament": t, "position": i + 1, "chapters": c}
    for i, (o, s, n, t, c) in enumerate(_BOOKS)
]
OSIS_SET = {b["osis"] for b in BOOKS}

# Build a tolerant name/code -> OSIS lookup (lowercased, punctuation/space-stripped).
def _key(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())

_ALIAS = {}
for b in BOOKS:
    for variant in (b["osis"], b["step"], b["name"], b["name"].replace(" ", "")):
        _ALIAS[_key(variant)] = b["osis"]
# Common extra spellings the datasets / user JSON may use.
_EXTRA = {
    "psalm": "Ps", "psalms": "Ps", "songofsongs": "Song", "canticles": "Song",
    "qoheleth": "Eccl", "revelationofjohn": "Rev", "apocalypse": "Rev",
    "1samuel": "1Sam", "iisamuel": "2Sam", "songofsolomon": "Song",
}
for k, v in _EXTRA.items():
    _ALIAS[_key(k)] = v


_ROMAN = re.compile(r"^\s*(III|II|I)\s+(.+)$", re.I)
_ROMAN_MAP = {"i": "1", "ii": "2", "iii": "3"}


def to_osis(name_or_code: str) -> str | None:
    """Map any book name or code (OSIS, STEP, full name, common variant) to OSIS."""
    s = name_or_code
    m = _ROMAN.match(s)  # "I Chronicles" / "III John" -> "1 Chronicles" / "3 John"
    if m:
        s = _ROMAN_MAP[m.group(1).lower()] + " " + m.group(2)
    return _ALIAS.get(_key(s))
