"""The one way WinPurge starts, whether from run_winpurge.pyw, `py -m winpurge`
or the built WinPurge.exe. Imports are written out plainly so PyInstaller
can see and bundle every module."""
from __future__ import annotations

import sys

from . import crashlog


def start() -> int:
    if sys.platform != "win32":
        print("WinPurge is a Windows app. Run it on Windows 10 or 11.", file=sys.stderr)
        return 1
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

        from .ui import WinPurgeApp
        app = WinPurgeApp()

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
