import { useEffect } from 'react';

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
  'input:not([disabled])', 'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * useFocusTrap — when `active`, traps Tab/Shift+Tab inside `containerRef`,
 * focuses the first focusable on activation, and restores focus on
 * deactivation. Plays well with click-outside / ESC handlers.
 */
export function useFocusTrap(containerRef, active) {
  useEffect(() => {
    if (!active) return;
    const node = containerRef.current;
    if (!node) return;

    const previouslyFocused = document.activeElement;
    const focusables = node.querySelectorAll(FOCUSABLE);
    const first = focusables[0];

    const t = setTimeout(() => {
      if (first && typeof first.focus === 'function') first.focus();
    }, 30);

    function onKey(e) {
      if (e.key !== 'Tab') return;
      const list = Array.from(node.querySelectorAll(FOCUSABLE))
        .filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null);
      if (list.length === 0) return;
      const f = list[0];
      const l = list[list.length - 1];
      if (e.shiftKey && document.activeElement === f) {
        e.preventDefault(); l.focus();
      } else if (!e.shiftKey && document.activeElement === l) {
        e.preventDefault(); f.focus();
      }
    }
    node.addEventListener('keydown', onKey);

    return () => {
      clearTimeout(t);
      node.removeEventListener('keydown', onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        try { previouslyFocused.focus(); } catch {}
      }
    };
  }, [active, containerRef]);
}
