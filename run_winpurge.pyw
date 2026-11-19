# Double-click to start WinPurge without a console window (needs Python for Windows).
import runpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_module("winpurge", run_name="__main__")
