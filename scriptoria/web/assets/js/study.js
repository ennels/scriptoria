// The study panel: everything about the selected verse.
import { api, app, el, emit, persist, refLabel, stripCantillation, put } from './core.js';
import { renderNotesTab } from './notes.js';
import { renderWordStudy } from './wordstudy.js';

const TABS = [['xref', 'Cross-refs'], ['inter', 'Interlinear'], ['word', 'Word study'], ['notes', 'Notes']];

export class Study {
  constructor(root) {
    this.root = root;
    this.osis = null;
    this.pane = null;
    this.wordId = null;
    this.tabBtns = {};
    this.head = el('header', { class: 'study-head' });
    this.tabs = el('div', { class: 'tabs', attrs: { role: 'tablist', 'aria-label': 'Study' } },
      TABS.map(([k, label]) => (this.tabBtns[k] = el('button', { class: 'tab', id: `tab-${k}`, text: label,
        attrs: { role: 'tab', 'aria-selected': 'false', 'aria-controls': 'tabpanel' }, on: { click: () => this.setTab(k) } }))));
    this.tabs.addEventListener('keydown', (e) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      const keys = TABS.map(([k]) => k);
      const i = keys.indexOf(this.tab) + (e.key === 'ArrowRight' ? 1 : -1);
      this.setTab(keys[(i + keys.length) % keys.length]);
      this.tabBtns[this.tab].focus();
    });
    this.panel = el('div', { class: 'tabpanel', id: 'tabpanel', attrs: { role: 'tabpanel' } });
    put(root, this.head, this.tabs, this.panel);
    this.tab = app.settings.studyTab || 'xref';
    this.empty();
  }

  get translation() { return this.pane?.textTranslation() || 'KJV'; }

  empty() {
    this.osis = null;
    put(this.head, el('div', { class: 'study-ref' }, el('h2', { text: 'Study' })));
    this.tabs.hidden = true;
    put(this.panel, el('div', { class: 'empty' },
      el('p', { style: { marginTop: 0 }, text: 'Select a verse to see its cross-references, the Hebrew or Greek behind it, and your notes. Click any word in the interlinear for a full word study.' }),
      el('p', { class: 'muted', style: { fontFamily: 'var(--ui)', fontSize: '.85rem' } },
        el('span', { class: 'kbd', text: '/' }), ' search  ', el('span', { class: 'kbd', text: '[' }), ' ', el('span', { class: 'kbd', text: ']' }),
        ' chapters  ', el('span', { class: 'kbd', text: 'I' }), ' interlinear  ', el('span', { class: 'kbd', text: 'S' }), ' side by side')));
  }

  show(osis, pane, { quiet = false } = {}) {
    const same = osis === this.osis;
    this.osis = osis;
    this.pane = pane;
    this.tabs.hidden = false;
    const text = pane?.selectedText(osis) || '';
    put(this.head, 
      el('div', { class: 'study-ref' }, el('h2', { text: refLabel(osis) }),
        el('button', { class: 'iconbtn', text: '✕', title: 'Close study panel (P)', attrs: { 'aria-label': 'Close study panel' },
          on: { click: () => emit('toggle-study', false) } })),
      text ? el('div', { class: 'study-verse', text: /[֐-׿]/.test(text) ? stripCantillation(text) : text }) : null);
    if (quiet && same) return;
    if (quiet && this.tab === 'word') return;
    this.setTab(this.tab === 'word' && !this.wordId ? 'xref' : this.tab, true);
  }

  openWord(id, osis, pane) {
    this.wordId = id;
    if (osis !== this.osis) this.show(osis, pane, { quiet: true });
    this.setTab('word', true);
  }

  setTab(k, force = false) {
    if (!this.osis) return;
    if (k === this.tab && !force) return;
    this.tab = k;
    app.settings.studyTab = k === 'word' ? app.settings.studyTab : k;
    persist('studyTab');
    for (const [key, b] of Object.entries(this.tabBtns)) b.setAttribute('aria-selected', String(key === k));
    this.panel.setAttribute('aria-labelledby', `tab-${k}`);
    this.panel.scrollTop = 0;
    const token = (this.token = Symbol());
    const done = (p) => p?.catch?.((e) => { if (this.token === token) put(this.panel, el('p', { class: 'empty', text: `Couldn't load: ${e.message}` })); });
    if (k === 'xref') done(this.renderXrefs(token));
    else if (k === 'inter') done(this.renderInterlinear(token));
    else if (k === 'word') {
      if (!this.wordId) { put(this.panel, el('p', { class: 'empty', text: 'Click a Hebrew or Greek word (in the Interlinear tab, or in the reader with interlinear on) to study it.' })); return; }
      done(renderWordStudy(this.panel, this.wordId, { translation: this.translation, alive: () => this.token === token }));
    } else if (k === 'notes') {
      const osis = this.osis;
      done(renderNotesTab(this.panel, osis, { onChange: () => emit('annotations-changed', { osis }), alive: () => this.token === token }));
    }
  }

  async renderXrefs(token) {
    put(this.panel, el('p', { class: 'muted', text: 'Loading…' }));
    const d = await api(`/api/verse/${this.osis}/crossrefs`, { params: { translation: this.translation, limit: 60 } });
    if (this.token !== token) return;
    if (!d.crossrefs.length) { put(this.panel, el('p', { class: 'empty', text: 'No cross-references for this verse.' })); return; }
    put(this.panel, 
      el('p', { class: 'muted', style: { fontSize: '.8rem', margin: '0 0 .4rem' }, text: 'Ranked by how many readers linked them (OpenBible.info).' }),
      ...d.crossrefs.map((x) => el('div', { class: 'xref', attrs: { role: 'button', tabindex: '0' },
        on: { click: () => emit('navigate', { osis: x.osis }), keydown: (e) => { if (e.key === 'Enter') emit('navigate', { osis: x.osis }); } } },
        el('div', { class: 'xref-top' }, el('span', { class: 'xref-ref', text: x.ref }),
          el('button', { class: 'beside', text: 'Open beside', title: 'Open in the side-by-side pane',
            on: { click: (e) => { e.stopPropagation(); emit('navigate', { osis: x.osis, pane: 'other' }); } } })),
        x.text ? el('div', { class: 'xref-text', text: x.text }) : null)));
  }

  async renderInterlinear(token) {
    put(this.panel, el('p', { class: 'muted', text: 'Loading…' }));
    const d = await api(`/api/verse/${this.osis}/interlinear`);
    if (this.token !== token) return;
    const heb = d.language === 'hebrew';
    const show = (s) => (heb && !app.settings.display.cantillation ? stripCantillation(s || '') : s || '');
    const rows = d.words.map((w) => {
      const parse = w.parsing;
      const detail = parse?.parts?.map((p) => p.explanation).filter(Boolean).join(' + ');
      return el('div', { class: `word ${w.language}` },
        el('div', { class: 'orig', lang: heb ? 'hbo' : 'grc', text: show(w.display || w.text) }),
        el('div', { class: 'line1' },
          el('span', { class: 'gloss', text: w.gloss || '—' }),
          w.translit ? el('span', { class: 'translit', text: w.translit }) : null),
        el('div', { class: 'line1' },
          w.strongs ? el('button', { class: 'sbtn', text: w.dstrong && w.dstrong !== w.strongs ? w.dstrong : w.strongs, title: 'Open word study',
            on: { click: () => this.studyWord(w.dstrong || w.strongs) } }) : null,
          w.lemma ? el('span', { class: 'lemma' }, 'from ', el('span', { class: 'orig-text', lang: heb ? 'hbo' : 'grc', text: show(w.lemma) }),
            w.lemma_gloss ? ` “${w.lemma_gloss}”` : '') : null),
        parse ? el('div', { class: 'parse', title: detail || '' }, el('b', { text: parse.label }),
          /^Verb/.test(parse.parts?.at(-1)?.label || '') && parse.parts.at(-1).example ? ` — like “${parse.parts.at(-1).example}”` : '') : null,
        w.variant ? el('div', { class: 'variant' }, el('span', { class: 'badge', text: w.variant.label }), ' ', w.variant.detail) : null);
    });
    put(this.panel, d.note ? el('div', { class: 'note-banner', text: d.note }) : null,
      ...(rows.length ? rows : []));
  }

  studyWord(id) { this.wordId = id; this.setTab('word', true); }
}
