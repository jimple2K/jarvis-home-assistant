import React, { useRef } from 'react';
import CodePanel from './CodePanel.jsx';

export default function Center({ txYou, txJarvis, codeBlocks, onOrbClick, onClearCode }) {
  const toolRef = useRef(null);

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

      <div id="tool-pill" ref={toolRef} />

      <CodePanel codeBlocks={codeBlocks} onClear={onClearCode} />
    </div>
  );
}
