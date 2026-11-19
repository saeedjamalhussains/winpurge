# Double-click to start WinPurge without a console window (needs Python from python.org).
# This is also the entry script PyInstaller builds WinPurge.exe from, so the import below
# must stay a plain import: PyInstaller only bundles modules it can see imported.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winpurge.launcher import start  # noqa: E402

sys.exit(start())
