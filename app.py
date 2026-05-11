import os
import io
import re
import json
import subprocess
import requests
import threading
import webbrowser
from flask import Flask, request, jsonify, render_template, send_file, Response
from dotenv import load_dotenv, set_key
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
import memory as mem

load_dotenv()

app = Flask(__name__)
conversation_history = []

SYSTEM_PROMPT = """You are Jarvis, a voice-operated home assistant on this Linux machine.
You have full tool access: shell, filesystem, processes, browser control, web search, memory, and more.

Rules — your replies are spoken aloud:
- Keep replies to 1-3 short sentences. No markdown, no bullet points, no asterisks.
- When asked about something online, ALWAYS web_search then browser_open the best results automatically.
- When you learn something about the user or something worth keeping, use remember() to save it.
- At conversation start, recall() relevant memories to personalize your responses.
- When closing the browser say so briefly.
- Summarize what you did, not how."""


def get_config():
    return {
        "url":          os.getenv("LM_STUDIO_URL",      "http://100.x.x.x:1234"),
        "model":        os.getenv("LM_STUDIO_MODEL",     "local-model"),
        "api_key":      os.getenv("LM_STUDIO_API_KEY",   ""),
        "supabase_url": os.getenv("SUPABASE_URL",        ""),
        "supabase_key": os.getenv("SUPABASE_ANON_KEY",   ""),
        "piper_voice":  os.getenv("PIPER_VOICE",         "en_US-amy-medium"),
    }


def auth_headers(cfg):
    if cfg["api_key"]:
        return {"Authorization": f"Bearer {cfg['api_key']}"}
    return {}


# ── Tool-call parser (handles both native JSON and Gemma text output) ─────────

_TC_PATTERN = re.compile(
    r'(?:<tool_call>|```(?:json)?)\s*(\{.*?"name"\s*:\s*"[^"]+".+?\})\s*(?:</tool_call>|```)',
    re.DOTALL,
)
_PLAIN_JSON = re.compile(r'\{[^{}]*"name"\s*:\s*"([^"]+)"[^{}]*"arguments"\s*:\s*(\{[^{}]*\})[^{}]*\}', re.DOTALL)


def _extract_text_tool_calls(text: str) -> list:
    """Parse tool calls that Gemma emits as text rather than structured output."""
    calls = []
    for m in _TC_PATTERN.finditer(text):
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
    if not calls:
        for m in _PLAIN_JSON.finditer(text):
            try:
                calls.append({
                    "id": f"tc_{len(calls)}",
                    "function": {"name": m.group(1), "arguments": m.group(2)},
                })
            except Exception:
                pass
    return calls


def call_lm(messages, cfg):
    payload = {
        "model":       cfg["model"],
        "messages":    messages,
        "tools":       TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens":  2048,
        "stream":      False,
    }
    resp = requests.post(
        f"{cfg['url']}/v1/chat/completions",
        headers=auth_headers(cfg),
        json=payload,
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
    cfg = get_config()

    # Inject relevant memories into context
    memory_ctx = mem.search_memories(user_message)
    sys_content = SYSTEM_PROMPT
    if memory_ctx:
        sys_content += f"\n\n{memory_ctx}"

    messages = [{"role": "system", "content": sys_content}] + history + [
        {"role": "user", "content": user_message}
    ]
    tool_log = []

    for round_num in range(12):
        msg       = call_lm(messages, cfg)
        content   = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        # Fallback: detect text-embedded tool calls from Gemma
        if not tool_calls and content:
            tool_calls = _extract_text_tool_calls(content)
            if tool_calls:
                # Strip the raw tool-call JSON from the visible reply
                content = _TC_PATTERN.sub("", content).strip()

        if not tool_calls:
            return content, tool_log

        # Execute tool calls
        messages.append({**msg, "content": content or ""})
        for tc in tool_calls:
            name   = tc["function"]["name"]
            raw    = tc["function"].get("arguments", "{}")
            args   = json.loads(raw) if isinstance(raw, str) else raw
            result = run_tool(name, args)
            tool_log.append({"tool": name, "args": args, "result": result[:400]})
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.get("id", f"tc_{round_num}"),
                "content":      result,
            })

    return "I've completed the requested tasks.", tool_log


# ── Piper TTS ─────────────────────────────────────────────────────────────────

def _piper_voices_dir():
    """Return the directory where piper voice models live."""
    candidates = [
        os.path.expanduser("~/.local/share/piper"),
        os.path.join(os.path.dirname(__file__), "voices"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    base = os.path.expanduser("~/.local/share/piper")
    os.makedirs(base, exist_ok=True)
    return base


def _piper_model_path(voice: str) -> str:
    vdir  = _piper_voices_dir()
    model = os.path.join(vdir, f"{voice}.onnx")
    config = os.path.join(vdir, f"{voice}.onnx.json")
    return model, config


def synth_piper(text: str, voice: str) -> bytes | None:
    model, config = _piper_model_path(voice)
    if not os.path.exists(model):
        return None  # voice not downloaded yet
    try:
        proc = subprocess.run(
            ["piper", "--model", model, "--config", config, "--output-raw"],
            input=text.encode(),
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout  # raw 16-bit 22050Hz PCM
    except Exception:
        pass
    return None


@app.route("/tts", methods=["POST"])
def tts():
    text  = request.json.get("text", "").strip()
    voice = get_config().get("piper_voice", "en_US-amy-medium")
    if not text:
        return ("", 204)

    # Strip any leftover markdown symbols before speaking
    text = re.sub(r"[*_`#>]", "", text)

    audio = synth_piper(text, voice)
    if audio is None:
        return jsonify({"error": "voice_not_downloaded", "voice": voice}), 503

    # Return as WAV (add minimal 44-byte header for 22050Hz mono 16-bit)
    sample_rate = 22050
    num_channels = 1
    bits = 16
    data_size = len(audio)
    header = (
        b"RIFF" + (36 + data_size).to_bytes(4, "little") +
        b"WAVE" +
        b"fmt " + (16).to_bytes(4, "little") +
        (1).to_bytes(2, "little") +                          # PCM
        num_channels.to_bytes(2, "little") +
        sample_rate.to_bytes(4, "little") +
        (sample_rate * num_channels * bits // 8).to_bytes(4, "little") +
        (num_channels * bits // 8).to_bytes(2, "little") +
        bits.to_bytes(2, "little") +
        b"data" + data_size.to_bytes(4, "little")
    )
    return Response(header + audio, mimetype="audio/wav")


@app.route("/tts/voices", methods=["GET"])
def list_voices():
    vdir = _piper_voices_dir()
    voices = [f.replace(".onnx", "") for f in os.listdir(vdir) if f.endswith(".onnx")]
    return jsonify({"voices": voices, "dir": vdir})


@app.route("/tts/download", methods=["POST"])
def download_voice():
    voice = request.json.get("voice", "en_US-amy-medium")
    vdir  = _piper_voices_dir()
    model   = os.path.join(vdir, f"{voice}.onnx")
    config  = os.path.join(vdir, f"{voice}.onnx.json")
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    # Map voice name to HuggingFace path (lang/lang_LOCALE/name/quality/)
    parts = voice.split("-")  # e.g. en_US-amy-medium → ['en_US', 'amy', 'medium']
    if len(parts) >= 3:
        locale, name, quality = parts[0], parts[1], parts[2]
        lang = locale.split("_")[0]
        path = f"{lang}/{locale}/{name}/{quality}/{voice}"
    else:
        return jsonify({"error": "Invalid voice format"}), 400

    def stream():
        for ext, dest in [(".onnx", model), (".onnx.json", config)]:
            url = f"{base_url}/{path}{ext}"
            yield f"data: Downloading {url}\n\n"
            try:
                import urllib.request
                urllib.request.urlretrieve(url, dest)
                yield f"data: Saved {dest}\n\n"
            except Exception as e:
                yield f"data: ERROR {e}\n\n"
        yield "data: DONE\n\n"

    return Response(stream(), mimetype="text/event-stream")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", config=get_config())


@app.route("/config", methods=["POST"])
def save_config():
    data = request.json
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        open(env_path, "w").close()
    mapping = {
        "url":          "LM_STUDIO_URL",
        "model":        "LM_STUDIO_MODEL",
        "api_key":      "LM_STUDIO_API_KEY",
        "supabase_url": "SUPABASE_URL",
        "supabase_key": "SUPABASE_ANON_KEY",
        "piper_voice":  "PIPER_VOICE",
    }
    for key, env_var in mapping.items():
        if key in data:
            set_key(env_path, env_var, data[key])
            os.environ[env_var] = data[key]
    # Reinit supabase client if credentials changed
    if "supabase_url" in data or "supabase_key" in data:
        import memory
        memory._client = None
    return jsonify({"status": "saved"})


@app.route("/memory/init", methods=["POST"])
def init_memory():
    sb = mem._get_client()
    if not sb:
        return jsonify({"error": "Supabase not configured"}), 503
    try:
        # Use raw SQL via rpc or just try to insert to trigger table creation
        # Tables must be created via Supabase dashboard SQL editor
        return jsonify({"status": "ok", "connected": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/memory/status", methods=["GET"])
def memory_status():
    return jsonify({"connected": mem.is_connected()})


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

        # Log to Supabase
        mem.log_conversation(
            user_message, reply,
            tools_used=[t["tool"] for t in tool_log]
        )

        return jsonify({"reply": reply, "tools": tool_log})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    url  = f"http://localhost:{port}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Jarvis starting at {url}")
    app.run(port=port, debug=False)
