// One popover at a time, anchored to the control that opened it. Closes on outside
// click, Escape, or when the same control is pressed again.
import { el } from './core.js';

let current = null;

export function closePopover() {
  if (!current) return;
  const { node, anchor, onClose } = current;
  current = null;
  node.remove();
  anchor?.setAttribute('aria-expanded', 'false');
  onClose?.();
}

export function openPopover(anchor, content, { onClose, align = 'left', label } = {}) {
  if (current?.anchor === anchor) { closePopover(); return null; }
  closePopover();
  const node = el('div', { class: 'pop', attrs: { role: 'dialog', 'aria-label': label || 'Options' } }, content);
  document.body.append(node);
  const r = anchor.getBoundingClientRect();
  const w = node.offsetWidth, h = node.offsetHeight;
  let left = align === 'right' ? r.right - w : r.left;
  left = Math.max(8, Math.min(left, innerWidth - w - 8));
  let top = r.bottom + 6;
  if (top + h > innerHeight - 8) top = Math.max(8, r.top - h - 6);
  Object.assign(node.style, { left: `${left}px`, top: `${top}px` });
  anchor.setAttribute('aria-expanded', 'true');
  current = { node, anchor, onClose };
  node.querySelector('input, button, select, textarea')?.focus({ preventScroll: true });
  return node;
}

export const popoverOpen = () => !!current;

document.addEventListener('pointerdown', (e) => {
  if (current && !current.node.contains(e.target) && !current.anchor.contains(e.target)) closePopover();
}, true);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && current) { const a = current.anchor; closePopover(); a?.focus(); e.stopPropagation(); }
}, true);
addEventListener('resize', closePopover);
