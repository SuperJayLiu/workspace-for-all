#!/usr/bin/env bash
# Run Scholar Workspace checks without touching the live workspace.
#
#   bash tests/跑全部.sh                 # Python, then UI when Playwright is ready
#   bash tests/跑全部.sh --python-only   # 14 core Python suites
#   bash tests/跑全部.sh --ui-only       # 6 Playwright suites; missing browser is an error
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MODE="all"
case "${1:-}" in
  "") ;;
  --python-only) MODE="python" ;;
  --ui-only) MODE="ui" ;;
  *) echo "usage: $0 [--python-only|--ui-only]" >&2; exit 2 ;;
esac

FAIL=0
PY_SANDBOX=""
UI_SANDBOX=""
SRV=""

cleanup() {
  [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true
  [ -n "$PY_SANDBOX" ] && [ -d "$PY_SANDBOX" ] && rm -rf "$PY_SANDBOX"
  [ -n "$UI_SANDBOX" ] && [ -d "$UI_SANDBOX" ] && rm -rf "$UI_SANDBOX"
}
trap cleanup EXIT INT TERM

run_limited() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 400 "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout 400 "$@"
  else
    "$@"
  fi
}

copy_workspace() {
  local dst="$1"
  tar -cf - --exclude=local --exclude=attachments --exclude=.git \
    --exclude=node_modules --exclude=__pycache__ --exclude='*.zip' . 2>/dev/null |
    (cd "$dst" && tar -xf -)
}

run_python() {
  echo "=== Python checks ==="
  local f out status
  for f in tests/*.py; do
    [ "$(basename "$f")" = "platform_smoke.py" ] && continue
    # Every suite receives a fresh factory-state copy. This prevents a failed
    # cleanup or deliberately corrupted fixture in one suite from affecting the next.
    PY_SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/scholar-python-tests-XXXXXX")" || { FAIL=1; return; }
    if ! copy_workspace "$PY_SANDBOX"; then
      echo "  ✗ could not create disposable test workspace"
      FAIL=1
      return
    fi
    mkdir -p "$PY_SANDBOX/local"
    out="$(run_limited python3 "$PY_SANDBOX/$f" 2>&1)"
    status=$?
    if [ "$status" -eq 0 ]; then
      printf '  ✓ %s\n' "$(basename "$f")"
    else
      printf '  ✗ %s (exit %s)\n' "$(basename "$f")" "$status"
      printf '%s\n' "$out" | tail -30 | sed 's/^/      /'
      FAIL=1
    fi
    rm -rf "$PY_SANDBOX"
    PY_SANDBOX=""
  done
}

browser_ready() {
  node -e '
    const pw = require("playwright");
    const name = process.env.PW_BROWSER || "chromium";
    if (!pw[name]) process.exit(2);
    const options = name === "chromium" && process.env.PW_CHROMIUM
      ? { executablePath: process.env.PW_CHROMIUM } : {};
    pw[name].launch(options).then(b => b.close()).then(() => process.exit(0)).catch(() => process.exit(1));
  ' >/dev/null 2>&1
}

run_ui() {
  local browser="${PW_BROWSER:-chromium}"
  if ! browser_ready; then
    echo "=== UI checks: browser unavailable ==="
    echo "Install with: npm ci && npx playwright install $browser"
    [ "$MODE" = "ui" ] && FAIL=1
    return
  fi

  echo "=== UI checks · $browser ==="
  UI_SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/scholar-ui-tests-XXXXXX")" || { FAIL=1; return; }
  if ! copy_workspace "$UI_SANDBOX"; then
    echo "  ✗ could not create disposable UI workspace"
    FAIL=1
    return
  fi
  mkdir -p "$UI_SANDBOX/local"

  local port log_file f out status
  port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')" || { FAIL=1; return; }
  log_file="$UI_SANDBOX/server-test.log"
  python3 "$UI_SANDBOX/server.py" --host 127.0.0.1 --port "$port" --no-open --test-mode >"$log_file" 2>&1 &
  SRV=$!

  if ! python3 - "$port" <<'PY'
import sys, time, urllib.request
url = f"http://127.0.0.1:{sys.argv[1]}/api/ping"
for _ in range(40):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                raise SystemExit(0)
    except Exception:
        time.sleep(0.25)
raise SystemExit(1)
PY
  then
    echo "  ✗ disposable server did not start"
    tail -40 "$log_file" | sed 's/^/      /'
    FAIL=1
    return
  fi

  export TEST_URL="http://127.0.0.1:$port/"
  for f in tests/*.js; do
    out="$(run_limited node "$f" 2>&1)"
    status=$?
    if [ "$status" -eq 0 ]; then
      printf '  ✓ %s\n' "$(basename "$f")"
    else
      printf '  ✗ %s (exit %s)\n' "$(basename "$f")" "$status"
      printf '%s\n' "$out" | tail -30 | sed 's/^/      /'
      FAIL=1
    fi
  done
}

[ "$MODE" != "ui" ] && run_python
[ "$MODE" != "python" ] && run_ui

echo
[ "$FAIL" -eq 0 ] && echo "All requested checks passed ✓" || echo "Some checks failed ✗"
exit "$FAIL"
