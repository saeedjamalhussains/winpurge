# Installing WinPurge

WinPurge removes apps completely, clears out junk and puts Windows' privacy settings in one place. It runs on **Windows 10 and 11**, works fully offline, and moves everything it removes to the Recycle Bin.

---

## Install

1. Download **`WinPurge-Setup-0.4.0.exe`**.
2. Double-click it, tick **Add a shortcut to the Desktop** if you want one, and press **Install**.
3. WinPurge opens when it's done.

That's it. No administrator rights and no Python are needed. WinPurge installs for your account only, adds itself to the Start menu, and appears in **Settings → Apps → Installed apps**.

### First start
WinPurge shows one welcome page before it looks at anything. Choose what it may look at, then press **Get started**. It then scans everything once and shows what you can safely get back.

| Permission | On at first |
|---|---|
| Read installed apps and command-line tools | Yes |
| Look in cache, temporary and developer tool folders | Yes |
| Look for files left by removed apps | Yes |
| Look for build folders in your coding projects | Yes |
| Look for large files in your folders | Yes |
| Offer to remove an app's registry settings | No |
| Show and change Windows privacy settings | No |

You can change these at any time under **Settings** in WinPurge.

### What each section does

| Section | What it does |
|---|---|
| **Overview** | One bar for the whole drive, split into App Caches, Dev Tools, Large Files, installed apps, leftovers and everything else. Click a row to open it. **Clean Safe Items** moves every *Safe* item to the Recycle Bin after one confirmation. Also shows what's in the Recycle Bin and how much WinPurge has cleaned so far. |
| **App Caches** | Windows junk (Temp, update downloads, crash dumps, error reports), browser caches and every app's own cache folders, one row per app. |
| **Dev Tools** | npm, pip, uv, NuGet, Gradle, Cargo, JetBrains, VS Code and other caches; Android emulators and system images; Docker Desktop's disk; and `node_modules`, `.venv`, `target`, `bin/obj` and build folders in projects you haven't changed for a while. |
| **Large Files** | Big files in Desktop, Documents, Downloads, Videos, Music and Pictures, filtered by kind, size and when you last used them. Finds downloaded AI models (Ollama, LM Studio, Hugging Face and more), disk images, virtual machines, leftover installers, unfinished downloads and exact **Duplicates**. |
| **Uninstaller** | Uninstall one app or several at once, then review what they left behind. **Leftovers** lists data from apps already gone. **Command-line tools** lists tools installed with npm, pipx, uv, Cargo or dotnet. |
| **Privacy** | Windows' telemetry and privacy settings, with switches that apply right away and **Restore originals**. |
| **Settings** | Appearance, automatic cleaning, how old a project must be, extra folders to scan, excluded folders, the right-click menu, the uninstall watcher, permissions, cleaning history, and **Uninstall WinPurge**. |

**Ratings:** *Safe* means it rebuilds itself and is ticked for you. *Check first* means it may hold something you want; it's never ticked for you and asks before you tick it. Greyed rows are in use or need administrator rights.

**Safety:**
- Everything goes to the **Recycle Bin**, and WinPurge never empties it.
- Running apps are asked to close the way clicking X does, never by force; if one won't close, its files stay.
- Projects you're working in (a git command running, a program running from the folder, or a change in the last few minutes) never appear.
- Files kept only in OneDrive are skipped, and OneDrive and Dropbox folders are never offered, because deleting there deletes on every device.

The only things removed permanently are command-line tools, which their own package manager uninstalls, and Steam games, which Steam deletes. WinPurge says so before either happens.

### Optional extras (off until you turn them on in Settings)
- **Uninstall from the right-click menu:** right-click any program or shortcut → **Uninstall with WinPurge**. On Windows 11 it's under **Show more options**. Dropping a program onto WinPurge does the same.
- **Review leftovers when an app is uninstalled:** a small background watcher notices when any app is uninstalled, even with WinPurge closed, and opens a review of just that app's leftovers. It stays quiet when nothing is left behind.
- **Clean automatically:** weekly, monthly or another interval. When a clean is due, WinPurge cleans the *Safe* items the next time it opens (the watcher reminds you). It never cleans in the background and never touches Large Files or *Check first* items.

### Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+1 to Ctrl+7 | Go to a section |
| Ctrl+R or F5 | Scan the current section |
| Ctrl+Shift+R | Scan everything |
| Ctrl+F | Search (Large Files, Uninstaller) |
| Alt+1 to Alt+3 | Filter: All, Safe, Check First |
| Ctrl+, | Settings |

A few things need administrator rights: system junk such as Windows Update downloads, leftovers in Program Files, and some privacy settings. For those, use **Restart as administrator** in Settings.

---

## If Windows warns you

| Message | What to do |
|---|---|
| **"Windows protected your PC"** (SmartScreen) | This appears for apps Windows hasn't seen much yet. If you got the installer from a source you trust, choose **More info → Run anyway**. |
| **"Smart App Control blocked an app"** | The installer you have isn't signed. Ask for a signed release, or build and sign it yourself (see below). Don't turn Smart App Control off: on many Windows 11 versions it can't be turned back on without reinstalling Windows. |
| **Firewall prompt** | There won't be one. WinPurge never connects to the internet. |
| **Antivirus warning** | Report it as a false positive at https://www.microsoft.com/wdsi/filesubmission. Don't add exclusions or turn protection off. |

To check that your download is the original, compare its SHA-256 with the one published next to the download:

```powershell
Get-FileHash .\WinPurge-Setup-0.4.0.exe -Algorithm SHA256
```

---

## Update
Run the newer `WinPurge-Setup-<version>.exe`. It replaces the old version and keeps your settings.

## Uninstall
In WinPurge: **Settings → Uninstall WinPurge**. It turns off the watcher and the right-click menu item, checks they stopped, then starts the uninstaller. You can also use **Settings → Apps → Installed apps → WinPurge → Uninstall**, which turns them off too.

- If WinPurge changed privacy settings, the uninstaller reminds you to restore them first, because they stay changed otherwise.
- It then asks whether to remove WinPurge's settings and logs. Backups of your original privacy and registry settings are kept either way.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| WinPurge shows an error or closes | The details are in `%LOCALAPPDATA%\WinPurge\logs\winpurge.log`. Include that file when you report the problem. |
| Some items say "Access denied" | Use **Restart as administrator**, or close the program that's using those files. |
| Disk space didn't go up after cleaning | Removed items are in the Recycle Bin. Empty it to get the space back. |
| The Privacy page says it's turned off | Turn on **Show and change Windows privacy settings** in WinPurge's **Settings**. |

Where WinPurge keeps its data:

| Folder | What's in it |
|---|---|
| `%APPDATA%\WinPurge` | `settings.json`, `history.json` (cleaning history), `ignored.json` (excluded folders), `privacy-backup.json` (your original privacy settings), `registry-backups\` (`.reg` files; double-click one to restore it) |
| `%LOCALAPPDATA%\WinPurge\logs` | Error log |

---

## For developers

### Build the installer
On a Windows PC:

```bat
winget install -e --id Python.Python.3.13
winget install -e --id JRSoftware.InnoSetup
```

Close and reopen the terminal, then in the WinPurge folder:

```bat
build.bat
```

It sets up a private build environment (`.build-venv`), builds the app with PyInstaller, signs it if signing is set up, and creates **`dist\WinPurge-Setup-<version>.exe`**. At the end it prints the installer's SHA-256 and says whether the build is signed.

### Sign it
Unsigned installers are blocked by Smart App Control. **[SIGNING.md](SIGNING.md)** explains how to get a trusted signature, through Microsoft Artifact Signing or a certificate authority. Once the environment variables it describes are set, `build.bat` signs the app, the installer and the uninstaller.

### Run from source
Double-click **`install.bat`**. It finds Python 3.10+ (or installs it with winget), adds WinPurge to the Start menu and Desktop, and starts it. Or run it directly:

```bat
py -m winpurge
```

Running from source uses Python's own signed launcher, so it works with Smart App Control on and no certificate.

### Project layout

| Path | What it is |
|---|---|
| `winpurge\app.py`, `pages.py`, `page_*.py`, `welcome.py`, `prompts.py` | The window, its sections, the welcome page and the watcher's pop-ups |
| `winpurge\caches.py`, `largefiles.py`, `leftovers.py`, `clitools.py`, `apps.py` | What each section scans for |
| `winpurge\trash.py`, `system.py`, `history.py`, `privacy.py` | Recycle Bin, running programs, history and schedule, privacy settings |
| `winpurge\shell.py`, `watcher.py` | Right-click menu, uninstall watcher |
| `winpurge\widgets.py`, `theme.py`, `gfx.py` | Look and feel: controls, colours, drawn graphics |
| `run_winpurge.pyw` | Starts the app; also the entry point for the build |
| `assets\winpurge.ico` | App icon, generated by `winpurge.gfx.write_ico` |
| `installer\` | Inno Setup script and the signing helper |
| `build.bat` | Builds and signs the installer |
| `install.bat` | Runs WinPurge from source |
| `version_info.txt` | File details for `WinPurge.exe`; keep it in step with `winpurge\__init__.py` |
