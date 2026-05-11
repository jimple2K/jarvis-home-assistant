import React, { useState, useEffect } from 'react';
import { getSpotifyCurrent } from '../api.js';

export default function TopBar({ apiOnline, alwaysOn, onToggleAlwaysOn, onNewChat, onOpenSettings, onOpenRaceHub }) {
  const [nowPlaying, setNowPlaying] = useState(null);

  useEffect(() => {
    function fetchNowPlaying() {
      getSpotifyCurrent()
        .then(d => setNowPlaying(d.running ? d : null))
        .catch(() => setNowPlaying(null));
    }
    fetchNowPlaying();
    const t = setInterval(fetchNowPlaying, 5000);
    return () => clearInterval(t);
  }, []);

  const isPlaying = nowPlaying?.status === 'Playing';
  const hasSong   = nowPlaying?.title;

  return (
    <div id="topbar">
      <span className="logo">J A R V I S</span>
      <div
        id="api-dot"
        className={apiOnline === true ? 'online' : apiOnline === false ? 'offline' : ''}
        title="LM Studio connection"
      />

      {hasSong && (
        <div className={'now-playing' + (isPlaying ? ' playing' : '')}>
          <span className="np-icon">{isPlaying ? '♫' : '⏸'}</span>
          <span className="np-text">
            <span className="np-title">{nowPlaying.title}</span>
            {nowPlaying.artist && (
              <span className="np-artist"> · {nowPlaying.artist}</span>
            )}
          </span>
        </div>
      )}

      <button
        className={'tbtn' + (alwaysOn ? ' active' : '')}
        onClick={onToggleAlwaysOn}
      >
        &#x27F3; Always On
      </button>
      <button className="tbtn" onClick={onNewChat}>New Chat</button>
      <button className="tbtn" onClick={onOpenRaceHub} title="Racing & media ops hub">&#9201; Racing</button>
      <button className="tbtn" onClick={onOpenSettings}>&#9881; Settings</button>
    </div>
  );
}
