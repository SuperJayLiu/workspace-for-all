@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo  学术工作台 · Windows 安装
echo  目录：%CD%
echo ================================================
echo.

rem 1) 找 Python -----------------------------------------------------------
set "PY="
for %%C in (python.exe py.exe) do (
  if not defined PY (
    where %%C >nul 2>&1 && set "PY=%%C"
  )
)
if not defined PY (
  echo ✗ 没找到 Python。
  echo   去 https://www.python.org/downloads/ 下载安装，
  echo   安装第一屏一定要勾上 "Add Python to PATH"，装完再双击本文件一次。
  echo.
  pause
  exit /b 1
)
if "%PY%"=="py.exe" set "PY=py -3"
for /f "delims=" %%V in ('%PY% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYV=%%V"
if not defined PYV (
  echo ✗ Python 装了但跑不起来，试着重装一次并勾选 Add Python to PATH。
  pause
  exit /b 1
)
echo ✓ Python：%PY% （%PYV%）

rem 2) 开机自启：往「启动」文件夹放一个静默启动的快捷方式 -------------------
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\学术工作台.vbs"
> "%VBS%" echo Set s = CreateObject("WScript.Shell")
>> "%VBS%" echo s.CurrentDirectory = "%CD%"
>> "%VBS%" echo s.Run "%PY% server.py --no-open", 0, False
if exist "%VBS%" (
  echo ✓ 开机自启已装好（登录后在后台静默运行，不弹黑框）
) else (
  echo △ 开机自启没装上，不影响手动启动——双击「启动.bat」即可
)

rem 3) 桌面快捷方式 ---------------------------------------------------------
set "LNKVBS=%TEMP%\mk_sw_lnk.vbs"
> "%LNKVBS%" echo Set s = CreateObject("WScript.Shell")
>> "%LNKVBS%" echo Set l = s.CreateShortcut(s.SpecialFolders("Desktop") ^& "\学术工作台.lnk")
>> "%LNKVBS%" echo l.TargetPath = "http://127.0.0.1:8765/"
>> "%LNKVBS%" echo l.Save
cscript //nologo "%LNKVBS%" >nul 2>&1
del "%LNKVBS%" >nul 2>&1
echo ✓ 桌面已放一个「学术工作台」快捷方式

rem 4) 起一次 ---------------------------------------------------------------
start "" /min %PY% server.py --no-open
timeout /t 3 >nul
start "" "http://127.0.0.1:8765/"

echo.
echo 装好了。以后：
echo   · 开机自动在后台跑，点桌面的「学术工作台」就能打开
echo   · 想让手机也能连：双击「局域网启动.bat」（要先在设置里填访问码）
echo   · 想取消自启：删掉 "%VBS%"
echo.
pause
