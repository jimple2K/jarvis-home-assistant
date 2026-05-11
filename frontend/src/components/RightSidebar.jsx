import React from 'react';
import SpotifyPanel from './SpotifyPanel.jsx';

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

  return (
    <div id="sidebar-right">
      <div id="ts-panel">
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

      <SpotifyPanel spotify={spotify} onUpdate={onSpotifyUpdate} />

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
  );
}
