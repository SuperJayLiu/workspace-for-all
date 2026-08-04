#!/usr/bin/env bash
# 一键跑全部体检。改完代码之前跑一遍，改完再跑一遍。
#
#   bash tests/跑全部.sh
#
# Python 部分零依赖，直接就能跑。
# JS 部分需要 Playwright（一次性安装：npm i -D playwright && npx playwright install chromium），
# 没装的话会自动跳过，不影响 Python 部分。
set -u
cd "$(dirname "$0")/.." || exit 1
PORT="${PORT:-8799}"
FAIL=0
PY_SANDBOX=""
SANDBOX=""

cleanup() {
  [ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null
  [ -n "${PY_SANDBOX:-}" ] && [ -d "$PY_SANDBOX" ] && rm -rf "$PY_SANDBOX"
  [ -n "${SANDBOX:-}" ] && [ -d "$SANDBOX" ] && rm -rf "$SANDBOX"
}
trap cleanup EXIT

# GNU coreutils provides `timeout`; macOS does not. Prefer it when available,
# accept Homebrew's `gtimeout`, and otherwise run without a wall-clock limit.
run_limited() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 400 "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout 400 "$@"
  else
    "$@"
  fi
}

echo "=== Python 体检 ==="
# Python tests exercise writes, recovery, queues and reports. Run them against
# a disposable copy too, so a failed test can never leave the user's data dirty.
PY_SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/工作台Python体检-XXXXXX")"
tar -cf - --exclude=local --exclude=attachments --exclude=.git \
         --exclude=__pycache__ --exclude='*.zip' . 2>/dev/null | (cd "$PY_SANDBOX" && tar -xf -)
mkdir -p "$PY_SANDBOX/local"
for f in tests/*.py; do
  out="$(run_limited python3 "$PY_SANDBOX/$f" 2>&1)"
  last="$(echo "$out" | tail -1)"
  if echo "$last" | grep -q "全部通过"; then
    printf '  ✓ %-24s %s\n' "$(basename "$f")" "$last"
  else
    printf '  ✗ %-24s %s\n' "$(basename "$f")" "$last"
    echo "$out" | tail -20 | sed 's/^/      /'
    FAIL=1
  fi
done
rm -rf "$PY_SANDBOX"
PY_SANDBOX=""

# 光有 playwright 包不够，浏览器本体也得在 —— 只查包的话，
# 浏览器没装时会报一堆看不懂的失败，让人以为是代码坏了
if ! node -e "
const {chromium}=require('playwright');
chromium.launch().then(b=>b.close()).then(()=>process.exit(0)).catch(()=>process.exit(1));
" >/dev/null 2>&1; then
  echo
  echo "=== JS 体检：跳过 ==="
  echo "    Playwright 或它的浏览器没装好。要跑界面测试的话："
  echo "      npm i -D playwright && npx playwright install chromium"
  echo "    Python 部分不受影响，上面那些才是核心逻辑。"
  exit $FAIL
fi

echo
echo "=== JS 体检 ==="

# 界面测试会真的去点按钮、加箴言、改设置。所以它**绝不能**连你正在用的那台服务 ——
# 早期就是这么干的，跑一遍体检，真实的 data/config.json 就被测试数据写花了。
# 现在的做法：把整个工程复制一份到临时目录，让测试服务跑那一份，
# 跑完连目录一起删。你的 data/ 从头到尾没人碰。
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/工作台体检-XXXXXX")"
# local/ 是生活数据和密钥，attachments/ 可能很大 —— 都不复制
tar -cf - --exclude=local --exclude=attachments --exclude=.git \
         --exclude=__pycache__ --exclude='*.zip' . 2>/dev/null | (cd "$SANDBOX" && tar -xf -)
mkdir -p "$SANDBOX/local"

# 找个没被占用的端口，免得撞上你自己开着的那台
for p in $(seq 8890 8920); do
  curl -s -m 1 "http://127.0.0.1:$p/api/ping" >/dev/null 2>&1 || { PORT="$p"; break; }
done
echo "    在 :$PORT 起一个沙盒服务（数据是副本，随后删掉）…"
python3 "$SANDBOX/server.py" --port "$PORT" --no-open >/tmp/test-server.log 2>&1 &
SRV=$!
UP=0
for i in $(seq 1 30); do
  curl -s -m 2 "http://127.0.0.1:$PORT/api/ping" >/dev/null 2>&1 && { UP=1; break; }
  sleep 1
done
if [ "$UP" -ne 1 ]; then
  echo "  ✗ 沙盒服务没起来，界面测试跳过。看看 /tmp/test-server.log"
  exit 1
fi
export TEST_URL="http://127.0.0.1:$PORT/"

for f in tests/*.js; do
  last="$(run_limited node "$f" 2>&1 | tail -1)"
  if echo "$last" | grep -q "全部通过"; then
    printf '  ✓ %-24s %s\n' "$(basename "$f")" "$last"
  else
    printf '  ✗ %-24s %s\n' "$(basename "$f")" "$last"
    FAIL=1
  fi
done

echo
[ $FAIL -eq 0 ] && echo "全部通过 ✓" || echo "有不通过的项 ✗"
exit $FAIL
