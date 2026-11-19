@echo off
setlocal EnableDelayedExpansion
rem Builds dist\WinPurge\WinPurge.exe (ship the whole dist\WinPurge folder).
rem
rem SMART APP CONTROL (Windows 11) blocks every .exe, .dll and .pyd that is not
rem signed by a certificate Windows trusts, unless Microsoft already knows the file.
rem A self-signed certificate does NOT count. To ship a build that SAC allows, sign
rem it with one of these (this script then signs every unsigned file in the build):
rem
rem   A) Microsoft Artifact Signing (formerly Trusted Signing), an Azure service:
rem        set WINPURGE_SIGN_DLIB=C:\path\to\Azure.CodeSigning.Dlib.dll
rem        set WINPURGE_SIGN_METADATA=C:\path\to\metadata.json
rem   B) A code-signing certificate from a public certificate authority (.pfx file):
rem        set WINPURGE_SIGN_PFX=C:\path\to\cert.pfx
rem        set WINPURGE_SIGN_PASSWORD=...
rem
rem Without signing, the build still works on PCs where Smart App Control is off
rem or in evaluation mode, and you can run WinPurge from source instead
rem (run_winpurge.pyw with Python from python.org, whose files are signed).
rem
rem Choices that make antivirus false alarms less likely:
rem  --onedir   a normal folder of files, instead of a single file that unpacks itself into Temp
rem  --noupx    no executable compression
rem  version_info.txt   real file properties

rem --- Use Python from python.org: its DLLs are signed, so fewer files need signing.
for /f "delims=" %%p in ('py -c "import sys; print(sys.base_prefix)"') do set PYHOME=%%p
echo Python: !PYHOME!
echo !PYHOME! | findstr /i "WindowsApps conda" >nul && (
  echo.
  echo WARNING: this is Microsoft Store or conda Python. Build with Python from python.org,
  echo          or the bundled files may be unsigned and blocked by Smart App Control.
  echo.
)

py -m pip install --upgrade pyinstaller || exit /b 1
py -m PyInstaller --noconfirm --clean --onedir --windowed --noupx ^
  --name WinPurge --version-file version_info.txt ^
  --collect-submodules winpurge ^
  run_winpurge.pyw || exit /b 1

rem --- Sign every file that isn't already signed by a trusted publisher.
where signtool >nul 2>&1
if errorlevel 1 (
  set HAVE_SIGNTOOL=0
) else (
  set HAVE_SIGNTOOL=1
)

set SIGN_ARGS=
if defined WINPURGE_SIGN_DLIB (
  set SIGN_ARGS=/fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib "!WINPURGE_SIGN_DLIB!" /dmdf "!WINPURGE_SIGN_METADATA!"
) else if defined WINPURGE_SIGN_PFX (
  set SIGN_ARGS=/fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f "!WINPURGE_SIGN_PFX!" /p "!WINPURGE_SIGN_PASSWORD!"
)

set UNSIGNED=0
if "!HAVE_SIGNTOOL!"=="0" (
  echo.
  echo signtool was not found ^(it comes with the Windows SDK^), so files can't be checked or signed.
  goto :done
)
for /r dist\WinPurge %%f in (*.exe *.dll *.pyd) do (
  signtool verify /pa /q "%%f" >nul 2>&1
  if errorlevel 1 (
    if defined SIGN_ARGS (
      signtool sign !SIGN_ARGS! "%%f" || (echo Signing failed: %%f & exit /b 1)
      echo Signed   %%~nxf
    ) else (
      set /a UNSIGNED+=1
      echo Unsigned %%~nxf
    )
  )
)

:done
echo.
echo Built dist\WinPurge\WinPurge.exe
if not "!UNSIGNED!"=="0" (
  echo.
  echo !UNSIGNED! file^(s^) are unsigned. Smart App Control will block this build.
  echo Set WINPURGE_SIGN_DLIB or WINPURGE_SIGN_PFX and build again, or run from source.
)
echo.
echo SHA-256 (publish this so people can check their download):
certutil -hashfile dist\WinPurge\WinPurge.exe SHA256 | findstr /v "hash CertUtil"
