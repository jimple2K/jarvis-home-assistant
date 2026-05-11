import React, { useEffect, useState, useRef } from 'react';
import { getActivity } from '../api.js';

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const KIND_LABEL = {
  user:        'YOU',
  llm:         'THINK',
  tool:        'TOOL',
  reply:       'REPLY',
  speak:       'SPEAK',
  'speak-done':'SPOKE',
  reset:       'RESET',
  error:       'ERR',
};

function timeAgo(ts, nowSrv, nowLocal) {
  // ts is server epoch seconds. Anchor relative to the server's "now" if known.
  const drift = nowLocal - nowSrv;
  const ageSec = Math.max(0, (Date.now() / 1000) - drift - ts);
  if (ageSec < 1)   return 'now';
  if (ageSec < 60)  return `${Math.floor(ageSec)}s`;
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)}m`;
  return `${Math.floor(ageSec / 3600)}h`;
}

export default function ActivityPanel() {
  const [data,    setData]    = useState({ current: null, events: [], now: 0 });
  const nowLocalRef = useRef(Date.now() / 1000);

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const d = await getActivity();
        if (!alive) return;
        nowLocalRef.current = Date.now() / 1000;
        setData(d);
      } catch {}
    }
    tick();
    const t = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const events = (data.events || []).slice().reverse(); // newest first
  const cur = data.current;

  return (
    <div id="activity-panel">
      <div className="sb-header"><span>Activity</span></div>

      <div className="ac-current">
        {cur ? (
          <>
            <span className={'ac-cur-dot ' + cur.kind} />
            <span className="ac-cur-kind">{esc((cur.kind || '').toUpperCase())}</span>
            <span className="ac-cur-label" title={cur.label}>{esc(cur.label)}</span>
          </>
        ) : (
          <>
            <span className="ac-cur-dot idle" />
            <span className="ac-cur-kind muted">IDLE</span>
            <span className="ac-cur-label muted">Waiting for input</span>
          </>
        )}
      </div>

      <div id="activity-list">
        {events.length === 0 ? (
          <div className="ac-empty">No activity yet</div>
        ) : (
          events.map(e => (
            <div key={e.id} className={'ac-item kind-' + e.kind}>
              <span className="ac-kind">{esc(KIND_LABEL[e.kind] || e.kind.toUpperCase())}</span>
              <span className="ac-label" title={e.label}>{esc(e.label)}</span>
              <span className="ac-time">{timeAgo(e.ts, data.now, nowLocalRef.current)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
