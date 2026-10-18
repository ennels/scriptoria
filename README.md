# Scriptoria

An offline interlinear study Bible for Linux (and anything else with Python). It runs
locally in your browser off a SQLite database — no account, no internet once installed.

- **Read** any installed translation as flowing text or verse-by-verse, or several side by
  side in aligned columns — including the **Hebrew and Greek** themselves (with the
  Nestle-Aland or the KJV's Textus Receptus New Testament).
- **Side-by-side panes**: two independent passages at once (Isaiah 53 beside Acts 8), or
  link the panes to follow the same chapter and scroll together.
- **Interlinear**: switch any pane to word-by-word Hebrew/Greek with transliteration,
  English gloss, Strong's number and parsing. Psalm titles appear as headings.
- **Every verse aligned**: all 31,102 KJV verses carry their original words. Where Hebrew
  or other editions number a verse differently (Malachi 4 = Hebrew 3:19–24, Joel 2:28 =
  Hebrew 3:1…), the study panel says so instead of guessing.
- **Plain-English parsing** (“Verb · Qal (Simple, Active) Perfect · Third Singular
  Masculine”) and **manuscript notes**: Qere/Ketiv readings, words found only in the
  Textus Receptus or only in Nestle-Aland (e.g. 1 John 5:7).
- **Word study**: Tyndale House lexicon entry (Abbott-Smith / BDB-based), every sense,
  how often and where it occurs (chart by book), every inflected form, how it's glossed,
  and a concordance of every verse.
- **Search**: all words / exact phrase / any word / advanced syntax, across any set of
  translations, limited to a testament, book or range of books, with hits per book. Search
  the Hebrew and Greek by Strong's number (`G26`), dictionary word (`ἀγάπη` = every form),
  exact form (`ἀγάπην`) or transliteration (`agape`, `reshit`) — accents and vowel points
  optional. Type a reference (`jn 3:16`, `1 cor 13`, `Ps 23:1-4`) to jump straight there.
- **Translation library**: 122 versions in 67 languages; install or remove by language
  (right-to-left scripts handled).
- **Profiles** for everyone in the house (no passwords): each has their own highlights,
  tagged notes (several per verse), reading place and settings. Browse, search and export
  notes as Markdown or JSON.
- Cross-references (OpenBible.info, ~345,000 links ranked by votes), light and dark themes,
  adjustable text size, keyboard shortcuts.

## Install on a new machine

Needs [uv](https://docs.astral.sh/uv/). If `uv` isn't found:
`curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env`

```bash
git clone https://github.com/ennels/scriptoria.git ~/Projects/scriptoria
cd ~/Projects/scriptoria
unzip ~/Downloads/scriptoria-db.zip      # prebuilt database -> scriptoria.db
uv sync
bash scripts/install-launcher.sh         # app-menu entry + desktop icon (optional)
uv run scriptoria                        # opens http://127.0.0.1:8701
```

No prebuilt database? Build one (below).

## Updating from the first version

The first release kept notes inside `scriptoria.db`. This version keeps them in a separate
user database and moves old notes across automatically the first time it starts — so start
it once **before** replacing the database:

```bash
cd ~/Projects/scriptoria && git pull && uv sync
uv run scriptoria          # moves any old notes, then shows "database is from an older version"
# Ctrl+C, then:
unzip -o ~/Downloads/scriptoria-db.zip
uv run scriptoria
```

## Where your things are kept

| What | Where |
|---|---|
| Scripture, lexicons, originals (rebuildable) | `scriptoria.db` in the project folder |
| Profiles, notes, highlights, settings | Linux `~/.local/share/scriptoria/user.db` · macOS `~/Library/Application Support/scriptoria/user.db` |

Back up `user.db` to keep your notes. Paths can be overridden with `SCRIPTORIA_DB` and
`SCRIPTORIA_USER_DB`.

The server listens only on this computer (127.0.0.1) and refuses requests from other
websites. To read from another device on your home network, start it with the address
and names you'll use — there are no passwords, so only do this on a network you trust:

```bash
SCRIPTORIA_HOST=0.0.0.0 SCRIPTORIA_ALLOWED_HOSTS="mybox.local,192.168.1.20" uv run scriptoria
```

## Using it

| Key | Does |
|---|---|
| `/` | search, or type a reference to go there |
| `[` `]` | previous / next chapter (in the active pane) |
| `I` | interlinear on/off |
| `S` | side-by-side panes |
| `P` | study panel |
| `Esc` | back to reading |

Click a verse for its cross-references, interlinear, word study and notes. Click any
Hebrew/Greek word for a word study. **Aa** sets text size, layout, which interlinear lines
show, Hebrew cantillation marks, cross-reference margin marks and theme.

Advanced search uses SQLite FTS5 syntax: `faith AND works`, `grace NOT law`,
`"the word of the lord"`, `NEAR(faith works, 5)`, `believ*`.

## Translations

Install more from **Library** in the app. Installs come from a local copy of the
[thiagobodruk/bible](https://github.com/thiagobodruk/bible) zip if one is found (set
`SCRIPTORIA_BIBLES`, or put `bible.zip` in `data/` or `~/Downloads/`), otherwise each
translation downloads once (~4 MB). Some versions in that collection are copyrighted
(NIV, ESV, NASB…); they're for your own study — don't redistribute them.

## Build the database

```bash
uv run python -m scriptoria.build --bibles ~/Downloads/bible.zip               # KJV + 9 English versions
uv run python -m scriptoria.build --bibles ~/Downloads/bible.zip --versions en  # every English version
uv run python -m scriptoria.build --versions BSB,RVR1960,LSG                     # downloads what's needed
```

Sources are downloaded once into `data/`. A full build takes about 30 seconds. Rebuilding
never touches notes.

## Development

```bash
uv sync --group dev
uv run pytest            # 57 tests: parsing, sanitizing, migrations, API, hardening
```

```
scriptoria/
  api/            FastAPI routers: reading, study (interlinear, word study), search, library, user
  importers/      STEPBible originals, lexicons, morphology, translations, cross-refs, Strong's
  build.py        downloads sources and builds scriptoria.db
  userdb.py       profiles/notes database + migrations
  references.py   "jn 3:16" -> John.3.16
  web/            index.html, styles.css, js/ (ES modules, no build step), bundled fonts
scripts/          launcher installer, catalog generator
tests/
```

## Data sources & licenses

- Hebrew & Greek tagged text, Tyndale brief lexicons, morphology expansions:
  [STEPBible.org](https://github.com/STEPBible/STEPBible-Data) — TAHOT, TAGNT, TBESH, TBESG,
  TEHMC, TEGMC (CC BY 4.0, Tyndale House Cambridge). Data is downloaded from STEPBible at
  build time, as they request, not redistributed here.
- Strong's dictionary: [OpenScriptures](https://github.com/openscriptures/strongs) (public domain).
- Cross-references: [OpenBible.info](https://www.openbible.info/labs/cross-references/) (CC BY).
- KJV: [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases) (public domain).
- Translation library: [thiagobodruk/bible](https://github.com/thiagobodruk/bible) (MIT code; each text has its own terms).
- Fonts (bundled, SIL Open Font License): Spectral, Public Sans, Gentium Book Plus, Noto Serif Hebrew.

## Known limitations

- Verse numbering follows the KJV. Translations that number a few verses differently
  (e.g. 3 John 1:15 in modern versions) show those verses, with a note that the Hebrew/Greek
  words sit under the neighbouring KJV verse.
- Lexicon definitions are brief-lexicon entries (Abbott-Smith for Greek, BDB-based for
  Hebrew), not full BDAG/HALOT.
