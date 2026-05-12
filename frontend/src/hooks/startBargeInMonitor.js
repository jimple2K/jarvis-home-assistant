/**
 * Adaptive barge-in monitor.
 *
 * Opens the mic (with echoCancellation + noiseSuppression) and watches RMS
 * loudness while Jarvis is speaking. Differs from a naive threshold:
 *
 *   1. A short *learn* window (default 400 ms) measures the background +
 *      TTS-echo floor — anything ≤ that floor is treated as "Jarvis's own
 *      voice leaking back through the mic".
 *   2. After the learn window, fires `onBarge()` once when the user's RMS
 *      stays at ≥ `floor × ratio` AND ≥ `absMin` for `framesNeeded` frames.
 *   3. Cleanly releases the stream + AudioContext on stop().
 *
 * @param {object} opts
 * @param {string} [opts.micId]
 * @param {() => void} opts.onBarge
 * @param {number} [opts.learnMs]
 * @param {number} [opts.absMin]
 * @param {number} [opts.ratio]
 * @param {number} [opts.framesNeeded]
 * @returns {() => void} stop
 */
export function startBargeInMonitor({
  micId,
  onBarge,
  learnMs = 400,
  absMin = 0.035,
  ratio = 2.0,
  framesNeeded = 4,
}) {
  let stopped = false;
  let raf = 0;
  let stream = null;
  let ctx = null;
  let fired = false;
  const t0 = performance.now();
  let floor = absMin;
  let learnSum = 0;
  let learnCount = 0;
  let streak = 0;

  function cleanup() {
    cancelAnimationFrame(raf);
    raf = 0;
    try {
      stream?.getTracks().forEach((t) => t.stop());
    } catch {}
    stream = null;
    try {
      ctx?.close();
    } catch {}
    ctx = null;
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    cleanup();
  }

  (async () => {
    try {
      const audio = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      };
      if (micId) audio.deviceId = { exact: micId };
      stream = await navigator.mediaDevices.getUserMedia({ audio });
    } catch {
      return;
    }
    if (stopped) { cleanup(); return; }
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') await ctx.resume();
    } catch {
      cleanup();
      return;
    }
    if (stopped) { cleanup(); return; }

    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.4;
    src.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    function tick() {
      if (stopped) return;
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const elapsed = performance.now() - t0;

      if (elapsed < learnMs) {
        learnSum += rms;
        learnCount += 1;
        raf = requestAnimationFrame(tick);
        return;
      }
      if (learnCount > 0 && floor === absMin) {
        // Snapshot floor once the learn window ends — keep it ≥ absMin.
        const learned = learnSum / learnCount;
        floor = Math.max(absMin, learned * 1.4);
      }

      const trigger = rms >= floor * ratio && rms >= absMin;
      if (trigger) {
        streak += 1;
        if (streak >= framesNeeded && !fired) {
          fired = true;
          try { onBarge(); } catch {}
        }
      } else {
        streak = Math.max(0, streak - 1);
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
  })();

  return stop;
}
