"""Regenerate scriptoria/catalog.json from a thiagobodruk bible zip (dev tool).

    python scripts/make_catalog.py path/to/bible.zip
"""
from __future__ import annotations

import collections
import json
import re
import sys
import zipfile
from pathlib import Path

RTL = {"ar", "fa", "ur", "ckb", "he", "yi", "ps", "sd", "ug", "dv"}
NO_SPACES = {"zh", "ja", "th", "my", "km", "lo"}          # need trigram search
OUT = Path(__file__).resolve().parent.parent / "scriptoria" / "catalog.json"


def main(zip_path: str) -> None:
    z = zipfile.ZipFile(zip_path)
    index_name = next(n for n in z.namelist() if n.endswith("json/index.json"))
    index = json.loads(z.read(index_name).decode("utf-8-sig"))
    present = {Path(n).stem for n in z.namelist() if re.search(r"/json/[^/]+\.json$", n)}
    sizes = {Path(n).stem: z.getinfo(n).file_size for n in z.namelist() if n.endswith(".json")}

    entries = []
    for group in index:
        for v in group["versions"]:
            abbr = v["abbreviation"]
            if abbr not in present:
                continue
            lang, _, short = abbr.partition("_")
            entries.append({"abbr": abbr, "short": short.upper(), "name": v["name"].strip(),
                            "language": lang, "language_name": group["language"].strip(),
                            "direction": "rtl" if lang in RTL else "ltr",
                            "fts": "en" if lang == "en" else "cjk" if lang in NO_SPACES else "intl",
                            "size": sizes.get(abbr, 0)})
    clashes = collections.Counter(e["short"] for e in entries)
    for e in entries:
        e["code"] = e["short"] if e["language"] == "en" or clashes[e["short"]] == 1 \
            else f"{e['short']}-{e['language'].upper()}"
        del e["short"]
    entries.sort(key=lambda e: (e["language_name"] != "English", e["language_name"], e["name"]))
    assert len({e["code"] for e in entries}) == len(entries), "duplicate codes"
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    langs = len({e["language"] for e in entries})
    print(f"{len(entries)} translations in {langs} languages -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
