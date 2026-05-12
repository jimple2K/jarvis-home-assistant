import React, { useState, useEffect, useRef, useCallback } from 'react';
import TopBar from './components/TopBar.jsx';
import LeftSidebar from './components/LeftSidebar.jsx';
import Center from './components/Center.jsx';
import RightSidebar from './components/RightSidebar.jsx';
import SettingsDrawer from './components/SettingsDrawer.jsx';
import RaceHubDrawer from './components/RaceHubDrawer.jsx';
import ToastHost from './components/ToastHost.jsx';
import ShortcutsOverlay from './components/ShortcutsOverlay.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import { useSpeech } from './hooks/useSpeech.js';
import { usePolling } from './hooks/usePolling.js';
import { startBargeInMonitor } from './hooks/startBargeInMonitor.js';
import { stripCodeFencesForTts } from './lib/stripCodeFencesForTts.js';
import { toast } from './lib/toast.js';
import {
  getConfig,
  getTopics,
  getTailscale,
  getConcepts,
  getSshHosts,
  getSpotifyCurrent,
  sendChat,
  tts,
  ttsStop,
  resetChat,
  ping,
} from './api.js';

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

const MAX_HISTORY = 12;

// True when the TTS_SINK is a personal listening device the mic can't hear
// (Bluetooth headphones, wired headphones via USB, virtual sinks, etc).
// Used to skip the barge-in monitor that would otherwise false-trigger on
// ambient mic noise and cut Jarvis off after a syllable or two.
function isHeadphoneLikeSink(name) {
  const n = (name || '').toLowerCase();
  if (!n) return false;
  return (
    n.startsWith('bluez_') ||
    n.includes('bluetooth') ||
    n.startsWith('bt_') ||
    n.includes('headphone') ||
    n.includes('headset') ||
    n.includes('a2dp') ||
    n.includes('hsp')
  );
}

// Two-key sequence handler — supports e.g. `g s` to open settings.
function useSequenceKey(onSequence) {
  const last = useRef({ key: '', ts: 0 });
  return useCallback((e) => {
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const now = performance.now();
    const k = e.key.toLowerCase();
    if (last.current.key && now - last.current.ts < 900) {
      onSequence(last.current.key + k, e);
      last.current = { key: '', ts: 0 };
      return;
    }
    last.current = { key: k, ts: now };
  }, [onSequence]);
}

export default function App() {
  // ── Core state ─────────────────────────────────────────────────────────────
  const [uiState, setUiStateRaw] = useState('');           // ''|listening|thinking|speaking
  const uiStateRef = useRef('');
  const [alwaysOn, setAlwaysOnRaw] = useState(false);
  const alwaysOnRef = useRef(false);
  const [micId, setMicId] = useState('');
  const micIdRef = useRef('');
  const speakAbortedRef = useRef(false);
  const bargeStopRef = useRef(() => {});

  // ── Transcript / history ───────────────────────────────────────────────────
  const [txYou, setTxYou] = useState('');                  // current interim input
  const [txJarvis, setTxJarvis] = useState('');            // most recent Jarvis reply
  const [history, setHistory] = useState([]);              // [{ id, user, userKind, reply, ts }]
  const [activeTool, setActiveTool] = useState(null);

  // ── Code blocks ────────────────────────────────────────────────────────────
  const [codeBlocks, setCodeBlocks] = useState([]);

  // ── Typed input ────────────────────────────────────────────────────────────
  const [typedDraft, setTypedDraft] = useState('');

  // ── Sidebar data ───────────────────────────────────────────────────────────
  const [topics, setTopics] = useState([]);
  const [tailscale, setTailscale] = useState(null);
  const [concepts, setConcepts] = useState(null);
  const [, setSshHosts] = useState([]);
  const [spotify, setSpotify] = useState(null);

  // ── Top bar ────────────────────────────────────────────────────────────────
  const [apiOnline, setApiOnline] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [raceHubOpen, setRaceHubOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [config, setConfig] = useState(null);

  // ── State helpers (React-driven, no DOM manipulation) ──────────────────────
  const setUiState = useCallback((s) => {
    uiStateRef.current = s;
    setUiStateRaw(s);
  }, []);

  // Reflect state class on body so existing CSS animations keep working.
  useEffect(() => {
    document.body.className = uiState || '';
  }, [uiState]);

  function isBusy() { return uiStateRef.current !== ''; }

  function setAlwaysOn(val) {
    alwaysOnRef.current = val;
    setAlwaysOnRaw(val);
  }

  function setMicIdState(val) {
    micIdRef.current = val;
    setMicId(val);
  }

  // ── Speech hook ────────────────────────────────────────────────────────────
  function speechErrorMessage(code) {
    switch (code) {
      case 'not-supported':          return 'Speech recognition not supported in this browser. Use Chrome.';
      case 'not-allowed':            return 'Mic permission denied — click 🔒 in the address bar and allow Microphone.';
      case 'service-not-allowed':    return 'Chrome blocked the speech service. Check chrome://settings/content/microphone.';
      case 'network':                return 'Speech recognition needs internet — Chrome routes SR to Google. Check your connection.';
      case 'audio-capture':          return 'No microphone detected. Plug one in or pick a different device in Settings.';
      case 'aborted':                return 'Speech recognition was aborted.';
      case 'language-not-supported': return 'Language not supported by Chrome speech recognition.';
      default:                       return `Speech error: ${code}`;
    }
  }

  const speech = useSpeech({
    endpointMs: 600,
    onInterim: (text) => {
      if (uiStateRef.current === 'speaking') return;
      setTxYou(text);
    },
    onFinal: useCallback((text, error) => {
      if (uiStateRef.current === 'speaking' && !error) return;

      if (error === 'rejected' || error === 'no-speech') {
        setTxYou('');
        if (!isBusy() || uiStateRef.current === 'listening') {
          setUiState(alwaysOnRef.current ? 'listening' : '');
        }
        return;
      }
      if (error && error !== 'rejected') {
        console.warn('[jarvis] speech recognition error:', error);
        setTxYou('');
        const msg = speechErrorMessage(error);
        toast.error(msg, 'Speech error');
        setTxJarvis(msg);
        setUiState('');
        setTimeout(() => {
          setTxJarvis(prev => (prev === msg ? '' : prev));
        }, 8000);
        if (alwaysOnRef.current && error !== 'not-allowed' && error !== 'not-supported') {
          setTimeout(() => { if (!isBusy()) startListening(); }, 600);
        }
        return;
      }
      if (text) sendToJarvis(text);
    }, [setUiState]),
  });

  // ── Listening control ──────────────────────────────────────────────────────
  function startListening() {
    setTxYou('');
    setUiState('listening');
    if (!speech.isActive()) speech.start(micIdRef.current || undefined);
  }

  function interrupt() {
    bargeStopRef.current();
    bargeStopRef.current = () => {};
    ttsStop();
    speech.abort();
    setUiState('');
    setTxYou('');
  }

  function handleOrbClick() {
    if (isBusy() || uiStateRef.current === 'listening') {
      interrupt();
      return;
    }
    startListening();
  }

  function toggleAlwaysOn() {
    const next = !alwaysOnRef.current;
    setAlwaysOn(next);
    if (next && !isBusy()) startListening();
    if (!next) {
      speech.abort();
      if (uiStateRef.current === 'listening') setUiState('');
    }
  }

  // ── Send to Jarvis ─────────────────────────────────────────────────────────
  function pushHistory(userText, userKind, replyText) {
    setHistory((prev) => {
      const next = [
        ...prev,
        { id: Date.now() + Math.random(), user: userText, userKind, reply: replyText, ts: Date.now() },
      ];
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
    });
  }

  function sendTypedToJarvis() {
    const raw = typedDraft.trim();
    if (!raw) return;
    if (uiStateRef.current === 'thinking') return;
    setTypedDraft('');
    const preview = raw.length > 140 ? `${raw.slice(0, 140)}…` : raw;
    const bridged =
      '[Typed in the UI for exact characters — voice was impractical or unreliable. Treat everything below as literal text; ask before repeating secrets, passwords, or API keys aloud.]\n\n' +
      raw;
    interrupt();
    setTxYou(`Typed — ${preview}`);
    sendToJarvis(bridged, { kind: 'typed', display: raw });
  }

  async function sendToJarvis(text, opts = {}) {
    setUiState('thinking');
    setTxJarvis('');
    try {
      const data = await sendChat(text);
      if (data.error && !data.reply) {
        const msg = `Error: ${data.error}`;
        setTxJarvis(msg);
        toast.error(data.error, 'Jarvis');
        setUiState(alwaysOnRef.current ? 'listening' : '');
        return;
      }

      if (data.tools?.length) {
        for (const t of data.tools) {
          setActiveTool(t.tool);
          await delay(220);
        }
        setActiveTool(null);
        getTopics().then(d => setTopics(d.topics || [])).catch(() => {});
        getConcepts().then(d => setConcepts(d)).catch(() => {});
      }

      if (data.code_blocks?.length) {
        setCodeBlocks(data.code_blocks);
      }

      const reply = data.error ? `Error: ${data.error}` : (data.reply || '');
      setTxJarvis(reply);
      const displayedUser = opts.kind === 'typed' ? opts.display : text;
      pushHistory(displayedUser, opts.kind || 'voice', reply);

      await speakReply(reply);
    } catch (e) {
      setTxJarvis('Connection error.');
      toast.error('Connection error contacting Jarvis backend.', 'Network');
      setUiState(alwaysOnRef.current ? 'listening' : '');
    }
  }

  // ── Speak ──────────────────────────────────────────────────────────────────
  async function speakReply(text) {
    if (!text) { doneAfterSpeaking(); return; }
    const lineForSpeech = stripCodeFencesForTts(text);
    if (!lineForSpeech) { doneAfterSpeaking(); return; }
    speakAbortedRef.current = false;
    setUiState('speaking');

    speech.abort();

    bargeStopRef.current = () => {};

    // Barge-in monitoring only makes sense when TTS audio can bleed back into
    // the mic (i.e. output is going through speakers in the same room). When
    // the user routes TTS to headphones (Bluetooth, USB) or any dedicated
    // sink, the mic only ever hears ambient noise — and a tweaked HVAC vent
    // or keyboard click will falsely "barge" and cut Jarvis off mid-word.
    // In that case we just play TTS to completion; the user can interrupt
    // with the orb or Escape.
    const sink = (config?.tts_sink || '').toLowerCase();
    const skipBargeIn = isHeadphoneLikeSink(sink);

    if (!skipBargeIn) {
      const stopMonitor = startBargeInMonitor({
        micId: micIdRef.current || undefined,
        // More forgiving thresholds — the previous defaults were tuned for a
        // very quiet room and would cut off on a fan or breath.
        absMin: 0.055,
        ratio: 2.4,
        framesNeeded: 7,
        learnMs: 600,
        onBarge: () => {
          if (speakAbortedRef.current) return;
          speakAbortedRef.current = true;
          bargeStopRef.current();
          bargeStopRef.current = () => {};
          ttsStop();
          setUiState('listening');
          speech.start(micIdRef.current || undefined);
        },
      });
      bargeStopRef.current = stopMonitor;
    }

    try {
      const result = await tts(lineForSpeech);
      if (result.status === 503) {
        setTxJarvis(prev => prev + ` [Voice "${result.voice}" not downloaded — open Settings]`);
        toast.warn('Open Settings → Voice to download the missing Piper voice.', 'Voice missing');
      }
    } catch {}
    finally {
      bargeStopRef.current();
      bargeStopRef.current = () => {};
    }
    doneAfterSpeaking();
  }

  function doneAfterSpeaking() {
    if (speakAbortedRef.current) {
      speakAbortedRef.current = false;
      return;
    }
    if (alwaysOnRef.current) {
      setUiState('listening');
      setTimeout(() => {
        if (uiStateRef.current === 'listening' && !speech.isActive()) {
          speech.start(micIdRef.current || undefined);
        }
      }, 250);
    } else {
      setUiState('');
    }
  }

  function handleNewChat() {
    resetChat().catch(() => {});
    setTxYou('');
    setTxJarvis('');
    setHistory([]);
    setCodeBlocks([]);
    setTypedDraft('');
    setSettingsOpen(false);
    toast.success('Conversation reset.', 'New chat');
  }

  // ── Keyboard ───────────────────────────────────────────────────────────────
  const onSequence = useCallback((seq, e) => {
    if (seq === 'gs') { e.preventDefault(); setSettingsOpen(true); }
    if (seq === 'gr') { e.preventDefault(); setRaceHubOpen(true); }
  }, []);
  const seqHandler = useSequenceKey(onSequence);

  useEffect(() => {
    function onKeyDown(e) {
      const tag = document.activeElement?.tagName;
      const inField = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

      // ESC always works
      if (e.key === 'Escape') {
        if (shortcutsOpen) { setShortcutsOpen(false); return; }
        if (settingsOpen)  { setSettingsOpen(false);  return; }
        if (raceHubOpen)   { setRaceHubOpen(false);   return; }
        interrupt();
        return;
      }

      // ? toggles help (when not typing)
      if (!inField && (e.key === '?' || (e.shiftKey && e.key === '/'))) {
        e.preventDefault();
        setShortcutsOpen((s) => !s);
        return;
      }

      // Ctrl-only shortcuts
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'Enter') {
          // handled inside Center for textareas, but allow global typed-send too
          if (typedDraft.trim() && uiStateRef.current !== 'thinking') {
            e.preventDefault();
            sendTypedToJarvis();
          }
          return;
        }
        if ((e.key === 'l' || e.key === 'L') && !inField) {
          e.preventDefault();
          handleNewChat();
          return;
        }
        if (e.key === '/' && !inField) {
          e.preventDefault();
          toggleAlwaysOn();
          return;
        }
        return;
      }

      if (inField) return;

      if (e.code === 'Space') { e.preventDefault(); handleOrbClick(); return; }

      // G-prefixed sequences
      seqHandler(e);
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shortcutsOpen, settingsOpen, raceHubOpen, typedDraft, seqHandler]);

  // ── Initial data load + Polling ────────────────────────────────────────────
  useEffect(() => {
    getConfig().then(setConfig).catch(() => {});
    getTopics().then(d => setTopics(d.topics || [])).catch(() => {});
    getTailscale().then(setTailscale).catch(() => {});
    getConcepts().then(setConcepts).catch(() => {});
    getSshHosts().then(d => setSshHosts(d.hosts || [])).catch(() => {});
    getSpotifyCurrent().then(setSpotify).catch(() => {});
    ping()
      .then(d => setApiOnline(d.status === 'online'))
      .catch(() => setApiOnline(false));
  }, []);

  usePolling(async () => {
    const d = await getTopics();
    setTopics(d.topics || []);
  }, 5000);

  usePolling(async () => setTailscale(await getTailscale()), 10000);

  usePolling(async () => {
    setConcepts(await getConcepts());
    const s = await getSshHosts();
    setSshHosts(s.hosts || []);
  }, 15000);

  usePolling(async () => setSpotify(await getSpotifyCurrent()), 4000);

  // Periodically re-ping LM Studio so the indicator stays honest.
  usePolling(async () => {
    try {
      const d = await ping();
      setApiOnline(d.status === 'online');
    } catch {
      setApiOnline(false);
    }
  }, 30000);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <ErrorBoundary>
      <TopBar
        apiOnline={apiOnline}
        alwaysOn={alwaysOn}
        spotify={spotify}
        onToggleAlwaysOn={toggleAlwaysOn}
        onNewChat={handleNewChat}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenRaceHub={() => setRaceHubOpen(true)}
        onOpenHelp={() => setShortcutsOpen(true)}
      />
      <LeftSidebar topics={topics} onTopicsChange={setTopics} />
      <Center
        uiState={uiState}
        txYou={txYou}
        txJarvis={txJarvis}
        history={history}
        codeBlocks={codeBlocks}
        activeTool={activeTool}
        onOrbClick={handleOrbClick}
        onClearCode={() => setCodeBlocks([])}
        typedDraft={typedDraft}
        onTypedDraftChange={setTypedDraft}
        onSendTyped={sendTypedToJarvis}
        typedSendDisabled={!typedDraft.trim() || uiState === 'thinking'}
        micId={micIdRef.current}
      />
      <RightSidebar
        tailscale={tailscale}
        concepts={concepts}
        spotify={spotify}
        onSpotifyUpdate={setSpotify}
      />
      <SettingsDrawer
        open={settingsOpen}
        config={config}
        onClose={() => setSettingsOpen(false)}
        onResetConversation={() => {
          setTxYou(''); setTxJarvis(''); setHistory([]); setCodeBlocks([]); setTypedDraft('');
        }}
        onApiOnlineChange={setApiOnline}
        onSshHostsChange={setSshHosts}
        onSetUiState={setUiState}
        onMicIdChange={setMicIdState}
        micId={micId}
      />
      <RaceHubDrawer
        open={raceHubOpen}
        onClose={() => setRaceHubOpen(false)}
      />
      <ShortcutsOverlay
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
      <ToastHost />
    </ErrorBoundary>
  );
}
