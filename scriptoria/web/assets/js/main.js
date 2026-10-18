// Scriptoria front end: boot, layout, and the wiring between panes, study panel and views.
import { $, api, app, el, emit, flushSettings, mergeSettings, on, persist, put, setProfileId, storedProfileId, toast } from './core.js';
import { applyScale, applyTheme, openDisplay } from './display.js';
import { openLibrary } from './library.js';
import { renderNotesView } from './notes.js';
import { Pane } from './pane.js';
import { closePopover } from './popover.js';
import { avatar, openProfileMenu } from './profiles.js';
import { renderSearchView } from './search.js';
import { Study } from './study.js';

const ws = $('#workspace');
const viewHost = $('#view');
const appEl = $('#app');
let panes = [];
let active = null;
let study = null;
let viewOpen = false;

// ------------------------------------------------------------------ boot
async function boot() {
  let meta;
  try { meta = await api('/api/meta'); } catch (e) { setup(`Scriptoria’s server isn’t responding (${e.message}).`); return; }
  app.meta = meta;
  if (!meta.ready) { setup(meta.message); return; }
  const stored = storedProfileId();
  if (stored) setProfileId(stored);
  await loadProfiles();
  const [books, saved] = await Promise.all([api('/api/books'), api('/api/settings')]);
  app.books = books;
  app.book = Object.fromEntries(books.map((b) => [b.osis, b]));
  app.settings = mergeSettings(saved);
  await loadTranslations();
  applyTheme(app.settings.theme);
  applyScale();
  study = new Study($('#study'));
  panes = [new Pane(0), new Pane(1)];
  layout();
  setActive(panes[0]);
  await panes[0].load();
  if (app.settings.split) await (app.settings.linked ? followLeft() : panes[1].load());
  wire();
}

function setup(message) {
  put(appEl, el('div', { class: 'setup' },
    el('h1', { text: 'Almost ready' }),
    el('p', { text: message }),
    el('p', {}, 'Your notes and profiles are kept separately, so updating the scripture database never touches them.')));
}

async function loadProfiles() {
  const r = await api('/api/profiles');
  app.profiles = r.profiles;
  app.colors = r.colors;
  app.profile = r.profiles.find((p) => p.id === r.current) || r.profiles[0];
  setProfileId(app.profile.id);
  const who = $('#btnWho');
  put(who, avatar(app.profile), el('span', { text: app.profile.name }));
  who.title = `Reading as ${app.profile.name} — switch or add a profile`;
}

async function loadTranslations() {
  app.translations = await api('/api/translations');
  app.tmap = Object.fromEntries(app.translations.map((t) => [t.code, t]));
  const fallback = app.tmap.KJV ? 'KJV' : app.translations[0]?.code;
  for (const p of app.settings.panes) {
    p.versions = p.versions.filter((c) => app.tmap[c]);
    if (!p.versions.length) p.versions = [fallback];
  }
  const st = app.settings.search;
  st.translations = st.translations.filter((c) => c === '*' || app.tmap[c]);
  if (!st.translations.length) st.translations = [fallback];
}

// ------------------------------------------------------------------ layout
function layout() {
  const split = !!app.settings.split;
  ws.classList.toggle('split', split);
  put(ws, panes[0].root, ...(split ? [panes[1].root] : []));
  $('#btnSplit').setAttribute('aria-pressed', String(split));
  appEl.classList.toggle('study-closed', !app.settings.studyOpen);
  $('#btnStudy').setAttribute('aria-pressed', String(!!app.settings.studyOpen));
}

function setActive(p) {
  active = p;
  panes.forEach((x) => x.root.classList.toggle('active', x === p));
}

async function setSplit(v) {
  app.settings.split = v;
  persist('split');
  layout();
  if (v) {
    if (app.settings.linked) await followLeft(); else await panes[1].load();
    setActive(panes[1]);
  } else setActive(panes[0]);
}

async function followLeft() {
  const s0 = panes[0].state;
  await panes[1].goto(s0.book, s0.chapter, { quiet: true });
  const a = panes[0].topAnchor();
  if (a) panes[1].syncTo(a.osis, a.delta);
}

function setLinked(v) {
  app.settings.linked = v;
  persist('linked');
  panes[1].syncChrome();
  if (v && app.settings.split) followLeft();
}

function sameChapter(a, b) { return a.state.book === b.state.book && a.state.chapter === b.state.chapter; }

// ------------------------------------------------------------------ views (search, notes)
function openView(render) {
  closePopover();
  viewOpen = true;
  ws.hidden = true;
  viewHost.hidden = false;
  render(viewHost);
}
function closeView() {
  if (!viewOpen) return;
  viewOpen = false;
  viewHost.hidden = true;
  put(viewHost);
  ws.hidden = false;
  active?.body.focus({ preventScroll: true });
}
const openSearch = (init) => openView((h) => renderSearchView(h, init, { onClose: closeView }));
const openNotes = () => openView((h) => renderNotesView(h, { onClose: closeView }));

// ------------------------------------------------------------------ wiring
function wire() {
  $('#btnSplit').addEventListener('click', () => setSplit(!app.settings.split));
  $('#btnStudy').addEventListener('click', () => emit('toggle-study'));
  $('#btnLibrary').addEventListener('click', () => openLibrary());
  $('#btnNotes').addEventListener('click', () => openNotes());
  $('#btnDisplay').addEventListener('click', (e) => openDisplay(e.currentTarget));
  $('#btnWho').addEventListener('click', (e) => openProfileMenu(e.currentTarget));

  $('#omnibox').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#omni');
    const q = input.value.trim();
    if (!q) return;
    try {
      const r = await api('/api/resolve', { params: { q } });
      if (r.found) {
        input.value = '';
        input.blur();
        emit('navigate', { osis: r.osis, book: r.book, chapter: r.chapter });
        return;
      }
    } catch (err) { /* fall through to search */ }
    input.value = '';
    openSearch({ q, mode: 'auto' });
  });

  on('pane-focus', setActive);
  on('toggle-split', (v) => setSplit(v ?? !app.settings.split));
  on('toggle-link', () => setLinked(!app.settings.linked));
  on('toggle-study', (v) => { app.settings.studyOpen = v ?? !app.settings.studyOpen; persist('studyOpen'); layout(); });

  on('pane-moved', (p) => {
    if (!app.settings.split || !app.settings.linked) return;
    if (p.i === 0) followLeft();
    else if (!sameChapter(panes[0], panes[1])) { setLinked(false); toast('Panes unlinked — each now moves on its own'); }
  });
  on('pane-scroll', ({ pane, osis, delta }) => {
    if (!app.settings.split || !app.settings.linked) return;
    const other = panes[1 - pane.i];
    if (sameChapter(pane, other)) other.syncTo(osis, delta);
  });

  on('select-verse', ({ osis, pane, quiet }) => { setActive(pane); study.show(osis, pane, { quiet }); });
  on('open-word', ({ id, osis, pane }) => {
    if (!app.settings.studyOpen) emit('toggle-study', true);
    study.openWord(id, osis, pane);
  });

  on('navigate', async ({ osis, book, chapter, pane }) => {
    closeView();
    let target = active || panes[0];
    if (pane === 'other') {
      if (app.settings.linked) setLinked(false);
      if (!app.settings.split) { app.settings.split = true; persist('split'); layout(); }
      target = panes[1];
    } else if (pane instanceof Pane) target = pane;
    if (osis) {
      const [b, c] = osis.split('.');
      await target.goto(b, +c, { verse: osis, select: true });
    } else if (book) await target.goto(book, chapter || 1);
    setActive(target);
  });

  on('annotations-changed', ({ osis }) => {
    const [b, c] = osis.split('.');
    panes.forEach((p) => { if (p.data && p.state.book === b && p.state.chapter === +c) p.refreshAnnotations(); });
    loadProfiles();
  });
  on('display-changed', () => {
    panes.forEach((p) => p.data && p.render());
    if (study.osis && study.tab !== 'notes') study.setTab(study.tab, true);
  });
  on('translations-changed', async () => {
    await loadTranslations();
    panes.forEach((p) => p.data && p.syncChrome());
  });
  on('open-library', () => openLibrary());
  on('search', (init) => openSearch(init));
  on('profiles-changed', () => loadProfiles());
  on('switch-profile', async (id) => {
    await flushSettings();
    setProfileId(id);
    await loadProfiles();
    app.settings = mergeSettings(await api('/api/settings'));
    await loadTranslations();
    applyTheme(app.settings.theme);
    applyScale();
    closeView();
    panes.forEach((p) => { p.sel = null; p.wordSel = null; });
    study.empty();
    layout();
    await panes[0].load();
    if (app.settings.split) await panes[1].load();
    toast(`Reading as ${app.profile.name}`);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (viewOpen && !document.querySelector('dialog[open]')) { closeView(); e.preventDefault(); } return; }
    if (e.target.closest('input, textarea, select, [contenteditable="true"]') || e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.querySelector('dialog[open]')) return;
    const k = e.key.toLowerCase();
    if (e.key === '/') { e.preventDefault(); $('#omni').focus(); }
    else if (viewOpen) return;
    else if (e.key === '[') active?.step(-1);
    else if (e.key === ']') active?.step(1);
    else if (k === 'i') active?.toggleInterlinear();
    else if (k === 's') setSplit(!app.settings.split);
    else if (k === 'p') emit('toggle-study');
  });
}

boot().catch((e) => {
  console.error(e);
  setup(`Something went wrong while starting: ${e.message}`);
});
