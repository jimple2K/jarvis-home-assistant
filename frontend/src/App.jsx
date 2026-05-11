import React, { useState, useEffect, useRef, useCallback } from 'react';
import TopBar from './components/TopBar.jsx';
import LeftSidebar from './components/LeftSidebar.jsx';
import Center from './components/Center.jsx';
import RightSidebar from './components/RightSidebar.jsx';
import SettingsDrawer from './components/SettingsDrawer.jsx';
import { useSpeech } from './hooks/useSpeech.js';
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

  // ── Transcript ───────────────────────────────────────────────────────────────
  const [txYou,    setTxYou]    = useState('');
  const [txJarvis, setTxJarvis] = useState('');

  // ── Code blocks ──────────────────────────────────────────────────────────────
  const [codeBlocks, setCodeBlocks] = useState([]);

  // ── Sidebar data ─────────────────────────────────────────────────────────────
  const [topics,    setTopics]    = useState([]);
  const [tailscale, setTailscale] = useState(null);
  const [concepts,  setConcepts]  = useState(null);
  const [sshHosts,  setSshHosts]  = useState([]);
  const [spotify,   setSpotify]   = useState(null);

  // ── Top bar ──────────────────────────────────────────────────────────────────
  const [apiOnline,    setApiOnline]    = useState(null);   // null=unknown, true, false
  const [settingsOpen, setSettingsOpen] = useState(false);
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
        // recognizer error
        setTxYou('');
        setUiState('');
        if (alwaysOnRef.current) {
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
    ttsStop();
    speech.abort();
    setUiState('');
    setTxYou('');
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
    setUiState('speaking');
    try {
      const result = await tts(text);
      if (result.status === 503) {
        setTxJarvis(prev => prev + ` [Voice "${result.voice}" not downloaded — open Settings]`);
      }
    } catch {}
    doneAfterSpeaking();
  }

  function doneAfterSpeaking() {
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
      />
      <LeftSidebar topics={topics} onTopicsChange={setTopics} />
      <Center
        txYou={txYou}
        txJarvis={txJarvis}
        codeBlocks={codeBlocks}
        onOrbClick={handleOrbClick}
        onClearCode={() => setCodeBlocks([])}
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
        onResetConversation={() => { setTxYou(''); setTxJarvis(''); }}
        onApiOnlineChange={setApiOnline}
        onSshHostsChange={setSshHosts}
        onSetUiState={setUiState}
      />
    </>
  );
}
