import ctypes
import sys

if sys.platform != "win32":
    sys.exit("WinPurge is a Windows app. Run it on Windows 10 or 11.")

try:  # sharp text on high-DPI screens
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass

from winpurge.ui import main

main()
