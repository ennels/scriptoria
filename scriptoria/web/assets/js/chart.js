// "Where it occurs": one column per book of the Bible in canonical order (single series,
// one validated hue). Hover or focus a column for its count; click to filter by that book.
// The summary names the top books and "Show every book" opens the full table.
import { app, el, fmt, put } from './core.js';

export function bookChart(byBook, { onPick, selected = null, unit = 'times', testaments = null } = {}) {
  const counts = new Map(byBook.map((b) => [b.osis, b.count]));
  if (!testaments) {
    const present = new Set(byBook.map((b) => app.book[b.osis]?.testament));
    testaments = ['OT', 'NT'].filter((t) => present.has(t));
    if (!testaments.length) testaments = ['OT', 'NT'];
  }
  const max = Math.max(1, ...byBook.map((b) => b.count));
  const wrap = el('div', { class: 'bookchart' });
  const tip = el('div', { class: 'bc-tip', hidden: true, attrs: { role: 'presentation' } });

  const show = (col, b, n) => {
    put(tip, el('b', { text: fmt(n) }), el('span', { text: b.name }));
    tip.hidden = false;
    const wr = wrap.getBoundingClientRect(), cr = col.getBoundingClientRect();
    const x = Math.max(40, Math.min(wr.width - 40, cr.left - wr.left + cr.width / 2));
    tip.style.left = `${x}px`;
    tip.style.top = `${cr.top - wr.top + (cr.height * (1 - n / max)) - 6}px`;
  };
  const hide = () => { tip.hidden = true; };

  const half = (testament) => el('div', { class: `bc-half ${testament.toLowerCase()}` },
    app.books.filter((b) => b.testament === testament).map((b) => {
      const n = counts.get(b.osis) || 0;
      const col = el('button', {
        class: `bc-col${selected === b.osis ? ' on' : selected && selected !== b.osis ? ' dim' : ''}`,
        attrs: { 'aria-label': `${b.name}: ${fmt(n)} ${unit}`, tabindex: n ? '0' : '-1', disabled: n ? undefined : true },
        on: {
          pointerenter: (e) => n && show(e.currentTarget, b, n), pointerleave: hide,
          focus: (e) => n && show(e.currentTarget, b, n), blur: hide,
          click: () => n && onPick?.(selected === b.osis ? null : b.osis),
        },
      }, el('span', { class: 'bc-bar', style: { height: n ? `max(3px, ${(n / max) * 100}%)` : '0' } }));
      return col;
    }));

  const ranked = [...byBook].sort((a, b) => b.count - a.count);
  const top = ranked.slice(0, 3).map((b) => `${b.name} (${fmt(b.count)})`).join(', ');
  const table = el('table', { class: 'mini', hidden: true },
    el('tbody', {}, ranked.map((b) => el('tr', {},
      el('td', {}, el('button', { class: 'note-ref', text: b.name, on: { click: () => onPick?.(b.osis) } })),
      el('td', { class: 'n', text: fmt(b.count) })))));
  const toggle = el('button', { class: 'linkbtn', text: 'Show every book',
    on: { click: () => { table.hidden = !table.hidden; toggle.textContent = table.hidden ? 'Show every book' : 'Hide the list'; } } });

  wrap.append(
    el('div', { class: 'bc-cols', attrs: { role: 'group', 'aria-label': 'Occurrences by book' } }, testaments.map(half)),
    el('div', { class: 'bc-axis', attrs: { 'aria-hidden': 'true' } }, testaments.map((t) =>
      el('span', { class: t.toLowerCase(), text: t === 'OT' ? 'Genesis → Malachi' : 'Matthew → Revelation' }))),
    tip,
    byBook.length ? el('div', { class: 'bc-summary' }, `Most in ${top}. `, toggle) : null,
    table);
  return wrap;
}
