import React, { useEffect, useMemo, useRef } from 'react';
import CodePanel from './CodePanel.jsx';
import MarkdownText from './MarkdownText.jsx';
import { useAudioReactive } from '../hooks/useAudioReactive.js';

const STATE_LABEL = {
  '':          'Ready',
  listening:   'Listening…',
  thinking:    'Thinking…',
  speaking:    'Speaking…',
};

const STATE_HINT = {
  '':          'Click the orb or press Space to talk',
  listening:   'Speak naturally — Jarvis will reply when you pause',
  thinking:    'Calling tools and composing a response',
  speaking:    'Speak again to interrupt',
};

function timeAgo(ts) {
  if (!ts) return '';
  const ageSec = (Date.now() - ts) / 1000;
  if (ageSec < 5) return 'just now';
  if (ageSec < 60) return `${Math.floor(ageSec)}s ago`;
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)}m ago`;
  return `${Math.floor(ageSec / 3600)}h ago`;
}

// Avoid duplicate rendering: only show the standalone bubble when the
// current reply isn't already represented by the latest history turn.
function showStandaloneReply(txJarvis, history) {
  if (!txJarvis) return false;
  const last = history[history.length - 1];
  if (!last) return true;
  return last.reply !== txJarvis;
}

export default function Center({
  uiState,
  txYou,
  txJarvis,
  history,
  codeBlocks,
  activeTool,
  onOrbClick,
  onClearCode,
  typedDraft,
  onTypedDraftChange,
  onSendTyped,
  typedSendDisabled,
  micId,
}) {
  const transcriptRef = useRef(null);
  const typedId = 'typed-message-body';

  // Drive bar heights from mic when listening. Falls back to CSS-only animation
  // (level=0) so the original keyframes remain visible.
  const level = useAudioReactive(uiState === 'listening', micId);

  // Smoothly scroll transcript to bottom whenever new content arrives.
  useEffect(() => {
    const el = transcriptRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [history.length, txJarvis, txYou]);

  function onTypedKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (!typedSendDisabled) onSendTyped();
    }
  }

  const bars = useMemo(() => Array.from({ length: 9 }), []);
  // Per-bar scale based on mic level.
  function barStyle(i) {
    if (!level) return undefined;
    const phase = (i / 9) * Math.PI * 2;
    const wave = 0.55 + Math.sin(phase + performance.now() / 220) * 0.18;
    const scale = Math.max(0.3, Math.min(1.4, level * 1.6 * wave + 0.25));
    return { transform: `scaleY(${scale})` };
  }

  return (
    <div id="center">
      <div
        id="orb-wrap"
        onClick={onOrbClick}
        role="button"
        tabIndex={0}
        aria-label={STATE_LABEL[uiState] || 'Ready'}
        title={STATE_HINT[uiState]}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); onOrbClick(); }
        }}
      >
        <div id="orb">
          <svg width="54" height="54" viewBox="0 0 60 60" aria-hidden>
            <defs>
              <linearGradient id="orbJGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#fde68a" />
                <stop offset="45%" stopColor="#f472b6" />
                <stop offset="100%" stopColor="#a78bfa" />
              </linearGradient>
            </defs>
            <text
              x="50%"
              y="55%"
              dominantBaseline="middle"
              textAnchor="middle"
              fontFamily="Inter, Segoe UI, sans-serif"
              fontSize="38"
              fontWeight="700"
              fill="url(#orbJGrad)"
            >
              J
            </text>
          </svg>
        </div>
      </div>

      <div id="wave" aria-hidden>
        {bars.map((_, i) => (
          <div key={i} className="bar" style={barStyle(i)} />
        ))}
      </div>

      <div id="state-label" aria-live="polite">
        {STATE_LABEL[uiState] || 'Ready'}
      </div>

      <div id="transcript" ref={transcriptRef}>
        {history.map((turn) => (
          <div key={turn.id} className="tx-turn">
            {turn.user && (
              <div className={'tx-user' + (turn.userKind === 'typed' ? ' is-typed' : '')}>
                {turn.user}
              </div>
            )}
            {turn.reply && (
              <div className="tx-jarvis">
                <MarkdownText text={turn.reply} />
                <div style={{
                  fontSize: 9.5, color: 'var(--muted-2)',
                  textAlign: 'right', marginTop: 6, letterSpacing: '.5px',
                  textTransform: 'uppercase',
                }}>
                  {timeAgo(turn.ts)}
                </div>
              </div>
            )}
          </div>
        ))}

        <div id="tx-you">{txYou}</div>

        {showStandaloneReply(txJarvis, history) && (
          <div id="tx-jarvis">
            <MarkdownText text={txJarvis} />
          </div>
        )}
      </div>

      <div id="typed-input-panel" aria-label="Type a message for Jarvis">
        <div className="typed-input-head">
          <span className="typed-input-title">
            <span aria-hidden>⌨</span> Type for Jarvis
          </span>
          <span className="typed-input-badge">exact text</span>
        </div>
        <p id="typed-input-hint" className="typed-input-hint">
          For passwords, IPs, API keys, or anything speech might garble — paste or type here.
          Jarvis gets the characters exactly as written.
        </p>
        <textarea
          id={typedId}
          className="typed-input-field"
          rows={3}
          placeholder="Example: SSH host 100.64.0.30 — password is …"
          value={typedDraft}
          onChange={(e) => onTypedDraftChange(e.target.value)}
          onKeyDown={onTypedKeyDown}
          spellCheck={false}
          autoComplete="off"
          aria-describedby="typed-input-hint"
        />
        <div className="typed-input-actions">
          <span className="typed-input-meta">
            <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to send
          </span>
          <button
            type="button"
            className="typed-input-send"
            disabled={typedSendDisabled}
            onClick={onSendTyped}
          >
            Send typed message
          </button>
        </div>
      </div>

      <div id="tool-pill" className={activeTool ? 'on' : ''} aria-live="polite">
        {activeTool ? `⚙ ${activeTool}` : ''}
      </div>

      <CodePanel codeBlocks={codeBlocks} onClear={onClearCode} />
    </div>
  );
}
