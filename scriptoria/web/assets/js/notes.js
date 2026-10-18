// Notes & highlights: the study-panel tab for one verse, and the "All my notes" view.
import { api, app, el, emit, plural, refLabel, toast, put } from './core.js';

const COLORS = ['amber', 'rose', 'sky', 'sage', 'lilac'];
const parseTags = (s) => s.split(/[,\n]/).map((t) => t.trim().replace(/^#/, '')).filter(Boolean);
const when = (ts) => { const d = new Date(`${ts.replace(' ', 'T')}Z`); return isNaN(d) ? ts : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); };

function composer({ body = '', tags = [], saveLabel = 'Save note', onSave, onCancel }) {
  const ta = el('textarea', { value: body, placeholder: 'Write a note on this verse…', attrs: { 'aria-label': 'Note' } });
  const tg = el('input', { class: 'field', value: tags.join(', '), placeholder: 'Tags, separated by commas', attrs: { 'aria-label': 'Tags' } });
  const save = el('button', { class: 'btn primary', text: saveLabel });
  const go = async () => {
    if (!ta.value.trim()) { ta.focus(); return; }
    save.disabled = true;
    try { await onSave(ta.value, parseTags(tg.value)); } catch (e) { toast(e.message, 'error'); save.disabled = false; }
  };
  save.addEventListener('click', go);
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) go(); });
  return el('div', { class: 'composer' }, ta, el('div', { class: 'row' }, tg, onCancel ? el('button', { class: 'btn quiet', text: 'Cancel', on: { click: onCancel } }) : null, save));
}

function confirmDelete(btn, onYes) {
  const box = el('span', { class: 'confirm' }, 'Delete this note?',
    el('button', { class: 'btn danger', text: 'Delete', on: { click: onYes } }),
    el('button', { class: 'btn quiet', text: 'Keep', on: { click: () => box.replaceWith(btn) } }));
  btn.replaceWith(box);
  box.querySelector('button').focus();
}

function noteCard(n, { onChange, showRef = false }) {
  const card = el('article', { class: 'note-card' });
  const view = () => {
    const del = el('button', { class: 'btn quiet danger', text: 'Delete' });
    del.addEventListener('click', () => confirmDelete(del, async () => { await api(`/api/notes/${n.id}`, { method: 'DELETE' }); onChange(); }));
    put(card, 
      showRef ? el('button', { class: 'note-ref', text: n.ref, on: { click: () => emit('navigate', { osis: n.osis }) } }) : null,
      el('div', { class: 'note-body', text: n.body }),
      el('div', { class: 'note-foot' },
        el('div', { class: 'tags' }, n.tags.map((t) => el('span', { class: 'tag', text: `#${t}` })),
          el('span', { class: 'note-time', text: n.updated !== n.created ? `edited ${when(n.updated)}` : when(n.created) })),
        el('div', {}, el('button', { class: 'btn quiet', text: 'Edit', on: { click: edit } }), del)));
  };
  const edit = () => put(card, composer({ body: n.body, tags: n.tags, saveLabel: 'Save changes',
    onCancel: view, onSave: async (body, tags) => { Object.assign(n, await api(`/api/notes/${n.id}`, { method: 'PATCH', body: { body, tags } })); view(); onChange(); } }));
  view();
  return card;
}

export async function renderNotesTab(box, osis, { onChange }) {
  const [book, chapter] = osis.split('.');
  put(box, el('p', { class: 'muted', text: 'Loading…' }));
  const [ann, list] = await Promise.all([
    api('/api/annotations', { params: { book, chapter } }),
    api('/api/notes', { params: { osis } }),
  ]);
  let color = ann.highlights[osis] || null;
  const swatches = el('div', { class: 'swatches', attrs: { role: 'group', 'aria-label': 'Highlight colour' } });
  const paint = () => put(swatches, 
    el('button', { class: 'swatch none', text: '∅', title: 'No highlight', attrs: { 'aria-pressed': String(!color), 'aria-label': 'No highlight' },
      on: { click: () => setColor(null) } }),
    ...COLORS.map((c) => el('button', { class: 'swatch', title: c, style: { background: `var(--sw-${c})` },
      attrs: { 'aria-pressed': String(color === c), 'aria-label': `Highlight ${c}` }, on: { click: () => setColor(c) } })));
  async function setColor(c) {
    try {
      if (c) await api(`/api/highlights/${osis}`, { method: 'PUT', body: { color: c } });
      else await api(`/api/highlights/${osis}`, { method: 'DELETE' });
      color = c; paint(); onChange();
    } catch (e) { toast(e.message, 'error'); }
  }
  paint();
  const refresh = () => { renderNotesTab(box, osis, { onChange }); onChange(); };
  const cards = list.notes.map((n) => noteCard(n, { onChange: refresh }));
  put(box, 
    el('div', { class: 'setting' }, el('span', { text: `Highlight for ${app.profile?.name || 'you'}` }), swatches),
    ...cards,
    composer({ saveLabel: list.notes.length ? 'Add another note' : 'Save note',
      onSave: async (body, tags) => { await api('/api/notes', { method: 'POST', body: { osis, body, tags } }); toast('Note saved'); refresh(); } }));
}

// ------------------------------------------------------------------ notes browser
export async function renderNotesView(host, { onClose }) {
  const state = { tag: null, q: '' };
  const list = el('div');
  const tagBox = el('div', { class: 'tags' });
  const search = el('input', { class: 'field', type: 'search', placeholder: 'Search your notes', attrs: { 'aria-label': 'Search notes' } });
  let t;
  search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.q = search.value.trim(); load(); }, 250); });

  async function exportAs(format) {
    try {
      const r = await api('/api/notes/export', { params: { format }, raw: true });
      const blob = await r.blob();
      const name = /filename="([^"]+)"/.exec(r.headers.get('content-disposition') || '')?.[1] || `scriptoria-notes.${format}`;
      const a = el('a', { href: URL.createObjectURL(blob), download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { toast(e.message, 'error'); }
  }

  async function load() {
    const [res, tags] = await Promise.all([
      api('/api/notes', { params: { tag: state.tag, q: state.q, limit: 1000 } }),
      api('/api/notes/tags'),
    ]);
    put(tagBox, 
      el('button', { class: 'tag', text: 'All', attrs: { 'aria-pressed': String(!state.tag) }, on: { click: () => { state.tag = null; load(); } } }),
      ...tags.map((g) => el('button', { class: 'tag', text: `#${g.tag} ${g.count}`, attrs: { 'aria-pressed': String(state.tag === g.tag) },
        on: { click: () => { state.tag = state.tag === g.tag ? null : g.tag; load(); } } })));
    if (!res.notes.length) {
      put(list, el('p', { class: 'empty', text: state.tag || state.q ? 'No notes match.'
        : 'No notes yet. Select a verse while reading and open the Notes tab to write one.' }));
      return;
    }
    const out = [el('p', { class: 'muted', style: { margin: '0 0 1rem' }, text: plural(res.total, 'note') })];
    let book = null;
    for (const n of res.notes) {
      const b = n.osis.split('.')[0];
      if (b !== book) { out.push(el('h2', { class: 'notes-book', text: app.book[b]?.name || b })); book = b; }
      out.push(noteCard(n, { onChange: load, showRef: true }));
    }
    put(list, ...out);
  }

  put(host, el('div', { class: 'view-wrap' },
    el('div', { class: 'view-head' },
      el('h1', { text: `Notes — ${app.profile?.name || ''}` }),
      el('button', { class: 'btn', text: 'Back to reading', title: 'Esc', on: { click: onClose } })),
    el('div', { class: 'notes-layout' },
      el('aside', { class: 'notes-side' },
        search,
        el('div', {}, el('h3', { text: 'Tags' }), tagBox),
        el('div', {}, el('h3', { text: 'Export' }), el('div', { class: 'row', style: { display: 'flex', gap: '.4rem' } },
          el('button', { class: 'btn', text: 'Markdown', on: { click: () => exportAs('md') } }),
          el('button', { class: 'btn', text: 'JSON', on: { click: () => exportAs('json') } })))),
      list)));
  await load();
  search.focus();
}

export { refLabel };
