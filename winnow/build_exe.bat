@echo off
rem Builds dist\Winnow.exe, a single file that runs without Python installed.
py -m pip install --upgrade pyinstaller || exit /b 1
py -m PyInstaller --noconfirm --onefile --windowed --name Winnow run_winnow.pyw || exit /b 1
echo.
echo Built dist\Winnow.exe
