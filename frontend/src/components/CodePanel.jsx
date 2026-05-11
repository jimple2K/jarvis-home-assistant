import React, { useState } from 'react';

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function CodeBlock({ block, index }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(block.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="code-block">
      <div className="code-block-toolbar">
        <span className="code-lang">{esc(block.lang)}</span>
        <button
          className={'copy-btn' + (copied ? ' copied' : '')}
          onClick={handleCopy}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre>{block.code}</pre>
    </div>
  );
}

export default function CodePanel({ codeBlocks, onClear }) {
  const hasCode = codeBlocks && codeBlocks.length > 0;

  return (
    <div id="code-panel" className={hasCode ? 'has-code' : 'is-empty'}>
      <div id="code-panel-header">
        <span>Code</span>
        {hasCode && (
          <button onClick={onClear} title="Clear">&#x2715;</button>
        )}
      </div>
      {hasCode ? (
        <div id="code-blocks">
          {codeBlocks.map((block, i) => (
            <CodeBlock key={i} block={block} index={i} />
          ))}
        </div>
      ) : (
        <div id="code-empty">
          <div className="code-empty-icon">{'<'}/{'>'}</div>
          <div className="code-empty-title">No code yet</div>
          <div className="code-empty-sub">Ask Jarvis to write code and it'll appear here with a copy button.</div>
        </div>
      )}
    </div>
  );
}
