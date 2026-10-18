// Translation picker: installed translations grouped by language, Hebrew & Greek first.
import { app, el, emit, put } from './core.js';
import { closePopover, openPopover } from './popover.js';

export function openPicker(anchor, selected, onToggle) {
  const list = el('div');
  const filter = el('input', { class: 'field', type: 'search', placeholder: 'Filter by name, code or language',
    attrs: { 'aria-label': 'Filter translations' } });

  function render() {
    const q = filter.value.trim().toLowerCase();
    put(list);
    const groups = new Map();
    for (const t of app.translations) {
      const hay = `${t.code} ${t.name} ${t.language_name}`.toLowerCase();
      if (q && !hay.includes(q)) continue;
      const g = t.kind === 'original' ? 'Hebrew & Greek' : t.language_name;
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(t);
    }
    const order = [...groups.keys()].sort((a, b) =>
      (a === 'Hebrew & Greek' ? -2 : a === 'English' ? -1 : 0) - (b === 'Hebrew & Greek' ? -2 : b === 'English' ? -1 : 0) || a.localeCompare(b));
    for (const g of order) {
      list.append(el('h4', { text: g }));
      for (const t of groups.get(g)) {
        const on = selected().includes(t.code);
        list.append(el('button', {
          class: 'pick', attrs: { role: 'menuitemcheckbox', 'aria-checked': String(on) },
          on: { click: () => { onToggle(t.code); render(); } },
        }, el('span', { class: 'check', text: on ? '✓' : '' }), el('span', { class: 'code', text: t.code }),
        el('span', { class: 'name', text: t.name, title: t.name })));
      }
    }
    if (!list.children.length) list.append(el('p', { class: 'muted', text: 'No installed translation matches.' }));
  }
  filter.addEventListener('input', render);
  render();
  const foot = el('div', { class: 'pop-foot' },
    el('button', { class: 'btn quiet', text: 'Get more translations…', on: { click: () => { closePopover(); emit('open-library'); } } }));
  openPopover(anchor, [filter, list, foot], { label: 'Choose translations' });
}
