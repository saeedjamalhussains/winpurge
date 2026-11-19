"""The uninstall watcher: a small background process (no window) that notices
when an app is uninstalled, however it was removed, and opens WinPurge with
just that app's leftovers to review. It also reminds you when a scheduled
clean is due. Off until you turn on "Review leftovers when an app is
uninstalled" in Settings.

It waits on Windows' own change notifications for the installed-apps registry
keys, so it uses no CPU while nothing changes."""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import time

from .apps import App, UNINSTALL_KEY, list_installed_apps
from .common import IS_WINDOWS
from .trash import app_data_dir

HANDLED_FILE = "handled-uninstalls.json"   # uninstalls WinPurge itself ran
HANDLED_FOR = 15 * 60


def encode_app(app: App) -> str:
    return base64.urlsafe_b64encode(json.dumps(dataclasses.asdict(app)).encode()).decode()


def decode_app(text: str) -> App:
    return App(**json.loads(base64.urlsafe_b64decode(text.encode())))


def mark_handled(app: App):
    """Called before WinPurge runs an uninstaller itself, so the watcher
    doesn't open a second review for the same app."""
    path = app_data_dir() / HANDLED_FILE
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    now = time.time()
    data = {k: t for k, t in data.items() if now - t < HANDLED_FOR}
    data[app.key_name] = now
    try:
        path.write_text(json.dumps(data), "utf-8")
    except OSError:
        pass


def recently_handled(app: App) -> bool:
    try:
        data = json.loads((app_data_dir() / HANDLED_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() - data.get(app.key_name, 0) < HANDLED_FOR


def removed_apps(before: list[App], after: list[App]) -> list[App]:
    still = {(a.key_name, a.norm) for a in after}
    return [a for a in before if (a.key_name, a.norm) not in still]


def run_watcher() -> int:
    if not IS_WINDOWS:
        return 1
    import ctypes
    import winreg
    from ctypes import wintypes

    from . import history, settings as settings_mod
    from .shell import WATCHER_PID, launch

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32")
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateEventW.restype = wintypes.HANDLE
    k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
    k32.WaitForMultipleObjects.restype = wintypes.DWORD
    advapi.RegNotifyChangeKeyValue.argtypes = [wintypes.HKEY, wintypes.BOOL, wintypes.DWORD, wintypes.HANDLE, wintypes.BOOL]
    k32.CreateMutexW(None, False, "Local\\WinPurgeUninstallWatcher")
    if ctypes.get_last_error() == 183:     # ERROR_ALREADY_EXISTS: one is running
        return 0
    (app_data_dir() / WATCHER_PID).write_text(str(os.getpid()))

    REG_NOTIFY_CHANGE_NAME, REG_NOTIFY_CHANGE_LAST_SET = 0x1, 0x4
    sources = [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
               (winreg.HKEY_CURRENT_USER, 0)]
    keys, events = [], []
    for root, view in sources:
        try:
            k = winreg.OpenKey(root, UNINSTALL_KEY, 0, winreg.KEY_NOTIFY | winreg.KEY_READ | view)
        except OSError:
            continue
        keys.append(k)
        events.append(k32.CreateEventW(None, False, False, None))

    def arm():
        for k, ev in zip(keys, events):
            advapi.RegNotifyChangeKeyValue(wintypes.HKEY(k.handle), True,
                                           REG_NOTIFY_CHANGE_NAME | REG_NOTIFY_CHANGE_LAST_SET, ev, True)

    if not events:
        return 1
    handles = (wintypes.HANDLE * len(events))(*events)
    snapshot = list_installed_apps()
    reminded_day = None
    arm()
    while True:
        rc = k32.WaitForMultipleObjects(len(events), handles, False, 60_000)
        if rc < len(events):
            time.sleep(4)          # let the uninstaller finish removing its key
            arm()
            current = list_installed_apps()
            for app in removed_apps(snapshot, current):
                if not recently_handled(app):
                    launch("--leftovers", encode_app(app))
            snapshot = current
        else:
            # Once a minute: is a scheduled clean due? Remind once a day.
            today = time.strftime("%Y-%m-%d")
            if reminded_day != today:
                s = settings_mod.Settings()
                if history.is_due(s.data):
                    launch("--clean-reminder")
                    reminded_day = today
