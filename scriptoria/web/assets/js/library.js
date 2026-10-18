// Translation library: every available version, grouped by language; install or remove.
import { api, el, emit, fmt, toast, put } from './core.js';

let dlg = null;

export async function openLibrary() {
  if (!dlg) {
    dlg = el('dialog', { class: 'sheet', attrs: { 'aria-labelledby': 'libTitle' } });
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
    document.body.append(dlg);
  }
  const state = { lang: 'en', q: '', data: null, busy: new Set() };
  const langs = el('nav', { class: 'lib-langs', attrs: { 'aria-label': 'Languages' } });
  const list = el('div', { class: 'lib-list' });
  const filter = el('input', { class: 'field', type: 'search', placeholder: 'Find a translation or language', attrs: { 'aria-label': 'Find a translation' } });
  const source = el('p', { class: 'hint', style: { margin: '.15rem 0 0' } });
  filter.addEventListener('input', () => { state.q = filter.value.trim().toLowerCase(); paintList(); });

  put(dlg, el('div', { class: 'sheet-inner' },
    el('div', { class: 'sheet-head' },
      el('div', {}, el('h2', { id: 'libTitle', text: 'Translation library' }), source),
      el('button', { class: 'btn', text: 'Done', on: { click: () => dlg.close() } })),
    el('div', { class: 'lib' }, langs, list)));
  dlg.showModal();
  put(list, el('p', { class: 'muted', text: 'Loading the catalog…' }));

  async function load() {
    state.data = await api('/api/library');
    const src = state.data.source;
    source.textContent = src.local ? `Installs from your copy at ${src.local} — no internet needed.`
      : 'Installs download from github.com/thiagobodruk/bible (about 4 MB each). Put bible.zip in Scriptoria’s data folder to install offline.';
    paintLangs(); paintList();
  }

  function paintLangs() {
    const d = state.data;
    const installed = d.translations.filter((t) => t.installed).length;
    const btn = (code, name, count, inst) => el('button', { class: 'lang', attrs: { 'aria-pressed': String(state.lang === code) },
      on: { click: () => { state.lang = code; filter.value = ''; state.q = ''; paintLangs(); paintList(); } } },
      el('span', { text: name }), el('small', { text: inst ? `${inst}/${count}` : `${count}` }));
    put(langs, btn('*installed', 'Installed', installed, 0), btn('*all', 'All languages', d.translations.length, 0),
      ...d.languages.map((l) => btn(l.code, l.name, l.count, l.installed)));
  }

  function paintList() {
    const d = state.data;
    let items = d.translations;
    if (state.q) items = items.filter((t) => `${t.code} ${t.name} ${t.language_name}`.toLowerCase().includes(state.q));
    else if (state.lang === '*installed') items = items.filter((t) => t.installed);
    else if (state.lang !== '*all') items = items.filter((t) => t.language === state.lang);
    const title = state.q ? `Matching “${state.q}”` : state.lang === '*installed' ? 'Installed' : state.lang === '*all' ? 'All languages'
      : d.languages.find((l) => l.code === state.lang)?.name;
    put(list, el('div', { class: 'lib-tools' }, filter),
      el('h3', { class: 'notes-book', style: { marginTop: '.2rem' }, text: title || '' }),
      ...items.map(row));
    if (!items.length) list.append(el('p', { class: 'empty', text: 'Nothing matches.' }));
  }

  function row(t) {
    const action = el('span');
    const paint = () => {
      if (state.busy.has(t.code)) { put(action, el('button', { class: 'btn', disabled: true, text: t.installed ? 'Removing…' : 'Installing…' })); return; }
      if (t.builtin || t.kind === 'original') { put(action, el('span', { class: 'muted', style: { fontSize: '.82rem' }, text: 'Included' })); return; }
      if (t.installed) {
        const rm = el('button', { class: 'btn quiet danger', text: 'Remove' });
        rm.addEventListener('click', () => put(action, el('span', { class: 'confirm' }, 'Remove?',
          el('button', { class: 'btn danger', text: 'Remove', on: { click: () => act('DELETE') } }),
          el('button', { class: 'btn quiet', text: 'Keep', on: { click: paint } }))));
        put(action, rm);
      } else put(action, el('button', { class: 'btn primary', text: 'Install', on: { click: () => act('POST') } }));
    };
    async function act(method) {
      state.busy.add(t.code); paint();
      try {
        const r = await api(`/api/library/${encodeURIComponent(t.code)}`, { method });
        t.installed = method === 'POST';
        t.verses = r.verses ?? null;
        toast(method === 'POST' ? `${t.name} installed (${fmt(r.verses)} verses)` : `${t.name} removed`);
        emit('translations-changed');
      } catch (e) { toast(e.message, 'error'); }
      state.busy.delete(t.code);
      const l = state.data.languages.find((x) => x.code === t.language);
      if (l) l.installed = state.data.translations.filter((x) => x.language === t.language && x.installed).length;
      paintLangs(); paint(); put(meta, ...metaBits());
    }
    const metaBits = () => [el('b', { text: t.code }), ` · ${t.language_name}`, t.direction === 'rtl' ? ' · right-to-left' : '',
      t.installed && t.verses ? ` · installed, ${fmt(t.verses)} verses` : t.size ? ` · ${(t.size / 1e6).toFixed(1)} MB` : ''];
    const meta = el('div', { class: 'tr-meta' }, ...metaBits());
    paint();
    return el('div', { class: 'tr-row' }, el('div', {}, el('div', { class: 'tr-name', text: t.name }), meta), action);
  }

  try { await load(); } catch (e) { put(list, el('p', { class: 'empty', text: e.message })); }
}
