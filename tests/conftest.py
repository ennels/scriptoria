"""Shared fixtures. API tests run against the built scripture database (skipped if absent)
and always use a throwaway user database, so real notes are never touched."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DB = Path(os.environ.get("SCRIPTORIA_DB", ROOT / "scriptoria.db"))
BIBLES_ZIP = next((p for p in [Path(os.environ.get("SCRIPTORIA_BIBLES", "")), ROOT / "data" / "bible.zip",
                               Path("/mnt/user-data/uploads/bible.zip")] if str(p) and p.is_file()), None)

needs_db = pytest.mark.skipif(not CONTENT_DB.exists(), reason="build scriptoria.db first")


@pytest.fixture(autouse=True)
def isolated_user_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIPTORIA_USER_DB", str(tmp_path / "user.db"))
    monkeypatch.setenv("SCRIPTORIA_DB", str(CONTENT_DB))
    yield tmp_path / "user.db"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from scriptoria.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def content_copy(tmp_path, monkeypatch):
    """A private copy of the scripture DB for tests that install/remove translations."""
    dest = tmp_path / "content.db"
    shutil.copy(CONTENT_DB, dest)
    monkeypatch.setenv("SCRIPTORIA_DB", str(dest))
    return dest
