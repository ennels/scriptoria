# Scriptoria

A local, offline Bible study app — parallel translations, full-text search,
cross-references, Strong's numbers, and Greek/Hebrew word analysis. Runs in your
browser off a local SQLite database. No internet needed once built.

## Status

- [x] Data layer: canonical 66-book verse spine; importers for translations,
      cross-references (OpenBible, ~345k links), and the Strong's lexicon
      (OpenScriptures, ~14k entries). Full-text search via SQLite FTS5.
- [x] Greek/Hebrew originals (STEPBible TAHOT/TAGNT) — interlinear word data with
      Strong's, morphology, transliteration and gloss (~425k tagged words).
- [x] FastAPI backend — chapters, parallel translations, cross-references,
      interlinear, Strong's lexicon, full-text search, notes & highlights.
- [x] Browser UI — illuminated reader with flowing or parallel columns, click-a-verse
      study panel (cross-refs, Greek/Hebrew interlinear with Strong's pop-ups, notes),
      full-text search, light/dark. Offline: fonts are bundled, no CDN.
- [ ] Versification map (see Known limitations)

## Known limitations

- **OT versification:** the Hebrew originals (STEPBible) use Masoretic verse
  numbering; the English translations use English numbering. These match for
  ~94% of OT verses but differ in Psalms (title counted as v1), Malachi 3/4,
  Joel, and scattered other passages — so the interlinear can be off by a verse
  there. A KJV↔Hebrew versification map (planned) will align them. The NT
  aligns fully.

## Install on a new machine

```bash
git clone https://github.com/ennels/scriptoria.git ~/Projects/scriptoria
cd ~/Projects/scriptoria
unzip ~/Downloads/scriptoria-db.zip      # prebuilt database -> scriptoria.db
uv sync
bash scripts/install-launcher.sh         # app-menu entry (optional)
uv run scriptoria
```

No prebuilt database? Build one instead (below).

## Build the database

```bash
uv sync
uv run python -m scriptoria.build
# add your own translations:
uv run python -m scriptoria.build --translations path/to/your.json --code WEB --name "World English Bible"
```

The build downloads public-domain / CC-BY sources into `data/` (cached). The
built `scriptoria.db` and `data/` are gitignored.

## Run it

```bash
uv run scriptoria          # serves 127.0.0.1:8701 and opens your browser
```

Everything runs locally against `scriptoria.db` — no network needed once built.

### Desktop launcher (Linux)

`scripts/install-launcher.sh` drops a "Scriptoria" entry into your app menu that
starts the server and opens the reader:

```bash
bash scripts/install-launcher.sh
```

## Data sources & licenses

- **Translations:** your own JSON (any of several common shapes), plus a
  public-domain KJV seed (scrollmapper).
- **Cross-references:** [OpenBible.info](https://www.openbible.info/labs/cross-references/) (CC BY).
- **Strong's lexicon:** [OpenScriptures](https://github.com/openscriptures/strongs) (public domain).
- **Greek/Hebrew originals:** [STEPBible](https://github.com/STEPBible/STEPBible-Data) TAHOT/TAGNT (CC BY 4.0).
