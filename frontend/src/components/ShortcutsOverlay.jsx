import React, { useEffect, useRef } from 'react';
import { useFocusTrap } from '../hooks/useFocusTrap.js';

const SHORTCUTS = [
  { keys: ['Space'],          label: 'Toggle listening' },
  { keys: ['Esc'],            label: 'Interrupt / close drawers' },
  { keys: ['?'],              label: 'Show this help' },
  { keys: ['Ctrl', 'Enter'],  label: 'Send typed message' },
  { keys: ['Ctrl', 'L'],      label: 'New chat' },
  { keys: ['Ctrl', '/'],      label: 'Toggle always-on' },
  { keys: ['G', 'S'],         label: 'Open Settings' },
  { keys: ['G', 'R'],         label: 'Open Racing hub' },
];

export default function ShortcutsOverlay({ open, onClose }) {
  const panelRef = useRef(null);
  useFocusTrap(panelRef, open);

  useEffect(() => {
    function onKey(e) {
      if (!open) return;
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <div
      className={'shortcuts-overlay' + (open ? ' open' : '')}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      aria-hidden={!open}
    >
      <div className="shortcuts-panel" ref={panelRef} role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
        <div className="shortcuts-head">
          <span className="shortcuts-title">Keyboard Shortcuts</span>
          <button className="shortcuts-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="shortcuts-grid">
          {SHORTCUTS.map((s, i) => (
            <div key={i} className="shortcut-row">
              <span className="shortcut-label">{s.label}</span>
              <span className="shortcut-keys">
                {s.keys.map((k, j) => (
                  <kbd key={j}>{k}</kbd>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
