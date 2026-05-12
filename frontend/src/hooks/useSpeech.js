import { useRef } from 'react';

/**
 * useSpeech({ onInterim, onFinal, endpointMs })
 *
 * Continuous, low-latency speech with manual endpointing.
 *
 * • Keeps ONE SpeechRecognition session alive across utterances.
 * • Emits onInterim(text) as the user speaks (interim + accumulated finals).
 * • Emits onFinal(text, null) when the user goes silent for `endpointMs`
 *   (default 650 ms) — far faster than Chrome's built-in 1.5–2 s pause.
 * • Auto-restarts the recognizer if Chrome's 30 s timer ends the session
 *   so listening never goes "cold" while always-on.
 * • Accepts short commands ("yes", "stop", "go", "next" …) instead of
 *   silently rejecting them.
 *
 * Return: { start(micId?), abort, isActive() }
 */

const SHORT_OK_RE =
  /^(stop|wait|hold on|cancel|nevermind|never mind|yes|yeah|yep|nope|no|ok|okay|sure|go|continue|repeat|again|next|previous|back|pause|resume|play|quiet|silence|enough|done|cool|nice|right|left|up|down|louder|softer|mute|unmute|help)$/i;

export function useSpeech({ onInterim, onFinal, endpointMs = 650 }) {
  const recRef = useRef(null);
  const aliveRef = useRef(false);
  const stoppingRef = useRef(false);
  const pendingTextRef = useRef('');
  const pendingConfRef = useRef(0);
  const silenceTimerRef = useRef(null);
  const lastMicIdRef = useRef('');

  function clearSilenceTimer() {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }

  function armSilenceTimer() {
    clearSilenceTimer();
    silenceTimerRef.current = setTimeout(commitNow, endpointMs);
  }

  function commitNow() {
    clearSilenceTimer();
    const text = pendingTextRef.current.trim();
    const conf = pendingConfRef.current;
    pendingTextRef.current = '';
    pendingConfRef.current = 0;
    if (!text) return;

    const words = text.split(/\s+/).filter(Boolean);
    const accepted =
      words.length >= 2 ||
      SHORT_OK_RE.test(text) ||
      conf >= 0.6;

    if (accepted) {
      if (onFinal) onFinal(text, null);
    } else {
      if (onInterim) onInterim('');
      if (onFinal) onFinal(text, 'rejected');
    }
  }

  function abort() {
    stoppingRef.current = true;
    aliveRef.current = false;
    clearSilenceTimer();
    pendingTextRef.current = '';
    pendingConfRef.current = 0;
    if (recRef.current) {
      try {
        recRef.current.onresult = null;
        recRef.current.onerror = null;
        recRef.current.onend = null;
        recRef.current.abort();
      } catch {}
      recRef.current = null;
    }
  }

  function attach(micId) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      onFinal && onFinal('', 'not-supported');
      return;
    }

    const rec = new SR();
    recRef.current = rec;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-US';
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      if (onInterim) onInterim(pendingTextRef.current);
    };

    rec.onresult = (e) => {
      let interim = '';
      let finalSeg = '';
      let maxConf = 0;
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          finalSeg += r[0].transcript;
          if (r[0].confidence > maxConf) maxConf = r[0].confidence;
        } else {
          interim += r[0].transcript;
        }
      }
      if (finalSeg) {
        pendingTextRef.current =
          (pendingTextRef.current ? pendingTextRef.current + ' ' : '') +
          finalSeg.trim();
        if (maxConf > pendingConfRef.current) pendingConfRef.current = maxConf;
      }
      const display = (pendingTextRef.current + ' ' + interim).trim();
      if (onInterim) onInterim(display);
      armSilenceTimer();
    };

    rec.onerror = (e) => {
      const err = e.error || 'error';
      if (err === 'no-speech') {
        // Recoverable: Chrome will fire onend right after. Just let auto-restart handle it.
        return;
      }
      if (stoppingRef.current) return;
      aliveRef.current = false;
      clearSilenceTimer();
      if (onFinal) onFinal('', err);
    };

    rec.onend = () => {
      if (stoppingRef.current) {
        aliveRef.current = false;
        recRef.current = null;
        return;
      }
      // Commit anything still pending (e.g. Chrome auto-stops after ~30 s).
      if (pendingTextRef.current.trim()) commitNow();
      recRef.current = null;
      // Seamless restart — no perceived gap.
      setTimeout(() => {
        if (stoppingRef.current) {
          aliveRef.current = false;
          return;
        }
        try {
          attach(micId);
          recRef.current && recRef.current.start();
        } catch {
          aliveRef.current = false;
        }
      }, 30);
    };

    return rec;
  }

  function start(micId) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      onFinal && onFinal('', 'not-supported');
      return;
    }
    if (aliveRef.current) return; // already listening
    stoppingRef.current = false;
    aliveRef.current = true;
    pendingTextRef.current = '';
    pendingConfRef.current = 0;
    lastMicIdRef.current = micId || '';

    const rec = attach(micId);
    if (!rec) return;

    const launch = () => {
      try {
        rec.start();
      } catch {
        // Chrome occasionally throws "already started"; ignore.
      }
    };
    if (micId) {
      navigator.mediaDevices
        .getUserMedia({ audio: { deviceId: { exact: micId } } })
        .then(launch)
        .catch(launch);
    } else {
      launch();
    }
  }

  return { start, abort, isActive: () => aliveRef.current };
}
