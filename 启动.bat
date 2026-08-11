@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    py -3 server.py
    goto :end
  )
)

where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys;sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    python server.py
    goto :end
  )
)

echo Scholar Workspace requires Python 3.9 or newer.
echo Install it from https://www.python.org/downloads/windows/ and select "Add Python to PATH".

:end
pause
