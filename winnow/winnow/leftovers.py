"""Files an app leaves behind: settings in AppData, data in ProgramData,
shortcuts in the Start menu, and folders whose app is no longer installed."""
from __future__ import annotations

import os
import time
from pathlib import Path

from .apps import App
from .common import CHECK, SAFE, IS_WINDOWS, Item, env_path, folder_size, is_protected, normalize

# Top-level AppData/ProgramData folders that belong to Windows itself or are
# shared by many programs. Never treated as one app's leftovers.
SYSTEM_FOLDERS = {
    "microsoft", "packages", "temp", "tmp", "programs", "windows", "comms",
    "connecteddevicesplatform", "d3dscache", "crashdumps", "history",
    "publishers", "virtualstore", "peerdistrepub", "placeholdertilelogofolder",
    "packagecache", "packagemanagement", "microsoftedge", "microsoftwindows",
    "regidcommicrosoft", "ssh", "usoshared", "usoprivate", "softwaredistribution",
    "intel", "nvidia", "nvidiacorporation", "amd", "ati", "realtek", "dell", "hp", "lenovo",
    "chocolatey", "scoop", "winget", "npm", "npmcache", "pip", "nuget",
    "applicationdata", "desktop", "documents", "startmenu", "templates",
    "mozilla", "google", "adobe", "apple", "appleinc", "jetbrains",   # vendor folders shared by several apps
    "fontcache", "iconcache", "identities", "wer", "ssl", "vs", "visualstudio",
}


def _roots(env) -> list[tuple[Path, str]]:
    pairs = [
        (env_path("APPDATA", env=env), "AppData\\Roaming"),
        (env_path("LOCALAPPDATA", env=env), "AppData\\Local"),
        (env_path("LOCALAPPDATA", "Programs", env=env), "AppData\\Local\\Programs"),
        (env_path("ProgramData", env=env), "ProgramData"),
        (env_path("ProgramFiles", env=env), "Program Files"),
        (env_path("ProgramFiles(x86)", env=env), "Program Files (x86)"),
        (env_path("APPDATA", "Microsoft", "Windows", "Start Menu", "Programs", env=env), "Start menu"),
        (env_path("ProgramData", "Microsoft", "Windows", "Start Menu", "Programs", env=env), "Start menu (all users)"),
    ]
    return [(p, label) for p, label in pairs if p is not None and p.is_dir()]


def _children(folder: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as it:
            return list(it)
    except OSError:
        return []


def app_names(app: App) -> set[str]:
    """Normalized names a folder for this app might use."""
    names = {app.norm}
    pub = normalize(app.publisher)
    if pub and app.norm.startswith(pub) and len(app.norm) - len(pub) >= 3:
        names.add(app.norm[len(pub):])          # "Mozilla Firefox" -> "firefox"
    if app.install_location:
        names.add(normalize(Path(app.install_location).name))
    return {n for n in names if len(n) >= 3}


def _owned_by_other(folder_norm: str, app: App, installed: list[App]) -> bool:
    for other in installed:
        if other is app or other.key_name == app.key_name:
            continue
        if folder_norm in app_names(other):
            return True
    return False


def find_leftovers(app: App, installed: list[App], env=None) -> list[Item]:
    """Folders and shortcuts matching `app`. Call after the app's own
    uninstaller ran; `installed` is the list of apps still present."""
    env = os.environ if env is None else env
    names = app_names(app)
    pub = normalize(app.publisher)
    found: dict[str, Item] = {}

    def add(path: str, where: str, level: str = SAFE, note: str = ""):
        if is_protected(path, env) or not os.path.exists(path):
            return
        key = os.path.normcase(os.path.normpath(path))
        if key in found:
            return
        found[key] = Item(
            path=path, label=f"{Path(path).name}  ({where})", category="Leftovers",
            level=level, size=folder_size(path, limit_seconds=5), note=note,
            checked=(level == SAFE),
        )

    if app.install_location and os.path.isdir(app.install_location):
        add(app.install_location, "install folder")

    for root, where in _roots(env):
        for entry in _children(root):
            n = normalize(Path(entry.name).stem if entry.is_file() else entry.name)
            if n in names and not _owned_by_other(n, app, installed):
                add(entry.path, where)
            elif pub and n == pub and entry.is_dir():
                # Publisher folder: take the app's subfolder, or the whole
                # publisher folder only if nothing else from that publisher is installed.
                subs = _children(Path(entry.path))
                matching = [s for s in subs if normalize(s.name) in names]
                others_from_pub = any(normalize(o.publisher) == pub and o.key_name != app.key_name for o in installed)
                if matching and (len(matching) < len(subs) or others_from_pub):
                    for s in matching:
                        add(s.path, f"{where}\\{entry.name}")
                elif matching or (subs == [] and not others_from_pub):
                    add(entry.path, where)
    return sorted(found.values(), key=lambda i: -i.size)


def find_registry_leftovers(app: App, installed: list[App]) -> list[Item]:
    """HKCU\\Software\\<Publisher>\\<App> or HKCU\\Software\\<App>. Registry keys
    cannot go to the Recycle Bin, so these are backed up to a .reg file first
    and are never ticked by default."""
    if not IS_WINDOWS:
        return []
    import winreg
    items = []
    names = app_names(app)
    pub = normalize(app.publisher)
    try:
        sw = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software")
    except OSError:
        return items
    with sw:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(sw, i)
            except OSError:
                break
            i += 1
            n = normalize(sub)
            if n in SYSTEM_FOLDERS or n in ("classes", "policies", "wow6432node"):
                continue
            if n in names and not _owned_by_other(n, app, installed):
                items.append(_reg_item(f"HKCU\\Software\\{sub}"))
            elif pub and n == pub:
                try:
                    with winreg.OpenKey(sw, sub) as pk:
                        j = 0
                        while True:
                            try:
                                child = winreg.EnumKey(pk, j)
                            except OSError:
                                break
                            j += 1
                            if normalize(child) in names:
                                items.append(_reg_item(f"HKCU\\Software\\{sub}\\{child}"))
                except OSError:
                    pass
    return items


def _reg_item(path: str) -> Item:
    return Item(path=path, label=path, category="Leftovers", level=CHECK, kind="registry",
                note="Registry settings. Backed up to a .reg file before removal.")


def _known_tokens(installed: list[App]) -> set[str]:
    tokens = set()
    for a in installed:
        tokens |= app_names(a)
        if a.publisher:
            tokens.add(normalize(a.publisher))
        first = normalize(a.name.split()[0]) if a.name.split() else ""
        if len(first) >= 4:
            tokens.add(first)
    return {t for t in tokens if t}


def find_orphans(installed: list[App], env=None, min_age_days: int = 90) -> list[Item]:
    """Top-level AppData/ProgramData folders that match no installed app and
    haven't changed for `min_age_days`. Always Check First: plenty of tools
    keep data there without registering an uninstaller."""
    env = os.environ if env is None else env
    tokens = _known_tokens(installed)
    cutoff = time.time() - min_age_days * 86400
    items = []
    roots = [r for r in _roots(env) if r[1] in ("AppData\\Roaming", "AppData\\Local", "ProgramData")]
    for root, where in roots:
        for entry in _children(root):
            if not entry.is_dir(follow_symlinks=False) or entry.name.startswith((".", "{")):
                continue
            n = normalize(entry.name)
            if not n or n in SYSTEM_FOLDERS:
                continue
            if n in tokens or any(len(t) >= 4 and (t.startswith(n) or n.startswith(t)) for t in tokens if len(n) >= 4):
                continue
            try:
                if entry.stat(follow_symlinks=False).st_mtime > cutoff:
                    continue
            except OSError:
                continue
            if is_protected(entry.path, env):
                continue
            items.append(Item(
                path=entry.path, label=f"{entry.name}  ({where})", category="Unused app data",
                level=CHECK, size=folder_size(entry.path, limit_seconds=3),
                note="No installed app matches this folder. It is app data, not a cache, "
                     "so it won't come back. Remove it only if you won't reinstall that app.",
            ))
    return sorted(items, key=lambda i: -i.size)
