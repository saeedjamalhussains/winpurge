# Installing WinPurge

WinPurge is an app uninstaller, junk cleaner and privacy-settings manager for **Windows 10 and 11**. It works fully offline and moves everything it removes to the Recycle Bin.

There are two ways to install it:

| | **A. Run with Python** | **B. Build WinPurge.exe** |
|---|---|---|
| Best for | Your own PC | Sharing with other people |
| Needs Python on the PC | Yes | Only on the PC that builds it |
| Works with Smart App Control on | Yes ([why](#smart-app-control)) | Only if the build is signed |
| Time | About 5 minutes | About 10 minutes |

---

## A. Run with Python (recommended)

### 1. Install Python
1. Download Python **3.10 or newer** from **python.org**, not the Microsoft Store.
2. Run the installer. On the first screen, leave **"Use admin privileges when installing py.exe"** as it is, then choose **Customize installation**.
3. Make sure **"tcl/tk and IDLE"** and **"py launcher"** are ticked. WinPurge needs Tk for its window.
4. Finish the installation.

### 2. Get WinPurge
Download it from the repository, https://github.com/saeedjamalhussains/winpurge:

- **With Git:** `git clone https://github.com/saeedjamalhussains/winpurge.git`
- **Without Git:** click **Code → Download ZIP**, then right-click the ZIP → **Extract All…**

Put the folder somewhere permanent, for example `C:\Users\<you>\Apps\WinPurge`.

### 3. Start it
Double-click **`run_winpurge.pyw`**. No console window opens; WinPurge appears after a moment.

Or, from a terminal in that folder:

```bat
py -m winpurge
```

### 4. Add a shortcut (optional)
Right-click `run_winpurge.pyw` → **Show more options → Send to → Desktop (create shortcut)**. Rename the shortcut to "WinPurge". You can then right-click it → **Pin to Start**.

---

## B. Build WinPurge.exe

Do this on one Windows PC; the result runs on other PCs without Python.

### 1. Prepare
1. Install Python from python.org as in [A1](#1-install-python). Builds made with Microsoft Store or conda Python may include unsigned files.
2. Optional, for signing: install the **Windows SDK** (it includes `signtool`).

### 2. Build
Open a terminal in the WinPurge folder and run:

```bat
build_exe.bat
```

It installs PyInstaller, builds the app, then lists or signs the files (see [Signing](#3-sign-the-build-for-smart-app-control)). The result is:

```
dist\WinPurge\
├── WinPurge.exe
└── _internal\        ← required, keep it next to WinPurge.exe
```

At the end it prints the **SHA-256** of `WinPurge.exe`. Publish it next to your download so people can check their copy.

### 3. Sign the build (for Smart App Control)
Unsigned builds are blocked on PCs with Smart App Control on. To sign, set **one** of these before running `build_exe.bat`:

**Microsoft Artifact Signing** (an Azure service; check it's offered in your country):
```bat
set WINPURGE_SIGN_DLIB=C:\path\to\Azure.CodeSigning.Dlib.dll
set WINPURGE_SIGN_METADATA=C:\path\to\metadata.json
```

**A code-signing certificate from a public certificate authority** (`.pfx` file):
```bat
set WINPURGE_SIGN_PFX=C:\path\to\certificate.pfx
set WINPURGE_SIGN_PASSWORD=your-password
```

The script signs **every** unsigned `.exe`, `.dll` and `.pyd` in the build. A self-signed certificate won't work.

### 4. Install the .exe
1. Copy the whole `dist\WinPurge` folder to `%LOCALAPPDATA%\Programs\WinPurge`. Paste that path into File Explorer's address bar to open it.
2. Right-click `WinPurge.exe` → **Pin to Start**.

---

## First start

A short setup appears before WinPurge looks at anything:

1. **Welcome**: how WinPurge keeps your PC safe.
2. **Permissions**: tick what it may look at. Each permission explains exactly what it reads.

   | Permission | Starts ticked |
   |---|---|
   | Read the list of installed apps | Yes |
   | Look in cache and temporary folders | Yes |
   | Look for files left by removed apps | Yes |
   | Look inside project folders you choose | No |
   | Offer to remove an app's registry settings | No |
   | Show and change Windows privacy settings | No |

3. **Project folders**: only if you allowed it.
4. **Ready**: press **Finish**.

You can change these later with **Settings…** at the bottom of the window.

### Administrator rights
WinPurge runs as a normal user. A few things need administrator rights: removing leftovers in Program Files or ProgramData, and the Privacy settings marked *admin*. For those, press **Restart as administrator** at the bottom right and accept the Windows prompt.

---

## Windows security messages

### Smart App Control
*"Smart App Control blocked an app that may be unsafe"*

- **Running with Python (A):** this route goes through Python's own signed launcher, so it should not be blocked. If it is, right-click the downloaded ZIP → **Properties** → tick **Unblock** → **OK**, then extract it again.
- **WinPurge.exe (B):** the build isn't signed. Sign it as in [B3](#3-sign-the-build-for-smart-app-control), or use route A.

Don't turn Smart App Control off to get around this. On many Windows 11 versions it can't be turned back on without reinstalling Windows.

### SmartScreen
*"Windows protected your PC"*

This is shown for new apps that Windows hasn't seen much yet. Choose **More info → Run anyway** if you trust the source. Signed builds stop showing it once the certificate has a reputation.

### Firewall
WinPurge never connects to the internet, so Windows Firewall has nothing to ask about and needs no rule.

### Antivirus
If Microsoft Defender flags `WinPurge.exe`, report it as a false positive at https://www.microsoft.com/wdsi/filesubmission. Don't add exclusions or turn Defender off.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Double-clicking `run_winpurge.pyw` opens a text editor | Right-click it → **Open with → Choose another app → Python** (the rocket icon), tick **Always**. |
| "This Python has no Tk" | Run the Python installer again → **Modify** → tick **tcl/tk and IDLE**. |
| `'py' is not recognized` | Run the Python installer again → **Modify** → tick **py launcher**. |
| WinPurge shows an error, or closes | Details are saved in `%LOCALAPPDATA%\WinPurge\logs\winpurge.log`. Include that file when you report the problem. |
| Some items say "Access denied" | Press **Restart as administrator**, or close the program using those files. |
| Disk space didn't go up after cleaning | Removed items are in the Recycle Bin. Empty it to get the space back. |

---

## Updating

- **Route A with Git:** run `git pull` in the WinPurge folder.
- **Route A with a ZIP, or route B:** replace the folder with the new one.

Your settings are kept, because they're stored separately (see below).

## Uninstalling WinPurge

1. **If you changed privacy settings**, open the **Privacy** tab and press **Restore my original settings** first. Otherwise those settings stay as you set them.
2. Delete the WinPurge folder.
3. Delete its data folders, if you don't want to keep them:

| Folder | What's in it |
|---|---|
| `%APPDATA%\WinPurge` | `settings.json` (setup choices), `ignored.json` (hidden items), `privacy-backup.json` (original privacy settings), `registry-backups\` (`.reg` files; double-click one to restore it) |
| `%LOCALAPPDATA%\WinPurge\logs` | Error log |

WinPurge adds no services, scheduled tasks or startup entries, so there's nothing else to remove.
