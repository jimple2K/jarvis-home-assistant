import React, { useRef } from 'react';
import CodePanel from './CodePanel.jsx';

export default function Center({
  txYou,
  txJarvis,
  codeBlocks,
  onOrbClick,
  onClearCode,
  typedDraft,
  onTypedDraftChange,
  onSendTyped,
  typedSendDisabled,
}) {
  const toolRef = useRef(null);
  const typedId = 'typed-message-body';

  function onTypedKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (!typedSendDisabled) onSendTyped();
    }
  }

  return (
    <div id="center">
      <div id="orb-wrap" onClick={onOrbClick}>
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
              fontFamily="Segoe UI,sans-serif"
              fontSize="38"
              fontWeight="700"
              fill="url(#orbJGrad)"
            >
              J
            </text>
          </svg>
        </div>
      </div>

      <div id="wave">
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
        <div className="bar" />
      </div>

      <div id="state-label">Ready</div>

      <div id="transcript">
        <div id="tx-you">{txYou}</div>
        <div id="tx-jarvis">{txJarvis}</div>
      </div>

      <div id="typed-input-panel" aria-label="Type a message for Jarvis">
        <div className="typed-input-head">
          <span className="typed-input-title">Type for Jarvis</span>
          <span className="typed-input-badge">exact text</span>
        </div>
        <p id="typed-input-hint" className="typed-input-hint">
          For passwords, IPs, API keys, or anything speech might garble — paste or type here. Jarvis gets the characters
          exactly as written. Ctrl+Enter sends; sending stops voice / TTS if active.
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
          <button type="button" className="typed-input-send" disabled={typedSendDisabled} onClick={onSendTyped}>
            Send typed message
          </button>
        </div>
      </div>

      <div id="tool-pill" ref={toolRef} />

      <CodePanel codeBlocks={codeBlocks} onClear={onClearCode} />
    </div>
  );
}
