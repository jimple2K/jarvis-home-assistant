#!/bin/bash
# Run Jarvis on port 80 so phones can use http://<tailscale-name>/mobile
# Linux: binding to port 80 usually requires root — use one of:
#   sudo ./launch-dispatch-80.sh
#   sudo setcap 'cap_net_bind_service=+ep' "$(readlink -f .venv/bin/python)"   # then run without sudo
# Or keep default 5757 and use:  tailscale serve --bg 80 http://127.0.0.1:5757
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
export JARVIS_HOST="${JARVIS_HOST:-0.0.0.0}"
export JARVIS_PORT="${JARVIS_PORT:-80}"
exec "$DIR/.venv/bin/python" "$DIR/app.py"
