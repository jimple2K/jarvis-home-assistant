import os
import requests
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://100.x.x.x:1234")  # Replace with your Tailscale IP
MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

SYSTEM_PROMPT = """You are Jarvis, a helpful home assistant. You are concise, intelligent, and proactive.
You help manage home automation, answer questions, and assist with daily tasks."""


def chat(user_message: str, history: list[dict] = []) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]

    response = requests.post(
        f"{LM_STUDIO_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    print("Jarvis online. Type 'quit' to exit.\n")
    history = []

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye"):
            print("Jarvis: Goodbye.")
            break

        reply = chat(user_input, history)
        print(f"Jarvis: {reply}\n")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
