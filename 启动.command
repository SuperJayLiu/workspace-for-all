#!/bin/bash
# macOS: double-click to start Scholar Workspace.
cd "$(dirname "$0")" || exit 1

for PY in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$PY" >/dev/null 2>&1 &&
     "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    exec "$PY" server.py
  fi
done

echo "Scholar Workspace requires Python 3.9 or newer."
echo "Install it from https://www.python.org/downloads/macos/ and try again."
read -r -p "Press Return to close…" _
exit 1
