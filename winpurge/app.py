"""The WinPurge main window: sidebar, pages, scanning, cleaning, history."""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk

from . import __version__, crashlog, gfx
from . import history as hist
from . import theme as th
from .apps import list_installed_apps
from .common import SAFE, human_size
from .permissions import allowed, needs_setup
from .privacy import Backup, default_backend, read_all
from .settings import Settings
from .theme import px
from .trash import IgnoreList, app_data_dir, is_admin, recycle, relaunch_as_admin
from .widgets import Dialog, Toast, apply_ttk_styles, bg_of, label

APP_ID = "WinPurge.App"
TABS = ("caches", "dev", "large", "leftovers", "cli")
TAB_NAMES = {"caches": "App Caches", "dev": "Dev Tools", "large": "Large Files", "leftovers": "Leftovers",
             "cli": "Command-line tools"}
ADMIN_LOCK = "Needs administrator rights. Use Restart as administrator to include it."


def open_path(path: str):
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
    def __init__(self, parent, key, text, icon, command, shortcut=""):
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0, height=px(36), cursor="hand2")
        self.key, self.text, self.icon, self.command, self.shortcut = key, text, icon, command, shortcut
        self.badge = ""
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

    def set_badge(self, text):
        self.badge = text
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
        self.create_text(px(22), h / 2, text=th.icon(self.icon), font=th.icon_font(12),
                         fill=P.accent if self.active else P.text2)
        self.create_text(px(42), h / 2, text=self.text, anchor="w",
                         font=th.body_strong() if self.active else th.body_font(), fill=P.text if self.active else P.text2)
        if self.badge:
            self.create_text(w - px(12), h / 2, text=self.badge, anchor="e", font=th.caption_font(), fill=P.text3)


class WinPurgeApp(tk.Tk):
    NAV = (("home", "Overview", "home"), ("caches", "App Caches", "clean"), ("dev", "Dev Tools", "code"),
           ("large", "Large Files", "folder"), ("apps", "Uninstaller", "apps"), ("privacy", "Privacy", "privacy"),
           ("settings", "Settings", "settings"))

    def __init__(self, uninstall_path: str | None = None):
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
        w, h = px(1180), px(760)
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(px(1000), px(660))
        self.iconphoto(True, gfx.logo_img(64), gfx.logo_img(32), gfx.logo_img(16))

        self.ignore = IgnoreList()
        self.history = hist.History()
        self.privacy_backup = Backup(app_data_dir() / "privacy-backup.json")
        self.privacy_backend = None
        self.jobs: queue.Queue = queue.Queue()
        self.installed = []
        self.apps_state = "idle"         # idle, loading, ready, off
        self.results: dict[str, list | None] = {t: None for t in TABS}
        self.tab_state = {t: "idle" for t in TABS}   # idle, scanning, done
        self.everything = "idle"          # idle, scanning, done
        self.everything_current = ""
        self.privacy_statuses = None
        self.privacy_edition = ""
        self.trash = (0, 0)
        self.current = "home"
        self.pages = {}
        self.uninstall_path = uninstall_path

        self.after(80, self._poll)
        if needs_setup(self.settings.data):
            self.show_welcome()
        else:
            self.build()
            self.start_up()
        self.deiconify()

    def start_up(self):
        self.load_apps()
        self.load_privacy()
        self.refresh_trash()
        if self.uninstall_path:
            path, self.uninstall_path = self.uninstall_path, None
            self.show("apps")
            self.after(400, lambda: self.pages["apps"].uninstall_from_path(path))
        elif self.settings.data.get("scan_on_open", True) or hist.is_due(self.settings.data):
            self.after(300, self.scan_everything)

    # ------------------------------------------------------------ layout

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.pages.clear()

    def build(self):
        from .page_apps import UninstallerPage
        from .page_privacy import PrivacyPage
        from .page_settings import SettingsPage
        from .pages import CleanTabPage, LargeFilesPage, OverviewPage
        self._clear()
        P = th.P
        apply_ttk_styles(self)
        self.configure(bg=P.window)
        th.set_dark_title_bar(self, P.name == "dark")

        side = tk.Frame(self, bg=P.sidebar, width=px(236))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=P.sidebar)
        brand.pack(fill="x", padx=px(18), pady=(px(22), px(22)))
        tk.Label(brand, image=gfx.logo_img(px(30)), bg=P.sidebar).pack(side="left")
        label(brand, "WinPurge", "big").pack(side="left", padx=(px(10), 0))
        self.nav = {}
        for i, (key, text, icon) in enumerate(self.NAV, 1):
            item = NavItem(side, key, text, icon, self.show)
            item.pack(fill="x", padx=px(10), pady=px(1))
            self.nav[key] = item
        foot = tk.Frame(side, bg=P.sidebar)
        foot.pack(side="bottom", fill="x", padx=px(20), pady=px(16))
        self.trash_label = label(foot, "", "caption", P.text2, cursor="hand2")
        self.trash_label.pack(anchor="w")
        self.trash_label.bind("<Button-1>", lambda e: open_recycle_bin())
        mode = "Administrator" if is_admin() else "Standard user"
        label(foot, f"Version {__version__}  ·  {mode}", "caption", P.text3).pack(anchor="w", pady=(px(4), 0))
        tk.Frame(self, bg=P.divider, width=1).pack(side="left", fill="y")

        self.content = tk.Frame(self, bg=P.window)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages = {
            "home": OverviewPage(self.content, self),
            "caches": CleanTabPage(self.content, self, "caches"),
            "dev": CleanTabPage(self.content, self, "dev"),
            "large": LargeFilesPage(self.content, self),
            "apps": UninstallerPage(self.content, self),
            "privacy": PrivacyPage(self.content, self),
            "settings": SettingsPage(self.content, self),
        }
        self.toast = Toast(self.content)
        self.bind_shortcuts()
        self.show(self.current)
        self.update_badges()
        self.update_trash_label()

    def bind_shortcuts(self):
        keys = [k for k, _, _ in self.NAV]
        for i, key in enumerate(keys, 1):
            self.bind_all(f"<Control-Key-{i}>", lambda e, k=key: self.show(k))
        self.bind_all("<Control-r>", lambda e: self.pages[self.current].rescan())
        self.bind_all("<Control-R>", lambda e: self.scan_everything())
        self.bind_all("<F5>", lambda e: self.pages[self.current].rescan())
        self.bind_all("<Control-f>", lambda e: self.pages[self.current].focus_search())
        self.bind_all("<Control-comma>", lambda e: self.show("settings"))
        for i in (1, 2, 3):
            self.bind_all(f"<Alt-Key-{i}>", lambda e, n=i: self.pages[self.current].set_filter(n))

    def show(self, key):
        if key not in self.pages:
            return
        self.current = key
        for page in self.pages.values():
            page.pack_forget()
        for k, item in self.nav.items():
            item.set_active(k == key)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        page.on_show()

    def rebuild(self):
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
        self.start_up()

    def notify(self, event: str):
        """Tell every page what changed: apps, privacy, permissions, scan, cleaned, trash."""
        for page in list(self.pages.values()):
            page.on_event(event)
        if event in ("scan", "cleaned"):
            self.update_badges()

    def update_badges(self):
        if not getattr(self, "nav", None):
            return
        for tab, nav in (("caches", "caches"), ("dev", "dev"), ("large", "large")):
            items = self.results.get(tab)
            self.nav[nav].set_badge(human_size(sum(i.size for i in items)) if items else
                                    "…" if self.tab_state[tab] == "scanning" else "")

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

    # ------------------------------------------------------------ apps and privacy

    def load_apps(self, then=None):
        if not self.can("read_apps"):
            self.apps_state, self.installed = "off", []
            self.notify("apps")
            return
        self.apps_state = "loading"
        self.notify("apps")

        def done(apps):
            self.installed, self.apps_state = apps, "ready"
            self.notify("apps")
            if then:
                then()
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

    def refresh_trash(self):
        from .system import recycle_bin_size
        self.run_bg(recycle_bin_size, self._trash_done)

    def _trash_done(self, value):
        self.trash = value
        self.update_trash_label()
        self.notify("trash")

    def update_trash_label(self):
        if getattr(self, "trash_label", None) and self.trash_label.winfo_exists():
            size, n = self.trash
            self.trash_label.configure(text=f"♻  Recycle Bin: {human_size(size)}" if n else "♻  Recycle Bin is empty")

    # ------------------------------------------------------------ scanning

    def tab_allowed(self, tab: str) -> bool:
        return {"caches": self.can("scan_caches"),
                "dev": self.can("scan_caches") or self.can("scan_projects"),
                "large": self.can("scan_large_files"),
                "leftovers": self.can("scan_leftovers") and self.can("read_apps"),
                "cli": self.can("read_apps")}[tab]

    def _scan_work(self, tab: str):
        from .caches import count_once, default_project_roots, scan_app_caches, scan_dev_tools
        from .clitools import scan_cli_tools
        from .largefiles import default_roots, mark_duplicates, scan_ai_models, scan_large_files
        from .leftovers import find_orphans
        from .system import running_exes
        data = self.settings.data
        extra = list(data.get("project_roots", []))
        installed = list(self.installed)
        can_caches, can_projects = self.can("scan_caches"), self.can("scan_projects")
        admin = is_admin()

        def work():
            if tab == "caches":
                items = count_once(scan_app_caches())
            elif tab == "dev":
                items = scan_dev_tools(default_project_roots() + extra, int(data.get("stale_days", 30)),
                                       running_exes=running_exes(), projects=can_projects)
                if not can_caches:
                    items = [i for i in items if i.category == "Developer projects"]
                items = count_once(items)
            elif tab == "large":
                items = scan_large_files(default_roots() + extra) + scan_ai_models()
                mark_duplicates(items)
            elif tab == "leftovers":
                items = find_orphans(installed or list_installed_apps())
                for i in items:
                    i.tab = "leftovers"
            else:
                items = scan_cli_tools()
            items = [i for i in items if not self.ignore.contains(i.path)]
            for i in items:
                if i.extra.get("admin") and not admin:
                    i.extra["locked"] = ADMIN_LOCK
                    i.checked = False
            return sorted(items, key=lambda i: -i.size)
        work.__name__ = f"scan {tab}"
        return work

    def scan_tab(self, tab: str, then=None):
        if self.tab_state[tab] == "scanning":
            return
        if not self.tab_allowed(tab):
            self.results[tab], self.tab_state[tab] = None, "idle"
            self.notify("scan")
            if then:
                then()
            return
        self.tab_state[tab] = "scanning"
        self.notify("scan")

        def done(items):
            self.results[tab], self.tab_state[tab] = items, "done"
            self.notify("scan")
            if then:
                then()

        def failed(_):
            self.tab_state[tab] = "idle"
            self.notify("scan")
            if then:
                then()
        self.run_bg(self._scan_work(tab), done, failed)

    def scan_everything(self):
        """Every category, one at a time so the PC stays responsive."""
        if self.everything == "scanning":
            return
        order = [t for t in TABS if self.tab_allowed(t)]
        if not order:
            Dialog(self, "Nothing to scan", "All scans are turned off. Turn some on in Settings.",
                   (("Close", None, "secondary"), ("Open Settings", True, "primary")), icon="info").show() \
                and self.show("settings")
            return
        self.everything = "scanning"

        def step(i=0):
            if i >= len(order):
                self.everything, self.everything_current = "done", ""
                self.notify("scan")
                self.after(200, self.run_scheduled_clean_if_due)
                return
            self.everything_current = TAB_NAMES[order[i]]
            self.notify("scan")
            self.scan_tab(order[i], then=lambda: step(i + 1))

        if self.apps_state in ("loading", "idle") and self.can("read_apps"):
            self.load_apps(then=step)
        else:
            step()

    def safe_items(self) -> list:
        """What Clean Safe Items takes: Safe rows in App Caches and Dev Tools."""
        return [i for t in ("caches", "dev") for i in (self.results[t] or [])
                if i.level == SAFE and not i.locked]

    # ------------------------------------------------------------ cleaning

    def clean_items(self, items, parent=None, kind="manual", done=None):
        """Move items to the Recycle Bin. Running programs that use them are
        asked to close first (manual) or their items are skipped (scheduled)."""
        from .system import close_gracefully, owners_running
        items = [i for i in items if not i.locked]
        if not items:
            return
        owners = owners_running(items)
        skipped: list[tuple[str, str]] = []

        def proceed(close_pids: list[int], skip_items: list):
            def work():
                still = close_gracefully(close_pids) if close_pids else []
                drop = list(skip_items)
                for name, o in owners.items():
                    if set(o["pids"]) & set(still):
                        drop += o["items"]
                for it in drop:
                    skipped.append((it.path, "In use by a program that didn't close."))
                return recycle([i for i in items if i not in drop])

            def finished(res):
                entry = self.history.add(kind, res.bytes_moved, res.moved, skipped=res.failed + skipped)
                for tab in ("caches", "dev", "large", "leftovers"):
                    if self.results[tab]:
                        moved = set(res.moved)
                        self.results[tab] = [i for i in self.results[tab]
                                             if i.path not in moved or i.extra.get("contents_only")]
                self.notify("cleaned")
                self.refresh_trash()
                self.show_result(res, kind, skipped)
                if done:
                    done(res, entry)
            self.run_bg(work, finished)

        if owners and kind == "manual":
            names = sorted(owners)
            who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            choice = Dialog(parent or self, f"Close {who} first?",
                            f"{'It is' if len(names) == 1 else 'They are'} using files WinPurge is about to remove. "
                            "WinPurge asks them to close the way clicking X does, never by force. Anything still "
                            "open afterwards keeps its files.",
                            (("Cancel", None, "secondary"), ("Skip their items", "skip", "secondary"),
                             ("Close and continue", "close", "primary")), icon="warning").show()
            if choice is None:
                return
            if choice == "close":
                proceed([p for o in owners.values() for p in o["pids"]], [])
            else:
                proceed([], [it for o in owners.values() for it in o["items"]])
        else:
            proceed([], [it for o in owners.values() for it in o["items"]])

    def show_result(self, res, kind="manual", skipped=()):
        from .widgets import inform
        n = len(res.moved)
        if n:
            what = "Scheduled clean: moved" if kind == "scheduled" else "Moved"
            self.toast.show(f"{what} {n} item{'s' if n != 1 else ''} ({human_size(res.bytes_moved)}) to the "
                            "Recycle Bin.", "success",
                            action=("Open Recycle Bin", open_recycle_bin) if sys.platform == "win32" else None)
        failed = [f for f in res.failed if f not in skipped] + list(skipped)
        if failed and kind == "manual":
            lines = "\n".join(f"• {os.path.basename(p) or p}: {why}" for p, why in failed[:12])
            more = f"\n…and {len(failed) - 12} more" if len(failed) > 12 else ""
            inform(self, "Some items were left in place", lines + more, icon="warning", icon_color=th.P.warning)

    def run_scheduled_clean_if_due(self):
        if not hist.is_due(self.settings.data):
            return
        items = self.safe_items()
        hist.mark_done(self.settings.data)
        self.settings.save()
        if items:
            self.clean_items(items, kind="scheduled")
