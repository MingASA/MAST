#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${1:-8765}"
python3 "$SCRIPT_DIR/export_replay.py"
echo "MAST deterministic replay: http://localhost:${PORT}/?presentation=1"
cd "$SCRIPT_DIR"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
