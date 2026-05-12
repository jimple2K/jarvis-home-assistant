// Tiny, dependency-free syntax highlighter.
// Supports approximate highlighting for the languages Jarvis is most likely
// to emit: bash, javascript/typescript, python, json, sql, html, css.
// The grammar is intentionally minimal — token order is tuned to avoid
// false matches (strings/comments first, then keywords, numbers, etc).

const KEYWORDS = {
  python: ['def','class','if','elif','else','return','import','from','as','for','while','in','not','and','or','is','None','True','False','try','except','finally','with','lambda','yield','pass','break','continue','raise','global','nonlocal','async','await'],
  javascript: ['var','let','const','function','return','if','else','for','while','do','switch','case','break','continue','default','class','extends','super','this','new','delete','typeof','instanceof','in','of','null','undefined','true','false','async','await','import','export','from','as','try','catch','finally','throw','yield','void'],
  typescript: ['var','let','const','function','return','if','else','for','while','do','switch','case','break','continue','default','class','extends','super','this','new','delete','typeof','instanceof','in','of','null','undefined','true','false','async','await','import','export','from','as','try','catch','finally','throw','yield','void','interface','type','enum','public','private','protected','readonly','implements','namespace'],
  bash: ['if','then','else','elif','fi','for','do','done','while','until','case','esac','function','return','in','do','export','local','readonly','source','alias','unalias','set','unset','exit','true','false','test'],
  sql: ['select','from','where','and','or','not','in','is','null','as','join','left','right','inner','outer','on','group','by','order','having','limit','offset','insert','into','values','update','set','delete','create','table','drop','alter','add','column','primary','key','foreign','references','distinct','count','sum','avg','min','max','case','when','then','else','end','if','exists','with','union','all'],
  json: ['true','false','null'],
  css: [],
  html: [],
  text: [],
};

const ALIASES = {
  js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  py: 'python',
  sh: 'bash', shell: 'bash', zsh: 'bash',
  yml: 'json', yaml: 'json',
};

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function tokenize(code, lang) {
  const norm = ALIASES[lang] || lang || 'text';
  const kws = KEYWORDS[norm] || [];
  const out = [];
  let i = 0;
  const n = code.length;

  const isKwChar = (c) => /[A-Za-z0-9_$]/.test(c);

  // Build keyword regex once.
  const kwSet = new Set(kws);

  while (i < n) {
    const c = code[i];

    // Line comments: // or # (shell/python) or -- (sql)
    if (
      (norm === 'javascript' || norm === 'typescript' || norm === 'css') && c === '/' && code[i + 1] === '/' ||
      (norm === 'python' || norm === 'bash') && c === '#' ||
      (norm === 'sql') && c === '-' && code[i + 1] === '-'
    ) {
      let j = i;
      while (j < n && code[j] !== '\n') j++;
      out.push({ kind: 'com', text: code.slice(i, j) });
      i = j;
      continue;
    }

    // Block comments /* ... */
    if ((norm === 'javascript' || norm === 'typescript' || norm === 'css')
        && c === '/' && code[i + 1] === '*') {
      let j = i + 2;
      while (j < n && !(code[j] === '*' && code[j + 1] === '/')) j++;
      out.push({ kind: 'com', text: code.slice(i, Math.min(n, j + 2)) });
      i = j + 2;
      continue;
    }

    // Strings — single, double, backtick
    if (c === '"' || c === "'" || c === '`') {
      const quote = c;
      let j = i + 1;
      while (j < n) {
        if (code[j] === '\\') { j += 2; continue; }
        if (code[j] === quote) { j++; break; }
        if (quote !== '`' && code[j] === '\n') break;
        j++;
      }
      out.push({ kind: 'str', text: code.slice(i, j) });
      i = j;
      continue;
    }

    // Numbers
    if (/[0-9]/.test(c) && !isKwChar(code[i - 1] || ' ')) {
      let j = i;
      while (j < n && /[0-9._xXa-fA-F]/.test(code[j])) j++;
      out.push({ kind: 'num', text: code.slice(i, j) });
      i = j;
      continue;
    }

    // Identifier / keyword
    if (/[A-Za-z_$]/.test(c)) {
      let j = i;
      while (j < n && isKwChar(code[j])) j++;
      const word = code.slice(i, j);
      const isKw = kwSet.has(norm === 'sql' ? word.toLowerCase() : word);
      // Function call detection (next non-space char is '(')
      let k = j;
      while (k < n && /[ \t]/.test(code[k])) k++;
      const isCall = code[k] === '(';
      if (isKw) out.push({ kind: 'kw', text: word });
      else if (isCall) out.push({ kind: 'fn', text: word });
      else if (/^[A-Z]/.test(word)) out.push({ kind: 'typ', text: word });
      else out.push({ kind: 't', text: word });
      i = j;
      continue;
    }

    // Operators / punctuation
    if (/[=+\-*/%<>!&|^~?:]/.test(c)) {
      out.push({ kind: 'op', text: c });
      i++;
      continue;
    }

    out.push({ kind: 't', text: c });
    i++;
  }
  return out;
}

export function highlightCode(code, lang) {
  if (!code) return '';
  try {
    const toks = tokenize(code, (lang || '').toLowerCase());
    return toks
      .map((t) => {
        const safe = esc(t.text);
        switch (t.kind) {
          case 'kw':  return `<span class="hl-kw">${safe}</span>`;
          case 'str': return `<span class="hl-str">${safe}</span>`;
          case 'num': return `<span class="hl-num">${safe}</span>`;
          case 'com': return `<span class="hl-com">${safe}</span>`;
          case 'fn':  return `<span class="hl-fn">${safe}</span>`;
          case 'op':  return `<span class="hl-op">${safe}</span>`;
          case 'typ': return `<span class="hl-typ">${safe}</span>`;
          default:    return safe;
        }
      })
      .join('');
  } catch {
    return esc(code);
  }
}
