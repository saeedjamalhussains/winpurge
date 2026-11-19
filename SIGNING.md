# Signing WinPurge.exe

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

## 1. Microsoft Artifact Signing

Microsoft's own signing service, formerly called **Trusted Signing**. It's part of Azure. Microsoft checks your identity once, then signs your files in the cloud with a certificate that Windows trusts.

### Set it up (once)

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

### Create metadata.json

Make a file such as `C:\signing\metadata.json`:

```json
{
  "Endpoint": "https://eus.codesigning.azure.net",
  "CodeSigningAccountName": "your-account-name",
  "CertificateProfileName": "your-profile-name"
}
```

Use the endpoint for your account's region. It's shown on the account's **Overview** page; East US is `https://eus.codesigning.azure.net`.

### Sign a build

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

## 2. Certificate from a certificate authority

You buy a **code-signing certificate** (an "OV" certificate is enough) from a public certificate authority, for example Certum, Sectigo, SSL.com, DigiCert or GlobalSign. Some offer cheaper certificates for open-source developers.

Since June 2023, CAs only issue these with the private key on a **USB hardware token** or in the CA's **cloud signing service**. They no longer provide a `.pfx` file you can copy around.

### Get the certificate

1. Order a code-signing certificate and choose token or cloud delivery.
2. Complete the CA's identity check: ID documents for an individual, or business registration for an organization.
3. Install the CA's token driver or cloud signing app and sign in. The certificate then appears in Windows' certificate store.

### Find the certificate's thumbprint

In PowerShell:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-List Subject, NotAfter, Thumbprint
```

Copy the **Thumbprint** of your certificate.

### Sign a build

```bat
set WINPURGE_SIGN_THUMBPRINT=0123456789ABCDEF0123456789ABCDEF01234567
build.bat
```

The token or signing app may ask for your PIN, possibly once per file.

*An older certificate that you do have as a `.pfx` file can still be used:* `set WINPURGE_SIGN_PFX=C:\path\cert.pfx` and `set WINPURGE_SIGN_PASSWORD=...`.

---

## Check the result

```bat
signtool verify /pa /v dist\WinPurge-Setup-0.4.0.exe
signtool verify /pa /v dist\WinPurge\WinPurge.exe
```

Both should end with **Successfully verified**. You can also right-click either file → **Properties** → **Digital Signatures**.

`build.bat` lists any file it couldn't sign. Smart App Control blocks a build while any file is left unsigned.

## SmartScreen after signing

Smart App Control accepts a correctly signed build. SmartScreen's "Windows protected your PC" message can still appear for a while, until enough people have downloaded files signed with your certificate. That reputation builds up on its own, and you don't need to do anything.

## What about the Microsoft Store?

The Store signs apps itself when they're submitted as MSIX packages. But MSIX apps run in a container that keeps them from changing other apps' files and system settings, which is exactly what WinPurge's uninstaller, cleanup and Privacy tab need to do. Shipping WinPurge through the Store would mean reworking those features and passing Store review. Options 1 or 2 are the practical routes.
