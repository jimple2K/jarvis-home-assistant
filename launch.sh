#!/usr/bin/env bash
# Single entry for Jarvis: venv, Python deps, frontend build, server (detached), browser.
# Use from the .desktop file or: ./launch.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LOG="$DIR/.jarvis-server.log"
PID_FILE="$DIR/.jarvis.pid"
PY="$DIR/.venv/bin/python"
PORT="${JARVIS_PORT:-5757}"
HOST="${JARVIS_HOST:-127.0.0.1}"
if [[ -f "$DIR/.env" ]]; then
  _line=$(grep -E '^[[:space:]]*JARVIS_PORT=' "$DIR/.env" | tail -n1 || true)
  if [[ -n "${_line:-}" ]]; then
    _v="${_line#*=}"
    _v="${_v//\"/}"
    _v="${_v//\'/}"
    _v="${_v// /}"
    [[ -n "$_v" ]] && PORT="$_v"
  fi
  _line=$(grep -E '^[[:space:]]*JARVIS_HOST=' "$DIR/.env" | tail -n1 || true)
  if [[ -n "${_line:-}" ]]; then
    _v="${_line#*=}"
    _v="${_v//\"/}"
    _v="${_v//\'/}"
    _v="${_v// /}"
    [[ -n "$_v" ]] && HOST="$_v"
  fi
fi

# ── Python virtualenv ─────────────────────────────────────────────────────────
if [[ ! -x "$PY" ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3." >&2
    exit 1
  fi
  echo "Creating .venv…"
  python3 -m venv "$DIR/.venv"
  "$PY" -m pip install -q -U pip
  "$PY" -m pip install -q -r "$DIR/requirements.txt"
fi

echo "Ensuring Python dependencies…"
"$PY" -m pip install -q -r "$DIR/requirements.txt"

# ── Frontend (Vite) ─────────────────────────────────────────────────────────
FRONTEND_DIST="$DIR/frontend/dist"
if [[ ! -d "$FRONTEND_DIST" ]]; then
  echo "Building React frontend (first run)…"
  cd "$DIR/frontend"
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found. Install Node.js to build the frontend." >&2
    exit 1
  fi
  npm install
  npm run build
  cd "$DIR"
fi

# ── Stop previous instance on the same port ───────────────────────────────────
OLD="$(lsof -ti ":$PORT" 2>/dev/null || true)"
if [[ -n "${OLD:-}" ]]; then
  echo "Stopping existing process on port $PORT…"
  kill $OLD 2>/dev/null || true
  sleep 0.7
fi

# ── Start Flask (background, survives launcher exit) ─────────────────────────
echo "Starting Jarvis → http://${HOST}:${PORT}/ (log: $LOG)"
nohup env JARVIS_HOST="$HOST" JARVIS_PORT="$PORT" "$PY" "$DIR/app.py" >>"$LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" >"$PID_FILE"
disown 2>/dev/null || true

# ── Wait until HTTP responds ─────────────────────────────────────────────────
READY=0
for _ in $(seq 1 30); do
  sleep 0.5
  if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    READY=1
    break
  fi
done
if [[ "$READY" -ne 1 ]]; then
  echo "WARNING: server did not respond on port $PORT yet. Check $LOG"
fi

# ── Open UI ──────────────────────────────────────────────────────────────────
URL="http://127.0.0.1:${PORT}/"
if command -v google-chrome >/dev/null 2>&1; then
  google-chrome --app="$URL" --new-window >/dev/null 2>&1 &
elif command -v chromium >/dev/null 2>&1; then
  chromium --app="$URL" --new-window >/dev/null 2>&1 &
elif command -v chromium-browser >/dev/null 2>&1; then
  chromium-browser --app="$URL" --new-window >/dev/null 2>&1 &
else
  xdg-open "$URL" >/dev/null 2>&1 &
fi

echo "Jarvis is running (PID $NEW_PID). You can close this window."
exit 0
