import os
import re
import json
import subprocess
import requests
import threading
import webbrowser
from flask import Flask, request, jsonify, render_template, Response
from dotenv import load_dotenv, set_key
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
import db
import ssh_metrics as ssh

load_dotenv()
db.init()
ssh.start_all_monitors()

app = Flask(__name__)
conversation_history = []


def get_config():
    return {
        "url":         os.getenv("LM_STUDIO_URL",    "http://100.x.x.x:1234"),
        "model":       os.getenv("LM_STUDIO_MODEL",   "local-model"),
        "api_key":     os.getenv("LM_STUDIO_API_KEY", ""),
        "piper_voice": os.getenv("PIPER_VOICE",       "en_US-amy-medium"),
    }


def build_system_prompt():
    base = """You are Jarvis, a voice-operated home assistant on this Linux machine.
You have full tool access: shell, filesystem, processes, browser, web search, memory, topics, and concepts.

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

    for _ in range(12):
        msg        = call_lm(messages, cfg)
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
            result = run_tool(name, args)
            tool_log.append({"tool": name, "result": result[:300]})
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.get("id", "tc"),
                "content":      result,
            })

    return "Done.", tool_log


# ── Piper TTS — server-side playback via paplay ───────────────────────────────
# Audio never touches Chrome. Piper → resample → paplay → PipeWire natively.
# The browser just waits for the HTTP response to know speech is done.

TARGET_SR   = 48000
_tts_lock   = threading.Lock()   # one utterance at a time
_tts_proc   = None               # current paplay process (for interruption)


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


def _resample_stereo(raw: bytes, src_sr: int) -> bytes:
    import numpy as np
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if src_sr != TARGET_SR:
        n_new   = int(len(samples) * TARGET_SR / src_sr)
        samples = np.interp(
            np.linspace(0, len(samples) - 1, n_new),
            np.arange(len(samples)),
            samples,
        )
    stereo = np.column_stack([samples, samples])
    return (stereo * 32767).clip(-32768, 32767).astype(np.int16).tobytes()


@app.route("/tts/stop", methods=["POST"])
def tts_stop():
    global _tts_proc
    if _tts_proc and _tts_proc.poll() is None:
        _tts_proc.terminate()
    return ("", 204)


@app.route("/tts", methods=["POST"])
def tts():
    global _tts_proc
    text  = request.json.get("text", "").strip()
    voice = get_config()["piper_voice"]
    if not text:
        return ("", 204)
    text = re.sub(r"[*_`#>]", "", text)

    vdir   = _voices_dir()
    model  = os.path.join(vdir, f"{voice}.onnx")
    config = os.path.join(vdir, f"{voice}.onnx.json")

    if not os.path.exists(model):
        return jsonify({"error": "voice_not_downloaded", "voice": voice}), 503

    with _tts_lock:
        # Stop anything currently playing
        if _tts_proc and _tts_proc.poll() is None:
            _tts_proc.terminate()
            _tts_proc.wait()

        try:
            piper = subprocess.run(
                ["piper", "--model", model, "--config", config, "--output-raw"],
                input=text.encode(), capture_output=True, timeout=30,
            )
            if piper.returncode != 0 or not piper.stdout:
                raise RuntimeError(piper.stderr.decode())

            pcm = _resample_stereo(piper.stdout, _piper_sr(config))

            # Play via paplay — raw s16le 48kHz stereo, directly to PipeWire
            _tts_proc = subprocess.Popen(
                [
                    "paplay",
                    "--raw",
                    "--format=s16le",
                    f"--rate={TARGET_SR}",
                    "--channels=2",
                ],
                stdin=subprocess.PIPE,
            )
            _tts_proc.communicate(input=pcm)  # blocks until playback done
            return ("", 204)
        except Exception as e:
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


# ── Concepts (auto-generated system insights) ─────────────────────────────────

@app.route("/api/concepts")
def concepts_status():
    import psutil, datetime

    # Auto-generate live concepts from system state
    auto = []
    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        if cpu > 70:
            db.add_concept(f"High CPU: {cpu:.0f}%", "warning", ttl_minutes=5)
        if mem.percent > 85:
            db.add_concept(f"RAM critical: {mem.percent:.0f}%", "warning", ttl_minutes=5)
        if disk.percent > 90:
            db.add_concept(f"Disk almost full: {disk.percent:.0f}%", "warning", ttl_minutes=30)

        db.add_concept(f"CPU {cpu:.0f}% · RAM {mem.percent:.0f}% · Disk {disk.percent:.0f}%", "system", ttl_minutes=2)
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

@app.route("/chat", methods=["POST"])
def chat():
    global conversation_history
    data = request.json

    if data.get("reset"):
        conversation_history = []
        return jsonify({"reply": "Conversation cleared.", "tools": []})

    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    try:
        reply, tool_log = agent_loop(user_message, conversation_history)
        conversation_history.append({"role": "user",      "content": user_message})
        conversation_history.append({"role": "assistant", "content": reply})
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
        db.log_conversation(user_message, reply, [t["tool"] for t in tool_log])
        return jsonify({"reply": reply, "tools": tool_log})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Config ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", config=get_config())


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
