import os
import re
import sys
import json
import time
import shutil
import subprocess
import requests
import threading
import webbrowser
from collections import deque
from flask import Flask, request, jsonify, render_template, Response, send_from_directory
from dotenv import load_dotenv, set_key
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
import db
import ssh_metrics as ssh
import spotify as _spotify

load_dotenv()
db.init()
ssh.start_all_monitors()

app = Flask(__name__)
conversation_history = []

# ── Activity feed (rolling task list shown in the UI) ─────────────────────────
_activity_lock    = threading.Lock()
_activity_log     = deque(maxlen=40)           # recent events, newest last
_activity_seq     = 0
_activity_current = None                       # {"kind", "label", "started"} or None


def _activity_push(kind: str, label: str, extra: dict | None = None) -> None:
    """Append an event to the rolling activity log. Thread-safe."""
    global _activity_seq
    with _activity_lock:
        _activity_seq += 1
        evt = {"id": _activity_seq, "ts": time.time(), "kind": kind, "label": label}
        if extra:
            evt.update(extra)
        _activity_log.append(evt)


def _activity_set_current(kind: str | None, label: str = "") -> None:
    """Mark Jarvis' current top-level task (or clear it with kind=None)."""
    global _activity_current
    with _activity_lock:
        if kind is None:
            _activity_current = None
        else:
            _activity_current = {"kind": kind, "label": label, "started": time.time()}


def _activity_snapshot() -> dict:
    with _activity_lock:
        return {
            "current": dict(_activity_current) if _activity_current else None,
            "events":  list(_activity_log),
            "now":     time.time(),
        }


def get_config():
    return {
        "url":         os.getenv("LM_STUDIO_URL",    "http://100.x.x.x:1234"),
        "model":       os.getenv("LM_STUDIO_MODEL",   "local-model"),
        "api_key":     os.getenv("LM_STUDIO_API_KEY", ""),
        "piper_voice": os.getenv("PIPER_VOICE",       "en_US-amy-medium"),
        "tts_sink":    os.getenv("TTS_SINK",           ""),
        "tts_style":   os.getenv("TTS_STYLE",          "natural"),
        "tts_speed":   float(os.getenv("TTS_SPEED",    "1.0")),
        "tts_volume":  float(os.getenv("TTS_VOLUME",   "1.0")),
    }


def build_system_prompt():
    base = """You are Jarvis, a voice-operated home assistant on this Linux machine.
You have full tool access: shell, filesystem, processes, browser, web search, memory, topics, concepts, and Spotify control.

Rules — your replies are spoken aloud via TTS:
- 1-3 short sentences max. No markdown, asterisks, or bullet points.
- When asked about something online, ALWAYS web_search then browser_open the best result automatically.
- Use remember() for anything worth keeping long-term.
- Use add_topic() to track ongoing subjects of interest — add them proactively.
- Use remove_topic() to clean up resolved or irrelevant topics.
- Use add_concept() to push live insights to the sidebar (system alerts, findings, observations).
- Use set_active_topic() when the user shifts focus to a different subject.
- If an active topic exists, stay on that topic unless the user redirects you.
- Summarize what you did; don't explain how."""

    mem = db.search_memories("", limit=5)
    if mem:
        base += f"\n\nRecent memory context:\n{mem}"

    active = db.get_active_topic()
    if active:
        base += f"\n\nActive topic: {active['title']} — {active['description']}. Keep responses focused here."

    return base


def auth_headers(cfg):
    if cfg["api_key"]:
        return {"Authorization": f"Bearer {cfg['api_key']}"}
    return {}


# ── Tool-call fallback parser for Gemma ───────────────────────────────────────

_TC_RE = re.compile(
    r'(?:<tool_call>|```(?:json|tool_call)?)\s*(\{.*?"name"\s*:\s*"[^"]+".+?\})\s*(?:</tool_call>|```)',
    re.DOTALL,
)

def _parse_text_tool_calls(text: str) -> list:
    calls = []
    for m in _TC_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            calls.append({
                "id": f"tc_{len(calls)}",
                "function": {
                    "name":      obj.get("name", ""),
                    "arguments": json.dumps(obj.get("arguments", obj.get("parameters", {}))),
                },
            })
        except Exception:
            pass
    return calls


def call_lm(messages, cfg):
    resp = requests.post(
        f"{cfg['url']}/v1/chat/completions",
        headers=auth_headers(cfg),
        json={
            "model":       cfg["model"],
            "messages":    messages,
            "tools":       TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens":  2048,
            "stream":      False,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def run_tool(name, args):
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"Tool error ({name}): {e}"


def agent_loop(user_message, history):
    cfg      = get_config()
    messages = [{"role": "system", "content": build_system_prompt()}] + history + [
        {"role": "user", "content": user_message}
    ]
    tool_log = []

    for turn in range(12):
        _activity_set_current("thinking", f"LM call · turn {turn + 1}")
        t0  = time.time()
        msg = call_lm(messages, cfg)
        _activity_push("llm", f"turn {turn + 1} · {time.time() - t0:.1f}s")

        content    = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls and content:
            tool_calls = _parse_text_tool_calls(content)
            if tool_calls:
                content = _TC_RE.sub("", content).strip()

        if not tool_calls:
            return content, tool_log

        messages.append({**msg, "content": content or ""})
        for tc in tool_calls:
            name   = tc["function"]["name"]
            raw    = tc["function"].get("arguments", "{}")
            args   = json.loads(raw) if isinstance(raw, str) else raw
            _activity_set_current("tool", f"{name}")
            tt = time.time()
            result = run_tool(name, args)
            _activity_push("tool", f"{name} · {time.time() - tt:.1f}s")
            tool_log.append({"tool": name, "result": result[:300]})
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.get("id", "tc"),
                "content":      result,
            })

    return "Done.", tool_log


# ── Piper TTS — server-side via paplay, zero Chrome audio involvement ─────────

TARGET_SR = 48000
_tts_lock = threading.Lock()
_tts_proc = None


def _piper_bin() -> str:
    """Find the piper executable. Prefer the one sitting next to the running
    Python interpreter (works whether the venv is activated or not), then fall
    back to whatever's on PATH."""
    candidate = os.path.join(os.path.dirname(sys.executable), "piper")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    found = shutil.which("piper")
    if found:
        return found
    return "piper"


def _voices_dir():
    d = os.path.expanduser("~/.local/share/piper")
    os.makedirs(d, exist_ok=True)
    return d


def _piper_sr(config_path: str) -> int:
    try:
        with open(config_path) as f:
            return json.load(f).get("audio", {}).get("sample_rate", 22050)
    except Exception:
        return 22050


def _apply_style(samples, style: str, volume: float, speed: float):
    """Apply EQ style + volume + speed to float32 mono samples."""
    import numpy as np

    # Volume
    samples = samples * volume

    # Speed — resample (changes pitch too, intentional for simplicity)
    if abs(speed - 1.0) > 0.01:
        n_new   = int(len(samples) / speed)
        samples = np.interp(
            np.linspace(0, len(samples) - 1, n_new),
            np.arange(len(samples)),
            samples,
        )

    if style == "enhanced":
        # Subtle presence boost — FIR high-shelf at ~3kHz
        kernel = np.array([0.02, -0.05, 0.12, 1.0, 0.12, -0.05, 0.02])
        kernel /= kernel.sum()
        samples = np.convolve(samples, kernel, mode="same")

    elif style == "warm":
        # Gentle low-pass — softens harsh highs for Bluetooth
        n = 31
        fc = 5000 / TARGET_SR
        h  = np.sinc(2 * fc * (np.arange(n) - n // 2))
        h *= np.hanning(n)
        h /= h.sum()
        samples = np.convolve(samples, h, mode="same")

    elif style == "crisp":
        # High-pass removes muddiness + slight treble lift
        n  = 31
        fc = 200 / TARGET_SR
        h  = np.sinc(2 * fc * (np.arange(n) - n // 2))
        h *= np.hanning(n)
        h /= h.sum()
        hp = -h.copy()
        hp[n // 2] += 1.0
        samples = np.convolve(samples, hp, mode="same")

    elif style == "broadcast":
        # Bandpass 300–8000 Hz + normalize (classic radio/podcast sound)
        n   = 63
        lo  = 300  / TARGET_SR
        hi  = 8000 / TARGET_SR
        win = np.hanning(n)
        h_lo = np.sinc(2 * lo * (np.arange(n) - n // 2)) * win
        h_hi = np.sinc(2 * hi * (np.arange(n) - n // 2)) * win
        bp = h_hi - h_lo
        bp /= bp.sum() or 1
        samples = np.convolve(samples, bp, mode="same")
        # Normalize
        peak = np.max(np.abs(samples))
        if peak > 0:
            samples = samples / peak * 0.92

    # Final clip
    return np.clip(samples, -1.0, 1.0)


def _resample_stereo(raw: bytes, src_sr: int, style: str, volume: float, speed: float) -> bytes:
    import numpy as np
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    # Resample to 48kHz
    if src_sr != TARGET_SR:
        n_new   = int(len(samples) * TARGET_SR / src_sr)
        samples = np.interp(
            np.linspace(0, len(samples) - 1, n_new),
            np.arange(len(samples)),
            samples,
        )

    samples = _apply_style(samples, style, volume, speed)
    stereo  = np.column_stack([samples, samples])
    return (stereo * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


def _tts_speak(text: str):
    """Fire-and-forget TTS for background threads (SSH monitor events, etc.)."""
    def _run():
        cfg    = get_config()
        voice  = cfg["piper_voice"]
        vdir   = _voices_dir()
        model  = os.path.join(vdir, f"{voice}.onnx")
        config = os.path.join(vdir, f"{voice}.onnx.json")
        if not os.path.exists(model):
            return
        with _tts_lock:
            try:
                piper = subprocess.run(
                    [_piper_bin(), "--model", model, "--config", config, "--output-raw"],
                    input=text.encode(), capture_output=True, timeout=30,
                )
                if piper.returncode != 0 or not piper.stdout:
                    return
                pcm = _resample_stereo(
                    piper.stdout, _piper_sr(config),
                    style=cfg["tts_style"], volume=cfg["tts_volume"], speed=cfg["tts_speed"],
                )
                _paplay(pcm, cfg.get("tts_sink", "").strip())
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True, name="ssh-tts").start()


# Register so SSH monitor threads can speak through Jarvis
ssh.set_speech_callback(_tts_speak)


@app.route("/api/audio/sinks")
def audio_sinks():
    try:
        raw = subprocess.run(
            ["pactl", "list", "sinks"],
            capture_output=True, text=True, timeout=5
        ).stdout
        sinks = []
        current = {}
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                current["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"):
                current["desc"] = line.split(":", 1)[1].strip()
                sinks.append(dict(current))
                current = {}
        return jsonify({"sinks": sinks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _paplay(pcm: bytes, sink: str = ""):
    """Play raw s16le 48kHz stereo PCM via paplay. Falls back to system default if sink fails."""
    global _tts_proc
    base = ["paplay", "--raw", "--format=s16le", f"--rate={TARGET_SR}", "--channels=2"]
    sinks_to_try = [sink, ""] if sink else [""]
    for s in sinks_to_try:
        cmd = base + ([f"--device={s}"] if s else [])
        _tts_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        _tts_proc.communicate(input=pcm)
        if _tts_proc.returncode == 0:
            return
    # Both failed — not a hard error, audio just didn't play


@app.route("/tts/stop", methods=["POST"])
def tts_stop():
    global _tts_proc
    if _tts_proc and _tts_proc.poll() is None:
        _tts_proc.terminate()
    return ("", 204)


@app.route("/tts", methods=["POST"])
def tts():
    global _tts_proc
    text = request.json.get("text", "").strip()
    if not text:
        return ("", 204)
    text = re.sub(r"[*_`#>]", "", text)

    cfg   = get_config()
    voice = cfg["piper_voice"]
    vdir  = _voices_dir()
    model  = os.path.join(vdir, f"{voice}.onnx")
    config = os.path.join(vdir, f"{voice}.onnx.json")

    if not os.path.exists(model):
        _activity_push("error", f"tts: voice {voice} not downloaded")
        return jsonify({"error": "voice_not_downloaded", "voice": voice}), 503

    snippet = (text[:60] + "…") if len(text) > 60 else text
    _activity_set_current("speaking", snippet)
    _activity_push("speak", snippet)
    t_start = time.time()

    with _tts_lock:
        if _tts_proc and _tts_proc.poll() is None:
            _tts_proc.terminate()
            _tts_proc.wait()
        try:
            piper = subprocess.run(
                [_piper_bin(), "--model", model, "--config", config, "--output-raw"],
                input=text.encode(), capture_output=True, timeout=30,
            )
            if piper.returncode != 0 or not piper.stdout:
                raise RuntimeError(piper.stderr.decode())

            pcm = _resample_stereo(
                piper.stdout,
                _piper_sr(config),
                style=cfg["tts_style"],
                volume=cfg["tts_volume"],
                speed=cfg["tts_speed"],
            )

            sink = cfg.get("tts_sink", "").strip()
            _paplay(pcm, sink)
            _activity_push("speak-done", f"{time.time() - t_start:.1f}s")
            _activity_set_current(None)
            return ("", 204)
        except Exception as e:
            _activity_push("error", f"tts: {e}")
            _activity_set_current(None)
            return jsonify({"error": str(e)}), 500


@app.route("/tts/download", methods=["POST"])
def download_voice():
    voice = request.json.get("voice", "en_US-amy-medium")
    vdir  = _voices_dir()
    parts = voice.split("-")
    if len(parts) < 3:
        return jsonify({"error": "Invalid voice format"}), 400
    locale, name, quality = parts[0], parts[1], parts[2]
    lang  = locale.split("_")[0]
    base  = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    path  = f"{lang}/{locale}/{name}/{quality}/{voice}"

    def stream():
        import urllib.request
        for ext in [".onnx", ".onnx.json"]:
            url  = f"{base}/{path}{ext}"
            dest = os.path.join(vdir, f"{voice}{ext}")
            yield f"data: Downloading {voice}{ext}...\n\n"
            try:
                urllib.request.urlretrieve(url, dest)
                yield f"data: OK {dest}\n\n"
            except Exception as e:
                yield f"data: ERROR {e}\n\n"
        yield "data: DONE\n\n"

    return Response(stream(), mimetype="text/event-stream")


# ── Spotify ───────────────────────────────────────────────────────────────────

@app.route("/api/spotify/current")
def spotify_current():
    return jsonify(_spotify.now_playing())


@app.route("/api/spotify/play-pause", methods=["POST"])
def spotify_play_pause():
    msg = _spotify.play_pause()
    return jsonify({"status": msg, "now": _spotify.now_playing()})


@app.route("/api/spotify/next", methods=["POST"])
def spotify_next():
    msg = _spotify.next_track()
    return jsonify({"status": msg, "now": _spotify.now_playing()})


@app.route("/api/spotify/previous", methods=["POST"])
def spotify_previous():
    msg = _spotify.previous_track()
    return jsonify({"status": msg, "now": _spotify.now_playing()})


# ── Tailscale + SSH metrics ────────────────────────────────────────────────────

@app.route("/api/tailscale")
def tailscale_status():
    try:
        raw = subprocess.run(
            ["/usr/bin/tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if raw.returncode != 0:
            return jsonify({"error": raw.stderr.strip()}), 500
        data  = json.loads(raw.stdout)
        self_ = data.get("Self", {})
        peers = data.get("Peer", {})

        machines = [{
            "hostname": self_.get("HostName", "this machine"),
            "ip":       self_.get("TailscaleIPs", [""])[0],
            "online":   True,
            "self":     True,
            "os":       self_.get("OS", ""),
        }]
        for key, peer in peers.items():
            machines.append({
                "hostname": peer.get("HostName", key),
                "ip":       peer.get("TailscaleIPs", [""])[0],
                "online":   peer.get("Online", False),
                "self":     False,
                "os":       peer.get("OS", ""),
            })

        # Merge in latest SSH metrics for any configured host
        ssh_hosts = {h["hostname"]: h for h in ssh.list_hosts()}
        for m in machines:
            hn = m["hostname"]
            if hn in ssh_hosts:
                metrics = ssh.get_recent_metrics(hn)
                m["metrics"] = metrics
                m["ssh_configured"] = True
            else:
                m["metrics"] = None
                m["ssh_configured"] = False

        machines.sort(key=lambda m: (not m["self"], not m["online"], m["hostname"]))
        return jsonify({"machines": machines})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ssh/hosts", methods=["GET"])
def ssh_hosts():
    return jsonify({"hosts": ssh.list_hosts()})


@app.route("/api/ssh/hosts", methods=["POST"])
def ssh_add_host():
    d = request.json
    result = ssh.add_host(
        hostname=d["hostname"], ip=d["ip"],
        username=d.get("username", "root"),
        port=int(d.get("port", 22)),
        key_path=d.get("key_path", ""),
        password=d.get("password", ""),
    )
    return jsonify({"status": result})


@app.route("/api/ssh/hosts/<hostname>", methods=["DELETE"])
def ssh_remove_host(hostname):
    return jsonify({"status": ssh.remove_host(hostname)})


@app.route("/api/ssh/metrics/<hostname>", methods=["POST"])
def ssh_collect(hostname):
    result = ssh.collect_metrics(hostname)
    return jsonify(result)


@app.route("/api/ssh/metrics/all", methods=["POST"])
def ssh_collect_all():
    results = ssh.collect_all_metrics()
    return jsonify({"results": results})


@app.route("/api/ssh/run", methods=["POST"])
def ssh_run():
    d = request.json
    out = ssh.run_remote(d["hostname"], d["command"])
    return jsonify({"output": out})


@app.route("/api/ssh/test/<hostname>", methods=["POST"])
def ssh_test(hostname):
    host = ssh.get_host(hostname)
    if not host:
        return jsonify({"ok": False, "error": "Not configured"}), 404
    try:
        out = ssh.run_remote(hostname, "echo OK && uname -sr && uptime -p")
        ok  = "OK" in out
        return jsonify({"ok": ok, "output": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── Concepts — local + remote machine stats ────────────────────────────────────

@app.route("/api/concepts")
def concepts_status():
    import psutil

    # ── Local machine ──
    try:
        cpu  = psutil.cpu_percent(interval=0.3)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        import socket as _s
        hostname = _s.gethostname()
        db.add_concept(
            f"[{hostname}] CPU {cpu:.0f}% · RAM {mem.percent:.0f}% · Disk {disk.percent:.0f}%",
            "system", ttl_minutes=2, key=f"[{hostname}]"
        )
        if cpu  > 80: db.add_concept(f"⚠ [{hostname}] High CPU {cpu:.0f}%",  "warning", 5)
        if mem.percent > 88: db.add_concept(f"⚠ [{hostname}] RAM {mem.percent:.0f}%", "warning", 5)
        if disk.percent > 90: db.add_concept(f"⚠ [{hostname}] Disk full {disk.percent:.0f}%", "warning", 30)
    except Exception:
        pass

    # ── Remote SSH machines — use cached last metrics, non-blocking ──
    try:
        for host in ssh.list_hosts():
            hn = host["hostname"]
            m  = ssh.get_recent_metrics(hn)
            if not m:
                continue
            live_mark = "🟢" if m.get("live") else "🔴"
            db.add_concept(
                f"{live_mark} [{hn}] CPU {m['cpu_pct']}% · RAM {m['mem_pct']}% · Disk {m['disk_pct']}%",
                "network", ttl_minutes=3, key=f"[{hn}]"
            )
            if m.get("cpu_pct", 0)  > 80: db.add_concept(f"⚠ [{hn}] High CPU {m['cpu_pct']}%",  "warning", 5)
            if m.get("mem_pct", 0)  > 88: db.add_concept(f"⚠ [{hn}] RAM {m['mem_pct']}%",       "warning", 5)
            if m.get("disk_pct", 0) > 90: db.add_concept(f"⚠ [{hn}] Disk full {m['disk_pct']}%","warning", 30)
    except Exception:
        pass

    return jsonify({"concepts": db.get_concepts()})


# ── Topics ─────────────────────────────────────────────────────────────────────

@app.route("/api/topics")
def get_topics():
    return jsonify({"topics": db.get_topics()})


@app.route("/api/topics", methods=["POST"])
def create_topic():
    data  = request.json
    topic = db.add_topic(data.get("title", ""), data.get("description", ""))
    return jsonify(topic)


@app.route("/api/topics/<int:tid>", methods=["DELETE"])
def delete_topic(tid):
    return jsonify({"status": db.remove_topic(tid)})


@app.route("/api/topics/<int:tid>/activate", methods=["POST"])
def activate_topic(tid):
    # Toggle off if already active
    topics = db.get_topics()
    already = any(t["id"] == tid and t["active"] for t in topics)
    db.set_active_topic(0 if already else tid)
    return jsonify({"active": not already})


@app.route("/api/topics/<int:tid>/pin", methods=["POST"])
def pin_topic(tid):
    pinned = request.json.get("pinned", True)
    return jsonify({"status": db.pin_topic(tid, pinned)})


# ── Chat ───────────────────────────────────────────────────────────────────────

_CODE_RE = re.compile(r'```(\w*)\n?(.*?)```', re.DOTALL)

def _extract_code_blocks(text: str) -> list:
    blocks = []
    for m in _CODE_RE.finditer(text):
        code = m.group(2).strip()
        if code:
            blocks.append({"lang": m.group(1) or "text", "code": code})
    return blocks


@app.route("/chat", methods=["POST"])
def chat():
    global conversation_history
    data = request.json

    if data.get("reset"):
        conversation_history = []
        _activity_push("reset", "conversation cleared")
        return jsonify({"reply": "Conversation cleared.", "tools": [], "code_blocks": []})

    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    snippet = (user_message[:60] + "…") if len(user_message) > 60 else user_message
    _activity_push("user", snippet)
    _activity_set_current("thinking", snippet)

    t_start = time.time()
    try:
        reply, tool_log = agent_loop(user_message, conversation_history)
        code_blocks = _extract_code_blocks(reply)
        conversation_history.append({"role": "user",      "content": user_message})
        conversation_history.append({"role": "assistant", "content": reply})
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
        db.log_conversation(user_message, reply, [t["tool"] for t in tool_log])

        reply_snippet = (reply[:80] + "…") if len(reply) > 80 else reply
        _activity_push("reply", f"{reply_snippet}  ({time.time() - t_start:.1f}s)")
        _activity_set_current(None)
        return jsonify({"reply": reply, "tools": tool_log, "code_blocks": code_blocks})
    except Exception as e:
        _activity_push("error", f"chat: {e}")
        _activity_set_current(None)
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity")
def api_activity():
    return jsonify(_activity_snapshot())


# ── Config ─────────────────────────────────────────────────────────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")


@app.route("/api/config")
def api_config():
    return jsonify(get_config())


@app.route("/")
def index():
    dist_index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(dist_index):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("index.html", config=get_config())


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(os.path.join(FRONTEND_DIST, "assets"), filename)


@app.route("/config", methods=["POST"])
def save_config():
    data     = request.json
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        open(env_path, "w").close()
    for k, v in {
        "url":         "LM_STUDIO_URL",
        "model":       "LM_STUDIO_MODEL",
        "api_key":     "LM_STUDIO_API_KEY",
        "piper_voice": "PIPER_VOICE",
        "tts_sink":    "TTS_SINK",
        "tts_style":   "TTS_STYLE",
        "tts_speed":   "TTS_SPEED",
        "tts_volume":  "TTS_VOLUME",
    }.items():
        if k in data:
            set_key(env_path, v, data[k])
            os.environ[v] = data[k]
    return jsonify({"status": "saved"})


@app.route("/ping", methods=["POST"])
def ping():
    cfg = get_config()
    try:
        resp   = requests.get(f"{cfg['url']}/v1/models", headers=auth_headers(cfg), timeout=5)
        models = [m["id"] for m in resp.json().get("data", [])]
        return jsonify({"status": "online", "models": models})
    except Exception as e:
        return jsonify({"status": "offline", "error": str(e)}), 503


if __name__ == "__main__":
    port = 5757
    print(f"Jarvis at http://localhost:{port}")
    app.run(port=port, debug=False, threaded=True)
