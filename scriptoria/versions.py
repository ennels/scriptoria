"""Translation metadata for the thiagobodruk multi-translation set.

Files are named <lang>_<code>.json (e.g. en_kjv.json). We derive the display
name from NAMES where known, else the uppercased code.
"""
from __future__ import annotations

from pathlib import Path

# Curated default: well-known English versions spanning literal -> dynamic,
# all public-domain or freely licensed. Add any others with --versions.
DEFAULT = ["kjv", "asv", "web", "bsb", "lsv", "ylt98", "leb", "bbe", "dra", "gnv"]

LANG_NAMES = {
    "en": "English", "pt": "Portuguese", "es": "Spanish", "de": "German",
    "fr": "French", "it": "Italian", "ko": "Korean", "ar": "Arabic",
    "sv": "Swedish", "vi": "Vietnamese", "tl": "Tagalog", "ta": "Tamil",
    "ru": "Russian", "zh": "Chinese", "eo": "Esperanto", "gd": "Scottish Gaelic",
}

NAMES = {
    "kjv": "King James Version", "kjva": "King James Version with Apocrypha",
    "asv": "American Standard Version (1901)", "web": "World English Bible",
    "webbe": "World English Bible (British)", "wmb": "World Messianic Bible",
    "bsb": "Berean Standard Bible", "mbsb": "Majority Berean Standard Bible",
    "lsv": "Literal Standard Version", "ylt98": "Young's Literal Translation",
    "leb": "Lexham English Bible", "bbe": "Bible in Basic English",
    "dra": "Douay-Rheims American", "gnv": "Geneva Bible (1599)",
    "darby": "Darby Translation", "jub": "Jubilee Bible 2000",
    "gnt": "Good News Translation", "esv": "English Standard Version",
    "niv": "New International Version", "nkjv": "New King James Version",
    "nasb": "New American Standard Bible", "nlt": "New Living Translation",
    "csb": "Christian Standard Bible", "amp": "Amplified Bible",
    "cev": "Contemporary English Version", "fbv": "Free Bible Version",
    "engrv": "Revised Version (1885)", "t4t": "Translation for Translators",
}


def meta_for(path: Path) -> tuple[str, str, str]:
    """-> (code, display_name, language_code) from a filename like 'en_kjv.json'."""
    stem = path.stem                      # en_kjv
    lang, _, code = stem.partition("_")   # en, kjv
    if not code:                          # no language prefix
        lang, code = "en", stem
    name = NAMES.get(code, code.upper())
    lang_label = LANG_NAMES.get(lang, lang)
    display = name if lang == "en" else f"{name} ({lang_label})"
    return code.upper(), display, lang
