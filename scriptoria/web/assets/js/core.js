// Core: API client, DOM helpers, app state, settings persistence, event bus.

// ------------------------------------------------------------------ API
let profileId = null;
export function setProfileId(id) {
  profileId = id;
  try { localStorage.setItem('scr.profile', String(id)); } catch (e) {}
}
export function storedProfileId() {
  try { return localStorage.getItem('scr.profile'); } catch (e) { return null; }
}

export async function api(path, { method = 'GET', body, params, raw = false } = {}) {
  let url = path;
  if (params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, v);
    const s = q.toString();
    if (s) url += (url.includes('?') ? '&' : '?') + s;
  }
  const headers = { 'X-Scriptoria': '1' };
  if (profileId != null) headers['X-Profile'] = String(profileId);
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const r = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => d.msg).join('; ');
    } catch (e) {}
    if (r.status === 409 && msg.startsWith('PROFILE_GONE')) {
      // This profile was deleted (e.g. in another tab): start again as whoever is first.
      try { localStorage.removeItem('scr.profile'); } catch (e) {}
      location.reload();
    }
    const err = new Error(msg.replace(/^PROFILE_GONE:\s*/, ''));
    err.status = r.status;
    throw err;
  }
  if (raw) return r;
  return (r.headers.get('content-type') || '').includes('application/json') ? r.json() : r.text();
}

// ------------------------------------------------------------------ DOM
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

/** el('button', {class:'x', text:'Hi', on:{click}, attrs:{'aria-pressed':'true'}, dataset:{osis}}, ...children) */
export function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'html') n.innerHTML = v;          // only ever used with server-sanitized HTML
    else if (k === 'dataset') Object.assign(n.dataset, v);
    else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith('--')) n.style.setProperty(sk, String(sv));   // custom properties need setProperty
        else n.style[sk] = sv;
      }
    }
    else if (k === 'on') for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn);
    else if (k === 'attrs') for (const [a, av] of Object.entries(v)) { if (av !== undefined && av !== null && av !== false) n.setAttribute(a, av === true ? '' : av); }
    else n[k] = v;
  }
  append(n, kids);
  return n;
}
/** replaceChildren that skips null/undefined/false (the DOM method would print "null"). */
export function put(node, ...kids) {
  node.replaceChildren();
  append(node, kids);
  return node;
}
function append(n, kids) {
  for (const c of kids) {
    if (c === null || c === undefined || c === false || c === '') continue;
    if (Array.isArray(c)) append(n, c);
    else n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
export const fmt = (n) => (n ?? 0).toLocaleString();
export const plural = (n, one, many = one + 's') => `${fmt(n)} ${n === 1 ? one : many}`;
export const stripCantillation = (s) => (s || '').replace(/[֑-ֽ֯׀]/g, '');

export function say(msg) { const l = document.getElementById('live'); if (l) { l.textContent = ''; l.textContent = msg; } }

let toastTimer;
export function toast(msg, kind = '') {
  document.querySelector('.toast')?.remove();
  const t = el('div', { class: `toast ${kind}`, attrs: { role: kind === 'error' ? 'alert' : 'status' }, text: msg });
  document.body.append(t);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.remove(), kind === 'error' ? 6000 : 2800);
}

// ------------------------------------------------------------------ events
const bus = new EventTarget();
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));
export const on = (type, fn) => bus.addEventListener(type, (e) => fn(e.detail));

// ------------------------------------------------------------------ state
export const app = {
  meta: null, books: [], book: {}, translations: [], tmap: {},
  profiles: [], profile: null, colors: [],
  settings: null,
};

export const DEFAULTS = {
  panes: [
    { book: 'John', chapter: 3, versions: ['KJV'], interlinear: false },
    { book: 'John', chapter: 3, versions: ['ORIG'], interlinear: false },
  ],
  split: false, linked: false, studyOpen: true, studyTab: 'xref', theme: 'auto',
  display: { scale: 1, layout: 'flow', cantillation: false, xrefMarks: false, translit: true, gloss: true, strongs: true, morph: false },
  search: { mode: 'auto', translations: ['KJV'], scope: 'all' },
};

export function mergeSettings(saved) {
  const s = structuredClone(DEFAULTS);
  for (const [k, v] of Object.entries(saved || {})) {
    if (k === 'display' || k === 'search') s[k] = { ...s[k], ...v };
    else if (k === 'panes' && Array.isArray(v)) {
      s.panes = [0, 1].map((i) => ({ ...DEFAULTS.panes[i], ...(v[i] || {}) }));
    } else s[k] = v;
  }
  return s;
}

const dirty = new Set();
let flushTimer = null;
/** Save changed settings now (also called before switching profile, so they land on the right one). */
export async function flushSettings() {
  clearTimeout(flushTimer);
  flushTimer = null;
  if (!dirty.size) return;
  const body = {};
  for (const k of dirty) body[k] = app.settings[k];
  dirty.clear();
  try { await api('/api/settings', { method: 'PUT', body }); } catch (e) { /* retried on the next change */ }
}
export function persist(...keys) {
  keys.forEach((k) => dirty.add(k));
  clearTimeout(flushTimer);
  flushTimer = setTimeout(flushSettings, 700);
}

export const bookName = (osis) => app.book[osis]?.name || osis;
export function refLabel(osis) {
  const [b, c, v] = osis.split('.');
  return `${bookName(b)} ${c}${v === '0' ? ' (title)' : `:${v}`}`;
}
export function testamentOf(osis) { return app.book[osis.split('.')[0]]?.testament || 'NT'; }

/** Text direction for a translation within a given book. */
export function dirFor(t, bookOsis) {
  if (!t) return 'ltr';
  if (t.direction === 'mixed') return app.book[bookOsis]?.testament === 'OT' ? 'rtl' : 'ltr';
  return t.direction || 'ltr';
}

/** Greek words carry edition markers (N = Nestle-Aland, K = KJV's Textus Receptus).
 *  Mirrors importers/original_text.in_edition. */
export function inEdition(type, ed) {
  const t = type || '';
  const outside = t.replace(/\([^)]*\)/g, '');
  return outside.includes(ed.toUpperCase()) || t.includes(ed.toLowerCase());
}
export function variantNote(word) {
  if (word.lang !== 'greek' && word.language !== 'greek') {
    const t = word.type || word.text_type || '';
    return t.startsWith('Q') ? 'Qere: read as the scribes’ margin directs' : t.startsWith('X') ? 'Restored from the Septuagint' : null;
  }
  const t = word.type || '';
  const na = inEdition(t, 'N'), tr = inEdition(t, 'K');
  if (na && tr) return null;
  if (tr) return "In the KJV's Greek (Textus Receptus) only";
  if (na) return "Not in the KJV's Greek (Textus Receptus)";
  return 'Found only in other Greek editions';
}
