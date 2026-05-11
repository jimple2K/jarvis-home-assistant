import React, { useState } from 'react';
import { spotifyPlayPause, spotifyNext, spotifyPrevious } from '../api.js';

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export default function SpotifyPanel({ spotify, onUpdate }) {
  const [busy, setBusy] = useState(false);

  const running = !!spotify?.running;
  const title   = spotify?.title  || '';
  const artist  = spotify?.artist || '';
  const status  = spotify?.status || '';
  const playing = status === 'Playing';

  async function wrap(fn) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fn();
      if (res?.now && onUpdate) onUpdate(res.now);
    } catch {} finally {
      setBusy(false);
    }
  }

  return (
    <div id="spotify-panel">
      <div className="sb-header">
        <span>Spotify</span>
        <span className={'sp-dot ' + (running ? (playing ? 'on' : 'paused') : 'off')} />
      </div>

      <div className="sp-now">
        {running ? (
          <>
            <div className="sp-title" title={title}>{esc(title) || '—'}</div>
            <div className="sp-artist" title={artist}>{esc(artist) || '—'}</div>
            <div className="sp-status">{esc(status) || 'idle'}</div>
          </>
        ) : (
          <div className="sp-offline">Spotify not running</div>
        )}
      </div>

      <div className="sp-controls">
        <button
          className="sp-btn"
          title="Previous"
          disabled={!running || busy}
          onClick={() => wrap(spotifyPrevious)}
        >⏮</button>
        <button
          className="sp-btn sp-play"
          title={playing ? 'Pause' : 'Play'}
          disabled={!running || busy}
          onClick={() => wrap(spotifyPlayPause)}
        >{playing ? '⏸' : '▶'}</button>
        <button
          className="sp-btn"
          title="Next"
          disabled={!running || busy}
          onClick={() => wrap(spotifyNext)}
        >⏭</button>
      </div>
    </div>
  );
}
