import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import SpotifyPanel from './SpotifyPanel.jsx';

const LS_KEY = 'jarvis.rightSidebar.layout';
const GUTTER = 6;
const MIN_TS = 92;
const MIN_SP = 100;
const MIN_CO = 64;
const MIN_RW = 168;
const MAX_RW = 520;

function clamp(v, a, b) {
  return Math.max(a, Math.min(b, v));
}

function clampVertical(tsH, spH, totalH) {
  const maxTs = totalH - GUTTER - MIN_SP - GUTTER - MIN_CO;
  const ts = clamp(tsH, MIN_TS, Math.max(MIN_TS, maxTs));
  const mid = totalH - ts - GUTTER;
  const maxSp = mid - GUTTER - MIN_CO;
  const sp = clamp(spH, MIN_SP, Math.max(MIN_SP, maxSp));
  return { tsH: ts, spH: sp };
}

function readSaved() {
  try {
    const r = localStorage.getItem(LS_KEY);
    if (!r) return null;
    const j = JSON.parse(r);
    const tsH = Number(j.tsH);
    const spH = Number(j.spH);
    const rightW = Number(j.rightW);
    if (![tsH, spH, rightW].every((n) => Number.isFinite(n))) return null;
    return { tsH, spH, rightW: clamp(rightW, MIN_RW, MAX_RW) };
  } catch {
    return null;
  }
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function TsMachine({ m }) {
  const mx = m.metrics;
  const sshClass = !m.ssh_configured
    ? 'ssh-none'
    : mx?.live
    ? 'ssh-live'
    : 'ssh-dead';

  const sshTip = !m.ssh_configured
    ? 'SSH: not configured'
    : mx?.live
    ? 'SSH: live connection'
    : 'SSH: reconnecting…';

  let metricsEl = null;
  if (mx) {
    const cpuCls  = mx.cpu_pct  > 85 ? 'crit' : mx.cpu_pct  > 70 ? 'warn' : '';
    const memCls  = mx.mem_pct  > 90 ? 'crit' : mx.mem_pct  > 80 ? 'warn' : '';
    const diskCls = mx.disk_pct > 90 ? 'crit' : mx.disk_pct > 80 ? 'warn' : '';
    metricsEl = (
      <div className="ts-metrics">
        <span className={'ts-metric ' + cpuCls}>CPU {mx.cpu_pct ?? '?'}%</span>
        <span className={'ts-metric ' + memCls}>RAM {mx.mem_pct ?? '?'}%</span>
        <span className={'ts-metric ' + diskCls}>Disk {mx.disk_pct ?? '?'}%</span>
        {mx.load_1m >= 0 && <span className="ts-metric">Load {mx.load_1m}</span>}
      </div>
    );
  }

  return (
    <div className="ts-machine">
      <div className="ts-dots">
        <div
          className={'ts-dot ts' + (m.online ? '' : ' off')}
          title={`Tailscale: ${m.online ? 'online' : 'offline'}`}
        />
        <div className={'ts-dot ' + sshClass} title={sshTip} />
      </div>
      <div className="ts-info">
        <div className="ts-name">
          {esc(m.hostname)}
          {m.self && <span className="ts-self-badge">this</span>}
        </div>
        <div className="ts-sub">
          {esc(m.ip)}{m.os ? ' · ' + esc(m.os) : ''}
        </div>
        {metricsEl}
      </div>
    </div>
  );
}

export default function RightSidebar({ tailscale, concepts, spotify, onSpotifyUpdate }) {
  const machines = tailscale?.machines || [];
  const conceptList = concepts?.concepts || [];
  const rootRef = useRef(null);
  const sizesRef = useRef({ tsH: 220, spH: 150, rightW: 220 });

  const [sizes, setSizes] = useState(() => {
    const saved = readSaved();
    return saved
      ? { ...saved, rightW: clamp(saved.rightW, MIN_RW, MAX_RW) }
      : { tsH: 220, spH: 150, rightW: 220 };
  });
  const [active, setActive] = useState(null);

  useLayoutEffect(() => {
    sizesRef.current = sizes;
  }, [sizes]);

  useLayoutEffect(() => {
    document.documentElement.style.setProperty('--right-sidebar-w', `${sizes.rightW}px`);
  }, [sizes.rightW]);

  useEffect(() => {
    try {
      const { tsH, spH, rightW } = sizes;
      localStorage.setItem(LS_KEY, JSON.stringify({ tsH, spH, rightW }));
    } catch {}
  }, [sizes]);

  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const H = entries[0]?.contentRect?.height;
      if (!H) return;
      setSizes((s) => ({ ...s, ...clampVertical(s.tsH, s.spH, H) }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const bindWidthDrag = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const node = e.currentTarget;
    node.setPointerCapture(e.pointerId);
    const x0 = e.clientX;
    const w0 = sizesRef.current.rightW;
    setActive('w');
    const move = (ev) => {
      const nw = clamp(w0 + (ev.clientX - x0), MIN_RW, MAX_RW);
      setSizes((s) => ({ ...s, rightW: nw }));
    };
    const end = (ev) => {
      try {
        node.releasePointerCapture(ev.pointerId);
      } catch {}
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', end);
      node.removeEventListener('pointercancel', end);
      setActive(null);
    };
    node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', end);
    node.addEventListener('pointercancel', end);
  }, []);

  const bindTsGutter = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const node = e.currentTarget;
    node.setPointerCapture(e.pointerId);
    const y0 = e.clientY;
    const ts0 = sizesRef.current.tsH;
    setActive('ts');
    const move = (ev) => {
      const H = rootRef.current?.clientHeight ?? 0;
      if (H < 80) return;
      const nextTs = ts0 + (ev.clientY - y0);
      setSizes((s) => ({ ...s, ...clampVertical(nextTs, s.spH, H) }));
    };
    const end = (ev) => {
      try {
        node.releasePointerCapture(ev.pointerId);
      } catch {}
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', end);
      node.removeEventListener('pointercancel', end);
      setActive(null);
    };
    node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', end);
    node.addEventListener('pointercancel', end);
  }, []);

  const bindSpGutter = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const node = e.currentTarget;
    node.setPointerCapture(e.pointerId);
    const y0 = e.clientY;
    const sp0 = sizesRef.current.spH;
    setActive('sp');
    const move = (ev) => {
      const H = rootRef.current?.clientHeight ?? 0;
      if (H < 80) return;
      const nextSp = sp0 + (ev.clientY - y0);
      setSizes((s) => ({ ...s, ...clampVertical(s.tsH, nextSp, H) }));
    };
    const end = (ev) => {
      try {
        node.releasePointerCapture(ev.pointerId);
      } catch {}
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', end);
      node.removeEventListener('pointercancel', end);
      setActive(null);
    };
    node.addEventListener('pointermove', move);
    node.addEventListener('pointerup', end);
    node.addEventListener('pointercancel', end);
  }, []);

  return (
    <div id="sidebar-right" ref={rootRef}>
      <div
        className={'rs-resize-edge-left' + (active === 'w' ? ' rs-resize-active' : '')}
        title="Drag to resize sidebar width"
        onPointerDown={bindWidthDrag}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize right sidebar width"
      />
      <div id="ts-panel" style={{ height: sizes.tsH, flexShrink: 0 }}>
        <div className="sb-header">Tailscale Network</div>
        <div id="ts-list">
          {tailscale?.error ? (
            <div className="ts-machine" style={{ color: 'var(--red)', fontSize: '10px' }}>
              {esc(tailscale.error)}
            </div>
          ) : machines.length === 0 ? (
            <div className="ts-machine" style={{ color: 'var(--muted)', fontSize: '10px' }}>
              Tailscale unavailable
            </div>
          ) : (
            machines.map((m, i) => <TsMachine key={i} m={m} />)
          )}
        </div>
      </div>

      <div
        className={'rs-resize-h' + (active === 'ts' ? ' rs-resize-active' : '')}
        onPointerDown={bindTsGutter}
        title="Drag to resize Tailscale vs lower panels"
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize Tailscale panel height"
      />

      <div className="rs-stack">
        <div className="rs-spotify-shell" style={{ height: sizes.spH, flexShrink: 0 }}>
          <SpotifyPanel spotify={spotify} onUpdate={onSpotifyUpdate} />
        </div>

        <div
          className={'rs-resize-h' + (active === 'sp' ? ' rs-resize-active' : '')}
          onPointerDown={bindSpGutter}
          title="Drag to resize Spotify vs Concepts"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize Spotify panel height"
        />

        <div id="concepts-panel">
          <div className="sb-header">Concepts</div>
          <div id="concepts-list">
            {conceptList.length === 0 ? (
              <div style={{ padding: '10px 12px', fontSize: '10px', color: 'var(--border)' }}>
                No concepts yet
              </div>
            ) : (
              conceptList.map((c, i) => (
                <div key={i} className="concept-item">
                  <span className={'concept-badge ' + esc(c.category)}>{esc(c.category)}</span>
                  <span className="concept-text">{esc(c.text)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
