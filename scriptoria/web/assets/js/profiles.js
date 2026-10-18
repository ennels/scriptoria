// "Who's reading?" — switch, add, rename and remove profiles. No passwords: profiles
// keep each person's notes, highlights and reading place apart on a shared computer.
import { api, app, el, emit, plural, toast, put } from './core.js';
import { closePopover, openPopover } from './popover.js';

export function avatar(p, size) {
  const a = el('span', { class: 'avatar', text: (p.name || '?').trim().charAt(0).toUpperCase(), style: { background: `var(--p-${p.color})` } });
  if (size) Object.assign(a.style, { width: size, height: size });
  return a;
}

function colorPicker(current, onPick) {
  const box = el('div', { class: 'colors', attrs: { role: 'group', 'aria-label': 'Colour' } });
  const paint = (sel) => put(box, ...app.colors.map((c) => el('button', { type: 'button', title: c, style: { background: `var(--p-${c})` },
    attrs: { 'aria-pressed': String(c === sel), 'aria-label': c }, on: { click: () => { onPick(c); paint(c); } } })));
  paint(current);
  return box;
}

export function openProfileMenu(anchor) {
  const content = el('div');
  const paint = () => {
    const cur = app.profile;
    const list = app.profiles.map((p) => el('button', { class: 'prof', attrs: { 'aria-current': String(p.id === cur.id) },
      on: { click: () => { closePopover(); if (p.id !== cur.id) emit('switch-profile', p.id); } } },
      avatar(p), el('span', {}, el('div', { text: p.name }), el('div', { class: 'meta', text: `${plural(p.notes, 'note')} · ${plural(p.highlights, 'highlight')}` }))));

    // edit current
    let color = cur.color;
    const name = el('input', { class: 'field', value: cur.name, attrs: { 'aria-label': 'Profile name', maxlength: '40' } });
    const save = el('button', { class: 'btn', text: 'Save', on: { click: async () => {
      try { const p = await api(`/api/profiles/${cur.id}`, { method: 'PATCH', body: { name: name.value, color } }); emit('profiles-changed', p.id); closePopover(); }
      catch (e) { toast(e.message, 'error'); }
    } } });
    const del = app.profiles.length > 1 ? el('button', { class: 'btn quiet danger', text: `Delete ${cur.name}…` }) : null;
    del?.addEventListener('click', () => del.replaceWith(el('span', { class: 'confirm' },
      `Delete ${cur.name} and their ${plural(cur.notes, 'note')}?`,
      el('button', { class: 'btn danger', text: 'Delete', on: { click: async () => {
        try { await api(`/api/profiles/${cur.id}`, { method: 'DELETE' }); const next = app.profiles.find((p) => p.id !== cur.id); closePopover(); emit('switch-profile', next.id); }
        catch (e) { toast(e.message, 'error'); }
      } } }),
      el('button', { class: 'btn quiet', text: 'Keep', on: { click: paint } }))));

    // add new
    let newColor = app.colors.find((c) => !app.profiles.some((p) => p.color === c)) || 'lapis';
    const newName = el('input', { class: 'field', placeholder: 'Name', attrs: { 'aria-label': 'New profile name', maxlength: '40' } });
    const create = async () => {
      if (!newName.value.trim()) { newName.focus(); return; }
      try { const p = await api('/api/profiles', { method: 'POST', body: { name: newName.value, color: newColor } }); closePopover(); emit('switch-profile', p.id); toast(`Welcome, ${p.name}`); }
      catch (e) { toast(e.message, 'error'); }
    };
    newName.addEventListener('keydown', (e) => { if (e.key === 'Enter') create(); });

    put(content, 
      el('h4', { text: 'Who’s reading?' }), ...list,
      el('h4', { text: `Edit ${cur.name}` }),
      el('div', { class: 'row', style: { marginBottom: '.45rem' } }, name, save),
      colorPicker(color, (c) => { color = c; }),
      del ? el('div', { style: { marginTop: '.5rem' } }, del) : null,
      el('h4', { text: 'Add someone' }),
      el('div', { class: 'row', style: { marginBottom: '.45rem' } }, newName, el('button', { class: 'btn primary', text: 'Add', on: { click: create } })),
      colorPicker(newColor, (c) => { newColor = c; }),
      el('p', { class: 'hint', style: { margin: '.7rem 0 0' }, text: 'Profiles keep notes, highlights and your place separate. There are no passwords — anyone at this computer can switch.' }));
  };
  paint();
  openPopover(anchor, content, { align: 'right', label: 'Profiles' });
}
