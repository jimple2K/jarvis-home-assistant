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
  getGithubStatus,
  saveGithubToken,
  configureGitHttps,
  setupGithubSsh,
  testGithubSsh,
  clearGithubAuth,
} from '../api.js';
import { toast } from '../lib/toast.js';
import { useFocusTrap } from '../hooks/useFocusTrap.js';

const VOICE_OPTIONS = [
  { value: 'en_US-amy-medium',    label: 'en_US-amy-medium' },
  { value: 'en_US-lessac-medium', label: 'en_US-lessac-medium' },
  { value: 'en_US-ryan-high',     label: 'en_US-ryan-high (best quality)' },
  { value: 'en_GB-alan-medium',   label: 'en_GB-alan-medium' },
  { value: 'en_GB-jenny-diphone', label: 'en_GB-jenny-diphone' },
];

const STYLE_OPTIONS = [
  { value: 'natural',   label: 'Natural — clean pass-through' },
  { value: 'enhanced',  label: 'Enhanced — presence boost, fuller sound' },
  { value: 'warm',      label: 'Warm — softer highs, great for Bluetooth' },
  { value: 'crisp',     label: 'Crisp — removes mud, clear articulation' },
  { value: 'broadcast', label: 'Broadcast — bandpass + normalize (podcast feel)' },
];

export default function SettingsDrawer({
  open,
  config,
  onClose,
  onResetConversation,
  onApiOnlineChange,
  onSshHostsChange,
  onSetUiState,
  onMicIdChange,
  micId,
}) {
  const drawerRef = useRef(null);
  useFocusTrap(drawerRef, open);

  // LM Studio fields
  const [url,    setUrl]    = useState('');
  const [model,  setModel]  = useState('');
  const [apiKey, setApiKey] = useState('');

  // Audio fields
  const [voice,  setVoice]  = useState('en_US-amy-medium');
  const [sink,   setSink]   = useState('');
  const [style,  setStyle]  = useState('natural');
  const [speed,  setSpeed]  = useState(1.0);
  const [volume, setVolume] = useState(1.0);

  const [sinks, setSinks] = useState([]);
  const [mics,  setMics]  = useState([]);

  const [svMsg,      setSvMsg]      = useState('');
  const [dlMsg,      setDlMsg]      = useState('');
  const [sshMsg,     setSshMsg]     = useState('');
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

  // GitHub fields
  const [ghToken,     setGhToken]     = useState('');
  const [ghStatus,    setGhStatus]    = useState(null);
  const [ghBusy,      setGhBusy]      = useState('');
  const [ghOutput,    setGhOutput]    = useState('');

  const svMsgTimer  = useRef(null);
  const sshMsgTimer = useRef(null);

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

  useEffect(() => {
    if (!open) return;
    loadSinks();
    loadMics();
    loadSshHostsLocal();
    refreshGithubStatus();
  }, [open]);

  async function refreshGithubStatus() {
    try {
      const s = await getGithubStatus();
      setGhStatus(s);
    } catch {}
  }

  // ESC closes drawer
  useEffect(() => {
    if (!open) return;
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

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
    toast.success('LM Studio config saved.', 'Settings');
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
      if (data.status === 'online') toast.success('LM Studio is online.', 'Connection');
      else toast.warn('LM Studio is offline.', 'Connection');
    } catch {
      setApiDotClass('offline');
      if (onApiOnlineChange) onApiOnlineChange(false);
      toast.error('Ping failed.', 'Connection');
    }
  }

  async function handleDownloadVoice() {
    setDlMsg('Downloading…');
    try {
      await downloadVoice(voice, line => setDlMsg(line.slice(0, 55)));
      setDlMsg('Done!');
      toast.success(`Voice "${voice}" ready.`, 'Voice download');
    } catch {
      setDlMsg('Failed');
      toast.error('Voice download failed.', 'Voice download');
    }
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
    toast.success('Audio settings applied.', 'Voice');
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
      toast.warn('Hostname and IP are required.', 'SSH');
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
    toast.success(`SSH host ${sshHostname} added.`, 'SSH');
    loadSshHostsLocal();
  }

  async function handleRemoveSshHost(hostname) {
    await deleteSshHost(hostname);
    toast.info(`Removed ${hostname}.`, 'SSH');
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
      if (data.ok) toast.success(`SSH to ${sshHostname} succeeded.`, 'SSH');
      else toast.error(`SSH test failed.`, 'SSH');
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
    toast.success('Conversation cleared.', 'Reset');
  }

  // ── GitHub handlers ──
  async function handleGhSave() {
    setGhBusy('save');
    setGhOutput('');
    try {
      const status = await saveGithubToken(ghToken);
      setGhStatus(status);
      if (status.ok) {
        toast.success(`Signed in as ${status.login}.`, 'GitHub');
        setGhToken('');
      } else if (status.configured && !ghToken) {
        toast.warn(status.error || 'Token validation failed.', 'GitHub');
      } else {
        toast.error(status.error || 'Could not validate token.', 'GitHub');
      }
    } catch {
      toast.error('Save failed.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  async function handleGhTest() {
    setGhBusy('test');
    try {
      await refreshGithubStatus();
      const s = await getGithubStatus();
      setGhStatus(s);
      if (s.ok) toast.success(`Token is valid. Signed in as ${s.login}.`, 'GitHub');
      else toast.warn(s.error || s.message || 'Not configured.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  async function handleGhConfigureHttps() {
    setGhBusy('https');
    try {
      const r = await configureGitHttps();
      setGhOutput(r.message || r.error || '');
      if (r.ok) toast.success('git is now authenticated over HTTPS.', 'GitHub');
      else toast.error(r.error || 'Failed.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  async function handleGhSetupSsh() {
    setGhBusy('ssh');
    setGhOutput('Generating ED25519 key + uploading to GitHub…');
    try {
      const r = await setupGithubSsh('');
      setGhOutput(r.message || r.error || '');
      if (r.ok) toast.success(r.message || 'SSH key set up.', 'GitHub');
      else toast.error(r.error || 'SSH setup failed.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  async function handleGhTestSsh() {
    setGhBusy('sshtest');
    setGhOutput('Running `ssh -T git@github.com`…');
    try {
      const r = await testGithubSsh();
      setGhOutput(r.output || (r.ok ? 'Authenticated.' : 'Failed.'));
      if (r.ok) toast.success('SSH auth to GitHub works.', 'GitHub');
      else toast.warn('SSH test did not return a success line.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  async function handleGhClear() {
    if (!window.confirm('Remove the saved GitHub token from this machine?')) return;
    setGhBusy('clear');
    try {
      await clearGithubAuth();
      setGhStatus({ ok: false, configured: false, message: 'No GitHub token configured.' });
      setGhOutput('');
      toast.info('GitHub token cleared.', 'GitHub');
    } finally {
      setGhBusy('');
    }
  }

  return (
    <>
      <div
        className={'drawer-backdrop' + (open ? ' open' : '')}
        onClick={onClose}
        aria-hidden
      />
      <div
        id="settings"
        className={open ? 'open' : ''}
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        aria-hidden={!open}
      >
        <div id="settings-close">
          <span>Settings</span>
          <button onClick={onClose} title="Close (Esc)" aria-label="Close settings">×</button>
        </div>

        <h3>LM Studio</h3>
        <div className="sg">
          <label htmlFor="lm-url">API URL</label>
          <input id="lm-url" type="text" value={url} onChange={e => setUrl(e.target.value)} />
        </div>
        <div className="sg">
          <label htmlFor="lm-model">Model</label>
          <input id="lm-model" type="text" value={model} onChange={e => setModel(e.target.value)} />
        </div>
        <div className="sg">
          <label htmlFor="lm-key">API Key</label>
          <input id="lm-key" type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} />
        </div>
        <div className="srow">
          <button className="sbtn p" onClick={handleSaveConfig}>Save</button>
          <button className="sbtn" onClick={handlePing}>
            {apiDotClass && (
              <span
                style={{
                  display: 'inline-block',
                  width: 8, height: 8,
                  borderRadius: '50%',
                  background: apiDotClass === 'online' ? 'var(--green)' : 'var(--red)',
                  marginRight: 6,
                  verticalAlign: 'middle',
                  boxShadow: apiDotClass === 'online' ? '0 0 6px var(--green)' : 'none',
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
          <label htmlFor="mic-input">Input Device</label>
          <select
            id="mic-input"
            value={micId || ''}
            onChange={e => onMicIdChange && onMicIdChange(e.target.value)}
          >
            <option value="">Default</option>
            {mics.map(m => (
              <option key={m.deviceId} value={m.deviceId}>{m.label}</option>
            ))}
          </select>
        </div>

        <hr />
        <h3>Voice &amp; Audio Output</h3>

        <div className="sg">
          <label htmlFor="piper-voice">Piper Voice</label>
          <select id="piper-voice" value={voice} onChange={e => setVoice(e.target.value)}>
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
          <label htmlFor="audio-sink">Output Device</label>
          <select id="audio-sink" value={sink} onChange={e => setSink(e.target.value)}>
            <option value="">System Default</option>
            {sinks.map(s => (
              <option key={s.name} value={s.name}>{s.desc || s.name}</option>
            ))}
          </select>
        </div>

        <div className="sg">
          <label htmlFor="audio-style">Audio Style</label>
          <select id="audio-style" value={style} onChange={e => setStyle(e.target.value)}>
            {STYLE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="sg">
          <label htmlFor="audio-speed">
            Speed <span className="slider-val">{Number(speed).toFixed(2)}×</span>
          </label>
          <input
            id="audio-speed"
            type="range"
            min="0.6" max="1.8" step="0.05"
            value={speed}
            onChange={e => setSpeed(parseFloat(e.target.value))}
          />
        </div>

        <div className="sg">
          <label htmlFor="audio-volume">
            Volume <span className="slider-val">{Number(volume).toFixed(2)}×</span>
          </label>
          <input
            id="audio-volume"
            type="range"
            min="0.3" max="2.0" step="0.05"
            value={volume}
            onChange={e => setVolume(parseFloat(e.target.value))}
          />
        </div>

        <div className="srow">
          <button className="sbtn p" onClick={handleSaveAudio}>Apply Audio</button>
          <button className="sbtn" onClick={handleTestTts}>▶ Test Voice</button>
        </div>

        <hr />
        <h3>SSH Hosts</h3>
        <div style={{ marginBottom: 6 }}>
          {sshHosts.length === 0 ? (
            <div style={{ fontSize: 11, color: 'var(--muted-2)', fontStyle: 'italic', padding: '4px 0' }}>
              No SSH hosts configured.
            </div>
          ) : (
            sshHosts.map(h => {
              const dot = h.live ? '🟢' : (h.last_error ? '🔴' : '🟡');
              return (
                <div key={h.hostname} className="ssh-host-row">
                  <span>{dot} {h.username}@{h.hostname}</span>
                  <button onClick={() => handleRemoveSshHost(h.hostname)} aria-label={`Remove ${h.hostname}`}>×</button>
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
          <input placeholder="22" value={sshPort} onChange={e => setSshPort(e.target.value)} style={{ width: 88 }} />
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
          {sshMsg && <span className="sv-msg">{sshMsg}</span>}
        </div>
        {sshTestOut && <div id="ssh-test-out">{sshTestOut}</div>}

        <hr />
        <h3>GitHub</h3>

        {ghStatus?.ok ? (
          <div className="gh-status gh-ok">
            <div className="gh-status-row">
              <span className="gh-status-dot gh-ok" />
              <div className="gh-status-body">
                <div className="gh-status-title">
                  Signed in as <strong>{ghStatus.login}</strong>
                  {ghStatus.name && <span style={{ color: 'var(--muted)' }}> · {ghStatus.name}</span>}
                </div>
                <div className="gh-status-sub">
                  {(ghStatus.public_repos ?? 0)} public ·{' '}
                  {(ghStatus.private_repos ?? 0)} private ·{' '}
                  API quota {ghStatus.rate_limit?.remaining ?? '?'} / {ghStatus.rate_limit?.limit ?? '?'}
                </div>
                {(ghStatus.scopes?.length ?? 0) > 0 && (
                  <div className="gh-status-scopes">
                    Scopes: {ghStatus.scopes.join(', ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="gh-status gh-off">
            <div className="gh-status-row">
              <span className={'gh-status-dot ' + (ghStatus?.configured ? 'gh-bad' : 'gh-off')} />
              <div className="gh-status-body">
                <div className="gh-status-title">
                  {ghStatus?.configured
                    ? 'Token configured but invalid'
                    : 'GitHub not configured'}
                </div>
                <div className="gh-status-sub">
                  {ghStatus?.error || ghStatus?.message
                    || 'Paste a Personal Access Token below to enable GitHub tools, HTTPS git, and SSH key setup.'}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="sg">
          <label htmlFor="gh-token">Personal Access Token</label>
          <input
            id="gh-token"
            type="password"
            placeholder={ghStatus?.configured ? '•••• (already set — paste to replace)' : 'ghp_…  or  github_pat_…'}
            value={ghToken}
            onChange={e => setGhToken(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="gh-help">
          Create at{' '}
          <a href="https://github.com/settings/tokens?type=beta" target="_blank" rel="noopener noreferrer">
            github.com → Settings → Developer settings → Tokens
          </a>
          . Recommended scopes: <code>repo</code>, <code>read:user</code>, <code>gist</code>,{' '}
          <code>workflow</code>, <code>admin:public_key</code>.
        </div>

        <div className="srow">
          <button className="sbtn p" onClick={handleGhSave} disabled={ghBusy === 'save'}>
            {ghBusy === 'save' ? 'Saving…' : 'Save & Verify'}
          </button>
          <button className="sbtn" onClick={handleGhTest} disabled={ghBusy === 'test'}>
            {ghBusy === 'test' ? 'Testing…' : 'Re-test'}
          </button>
          {ghStatus?.configured && (
            <button className="sbtn d" onClick={handleGhClear} disabled={ghBusy === 'clear'}>
              Clear
            </button>
          )}
        </div>

        {ghStatus?.ok && (
          <>
            <div className="gh-help" style={{ marginTop: 6 }}>
              <strong>HTTPS git (recommended):</strong> one click and{' '}
              <code>git clone / pull / push</code> on github.com just work — no SSH agent needed.
            </div>
            <div className="srow">
              <button className="sbtn p" onClick={handleGhConfigureHttps} disabled={ghBusy === 'https'}>
                {ghBusy === 'https' ? 'Configuring…' : 'Wire git HTTPS auth'}
              </button>
            </div>

            <div className="gh-help" style={{ marginTop: 6 }}>
              <strong>SSH (optional):</strong> generates <code>~/.ssh/jarvis_github_ed25519</code>,
              uploads its public half, and configures <code>~/.ssh/config</code> so{' '}
              <code>git@github.com</code> uses it.
            </div>
            <div className="srow">
              <button className="sbtn" onClick={handleGhSetupSsh} disabled={ghBusy === 'ssh'}>
                {ghBusy === 'ssh' ? 'Setting up…' : 'Set up SSH key on GitHub'}
              </button>
              <button className="sbtn" onClick={handleGhTestSsh} disabled={ghBusy === 'sshtest'}>
                {ghBusy === 'sshtest' ? 'Testing…' : 'Test SSH'}
              </button>
            </div>
          </>
        )}

        {ghOutput && <div id="gh-output">{ghOutput}</div>}

        <hr />
        <button className="sbtn d" onClick={handleResetConversation}>Clear Conversation</button>
      </div>
    </>
  );
}
