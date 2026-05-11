#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Kill any existing Jarvis on port 5757
OLD=$(lsof -ti :5757 2>/dev/null)
if [ -n "$OLD" ]; then
  kill "$OLD" 2>/dev/null
  sleep 0.6
fi

# Build the React frontend if the dist directory doesn't exist yet
FRONTEND_DIST="$DIR/frontend/dist"
if [ ! -d "$FRONTEND_DIST" ]; then
  echo "Frontend dist not found — building React frontend..."
  cd "$DIR/frontend"
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found. Install Node.js to build the frontend."
    exit 1
  fi
  npm install && npm run build
  if [ $? -ne 0 ]; then
    echo "ERROR: Frontend build failed."
    exit 1
  fi
  cd "$DIR"
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

# Open in Google Chrome as an app window (no tabs/URL bar)
if command -v google-chrome >/dev/null 2>&1; then
  google-chrome --app=http://localhost:5757/ --new-window >/dev/null 2>&1 &
elif command -v chromium >/dev/null 2>&1; then
  chromium --app=http://localhost:5757/ --new-window >/dev/null 2>&1 &
elif command -v chromium-browser >/dev/null 2>&1; then
  chromium-browser --app=http://localhost:5757/ --new-window >/dev/null 2>&1 &
else
  xdg-open http://localhost:5757/ >/dev/null 2>&1 &
fi

# Keep process alive
wait "$APP_PID"
