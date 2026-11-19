"""The WinPurge main window: sidebar navigation, pages, background work."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk

from . import __version__, crashlog, gfx
from . import theme as th
from .apps import list_installed_apps
from .permissions import allowed, needs_setup
from .privacy import Backup, default_backend, read_all
from .settings import Settings
from .theme import px
from .trash import IgnoreList, app_data_dir, is_admin, relaunch_as_admin
from .widgets import Dialog, Toast, apply_ttk_styles, bg_of, label

APP_ID = "WinPurge.App"


def open_path(path: str):
    """Open a folder or file in Explorer."""
    if sys.platform == "win32" and os.path.exists(path):
        os.startfile(path)


def show_in_explorer(path: str):
    if sys.platform == "win32" and os.path.exists(path):
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def open_recycle_bin():
    if sys.platform == "win32":
        import subprocess
        subprocess.Popen(["explorer", "shell:RecycleBinFolder"])


class NavItem(tk.Canvas):
    def __init__(self, parent, key, text, icon, command):
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0, height=px(38), cursor="hand2")
        self.key, self.text, self.icon, self.command = key, text, icon, command
        self.active = self.hover = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self.command(self.key))

    def _set_hover(self, v):
        self.hover = v
        self._draw()

    def set_active(self, v):
        self.active = v
        self._draw()

    def _draw(self):
        from .widgets import rounded_rect
        P = th.P
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        if self.active or self.hover:
            rounded_rect(self, 0, 0, w, h, px(6), P.card if self.active else P.control_hover,
                         P.border if self.active else None)
        if self.active:
            rounded_rect(self, px(1), h // 2 - px(8), px(4), h // 2 + px(8), px(2), P.accent)
        fg = P.text if self.active else P.text2
        self.create_text(px(22), h / 2, text=th.icon(self.icon), font=th.icon_font(12),
                         fill=P.accent if self.active else P.text2)
        self.create_text(px(42), h / 2, text=self.text, anchor="w",
                         font=th.body_strong() if self.active else th.body_font(), fill=fg)


class WinPurgeApp(tk.Tk):
    NAV = (("home", "Overview", "home"), ("apps", "Apps", "apps"), ("clean", "Clean Up", "clean"),
           ("privacy", "Privacy", "privacy"), ("settings", "Settings", "settings"))

    def __init__(self):
        if sys.platform == "win32":
            try:  # own taskbar button and icon, not Python's
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            except (AttributeError, OSError):
                pass
        super().__init__(className="WinPurge")
        self.withdraw()
        self.settings = Settings()
        th.init(self, self.settings.data["theme"])
        self.title("WinPurge")
        w, h = px(1120), px(740)
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(px(960), px(640))
        self.iconphoto(True, gfx.logo_img(64), gfx.logo_img(32), gfx.logo_img(16))

        self.ignore = IgnoreList()
        self.privacy_backup = Backup(app_data_dir() / "privacy-backup.json")
        self.privacy_backend = None
        self.jobs: queue.Queue = queue.Queue()
        self.installed = []
        self.apps_state = "idle"         # idle, loading, ready, off
        self.scan_items = None            # list[Item] after a scan
        self.scan_state = "idle"          # idle, scanning, done
        self.privacy_statuses = None
        self.privacy_edition = ""
        self.current = "home"
        self.pages = {}

        self.after(80, self._poll)
        if needs_setup(self.settings.data):
            self.show_welcome()
        else:
            self.build()
            self.load_everything()
        self.deiconify()

    # ------------------------------------------------------------ layout

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.pages.clear()

    def build(self):
        from .pages import AppsPage, CleanPage, HomePage, PrivacyPage, SettingsPage
        self._clear()
        P = th.P
        apply_ttk_styles(self)
        self.configure(bg=P.window)
        th.set_dark_title_bar(self, P.name == "dark")

        side = tk.Frame(self, bg=P.sidebar, width=px(232))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=P.sidebar)
        brand.pack(fill="x", padx=px(18), pady=(px(22), px(24)))
        tk.Label(brand, image=gfx.logo_img(px(30)), bg=P.sidebar).pack(side="left")
        label(brand, "WinPurge", "big").pack(side="left", padx=(px(10), 0))
        self.nav = {}
        for key, text, icon in self.NAV:
            item = NavItem(side, key, text, icon, self.show)
            item.pack(fill="x", padx=px(10), pady=px(1))
            self.nav[key] = item
        foot = tk.Frame(side, bg=P.sidebar)
        foot.pack(side="bottom", fill="x", padx=px(20), pady=px(18))
        mode = "Administrator" if is_admin() else "Standard user"
        label(foot, f"Version {__version__}  ·  {mode}", "caption", P.text3).pack(anchor="w")
        tk.Frame(self, bg=P.divider, width=1).pack(side="left", fill="y")

        self.content = tk.Frame(self, bg=P.window)
        self.content.pack(side="left", fill="both", expand=True)
        for key, cls in (("home", HomePage), ("apps", AppsPage), ("clean", CleanPage),
                         ("privacy", PrivacyPage), ("settings", SettingsPage)):
            self.pages[key] = cls(self.content, self)
        self.toast = Toast(self.content)
        self.show(self.current)

    def show(self, key):
        self.current = key
        for k, page in self.pages.items():
            page.pack_forget()
        for k, item in self.nav.items():
            item.set_active(k == key)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        page.on_show()

    def rebuild(self):
        """Apply a new theme: rebuild the window with the new palette."""
        th.init(self, self.settings.data["theme"])
        gfx.IMAGES.clear()
        self.build()

    def show_welcome(self):
        from .welcome import Welcome
        self._clear()
        apply_ttk_styles(self)
        self.configure(bg=th.P.window)
        th.set_dark_title_bar(self, th.P.name == "dark")
        Welcome(self, self).pack(fill="both", expand=True)

    def finish_welcome(self):
        self.settings.save()
        self.current = "home"
        self.build()
        self.load_everything()

    def notify(self, event: str):
        """Tell every page something changed: apps, scan, privacy, permissions."""
        for page in self.pages.values():
            page.on_event(event)

    # ------------------------------------------------------------ permissions

    def can(self, key: str) -> bool:
        return allowed(self.settings.data, key)

    # ------------------------------------------------------------ background work

    def run_bg(self, work, done, on_error=None):
        def target():
            try:
                self.jobs.put((done, work(), None, on_error))
            except Exception as e:
                crashlog.report(type(e), e, e.__traceback__, where=getattr(work, "__name__", "background"))
                self.jobs.put((done, None, e, on_error))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, result, err, on_error = self.jobs.get_nowait()
                if err:
                    if on_error:
                        on_error(err)
                    self.error(err)
                else:
                    done(result)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def error(self, err):
        Dialog(self, "Something went wrong", f"{err}\n\nDetails are saved in {crashlog.log_path()}",
               (("OK", True, "primary"),), icon="warning", icon_color=th.P.danger).show()

    def load_everything(self):
        self.load_apps()
        self.load_privacy()

    def load_apps(self):
        if not self.can("read_apps"):
            self.apps_state, self.installed = "off", []
            self.notify("apps")
            return
        self.apps_state = "loading"
        self.notify("apps")

        def done(apps):
            self.installed, self.apps_state = apps, "ready"
            self.notify("apps")
        self.run_bg(list_installed_apps, done, lambda e: setattr(self, "apps_state", "idle"))

    def load_privacy(self):
        if not self.can("privacy"):
            self.privacy_statuses = None
            self.notify("privacy")
            return

        def work():
            from .privacy import windows_edition
            if self.privacy_backend is None:
                self.privacy_backend = default_backend()
            return read_all(self.privacy_backend), windows_edition(self.privacy_backend)

        def done(result):
            self.privacy_statuses, self.privacy_edition = result
            self.notify("privacy")
        self.run_bg(work, done)

    def restart_as_admin(self):
        if relaunch_as_admin():
            self.destroy()

    # ------------------------------------------------------------ Smart Scan

    def scan_blocked_reason(self) -> str | None:
        if not (self.can("scan_caches") or self.can("scan_projects") or
                (self.can("scan_leftovers") and self.can("read_apps"))):
            return "All scans are turned off. Turn some on in Settings."
        return None

    def start_scan(self):
        from .caches import scan_caches, scan_projects
        from .leftovers import find_orphans
        if self.scan_state == "scanning":
            return
        reason = self.scan_blocked_reason()
        if reason:
            Dialog(self, "Nothing to scan", reason,
                   (("Close", None, "secondary"), ("Open Settings", True, "primary")), icon="info").show() \
                and self.show("settings")
            return
        roots = list(self.settings.data["project_roots"])
        age = self.settings.data["project_age_days"]
        do_caches, do_projects = self.can("scan_caches"), self.can("scan_projects")
        do_orphans = self.can("scan_leftovers") and self.can("read_apps")
        installed = list(self.installed)

        def smart_scan():
            items = []
            if do_caches:
                items += scan_caches()
            if do_projects and roots:
                items += scan_projects(roots, min_age_days=age)
            if do_orphans:
                items += find_orphans(installed or list_installed_apps())
            return [i for i in items if not self.ignore.contains(i.path)]

        def done(items):
            self.scan_items, self.scan_state = items, "done"
            self.notify("scan")

        def failed(_):
            self.scan_state = "idle"
            self.notify("scan")

        self.scan_state = "scanning"
        self.notify("scan")
        self.run_bg(smart_scan, done, failed)
