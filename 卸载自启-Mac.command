#!/bin/bash
# 取消开机自启（工作台本身不会被删，随时还能手动启动）
PLIST="$HOME/Library/LaunchAgents/com.scholar.workspace.plist"
launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
pkill -f "server.py" 2>/dev/null
echo "已取消开机自启，并停掉了正在运行的服务。"
echo "以后想用，双击「启动.command」即可。"
read -r -p "按回车关闭…" _
