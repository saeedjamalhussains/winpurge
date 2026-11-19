"""Installed programs, read from the same registry keys that
Settings > Apps and Control Panel > Programs use."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .common import IS_WINDOWS, normalize

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


@dataclass
class App:
    key_name: str
    name: str
    publisher: str = ""
    version: str = ""
    install_location: str = ""
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    size_kb: int = 0
    scope: str = ""          # "machine" or "user"
    registry_path: str = ""  # e.g. HKLM\Software\...\Uninstall\{GUID}

    @property
    def norm(self) -> str:
        return normalize(self.name)

    @property
    def is_msi(self) -> bool:
        return bool(re.match(r"^\{[0-9A-F-]{36}\}$", self.key_name, re.I)) or \
            "msiexec" in self.uninstall_string.lower()


def _read_key(winreg, root, path, view):
    apps = []
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
    except OSError:
        return apps
    with key:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, sub) as sk:
                    def val(n, default=""):
                        try:
                            return winreg.QueryValueEx(sk, n)[0]
                        except OSError:
                            return default
                    name = val("DisplayName")
                    if not name or val("SystemComponent", 0) == 1:
                        continue
                    if val("ParentKeyName") or val("ReleaseType") in ("Update", "Hotfix", "Security Update"):
                        continue  # patches belong to their parent product
                    uninst = val("UninstallString")
                    if not uninst:
                        continue
                    apps.append(App(
                        key_name=sub,
                        name=str(name).strip(),
                        publisher=str(val("Publisher")).strip(),
                        version=str(val("DisplayVersion")).strip(),
                        install_location=str(val("InstallLocation")).strip().strip('"'),
                        uninstall_string=str(uninst).strip(),
                        quiet_uninstall_string=str(val("QuietUninstallString")).strip(),
                        size_kb=int(val("EstimatedSize", 0) or 0),
                    ))
            except OSError:
                continue
    return apps


def list_installed_apps() -> list[App]:
    """All programs with an uninstaller, from 64-bit, 32-bit and per-user keys."""
    if not IS_WINDOWS:
        return []
    import winreg
    seen: dict[tuple, App] = {}
    sources = [
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", winreg.KEY_WOW64_64KEY, "machine"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", winreg.KEY_WOW64_32KEY, "machine"),
        (winreg.HKEY_CURRENT_USER, "HKCU", 0, "user"),
    ]
    for root, root_name, view, scope in sources:
        for app in _read_key(winreg, root, UNINSTALL_KEY, view):
            app.scope = scope
            wow = "\\WOW6432Node" if view == winreg.KEY_WOW64_32KEY else ""
            app.registry_path = f"{root_name}\\Software{wow}\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app.key_name}"
            dedupe = (app.norm, app.version)
            seen.setdefault(dedupe, app)
    return sorted(seen.values(), key=lambda a: a.name.lower())


def build_uninstall_command(app: App) -> list[str] | str:
    """The command that runs the program's own uninstaller (interactive, so
    the user sees and answers its prompts)."""
    cmd = app.uninstall_string
    if app.is_msi:
        m = re.search(r"\{[0-9A-F-]{36}\}", cmd, re.I) or re.search(r"\{[0-9A-F-]{36}\}", app.key_name, re.I)
        if m:
            # /I would *repair or modify*; /X is uninstall.
            return ["msiexec.exe", "/X", m.group(0)]
    return cmd  # run through the shell as Windows stores it (often quoted path + args)


def run_uninstaller(app: App) -> int:
    """Run the program's uninstaller and wait for it. Returns its exit code."""
    cmd = build_uninstall_command(app)
    if isinstance(cmd, list):
        return subprocess.call(cmd)
    return subprocess.call(cmd, shell=True)


def still_installed(app: App) -> bool:
    return any(a.key_name == app.key_name and a.norm == app.norm for a in list_installed_apps())
