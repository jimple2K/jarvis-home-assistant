import { useEffect, useRef, useState } from 'react';

/**
 * useAudioReactive — exposes a smoothed RMS level [0..1] from the user's
 * default mic while `active` is true. Cleans up the AudioContext + stream
 * when toggled off. Designed to drive the listening waveform.
 *
 * It does NOT compete with the SpeechRecognition stream — we get our own
 * MediaStream and analyser. Chrome happily shares the input device.
 */
export function useAudioReactive(active, micId) {
  const [level, setLevel] = useState(0);
  const rafRef = useRef(0);
  const streamRef = useRef(null);
  const ctxRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      if (!active) return;
      try {
        const constraints = { audio: micId ? { deviceId: { exact: micId } } : true };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        streamRef.current = stream;
        const Ctx = window.AudioContext || window.webkitAudioContext;
        const ctx = new Ctx();
        ctxRef.current = ctx;
        if (ctx.state === 'suspended') await ctx.resume();
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.7;
        src.connect(analyser);
        const buf = new Float32Array(analyser.fftSize);

        let smooth = 0;
        function tick() {
          if (cancelled) return;
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
          const rms = Math.sqrt(sum / buf.length);
          // Normalise — empirical: speech RMS around 0.05–0.25.
          const norm = Math.min(1, rms / 0.25);
          smooth = smooth * 0.78 + norm * 0.22;
          setLevel(smooth);
          rafRef.current = requestAnimationFrame(tick);
        }
        rafRef.current = requestAnimationFrame(tick);
      } catch {
        // Mic permission denied — fall back to CSS-only animation.
      }
    }
    start();
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch {}
      streamRef.current = null;
      try { ctxRef.current?.close(); } catch {}
      ctxRef.current = null;
      setLevel(0);
    };
  }, [active, micId]);

  return level;
}
