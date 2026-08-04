#!/bin/bash
# 让手机 / 另一台电脑也能连进来（同一 Wi-Fi 或同一 VPN 下）
# 前提：先在「设置 → 远程访问与手机」里填过访问码。
cd "$(dirname "$0")" || exit 1
echo "以局域网模式启动。远程进来必须输访问码，而且默认只读。"
echo "按 Ctrl+C 停止。"
echo
python3 server.py --lan
read -r -p "按回车关闭…" _
