-- Scriptoria content database (schema v2). Scripture, originals, lexicons.
-- Everything here can be rebuilt from public sources; user data lives in user.db.
-- One canonical verse spine (English/KJV numbering); every dataset joins on verse_id.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
  key    TEXT PRIMARY KEY,
  value  TEXT
);

CREATE TABLE IF NOT EXISTS book (
  id         INTEGER PRIMARY KEY,   -- 1..66 canonical position
  osis       TEXT UNIQUE NOT NULL,  -- "Gen", "Matt", ...
  name       TEXT NOT NULL,
  testament  TEXT NOT NULL,         -- OT / NT
  chapters   INTEGER NOT NULL
);

-- verse = 0 is a Psalm superscription (title), which English Bibles leave unnumbered.
CREATE TABLE IF NOT EXISTS verse (
  id       INTEGER PRIMARY KEY,
  osis     TEXT UNIQUE NOT NULL,    -- "John.3.16"
  book_id  INTEGER NOT NULL REFERENCES book(id),
  chapter  INTEGER NOT NULL,
  verse    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS verse_bcv ON verse(book_id, chapter, verse);

CREATE TABLE IF NOT EXISTS translation (
  id            INTEGER PRIMARY KEY,
  code          TEXT UNIQUE NOT NULL,   -- "KJV", "BSB", "ORIG", "RVR-ES" ...
  name          TEXT NOT NULL,
  language      TEXT NOT NULL DEFAULT 'en',   -- ISO code; 'hbo+grc' for the original-language texts
  language_name TEXT NOT NULL DEFAULT 'English',
  direction     TEXT NOT NULL DEFAULT 'ltr',  -- ltr | rtl | mixed (Hebrew OT + Greek NT)
  kind          TEXT NOT NULL DEFAULT 'text', -- text | original
  fts           TEXT NOT NULL DEFAULT 'en',   -- which search index: en | intl | cjk
  source        TEXT NOT NULL DEFAULT '',     -- where it came from (e.g. thiagobodruk:en_bsb)
  license       TEXT NOT NULL DEFAULT '',
  verses        INTEGER NOT NULL DEFAULT 0,
  installed_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS verse_text (
  id              INTEGER PRIMARY KEY,      -- rowid shared with the FTS indexes
  translation_id  INTEGER NOT NULL REFERENCES translation(id),
  verse_id        INTEGER NOT NULL REFERENCES verse(id),
  text            TEXT NOT NULL,
  UNIQUE (translation_id, verse_id)
);
CREATE INDEX IF NOT EXISTS verse_text_verse ON verse_text(verse_id);

-- Search indexes over verse_text (external content: text is stored once).
-- English gets stemming; other alphabetic scripts get accent folding;
-- Chinese/Japanese/Thai (no spaces between words) get trigram matching.
CREATE VIRTUAL TABLE IF NOT EXISTS fts_en USING fts5(
  text, content='verse_text', content_rowid='id', tokenize='porter unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS fts_intl USING fts5(
  text, content='verse_text', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE IF NOT EXISTS fts_cjk USING fts5(
  text, content='verse_text', content_rowid='id', tokenize='trigram');
-- Hebrew/Greek reading texts: indexed without accents, breathings or vowel points
-- (stored folded, rowid = verse_text.id), so 'λογος' finds λόγος and 'בראשית' finds בְּרֵאשִׁית.
CREATE VIRTUAL TABLE IF NOT EXISTS fts_orig USING fts5(text, tokenize='unicode61');

-- OpenBible cross-references: one verse -> a verse or range, with a vote weight.
CREATE TABLE IF NOT EXISTS cross_ref (
  from_verse_id  INTEGER NOT NULL REFERENCES verse(id),
  to_verse_id    INTEGER NOT NULL REFERENCES verse(id),
  to_end_id      INTEGER REFERENCES verse(id),
  votes          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS xref_from ON cross_ref(from_verse_id, votes DESC);

-- OpenScriptures Strong's dictionary — kept for the KJV-usage and derivation notes.
CREATE TABLE IF NOT EXISTS strongs (
  id          TEXT PRIMARY KEY,     -- "G26", "H430"
  language    TEXT NOT NULL,
  lemma       TEXT,
  translit    TEXT,
  pronounce   TEXT,
  definition  TEXT,
  kjv_def     TEXT,
  derivation  TEXT
);

-- Tyndale House brief lexicons (TBESG/TBESH via STEPBible), keyed by disambiguated
-- Strong's (dStrong): H7225G and H7225H are distinct senses of רֵאשִׁית.
CREATE TABLE IF NOT EXISTS lexicon (
  dstrong     TEXT PRIMARY KEY,     -- "H7225G", "G25"
  strongs     TEXT NOT NULL,        -- base number "H7225"
  language    TEXT NOT NULL,        -- greek / hebrew
  lemma       TEXT,
  lemma_norm  TEXT,                 -- accents/points removed, for search
  translit    TEXT,
  translit_norm TEXT,               -- folded transliteration, for search
  pos         TEXT,                 -- "N-F", "V", ...
  gloss       TEXT,
  definition  TEXT,                 -- sanitized HTML (b, i, br, scripture links)
  relation    TEXT                  -- e.g. "a Meaning of H7225G"
);
CREATE INDEX IF NOT EXISTS lexicon_strongs ON lexicon(strongs);
CREATE INDEX IF NOT EXISTS lexicon_norm ON lexicon(lemma_norm);
CREATE INDEX IF NOT EXISTS lexicon_translit ON lexicon(translit_norm);

-- STEPBible morphology code expansions (TEGMC/TEHMC).
CREATE TABLE IF NOT EXISTS morph_code (
  code         TEXT PRIMARY KEY,    -- "V-AAI-3S", "HVqp3ms", "HR"
  language     TEXT NOT NULL,
  label        TEXT,                -- "Verb Aorist Active Indicative 3rd Singular"
  fields       TEXT,                -- JSON {"Function": "Verb", "Tense": "Aorist", ...}
  explanation  TEXT,
  example      TEXT
);

-- STEPBible tagged originals: one row per Hebrew/Greek word, placed in its English verse.
CREATE TABLE IF NOT EXISTS original_word (
  id          INTEGER PRIMARY KEY,
  verse_id    INTEGER NOT NULL REFERENCES verse(id),
  position    INTEGER NOT NULL,     -- reading order within the English verse
  language    TEXT NOT NULL,        -- greek / hebrew
  text        TEXT NOT NULL,        -- original script (Hebrew keeps / between morphemes)
  norm        TEXT,                 -- accents/points removed, lowercase — for searching forms
  translit    TEXT,
  gloss       TEXT,                 -- English gloss in context
  meaning     TEXT,                 -- context-specific sense, when given
  strongs     TEXT,                 -- base Strong's of the content word, "G25" / "H1254"
  dstrong     TEXT,                 -- disambiguated, "H1254A"
  strongs_raw TEXT,                 -- full tag incl. prefixes, "H9003/{H7225G}"
  morph       TEXT,                 -- "V-AAI-3S" / "HR/Ncfsa"
  lemma       TEXT,                 -- dictionary form
  text_type   TEXT,                 -- manuscript tag: L, Q(K), R, X (Heb) / NKO, K, N(k)O ... (Grk)
  editions    TEXT,                 -- Greek editions containing the word, "NA28+TR+Byz..."
  variants    TEXT,                 -- meaning-affecting variant notes
  alt_ref     TEXT,                 -- the other tradition's number when it differs: "heb:3.19"
  UNIQUE (verse_id, position)
);
CREATE INDEX IF NOT EXISTS ow_strongs ON original_word(strongs);
CREATE INDEX IF NOT EXISTS ow_dstrong ON original_word(dstrong);
CREATE INDEX IF NOT EXISTS ow_norm ON original_word(norm);
