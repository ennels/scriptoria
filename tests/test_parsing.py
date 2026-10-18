"""Pure-function tests: references, STEPBible refs, text folding, lexicon sanitizing, search expressions."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from scriptoria.api.search import fts_expression, scope_range
from scriptoria.importers.original_text import in_edition
from scriptoria.importers.originals import describe_text_type, parse_line, parse_step_ref
from scriptoria.references import parse_reference
from scriptoria.text import display_form, dstrong, fold, sanitize_lexicon_html, strongs_base


@pytest.mark.parametrize("text,label,osis", [
    ("jn 3:16", "John 3:16", "John.3.16"),
    ("1 cor 13", "1 Corinthians 13", None),
    ("Ps 23:1-4", "Psalms 23:1-4", "Ps.23.1"),
    ("gen1:1", "Genesis 1:1", "Gen.1.1"),
    ("Song 2.4", "Song of Solomon 2:4", "Song.2.4"),
    ("III John 1:4", "3 John 1:4", "3John.1.4"),
    ("jude 3", "Jude 1:3", "Jude.1.3"),
    ("2 ti 3:16", "2 Timothy 3:16", "2Tim.3.16"),
    ("phil 4:13", "Philippians 4:13", "Phil.4.13"),
])
def test_parse_reference(text, label, osis):
    r = parse_reference(text)
    assert r and r.label() == label and r.osis == osis


@pytest.mark.parametrize("text", ["love", "john 99", "", "the 3 kings"])
def test_parse_reference_rejects(text):
    assert parse_reference(text) is None


def test_step_ref_shapes():
    assert parse_step_ref("Gen.1.1#01=L", "hebrew") == {
        "book": "Gen", "ch": 1, "vs": 1, "pos": 1, "type": "L", "alt_ref": None}
    r = parse_step_ref("Mal.4.1(3.19)#05=L", "hebrew")          # English 4:1 = Hebrew 3:19
    assert (r["ch"], r["vs"], r["alt_ref"]) == (4, 1, "heb:3.19")
    r = parse_step_ref("Psa.3.0(3.1)#01=L", "hebrew")           # Psalm title = verse 0
    assert (r["ch"], r["vs"]) == (3, 0)
    r = parse_step_ref("Act.2.11[2.10]#03=NKO", "greek")       # KJV number wins
    assert (r["ch"], r["vs"], r["alt_ref"]) == (2, 10, "nrsv:2.11")
    r = parse_step_ref("Rom.16.25{14.24}#01=NKO", "greek")
    assert (r["ch"], r["vs"], r["alt_ref"]) == (16, 25, "other:14.24")
    assert parse_step_ref("# Gen.1.1 header", "hebrew") is None


def test_parse_hebrew_line():
    line = ("Gen.1.1#01=L\tבְּ/רֵאשִׁ֖ית\tbe./re.Shit\tin/ beginning\tH9003/{H7225G}\tHR/Ncfsa\t\t\tH7225G\t\t\t"
            "H9003=ב=in/{H7225G=רֵאשִׁית=: beginning»first:1_beginning}\t\t\t\t\t")
    ref, w = parse_line(line, "hebrew")
    assert w["dstrong"] == "H7225G" and w["strongs"] == "H7225"
    assert w["lemma"] == "רֵאשִׁית" and w["meaning"] == "beginning" and w["morph"] == "HR/Ncfsa"
    assert w["norm"] == "בראשית"


def test_parse_greek_line_strips_number_markers():
    line = "Rom.16.25{14.24}#01=NKO\tΤῷ (Tō)\t{14.24} To Him\tG3588=T-DSM\tὁ=the/this/who\tNA28+TR\t\t\t\tthe\t\tG3588\t"
    ref, w = parse_line(line, "greek")
    assert w["gloss"] == "To Him" and w["translit"] == "Tō" and w["morph"] == "T-DSM"


def test_editions():
    assert in_edition("NKO", "N") and in_edition("NKO", "K")
    assert in_edition("K", "K") and not in_edition("K", "N")
    assert in_edition("N(k)O", "K")                 # minor spelling difference: TR still has the word
    assert not in_edition("N(K)O", "K")             # TR has a different word here
    assert describe_text_type("K", "greek")["kind"] == "tr-only"
    assert describe_text_type("NO", "greek")["kind"] == "na-only"
    assert describe_text_type("NKO", "greek") is None
    assert describe_text_type("Q(K)", "hebrew")["kind"] == "qere"
    assert describe_text_type("L", "hebrew") is None


def test_text_helpers():
    assert fold("ἠγάπησεν") == "ηγαπησεν"
    assert fold("λόγος") == fold("λογοσ") == fold("ΛΌΓΟΣ")
    assert fold("בְּרֵאשִׁ֖ית") == "בראשית"
    assert fold("agapē") == "agape" and fold("re.shit") == "reshit"
    assert dstrong("H0430G") == "H430G" and dstrong("G0026") == "G26"
    assert strongs_base("{H7225G}") == "H7225"
    assert display_form("θεὸς,", "greek") == display_form("θεός", "greek")
    assert display_form("בְּ/רֵאשִׁ֖ית", "hebrew") == "בְּרֵאשִׁית"


def test_lexicon_html_is_sanitized():
    raw = ("<b>ἀγάπη</b> <BR /><script>alert(1)</script><img src=x onerror=alert(1)>"
           "<ref='Jhn.13.35'>Jhn.13:35;</ref> <a href='javascript:x'>bad</a> __1. <i>ok</i>")
    out = sanitize_lexicon_html(raw)
    assert "<script" not in out and "<img" not in out and "onerror" not in out and "href" not in out
    assert '<a class="sref" data-ref="Jhn.13.35">Jhn.13:35;</a>' in out
    assert "<b>ἀγάπη</b>" in out and "<i>ok</i>" in out and "<br>" in out and "__" not in out


def test_fts_expression_modes():
    assert fts_expression("love neighbour", "all") == '"love" "neighbour"'
    assert fts_expression("love thy neighbour", "phrase") == '"love thy neighbour"'
    assert fts_expression("grace mercy", "any") == '"grace" OR "mercy"'
    assert fts_expression("believ*", "all") == '"believ"*'
    assert fts_expression('he said "NOT', "all") == '"he" "said" "NOT"'     # operators are quoted away
    assert fts_expression("faith NEAR(works, 4)", "advanced") == "faith NEAR(works, 4)"
    with pytest.raises(HTTPException):
        fts_expression("!!!", "all")


def test_scope_range():
    assert scope_range("all")[:2] == (1, 66)
    assert scope_range("ot")[:2] == (1, 39) and scope_range("nt")[:2] == (40, 66)
    assert scope_range("Rom")[:2] == (45, 45)
    assert scope_range("Matt-John")[:2] == (40, 43)
    assert scope_range("John-Matt")[:2] == (40, 43)
