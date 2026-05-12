import React from 'react';

function initialOf(name) {
  if (!name) return '♫';
  const ch = String(name).trim()[0];
  return (ch || '♫').toUpperCase();
}

export default function TopBar({
  apiOnline,
  alwaysOn,
  spotify,
  onToggleAlwaysOn,
  onNewChat,
  onOpenSettings,
  onOpenRaceHub,
  onOpenHelp,
}) {
  const isPlaying = spotify?.status === 'Playing';
  const hasSong = spotify?.running && spotify?.title;

  const apiTitle = apiOnline === true
    ? 'LM Studio: online'
    : apiOnline === false
    ? 'LM Studio: offline — check Settings → LM Studio'
    : 'LM Studio: status unknown';

  return (
    <div id="topbar" role="banner">
      <span className="logo" aria-label="Jarvis">JARVIS</span>

      <div
        id="api-dot"
        className={apiOnline === true ? 'online' : apiOnline === false ? 'offline' : ''}
        title={apiTitle}
        role="status"
        aria-label={apiTitle}
      />

      {hasSong && (
        <div
          className={'now-playing' + (isPlaying ? ' playing' : '')}
          title={`${spotify.title}${spotify.artist ? ' — ' + spotify.artist : ''}`}
        >
          <span className="np-art" aria-hidden>{isPlaying ? '♫' : '⏸'}</span>
          <span className="np-text">
            <span className="np-title">{spotify.title}</span>
            {spotify.artist && <span className="np-artist"> · {spotify.artist}</span>}
          </span>
        </div>
      )}

      <button
        className={'tbtn' + (alwaysOn ? ' active' : '')}
        onClick={onToggleAlwaysOn}
        aria-pressed={alwaysOn}
        title="Continuous listening (Ctrl+/)"
      >
        <span className="tbtn-icon" aria-hidden>⟳</span>
        Always On
      </button>
      <button className="tbtn" onClick={onNewChat} title="Start a fresh conversation (Ctrl+L)">
        <span className="tbtn-icon" aria-hidden>＋</span>
        New Chat
      </button>
      <button className="tbtn" onClick={onOpenRaceHub} title="Racing & media ops hub (G then R)">
        <span className="tbtn-icon" aria-hidden>⏱</span>
        Racing
      </button>
      <button className="tbtn" onClick={onOpenSettings} title="Settings (G then S)">
        <span className="tbtn-icon" aria-hidden>⚙</span>
        Settings
      </button>
      <button className="tbtn" onClick={onOpenHelp} title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts">
        <span className="tbtn-icon" aria-hidden>?</span>
      </button>
    </div>
  );
}
