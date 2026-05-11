import os
import json
import requests
import threading
import webbrowser
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv, set_key
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

load_dotenv()

app = Flask(__name__)
conversation_history = []

SYSTEM_PROMPT = """You are Jarvis, a voice-operated home assistant running on this Linux machine.
You have full tool access: shell commands, filesystem, processes, web search, desktop notifications, and more.
Be concise — your responses are spoken aloud via TTS, so avoid markdown, bullet lists, or long text.
One to three sentences is ideal unless the user asks for more detail.
When you use tools, briefly summarize what you found or did."""


def get_config():
    return {
        "url":     os.getenv("LM_STUDIO_URL",   "http://100.x.x.x:1234"),
        "model":   os.getenv("LM_STUDIO_MODEL",  "local-model"),
        "api_key": os.getenv("LM_STUDIO_API_KEY", ""),
    }


def auth_headers(cfg):
    if cfg["api_key"]:
        return {"Authorization": f"Bearer {cfg['api_key']}"}
    return {}


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
            "max_tokens":  1024,
            "stream":      False,
        },
        timeout=60,
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
        return f"Tool error: {e}"


def agent_loop(user_message, history):
    cfg = get_config()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]
    tool_log = []

    for _ in range(10):  # max tool rounds
        msg = call_lm(messages, cfg)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return msg.get("content", ""), tool_log

        # Execute all tool calls this round
        messages.append(msg)
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            result = run_tool(name, args)
            tool_log.append({"tool": name, "args": args, "result": result[:300]})
            messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      result,
            })

    return "I've completed the requested tasks.", tool_log


@app.route("/")
def index():
    return render_template("index.html", config=get_config())


@app.route("/config", methods=["POST"])
def save_config():
    data = request.json
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        open(env_path, "w").close()
    for key, env_var in [("url", "LM_STUDIO_URL"), ("model", "LM_STUDIO_MODEL"), ("api_key", "LM_STUDIO_API_KEY")]:
        if key in data:
            set_key(env_path, env_var, data[key])
            os.environ[env_var] = data[key]
    return jsonify({"status": "saved"})


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
        # Keep last 20 turns
        if len(conversation_history) > 40:
            conversation_history = conversation_history[-40:]
        return jsonify({"reply": reply, "tools": tool_log})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ping", methods=["POST"])
def ping():
    cfg = get_config()
    try:
        resp = requests.get(f"{cfg['url']}/v1/models", headers=auth_headers(cfg), timeout=5)
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
