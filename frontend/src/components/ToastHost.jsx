import React, { useEffect, useState } from 'react';
import { subscribe, dismiss } from '../lib/toast.js';

const ICONS = {
  info: 'i',
  success: '✓',
  warn: '!',
  error: '✕',
};

export default function ToastHost() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => subscribe(setToasts), []);

  if (toasts.length === 0) return null;
  return (
    <div id="toast-host" role="region" aria-label="Notifications" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast ${t.kind}${t.leaving ? ' leaving' : ''}`}
          role={t.kind === 'error' ? 'alert' : 'status'}
        >
          <span className="toast-icon" aria-hidden>{ICONS[t.kind] || 'i'}</span>
          <div className="toast-body">
            {t.title && <div className="toast-title">{t.title}</div>}
            {t.message && <div className="toast-msg">{t.message}</div>}
          </div>
          <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
