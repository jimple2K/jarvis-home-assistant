import React, { useMemo, useState } from 'react';
import { highlightCode } from '../lib/highlight.js';
import { toast } from '../lib/toast.js';

function CodeBlock({ block }) {
  const [copied, setCopied] = useState(false);

  const html = useMemo(
    () => highlightCode(block.code || '', (block.lang || '').toLowerCase()),
    [block.code, block.lang],
  );

  const lines = useMemo(() => {
    const text = String(block.code || '').replace(/\n$/, '');
    return text.length === 0 ? 1 : text.split('\n').length;
  }, [block.code]);

  function handleCopy() {
    const t = block.code || '';
    if (!navigator.clipboard) return;
    navigator.clipboard
      .writeText(t)
      .then(() => {
        setCopied(true);
        toast.success(`Copied ${t.length} character${t.length === 1 ? '' : 's'} to clipboard.`, 'Code');
        setTimeout(() => setCopied(false), 1800);
      })
      .catch(() => {
        toast.error('Clipboard write failed.', 'Copy');
      });
  }

  return (
    <div className="code-block">
      <div className="code-block-toolbar">
        <span className="code-lang">{block.lang || 'text'}</span>
        <button
          className={'copy-btn' + (copied ? ' copied' : '')}
          onClick={handleCopy}
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre>
        <span
          className="hl-root"
          // Highlight is pre-escaped HTML.
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
      <div style={{
        textAlign: 'right',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--muted-2)',
        padding: '2px 14px 6px',
      }}>
        {lines} line{lines === 1 ? '' : 's'}
      </div>
    </div>
  );
}

export default function CodePanel({ codeBlocks, onClear }) {
  const hasCode = codeBlocks && codeBlocks.length > 0;

  return (
    <div id="code-panel" className={hasCode ? 'has-code' : 'is-empty'}>
      <div id="code-panel-header">
        <span>
          <span aria-hidden>›_</span> Code
          {hasCode && (
            <span style={{
              marginLeft: 6, color: 'var(--muted-2)',
              fontWeight: 500, letterSpacing: 0,
              textTransform: 'none', fontSize: 10,
            }}>
              · {codeBlocks.length} block{codeBlocks.length === 1 ? '' : 's'}
            </span>
          )}
        </span>
        {hasCode && (
          <button onClick={onClear} title="Clear code" aria-label="Clear code panel">✕</button>
        )}
      </div>
      {hasCode ? (
        <div id="code-blocks">
          {codeBlocks.map((block, i) => (
            <CodeBlock key={i} block={block} />
          ))}
        </div>
      ) : (
        <div id="code-empty">
          <div className="code-empty-icon">{'</>'}</div>
          <div className="code-empty-title">No code yet</div>
          <div className="code-empty-sub">
            Ask Jarvis to write code and it'll appear here with syntax highlighting and a copy button.
          </div>
        </div>
      )}
    </div>
  );
}
