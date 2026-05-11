const JSON_HEADERS = { 'Content-Type': 'application/json' };

// ── Config ──────────────────────────────────────────────────────────────────

export async function getConfig() {
  const res = await fetch('/api/config');
  return res.json();
}

export async function saveConfig(data) {
  const res = await fetch('/config', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
  return res.json();
}

// ── Ping / LM Studio ────────────────────────────────────────────────────────

export async function ping() {
  const res = await fetch('/ping', { method: 'POST' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { status: 'offline', ...data };
  }
  return res.json();
}

// ── Chat ────────────────────────────────────────────────────────────────────

export async function sendChat(message) {
  const res = await fetch('/chat', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ message }),
  });
  return res.json();
}

export async function resetChat() {
  const res = await fetch('/chat', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ reset: true }),
  });
  return res.json();
}

// ── TTS ─────────────────────────────────────────────────────────────────────

export async function tts(text) {
  const res = await fetch('/tts', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ text }),
  });
  if (res.status === 503 || res.status === 500) {
    return { error: true, status: res.status, ...(await res.json().catch(() => ({}))) };
  }
  return { error: false, status: res.status };
}

export async function ttsStop() {
  await fetch('/tts/stop', { method: 'POST' }).catch(() => {});
}

export async function downloadVoice(voice, onProgress) {
  const res = await fetch('/tts/download', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ voice }),
  });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const line = dec.decode(value).replace(/^data: /, '').trim();
    if (line && onProgress) onProgress(line);
  }
}

// ── Topics ──────────────────────────────────────────────────────────────────

export async function getTopics() {
  const res = await fetch('/api/topics');
  return res.json();
}

export async function createTopic(title, description = '') {
  const res = await fetch('/api/topics', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ title, description }),
  });
  return res.json();
}

export async function deleteTopic(id) {
  const res = await fetch(`/api/topics/${id}`, { method: 'DELETE' });
  return res.json();
}

export async function activateTopic(id) {
  const res = await fetch(`/api/topics/${id}/activate`, { method: 'POST' });
  return res.json();
}

// ── Tailscale ────────────────────────────────────────────────────────────────

export async function getTailscale() {
  const res = await fetch('/api/tailscale');
  return res.json();
}

// ── Concepts ─────────────────────────────────────────────────────────────────

export async function getConcepts() {
  const res = await fetch('/api/concepts');
  return res.json();
}

// ── Activity feed ────────────────────────────────────────────────────────────

export async function getActivity() {
  const res = await fetch('/api/activity');
  return res.json();
}

// ── Audio sinks ──────────────────────────────────────────────────────────────

export async function getAudioSinks() {
  const res = await fetch('/api/audio/sinks');
  return res.json();
}

// ── SSH hosts ─────────────────────────────────────────────────────────────────

export async function getSshHosts() {
  const res = await fetch('/api/ssh/hosts');
  return res.json();
}

export async function addSshHost(data) {
  const res = await fetch('/api/ssh/hosts', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteSshHost(hostname) {
  const res = await fetch(`/api/ssh/hosts/${hostname}`, { method: 'DELETE' });
  return res.json();
}

export async function testSshHost(hostname) {
  const res = await fetch(`/api/ssh/test/${hostname}`, { method: 'POST' });
  return res.json();
}

// ── Spotify ───────────────────────────────────────────────────────────────────

export async function getSpotifyCurrent() {
  const res = await fetch('/api/spotify/current');
  return res.json();
}

export async function spotifyPlayPause() {
  const res = await fetch('/api/spotify/play-pause', { method: 'POST' });
  return res.json();
}

export async function spotifyNext() {
  const res = await fetch('/api/spotify/next', { method: 'POST' });
  return res.json();
}

export async function spotifyPrevious() {
  const res = await fetch('/api/spotify/previous', { method: 'POST' });
  return res.json();
}
