import { useEffect, useRef } from 'react';

/**
 * usePolling — runs `fn` every `intervalMs` while visible.
 * Pauses when the document is hidden (Page Visibility API) and resumes when shown.
 * `fn` is called once immediately. Errors are swallowed so a flaky endpoint
 * doesn't crash the loop.
 */
export function usePolling(fn, intervalMs, deps = []) {
  const saved = useRef(fn);
  saved.current = fn;

  useEffect(() => {
    let stopped = false;
    let timer = null;

    async function tick() {
      if (stopped) return;
      try { await saved.current(); } catch {}
      if (stopped) return;
      timer = setTimeout(tick, intervalMs);
    }

    function onVisibility() {
      if (document.hidden) {
        if (timer) { clearTimeout(timer); timer = null; }
      } else {
        if (!timer) tick();
      }
    }

    document.addEventListener('visibilitychange', onVisibility);
    tick();

    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}
