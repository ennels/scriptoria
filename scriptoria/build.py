"""Build scriptoria.db: download the public-domain sources and import everything.

    python -m scriptoria.build                       # public-domain data only (seed KJV)
    python -m scriptoria.build --translations my.json --code WEB --name "World English Bible"

Downloads are cached in data/ and skipped if already present.
Originals (STEPBible Greek/Hebrew) import is wired in importers/originals.py.
"""
from __future__ import annotations

import argparse
import sys
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
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args(argv)

    print("==> Downloading public-domain sources")
    paths = {n: fetch(n, u) for n, u in SOURCES.items()}
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

    # Originals (STEPBible) — added by importers/originals.py when present.
    try:
        from .importers.originals import import_originals  # noqa
        print("  Greek/Hebrew originals")
        print(f"    {import_originals(con, DATA)}")
    except ImportError:
        print("  (originals importer not installed yet - skipping Greek/Hebrew)")

    con.close()
    print(f"Done -> {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
