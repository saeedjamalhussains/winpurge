# Installing WinPurge

WinPurge removes apps completely, clears out junk and puts Windows' privacy settings in one place. It runs on **Windows 10 and 11**, works fully offline, and moves everything it removes to the Recycle Bin.

---

## Install

1. Download **`WinPurge-Setup-0.3.0.exe`**.
2. Double-click it, tick **Add a shortcut to the Desktop** if you want one, and press **Install**.
3. WinPurge opens when it's done.

That's it. No administrator rights and no Python are needed. WinPurge installs for your account only, adds itself to the Start menu, and appears in **Settings → Apps → Installed apps**.

### First start
WinPurge shows one welcome page before it looks at anything. Choose what it may look at, then press **Get started**:

| Permission | On at first |
|---|---|
| Read the list of installed apps | Yes |
| Look in cache and temporary folders | Yes |
| Look for files left by removed apps | Yes |
| Look inside project folders you choose | No |
| Offer to remove an app's registry settings | No |
| Show and change Windows privacy settings | No |

You can change these at any time under **Settings** in WinPurge.

### Using it
- **Overview:** press **Scan now**. Smart Scan shows how much can be cleaned, then **Review and clean** takes you to the list.
- **Apps:** select an app and press **Uninstall**. Its own uninstaller runs, then WinPurge shows what it left behind.
- **Clean Up:** items marked *Safe* are already ticked; *Check first* items ask before you tick them. **Move to Recycle Bin** removes the ticked items.
- **Privacy:** flip a switch to change a setting right away, or press **Make everything private**. **Restore originals** puts back everything WinPurge changed.

A few things need administrator rights: leftovers in Program Files and some privacy settings. For those, use **Restart as administrator** on the Privacy page or in Settings.

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
Get-FileHash .\WinPurge-Setup-0.3.0.exe -Algorithm SHA256
```

---

## Update
Run the newer `WinPurge-Setup-<version>.exe`. It replaces the old version and keeps your settings.

## Uninstall
**Settings → Apps → Installed apps → WinPurge → Uninstall.**

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
| `%APPDATA%\WinPurge` | `settings.json`, `ignored.json` (hidden items), `privacy-backup.json` (your original privacy settings), `registry-backups\` (`.reg` files; double-click one to restore it) |
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
| `winpurge\` | The app: `app.py` (window), `pages.py`, `welcome.py`, `widgets.py`, `theme.py`, `gfx.py` (drawn graphics), plus the scanning, cleaning and privacy logic |
| `run_winpurge.pyw` | Starts the app; also the entry point for the build |
| `assets\winpurge.ico` | App icon, generated by `winpurge.gfx.write_ico` |
| `installer\` | Inno Setup script and the signing helper |
| `build.bat` | Builds and signs the installer |
| `install.bat` | Runs WinPurge from source |
| `version_info.txt` | File details for `WinPurge.exe`; keep it in step with `winpurge\__init__.py` |
