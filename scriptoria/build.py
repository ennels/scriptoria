"""Build scriptoria.db: download the public-domain sources and import everything.

    python -m scriptoria.build                       # public-domain data only (seed KJV)
    python -m scriptoria.build --translations my.json --code WEB --name "World English Bible"

Downloads are cached in data/ and skipped if already present.
Originals (STEPBible Greek/Hebrew) import is wired in importers/originals.py.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .db import connect, init_schema, DEFAULT_DB
from .importers.verses import import_translation
from .importers.crossrefs import import_crossrefs
from .importers.strongs import import_strongs

DATA = Path(__file__).resolve().parent.parent / "data"
SOURCES = {
    "kjv.json": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/KJV.json",
    "strongs-greek.js": "https://raw.githubusercontent.com/openscriptures/strongs/master/greek/strongs-greek-dictionary.js",
    "strongs-hebrew.js": "https://raw.githubusercontent.com/openscriptures/strongs/master/hebrew/strongs-hebrew-dictionary.js",
    "cross-references.zip": "https://a.openbible.info/data/cross-references.zip",
}

# STEPBible tagged originals (CC BY). Saved locally under short names; the originals
# importer keys on the TAGNT/TAHOT prefix for Greek vs Hebrew.
_STEP_BASE = "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/"
_STEP_DIR = "Translators Amalgamated OT+NT/"
STEP_FILES = {
    "TAGNT_Mat-Jhn.txt": "TAGNT Mat-Jhn - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
    "TAGNT_Act-Rev.txt": "TAGNT Act-Rev - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
    "TAHOT_Gen-Deu.txt": "TAHOT Gen-Deu - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Jos-Est.txt": "TAHOT Jos-Est - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Job-Sng.txt": "TAHOT Job-Sng - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Isa-Mal.txt": "TAHOT Isa-Mal - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
}


def fetch(name: str, url: str) -> Path:
    DATA.mkdir(exist_ok=True)
    dest = DATA / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    print(f"  downloading {name} ...", flush=True)
    urllib.request.urlretrieve(url, dest)
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Scriptoria database")
    ap.add_argument("--translations", help="path to a single translations JSON")
    ap.add_argument("--code", default="", help="translation code (with --translations)")
    ap.add_argument("--name", default="", help="display name (with --translations)")
    ap.add_argument("--bibles-dir", help="thiagobodruk json/ directory of <lang>_<code>.json files")
    ap.add_argument("--versions", default="default",
                    help="comma-separated codes (kjv,asv,...), or 'default', 'en' (all English), 'all'")
    ap.add_argument("--no-originals", action="store_true", help="skip the Greek/Hebrew STEPBible import")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args(argv)

    print("==> Downloading public-domain sources")
    paths = {n: fetch(n, u) for n, u in SOURCES.items()}
    if not args.no_originals:
        for local, remote in STEP_FILES.items():
            fetch(local, _STEP_BASE + urllib.parse.quote(_STEP_DIR + remote))
    xref_txt = DATA / "cross_references.txt"
    if not xref_txt.exists():
        with zipfile.ZipFile(paths["cross-references.zip"]) as z:
            z.extractall(DATA)

    print("==> Building database")
    con = connect(args.db)
    init_schema(con)

    print("  seed translation (KJV)")
    r = import_translation(con, paths["kjv.json"], "KJV", "King James Version (1769)", license="Public Domain")
    print(f"    {r['verses']} verses" + (f"  (unknown books: {r['unknown_books']})" if r["unknown_books"] else ""))

    if args.bibles_dir:
        from .versions import DEFAULT, meta_for
        jdir = Path(args.bibles_dir)
        files = sorted(jdir.glob("*.json"))
        sel = args.versions.strip().lower()
        if sel == "all":
            chosen = files
        elif sel == "en":
            chosen = [f for f in files if f.stem.startswith("en_") or f.stem == "en"]
        elif sel == "default":
            codes = set(DEFAULT)
            chosen = [f for f in files if f.stem.replace("en_", "") in codes]
        else:
            want = {c.strip() for c in sel.split(",")}
            chosen = [f for f in files if f.stem in want or f.stem.replace("en_", "") in want]
        print(f"  importing {len(chosen)} translation(s) from {jdir}")
        for f in chosen:
            code, name, lang = meta_for(f)
            if code == "KJV":  # already seeded
                continue
            try:
                r = import_translation(con, f, code, name, language=lang)
                print(f"    {code:8} {r['verses']} verses" + (f"  (unknown: {r['unknown_books']})" if r["unknown_books"] else ""))
            except Exception as e:
                print(f"    {code:8} SKIPPED ({type(e).__name__}: {e})", file=sys.stderr)

    if args.translations:
        if not (args.code and args.name):
            print("  ! --translations needs --code and --name", file=sys.stderr)
            return 2
        r = import_translation(con, args.translations, args.code, args.name)
        print(f"  {args.code}: {r['verses']} verses" + (f"  (unknown books: {r['unknown_books']})" if r["unknown_books"] else ""))

    print("  Strong's lexicon")
    print(f"    {import_strongs(con, paths['strongs-greek.js'], paths['strongs-hebrew.js'])['strongs_entries']} entries")
    print("  cross-references")
    print(f"    {import_crossrefs(con, xref_txt)['cross_refs']} links")

    if not args.no_originals:
        from .importers.originals import import_originals
        print("  Greek/Hebrew originals (STEPBible)")
        print(f"    {import_originals(con, DATA)}")

    con.close()
    print(f"Done -> {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
