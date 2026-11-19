@echo off
setlocal EnableDelayedExpansion
rem ===========================================================================
rem  Builds the WinPurge installer:  dist\WinPurge-Setup-<version>.exe
rem
rem  Needs: Python 3.10+ from python.org, and Inno Setup 6.3+
rem         (winget install -e --id JRSoftware.InnoSetup)
rem  Optional: signing. Set one of these first (see "Signing" in INSTALL.md):
rem         WINPURGE_SIGN_DLIB + WINPURGE_SIGN_METADATA   (Microsoft Artifact Signing)
rem         WINPURGE_SIGN_THUMBPRINT                       (certificate on a token)
rem         WINPURGE_SIGN_PFX + WINPURGE_SIGN_PASSWORD     (older .pfx file)
rem  Smart App Control blocks unsigned builds; the build tells you if it's unsigned.
rem
rem  build.bat sign <file>   signs one file (Inno Setup uses this for Setup.exe
rem                          and the uninstaller). Already-signed files are skipped.
rem ===========================================================================
if /i "%~1"=="sign" goto :sign_one
cd /d "%~dp0"
echo.
echo  Building WinPurge
echo  =================

rem ---------------------------------------------------------------- Python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo  Python 3.10 or newer is needed. Install it with:
  echo      winget install -e --id Python.Python.3.13
  exit /b 1
)
for /f "delims=" %%v in ('py -3 -c "import winpurge; print(winpurge.__version__)"') do set VERSION=%%v
for /f "delims=" %%p in ('py -3 -c "import sys; print(sys.base_prefix)"') do set PYHOME=%%p
echo  WinPurge !VERSION!, Python at !PYHOME!
echo %PYHOME% | findstr /i "WindowsApps conda" >nul && (
  echo  WARNING: this is Microsoft Store or conda Python. Use Python from python.org,
  echo           or the build may include unsigned files that Smart App Control blocks.
)

rem A private build environment keeps your own Python untouched.
if not exist ".build-venv\Scripts\python.exe" (
  echo  Creating build environment...
  py -3 -m venv .build-venv || exit /b 1
)
set PY=.build-venv\Scripts\python.exe
"%PY%" -m pip install --quiet --upgrade pip "pyinstaller>=6.6,<7" || exit /b 1

rem ---------------------------------------------------------------- App
echo  Building WinPurge.exe...
rem Icon and file details are generated from the code.
"%PY%" -c "from winpurge.ui import write_build_files; write_build_files(r'build\assets')" || exit /b 1
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN --onedir --windowed --noupx --optimize 2 ^
  --name WinPurge --icon build\assets\winpurge.ico --version-file build\assets\version_info.txt ^
  --collect-submodules winpurge --distpath dist --workpath build\pyinstaller ^
  --exclude-module unittest --exclude-module pydoc --exclude-module doctest --exclude-module pdb ^
  --exclude-module lib2to3 --exclude-module xmlrpc --exclude-module tkinter.test ^
  run_winpurge.pyw || exit /b 1

rem ---------------------------------------------------------------- Sign
set SIGN=0
if defined WINPURGE_SIGN_DLIB set SIGN=1
if defined WINPURGE_SIGN_THUMBPRINT set SIGN=1
if defined WINPURGE_SIGN_PFX set SIGN=1
set UNSIGNED=0
where signtool >nul 2>&1
if errorlevel 1 (
  if "!SIGN!"=="1" (
    echo  signtool was not found. Install the signing tools described in INSTALL.md.
    exit /b 1
  )
  set UNSIGNED=?
  goto :installer
)
echo  Checking signatures...
for /r dist\WinPurge %%f in (*.exe *.dll *.pyd) do (
  if "!SIGN!"=="1" (
    call "%~f0" sign "%%f" || (echo  Signing failed: %%~nxf & exit /b 1)
  ) else (
    signtool verify /pa /q "%%f" >nul 2>&1 || set /a UNSIGNED+=1
  )
)

rem ---------------------------------------------------------------- Installer
:installer
set ISCC=
for %%d in ("%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6" "%LOCALAPPDATA%\Programs\Inno Setup 6") do (
  if exist "%%~d\ISCC.exe" set "ISCC=%%~d\ISCC.exe"
)
if not defined ISCC (
  echo.
  echo  WinPurge.exe is built in dist\WinPurge, but Inno Setup isn't installed,
  echo  so there's no installer yet. Install it, then run build.bat again:
  echo      winget install -e --id JRSoftware.InnoSetup
  exit /b 1
)
echo  Building the installer...
set "SIGNCMD=cmd.exe /c call $q%~f0$q sign $f"
if "!SIGN!"=="1" (
  "!ISCC!" /Q /DAppVersion=!VERSION! /DSign "/Swp=!SIGNCMD!" WinPurge.iss || exit /b 1
) else (
  "!ISCC!" /Q /DAppVersion=!VERSION! WinPurge.iss || exit /b 1
)

rem ---------------------------------------------------------------- Done
set SETUP=dist\WinPurge-Setup-!VERSION!.exe
echo.
echo  Done:  !SETUP!
if "!SIGN!"=="1" (
  echo  Signed. Smart App Control and SmartScreen will check the signature.
) else (
  echo  NOT SIGNED. Smart App Control blocks unsigned apps. See "Signing" in INSTALL.md.
  if not "!UNSIGNED!"=="?" echo  ^(!UNSIGNED! unsigned files in the app^)
)
echo.
echo  SHA-256 ^(publish it next to the download^):
certutil -hashfile "!SETUP!" SHA256 | findstr /v "hash CertUtil"
exit /b 0

rem ---------------------------------------------------------------- build.bat sign <file>
:sign_one
if "%~2"=="" exit /b 2
signtool verify /pa /q "%~2" >nul 2>&1
if not errorlevel 1 exit /b 0
if defined WINPURGE_SIGN_DLIB (
  signtool sign /q /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib "!WINPURGE_SIGN_DLIB!" /dmdf "!WINPURGE_SIGN_METADATA!" "%~2"
  exit /b !errorlevel!
)
if defined WINPURGE_SIGN_THUMBPRINT (
  signtool sign /q /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /sha1 "!WINPURGE_SIGN_THUMBPRINT!" "%~2"
  exit /b !errorlevel!
)
if defined WINPURGE_SIGN_PFX (
  signtool sign /q /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f "!WINPURGE_SIGN_PFX!" /p "!WINPURGE_SIGN_PASSWORD!" "%~2"
  exit /b !errorlevel!
)
echo No signing certificate set. See "Signing" in INSTALL.md.
exit /b 1
