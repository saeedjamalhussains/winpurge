# Installing WinPurge

WinPurge removes apps completely, clears out junk and puts Windows' privacy settings in one place. It runs on **Windows 10 and 11**, works fully offline, and moves everything it removes to the Recycle Bin.

---

## Install

1. Download **`WinPurge-Setup-0.4.1.exe`**.
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
Get-FileHash .\WinPurge-Setup-0.4.1.exe -Algorithm SHA256
```

---

## Update
Run the newer `WinPurge-Setup-<version>.exe`. If WinPurge is already installed, Setup's last page says which version, and Setup then:

1. Closes WinPurge and its background watcher.
2. Removes the old version with its own uninstaller, silently.
3. Installs the new version fresh.
4. Turns the uninstall watcher and right-click menu back on, if you had them on.

Your settings, cleaning history, excluded folders and privacy backups are kept. If the old version can't be removed, Setup stops and says so, so the old and new versions never end up mixed.

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

### Signing
Smart App Control and SmartScreen trust an app when its files carry a **code signature** from a certificate that chains to a root in **Microsoft's Trusted Root Program**. Once `WinPurge.exe` and every `.dll` and `.pyd` next to it are signed that way, Smart App Control lets it run.

`build.bat` signs every unsigned file in the app, plus the installer and its uninstaller. You only need to get a certificate and tell the script where it is.

| | **1. Microsoft Artifact Signing** | **2. Certificate from a certificate authority** |
|---|---|---|
| Who issues it | Microsoft | A public certificate authority (CA) |
| Cost | Monthly subscription | Yearly certificate, usually with a USB token |
| Identity check | Yes, through Microsoft | Yes, through the CA |
| Available to | Organizations and individual developers in supported countries only | Worldwide |
| Hardware | None, it's in the cloud | USB token, or the CA's cloud signing app |
| Script setting | `WINPURGE_SIGN_DLIB` + `WINPURGE_SIGN_METADATA` | `WINPURGE_SIGN_THUMBPRINT` |

Check current prices and eligibility on the provider's website before you start. They change.

**These don't work:**
- **Self-signed certificates.** Windows doesn't trust them.
- **Submitting the file to Microsoft Defender.** That clears false virus alarms but doesn't sign anything.
- **Turning Smart App Control off.** That only changes your own PC, and on many Windows 11 versions it can't be turned back on without reinstalling Windows.

---

#### 1. Microsoft Artifact Signing

Microsoft's own signing service, formerly called **Trusted Signing**. It's part of Azure. Microsoft checks your identity once, then signs your files in the cloud with a certificate that Windows trusts.

##### Set it up (once)

1. **Create an Azure account** at azure.microsoft.com and add a pay-as-you-go subscription.
2. **Install the tools** on the Windows PC that builds WinPurge:
   ```bat
   winget install -e --id Microsoft.AzureCLI
   winget install -e --id Microsoft.Azure.TrustedSigningClientTools
   ```
   The client tools include `signtool` and the signing library (`Azure.CodeSigning.Dlib.dll`). If `signtool` still isn't found afterwards, install the Windows SDK from Microsoft's website.
3. **Sign in and turn on the service** in a new terminal:
   ```bat
   az login
   az provider register --namespace Microsoft.CodeSigning
   ```
4. **Create an Artifact Signing account** in the Azure portal: search for **Artifact Signing** (or **Trusted Signing**) → **Create**. Pick a region and note it, for example *East US*.
5. **Verify your identity**: in the new account, open **Identity validation** → **New** → **Public**. Choose *Individual* or *Organization* and follow the steps. Microsoft reviews it, which can take several days.
6. **Create a certificate profile**: open **Certificate profiles** → **Create** → **Public Trust**, and pick the validated identity. Note the profile name.
7. **Give yourself permission to sign**: open **Access control (IAM)** → **Add role assignment**, choose the **Certificate Profile Signer** role for Artifact Signing (or Trusted Signing), and assign it to your own account.

##### Create metadata.json

Make a file such as `C:\signing\metadata.json`:

```json
{
  "Endpoint": "https://eus.codesigning.azure.net",
  "CodeSigningAccountName": "your-account-name",
  "CertificateProfileName": "your-profile-name"
}
```

Use the endpoint for your account's region. It's shown on the account's **Overview** page; East US is `https://eus.codesigning.azure.net`.

##### Sign a build

Open a terminal in the WinPurge folder:

```bat
az login
where /r "%LOCALAPPDATA%" Azure.CodeSigning.Dlib.dll
where /r "%ProgramFiles%" Azure.CodeSigning.Dlib.dll
```

Use the path that `where` prints:

```bat
set WINPURGE_SIGN_DLIB=C:\path\printed\above\Azure.CodeSigning.Dlib.dll
set WINPURGE_SIGN_METADATA=C:\signing\metadata.json
build.bat
```

Artifact Signing certificates last only a few days. Each signature is timestamped (the script does this), so signed files stay valid after the certificate expires. Just sign each new build.

---

#### 2. Certificate from a certificate authority

You buy a **code-signing certificate** (an "OV" certificate is enough) from a public certificate authority, for example Certum, Sectigo, SSL.com, DigiCert or GlobalSign. Some offer cheaper certificates for open-source developers.

Since June 2023, CAs only issue these with the private key on a **USB hardware token** or in the CA's **cloud signing service**. They no longer provide a `.pfx` file you can copy around.

##### Get the certificate

1. Order a code-signing certificate and choose token or cloud delivery.
2. Complete the CA's identity check: ID documents for an individual, or business registration for an organization.
3. Install the CA's token driver or cloud signing app and sign in. The certificate then appears in Windows' certificate store.

##### Find the certificate's thumbprint

In PowerShell:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-List Subject, NotAfter, Thumbprint
```

Copy the **Thumbprint** of your certificate.

##### Sign a build

```bat
set WINPURGE_SIGN_THUMBPRINT=0123456789ABCDEF0123456789ABCDEF01234567
build.bat
```

The token or signing app may ask for your PIN, possibly once per file.

*An older certificate that you do have as a `.pfx` file can still be used:* `set WINPURGE_SIGN_PFX=C:\path\cert.pfx` and `set WINPURGE_SIGN_PASSWORD=...`.

---

#### Check the result

```bat
signtool verify /pa /v dist\WinPurge-Setup-0.4.1.exe
signtool verify /pa /v dist\WinPurge\WinPurge.exe
```

Both should end with **Successfully verified**. You can also right-click either file → **Properties** → **Digital Signatures**.

`build.bat` lists any file it couldn't sign. Smart App Control blocks a build while any file is left unsigned.

#### SmartScreen after signing

Smart App Control accepts a correctly signed build. SmartScreen's "Windows protected your PC" message can still appear for a while, until enough people have downloaded files signed with your certificate. That reputation builds up on its own, and you don't need to do anything.

#### What about the Microsoft Store?

The Store signs apps itself when they're submitted as MSIX packages. But MSIX apps run in a container that keeps them from changing other apps' files and system settings, which is exactly what WinPurge's uninstaller, cleanup and Privacy tab need to do. Shipping WinPurge through the Store would mean reworking those features and passing Store review. Options 1 or 2 are the practical routes.

### Run from source
Double-click **`install.bat`**. It finds Python 3.10+ (or installs it with winget), adds WinPurge to the Start menu and Desktop, and starts it. Or run it directly:

```bat
py -m winpurge
```

Running from source uses Python's own signed launcher, so it works with Smart App Control on and no certificate.

### Project layout

| Path | What it is |
|---|---|
| `winpurge\__init__.py` | Version, and how WinPurge starts (window, watcher, right-click uninstall) |
| `winpurge\core.py` | Basics: items, settings, permissions, Recycle Bin, history and schedule, error log, Windows helpers |
| `winpurge\scan.py` | What it looks for: installed apps, caches, dev tools, leftovers, large files, command-line tools |
| `winpurge\windows.py` | Privacy settings, right-click menu, uninstall watcher |
| `winpurge\ui.py` | Look and feel: colours, fonts, icons, drawn graphics, widgets |
| `winpurge\app.py` | The window, its sections, the welcome page and pop-ups |
| `run_winpurge.pyw` | Starts the app; also the entry point for the build |
| `build.bat` | Builds and signs the installer (the icon and file details are generated) |
| `WinPurge.iss` | The installer, including clean upgrades |
| `install.bat` | Runs WinPurge from source |
