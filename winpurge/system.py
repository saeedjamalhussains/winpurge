"""Small Windows helpers: running programs, closing them politely, and the
Recycle Bin's size. Everything degrades to "nothing found" off Windows."""
from __future__ import annotations

import os
import subprocess
import time

from .common import IS_WINDOWS

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
