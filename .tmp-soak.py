#!/usr/bin/env python3
"""Jarvis 10-prompt soak test with deliberate idle pauses."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:5757"

PROMPTS = [
    ("Hi Jarvis, how are you doing today?",                                          5),
    ("What time is it right now?",                                                   5),
    ("Tell me a quick one-sentence joke.",                                          30),  # long pause
    ("What is two hundred forty-seven times sixteen?",                               5),
    ("Who wrote Pride and Prejudice, in one sentence?",                              5),
    ("Briefly check this machine's CPU and tell me if anything looks concerning.",   5),
    ("Add a topic called soak test so I can track this conversation.",               5),
    ("Remember that we ran a 10-prompt soak test tonight.",                         40),  # long pause
    ("What is the capital of Australia, in one sentence?",                           5),
    ("Thanks Jarvis, we are done with the test.",                                    0),
]


def post_json(path: str, payload: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def stamp() -> str:
    return time.strftime("%H:%M:%S")


def main() -> int:
    print(f"[{stamp()}] === RESET ===", flush=True)
    post_json("/chat", {"reset": True})

    summary = []
    for i, (q, pause) in enumerate(PROMPTS, 1):
        print(f"\n[{stamp()}] --- Q{i}: {q}", flush=True)
        t0 = time.time()
        try:
            data = post_json("/chat", {"message": q})
            elapsed = time.time() - t0
            reply = (data.get("reply") or "").strip()
            tools = [t.get("tool") for t in (data.get("tools") or [])]
            err   = data.get("error")
        except Exception as e:
            elapsed = time.time() - t0
            reply, tools, err = "", [], f"client-exception: {e}"

        tool_str = ",".join(tools) if tools else "—"
        print(f"[{stamp()}]    elapsed={elapsed:6.2f}s  tools=[{tool_str}]", flush=True)
        if err:
            print(f"[{stamp()}]    ERROR: {err}", flush=True)
        clean = reply.replace("\n", " ")
        print(f"[{stamp()}]    A: {clean[:220]}{'…' if len(clean) > 220 else ''}", flush=True)

        summary.append({
            "n": i, "q": q, "elapsed": elapsed,
            "tools": tools, "reply": reply, "error": err,
        })

        if pause > 0:
            print(f"[{stamp()}]    ...sleeping {pause}s (void time)...", flush=True)
            time.sleep(pause)

    print(f"\n[{stamp()}] === DONE ===\n", flush=True)
    print("---- summary ----", flush=True)
    ok = 0
    for s in summary:
        status = "OK" if (s["reply"] and not s["error"]) else "FAIL"
        if status == "OK":
            ok += 1
        print(f"  Q{s['n']:2d}  {status:4s}  {s['elapsed']:6.2f}s  tools={s['tools']}", flush=True)
    print(f"\n  total OK: {ok}/{len(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
