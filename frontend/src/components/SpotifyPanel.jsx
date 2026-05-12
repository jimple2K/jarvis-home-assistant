import React, { useState } from 'react';
import { spotifyPlayPause, spotifyNext, spotifyPrevious } from '../api.js';
import { toast } from '../lib/toast.js';

function initialOf(name) {
  if (!name) return '♫';
  const ch = String(name).trim()[0];
  return (ch || '♫').toUpperCase();
}

export default function SpotifyPanel({ spotify, onUpdate }) {
  const [busy, setBusy] = useState(false);

  const running = !!spotify?.running;
  const title   = spotify?.title  || '';
  const artist  = spotify?.artist || '';
  const status  = spotify?.status || '';
  const playing = status === 'Playing';

  async function wrap(fn, opName) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fn();
      if (res?.now && onUpdate) onUpdate(res.now);
    } catch {
      toast.error(`Spotify ${opName || 'control'} failed.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="spotify-panel">
      <div className="sb-header">
        <span>
          Spotify
          <span className={'sp-dot ' + (running ? (playing ? 'on' : 'paused') : 'off')}
                style={{ display: 'inline-block', marginLeft: 8, verticalAlign: 'middle' }} />
        </span>
      </div>

      {running ? (
        <div className={'sp-now' + (playing ? ' playing' : '')}>
          <div className="sp-art" aria-hidden>{initialOf(title)}</div>
          <div className="sp-meta">
            <div className="sp-title" title={title}>{title || '—'}</div>
            <div className="sp-artist" title={artist}>{artist || '—'}</div>
            <div className="sp-status">{status || 'idle'}</div>
          </div>
        </div>
      ) : (
        <div className="sp-offline">Spotify not running</div>
      )}

      <div className="sp-controls">
        <button
          className="sp-btn"
          title="Previous"
          aria-label="Previous track"
          disabled={!running || busy}
          onClick={() => wrap(spotifyPrevious, 'previous')}
        >⏮</button>
        <button
          className="sp-btn sp-play"
          title={playing ? 'Pause' : 'Play'}
          aria-label={playing ? 'Pause' : 'Play'}
          disabled={!running || busy}
          onClick={() => wrap(spotifyPlayPause, 'play/pause')}
        >{playing ? '⏸' : '▶'}</button>
        <button
          className="sp-btn"
          title="Next"
          aria-label="Next track"
          disabled={!running || busy}
          onClick={() => wrap(spotifyNext, 'next')}
        >⏭</button>
      </div>
    </div>
  );
}
