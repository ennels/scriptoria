// A reading pane: its own passage, translations and interlinear toggle.
import { api, app, bookName, dirFor, el, emit, persist, say, stripCantillation, toast, variantNote, put } from './core.js';
import { openPicker } from './picker.js';

export class Pane {
  constructor(index) {
    this.i = index;
    this.data = null;
    this.ann = { highlights: {}, notes: {} };
    this.sel = null;
    this.wordSel = null;
    this.syncing = false;
    this.build();
  }

  get state() { return app.settings.panes[this.i]; }

  // ------------------------------------------------------------------ chrome
  build() {
    this.bookSel = el('select', { class: 'select book', attrs: { 'aria-label': 'Book' },
      on: { change: () => this.goto(this.bookSel.value, 1) } });
    this.chapSel = el('select', { class: 'select', attrs: { 'aria-label': 'Chapter' },
      on: { change: () => this.goto(this.state.book, +this.chapSel.value) } });
    this.prevBtn = el('button', { class: 'iconbtn', text: '‹', title: 'Previous chapter ( [ )', attrs: { 'aria-label': 'Previous chapter' },
      on: { click: () => this.step(-1) } });
    this.nextBtn = el('button', { class: 'iconbtn', text: '›', title: 'Next chapter ( ] )', attrs: { 'aria-label': 'Next chapter' },
      on: { click: () => this.step(1) } });
    this.chips = el('div', { class: 'chips' });
    this.interBtn = el('button', { class: 'iconbtn', text: 'αβ', title: 'Word-by-word interlinear (I)',
      attrs: { 'aria-label': 'Interlinear', 'aria-pressed': 'false' }, on: { click: () => this.toggleInterlinear() } });
    const extra = [];
    if (this.i === 1) {
      this.linkBtn = el('button', { class: 'iconbtn', text: '⛓', title: 'Follow the left pane (same chapter, scroll together)',
        attrs: { 'aria-label': 'Link to left pane', 'aria-pressed': String(!!app.settings.linked) },
        on: { click: () => emit('toggle-link') } });
      extra.push(this.linkBtn, el('button', { class: 'iconbtn', text: '✕', title: 'Close this pane',
        attrs: { 'aria-label': 'Close side-by-side pane' }, on: { click: () => emit('toggle-split', false) } }));
    }
    this.bar = el('div', { class: 'pane-bar' }, this.prevBtn, this.bookSel, this.chapSel, this.nextBtn, this.chips,
      el('span', { class: 'gap' }), this.interBtn, ...extra);
    this.page = el('article', { class: 'page' });
    this.body = el('div', { class: 'pane-body', attrs: { tabindex: '-1' } }, this.page);
    this.root = el('section', { class: 'pane', dataset: { pane: this.i }, attrs: { 'aria-label': this.i ? 'Right pane' : 'Left pane' },
      on: { pointerdown: () => emit('pane-focus', this), focusin: () => emit('pane-focus', this) } }, this.bar, this.body);

    this.body.addEventListener('scroll', () => {
      if (this.syncing) return;
      cancelAnimationFrame(this.raf);
      this.raf = requestAnimationFrame(() => { const a = this.topAnchor(); if (a) emit('pane-scroll', { pane: this, ...a }); });
    }, { passive: true });

    this.fillBooks();
  }

  fillBooks() {
    const groups = { OT: el('optgroup', { label: 'Old Testament' }), NT: el('optgroup', { label: 'New Testament' }) };
    for (const b of app.books) groups[b.testament].append(el('option', { value: b.osis, text: b.name }));
    put(this.bookSel, groups.OT, groups.NT);
  }

  syncChrome() {
    const s = this.state, b = app.book[s.book];
    this.bookSel.value = s.book;
    put(this.chapSel, ...Array.from({ length: b.chapters }, (_, k) =>
      el('option', { value: k + 1, text: `${k + 1}` })));
    this.chapSel.value = String(s.chapter);
    this.prevBtn.disabled = !this.data?.prev;
    this.nextBtn.disabled = !this.data?.next;
    this.interBtn.setAttribute('aria-pressed', String(!!s.interlinear));
    if (this.linkBtn) this.linkBtn.setAttribute('aria-pressed', String(!!app.settings.linked));
    put(this.chips, 
      ...s.versions.map((code) => {
        const t = app.tmap[code];
        return el('span', { class: 'chip', title: t?.name || code }, code,
          s.versions.length > 1 ? el('button', { text: '×', title: `Remove ${code}`, attrs: { 'aria-label': `Remove ${code}` },
            on: { click: () => this.setVersions(s.versions.filter((c) => c !== code)) } }) : null);
      }),
      el('button', { class: 'chip add', text: '+ Add', title: 'Add a translation or the Hebrew/Greek text',
        attrs: { 'aria-haspopup': 'dialog' }, on: { click: (e) => this.openPicker(e.currentTarget) } }));
  }

  openPicker(anchor) {
    openPicker(anchor, () => this.state.versions, (code) => {
      const v = this.state.versions;
      if (v.includes(code)) { if (v.length > 1) this.setVersions(v.filter((c) => c !== code)); }
      else this.setVersions([...v, code]);
    });
  }

  setVersions(v) {
    this.state.versions = v;
    persist('panes');
    this.load({ keepScroll: true });
  }

  toggleInterlinear() {
    this.state.interlinear = !this.state.interlinear;
    persist('panes');
    this.load({ keepScroll: true });
  }

  // ------------------------------------------------------------------ navigation
  async goto(book, chapter, { verse = null, select = false, quiet = false } = {}) {
    Object.assign(this.state, { book, chapter });
    persist('panes');
    await this.load({ scrollTo: verse });
    if (verse && select) this.select(verse);
    if (!quiet) emit('pane-moved', this);
  }

  step(dir) {
    const n = dir < 0 ? this.data?.prev : this.data?.next;
    if (n) this.goto(n.book, n.chapter);
  }

  async load({ scrollTo = null, keepScroll = false } = {}) {
    const s = this.state;
    const seq = (this.seq = (this.seq || 0) + 1);       // only the latest request may render
    const anchor = keepScroll ? this.topAnchor() : null;
    this.page.classList.add('loading');
    try {
      const [data, ann] = await Promise.all([
        api('/api/chapter', { params: { book: s.book, chapter: s.chapter, translations: s.versions.join(','), words: s.interlinear ? 1 : '' } }),
        api('/api/annotations', { params: { book: s.book, chapter: s.chapter } }),
      ]);
      if (seq !== this.seq) return;
      this.data = data;
      this.ann = ann;
      const got = data.translations.map((t) => t.code);
      if (got.join() !== s.versions.join()) { s.versions = got; persist('panes'); }
    } catch (e) {
      if (seq !== this.seq) return;
      this.page.classList.remove('loading');
      toast(`Couldn't open ${bookName(s.book)} ${s.chapter}: ${e.message}`, 'error');
      return;
    }
    this.render();
    this.syncChrome();
    if (scrollTo) this.scrollToVerse(scrollTo);
    else if (anchor) this.syncTo(anchor.osis, anchor.delta, true);
    else this.body.scrollTop = 0;
    say(`${this.data.book_name} ${this.data.chapter}`);
    emit('pane-loaded', this);
  }

  async refreshAnnotations() {
    const s = this.state;
    const seq = this.seq;
    const anchor = this.topAnchor();
    const ann = await api('/api/annotations', { params: { book: s.book, chapter: s.chapter } });
    if (seq !== this.seq || !this.data) return;          // a newer chapter load took over
    this.ann = ann;
    this.render();
    if (anchor) this.syncTo(anchor.osis, anchor.delta, true);
  }

  // ------------------------------------------------------------------ rendering
  render() {
    const d = this.data;
    const disp = app.settings.display;
    this.page.className = 'page' + (d.translations.length > 1 && !this.state.interlinear ? ' wide' : '');
    for (const k of ['translit', 'gloss', 'strongs', 'morph']) this.page.classList.toggle(`hide-${k}`, !disp[k]);
    const head = el('header', { class: 'chapter-head' },
      el('div', { class: 'chapter-num', text: d.chapter, attrs: { 'aria-hidden': 'true' } }),
      el('h1', { class: 'chapter-book', style: { margin: 0, fontWeight: 400 } },
        el('span', { class: 'sr', text: `${d.book_name} chapter ${d.chapter}` }),
        el('span', { attrs: { 'aria-hidden': 'true' }, text: d.book_name }),
        el('small', { text: d.translations.map((t) => t.name).join(' · ') })));
    const title = d.verses.find((v) => v.superscription);
    const verses = d.verses.filter((v) => !v.superscription);
    let body;
    if (this.state.interlinear) body = this.renderInterlinear(verses);
    else if (d.translations.length > 1) body = this.renderGrid(verses);
    else body = this.renderProse(verses, disp.layout === 'lines');
    const nav = el('nav', { class: 'chapter-nav', attrs: { 'aria-label': 'Chapter navigation' } },
      d.prev ? el('button', { text: `‹ ${d.prev.label}`, on: { click: () => this.step(-1) } }) : el('span'),
      d.next ? el('button', { text: `${d.next.label} ›`, on: { click: () => this.step(1) } }) : el('span'));
    put(this.page, head, title ? this.renderTitle(title) : null, body, nav);
    this.page.classList.remove('loading');
    if (this.sel) this.markSelected();
  }

  heb(text) { return app.settings.display.cantillation ? text : stripCantillation(text); }

  marks(v) {
    const n = this.ann.notes[v.osis];
    const x = v.has_xrefs && app.settings.display.xrefMarks;
    if (!x && !n) return null;
    return el('span', { class: 'marks', attrs: { 'aria-hidden': 'true' } },
      x ? el('span', { class: 'mark-x', text: '✦', title: 'Has cross-references' }) : null,
      n ? el('span', { class: 'mark-n', text: '¶', title: n > 1 ? `${n} notes` : 'Your note' }) : null);
  }

  hl(osis) { const c = this.ann.highlights[osis]; return c ? ` hl-${c}` : ''; }

  renderTitle(v) {
    return el('div', { class: 'title-row', dataset: { osis: v.osis }, attrs: { role: 'button', tabindex: '0' },
      on: { click: () => this.select(v.osis), keydown: (e) => { if (e.key === 'Enter') this.select(v.osis); } } },
      el('span', { class: 'lbl', text: 'Title' }),
      el('span', { class: 'heb', lang: 'hbo', text: this.heb(v.title || '') }));
  }

  renderProse(verses, lines) {
    const t = this.data.translations[0];
    const dir = dirFor(t, this.data.book);
    const orig = t.kind === 'original';
    const box = el('div', { class: `prose${lines ? ' lines' : ''}${orig ? ' orig-text' : ''}`, attrs: { dir, lang: orig ? undefined : t.language } });
    for (const v of verses) {
      const text = v.texts[t.code];
      if (!text) continue;
      const span = el('span', { class: 'v', dataset: { osis: v.osis } },
        el('span', { class: 'vn', text: v.verse }),
        el('span', { class: 'vt' + this.hl(v.osis), text: orig ? this.heb(text) : text,
          attrs: { role: 'button', tabindex: '0', 'aria-label': `Verse ${v.verse}` } }),
        this.marks(v));
      box.append(span, ' ');
    }
    box.addEventListener('click', (e) => { const v = e.target.closest('.v'); if (v) this.select(v.dataset.osis); });
    box.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const v = e.target.closest('.v'); if (v) this.select(v.dataset.osis); } });
    return box;
  }

  renderGrid(verses) {
    const ts = this.data.translations;
    const head = el('div', { class: 'colhead', style: { '--cols': ts.length } }, el('span'),
      ...ts.map((t) => el('span', { title: t.name }, t.code, t.kind === 'original' ? el('small', { text: 'Heb/Grk' }) : null)));
    const rows = verses.map((v) => el('div', { class: 'grow' + this.hl(v.osis), dataset: { osis: v.osis }, style: { '--cols': ts.length },
      attrs: { role: 'button', tabindex: '0', 'aria-label': `Verse ${v.verse}` } },
      el('div', { class: 'gn' }, String(v.verse), this.marks(v)),
      ...ts.map((t) => {
        const text = v.texts[t.code];
        if (!text) return el('div', { class: 'gc none', text: '—', title: `${t.code} doesn't number a verse here` });
        const orig = t.kind === 'original';
        return el('div', { class: `gc${orig ? ' orig-col' : ''}`, attrs: { dir: dirFor(t, this.data.book), lang: orig ? undefined : t.language },
          text: orig ? this.heb(text) : text });
      })));
    const grid = el('div', { class: 'grid' }, head, rows);
    grid.addEventListener('click', (e) => { const r = e.target.closest('.grow'); if (r) this.select(r.dataset.osis); });
    grid.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const r = e.target.closest('.grow'); if (r) this.select(r.dataset.osis); } });
    return grid;
  }

  renderInterlinear(verses) {
    const ts = this.data.translations;
    const texts = ts.filter((t) => t.kind !== 'original');
    const box = el('div', { class: 'inter' });
    for (const v of verses) {
      const lang = v.words?.[0]?.lang;
      const words = (v.words || []).map((w) => {
        const note = variantNote(w);
        return el('button', { class: `iw${note ? ' var' : ''}`, dataset: { osis: v.osis, p: w.p },
          title: [w.lemma && `${w.lemma}`, w.morph, note].filter(Boolean).join(' · '),
          attrs: { 'aria-label': `${w.text}, ${w.gloss || ''}, ${w.strongs || ''}` },
          on: { click: (e) => { e.stopPropagation(); this.openWord(v.osis, w); } } },
        el('span', { class: 'iw-o', text: w.lang === 'hebrew' ? this.heb(w.text) : w.text }),
        el('span', { class: 'iw-t', text: w.translit || '' }),
        el('span', { class: 'iw-g', text: w.gloss || '' }),
        el('span', { class: 'iw-s', text: w.strongs || '' }),
        el('span', { class: 'iw-m', text: w.morph || '' }));
      });
      const main = texts[0] ? v.texts[texts[0].code] : null;
      box.append(el('div', { class: 'iv' + this.hl(v.osis), dataset: { osis: v.osis } },
        el('div', { class: 'iv-text', attrs: { role: 'button', tabindex: '0' }, on: { click: () => this.select(v.osis) } },
          el('span', { class: 'vn', text: v.verse }),
          el('span', { attrs: { dir: texts[0] ? dirFor(texts[0], this.data.book) : 'ltr' }, text: main || '' }),
          this.marks(v),
          ...texts.slice(1).map((t) => v.texts[t.code] ? el('span', { class: 'alt', attrs: { dir: dirFor(t, this.data.book) } },
            el('b', { text: `${t.code} ` }), v.texts[t.code]) : null)),
        words.length ? el('div', { class: 'iwords', attrs: { dir: lang === 'hebrew' ? 'rtl' : 'ltr', lang: lang === 'hebrew' ? 'hbo' : 'grc' } }, words)
          : el('div', { class: 'muted', style: { fontSize: '.85rem', marginTop: '.3rem' },
            text: 'No Hebrew/Greek words are numbered as this verse in this translation’s numbering.' })));
    }
    return box;
  }

  // ------------------------------------------------------------------ selection
  select(osis, { silent = false } = {}) {
    this.sel = osis;
    this.markSelected();
    if (!silent) emit('select-verse', { osis, pane: this });
  }

  openWord(osis, w) {
    this.sel = osis;
    this.wordSel = `${osis}#${w.p}`;
    this.markSelected();
    emit('select-verse', { osis, pane: this, quiet: true });
    emit('open-word', { id: w.dstrong || w.strongs, osis, pane: this });
  }

  markSelected() {
    this.page.querySelectorAll('.sel, .iw.on').forEach((n) => n.classList.remove('sel', 'on'));
    if (!this.sel) return;
    this.page.querySelectorAll(`[data-osis="${CSS.escape(this.sel)}"]`).forEach((n) => {
      if (!n.classList.contains('iw')) n.classList.add('sel');
    });
    if (this.wordSel) {
      const [o, p] = this.wordSel.split('#');
      this.page.querySelector(`.iw[data-osis="${CSS.escape(o)}"][data-p="${p}"]`)?.classList.add('on');
    }
  }

  selectedText(osis) {
    const v = this.data?.verses.find((x) => x.osis === osis);
    if (!v) return '';
    const t = this.data.translations.find((x) => x.kind !== 'original') || this.data.translations[0];
    return v.texts[t.code] || v.title || '';
  }

  textTranslation() {
    return (this.data?.translations.find((t) => t.kind !== 'original') || { code: 'KJV' }).code;
  }

  // ------------------------------------------------------------------ scrolling
  scrollToVerse(osis) {
    const n = this.page.querySelector(`[data-osis="${CSS.escape(osis)}"]`);
    if (!n) return;
    const top = this.body.getBoundingClientRect().top;
    this.body.scrollTop += n.getBoundingClientRect().top - top - this.body.clientHeight * 0.28;
  }

  topAnchor() {
    if (!this.data) return null;
    const top = this.body.getBoundingClientRect().top;
    for (const n of this.page.querySelectorAll('[data-osis]:not(.iw)')) {
      const r = n.getBoundingClientRect();
      if (r.bottom > top + 4) return { osis: n.dataset.osis, delta: r.top - top };
    }
    return null;
  }

  syncTo(osis, delta, force = false) {
    const n = this.page.querySelector(`[data-osis="${CSS.escape(osis)}"]:not(.iw)`);
    if (!n) return;
    this.syncing = !force;
    const top = this.body.getBoundingClientRect().top;
    this.body.scrollTop += n.getBoundingClientRect().top - top - delta;
    requestAnimationFrame(() => requestAnimationFrame(() => { this.syncing = false; }));
  }
}
