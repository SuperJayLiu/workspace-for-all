@echo off
chcp 65001 >nul
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\学术工作台.vbs"
if exist "%VBS%" (del "%VBS%" & echo 已取消开机自启。) else (echo 本来就没装开机自启。)
taskkill /f /im python.exe >nul 2>&1
echo 已停掉正在运行的服务。以后想用，双击「启动.bat」即可。
pause
