@echo off
rem Builds dist\WinPurge\WinPurge.exe.
rem
rem Choices that make antivirus false alarms less likely:
rem  --onedir  : a normal folder of files. One-file builds unpack themselves into
rem              Temp at every start, which some scanners treat as suspicious.
rem  --noupx   : no UPX compression. Packed executables are a common false-alarm trigger.
rem  version_info.txt : real file properties (name, version, description).
rem  Signing   : set WINPURGE_SIGN_PFX (and WINPURGE_SIGN_PASSWORD) to sign with your
rem              code-signing certificate. Signed apps stop SmartScreen's
rem              "Windows protected your PC" warning once the certificate has reputation.

py -m pip install --upgrade pyinstaller || exit /b 1
py -m PyInstaller --noconfirm --clean --onedir --windowed --noupx ^
  --name WinPurge --version-file version_info.txt run_winpurge.pyw || exit /b 1

if defined WINPURGE_SIGN_PFX (
  signtool sign /f "%WINPURGE_SIGN_PFX%" /p "%WINPURGE_SIGN_PASSWORD%" /fd SHA256 ^
    /tr http://timestamp.digicert.com /td SHA256 dist\WinPurge\WinPurge.exe || exit /b 1
  echo Signed dist\WinPurge\WinPurge.exe
) else (
  echo Not signed: set WINPURGE_SIGN_PFX to sign.
)

echo.
echo Built dist\WinPurge\WinPurge.exe
echo SHA-256 (publish this so people can check their download):
certutil -hashfile dist\WinPurge\WinPurge.exe SHA256 | findstr /v "hash CertUtil"
