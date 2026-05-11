#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Kill any existing Jarvis on port 5757
OLD=$(lsof -ti :5757 2>/dev/null)
if [ -n "$OLD" ]; then
  kill "$OLD" 2>/dev/null
  sleep 0.6
fi

# Start Jarvis server in background
"$DIR/.venv/bin/python" "$DIR/app.py" &
APP_PID=$!

# Wait until server responds (up to 12 seconds)
for i in $(seq 1 24); do
  sleep 0.5
  if curl -sf http://localhost:5757/ >/dev/null 2>&1; then
    break
  fi
done

# Open in browser — prefer firefox, fallback to xdg-open
if command -v firefox >/dev/null 2>&1; then
  firefox --new-window http://localhost:5757/ >/dev/null 2>&1 &
else
  xdg-open http://localhost:5757/ >/dev/null 2>&1 &
fi

# Keep process alive
wait "$APP_PID"
