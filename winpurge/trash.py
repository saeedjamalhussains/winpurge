"""Removal. Files and folders go to the Recycle Bin, never straight to
deletion; registry keys are exported to a .reg backup before removal."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .common import IS_WINDOWS, Item, is_protected


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = Path(base, "WinPurge")
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Result:
    moved: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    bytes_moved: int = 0


# ---------------------------------------------------------------- Recycle Bin

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040
    FOF_NOERRORUI = 0x0400
    # Without this flag, an item too big for the Recycle Bin is deleted
    # permanently and silently. With it, Windows asks first.
    FOF_WANTNUKEWARNING = 0x4000
    DRIVE_FIXED = 3


def _on_fixed_drive(path: str) -> bool:
    if not IS_WINDOWS:
        return True
    drive = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    return ctypes.windll.kernel32.GetDriveTypeW(drive) == DRIVE_FIXED


def _recycle_one(path: str) -> str | None:
    """Move one path to the Recycle Bin. Returns an error message or None."""
    if IS_WINDOWS:
        if not _on_fixed_drive(path):
            return "On a network or removable drive, which has no Recycle Bin. Skipped."
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = os.path.abspath(path) + "\0"   # list must end with two NULs; ctypes adds one
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc != 0:
            if rc in (5, 0x78):
                return "Access denied. Restart WinPurge as administrator, or close the program using it."
            if rc == 32:
                return "In use by another program."
            return f"Windows error {rc:#x}"
        if op.fAnyOperationsAborted:
            return "Cancelled."
        if os.path.exists(path):
            return "Some files are in use and were left in place."
        return None
    # Not Windows: only for development and tests. Moves into a local
    # folder that stands in for the Recycle Bin. Never deletes.
    fake = os.environ.get("WINPURGE_FAKE_TRASH")
    if not fake:
        return "Removal only works on Windows."
    dest = Path(fake, f"{int(time.time()*1000)}-{Path(path).name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(path, dest)
    except OSError as e:
        return str(e)
    return None


def _allowed_system_junk(path: str) -> bool:
    """True only for the exact system junk folders WinPurge knows, such as
    C:\\Windows\\Temp. Everything else under Windows stays protected."""
    from .caches import system_junk_paths
    return os.path.normcase(os.path.normpath(path)) in system_junk_paths()


def _recycle_path(path: str, contents_only: bool, system_junk: bool, res: Result) -> bool:
    """Recycle one folder (or its contents). Returns True if anything moved."""
    if not os.path.exists(path):
        return False
    # Checked for "contents only" items too: if TEMP pointed at the user
    # profile, emptying it would take the whole profile.
    if is_protected(path) and not (system_junk and contents_only and _allowed_system_junk(path)):
        res.failed.append((path, "Protected system folder. Skipped."))
        return False
    if contents_only:
        try:
            children = list(os.scandir(path))
        except OSError as e:
            res.failed.append((path, str(e)))
            return False
        failures = sum(1 for c in children if _recycle_one(c.path))  # files in use are normal here
        if failures:
            res.failed.append((path, f"{failures} item(s) in use were left in place."))
        return failures < len(children) or not children
    err = _recycle_one(path)
    if err:
        res.failed.append((path, err))
        return False
    return True


def recycle(items: list[Item], progress=None) -> Result:
    """Move items to the Recycle Bin (registry keys: back up, then remove).
    Rows that are locked (in use) are skipped and reported."""
    res = Result()
    for n, item in enumerate(items, 1):
        if progress:
            progress(n, len(items), item)
        if item.locked:
            res.failed.append((item.path, item.locked))
            continue
        if item.kind == "registry":
            err = remove_registry_key(item.path)
            (res.failed.append((item.path, err)) if err else res.moved.append(item.path))
            continue
        if item.kind == "command":
            continue   # command-line tools are removed by their own manager (clitools)
        moved = False
        for p in item.paths:
            moved |= _recycle_path(p, bool(item.extra.get("contents_only")), bool(item.extra.get("system_junk")), res)
        if moved:
            res.moved.append(item.path)
            res.bytes_moved += item.size
    return res


# ---------------------------------------------------------------- Registry

def remove_registry_key(key: str) -> str | None:
    """Export the key to a .reg backup, then delete it. Only HKCU keys."""
    if not IS_WINDOWS:
        return "Registry only exists on Windows."
    if not key.upper().startswith("HKCU\\SOFTWARE\\") or key.count("\\") < 2:
        return "Only per-user software keys are removed."
    backups = app_data_dir() / "registry-backups"
    backups.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in key)[-80:]
    backup = backups / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe_name}.reg"
    flags = subprocess.CREATE_NO_WINDOW
    exp = subprocess.run(["reg", "export", key, str(backup), "/y"], capture_output=True, creationflags=flags)
    if exp.returncode != 0 or not backup.exists():
        return "Could not back up the key, so it was left in place."
    rm = subprocess.run(["reg", "delete", key, "/f"], capture_output=True, creationflags=flags)
    if rm.returncode != 0:
        return (rm.stderr or b"").decode(errors="replace").strip() or "reg delete failed"
    return None


# ---------------------------------------------------------------- Admin

def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin() -> bool:
    """Start a new elevated copy (Windows shows the UAC prompt)."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, ""
    else:
        exe, params = sys.executable, f'-m winpurge'
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params,
                                             str(Path(__file__).resolve().parent.parent), 1)
    return rc > 32


# ---------------------------------------------------------------- Ignore list

class IgnoreList:
    """Paths the user said not to suggest again (optionally until a date)."""

    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "ignored.json"
        try:
            self.entries = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.entries = []

    def _key(self, p: str) -> str:
        return os.path.normcase(os.path.normpath(p))

    def contains(self, p: str) -> bool:
        now = time.time()
        return any(self._key(e["path"]) == self._key(p) and (e.get("until") or now + 1) > now
                   for e in self.entries)

    def count(self) -> int:
        now = time.time()
        return sum(1 for e in self.entries if (e.get("until") or now + 1) > now)

    def clear(self):
        self.entries = []
        try:
            self.path.write_text("[]", "utf-8")
        except OSError:
            pass

    def active(self) -> list[str]:
        now = time.time()
        return [e["path"] for e in self.entries if (e.get("until") or now + 1) > now]

    def remove(self, p: str):
        self.entries = [e for e in self.entries if self._key(e["path"]) != self._key(p)]
        try:
            self.path.write_text(json.dumps(self.entries, indent=1), "utf-8")
        except OSError:
            pass

    def add(self, p: str, days: int | None = None):
        self.entries = [e for e in self.entries if self._key(e["path"]) != self._key(p)]
        self.entries.append({"path": p, "until": time.time() + days * 86400 if days else None})
        self.path.write_text(json.dumps(self.entries, indent=1), "utf-8")
