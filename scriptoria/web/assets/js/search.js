// Advanced search view.
import { api, app, el, emit, fmt, persist, plural, stripCantillation, toast, put } from './core.js';
import { bookChart } from './chart.js';
import { openPicker } from './picker.js';

const MODES = [
  ['auto', 'Smart', 'Words search the text; a passage (jn 3:16) jumps to it; a Strong’s number or Greek/Hebrew word (G26, ἀγάπη) finds every occurrence.'],
  ['all', 'All words', 'Verses containing every word. End a word with * to match its beginning: believ*'],
  ['phrase', 'Exact phrase', 'These words, together, in this order.'],
  ['any', 'Any word', 'Verses containing at least one of the words.'],
  ['original', 'Hebrew & Greek', 'A Strong’s number (G26, H7225), a Greek or Hebrew dictionary word (ἀγάπη = every form; ἀγάπην = that form only), or a transliteration (agape, reshit). Accents and vowel points are optional.'],
  ['advanced', 'Advanced', 'Full-text syntax: AND · OR · NOT · "exact phrase" · NEAR(faith works, 5) · prefix*'],
];

export function renderSearchView(host, init, { onClose }) {
  const s = app.settings.search;
  if (init.mode) s.mode = init.mode;
  if (init.translations) s.translations = init.translations;
  if (init.scope) s.scope = init.scope;
  const q = el('input', { class: 'field', type: 'search', value: init.q || '', placeholder: 'What are you looking for?', attrs: { 'aria-label': 'Search text' } });
  const hint = el('p', { class: 'hint', style: { margin: 0 } });
  const seg = el('div', { class: 'seg', attrs: { role: 'group', 'aria-label': 'Search mode' } });
  const trChips = el('div', { class: 'chips' });
  const scopeSel = el('select', { class: 'select', attrs: { 'aria-label': 'Where to search' } });
  const fromSel = el('select', { class: 'select', attrs: { 'aria-label': 'From book' } });
  const toSel = el('select', { class: 'select', attrs: { 'aria-label': 'To book' } });
  const range = el('span', { class: 'row', hidden: true }, fromSel, 'to', toSel);
  const out = el('div');

  function paintModes() {
    put(seg, ...MODES.map(([k, label]) => el('button', { type: 'button', text: label, attrs: { 'aria-pressed': String(s.mode === k) },
      on: { click: () => { s.mode = k; paintModes(); persist('search'); if (q.value.trim()) run(); } } })));
    hint.textContent = MODES.find((m) => m[0] === s.mode)?.[2] || '';
  }
  function paintTranslations() {
    const all = s.translations.includes('*');
    put(trChips, 
      el('button', { type: 'button', class: 'btn', style: { padding: '.25rem .6rem' }, text: 'All installed', attrs: { 'aria-pressed': String(all) },
        on: { click: () => { s.translations = all ? ['KJV'] : ['*']; paintTranslations(); persist('search'); } } }),
      ...(all ? [] : s.translations.map((c) => el('span', { class: 'chip', title: app.tmap[c]?.name || c }, c,
        s.translations.length > 1 ? el('button', { type: 'button', text: '×', attrs: { 'aria-label': `Remove ${c}` },
          on: { click: () => { s.translations = s.translations.filter((x) => x !== c); paintTranslations(); persist('search'); } } }) : null))),
      all ? null : el('button', { type: 'button', class: 'chip add', text: '+ Add', on: { click: (e) => openPicker(e.currentTarget, () => s.translations, (code) => {
        s.translations = s.translations.includes(code) ? (s.translations.length > 1 ? s.translations.filter((x) => x !== code) : s.translations) : [...s.translations, code];
        paintTranslations(); persist('search');
      }) } }));
  }
  function paintScope() {
    const opt = (v, t) => el('option', { value: v, text: t });
    put(scopeSel, opt('all', 'Whole Bible'), opt('ot', 'Old Testament'), opt('nt', 'New Testament'), opt('range', 'Range of books…'),
      el('optgroup', { label: 'Old Testament' }, app.books.filter((b) => b.testament === 'OT').map((b) => opt(b.osis, b.name))),
      el('optgroup', { label: 'New Testament' }, app.books.filter((b) => b.testament === 'NT').map((b) => opt(b.osis, b.name))));
    for (const sel of [fromSel, toSel]) put(sel, ...app.books.map((b) => opt(b.osis, b.name)));
    if (s.scope.includes('-')) { scopeSel.value = 'range'; [fromSel.value, toSel.value] = s.scope.split('-'); range.hidden = false; }
    else { scopeSel.value = s.scope; range.hidden = true; fromSel.value = 'Matt'; toSel.value = 'John'; }
  }
  const scopeValue = () => (scopeSel.value === 'range' ? `${fromSel.value}-${toSel.value}` : scopeSel.value);
  scopeSel.addEventListener('change', () => { range.hidden = scopeSel.value !== 'range'; s.scope = scopeValue(); persist('search'); });
  for (const sel of [fromSel, toSel]) sel.addEventListener('change', () => { s.scope = scopeValue(); persist('search'); });

  let offset = 0, last = null;
  async function run(more = false) {
    const text = q.value.trim();
    if (!text) { q.focus(); return; }
    s.scope = scopeValue();
    if (!more) offset = 0;
    const params = { q: text, mode: s.mode, translations: s.translations.join(','), scope: s.scope, offset, limit: 50 };
    if (!more) put(out, el('p', { class: 'muted', text: 'Searching…' }));
    let d;
    try { d = await api('/api/search', { params }); }
    catch (e) { put(out, el('div', { class: 'note-banner', text: e.message })); return; }
    if (d.reference) { emit('navigate', { osis: d.reference.osis, book: d.reference.book, chapter: d.reference.chapter }); onClose(); return; }
    last = d;
    const items = d.results.map(resultItem);
    if (more) { out.querySelector('.rlist').append(...items); }
    else {
      const unit = d.unit === 'matches' ? 'match' : 'verse';
      put(out, 
        el('div', { class: 'rsummary' },
          el('h2', { text: d.total ? plural(d.total, unit, unit === 'match' ? 'matches' : 'verses') : 'Nothing found' }),
          el('span', { class: 'muted', text: [d.mode === 'original' ? d.interpreted : `“${d.query}”`, d.scope,
            d.translations.length > 4 ? `${d.translations.length} translations` : d.translations.join(', ')].filter(Boolean).join(' · ') })),
        d.message ? el('div', { class: 'note-banner', text: d.message }) : null,
        !d.total && !d.message ? el('p', { class: 'empty', text: s.mode === 'phrase' ? 'Try fewer words, or switch to All words.' : 'Try another spelling, another translation, or a wider scope.' }) : null,
        d.by_book.length > 1 ? bookChart(d.by_book, { unit: unit === 'match' ? 'matches' : 'verses',
          onPick: (osis) => { s.scope = osis || 'all'; paintScope(); run(); } }) : null,
        el('div', { class: 'rlist', style: { marginTop: '.8rem' } }, items));
    }
    offset += d.results.length;
    out.querySelector('.more')?.remove();
    if (offset < d.total) out.append(el('div', { class: 'more' }, el('button', { class: 'btn', text: `Show more (${fmt(d.total - offset)} left)`, on: { click: () => run(true) } })));
    persist('search');
  }

  function resultItem(r) {
    const t = app.tmap[r.translation];
    const orig = t?.kind === 'original';
    const snip = el('div', { class: `result-snip${orig ? ' orig-text' : ''}`, attrs: { dir: orig && /[֐-׿]/.test(r.html) ? 'rtl' : (t?.direction === 'rtl' ? 'rtl' : 'ltr') } });
    snip.innerHTML = orig ? stripCantillation(r.html) : r.html;            // server-escaped, only <mark> added
    return el('button', { class: 'result', on: { click: () => { emit('navigate', { osis: r.osis }); onClose(); } } },
      el('div', { class: 'result-ref' }, r.ref, last && (last.translations.length > 1 || orig) && r.translation ? el('span', { class: 'tcode', text: r.translation }) : null),
      snip,
      r.words?.length ? el('div', { class: 'result-words' }, r.words.map((w) => el('span', {},
        el('span', { class: 'orig-text', text: stripCantillation(w.text) }), ` ${w.gloss || ''}`))) : null);
  }

  const form = el('form', { class: 'sform', on: { submit: (e) => { e.preventDefault(); run(); } } },
    el('div', { class: 'q' }, q, el('button', { class: 'btn primary', type: 'submit', text: 'Search' })),
    el('div', { class: 'opts' },
      el('div', { class: 'opt' }, el('span', { text: 'Match' }), seg),
      el('div', { class: 'opt' }, el('span', { text: 'In' }), trChips),
      el('div', { class: 'opt' }, el('span', { text: 'Where' }), el('div', { class: 'row' }, scopeSel, range))),
    hint);

  put(host, el('div', { class: 'view-wrap' },
    el('div', { class: 'view-head' }, el('h1', { text: 'Search' }),
      el('button', { class: 'btn', text: 'Back to reading', title: 'Esc', on: { click: onClose } })),
    form, out));
  paintModes(); paintTranslations(); paintScope();
  if (init.q) run(); else q.focus();
  return { focus: () => q.focus() };
}

export { toast };
