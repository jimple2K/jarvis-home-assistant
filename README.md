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

4. **Run Jarvis**
   ```bash
   python main.py
   ```

## Configuration

| Variable | Description |
|---|---|
| `LM_STUDIO_URL` | Tailscale IP + port of your LM Studio server (e.g. `http://100.x.x.x:1234`) |
| `LM_STUDIO_MODEL` | Model name as shown in LM Studio |

## Network

Make sure your AI server is connected to your Tailscale network and LM Studio's API server is bound to `0.0.0.0` (not just localhost) so it's reachable over Tailscale.
