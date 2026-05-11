import React, { useState, useEffect, useRef, useCallback } from 'react';
import TopBar from './components/TopBar.jsx';
import LeftSidebar from './components/LeftSidebar.jsx';
import Center from './components/Center.jsx';
import RightSidebar from './components/RightSidebar.jsx';
import SettingsDrawer from './components/SettingsDrawer.jsx';
import RaceHubDrawer from './components/RaceHubDrawer.jsx';
import { useSpeech } from './hooks/useSpeech.js';
import { startBargeInMonitor } from './hooks/startBargeInMonitor.js';
import { stripCodeFencesForTts } from './lib/stripCodeFencesForTts.js';
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

export default function App() {
  // ── Core state ──────────────────────────────────────────────────────────────
  const [uiState,      setUiStateRaw]  = useState('');      // ''|listening|thinking|speaking
  const uiStateRef     = useRef('');
  const [alwaysOn,     setAlwaysOnRaw] = useState(false);
  const alwaysOnRef    = useRef(false);
  const [micId,        setMicIdRaw]    = useState('');
  const micIdRef       = useRef('');
  const speakAbortedRef = useRef(false);
  const bargeStopRef   = useRef(() => {});

  // ── Transcript ───────────────────────────────────────────────────────────────
  const [txYou,    setTxYou]    = useState('');
  const [txJarvis, setTxJarvis] = useState('');

  // ── Code blocks ──────────────────────────────────────────────────────────────
  const [codeBlocks, setCodeBlocks] = useState([]);

  const [typedDraft, setTypedDraft] = useState('');

  // ── Sidebar data ─────────────────────────────────────────────────────────────
  const [topics,    setTopics]    = useState([]);
  const [tailscale, setTailscale] = useState(null);
  const [concepts,  setConcepts]  = useState(null);
  const [sshHosts,  setSshHosts]  = useState([]);
  const [spotify,   setSpotify]   = useState(null);

  // ── Top bar ──────────────────────────────────────────────────────────────────
  const [apiOnline,    setApiOnline]    = useState(null);   // null=unknown, true, false
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [raceHubOpen,  setRaceHubOpen]  = useState(false);
  const [config,       setConfig]       = useState(null);

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function setUiState(s) {
    uiStateRef.current = s;
    setUiStateRaw(s);
    // Apply to body className for CSS animations
    document.body.className = s || '';
    // Update state label text
    const label = document.getElementById('state-label');
    if (label) {
      label.textContent = { '': 'Ready', listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking…' }[s] ?? s;
    }
  }

  function isBusy() {
    return uiStateRef.current !== '';
  }

  function setAlwaysOn(val) {
    alwaysOnRef.current = val;
    setAlwaysOnRaw(val);
  }

  function setMicId(val) {
    micIdRef.current = val;
    setMicIdRaw(val);
  }

  // ── Tool pill ────────────────────────────────────────────────────────────────
  function showTool(name) {
    const pill = document.getElementById('tool-pill');
    if (pill) { pill.textContent = `⚙ ${name}`; pill.classList.add('on'); }
  }
  function hideTool() {
    const pill = document.getElementById('tool-pill');
    if (pill) pill.classList.remove('on');
  }

  // ── Speech hook ───────────────────────────────────────────────────────────────
  function speechErrorMessage(code) {
    switch (code) {
      case 'not-supported':       return 'Speech recognition not supported in this browser. Use Chrome.';
      case 'not-allowed':         return 'Mic permission denied — click 🔒 in the address bar and allow Microphone for 127.0.0.1.';
      case 'service-not-allowed': return 'Chrome blocked the speech service. Check chrome://settings/content/microphone.';
      case 'network':             return 'Speech recognition needs internet — Chrome routes SR to Google. Check your connection.';
      case 'audio-capture':       return 'No microphone detected. Plug one in or pick a different device in Settings.';
      case 'aborted':             return 'Speech recognition was aborted.';
      case 'language-not-supported': return 'Language not supported by Chrome speech recognition.';
      default:                    return `Speech error: ${code}`;
    }
  }

  const speech = useSpeech({
    onInterim: (text) => {
      setTxYou(text);
    },
    onFinal: useCallback((text, error) => {
      if (error === 'rejected' || error === 'no-speech') {
        // silent reject — clear interim
        setTxYou('');
        uiStateRef.current = '';
        setUiState('');
        if (error === 'no-speech' && alwaysOnRef.current) {
          setTimeout(() => {
            if (!isBusy()) startListening();
          }, 800);
          return;
        }
        if (alwaysOnRef.current) {
          setTimeout(() => { if (!isBusy()) startListening(); }, 800);
        }
        return;
      }
      if (error && error !== 'rejected') {
        // recognizer error — surface it so the user knows what happened
        console.warn('[jarvis] speech recognition error:', error);
        setTxYou('');
        setTxJarvis(speechErrorMessage(error));
        setUiState('');
        // Auto-clear the error after a while so the UI doesn't get stuck on it
        setTimeout(() => {
          setTxJarvis(prev => prev === speechErrorMessage(error) ? '' : prev);
        }, 8000);
        if (alwaysOnRef.current && error !== 'not-allowed' && error !== 'not-supported') {
          setTimeout(() => { if (!isBusy()) startListening(); }, 1500);
        }
        return;
      }
      // Success — send to Jarvis
      if (text) sendToJarvis(text);
    }, []),
  });

  // ── Start listening ──────────────────────────────────────────────────────────
  function startListening() {
    setTxYou('');
    setUiState('listening');
    speech.start(micIdRef.current || undefined);
  }

  // ── Interrupt ────────────────────────────────────────────────────────────────
  function interrupt() {
    bargeStopRef.current();
    bargeStopRef.current = () => {};
    ttsStop();
    speech.abort();
    setUiState('');
    setTxYou('');
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
    sendToJarvis(bridged);
  }

  // ── Orb click ────────────────────────────────────────────────────────────────
  function handleOrbClick() {
    if (isBusy() || uiStateRef.current === 'listening') {
      interrupt();
      return;
    }
    startListening();
  }

  // ── Toggle always-on ─────────────────────────────────────────────────────────
  function toggleAlwaysOn() {
    const next = !alwaysOnRef.current;
    setAlwaysOn(next);
    if (next && !isBusy()) startListening();
  }

  // ── Send to Jarvis ────────────────────────────────────────────────────────────
  async function sendToJarvis(text) {
    setUiState('thinking');
    setTxJarvis('');
    try {
      const data = await sendChat(text);
      if (data.error && !data.reply) {
        setUiState('');
        setTxJarvis(`Error: ${data.error}`);
        if (alwaysOnRef.current) {
          setTimeout(() => { if (!isBusy()) startListening(); }, 1500);
        }
        return;
      }

      if (data.tools?.length) {
        for (const t of data.tools) {
          showTool(t.tool);
          await delay(300);
        }
        hideTool();
        // Refresh panels after tool calls
        getTopics().then(d => setTopics(d.topics || []));
        getConcepts().then(d => setConcepts(d));
      }

      if (data.code_blocks?.length) {
        setCodeBlocks(data.code_blocks);
      }

      const reply = data.error ? `Error: ${data.error}` : (data.reply || '');
      setTxJarvis(reply);

      await speakReply(reply);
    } catch (e) {
      setUiState('');
      setTxJarvis('Connection error.');
      if (alwaysOnRef.current) {
        setTimeout(() => { if (!isBusy()) startListening(); }, 1500);
      }
    }
  }

  // ── Speak reply via Piper (server-side, blocking) ────────────────────────────
  async function speakReply(text) {
    if (!text) {
      doneAfterSpeaking();
      return;
    }
    const lineForSpeech = stripCodeFencesForTts(text);
    if (!lineForSpeech) {
      doneAfterSpeaking();
      return;
    }
    speakAbortedRef.current = false;
    setUiState('speaking');

    bargeStopRef.current = () => {};
    const stopMonitor = startBargeInMonitor({
      micId: micIdRef.current || undefined,
      onBarge: () => {
        if (speakAbortedRef.current) return;
        speakAbortedRef.current = true;
        bargeStopRef.current();
        bargeStopRef.current = () => {};
        ttsStop();
        speech.abort();
        setTimeout(() => {
          setUiState('listening');
          speech.start(micIdRef.current || undefined);
        }, 60);
      },
    });
    bargeStopRef.current = stopMonitor;

    try {
      const result = await tts(lineForSpeech);
      if (result.status === 503) {
        setTxJarvis(prev => prev + ` [Voice "${result.voice}" not downloaded — open Settings]`);
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
    setUiState('');
    // 1.8s gap after speaking — enough for paplay to fully drain
    if (alwaysOnRef.current) {
      setTimeout(() => {
        if (!isBusy() && uiStateRef.current !== 'listening') startListening();
      }, 1800);
    }
  }

  // ── New chat ──────────────────────────────────────────────────────────────────
  function handleNewChat() {
    resetChat().catch(() => {});
    setTxYou('');
    setTxJarvis('');
    setCodeBlocks([]);
    setTypedDraft('');
    setSettingsOpen(false);
  }

  // ── Keyboard ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    function onKeyDown(e) {
      // Ignore if focused on an input/textarea/select
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.code === 'Space') {
        e.preventDefault();
        handleOrbClick();
      }
      if (e.key === 'Escape') {
        interrupt();
        setSettingsOpen(false);
        setRaceHubOpen(false);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []); // eslint-disable-line

  // ── Initial data load ─────────────────────────────────────────────────────────
  useEffect(() => {
    getConfig().then(cfg => setConfig(cfg)).catch(() => {});
    getTopics().then(d => setTopics(d.topics || [])).catch(() => {});
    getTailscale().then(d => setTailscale(d)).catch(() => {});
    getConcepts().then(d => setConcepts(d)).catch(() => {});
    getSshHosts().then(d => setSshHosts(d.hosts || [])).catch(() => {});
    getSpotifyCurrent().then(d => setSpotify(d)).catch(() => {});

    // Initial API ping
    ping().then(d => setApiOnline(d.status === 'online')).catch(() => setApiOnline(false));
  }, []);

  // ── Polling ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    const t1 = setInterval(() => {
      getTopics().then(d => setTopics(d.topics || [])).catch(() => {});
    }, 5000);
    const t2 = setInterval(() => {
      getTailscale().then(d => setTailscale(d)).catch(() => {});
    }, 10000);
    const t3 = setInterval(() => {
      getConcepts().then(d => setConcepts(d)).catch(() => {});
      getSshHosts().then(d => setSshHosts(d.hosts || [])).catch(() => {});
    }, 15000);
    const t4 = setInterval(() => {
      getSpotifyCurrent().then(d => setSpotify(d)).catch(() => {});
    }, 4000);
    return () => { clearInterval(t1); clearInterval(t2); clearInterval(t3); clearInterval(t4); };
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <>
      <TopBar
        apiOnline={apiOnline}
        alwaysOn={alwaysOn}
        onToggleAlwaysOn={toggleAlwaysOn}
        onNewChat={handleNewChat}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenRaceHub={() => setRaceHubOpen(true)}
      />
      <LeftSidebar topics={topics} onTopicsChange={setTopics} />
      <Center
        txYou={txYou}
        txJarvis={txJarvis}
        codeBlocks={codeBlocks}
        onOrbClick={handleOrbClick}
        onClearCode={() => setCodeBlocks([])}
        typedDraft={typedDraft}
        onTypedDraftChange={setTypedDraft}
        onSendTyped={sendTypedToJarvis}
        typedSendDisabled={!typedDraft.trim() || uiState === 'thinking'}
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
        onResetConversation={() => { setTxYou(''); setTxJarvis(''); setCodeBlocks([]); setTypedDraft(''); }}
        onApiOnlineChange={setApiOnline}
        onSshHostsChange={setSshHosts}
        onSetUiState={setUiState}
      />
      <RaceHubDrawer
        open={raceHubOpen}
        onClose={() => setRaceHubOpen(false)}
      />
    </>
  );
}
