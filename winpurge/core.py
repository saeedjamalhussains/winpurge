"""Shared basics: items and paths, settings, permissions, the Recycle Bin, history and
schedule, error log, and small Windows helpers (running programs, known folders)."""
from __future__ import annotations

import datetime
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import traceback

from dataclasses import dataclass, field
from pathlib import Path



# ============================================================================
# common
# Shared types and helpers: paths, sizes, safety rules.
IS_WINDOWS = sys.platform == "win32"

SAFE = "Safe"            # rebuilds itself; fine to remove
CHECK = "Check First"    # real data or uncertain; never ticked by default

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass
class Item:
    """One removable thing shown in the UI."""
    path: str
    label: str
    category: str
    level: str = SAFE
    size: int = 0
    note: str = ""
    kind: str = "path"          # "path", "registry" or "command" (a tool's own uninstall)
    checked: bool = False
    extra: dict = field(default_factory=dict)  # paths, contents_only, locked, admin, ...
    tab: str = ""               # caches, dev, large, leftovers, cli
    mtime: float = 0.0          # last change, for sorting by date

    @property
    def paths(self) -> list[str]:
        return self.extra.get("paths") or [self.path]

    @property
    def locked(self) -> str | None:
        """Why this row can't be selected right now (for example, in use)."""
        return self.extra.get("locked")


def env_path(var: str, *parts: str, env=None) -> Path | None:
    """Join an environment folder like LOCALAPPDATA with parts, or None if unset."""
    env = os.environ if env is None else env
    base = env.get(var)
    if not base:
        return None
    return Path(base, *parts)


def is_link_or_junction(entry: os.DirEntry) -> bool:
    """True for symlinks and Windows junctions. Never follow these: a junction
    can point at C:\\ and a size scan or delete would walk the whole disk."""
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def folder_size(path: str | Path, limit_seconds: float | None = None) -> int:
    """Total bytes under path, not following links or junctions."""
    import time
    start = time.monotonic()
    total = 0
    stack = [str(path)]
    try:
        st = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(st.st_mode):
            return st.st_size
    except OSError:
        return 0
    while stack:
        if limit_seconds and time.monotonic() - start > limit_seconds:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if is_link_or_junction(entry):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


_NOISE = re.compile(
    r"\(?\b(x64|x86|64-bit|32-bit|amd64|arm64|win64|win32|version|v?\d+(\.\d+)+|\d{4})\b\)?",
    re.I,
)


def normalize(name: str) -> str:
    """'Notepad++ (64-bit x64) 8.6.2' -> 'notepad++'. Used to match folders to apps."""
    name = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name or "")  # "(x64 en-US)", "[beta]"
    name = _NOISE.sub(" ", name)
    name = re.sub(r"[^a-z0-9+]+", "", name.lower())
    return name


# Folders that must never be offered for removal, however a match looks.
def protected_paths(env=None) -> set[str]:
    env = os.environ if env is None else env
    roots = [
        env.get("SystemRoot", r"C:\Windows"),
        env.get("ProgramFiles", r"C:\Program Files"),
        env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        env.get("ProgramData", r"C:\ProgramData"),
        env.get("USERPROFILE"),
        env.get("APPDATA"),
        env.get("LOCALAPPDATA"),
        env.get("SystemDrive", "C:") + "\\",
    ]
    return {os.path.normcase(os.path.normpath(r)) for r in roots if r}


def is_protected(path: str | Path, env=None) -> bool:
    p = os.path.normcase(os.path.normpath(str(path)))
    if p in protected_paths(env):
        return True
    # Nothing directly inside the Windows folder, and nothing under it at all.
    win = os.path.normcase(os.path.normpath((env or os.environ).get("SystemRoot", r"C:\Windows")))
    return p == win or p.startswith(win + os.sep)


# ============================================================================
# crashlog
# Never fail silently. A windowed .exe has no console, so an error at start
# or inside a button handler would otherwise just make the app vanish.
# Errors go to %LOCALAPPDATA%\WinPurge\logs\winpurge.log and are shown in a box.
def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    d = Path(base, "WinPurge", "logs")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(os.environ.get("TEMP", "."))
    return d


def log_path() -> Path:
    return log_dir() / "winpurge.log"


def write(text: str) -> Path:
    path = log_path()
    try:
        # Keep the log small: start over past 1 MB.
        if path.exists() and path.stat().st_size > 1_000_000:
            path.unlink()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ---\n{text}\n")
    except OSError:
        pass
    return path


def environment() -> str:
    from . import __version__
    return (f"WinPurge {__version__}, Python {platform.python_version()} "
            f"({'frozen .exe' if getattr(sys, 'frozen', False) else sys.executable}), "
            f"{platform.platform()}")


def report(exc_type, exc, tb, where: str = "") -> Path:
    text = environment() + (f"\nWhere: {where}" if where else "") + "\n" + \
        "".join(traceback.format_exception(exc_type, exc, tb))
    return write(text)


def show_box(title: str, message: str):
    """A plain Windows message box. Works even when Tk itself failed to load."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
    else:
        print(f"{title}: {message}", file=sys.stderr)


# ============================================================================
# trash
# Removal. Files and folders go to the Recycle Bin, never straight to
# deletion; registry keys are exported to a .reg backup before removal.
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
    from .scan import system_junk_paths
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
    import subprocess
    from .windows import self_command
    cmd = self_command()       # WinPurge.exe, or pythonw + run_winpurge.pyw (no console window)
    exe, params = cmd[0], subprocess.list2cmdline(cmd[1:])
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


# ============================================================================
# settings
# User preferences, saved in %APPDATA%\WinPurge\settings.json.
class Settings:
    def __init__(self):
        self.path = app_data_dir() / "settings.json"
        try:
            self.data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("project_roots", [])
        self.data.setdefault("project_age_days", 30)
        self.data.setdefault("theme", "system")   # system, light, dark

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=1), "utf-8")
        except OSError:
            pass


# ============================================================================
# permissions
# What the user allowed WinPurge to do, chosen in the first-run setup.
# Kept free of Tk so it can be tested anywhere.
SETUP_VERSION = 3  # bump to show setup again when permissions change meaning


@dataclass(frozen=True)
class Permission:
    key: str
    title: str
    detail: str
    default: bool


PERMISSIONS: list[Permission] = [
    Permission(
        "read_apps", "Read installed apps and command-line tools",
        "Reads the same registry list that Settings > Apps shows, and asks npm, pipx, uv, Cargo and "
        "dotnet which tools they installed. Needed for the Uninstaller and to tell which leftover "
        "folders belong to apps that are still installed.",
        True),
    Permission(
        "scan_caches", "Look in cache, temporary and developer tool folders",
        "Reads folder sizes in Temp, Windows update and crash files, browser and app caches (never "
        "history, cookies or passwords), and developer tool caches such as npm and pip.",
        True),
    Permission(
        "scan_leftovers", "Look for files left by removed apps",
        "Reads folder names in AppData, ProgramData and Program Files after an uninstall, and "
        "finds app data folders unchanged for 90 days whose app is gone.",
        True),
    Permission(
        "scan_projects", "Look for build folders in your coding projects",
        "Finds node_modules, build and virtual environment folders in projects you haven't changed "
        "for a while, in your usual code folders and any you add in Settings.",
        True),
    Permission(
        "scan_large_files", "Look for large files in your folders",
        "Reads the names and sizes of big files in Desktop, Documents, Downloads, Videos, Music and "
        "Pictures, and compares same-size files to find exact duplicates. Files are never opened "
        "otherwise, and cloud-only OneDrive files are skipped.",
        True),
    Permission(
        "registry_cleanup", "Offer to remove an app's registry settings",
        "After an uninstall, offers the app's own keys under HKEY_CURRENT_USER\\Software. "
        "Each key is saved to a .reg backup file first, and is never ticked for you.",
        False),
    Permission(
        "privacy", "Show and change Windows privacy settings",
        "Shows what diagnostic data, ads, activity history, typing, speech and location settings "
        "this PC uses, and lets you change them from WinPurge. Nothing changes until you choose to, "
        "and your original settings are saved so you can restore them.",
        False),
]

PERMISSION_KEYS = {p.key for p in PERMISSIONS}


def defaults() -> dict[str, bool]:
    return {p.key: p.default for p in PERMISSIONS}


def needs_setup(settings: dict) -> bool:
    return settings.get("setup_version", 0) < SETUP_VERSION


def allowed(settings: dict, key: str) -> bool:
    """Before setup is finished nothing is allowed."""
    if key not in PERMISSION_KEYS:
        raise KeyError(key)
    if needs_setup(settings):
        return False
    return bool(settings.get("permissions", {}).get(key, False))


def complete_setup(settings: dict, chosen: dict[str, bool], project_roots: list[str]) -> dict:
    unknown = set(chosen) - PERMISSION_KEYS
    if unknown:
        raise KeyError(", ".join(sorted(unknown)))
    perms = defaults()
    perms.update({k: bool(v) for k, v in chosen.items()})
    settings["permissions"] = perms
    settings["project_roots"] = list(project_roots) if perms["scan_projects"] else []
    settings["setup_version"] = SETUP_VERSION
    return settings


# ============================================================================
# history
# Cleaning history and the cleaning schedule.
#
# History: every clean, manual or scheduled, with the space freed, what moved to
# the Recycle Bin, what was removed permanently and what was skipped.
# Schedule: WinPurge never cleans in the background. When a scheduled clean is
# due, the next time WinPurge opens it scans and moves the Safe items in App
# Caches and Dev Tools to the Recycle Bin (never Large Files, never Check First).
KEEP = 200            # cleans kept in history
PATHS_PER_CLEAN = 300  # paths kept per clean

FREQUENCIES = (("7", "Every week"), ("30", "Every month"), ("91", "Every 3 months"))


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "history.json"
        try:
            self.entries: list[dict] = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.entries = []

    def add(self, kind: str, freed: int, moved: list[str], permanent: list[str] | None = None,
            skipped: list[tuple[str, str]] | None = None) -> dict:
        entry = {"time": time.time(), "kind": kind, "freed": int(freed), "items": len(moved) + len(permanent or []),
                 "moved": moved[:PATHS_PER_CLEAN], "permanent": (permanent or [])[:PATHS_PER_CLEAN],
                 "skipped": [list(s) for s in (skipped or [])][:PATHS_PER_CLEAN]}
        self.entries.insert(0, entry)
        del self.entries[KEEP:]
        try:
            self.path.write_text(json.dumps(self.entries, indent=1), "utf-8")
        except OSError:
            pass
        return entry

    def total_freed(self) -> int:
        return sum(e.get("freed", 0) for e in self.entries)

    def last(self) -> dict | None:
        return self.entries[0] if self.entries else None


def schedule(settings: dict) -> dict:
    return settings.setdefault("auto_clean", {"enabled": False, "every_days": 7, "last": 0})


def next_due(settings: dict) -> float | None:
    s = schedule(settings)
    if not s.get("enabled"):
        return None
    # Turning the schedule on sets "last" to now, so the first clean is one
    # interval later, not straight away.
    return (s.get("last") or time.time()) + int(s.get("every_days", 7)) * 86400


def is_due(settings: dict, now: float | None = None) -> bool:
    due = next_due(settings)
    return due is not None and (now or time.time()) >= due


def mark_done(settings: dict, now: float | None = None):
    schedule(settings)["last"] = now or time.time()


# ============================================================================
# system
# Small Windows helpers: running programs, closing them politely, and the
# Recycle Bin's size. Everything degrades to "nothing found" off Windows.
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _psapi = ctypes.WinDLL("psapi")
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def running_processes() -> list[tuple[int, str]]:
    """(pid, full path of the program) for every process we may look at."""
    if not IS_WINDOWS:
        return []
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    if not _psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return []
    out = []
    buf = ctypes.create_unicode_buffer(32768)
    for pid in arr[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid:
            continue
        h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        try:
            size = wintypes.DWORD(len(buf))
            if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                out.append((int(pid), buf.value))
        finally:
            _k32.CloseHandle(h)
    return out


def running_exes() -> list[str]:
    return [exe for _, exe in running_processes()]


def processes_inside(folders: list[str]) -> dict[str, list[int]]:
    """Programs running from inside any of `folders`: {exe path: [pids]}."""
    keys = [os.path.normcase(os.path.normpath(f)) + os.sep for f in folders if f]
    found: dict[str, list[int]] = {}
    for pid, exe in running_processes():
        if pid == os.getpid():
            continue
        e = os.path.normcase(exe)
        if any(e.startswith(k) for k in keys):
            found.setdefault(exe, []).append(pid)
    return found


def close_gracefully(pids: list[int], wait: float = 10.0) -> list[int]:
    """Ask programs to close the way clicking X does (no force). Returns the
    pids still running after `wait` seconds; those are left alone."""
    if not IS_WINDOWS or not pids:
        return []
    flags = subprocess.CREATE_NO_WINDOW
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, creationflags=flags)
    deadline = time.time() + wait
    alive = list(pids)
    while alive and time.time() < deadline:
        time.sleep(0.5)
        current = {p for p, _ in running_processes()}
        alive = [p for p in alive if p in current]
    return alive


def recycle_bin_size() -> tuple[int, int]:
    """(bytes, items) in the Recycle Bin on all drives."""
    if not IS_WINDOWS:
        return 0, 0

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(info)
    if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        return 0, 0
    return int(info.i64Size), int(info.i64NumItems)


def known_folder(name: str, env=None) -> str | None:
    """A user folder such as Downloads, where Windows really keeps it (it may
    have been moved to another drive)."""
    env = os.environ if env is None else env
    guids = {
        "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
        "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
        "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
        "Pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
        "Videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    }
    if IS_WINDOWS and name in guids:
        try:
            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]
            g = GUID()
            ctypes.windll.ole32.CLSIDFromString(guids[name], ctypes.byref(g))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                path = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return path
        except (OSError, AttributeError):
            pass
    home = env.get("USERPROFILE")
    if home and os.path.isdir(os.path.join(home, name)):
        return os.path.join(home, name)
    return None


# Program names that don't match the app's name.
EXE_ALIASES = {"edge": "msedge", "vs code": "code", "vscode": "code", "teams": "ms-teams",
               "docker": "docker desktop", "docker desktop": "docker desktop", "firefox": "firefox",
               "brave": "brave", "whatsapp": "whatsapp", "zoom": "zoom"}
# Never offered for closing.
NEVER_CLOSE = {"explorer", "svchost", "system", "winlogon", "csrss", "dwm", "python", "pythonw", "winpurge",
               "searchhost", "runtimebroker", "sihost", "taskhostw", "conhost", "cmd", "powershell"}


def owners_running(items) -> dict[str, dict]:
    """Running programs that use files these items would remove:
    {program name: {"pids": [...], "items": [items it owns]}}. Matches programs
    running from inside an item's folder, and programs named like the app a
    cache row belongs to (Chrome -> chrome.exe)."""
    procs = [(pid, exe) for pid, exe in running_processes()
             if pid != os.getpid() and os.path.splitext(os.path.basename(exe))[0].lower() not in NEVER_CLOSE]
    found: dict[str, dict] = {}
    if not procs:
        return found
    for it in items:
        folders = [] if it.extra.get("contents_only") else it.paths
        keys = [os.path.normcase(os.path.normpath(f)) + os.sep for f in folders]
        names = set()
        if it.category in ("Apps", "Browsers", "Dev tool caches", "Docker", "Leftovers", "Unused app data"):
            base = it.label.split("  ")[0].split(" (")[0].lower()
            names.add(EXE_ALIASES.get(base, base).replace(" ", ""))
            names |= {EXE_ALIASES.get(w, w) for w in base.replace("-", " ").split() if len(w) >= 4}
        for pid, exe in procs:
            stem = os.path.splitext(os.path.basename(exe))[0]
            e = os.path.normcase(exe)
            if any(e.startswith(k) for k in keys) or stem.lower().replace(" ", "") in names:
                entry = found.setdefault(stem, {"pids": [], "items": []})
                if pid not in entry["pids"]:
                    entry["pids"].append(pid)
                if it not in entry["items"]:
                    entry["items"].append(it)
    return found


def background_priority(whole_process: bool = False):
    """Run at background priority: Windows lowers CPU and disk priority so
    scans never slow down what you're doing. For one thread, or (watcher)
    the whole process."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        if whole_process:
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetPriorityClass(ctypes.c_void_p(k32.GetCurrentProcess()), 0x00100000)  # PROCESS_MODE_BACKGROUND_BEGIN
        else:
            k32.GetCurrentThread.restype = ctypes.c_void_p
            k32.SetThreadPriority(ctypes.c_void_p(k32.GetCurrentThread()), 0x00010000)  # THREAD_MODE_BACKGROUND_BEGIN
    except (AttributeError, OSError):
        pass
