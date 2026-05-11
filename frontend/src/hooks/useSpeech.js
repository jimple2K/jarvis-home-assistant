import { useRef } from 'react';

/**
 * useSpeech({ onInterim, onFinal })
 *
 * onInterim(text)            — called with interim transcript text
 * onFinal(text, error)       — called when recognition ends:
 *                              error=null on success
 *                              error='rejected' if empty/too short/low confidence
 *                              error=<SR error string> on recognizer error
 *
 * Returns { start(micId?), abort }
 */
export function useSpeech({ onInterim, onFinal }) {
  const recognitionRef = useRef(null);
  const sessionTextRef = useRef('');
  const finalConfRef   = useRef(0);
  const abortedRef     = useRef(false);

  function abort() {
    abortedRef.current = true;
    if (recognitionRef.current) {
      recognitionRef.current.abort();
      recognitionRef.current = null;
    }
    sessionTextRef.current = '';
    finalConfRef.current   = 0;
  }

  function start(micId) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      onFinal && onFinal('', 'not-supported');
      return;
    }

    abortedRef.current     = false;
    sessionTextRef.current = '';
    finalConfRef.current   = 0;

    const rec = new SR();
    recognitionRef.current = rec;

    rec.continuous      = false;
    rec.interimResults  = true;
    rec.lang            = 'en-US';

    rec.onstart = () => {
      sessionTextRef.current = '';
      finalConfRef.current   = 0;
      if (onInterim) onInterim('');
    };

    rec.onresult = (e) => {
      let interim = '';
      let final   = '';
      let maxConf = 0;

      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
          if (result[0].confidence > maxConf) maxConf = result[0].confidence;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final) {
        sessionTextRef.current = final;
        finalConfRef.current   = maxConf;
      } else {
        sessionTextRef.current = interim;
      }

      if (onInterim) onInterim(sessionTextRef.current.trim());
    };

    rec.onerror = (e) => {
      if (abortedRef.current) return;
      const errType = e.error || 'error';
      sessionTextRef.current = '';
      finalConfRef.current   = 0;
      recognitionRef.current = null;
      // Mark as aborted so the followup onend() doesn't fire a second onFinal
      // and clobber the real error with a silent "rejected".
      abortedRef.current = true;
      if (onFinal) onFinal('', errType);
    };

    rec.onend = () => {
      if (abortedRef.current) return;
      recognitionRef.current = null;

      const text  = sessionTextRef.current.trim();
      const conf  = finalConfRef.current;
      sessionTextRef.current = '';
      finalConfRef.current   = 0;

      const words = text.split(/\s+/).filter(Boolean).length;

      // Reject: empty, single-word noise, or low confidence
      if (!text || words < 2 || (conf > 0 && conf < 0.50)) {
        if (onFinal) onFinal(text, 'rejected');
        return;
      }

      if (onFinal) onFinal(text, null);
    };

    // Start with optional mic constraint
    if (micId) {
      navigator.mediaDevices
        .getUserMedia({ audio: { deviceId: { exact: micId } } })
        .then(() => rec.start())
        .catch(() => rec.start());
    } else {
      rec.start();
    }
  }

  return { start, abort };
}
