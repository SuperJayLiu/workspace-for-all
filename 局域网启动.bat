@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 以局域网模式启动：手机 / 另一台电脑在同一网络下可以连进来。
echo 前提是先在「设置 - 远程访问与手机」里填过访问码。
echo 远程进来必须输访问码，而且默认只读。按 Ctrl+C 停止。
echo.
python server.py --lan
pause
