import React, { useState, useEffect, useRef } from 'react';
import {
  saveConfig,
  ping,
  downloadVoice,
  getAudioSinks,
  getSshHosts,
  addSshHost,
  deleteSshHost,
  testSshHost,
  resetChat,
  tts,
} from '../api.js';

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

const VOICE_OPTIONS = [
  { value: 'en_US-amy-medium',      label: 'en_US-amy-medium' },
  { value: 'en_US-lessac-medium',   label: 'en_US-lessac-medium' },
  { value: 'en_US-ryan-high',       label: 'en_US-ryan-high (best quality)' },
  { value: 'en_GB-alan-medium',     label: 'en_GB-alan-medium' },
  { value: 'en_GB-jenny-diphone',   label: 'en_GB-jenny-diphone' },
];

const STYLE_OPTIONS = [
  { value: 'natural',    label: 'Natural — clean pass-through' },
  { value: 'enhanced',   label: 'Enhanced — presence boost, fuller sound' },
  { value: 'warm',       label: 'Warm — softer highs, great for Bluetooth' },
  { value: 'crisp',      label: 'Crisp — removes mud, clear articulation' },
  { value: 'broadcast',  label: 'Broadcast — bandpass + normalize (podcast feel)' },
];

export default function SettingsDrawer({
  open,
  config,
  onClose,
  onResetConversation,
  onApiOnlineChange,
  onSshHostsChange,
  onSetUiState,
}) {
  // LM Studio fields
  const [url,   setUrl]   = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');

  // Audio fields
  const [voice,  setVoice]  = useState('en_US-amy-medium');
  const [sink,   setSink]   = useState('');
  const [style,  setStyle]  = useState('natural');
  const [speed,  setSpeed]  = useState(1.0);
  const [volume, setVolume] = useState(1.0);

  // Audio sinks
  const [sinks, setSinks] = useState([]);

  // Mic enumeration
  const [mics,  setMics]  = useState([]);
  const [micId, setMicId] = useState('');

  // Status messages
  const [svMsg,  setSvMsg]  = useState('');
  const [dlMsg,  setDlMsg]  = useState('');
  const [sshMsg, setSshMsg] = useState('');
  const [sshTestOut, setSshTestOut] = useState('');
  const [apiDotClass, setApiDotClass] = useState('');

  // SSH fields
  const [sshHostname, setSshHostname] = useState('');
  const [sshIp,       setSshIp]       = useState('');
  const [sshUser,     setSshUser]     = useState('root');
  const [sshPort,     setSshPort]     = useState('22');
  const [sshKey,      setSshKey]      = useState('');
  const [sshPass,     setSshPass]     = useState('');
  const [sshHosts,    setSshHosts]    = useState([]);

  const svMsgTimer  = useRef(null);
  const sshMsgTimer = useRef(null);

  // Sync config props into local state
  useEffect(() => {
    if (!config) return;
    setUrl(config.url      || '');
    setModel(config.model  || '');
    setApiKey(config.api_key || '');
    setVoice(config.piper_voice || 'en_US-amy-medium');
    setSink(config.tts_sink    || '');
    setStyle(config.tts_style  || 'natural');
    setSpeed(config.tts_speed  != null ? config.tts_speed : 1.0);
    setVolume(config.tts_volume != null ? config.tts_volume : 1.0);
  }, [config]);

  // Load sinks and mics and SSH hosts when drawer opens
  useEffect(() => {
    if (!open) return;
    loadSinks();
    loadMics();
    loadSshHostsLocal();
  }, [open]);

  async function loadSinks() {
    try {
      const data = await getAudioSinks();
      setSinks(data.sinks || []);
    } catch {}
  }

  async function loadMics() {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const devs = await navigator.mediaDevices.enumerateDevices();
      const inputs = devs.filter(d => d.kind === 'audioinput').map(d => ({
        deviceId: d.deviceId,
        label: d.label || `Mic ${d.deviceId.slice(0, 8)}`,
      }));
      setMics(inputs);
    } catch {}
  }

  async function loadSshHostsLocal() {
    try {
      const data = await getSshHosts();
      setSshHosts(data.hosts || []);
      if (onSshHostsChange) onSshHostsChange(data.hosts || []);
    } catch {}
  }

  function flash(setter, msg, ms = 2000, timerRef) {
    setter(msg);
    if (timerRef) {
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setter(''), ms);
    } else {
      setTimeout(() => setter(''), ms);
    }
  }

  async function handleSaveConfig() {
    await saveConfig({ url, model, api_key: apiKey, piper_voice: voice });
    flash(setSvMsg, 'Saved!', 2000, svMsgTimer);
  }

  async function handlePing() {
    setApiDotClass('');
    await handleSaveConfig();
    try {
      const data = await ping();
      const cls = data.status === 'online' ? 'online' : 'offline';
      setApiDotClass(cls);
      if (onApiOnlineChange) onApiOnlineChange(data.status === 'online');
      if (data.models?.length) setModel(m => m || data.models[0]);
    } catch {
      setApiDotClass('offline');
      if (onApiOnlineChange) onApiOnlineChange(false);
    }
  }

  async function handleDownloadVoice() {
    setDlMsg('Downloading…');
    await downloadVoice(voice, line => setDlMsg(line.slice(0, 55)));
    setDlMsg('Done!');
    setTimeout(() => setDlMsg(''), 3000);
  }

  async function handleSaveAudio() {
    await saveConfig({
      piper_voice: voice,
      tts_sink:    sink,
      tts_style:   style,
      tts_speed:   String(speed),
      tts_volume:  String(volume),
    });
    flash(setSvMsg, 'Audio saved!', 2000, svMsgTimer);
  }

  async function handleTestTts() {
    await handleSaveAudio();
    if (onSetUiState) onSetUiState('speaking');
    await tts('Hello, I am Jarvis. Audio test complete.');
    if (onSetUiState) onSetUiState('');
  }

  async function handleAddSshHost() {
    if (!sshHostname || !sshIp) {
      flash(setSshMsg, 'Hostname and IP required', 2000, sshMsgTimer);
      return;
    }
    const res = await addSshHost({
      hostname: sshHostname,
      ip:       sshIp,
      username: sshUser || 'root',
      port:     parseInt(sshPort) || 22,
      key_path: sshKey,
      password: sshPass,
    });
    flash(setSshMsg, res.status || 'Added!', 2000, sshMsgTimer);
    loadSshHostsLocal();
  }

  async function handleRemoveSshHost(hostname) {
    await deleteSshHost(hostname);
    loadSshHostsLocal();
  }

  async function handleTestSshHost() {
    if (!sshHostname) {
      flash(setSshMsg, 'Enter hostname first', 2000, sshMsgTimer);
      return;
    }
    setSshMsg('Testing…');
    setSshTestOut('');
    try {
      const data = await testSshHost(sshHostname);
      setSshMsg(data.ok ? '✓ Connected' : '✗ Failed');
      setSshTestOut(data.output || data.error || '');
      setTimeout(() => setSshMsg(''), 4000);
    } catch {
      setSshMsg('✗ Error');
      setTimeout(() => setSshMsg(''), 4000);
    }
  }

  async function handleResetConversation() {
    await resetChat();
    if (onResetConversation) onResetConversation();
    onClose();
  }

  return (
    <div id="settings" className={open ? 'open' : ''}>
      <div id="settings-close">
        <span>Settings</span>
        <button onClick={onClose} title="Close">&#x2715;</button>
      </div>

      <h3>LM Studio</h3>
      <div className="sg">
        <label>API URL</label>
        <input type="text" value={url} onChange={e => setUrl(e.target.value)} />
      </div>
      <div className="sg">
        <label>Model</label>
        <input type="text" value={model} onChange={e => setModel(e.target.value)} />
      </div>
      <div className="sg">
        <label>API Key</label>
        <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} />
      </div>
      <div className="srow">
        <button className="sbtn p" onClick={handleSaveConfig}>Save</button>
        <button className="sbtn" onClick={handlePing}>
          {apiDotClass && (
            <span
              style={{
                display: 'inline-block',
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: apiDotClass === 'online' ? 'var(--green)' : 'var(--red)',
                marginRight: 5,
                verticalAlign: 'middle',
              }}
            />
          )}
          Test
        </button>
        {svMsg && <span className="sv-msg">{svMsg}</span>}
      </div>

      <hr />
      <h3>Microphone</h3>
      <div className="sg">
        <label>Input Device</label>
        <select value={micId} onChange={e => setMicId(e.target.value)}>
          <option value="">Default</option>
          {mics.map(m => (
            <option key={m.deviceId} value={m.deviceId}>{m.label}</option>
          ))}
        </select>
      </div>

      <hr />
      <h3>Voice &amp; Audio Output</h3>

      <div className="sg">
        <label>Piper Voice</label>
        <select value={voice} onChange={e => setVoice(e.target.value)}>
          {VOICE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
      <div className="srow">
        <button className="sbtn" onClick={handleDownloadVoice}>Download Voice</button>
        {dlMsg && <span className="dl-msg">{dlMsg}</span>}
      </div>

      <div className="sg">
        <label>Output Device</label>
        <select value={sink} onChange={e => setSink(e.target.value)}>
          <option value="">System Default</option>
          {sinks.map(s => (
            <option key={s.name} value={s.name}>{s.desc || s.name}</option>
          ))}
        </select>
      </div>

      <div className="sg">
        <label>Audio Style</label>
        <select value={style} onChange={e => setStyle(e.target.value)}>
          {STYLE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="sg">
        <label>
          Speed <span className="slider-val">{Number(speed).toFixed(2)}&times;</span>
        </label>
        <input
          type="range"
          min="0.6"
          max="1.8"
          step="0.05"
          value={speed}
          onChange={e => setSpeed(parseFloat(e.target.value))}
        />
      </div>

      <div className="sg">
        <label>
          Volume <span className="slider-val">{Number(volume).toFixed(2)}&times;</span>
        </label>
        <input
          type="range"
          min="0.3"
          max="2.0"
          step="0.05"
          value={volume}
          onChange={e => setVolume(parseFloat(e.target.value))}
        />
      </div>

      <button className="sbtn p" onClick={handleSaveAudio}>Apply Audio Settings</button>
      <button className="sbtn" onClick={handleTestTts}>&#x25B6; Test Voice</button>

      <hr />
      <h3>SSH Hosts</h3>
      <div id="ssh-host-list" style={{ fontSize: '10px', color: 'var(--muted)', marginBottom: '6px' }}>
        {sshHosts.length === 0 ? (
          <span>No SSH hosts configured.</span>
        ) : (
          sshHosts.map(h => {
            const dot = h.live ? '🟢' : (h.last_error ? '🔴' : '🟡');
            return (
              <div key={h.hostname} className="ssh-host-row">
                <span>{dot} {esc(h.username)}@{esc(h.hostname)}</span>
                <button onClick={() => handleRemoveSshHost(h.hostname)}>&times;</button>
              </div>
            );
          })
        )}
      </div>

      <div className="sg"><label>Hostname</label>
        <input placeholder="server-01" value={sshHostname} onChange={e => setSshHostname(e.target.value)} />
      </div>
      <div className="sg"><label>Tailscale IP</label>
        <input placeholder="100.x.x.x" value={sshIp} onChange={e => setSshIp(e.target.value)} />
      </div>
      <div className="sg"><label>Username</label>
        <input placeholder="root" value={sshUser} onChange={e => setSshUser(e.target.value)} />
      </div>
      <div className="sg"><label>Port</label>
        <input placeholder="22" value={sshPort} onChange={e => setSshPort(e.target.value)} style={{ width: '70px' }} />
      </div>
      <div className="sg"><label>Key Path (optional)</label>
        <input placeholder="~/.ssh/id_ed25519" value={sshKey} onChange={e => setSshKey(e.target.value)} />
      </div>
      <div className="sg"><label>Password (optional)</label>
        <input type="password" placeholder="leave blank if using key" value={sshPass} onChange={e => setSshPass(e.target.value)} />
      </div>
      <div className="srow">
        <button className="sbtn p" onClick={handleAddSshHost}>Add &amp; Monitor</button>
        <button className="sbtn" onClick={handleTestSshHost}>Test</button>
        {sshMsg && <span style={{ fontSize: '10px', color: 'var(--green)' }}>{sshMsg}</span>}
      </div>
      {sshTestOut && <div id="ssh-test-out">{sshTestOut}</div>}

      <hr />
      <button className="sbtn d" onClick={handleResetConversation}>Clear Conversation</button>
    </div>
  );
}
