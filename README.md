# WinPurge

An app uninstaller and junk cleaner for Windows 10 and 11. Pure Python (standard library only), with a Tk window.

## First run
The first time it opens, WinPurge shows a setup wizard before it looks at anything:
1. **Welcome**: how it stays safe (works offline, asks before removing, uses the Recycle Bin, leaves Windows alone, no administrator rights needed).
2. **Permissions**: you tick what it may look at: installed apps, caches, leftovers, project folders, registry settings. Until setup is finished, nothing is allowed; cancelling closes the app.
3. **Project folders**: only if you allowed project scanning.
4. **Ready**: a summary of your choices.

Change these later with **Settings…** at the bottom of the window.

## What it does

**Apps tab**
- Lists installed programs from the same registry keys Settings uses (64-bit, 32-bit and per-user).
- **Uninstall…** runs the program's own uninstaller (MSI products with `msiexec /X`), waits for it, then looks for what it left behind:
  - folders in `AppData\Roaming`, `AppData\Local`, `AppData\Local\Programs`, `ProgramData`, `Program Files`, `Program Files (x86)`
  - Start menu shortcuts
  - `HKCU\Software\<Publisher>\<App>` registry keys (Check First, backed up to a `.reg` file before removal)
- A publisher folder (for example `ProgramData\Acme`) is only taken whole when no other app from that publisher is installed.

**Clean Up tab**
- **Caches**: Temp, crash dumps, shader cache, browser caches (Chrome, Edge, Brave, Firefox: cache only, never history, cookies or passwords), Discord, Slack, Teams, VS Code, npm, Yarn, pnpm, Bun, pip, uv, Poetry, NuGet, Gradle, Maven, Go, Cargo, Playwright, Hugging Face and more.
- **Old projects**: `node_modules`, `.next`, `__pycache__`, `.venv`, `target`, `bin`/`obj` and similar, in projects not edited for 30 days, inside folders you choose with **Project folders…**. Generic names like `bin` only count next to a `.csproj`/`.sln`.
- **Unused app data**: AppData/ProgramData folders that match no installed app and haven't changed in 90 days.

## Safety rules
- Everything goes to the **Recycle Bin**, so you can restore it until you empty it. Network and USB drives (no Recycle Bin) are skipped.
- Items rated **Check First** are never ticked automatically and ask before you tick them.
- Windows, Program Files, ProgramData, AppData and your profile folder themselves can never be removed.
- Symlinks and junctions are never followed.
- Right-click → **Don't suggest again** hides an item for good.

## Run it (Windows)
Install Python 3.10+ from python.org (includes Tk), then double-click `run_winpurge.pyw`, or:

```bat
py -m winpurge
```

Leftovers in Program Files or ProgramData need **Restart as administrator** (bottom right).

## Build the .exe
On Windows, run `build_exe.bat`. It produces `dist\WinPurge\WinPurge.exe` (ship the whole `dist\WinPurge` folder), which runs without Python installed.

### Firewall, antivirus and SmartScreen
- **Firewall:** WinPurge has no network code (a test enforces this), so Windows Firewall never asks about it and needs no rule.
- **Antivirus false alarms:** the build avoids the usual triggers: a normal folder build instead of a self-unpacking single file, no UPX compression, and real file properties. If Defender still flags it, report it as a false positive at https://www.microsoft.com/wdsi/filesubmission. Don't turn off Defender or add exclusions for it.
- **SmartScreen** ("Windows protected your PC") appears for any new unsigned app. Sign it with a code-signing certificate by setting `WINPURGE_SIGN_PFX` and `WINPURGE_SIGN_PASSWORD` before running `build_exe.bat`. Until then, people can choose **More info → Run anyway**.
- The build prints the SHA-256 of `WinPurge.exe`; publish it next to your download so people can check it.

## Tests
```bat
py -m unittest discover -s tests -t .
```
The tests build a fake Windows folder layout in a temp folder, so they also run on macOS and Linux.

## Settings and data
`%APPDATA%\WinPurge\settings.json` (setup choices and project folders), `ignored.json` (hidden items), `registry-backups\` (`.reg` files you can double-click to restore).
