"""Where Scriptoria keeps its files. Every path can be overridden by an
environment variable, which is also how the tests point at scratch locations.

  SCRIPTORIA_DB        content database (scripture, lexicons, originals) — rebuildable
  SCRIPTORIA_USER_DB   user database (profiles, notes, highlights)      — precious
  SCRIPTORIA_DATA      download cache for build sources
  SCRIPTORIA_BIBLES    a thiagobodruk bible zip or json/ folder for the translation library
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent

HOST, PORT = "127.0.0.1", 8701

# Translation library source (MIT-licensed repo of 120+ versions, 67 languages).
LIBRARY_RAW_URL = "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/{abbr}.json"


def _user_data_home() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def content_db() -> Path:
    return Path(os.environ.get("SCRIPTORIA_DB", ROOT / "scriptoria.db"))


def user_db() -> Path:
    return Path(os.environ.get("SCRIPTORIA_USER_DB", _user_data_home() / "scriptoria" / "user.db"))


def data_dir() -> Path:
    return Path(os.environ.get("SCRIPTORIA_DATA", ROOT / "data"))


def bibles_source_candidates() -> list[Path]:
    """Places a downloaded thiagobodruk bible zip/folder might be, in priority order."""
    out = []
    if os.environ.get("SCRIPTORIA_BIBLES"):
        out.append(Path(os.environ["SCRIPTORIA_BIBLES"]).expanduser())
    d = data_dir()
    home = Path.home()
    out += [d / "bible.zip", d / "bible-master.zip", d / "bible-master" / "json",
            home / "Downloads" / "bible.zip", home / "Downloads" / "bible-master.zip",
            home / "Downloads" / "bible-master" / "json"]
    return out
