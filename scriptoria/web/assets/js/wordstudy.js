// Word study: lexicon entry, where the word occurs, its forms, how it's translated,
// and a concordance of every verse — all from the Hebrew/Greek tagging.
import { api, el, emit, fmt, plural, stripCantillation, app, put } from './core.js';
import { bookChart } from './chart.js';

const POS = { N: 'Noun', V: 'Verb', A: 'Adjective', ADV: 'Adverb', CONJ: 'Conjunction', PREP: 'Preposition',
  PRT: 'Particle', T: 'Article', P: 'Pronoun', INJ: 'Interjection', R: 'Pronoun', D: 'Demonstrative',
  C: 'Pronoun', I: 'Pronoun', X: 'Pronoun', Q: 'Pronoun', K: 'Pronoun', S: 'Pronoun', COND: 'Conditional',
  ARAM: 'Aramaic', HEB: 'Hebrew', 'N-PRI': 'Proper noun' };
const GENDER = { M: 'masculine', F: 'feminine', N: 'neuter' };

export function posLabel(pos) {
  if (!pos) return '';
  if (POS[pos]) return POS[pos];
  const [head, rest] = pos.split('-');
  const g = (rest || '').split('/').map((x) => GENDER[x]).filter(Boolean).join(' or ');
  return [POS[head] || head, g].filter(Boolean).join(', ');
}

/** STEPBible refs inside lexicon entries look like 'Mat.5.43' or '2Ti.4.8, 10'. */
async function followRef(raw) {
  const m = /^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)/.exec(raw || '');
  if (!m) return;
  try {
    const r = await api('/api/resolve', { params: { q: `${m[1]} ${m[2]}:${m[3]}` } });
    if (r.found) emit('navigate', { osis: r.osis, book: r.book, chapter: r.chapter });
  } catch (e) { /* unknown ref: ignore */ }
}

export async function renderWordStudy(box, id, { translation = 'KJV', alive = () => true } = {}) {
  put(box, el('p', { class: 'muted', text: 'Opening word study…' }));
  let d;
  try { d = await api(`/api/word/${encodeURIComponent(id)}`); }
  catch (e) { if (alive()) put(box, el('p', { class: 'empty', text: `No word study for ${id}: ${e.message}` })); return; }
  if (!alive()) return;

  const heb = d.language === 'hebrew';
  const show = (s) => (heb && !app.settings.display.cantillation ? stripCantillation(s || '') : s || '');
  const filter = { book: null, sense: d.senses.length > 1 && d.senses.some((s) => s.dstrong === id) ? id : null };
  let primary = d.senses.find((s) => s.dstrong === id) || d.senses[0];

  // ---- header
  const senseChips = d.senses.length > 1 ? el('div', { class: 'senses', attrs: { role: 'group', 'aria-label': 'Senses' } },
    d.senses.map((s) => el('button', { class: 'sense', attrs: { 'aria-pressed': String(filter.sense === s.dstrong) },
      title: s.relation ? `${s.dstrong} — ${s.relation}` : s.dstrong,
      text: `${s.gloss || s.dstrong} · ${fmt(s.count)}`,
      on: { click: () => { filter.sense = filter.sense === s.dstrong ? null : s.dstrong; primary = d.senses.find((x) => x.dstrong === (filter.sense || id)) || d.senses[0]; refreshSenses(); renderDef(); loadOcc(true); } } }))) : null;
  function refreshSenses() { senseChips?.querySelectorAll('.sense').forEach((b, i) => b.setAttribute('aria-pressed', String(filter.sense === d.senses[i].dstrong))); }

  const head = el('div', {},
    el('div', { class: 'ws-head' },
      el('span', { class: 'ws-lemma', lang: heb ? 'hbo' : 'grc', attrs: { dir: heb ? 'rtl' : 'ltr' }, text: show(d.lemma) }),
      el('span', { class: 'ws-translit', text: d.translit || '' })),
    el('div', { class: 'ws-gloss', text: d.gloss || '' }),
    el('div', { class: 'ws-meta' },
      [d.strongs, posLabel(d.pos), d.pronounce && `say “${d.pronounce}”`].filter(Boolean).join(' · '), el('br'),
      `${plural(d.occurrences, 'time')} in ${plural(d.verses, 'verse')}, across ${plural(d.by_book.length, 'book')}`),
    senseChips);

  // ---- distribution
  const chartHost = el('div');
  const renderChart = () => put(chartHost, bookChart(d.by_book, { selected: filter.book, unit: 'times',
    onPick: (osis) => { filter.book = osis; renderChart(); loadOcc(true); } }));
  renderChart();

  // ---- definition
  const def = el('div', { class: 'lexdef clamp' });
  const more = el('button', { class: 'linkbtn', text: 'Show full entry',
    on: { click: () => { def.classList.toggle('clamp'); more.textContent = def.classList.contains('clamp') ? 'Show full entry' : 'Show less'; } } });
  def.addEventListener('click', (e) => { const a = e.target.closest('.sref'); if (a) followRef(a.dataset.ref); });
  function renderDef() {
    def.innerHTML = primary?.definition || '<i>No lexicon entry.</i>';      // sanitized on import
    requestAnimationFrame(() => { more.hidden = def.scrollHeight <= def.clientHeight + 8; });
  }
  renderDef();
  const se = d.strongs_entry;
  const strongs = se ? el('div', { class: 'kv', style: { marginTop: '.7rem' } },
    se.kjv_def ? el('div', {}, el('b', { text: 'KJV renders it: ' }), se.kjv_def) : null,
    se.derivation ? el('div', {}, el('b', { text: 'Derivation: ' }), se.derivation) : null,
    se.definition ? el('div', {}, el('b', { text: 'Strong’s: ' }), se.definition) : null) : null;

  // ---- forms & glosses
  const formRows = d.forms.map((f) => el('tr', {},
    el('td', { class: 'f', lang: heb ? 'hbo' : 'grc', attrs: { dir: heb ? 'rtl' : 'ltr' }, text: show(f.form) }),
    el('td', { class: 'p', text: f.parsing || f.morph || '' }),
    el('td', { class: 'n', text: fmt(f.count) })));
  const forms = el('table', { class: 'mini' }, el('tbody', {}, formRows.slice(0, 8)));
  const formsMore = formRows.length > 8 ? el('button', { class: 'linkbtn',
    text: `All ${formRows.length} forms`, on: { click: (e) => { put(forms.tBodies[0], ...formRows); e.currentTarget.remove(); } } }) : null;
  const glosses = el('div', { class: 'glosses' }, d.glosses.slice(0, 14).map((g) => el('span', {}, g.gloss, el('small', { text: `×${fmt(g.count)}` }))));

  // ---- concordance
  const occList = el('div');
  const occHead = el('span');
  const filterChips = el('span', { style: { display: 'inline-flex', gap: '.3rem' } });
  const moreBtn = el('button', { class: 'btn', text: 'Show more', on: { click: () => loadOcc(false) } });
  let offset = 0, occSeq = 0;
  async function loadOcc(reset) {
    const seq = ++occSeq;
    if (reset) offset = 0;
    put(filterChips, ...[
      filter.book && el('span', { class: 'filterchip' }, app.book[filter.book].name,
        el('button', { text: '×', attrs: { 'aria-label': 'Clear book filter' }, on: { click: () => { filter.book = null; renderChart(); loadOcc(true); } } })),
    ].filter(Boolean));
    const r = await api(`/api/word/${encodeURIComponent(d.strongs)}/occurrences`,
      { params: { translation, book: filter.book, sense: filter.sense, offset, limit: 25 } });
    if (seq !== occSeq || !alive()) return;           // a newer filter or another word replaced this
    if (reset) put(occList);
    occHead.textContent = `${plural(r.total, 'verse')}`;
    for (const o of r.results) {
      occList.append(el('div', { class: 'occ', attrs: { role: 'button', tabindex: '0' },
        on: { click: () => emit('navigate', { osis: o.osis }), keydown: (e) => { if (e.key === 'Enter') emit('navigate', { osis: o.osis }); } } },
        el('div', { class: 'occ-ref' }, o.ref, ...o.words.map((w) => el('span', { class: 'orig-text', lang: heb ? 'hbo' : 'grc', text: show(w.text) }))),
        o.text ? el('div', { class: 'occ-text', text: o.text }) : null));
    }
    offset += r.results.length;
    moreBtn.hidden = offset >= r.total;
  }

  const sec = (title, ...kids) => el('section', { class: 'ws-sec' }, el('h3', {}, ...[].concat(title)), ...kids);
  put(box, 
    head,
    sec('Where it occurs', chartHost),
    sec(['Meaning', more], def, strongs),
    d.forms.length ? sec('Forms in the text', forms, formsMore) : null,
    d.glosses.length ? sec('How it’s glossed', glosses) : null,
    sec([el('span', {}, 'Every occurrence ', occHead), el('button', { class: 'linkbtn',
      text: 'Open in search', on: { click: () => emit('search', { q: filter.sense || d.strongs, mode: 'original' }) } })],
    filterChips, occList, el('div', { class: 'more' }, moreBtn)));
  await loadOcc(true);
}
