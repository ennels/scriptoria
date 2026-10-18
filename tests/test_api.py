"""End-to-end API tests against the built scripture database."""
from __future__ import annotations

import pytest

from conftest import BIBLES_ZIP, needs_db

pytestmark = needs_db


def test_meta_and_translations(client):
    m = client.get("/api/meta").json()
    assert m["ready"] and m["schema_version"] >= 2
    codes = {t["code"] for t in client.get("/api/translations").json()}
    assert {"KJV", "ORIG", "ORIG-TR"} <= codes


def test_every_kjv_verse_has_original_words():
    from scriptoria import db
    con = db.connect(must_exist=True)
    missing = con.execute(
        "SELECT COUNT(*) FROM verse_text vt JOIN translation t ON t.id = vt.translation_id "
        "WHERE t.code = 'KJV' AND NOT EXISTS (SELECT 1 FROM original_word w WHERE w.verse_id = vt.verse_id)"
    ).fetchone()[0]
    con.close()
    assert missing == 0


def test_chapter_parallel_with_words_and_title(client):
    d = client.get("/api/chapter", params={"book": "psalm", "chapter": 3, "translations": "WEB,ORIG",
                                           "words": 1}).json()
    assert d["book"] == "Ps" and d["prev"]["chapter"] == 2 and d["next"]["chapter"] == 4
    title, v1 = d["verses"][0], d["verses"][1]
    assert title["superscription"] and title["verse"] == 0 and title["words"]
    assert set(v1["texts"]) == {"WEB", "ORIG"} and v1["words"][0]["lang"] == "hebrew"
    assert "/" not in v1["words"][0]["text"]


def test_chapter_bounds(client):
    assert client.get("/api/chapter", params={"book": "Jude", "chapter": 2}).status_code == 404
    assert client.get("/api/chapter", params={"book": "Nope", "chapter": 1}).status_code == 404
    assert client.get("/api/chapter", params={"book": "Rev", "chapter": 22}).json()["next"] is None


def test_interlinear_alignment_notes(client):
    d = client.get("/api/verse/Mal.4.1/interlinear").json()
    assert d["aligned"] and "Hebrew 3:19" in d["note"]
    w = d["words"][0]
    assert w["parsing"]["label"] and w["lemma"] and w["strongs"]
    d = client.get("/api/verse/1John.5.7/interlinear").json()
    assert any((w["variant"] or {}).get("kind") == "tr-only" for w in d["words"])     # Johannine Comma
    d = client.get("/api/verse/3John.1.15/interlinear").json()
    assert not d["aligned"] and "numbers verses differently" in d["note"]


def test_crossrefs_batched(client):
    d = client.get("/api/verse/John.3.16/crossrefs", params={"limit": 5}).json()
    assert d["crossrefs"][0]["ref"] == "Romans 5:8" and d["crossrefs"][0]["text"]
    assert any("–" in x["ref"] for x in d["crossrefs"])                                # ranged target


def test_word_study_and_concordance(client):
    d = client.get("/api/word/G26").json()
    assert d["lemma"] == "ἀγάπη" and d["occurrences"] > 100 and d["verses"] > 100
    assert d["forms"][0]["parsing"] and d["glosses"][0]["gloss"] == "love" and d["by_book"]
    assert "<script" not in d["senses"][0]["definition"]
    occ = client.get("/api/word/G26/occurrences", params={"book": "1John", "limit": 3}).json()
    assert occ["total"] == 14 and len(occ["results"]) == 3 and occ["results"][0]["words"]
    senses = client.get("/api/word/H7225").json()["senses"]
    assert {s["dstrong"] for s in senses} >= {"H7225G", "H7225H"}
    assert client.get("/api/word/xyz").status_code == 404


def test_morph_compound(client):
    d = client.get("/api/morph/HR/Ncfsa", params={"language": "hebrew"}).json()
    assert d["label"].startswith("Preposition + Noun")


@pytest.mark.parametrize("params,expect", [
    ({"q": "love thy neighbour", "mode": "phrase"}, 6),
    ({"q": "grace mercy", "mode": "any", "scope": "nt"}, 100),
    ({"q": "G26"}, 100),
    ({"q": "agape", "mode": "original"}, 100),
    ({"q": "λογοσ", "translations": "ORIG", "mode": "all"}, 50),
    ({"q": "בראשית", "translations": "ORIG", "mode": "all"}, 4),
    ({"q": "love", "translations": "*", "scope": "1John"}, 100),
])
def test_search_modes(client, params, expect):
    d = client.get("/api/search", params=params).json()
    assert d["total"] >= expect and d["results"] and d["by_book"]


def test_resolve(client):
    r = client.get("/api/resolve", params={"q": "1 cor 13:4-7"}).json()
    assert r["found"] and r["osis"] == "1Cor.13.4" and r["verse_end"] == 7
    assert client.get("/api/resolve", params={"q": "love one another"}).json() == {"found": False, "query": "love one another"}


def test_search_reference_and_errors(client):
    assert client.get("/api/search", params={"q": "jn 3:16"}).json()["reference"]["osis"] == "John.3.16"
    assert client.get("/api/search", params={"q": "faith AND (", "mode": "advanced"}).status_code == 400
    assert client.get("/api/search", params={"q": "x", "mode": "bogus"}).status_code == 400
    html = client.get("/api/search", params={"q": "love"}).json()["results"][0]["html"]
    assert "<mark>" in html and "<script" not in html


def test_profiles_keep_notes_apart(client):
    me = client.get("/api/profiles").json()["current"]
    anna = client.post("/api/profiles", json={"name": "Anna", "color": "sage"}).json()["id"]
    H = {"X-Profile": str(anna)}
    client.put("/api/highlights/John.3.16", json={"color": "amber"}, headers=H)
    n = client.post("/api/notes", json={"osis": "John.3.16", "body": "God's love", "tags": ["love", "#love"]},
                    headers=H).json()
    assert n["tags"] == ["love"]
    assert client.get("/api/annotations", params={"book": "John", "chapter": 3}, headers=H).json() == \
        {"highlights": {"John.3.16": "amber"}, "notes": {"John.3.16": 1}}
    assert client.get("/api/annotations", params={"book": "John", "chapter": 3},
                      headers={"X-Profile": str(me)}).json() == {"highlights": {}, "notes": {}}
    assert client.patch(f"/api/notes/{n['id']}", json={"body": "x"}, headers={"X-Profile": str(me)}).status_code == 404
    md = client.get("/api/notes/export", params={"format": "md"}, headers=H)
    assert "### John 3:16  #love" in md.text and "attachment" in md.headers["content-disposition"]
    assert client.post("/api/notes", json={"osis": "Nope.1.1", "body": "x"}, headers=H).status_code == 400


def test_settings_roundtrip(client):
    s = client.put("/api/settings", json={"panes": [{"book": "John", "chapter": 3}], "theme": "dark"}).json()
    assert s["panes"][0]["book"] == "John" and client.get("/api/settings").json()["theme"] == "dark"


def test_library_catalog(client):
    d = client.get("/api/library").json()
    assert len(d["translations"]) >= 120 and len(d["languages"]) >= 60
    kjv = next(t for t in d["translations"] if t["code"] == "KJV")
    assert kjv["installed"]
    assert client.delete("/api/library/ORIG").status_code == 400


@pytest.mark.skipif(BIBLES_ZIP is None, reason="needs a local bible.zip")
def test_library_install_and_remove(content_copy, monkeypatch):
    monkeypatch.setenv("SCRIPTORIA_BIBLES", str(BIBLES_ZIP))
    from fastapi.testclient import TestClient
    from scriptoria.server import app
    with TestClient(app, headers={"X-Scriptoria": "1"}) as c:
        r = c.post("/api/library/KEHM")                          # Arabic, right-to-left
        assert r.status_code == 200 and r.json()["verses"] > 30000
        t = next(t for t in c.get("/api/translations").json() if t["code"] == "KEHM")
        assert t["direction"] == "rtl"
        d = c.get("/api/chapter", params={"book": "John", "chapter": 1, "translations": "KEHM"}).json()
        assert d["verses"][0]["texts"]["KEHM"]
        assert c.get("/api/search", params={"q": "الله", "translations": "KEHM"}).json()["total"] > 0
        assert c.delete("/api/library/KEHM").status_code == 200
        assert "KEHM" not in {t["code"] for t in c.get("/api/translations").json()}
        assert c.get("/api/search", params={"q": "love", "translations": "KJV"}).json()["total"] > 0
        # verse rows only a removed translation used are cleaned up (Douay-Rheims numbers Daniel 3 to 100)
        assert c.get("/api/chapter", params={"book": "Dan", "chapter": 3, "translations": "DRA"}).json()["verses"][-1]["verse"] > 90
        assert c.delete("/api/library/DRA").status_code == 200
        from scriptoria import db
        con = db.connect(must_exist=True)
        assert con.execute("SELECT COUNT(*) FROM verse WHERE osis = 'Dan.3.95'").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM verse WHERE osis = 'Dan.3.30'").fetchone()[0] == 1
        con.close()
