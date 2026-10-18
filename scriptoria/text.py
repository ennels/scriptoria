"""Text helpers shared by importers and the API: accent folding for Greek/Hebrew,
Strong's normalization, and a strict sanitizer for lexicon HTML."""
from __future__ import annotations

import html
import re
import unicodedata

_STRONG = re.compile(r"([GH])0*(\d+)([A-Za-z]?)")


def strongs_base(raw: str | None) -> str | None:
    """'G0026' / 'H7225G' / '{H7225G}' -> 'G26' / 'H7225' / 'H7225'."""
    m = _STRONG.search(raw or "")
    return f"{m.group(1)}{int(m.group(2))}" if m else None


def dstrong(raw: str | None) -> str | None:
    """Disambiguated Strong's without zero padding: 'H0430G' -> 'H430G', 'G0025' -> 'G25'."""
    m = _STRONG.search(raw or "")
    return f"{m.group(1)}{int(m.group(2))}{m.group(3).upper()}" if m else None


def fold(s: str | None) -> str:
    """Remove accents, breathings, vowel points and cantillation; lowercase; normalize
    final sigma. 'ἠγάπησεν' -> 'ηγαπησεν', 'בְּרֵאשִׁ֖ית' -> 'בראשית', 'Ἀβραάμ' -> 'αβρααμ'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("/", "").replace("\\", "").replace("־", " ")  # morpheme marks, maqaf
    s = s.lower().replace("ς", "σ")
    s = re.sub(r"[^\w\s]", "", s)
    return unicodedata.normalize("NFC", s).strip()


def is_original_script(s: str) -> bool:
    return any("Ͱ" <= ch <= "Ͽ" or "ἀ" <= ch <= "῿" or "֐" <= ch <= "׿"
               for ch in s)


def reading_form(word: str) -> str:
    """A tagged word as it appears in running text: drop morpheme separators."""
    return word.replace("/", "").replace("\\", "")


_HEB_MARKS = re.compile("[֑-ֽ֯׀׃]")   # cantillation, meteg, paseq, sof pasuq
_PUNCT = re.compile(r"[^\w\s̀-ͯ֐-׿]")


def display_form(word: str, language: str) -> str:
    """Normalize an inflected form for grouping in a word study: Hebrew keeps vowel points
    but drops cantillation; Greek drops punctuation and treats grave as acute."""
    w = reading_form(word or "")
    if language == "hebrew":
        return _HEB_MARKS.sub("", w).strip()
    w = unicodedata.normalize("NFD", w).replace("̀", "́")
    w = _PUNCT.sub("", w).lower()
    return unicodedata.normalize("NFC", w).strip()


# ------------------------------------------------------------- lexicon HTML
_REF_TAG = re.compile(r"<ref=['\"]([^'\"]+)['\"]>(.*?)</ref>", re.S | re.I)
_ALLOWED = {"b", "i", "br", "sup", "sub"}
_TAG = re.compile(r"<\s*(/?)\s*([a-zA-Z0-9]+)[^>]*>")


def sanitize_lexicon_html(raw: str | None) -> str:
    """Keep only <b>, <i>, <br>, <sup>, <sub>; turn STEPBible <ref='Jhn.3.16'> tags into
    <a class="sref" data-ref="Jhn.3.16">. Everything else is escaped or dropped, so the
    result is safe to render with innerHTML."""
    if not raw:
        return ""
    refs: list[tuple[str, str]] = []

    def stash(m):
        refs.append((m.group(1).strip(), _TAG.sub("", m.group(2))))
        return f"\x00{len(refs) - 1}\x00"

    s = raw
    for _ in range(3):                      # refs can be nested one level deep
        s = _REF_TAG.sub(stash, s)
    s = s.replace("__", "")                 # STEP's indentation markers

    out, pos = [], 0
    for m in _TAG.finditer(s):
        out.append(html.escape(html.unescape(s[pos:m.start()]), quote=False))
        closing, name = m.group(1), m.group(2).lower()
        if name in _ALLOWED:
            out.append("<br>" if name == "br" else f"<{closing}{name}>")
        pos = m.end()
    out.append(html.escape(html.unescape(s[pos:]), quote=False))
    s = "".join(out)

    def unstash(m):
        ref, label = refs[int(m.group(1))]
        label = re.sub(r"\x00(\d+)\x00", lambda mm: refs[int(mm.group(1))][1], label)
        return (f'<a class="sref" data-ref="{html.escape(ref)}">'
                f"{html.escape(html.unescape(label), quote=False)}</a>")

    for _ in range(3):
        s = re.sub(r"\x00(\d+)\x00", unstash, s)
    s = re.sub(r"(<br>\s*){3,}", "<br><br>", s).strip()
    return re.sub(r"^(<br>\s*)+|(<br>\s*)+$", "", s)
