import os
import json
import requests
import threading
import webbrowser
from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv, set_key

load_dotenv()

app = Flask(__name__)
conversation_history = []


def get_config():
    return {
        "url": os.getenv("LM_STUDIO_URL", "http://100.x.x.x:1234"),
        "model": os.getenv("LM_STUDIO_MODEL", "local-model"),
        "api_key": os.getenv("LM_STUDIO_API_KEY", ""),
    }


def auth_headers(cfg):
    if cfg["api_key"]:
        return {"Authorization": f"Bearer {cfg['api_key']}"}
    return {}


SYSTEM_PROMPT = """You are Jarvis, a helpful home assistant. You are concise, intelligent, and proactive.
You help manage home automation, answer questions, and assist with daily tasks."""


@app.route("/")
def index():
    return render_template("index.html", config=get_config())


@app.route("/config", methods=["POST"])
def save_config():
    data = request.json
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        open(env_path, "w").close()
    if "url" in data:
        set_key(env_path, "LM_STUDIO_URL", data["url"])
        os.environ["LM_STUDIO_URL"] = data["url"]
    if "model" in data:
        set_key(env_path, "LM_STUDIO_MODEL", data["model"])
        os.environ["LM_STUDIO_MODEL"] = data["model"]
    if "api_key" in data:
        set_key(env_path, "LM_STUDIO_API_KEY", data["api_key"])
        os.environ["LM_STUDIO_API_KEY"] = data["api_key"]
    return jsonify({"status": "saved"})


@app.route("/chat", methods=["POST"])
def chat():
    global conversation_history
    data = request.json
    user_message = data.get("message", "")
    if data.get("reset"):
        conversation_history = []
        return jsonify({"reply": "Conversation reset."})

    cfg = get_config()
    conversation_history.append({"role": "user", "content": user_message})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    try:
        resp = requests.post(
            f"{cfg['url']}/v1/chat/completions",
            headers=auth_headers(cfg),
            json={
                "model": cfg["model"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]
        conversation_history.append({"role": "assistant", "content": reply})
        return jsonify({"reply": reply})
    except Exception as e:
        conversation_history.pop()
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
    url = f"http://localhost:{port}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Jarvis starting at {url}")
    app.run(port=port, debug=False)
