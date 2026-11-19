"""WinPurge: an app uninstaller, junk cleaner and privacy-settings manager for Windows.

Modules: core (basics), scan (what it looks for), windows (Windows integration),
ui (look and feel), app (the window). start() below is the one way WinPurge
starts: from run_winpurge.pyw, `py -m winpurge` or the built WinPurge.exe."""
from __future__ import annotations

__version__ = "0.4.1"


import sys



USAGE = """WinPurge
  WinPurge                       open the app
  WinPurge <program or shortcut> uninstall that app (same as the right-click menu)
  WinPurge --uninstall <path>    the same
  WinPurge --watch               run the uninstall watcher (started at sign-in when it's on)
  WinPurge --leftovers <data>    review one uninstalled app's leftovers (the watcher uses this)
  WinPurge --clean-reminder      show the "scheduled clean is due" reminder
  WinPurge --remove-integrations turn off the watcher and right-click menu (the uninstaller uses this)
  WinPurge --restore-integrations watch,menu
                                 turn them back on after an upgrade (Setup uses this)"""


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    """(mode, value). Modes: app, uninstall, watch, leftovers, reminder, remove, help."""
    if not argv:
        return "app", None
    a = argv[0]
    flags = {"--watch": "watch", "--clean-reminder": "reminder", "--remove-integrations": "remove",
             "--help": "help", "/?": "help", "-h": "help"}
    if a in flags:
        return flags[a], None
    if a == "--restore-integrations":
        return "restore", argv[1] if len(argv) > 1 else ""
    if a in ("--uninstall", "--leftovers"):
        return (a[2:], argv[1]) if len(argv) > 1 else ("help", None)
    if not a.startswith("-"):
        return "uninstall", a        # a program dropped onto WinPurge
    return "help", None


def start() -> int:
    from . import core
    if sys.platform != "win32":
        print("WinPurge is a Windows app. Run it on Windows 10 or 11.", file=sys.stderr)
        return 1
    mode, value = parse_args(sys.argv[1:])
    if mode == "watch":
        from .windows import run_watcher
        try:
            return run_watcher()
        except Exception:
            core.report(*sys.exc_info(), where="watcher")
            return 1
    if mode == "remove":
        from .windows import remove_integrations
        remove_integrations()
        return 0
    if mode == "restore":
        # After an upgrade: stop any watcher still running from the old copy,
        # then turn back on what was on, pointing at this copy.
        from . import windows as shell
        parts = {p.strip() for p in (value or "").split(",")}
        shell.stop_watcher()
        if "menu" in parts:
            shell.set_context_menu(True)
        if "watch" in parts:
            shell.set_watcher(True)
        return 0
    if mode == "help":
        core.show_box("WinPurge", USAGE)
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
            core.show_box("WinPurge can't start",
                              "This Python has no Tk, which WinPurge needs for its window.\n\n"
                              "Install Python from python.org and keep \"tcl/tk and IDLE\" ticked.")
            return 1

        if mode == "leftovers":
            from .app import LeftoversPrompt
            from .windows import decode_app
            app = LeftoversPrompt(decode_app(value))
        elif mode == "reminder":
            from .app import ReminderPrompt
            app = ReminderPrompt()
        else:
            from .app import WinPurgeApp
            app = WinPurgeApp(uninstall_path=value if mode == "uninstall" else None)

        def on_tk_error(exc_type, exc, tb):
            path = core.report(exc_type, exc, tb, where="window")
            core.show_box("WinPurge hit a problem",
                              f"{exc_type.__name__}: {exc}\n\nThe details are saved in:\n{path}")
        app.report_callback_exception = on_tk_error
        app.mainloop()
        return 0
    except Exception:
        path = core.report(*sys.exc_info(), where="start")
        core.show_box("WinPurge can't start",
                          f"{sys.exc_info()[1]}\n\nThe details are saved in:\n{path}\n\n"
                          "Send that file with your bug report.")
        return 1
