-- Scriptoria schema. One canonical verse spine; every dataset hangs off verse_id.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS book (
  id         INTEGER PRIMARY KEY,   -- 1..66 canonical position
  osis       TEXT UNIQUE NOT NULL,  -- "Gen", "Matt", ...
  name       TEXT NOT NULL,
  testament  TEXT NOT NULL,         -- OT / NT
  chapters   INTEGER NOT NULL
);

-- The canonical verse spine. osis like "John.3.16". Every other table joins on verse_id.
CREATE TABLE IF NOT EXISTS verse (
  id       INTEGER PRIMARY KEY,
  osis     TEXT UNIQUE NOT NULL,
  book_id  INTEGER NOT NULL REFERENCES book(id),
  chapter  INTEGER NOT NULL,
  verse    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS verse_bcv ON verse(book_id, chapter, verse);

CREATE TABLE IF NOT EXISTS translation (
  id        INTEGER PRIMARY KEY,
  code      TEXT UNIQUE NOT NULL,   -- "KJV", "ASV", ...
  name      TEXT NOT NULL,
  language  TEXT DEFAULT 'en',
  license   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS verse_text (
  translation_id INTEGER NOT NULL REFERENCES translation(id),
  verse_id       INTEGER NOT NULL REFERENCES verse(id),
  text           TEXT NOT NULL,
  PRIMARY KEY (translation_id, verse_id)
);

-- Full-text search over every translation's text (contentless FTS5, kept in sync by importer).
CREATE VIRTUAL TABLE IF NOT EXISTS verse_fts USING fts5(
  text, translation_id UNINDEXED, verse_id UNINDEXED, tokenize = 'porter unicode61'
);

-- OpenBible cross-references: from one verse to a passage (to_verse .. to_end), with a vote weight.
CREATE TABLE IF NOT EXISTS cross_ref (
  from_verse_id  INTEGER NOT NULL REFERENCES verse(id),
  to_verse_id    INTEGER NOT NULL REFERENCES verse(id),
  to_end_id      INTEGER REFERENCES verse(id),   -- end of a ranged target, else NULL
  votes          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS xref_from ON cross_ref(from_verse_id, votes DESC);

-- Strong's lexicon (Greek G####, Hebrew H####).
CREATE TABLE IF NOT EXISTS strongs (
  id          TEXT PRIMARY KEY,     -- "G26", "H430"
  language    TEXT NOT NULL,        -- greek / hebrew
  lemma       TEXT,                 -- original-script headword
  translit    TEXT,
  pronounce   TEXT,
  definition  TEXT,                 -- Strong's definition
  kjv_def     TEXT                  -- how the KJV renders it
);

-- STEPBible tagged originals: one row per original-language word.
CREATE TABLE IF NOT EXISTS original_word (
  verse_id   INTEGER NOT NULL REFERENCES verse(id),
  position   INTEGER NOT NULL,      -- word order within the verse
  language   TEXT NOT NULL,         -- greek / hebrew
  text       TEXT NOT NULL,         -- original-script word
  translit   TEXT,
  gloss      TEXT,                  -- English gloss
  strongs    TEXT,                  -- normalized Strong's id for lexicon link (e.g. G976)
  strongs_raw TEXT,                 -- full original tag (compounds, variants)
  morph      TEXT,                  -- morphology code
  lemma      TEXT,
  PRIMARY KEY (verse_id, position)
);

-- User's own highlights and notes, keyed to a verse (local, private).
CREATE TABLE IF NOT EXISTS note (
  id         INTEGER PRIMARY KEY,
  verse_id   INTEGER NOT NULL REFERENCES verse(id),
  color      TEXT DEFAULT '',       -- highlight color, '' = note only
  body       TEXT DEFAULT '',
  created    TEXT DEFAULT (datetime('now')),
  updated    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS note_verse ON note(verse_id);
