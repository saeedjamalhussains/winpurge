@echo off
setlocal EnableDelayedExpansion
rem WinPurge installer: run from the WinPurge folder (double-click it).
rem  1. Finds Python 3.10+ with Tk, or installs Python 3.13 for you with winget.
rem  2. Adds WinPurge shortcuts to the Start menu and Desktop.
rem  3. Starts WinPurge.
rem It changes nothing else. Shortcuts point at Python's own signed launcher (pythonw.exe),
rem which is why WinPurge runs with Smart App Control on.

cd /d "%~dp0"
title WinPurge installer
echo.
echo  WinPurge installer
echo  ==================
echo.

if not exist "run_winpurge.pyw" (
  echo  run_winpurge.pyw is missing. Run install.bat from inside the WinPurge folder.
  goto :fail
)

rem ---------------------------------------------------------------- Python
call :find_python
if not errorlevel 1 goto :have_python

echo  Python 3.10 or newer was not found.
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo  winget is not available on this PC, so Python can't be installed automatically.
  echo  Install Python from https://www.python.org/downloads/  ^(keep "tcl/tk and IDLE"
  echo  and "py launcher" ticked^), then run install.bat again.
  goto :fail
)
echo.
echo  Installing Python 3.13 with winget.
echo  winget may ask you to accept its terms; answer Y to continue.
echo.
winget install --exact --id Python.Python.3.13
if errorlevel 1 (
  echo.
  echo  winget could not install Python. Install it from https://www.python.org/downloads/
  echo  and run install.bat again.
  goto :fail
)
rem This window still has the old PATH, so also look where installs put py.exe.
set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%SystemRoot%;%PATH%"
call :find_python
if errorlevel 1 (
  echo.
  echo  Python was installed, but this window can't see it yet.
  echo  Close this window and double-click install.bat again.
  goto :fail
)

:have_python
for /f "delims=" %%v in ('py -3 -c "import platform; print(platform.python_version())"') do set PYVER=%%v
echo  Found Python !PYVER!.

py -3 -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  This Python has no Tk, which WinPurge needs for its window.
  echo  Open Settings ^> Apps ^> Installed apps, find Python !PYVER!, choose Modify,
  echo  tick "tcl/tk and IDLE", finish, then run install.bat again.
  goto :fail
)

for /f "delims=" %%p in ('py -3 -c "import sys, os; print(os.path.join(sys.base_prefix, 'pythonw.exe'))"') do set "PYW=%%p"
if not exist "!PYW!" (
  echo  Could not find pythonw.exe next to Python. Reinstall Python from python.org.
  goto :fail
)

rem ---------------------------------------------------------------- Shortcuts
echo  Adding shortcuts to the Start menu and Desktop...
set "WP_TARGET=!PYW!"
set "WP_ARGS="%~dp0run_winpurge.pyw""
set "WP_DIR=%~dp0"
powershell -NoProfile -Command "$w = New-Object -ComObject WScript.Shell; foreach ($d in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { $s = $w.CreateShortcut((Join-Path $d 'WinPurge.lnk')); $s.TargetPath = $env:WP_TARGET; $s.Arguments = $env:WP_ARGS; $s.WorkingDirectory = $env:WP_DIR; $s.Description = 'WinPurge: app uninstaller and cleaner'; $s.Save() }" >nul 2>&1
if errorlevel 1 (
  echo  Couldn't create shortcuts here. You can still start WinPurge by double-clicking
  echo  run_winpurge.pyw, or right-click it ^> Send to ^> Desktop ^(create shortcut^).
) else (
  echo  Shortcuts added: Start menu ^> WinPurge, and Desktop ^> WinPurge.
)

rem ---------------------------------------------------------------- Start
echo.
echo  Starting WinPurge...
start "" "!PYW!" "%~dp0run_winpurge.pyw"
echo  Done. You can close this window.
echo.
timeout /t 5 >nul
exit /b 0

:fail
echo.
pause
exit /b 1

rem Sets errorlevel 0 if "py" runs Python 3.10 or newer.
:find_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
exit /b %errorlevel%
