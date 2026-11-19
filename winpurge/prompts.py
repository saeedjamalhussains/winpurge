"""Small windows the watcher opens on its own:

LeftoversPrompt: an app was just uninstalled; review only its leftovers.
  If there are none (or looking for leftovers is turned off), nothing appears.
ReminderPrompt: a scheduled clean is due; open WinPurge to run it."""
from __future__ import annotations

import tkinter as tk

from . import gfx
from . import history as hist
from . import theme as th
from .apps import App, list_installed_apps
from .common import CHECK, human_size
from .leftovers import find_dot_folders, find_leftovers, find_registry_leftovers
from .permissions import allowed
from .settings import Settings
from .theme import px
from .trash import IgnoreList, recycle
from .widgets import Button, Card, CheckTable, apply_ttk_styles, icon_label, label


class _Small(tk.Tk):
    def __init__(self, title, w, h):
        super().__init__(className="WinPurge")
        self.withdraw()
        self.settings = Settings()
        th.init(self, self.settings.data.get("theme", "system"))
        apply_ttk_styles(self)
        self.title(title)
        self.configure(bg=th.P.window)
        self.iconphoto(True, gfx.logo_img(32), gfx.logo_img(16))
        self.resizable(False, False)
        W, H = px(w), px(h)
        x = self.winfo_screenwidth() - W - px(24)
        y = self.winfo_screenheight() - H - px(72)
        self.geometry(f"{W}x{H}+{max(0, x)}+{max(0, y)}")
        self.attributes("-topmost", True)
        th.set_dark_title_bar(self, th.P.name == "dark")

    def show_now(self):
        self.deiconify()
        self.lift()
        self.after(1500, lambda: self.attributes("-topmost", False))


class LeftoversPrompt(_Small):
    def __init__(self, app: App):
        super().__init__("WinPurge", 620, 470)
        self.app_info = app
        if not allowed(self.settings.data, "scan_leftovers"):
            self.after(10, self.destroy)
            return
        self.after(50, self.look)

    def look(self):
        try:
            remaining = list_installed_apps()
            items = find_leftovers(self.app_info, remaining) + find_dot_folders(self.app_info)
            if allowed(self.settings.data, "registry_cleanup"):
                items += find_registry_leftovers(self.app_info, remaining)
        except OSError:
            items = []
        ignore = IgnoreList()
        items = [i for i in items if not ignore.contains(i.path)]
        if not items:
            self.destroy()          # nothing left behind: stay out of the way
            return
        for i in items:
            # Exact matches inside your folders arrive ticked; settings folders,
            # registry keys and anything uncertain arrive unticked.
            i.checked = i.level != CHECK
        self.items = items
        self.build()
        self.show_now()

    def build(self):
        P = th.P
        body = tk.Frame(self, bg=P.window, padx=px(22), pady=px(18))
        body.pack(fill="both", expand=True)
        top = tk.Frame(body, bg=P.window)
        top.pack(fill="x")
        tk.Label(top, image=gfx.logo_img(px(36)), bg=P.window).pack(side="left")
        t = tk.Frame(top, bg=P.window)
        t.pack(side="left", padx=(px(12), 0))
        label(t, f"{self.app_info.name} was uninstalled", "heading").pack(anchor="w")
        total = human_size(sum(i.size for i in self.items))
        label(t, f"It left {len(self.items)} item{'s' if len(self.items) != 1 else ''} behind ({total}).",
              "caption").pack(anchor="w")
        card = Card(body, padding=4, stretch=True)
        card.configure(height=px(250))
        card.pack(fill="both", expand=True, pady=(px(14), px(10)))
        self.table = CheckTable(card.body, grouped=False)
        self.table.pack(fill="both", expand=True)
        self.table.set_items(self.items, human_size)
        label(body, "Ticked items move to the Recycle Bin, so you can put them back until you empty it.",
              "caption", wrap=px(560)).pack(anchor="w")
        foot = tk.Frame(self, bg=P.sidebar, padx=px(22), pady=px(14))
        foot.pack(fill="x", side="bottom")
        self.go_btn = Button(foot, "Move to Recycle Bin", icon="delete", kind="primary", command=self.clean)
        self.go_btn.pack(side="right")
        Button(foot, "Keep all", kind="secondary", command=self.destroy).pack(side="right", padx=(0, px(8)))
        self.bind("<Escape>", lambda e: self.destroy())

    def clean(self):
        chosen = self.table.checked()
        if not chosen:
            self.destroy()
            return
        self.go_btn.set_text("Moving…")
        self.go_btn.set_disabled(True)
        self.update()
        res = recycle(chosen)
        hist.History().add("manual", res.bytes_moved, res.moved, skipped=res.failed)
        if res.failed:
            from .widgets import inform
            inform(self, "Some items were left in place",
                   "\n".join(f"• {p}: {w}" for p, w in res.failed[:10]), icon="warning")
        self.destroy()


class ReminderPrompt(_Small):
    def __init__(self):
        super().__init__("WinPurge", 440, 190)
        if not hist.is_due(self.settings.data):
            self.after(10, self.destroy)
            return
        P = th.P
        body = tk.Frame(self, bg=P.window, padx=px(22), pady=px(18))
        body.pack(fill="both", expand=True)
        top = tk.Frame(body, bg=P.window)
        top.pack(fill="x")
        icon_label(top, "history", 16, P.accent).pack(side="left", anchor="n")
        t = tk.Frame(top, bg=P.window)
        t.pack(side="left", padx=(px(12), 0))
        label(t, "Your scheduled clean is due", "heading").pack(anchor="w")
        label(t, "Open WinPurge to move the safe caches and build folders to the Recycle Bin.", "caption",
              wrap=px(340)).pack(anchor="w", pady=(px(2), 0))
        foot = tk.Frame(self, bg=P.sidebar, padx=px(22), pady=px(12))
        foot.pack(fill="x", side="bottom")
        Button(foot, "Clean now", kind="primary", command=self.open_app).pack(side="right")
        Button(foot, "Later", kind="secondary", command=self.destroy).pack(side="right", padx=(0, px(8)))
        self.show_now()

    def open_app(self):
        from .shell import launch
        launch()        # WinPurge runs a due clean when it opens
        self.destroy()
