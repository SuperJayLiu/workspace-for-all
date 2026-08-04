#!/bin/bash
# 学术工作台 · Mac 一键安装
# 双击本文件即可。它做四件事：检查环境、装好开机自启、生成快捷方式、启动一次。
# 想撤销开机自启，双击同目录下的「卸载自启-Mac.command」。

cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.scholar.workspace.plist"

echo "================================================"
echo " 学术工作台 · 安装"
echo " 目录：$DIR"
echo "================================================"
echo

# 1) Python 检查 -------------------------------------------------------------
PY=""
for c in python3 /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
    if [ -n "$v" ] && [ "${v%%.*}" -ge 3 ] && [ "${v#*.}" -ge 8 ]; then PY="$(command -v "$c")"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "✗ 没找到 Python 3.8 或更新的版本。"
  echo "  最省事的办法：打开「终端」，运行  xcode-select --install"
  echo "  装完以后再双击本文件一次。"
  echo; read -r -p "按回车关闭…" _; exit 1
fi
echo "✓ Python：$PY （$("$PY" -c 'import sys;print(sys.version.split()[0])')）"

# 2) 权限与快捷方式 -----------------------------------------------------------
chmod +x "$DIR/启动.command" "$DIR/局域网启动.command" "$DIR/卸载自启-Mac.command" 2>/dev/null
echo "✓ 启动脚本已授权"

# 3) 开机自启（LaunchAgent） ---------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.scholar.workspace</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$DIR/server.py</string><string>--no-open</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>$DIR/local/launch.log</string>
  <key>StandardErrorPath</key><string>$DIR/local/launch.err.log</string>
</dict></plist>
PLISTEOF
mkdir -p "$DIR/local"
launchctl unload "$PLIST" >/dev/null 2>&1
if launchctl load "$PLIST" 2>/dev/null; then
  echo "✓ 开机自启已装好（登录后自动在后台运行）"
else
  echo "△ 开机自启装配失败，不影响手动启动——双击「启动.command」即可"
fi

# 4) 起一次看看 ----------------------------------------------------------------
sleep 2
if curl -s -o /dev/null -m 3 "http://127.0.0.1:8765/api/ping"; then
  echo "✓ 服务已在运行"
else
  echo "… 正在启动"
  nohup "$PY" "$DIR/server.py" --no-open >/dev/null 2>&1 &
  sleep 3
fi
open "http://127.0.0.1:8765/" 2>/dev/null

echo
echo "装好了。以后："
echo "  · 开机就会自动在后台跑，浏览器打开 http://127.0.0.1:8765/ 即可"
echo "  · 想让手机也能连：双击「局域网启动.command」（要先在设置里填访问码）"
echo "  · 想取消自启：双击「卸载自启-Mac.command」"
echo
read -r -p "按回车关闭…" _
