"""The one way WinPurge starts, whether from run_winpurge.pyw, `py -m winpurge`
or the built WinPurge.exe. Imports are written out plainly so PyInstaller
can see and bundle every module."""
from __future__ import annotations

import sys

from . import crashlog


USAGE = """WinPurge
  WinPurge                       open the app
  WinPurge <program or shortcut> uninstall that app (same as the right-click menu)
  WinPurge --uninstall <path>    the same
  WinPurge --watch               run the uninstall watcher (started at sign-in when it's on)
  WinPurge --leftovers <data>    review one uninstalled app's leftovers (the watcher uses this)
  WinPurge --clean-reminder      show the "scheduled clean is due" reminder
  WinPurge --remove-integrations turn off the watcher and right-click menu (the uninstaller uses this)"""


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    """(mode, value). Modes: app, uninstall, watch, leftovers, reminder, remove, help."""
    if not argv:
        return "app", None
    a = argv[0]
    flags = {"--watch": "watch", "--clean-reminder": "reminder", "--remove-integrations": "remove",
             "--help": "help", "/?": "help", "-h": "help"}
    if a in flags:
        return flags[a], None
    if a in ("--uninstall", "--leftovers"):
        return (a[2:], argv[1]) if len(argv) > 1 else ("help", None)
    if not a.startswith("-"):
        return "uninstall", a        # a program dropped onto WinPurge
    return "help", None


def start() -> int:
    if sys.platform != "win32":
        print("WinPurge is a Windows app. Run it on Windows 10 or 11.", file=sys.stderr)
        return 1
    mode, value = parse_args(sys.argv[1:])
    if mode == "watch":
        from .watcher import run_watcher
        try:
            return run_watcher()
        except Exception:
            crashlog.report(*sys.exc_info(), where="watcher")
            return 1
    if mode == "remove":
        from .shell import remove_integrations
        remove_integrations()
        return 0
    if mode == "help":
        crashlog.show_box("WinPurge", USAGE)
        return 0
    try:
        import ctypes
        try:  # sharp text on high-DPI screens
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass

        try:
            import tkinter  # noqa: F401
        except ImportError:
            crashlog.show_box("WinPurge can't start",
                              "This Python has no Tk, which WinPurge needs for its window.\n\n"
                              "Install Python from python.org and keep \"tcl/tk and IDLE\" ticked.")
            return 1

        if mode == "leftovers":
            from .prompts import LeftoversPrompt
            from .watcher import decode_app
            app = LeftoversPrompt(decode_app(value))
        elif mode == "reminder":
            from .prompts import ReminderPrompt
            app = ReminderPrompt()
        else:
            from .app import WinPurgeApp
            app = WinPurgeApp(uninstall_path=value if mode == "uninstall" else None)

        def on_tk_error(exc_type, exc, tb):
            path = crashlog.report(exc_type, exc, tb, where="window")
            crashlog.show_box("WinPurge hit a problem",
                              f"{exc_type.__name__}: {exc}\n\nThe details are saved in:\n{path}")
        app.report_callback_exception = on_tk_error
        app.mainloop()
        return 0
    except Exception:
        path = crashlog.report(*sys.exc_info(), where="start")
        crashlog.show_box("WinPurge can't start",
                          f"{sys.exc_info()[1]}\n\nThe details are saved in:\n{path}\n\n"
                          "Send that file with your bug report.")
        return 1
