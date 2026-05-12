// Tiny global toast store using a pub/sub pattern.
// Components subscribe via `useToasts` and dispatch via `toast.<kind>(msg)`.

let nextId = 1;
let state = [];
const listeners = new Set();

function emit() {
  listeners.forEach((l) => l(state));
}

function add(kind, message, title, durationMs) {
  const id = nextId++;
  const item = {
    id,
    kind,
    title: title || '',
    message: message || '',
    leaving: false,
  };
  state = [...state, item];
  emit();
  const ttl = durationMs ?? (kind === 'error' ? 6000 : 3500);
  setTimeout(() => dismiss(id), ttl);
  return id;
}

export function dismiss(id) {
  state = state.map((t) => (t.id === id ? { ...t, leaving: true } : t));
  emit();
  setTimeout(() => {
    state = state.filter((t) => t.id !== id);
    emit();
  }, 220);
}

export const toast = {
  info:    (message, title, ms) => add('info',    message, title, ms),
  success: (message, title, ms) => add('success', message, title, ms),
  warn:    (message, title, ms) => add('warn',    message, title, ms),
  error:   (message, title, ms) => add('error',   message, title, ms),
  dismiss,
};

export function subscribe(fn) {
  listeners.add(fn);
  fn(state);
  return () => listeners.delete(fn);
}
