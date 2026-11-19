"""Windows integration, all per-user (no administrator needed) and all off
until you turn it on in Settings:

- "Uninstall with WinPurge" in the right-click menu of programs (.exe) and
  shortcuts (.lnk). On Windows 11 it's under "Show more options".
- The uninstall watcher, started when you sign in (HKCU ...\\Run).

remove_integrations() turns everything off again; the uninstaller calls it."""
from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

from .common import IS_WINDOWS, normalize
from .trash import app_data_dir

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WinPurge Watcher"
MENU_KEYS = (r"Software\Classes\exefile\shell\WinPurge.Uninstall",
             r"Software\Classes\lnkfile\shell\WinPurge.Uninstall")
WATCHER_PID = "watcher.pid"


def self_command(*args: str) -> list[str]:
    """How to start WinPurge with `args`, installed or run from source.
    From source it uses pythonw.exe, so no console window opens."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    script = str(Path(__file__).resolve().parent.parent / "run_winpurge.pyw")
    return [w if os.path.exists(w) else exe, script, *args]


def launch(*args: str):
    """Start another WinPurge process, detached from this one."""
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0
    subprocess.Popen(self_command(*args), creationflags=flags, close_fds=True)


def _icon_path() -> str:
    return self_command()[0]


# ---------------------------------------------------------------- registry helpers

def _set(path: str, name: str, value: str):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _get(path: str, name: str) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _delete_tree(path: str):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    _delete_tree(path + "\\" + winreg.EnumKey(k, 0))
                except OSError:
                    break
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


# ---------------------------------------------------------------- right-click menu

def context_menu_enabled() -> bool:
    return IS_WINDOWS and _get(MENU_KEYS[0] + r"\command", "") is not None


def set_context_menu(enabled: bool):
    if not IS_WINDOWS:
        return
    for key in MENU_KEYS:
        if enabled:
            _set(key, "MUIVerb", "Uninstall with WinPurge")
            _set(key, "Icon", _icon_path())
            _set(key + r"\command", "", subprocess.list2cmdline(self_command("--uninstall")) + ' "%1"')
        else:
            _delete_tree(key)


# ---------------------------------------------------------------- watcher at sign-in

def watcher_enabled() -> bool:
    return IS_WINDOWS and _get(RUN_KEY, RUN_VALUE) is not None


def set_watcher(enabled: bool):
    if not IS_WINDOWS:
        return
    import winreg
    if enabled:
        _set(RUN_KEY, RUN_VALUE, subprocess.list2cmdline(self_command("--watch")))
        launch("--watch")   # start now too; a second copy exits by itself
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_VALUE)
        except OSError:
            pass
        stop_watcher()


def stop_watcher() -> bool:
    """Stop a running watcher. True if none is left running."""
    pid_file = app_data_dir() / WATCHER_PID
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return True
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        from .system import running_processes
        alive = any(p == pid for p, _ in running_processes())
    else:
        alive = False
    if not alive:
        try:
            pid_file.unlink()
        except OSError:
            pass
    return not alive


INSTALLER_ID = "{8F3C2A51-6D4E-4B8A-9E2F-5C1D7A3B9E40}_is1"


def own_uninstaller() -> str | None:
    """The command that uninstalls WinPurge, if it was installed with Setup."""
    if not IS_WINDOWS:
        return None
    return _get("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + INSTALLER_ID, "UninstallString")


def remove_integrations() -> list[str]:
    """Turn off everything WinPurge set up, and say what was turned off."""
    done = []
    if watcher_enabled() or (app_data_dir() / WATCHER_PID).exists():
        set_watcher(False)
        done.append("Uninstall watcher")
    if context_menu_enabled():
        set_context_menu(False)
        done.append("Right-click menu item")
    return done


# ---------------------------------------------------------------- shortcuts and matching

def shortcut_target(lnk: str) -> str | None:
    """The program a .lnk shortcut points to (reads the file directly)."""
    try:
        data = Path(lnk).read_bytes()
    except OSError:
        return None
    if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
        return None
    flags = struct.unpack_from("<I", data, 0x14)[0]
    pos = 0x4C
    if flags & 0x01:                      # HasLinkTargetIDList
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if not flags & 0x02:                  # HasLinkInfo
        return None
    info = pos
    header = struct.unpack_from("<I", data, info + 4)[0]
    base_off = struct.unpack_from("<I", data, info + 16)[0]
    if header >= 0x24:                    # Unicode path present
        uoff = struct.unpack_from("<I", data, info + 28)[0]
        if uoff:
            start = end = info + uoff
            while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                end += 2
            return data[start:end].decode("utf-16-le", "replace") or None
    if base_off:
        end = data.find(b"\x00", info + base_off)
        return data[info + base_off:end].decode("mbcs" if IS_WINDOWS else "latin-1", "replace") or None
    return None


def match_app(path: str, installed: list):
    """The installed app a program or shortcut belongs to, or None."""
    if path.lower().endswith(".lnk"):
        target = shortcut_target(path)
        by_name = normalize(Path(path).stem)
        if target:
            path = target
        else:
            return next((a for a in installed if a.norm == by_name), None)
    p = os.path.normcase(os.path.normpath(path))
    best = None
    for a in installed:
        for folder in (a.install_location, os.path.dirname(a.display_icon) if a.display_icon else ""):
            if not folder:
                continue
            f = os.path.normcase(os.path.normpath(folder))
            if p == f or p.startswith(f + os.sep):
                # The most specific folder wins (Program Files\Vendor\App over Program Files\Vendor).
                if best is None or len(f) > best[0]:
                    best = (len(f), a)
    if best:
        return best[1]
    stem = normalize(Path(path).stem)
    return next((a for a in installed if a.norm == stem), None)
