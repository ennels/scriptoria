"""Build the Scriptoria content database from public sources.

    python -m scriptoria.build                                  # KJV + originals + lexicons
    python -m scriptoria.build --bibles ~/Downloads/bible.zip   # + the default English set
    python -m scriptoria.build --bibles bible.zip --versions en # every English version
    python -m scriptoria.build --bibles bible.zip --versions BSB,RVR-ES,LSG

More translations can be added later from the app's Library without rebuilding.
Downloads are cached in data/. User notes live in a separate database and are untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from . import config, library
from .db import SCHEMA_VERSION, connect, init_schema, set_meta
from .importers.crossrefs import import_crossrefs
from .importers.lexicon import import_lexicons
from .importers.morphology import import_morphology
from .importers.original_text import build_original_texts
from .importers.originals import import_originals
from .importers.strongs import import_strongs
from .importers.verses import import_translation, install_rows, rows_from_json

DEFAULT_VERSIONS = ["ASV", "WEB", "BSB", "LSV", "YLT98", "LEB", "BBE", "DRA", "GNV"]

SOURCES = {
    "kjv.json": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/KJV.json",
    "strongs-greek.js": "https://raw.githubusercontent.com/openscriptures/strongs/master/greek/strongs-greek-dictionary.js",
    "strongs-hebrew.js": "https://raw.githubusercontent.com/openscriptures/strongs/master/hebrew/strongs-hebrew-dictionary.js",
    "cross-references.zip": "https://a.openbible.info/data/cross-references.zip",
}
_STEP = "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/"
STEP_FILES = {   # local name -> path in the STEPBible-Data repo (CC BY 4.0)
    "TAGNT_Mat-Jhn.txt": "Translators Amalgamated OT+NT/TAGNT Mat-Jhn - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
    "TAGNT_Act-Rev.txt": "Translators Amalgamated OT+NT/TAGNT Act-Rev - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
    "TAHOT_Gen-Deu.txt": "Translators Amalgamated OT+NT/TAHOT Gen-Deu - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Jos-Est.txt": "Translators Amalgamated OT+NT/TAHOT Jos-Est - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Job-Sng.txt": "Translators Amalgamated OT+NT/TAHOT Job-Sng - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TAHOT_Isa-Mal.txt": "Translators Amalgamated OT+NT/TAHOT Isa-Mal - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt",
    "TBESG.txt": "Lexicons/TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt",
    "TBESH.txt": "Lexicons/TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt",
    "TEGMC.txt": "Morphology codes/TEGMC - Translators Expansion of Greek Morphhology Codes - STEPBible.org CC BY.txt",
    "TEHMC.txt": "Morphology codes/TEHMC - Translators Expansion of Hebrew Morphology Codes - STEPBible.org CC BY.txt",
}


def fetch(name: str, url: str) -> Path:
    d = config.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    print(f"  downloading {name} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)
    return dest


def _choose(selection: str) -> list[dict]:
    sel = selection.strip()
    cat = library.catalog()
    if sel.lower() == "all":
        return cat
    if sel.lower() == "en":
        return [e for e in cat if e["language"] == "en"]
    codes = DEFAULT_VERSIONS if sel.lower() == "default" else [c.strip() for c in sel.split(",") if c.strip()]
    out = []
    for c in codes:
        e = library.entry(c)
        if e:
            out.append(e)
        else:
            print(f"    ! unknown translation code: {c}", file=sys.stderr)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Scriptoria content database")
    ap.add_argument("--bibles", help="thiagobodruk bible zip or json/ folder (else auto-detected)")
    ap.add_argument("--versions", default="default",
                    help="'default', 'en' (all English), 'all', or codes like BSB,ESV,RVR-ES")
    ap.add_argument("--translations", help="an extra translation JSON file (with --code and --name)")
    ap.add_argument("--code", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--no-originals", action="store_true", help="skip Greek/Hebrew, lexicons and morphology")
    ap.add_argument("--db", default=str(config.content_db()))
    args = ap.parse_args(argv)
    t0 = time.time()

    print("==> Downloading sources (cached in data/)")
    paths = {n: fetch(n, u) for n, u in SOURCES.items()}
    if not args.no_originals:
        for local, remote in STEP_FILES.items():
            paths[local] = fetch(local, _STEP + urllib.parse.quote(remote))
    xref_txt = config.data_dir() / "cross_references.txt"
    if not xref_txt.exists():
        with zipfile.ZipFile(paths["cross-references.zip"]) as z:
            z.extractall(config.data_dir())

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()                              # always a clean build
    for ext in ("-wal", "-shm"):
        Path(str(db_path) + ext).unlink(missing_ok=True)
    print(f"==> Building {db_path}")
    con = connect(db_path)
    init_schema(con)

    r = import_translation(con, paths["kjv.json"], "KJV", "King James Version", license="Public Domain",
                           source="scrollmapper:KJV")
    print(f"  KJV            {r['verses']} verses")

    if args.bibles:
        import os
        os.environ["SCRIPTORIA_BIBLES"] = args.bibles
    chosen = [e for e in _choose(args.versions) if e["code"] != "KJV"]
    if chosen:
        src = library.local_source()
        print(f"  translations from {src or 'download'}")
        for e in chosen:
            try:
                raw, origin = library.fetch(e["abbr"])
                rr = install_rows(con, rows_from_json(json.loads(raw.decode("utf-8-sig"))),
                                  code=e["code"], name=e["name"], language=e["language"],
                                  language_name=e["language_name"], direction=e["direction"],
                                  fts=e["fts"], source=f"thiagobodruk:{e['abbr']}")
                print(f"    {e['code']:12} {rr['verses']} verses")
            except Exception as ex:                       # keep building; report clearly
                print(f"    {e['code']:12} SKIPPED ({type(ex).__name__}: {ex})", file=sys.stderr)

    if args.translations:
        if not (args.code and args.name):
            print("  ! --translations needs --code and --name", file=sys.stderr)
            return 2
        rr = import_translation(con, args.translations, args.code.upper(), args.name, source="file")
        print(f"  {args.code.upper():12} {rr['verses']} verses")

    print(f"  Strong's       {import_strongs(con, paths['strongs-greek.js'], paths['strongs-hebrew.js'])}")
    print(f"  cross-refs     {import_crossrefs(con, xref_txt)}")
    if not args.no_originals:
        d = config.data_dir()
        print(f"  originals      {import_originals(con, d)}")
        print(f"  reading texts  {build_original_texts(con)}")
        print(f"  lexicons       {import_lexicons(con, paths['TBESG.txt'], paths['TBESH.txt'])}")
        print(f"  morphology     {import_morphology(con, paths['TEGMC.txt'], paths['TEHMC.txt'])}")

    print("  optimizing")
    for t in ("fts_en", "fts_intl", "fts_cjk"):
        con.execute(f"INSERT INTO {t}({t}) VALUES('optimize')")
    set_meta(con, "schema_version", SCHEMA_VERSION)
    set_meta(con, "built_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    con.commit()
    con.execute("ANALYZE")
    con.execute("VACUUM")
    con.close()
    print(f"Done in {time.time() - t0:.0f}s -> {db_path} ({db_path.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
