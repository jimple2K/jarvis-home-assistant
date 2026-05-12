// Lightweight, dependency-free Markdown renderer for Jarvis replies.
// Supports: headings, paragraphs, bold/italic, inline code, links,
// fenced + indented code blocks, unordered & ordered lists, blockquotes, hr.
// Output is sanitised HTML — all raw HTML in input is escaped first.
//
// Returned shape: { html, codeBlocks } so the caller can show code panels too.
import { highlightCode } from './highlight.js';

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderInline(text) {
  // Already escaped before this. Apply inline transforms in a safe order.
  // 1) Inline code (don't allow nested formatting inside)
  let out = text.replace(/`([^`\n]+?)`/g, (_, code) => `<code>${code}</code>`);
  // 2) Links [label](url) — only http(s)://, mailto:, /relative
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => {
    const safeUrl = /^(https?:\/\/|mailto:|\/)/.test(url) ? url : '#';
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  // 3) Bold + italic
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  out = out.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
  // 4) Strike
  out = out.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  return out;
}

export function renderMarkdown(input) {
  const codeBlocks = [];
  if (!input) return { html: '', codeBlocks };
  const src = String(input).replace(/\r\n/g, '\n');

  // First, extract fenced code blocks so they don't get processed line-by-line.
  const slots = [];
  let withoutFences = src.replace(/```([^\n`]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = slots.length;
    const language = (lang || '').trim().toLowerCase();
    const raw = code.replace(/\n$/, '');
    codeBlocks.push({ lang: language || 'text', code: raw });
    const highlighted = highlightCode(raw, language);
    const pill = language
      ? `<span class="md-code-lang">${escapeHtml(language)}</span>`
      : '';
    slots.push(`<pre class="md-codeblock">${pill}<code class="hl-root">${highlighted}</code></pre>`);
    return `\u0000FENCE${idx}\u0000`;
  });

  // Escape everything else.
  withoutFences = escapeHtml(withoutFences);

  // Split into block-level lines.
  const lines = withoutFences.split('\n');
  const out = [];
  let i = 0;

  function isBlank(s) { return /^\s*$/.test(s); }

  while (i < lines.length) {
    const line = lines[i];

    // Slot placeholder for code block — pass through.
    const slotMatch = line.match(/^\u0000FENCE(\d+)\u0000$/);
    if (slotMatch) {
      out.push(slots[Number(slotMatch[1])]);
      i++;
      continue;
    }

    // Horizontal rule
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      out.push('<hr />');
      i++;
      continue;
    }

    // Heading
    const heading = line.match(/^(#{1,6})\s+(.+?)\s*$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i++;
      continue;
    }

    // Blockquote (consecutive lines starting with > )
    if (/^&gt;\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^&gt;\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^&gt;\s?/, ''));
        i++;
      }
      out.push(`<blockquote>${renderInline(buf.join(' '))}</blockquote>`);
      continue;
    }

    // Unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*[-*+]\s+/, ''));
        i++;
      }
      out.push('<ul>' + buf.map(b => `<li>${renderInline(b)}</li>`).join('') + '</ul>');
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push('<ol>' + buf.map(b => `<li>${renderInline(b)}</li>`).join('') + '</ol>');
      continue;
    }

    // Blank line
    if (isBlank(line)) { i++; continue; }

    // Paragraph (consume contiguous non-blank, non-block lines)
    const buf = [line];
    i++;
    while (i < lines.length && !isBlank(lines[i])
      && !/^(#{1,6})\s+/.test(lines[i])
      && !/^&gt;\s?/.test(lines[i])
      && !/^\s*[-*+]\s+/.test(lines[i])
      && !/^\s*\d+\.\s+/.test(lines[i])
      && !/^\s*(---|\*\*\*|___)\s*$/.test(lines[i])
      && !/^\u0000FENCE\d+\u0000$/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i++;
    }
    out.push(`<p>${renderInline(buf.join(' '))}</p>`);
  }

  return { html: out.join('\n'), codeBlocks };
}
