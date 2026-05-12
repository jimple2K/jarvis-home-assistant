import React, { useMemo } from 'react';
import { renderMarkdown } from '../lib/markdown.js';

export default function MarkdownText({ text, className = '' }) {
  const html = useMemo(() => renderMarkdown(text || '').html, [text]);
  if (!text) return null;
  return (
    <div
      className={'md ' + className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
