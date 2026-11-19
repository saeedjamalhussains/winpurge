@echo off
setlocal EnableDelayedExpansion
rem Signs one file with the certificate set in the environment (see SIGNING.md).
rem Files already signed by a trusted publisher are left alone.
rem Used by build.bat and by Inno Setup for Setup.exe and the uninstaller.
if "%~1"=="" exit /b 2
signtool verify /pa /q "%~1" >nul 2>&1
if not errorlevel 1 exit /b 0

if defined WINPURGE_SIGN_DLIB goto :artifact
if defined WINPURGE_SIGN_THUMBPRINT goto :thumb
if defined WINPURGE_SIGN_PFX goto :pfx
echo No signing certificate set. See SIGNING.md.
exit /b 1

:artifact
signtool sign /q /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib "!WINPURGE_SIGN_DLIB!" /dmdf "!WINPURGE_SIGN_METADATA!" "%~1"
exit /b %errorlevel%

:thumb
signtool sign /q /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /sha1 "!WINPURGE_SIGN_THUMBPRINT!" "%~1"
exit /b %errorlevel%

:pfx
signtool sign /q /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f "!WINPURGE_SIGN_PFX!" /p "!WINPURGE_SIGN_PASSWORD!" "%~1"
exit /b %errorlevel%
