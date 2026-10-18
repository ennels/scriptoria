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
- [ ] FastAPI backend
- [ ] Browser UI (reader, parallel view, search, cross-refs, interlinear, notes)
- [ ] Versification map (see Known limitations)

## Known limitations

- **OT versification:** the Hebrew originals (STEPBible) use Masoretic verse
  numbering; the English translations use English numbering. These match for
  ~94% of OT verses but differ in Psalms (title counted as v1), Malachi 3/4,
  Joel, and scattered other passages — so the interlinear can be off by a verse
  there. A KJV↔Hebrew versification map (planned) will align them. The NT
  aligns fully.

## Build the database

```bash
uv sync
uv run python -m scriptoria.build
# add your own translations:
uv run python -m scriptoria.build --translations path/to/your.json --code WEB --name "World English Bible"
```

The build downloads public-domain / CC-BY sources into `data/` (cached). The
built `scriptoria.db` and `data/` are gitignored.

## Data sources & licenses

- **Translations:** your own JSON (any of several common shapes), plus a
  public-domain KJV seed (scrollmapper).
- **Cross-references:** [OpenBible.info](https://www.openbible.info/labs/cross-references/) (CC BY).
- **Strong's lexicon:** [OpenScriptures](https://github.com/openscriptures/strongs) (public domain).
- **Greek/Hebrew originals:** [STEPBible](https://github.com/STEPBible/STEPBible-Data) TAHOT/TAGNT (CC BY 4.0).
