"""Never fail silently. A windowed .exe has no console, so an error at start
or inside a button handler would otherwise just make the app vanish.
Errors go to %LOCALAPPDATA%\\WinPurge\\logs\\winpurge.log and are shown in a box."""
from __future__ import annotations

import datetime
import os
import platform
import sys
import traceback
from pathlib import Path


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
