#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Kill any existing Jarvis instance on port 5757
OLD_PID=$(lsof -ti :5757 2>/dev/null)
if [ -n "$OLD_PID" ]; then
  kill "$OLD_PID" 2>/dev/null
  sleep 0.8
fi

exec "$DIR/.venv/bin/python" "$DIR/app.py"
