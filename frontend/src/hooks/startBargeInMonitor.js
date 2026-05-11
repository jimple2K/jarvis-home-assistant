/**
 * Watch microphone level while TTS plays; when the user speaks, call onBarge once.
 * Stops the monitor (releases mic) before you start SpeechRecognition.
 *
 * @param {object} opts
 * @param {string} [opts.micId] deviceId from Settings
 * @param {() => void} opts.onBarge
 * @param {number} [opts.threshold] RMS 0..1
 * @param {number} [opts.framesNeeded] consecutive frames above threshold
 * @returns {() => void} stop — idempotent, releases mic + AudioContext
 */
export function startBargeInMonitor({
  micId,
  onBarge,
  threshold = 0.04,
  framesNeeded = 8,
}) {
  let stopped = false;
  let raf = 0;
  let stream = null;
  let ctx = null;
  let fired = false;

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
      };
      if (micId) audio.deviceId = { exact: micId };
      stream = await navigator.mediaDevices.getUserMedia({ audio });
    } catch {
      return;
    }
    if (stopped) {
      cleanup();
      return;
    }
    try {
      ctx = new AudioContext();
      if (ctx.state === 'suspended') await ctx.resume();
    } catch {
      cleanup();
      return;
    }
    if (stopped) {
      cleanup();
      return;
    }

    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    let streak = 0;

    function tick() {
      if (stopped) return;
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      if (rms >= threshold) {
        streak++;
        if (streak >= framesNeeded && !fired) {
          fired = true;
          onBarge();
        }
      } else {
        streak = Math.max(0, streak - 2);
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
  })();

  return stop;
}
