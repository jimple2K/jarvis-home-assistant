# Jarvis Home Assistant

A local home assistant powered by [LM Studio](https://lmstudio.ai/) running on your AI server over [Tailscale](https://tailscale.com/).

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set your Tailscale IP and LM Studio model name.

3. **Start LM Studio** on your AI server with the local API server enabled (default port `1234`).

4. **Run Jarvis** (recommended: one script does venv, pip, frontend build, server, and opens the UI)

   ```bash
   ./launch.sh
   ```

   Or double-click **`Jarvis.desktop`** on your desktop — it runs the same `launch.sh` with `Path` set to this repo. Logs: `.jarvis-server.log`, PID: `.jarvis.pid`.

   Legacy CLI: `python main.py` (does not start the web UI).

## Configuration

| Variable | Description |
|---|---|
| `LM_STUDIO_URL` | Tailscale IP + port of your LM Studio server (e.g. `http://100.x.x.x:1234`) |
| `LM_STUDIO_MODEL` | Model name as shown in LM Studio |
| `JARVIS_HOST` | Bind address (default `127.0.0.1` — set to `0.0.0.0` for Tailscale / LAN) |
| `JARVIS_PORT` | HTTP port (default `5757`; use `80` with sudo or `tailscale serve`) |
| `MOBILE_DISPATCH_TOKEN` | Optional bearer token required by `/api/mobile/chat` |

## Network

Make sure your AI server is connected to your Tailscale network and LM Studio's API server is bound to `0.0.0.0` (not just localhost) so it's reachable over Tailscale.

## Mobile dispatch (phone / remote tasks)

Jarvis serves a **phone-friendly chat** at **`/mobile`** (short link **`/m`**). It uses the same LM Studio + tools as the desktop UI but keeps a **separate conversation thread** so quick remote tasks do not overwrite your orb session.

1. **Reach it over Tailscale** — bind Jarvis on your tailnet interface (or all interfaces) and open `/mobile` from the phone:

   ```bash
   export JARVIS_HOST=0.0.0.0
   export JARVIS_PORT=5757
   .venv/bin/python app.py
   ```

   On your phone (Tailscale on), open `http://<this-machine-tailscale-ip>:5757/mobile`.

2. **Port 80** (optional) — many phones assume HTTP on port 80. On Linux, binding to 80 often needs `sudo` or `setcap`; helper script:

   ```bash
   chmod +x launch-dispatch-80.sh
   sudo ./launch-dispatch-80.sh
   ```

   **Without root:** leave Jarvis on `5757` and expose 80 with [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve):

   ```bash
   tailscale serve --bg 80 http://127.0.0.1:5757
   ```

3. **Lock it down** — set a shared secret so random tailnet devices cannot chat:

   ```bash
   # in .env
   MOBILE_DISPATCH_TOKEN=choose-a-long-random-string
   ```

   The `/mobile` page will ask once for that token and send `Authorization: Bearer …` on each request.
