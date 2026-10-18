// Reading options: text size, verse layout, interlinear lines, Hebrew marks, theme.
import { app, el, emit, persist, put } from './core.js';
import { openPopover } from './popover.js';

const SIZES = [0.88, 1, 1.12, 1.26, 1.42];

export function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === 'light' || mode === 'dark') root.dataset.theme = mode; else delete root.dataset.theme;
  try { localStorage.setItem('scr.theme', mode); } catch (e) {}
}
export function applyScale() { document.documentElement.style.setProperty('--scale', app.settings.display.scale); }

export function openDisplay(anchor) {
  const d = app.settings.display;
  const changed = (rerender = true) => { persist('display'); applyScale(); if (rerender) emit('display-changed'); };
  const seg = (label, opts, get, set) => {
    const box = el('div', { class: 'seg', attrs: { role: 'group', 'aria-label': label } });
    const paint = () => put(box, ...opts.map(([v, t, title]) => el('button', { text: t, title: title || t,
      attrs: { 'aria-pressed': String(get() === v) }, on: { click: () => { set(v); paint(); } } })));
    paint();
    return el('div', { class: 'setting' }, el('span', { text: label }), box);
  };
  const check = (key, label) => el('label', { class: 'check-row' },
    el('input', { type: 'checkbox', checked: !!d[key], on: { change: (e) => { d[key] = e.target.checked; changed(); } } }), label);

  openPopover(anchor, [
    seg('Text size', SIZES.map((v, i) => [v, ['A−', 'A', 'A+', 'A++', 'A+++'][i]]), () => d.scale, (v) => { d.scale = v; changed(false); }),
    seg('Verses', [['flow', 'Flowing'], ['lines', 'One per line']], () => d.layout, (v) => { d.layout = v; changed(); }),
    el('div', { class: 'setting' }, el('span', { text: 'Interlinear lines' }),
      check('translit', 'Transliteration'), check('gloss', 'English gloss'), check('strongs', 'Strong’s number'), check('morph', 'Parsing code')),
    el('div', { class: 'setting' }, el('span', { text: 'Margin marks' }), check('xrefMarks', 'Mark verses that have cross-references (✦)')),
    el('div', { class: 'setting' }, el('span', { text: 'Hebrew' }), check('cantillation', 'Show cantillation (accent) marks')),
    seg('Theme', [['auto', 'Auto', 'Follow the system'], ['light', 'Light'], ['dark', 'Dark']], () => app.settings.theme,
      (v) => { app.settings.theme = v; applyTheme(v); persist('theme'); }),
    el('div', { class: 'setting', style: { marginBottom: 0 } }, el('span', { text: 'Keyboard' }),
      el('div', { class: 'hint' }, ...[['/', 'search'], ['[ ]', 'previous / next chapter'], ['I', 'interlinear'], ['S', 'side by side'],
        ['P', 'study panel'], ['Esc', 'back to reading']].map(([k, t]) => el('div', {}, el('span', { class: 'kbd', text: k }), ` ${t}`)))),
  ], { align: 'right', label: 'Reading options' });
}
