"""The five pages of the WinPurge window."""
from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from . import __version__, crashlog, gfx
from . import theme as th
from .apps import list_installed_apps, run_uninstaller
from .common import SAFE, human_size
from .leftovers import find_leftovers, find_registry_leftovers
from .permissions import PERMISSIONS
from .privacy import SETTINGS, apply, restore
from .theme import px
from .trash import app_data_dir, is_admin, recycle
from .widgets import (Badge, Button, Card, CheckTable, Dialog, Dropdown, ProgressBar, ScrollFrame, SearchBox,
                      Toggle, ask, icon_label, inform, label)

PAD = 32


class Page(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=th.P.window)
        self.app = app
        self.build()

    def header(self, title, subtitle):
        P = th.P
        h = tk.Frame(self, bg=P.window)
        h.pack(fill="x", padx=px(PAD), pady=(px(28), px(18)))
        left = tk.Frame(h, bg=P.window)
        left.pack(side="left", fill="x", expand=True)
        label(left, title, "title").pack(anchor="w")
        label(left, subtitle, "body", P.text2).pack(anchor="w", pady=(px(2), 0))
        actions = tk.Frame(h, bg=P.window)
        actions.pack(side="right", anchor="s")
        return actions

    def build(self):
        pass

    def on_show(self):
        pass

    def on_event(self, event):
        pass


def icon_chip(parent, name, color=None, soft=None, size=36):
    """An icon in a soft rounded square."""
    P = th.P
    from .widgets import rounded_rect
    cv = tk.Canvas(parent, width=px(size), height=px(size), bg=parent.cget("bg"), highlightthickness=0, bd=0)
    rounded_rect(cv, 0, 0, px(size), px(size), px(8), soft or P.accent_soft)
    cv.create_text(px(size) / 2, px(size) / 2, text=th.icon(name), font=th.icon_font(size * 0.38),
                   fill=color or P.accent)
    return cv


def divider(parent, pady=10):
    tk.Frame(parent, bg=th.P.divider, height=1).pack(fill="x", pady=px(pady))


def setting_row(parent, title, desc, control_factory, badge=None, status=None):
    """Title and description on the left, a control on the right."""
    P = th.P
    row = tk.Frame(parent, bg=parent.cget("bg"))
    row.pack(fill="x", pady=px(4))
    right = tk.Frame(row, bg=row.cget("bg"))
    right.pack(side="right", padx=(px(16), 0))
    control = control_factory(right)
    control.pack(side="right")
    left = tk.Frame(row, bg=row.cget("bg"))
    left.pack(side="left", fill="x", expand=True)
    top = tk.Frame(left, bg=row.cget("bg"))
    top.pack(anchor="w")
    label(top, title, "strong").pack(side="left")
    if badge:
        Badge(top, *badge).pack(side="left", padx=(px(8), 0))
    if desc:
        label(left, desc, "caption", wrap=px(560)).pack(anchor="w", pady=(px(2), 0))
    if status:
        text, color = status
        s = tk.Frame(left, bg=row.cget("bg"))
        s.pack(anchor="w", pady=(px(4), 0))
        tk.Label(s, text="●", font=th.font(8), fg=color, bg=row.cget("bg")).pack(side="left")
        label(s, text, "caption", color).pack(side="left", padx=(px(4), 0))
    return control


# ====================================================================== Home

class StatCard(Card):
    def __init__(self, parent, icon, title, action_text, action, bar=True):
        super().__init__(parent, padding=20)
        P = th.P
        b = self.body
        top = tk.Frame(b, bg=P.card)
        top.pack(fill="x")
        icon_chip(top, icon).pack(side="left")
        label(top, title, "strong", P.text2).pack(side="left", padx=(px(12), 0))
        self.value = label(b, "—", "big")
        self.value.pack(anchor="w", pady=(px(16), 0))
        self.caption = label(b, "", "caption")
        self.caption.pack(anchor="w", pady=(px(2), 0))
        # Cards without a bar keep the same height, so the three line up.
        self.bar = ProgressBar(b, height=6) if bar else tk.Frame(b, bg=P.card, height=px(6))
        self.bar.pack(fill="x", pady=(px(14), 0))
        self.action = Button(b, text=action_text + "  ›", kind="link", command=action, height=24)
        self.action.pack(anchor="w", pady=(px(14), 0))


class HomePage(Page):
    def build(self):
        P = th.P
        self.header("Overview", "Keep your PC clean, light and private.")
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True, padx=(px(PAD), px(PAD) - px(12)))
        body = scroll.inner

        hero = Card(body, padding=28)
        hero.pack(fill="x", padx=(0, px(12)))
        hb = hero.body
        hb.columnconfigure(0, weight=1)
        left = tk.Frame(hb, bg=P.card)
        left.grid(row=0, column=0, sticky="we")
        label(left, "SMART SCAN", "caption", P.accent).configure(font=th.font(8, "semibold"))
        left.winfo_children()[-1].pack(anchor="w")
        self.hero_title = label(left, "", "display")
        self.hero_title.pack(anchor="w", pady=(px(6), 0))
        self.hero_text = label(left, "", "body", P.text2, wrap=px(560))
        self.hero_text.pack(anchor="w", pady=(px(6), 0))
        self.hero_bar = ProgressBar(left, height=4)
        right = tk.Frame(hb, bg=P.card)
        right.grid(row=0, column=1, sticky="e", padx=(px(24), 0))
        self.scan_btn = Button(right, "Scan now", icon="sparkle", kind="primary", height=40, min_width=160,
                               command=self.app.start_scan)
        self.scan_btn.pack(anchor="e")
        self.review_btn = Button(right, "Review and clean", icon="chevron_right", kind="primary", height=40,
                                 min_width=160, command=lambda: self.app.show("clean"))
        self.again_btn = Button(right, "Scan again", kind="link", height=28, command=self.app.start_scan)

        row = tk.Frame(body, bg=P.window)
        row.pack(fill="x", pady=(px(16), 0), padx=(0, px(12)))
        for i in range(3):
            row.columnconfigure(i, weight=1, uniform="stats")
        self.storage = StatCard(row, "drive", "Storage", "Open Storage settings", self._storage_settings)
        self.apps = StatCard(row, "apps", "Apps", "Manage apps", lambda: self.app.show("apps"), bar=False)
        self.privacy = StatCard(row, "privacy", "Privacy", "Review privacy", lambda: self.app.show("privacy"))
        for i, c in enumerate((self.storage, self.apps, self.privacy)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(8), 0 if i == 2 else px(8)))

        trust = tk.Frame(body, bg=P.window)
        trust.pack(fill="x", pady=(px(22), px(12)), padx=(0, px(12)))
        for i in range(3):
            trust.columnconfigure(i, weight=1, uniform="trust")
        for i, (icon, title, text) in enumerate((
                ("recycle", "Recycle Bin first", "Everything removed can be put back until you empty it."),
                ("offline", "Works offline", "WinPurge never connects to the internet."),
                ("undo", "Your settings are saved", "Privacy changes can be restored in one click."))):
            f = tk.Frame(trust, bg=P.window)
            f.grid(row=0, column=i, sticky="nw", padx=(0, px(12)))
            icon_label(f, icon, 12, P.text3).pack(side="left", anchor="n", pady=(px(1), 0))
            t = tk.Frame(f, bg=P.window)
            t.pack(side="left", padx=(px(8), 0))
            label(t, title, "strong", P.text2).pack(anchor="w")
            label(t, text, "caption", P.text3, wrap=px(220)).pack(anchor="w")

    def _storage_settings(self):
        if sys.platform == "win32":
            os.startfile("ms-settings:storagesense")

    def on_show(self):
        self.update_hero()
        self.update_stats()

    def on_event(self, event):
        if event == "scan":
            self.update_hero()
        if event in ("apps", "privacy", "permissions", "scan"):
            self.update_stats()

    def update_hero(self):
        app, P = self.app, th.P
        for w in (self.scan_btn, self.review_btn, self.again_btn):
            w.pack_forget()
        self.hero_bar.pack_forget()
        self.hero_bar.stop()
        if app.scan_state == "scanning":
            self.hero_title.configure(text="Scanning your PC…")
            self.hero_text.configure(text="Looking through caches, old build folders and data from removed apps. "
                                          "This usually takes under a minute.")
            self.hero_bar.pack(fill="x", pady=(px(16), 0))
            self.hero_bar.start()
            self.scan_btn.set_text("Scanning…")
            self.scan_btn.set_disabled(True)
            self.scan_btn.pack(anchor="e")
        elif app.scan_state == "done" and app.scan_items:
            items = app.scan_items
            safe = [i for i in items if i.level == SAFE]
            self.hero_title.configure(text=f"{human_size(sum(i.size for i in items))} can be cleaned")
            self.hero_text.configure(
                text=f"Found {len(items)} items. {human_size(sum(i.size for i in safe))} of it is safe to remove "
                     "and already selected. Everything goes to the Recycle Bin.")
            self.review_btn.pack(anchor="e")
            self.again_btn.pack(anchor="center", pady=(px(10), 0))
        elif app.scan_state == "done":
            self.hero_title.configure(text="Your PC is already tidy")
            self.hero_text.configure(text="Nothing worth removing turned up. Check back in a few weeks.")
            self.scan_btn.set_text("Scan again")
            self.scan_btn.set_disabled(False)
            self.scan_btn.pack(anchor="e")
        else:
            self.hero_title.configure(text="Find what you can safely remove")
            self.hero_text.configure(text="Smart Scan looks for caches, old build folders and data left by apps "
                                          "you removed. Nothing is touched until you review it.")
            self.scan_btn.set_text("Scan now")
            self.scan_btn.set_disabled(False)
            self.scan_btn.pack(anchor="e")

    def update_stats(self):
        app, P = self.app, th.P
        # Storage
        drive = (os.environ.get("SystemDrive", "C:") + "\\") if sys.platform == "win32" else "/"
        try:
            du = shutil.disk_usage(drive)
            used = du.used / du.total
            self.storage.value.configure(text=f"{human_size(du.free)} free")
            self.storage.caption.configure(text=f"of {human_size(du.total)} on {drive.rstrip(chr(92))}")
            self.storage.bar.set(used, P.danger if used > 0.9 else P.warning if used > 0.8 else P.accent)
        except OSError:
            self.storage.value.configure(text="—")
        # Apps
        if app.apps_state == "ready":
            total = sum(a.size_kb for a in app.installed) * 1024
            self.apps.value.configure(text=f"{len(app.installed)} apps")
            self.apps.caption.configure(text=f"Using about {human_size(total)}" if total else "Installed on this PC")
        elif app.apps_state == "loading":
            self.apps.value.configure(text="…")
            self.apps.caption.configure(text="Reading installed apps")
        elif app.apps_state == "off":
            self.apps.value.configure(text="Off")
            self.apps.caption.configure(text="Turn on in Settings")
        # Privacy
        st = app.privacy_statuses
        if not app.can("privacy"):
            self.privacy.value.configure(text="Off")
            self.privacy.caption.configure(text="Turn on in Settings to review")
            self.privacy.bar.set(0)
        elif st is None:
            self.privacy.value.configure(text="…")
            self.privacy.caption.configure(text="Reading privacy settings")
        else:
            n = sum(s.is_private for s in st)
            self.privacy.value.configure(text=f"{n} of {len(st)} private")
            self.privacy.caption.configure(text="All set" if n == len(st) else f"{len(st) - n} could share less")
            self.privacy.bar.set(n / len(st), P.success if n == len(st) else P.accent)


# ====================================================================== Apps

class AppsPage(Page):
    COLS = (("name", "Name", 300), ("publisher", "Publisher", 200), ("version", "Version", 110), ("size", "Size", 90))

    def build(self):
        P = th.P
        actions = self.header("Apps", "Uninstall apps completely, including the files they leave behind.")
        Button(actions, icon="refresh", kind="subtle", command=self.app.load_apps).pack(side="right")
        self.search = SearchBox(actions, "Search apps", command=lambda q: self.fill())
        self.search.pack(side="right", padx=(0, px(8)))
        self.sort_key, self.sort_rev = "name", False

        wrap = tk.Frame(self, bg=P.window)
        wrap.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(24)))
        foot = Card(wrap, padding=16)
        foot.pack(side="bottom", fill="x", pady=(px(12), 0))
        card = Card(wrap, padding=6, stretch=True)
        card.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(card.body, style="WP.Treeview", columns=[c[0] for c in self.COLS],
                                 show="headings", selectmode="browse")
        for key, text, width in self.COLS:
            self.tree.heading(key, text=text, anchor="e" if key == "size" else "w",
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=px(width), anchor="e" if key == "size" else "w",
                             stretch=key in ("name", "publisher"))
        bar = ttk.Scrollbar(card.body, orient="vertical", command=self.tree.yview, style="WP.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_footer())
        self.tree.bind("<Double-1>", lambda e: self.uninstall())
        self.overlay = label(card.body, "", "body", P.text2)

        fb = foot.body
        self.uninstall_btn = Button(fb, "Uninstall…", icon="delete", kind="danger", min_width=140,
                                    command=self.uninstall)
        self.uninstall_btn.pack(side="right")
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.sel_caption = label(info, "", "caption")
        self.sel_caption.pack(anchor="w")
        self.update_footer()

    def on_show(self):
        self.fill()

    def on_event(self, event):
        if event in ("apps", "permissions"):
            self.fill()

    def sort_by(self, key):
        self.sort_rev = not self.sort_rev if self.sort_key == key else key == "size"
        self.sort_key = key
        self.fill()

    def fill(self):
        app = self.app
        self.tree.delete(*self.tree.get_children())
        msg = {"loading": "Reading installed apps…", "off": "Reading installed apps is turned off. "
               "Turn it on in Settings.", "idle": ""}.get(app.apps_state, "")
        q = self.search.get().lower().strip()
        rows = [(i, a) for i, a in enumerate(app.installed)
                if not q or q in a.name.lower() or q in a.publisher.lower()]
        keyf = {"name": lambda r: r[1].name.lower(), "publisher": lambda r: r[1].publisher.lower(),
                "version": lambda r: r[1].version, "size": lambda r: r[1].size_kb}[self.sort_key]
        rows.sort(key=keyf, reverse=self.sort_rev)
        for i, a in rows:
            self.tree.insert("", "end", iid=str(i), values=(
                a.name, a.publisher or "—", a.version or "",
                human_size(a.size_kb * 1024) if a.size_kb else ""))
        if app.apps_state == "ready" and not rows:
            msg = f"No apps match “{q}”." if q else "No apps found."
        if msg:
            self.overlay.configure(text=msg)
            self.overlay.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.overlay.place_forget()
        self.update_footer()

    def selected_app(self):
        sel = self.tree.focus()
        return self.app.installed[int(sel)] if sel and int(sel) < len(self.app.installed) else None

    def update_footer(self):
        a = self.selected_app()
        if a:
            self.sel_title.configure(text=a.name)
            parts = [p for p in (a.publisher, f"Version {a.version}" if a.version else "",
                                 human_size(a.size_kb * 1024) if a.size_kb else "") if p]
            self.sel_caption.configure(text="  ·  ".join(parts))
        else:
            n = len(self.app.installed)
            self.sel_title.configure(text="Select an app to uninstall" if n else "Apps")
            self.sel_caption.configure(text=f"{n} apps installed" if n else "")
        self.uninstall_btn.set_disabled(a is None)

    def uninstall(self):
        app = self.selected_app()
        if not app:
            return
        if not ask(self, f"Uninstall {app.name}?",
                   "Its own uninstaller opens first. When it finishes, WinPurge looks for files and settings "
                   "it left behind and shows them to you before anything is removed.",
                   ok="Uninstall", danger=True, icon="delete"):
            return
        look_files, look_reg = self.app.can("scan_leftovers"), self.app.can("registry_cleanup")
        ignore = self.app.ignore

        def uninstall_app():
            code = run_uninstaller(app)
            remaining = list_installed_apps()
            gone = not any(a.key_name == app.key_name and a.norm == app.norm for a in remaining)
            items = (find_leftovers(app, remaining) if look_files and gone else []) + \
                (find_registry_leftovers(app, remaining) if look_reg and gone else [])
            return code, gone, remaining, [i for i in items if not ignore.contains(i.path)]

        self.uninstall_btn.set_text("Uninstalling…")
        self.uninstall_btn.set_disabled(True)
        self.app.toast.show(f"Finish {app.name}’s uninstaller window to continue.", "info", seconds=8)

        def done(result):
            code, gone, remaining, items = result
            self.uninstall_btn.set_text("Uninstall…")
            self.app.installed = remaining
            self.app.notify("apps")
            if not gone:
                inform(self, f"{app.name} is still installed",
                       "The uninstaller may have been cancelled, or it needs a restart to finish.", icon="info")
            elif not items:
                self.app.toast.show(f"{app.name} was removed. Nothing was left behind.")
            else:
                self.leftovers(app, items)

        def failed(_):
            self.uninstall_btn.set_text("Uninstall…")
            self.update_footer()
        self.app.run_bg(uninstall_app, done, failed)

    def leftovers(self, app, items):
        P = th.P

        def build(frame):
            box = Card(frame, padding=4, stretch=True)
            box.configure(width=px(600), height=px(280))
            box.pack(fill="both", expand=True)
            table = CheckTable(box.body, confirm_check=lambda it: ask(self, "Check first", it.note or
                               "This may hold data you want to keep.", ok="Select it"))
            table.pack(fill="both", expand=True)
            table.set_items(items, human_size)
        size = human_size(sum(i.size for i in items if i.checked))
        ok = Dialog(self, f"{app.name} left files behind",
                    "Ticked items move to the Recycle Bin, so you can put them back until you empty it.",
                    (("Keep all", False, "secondary"), ("Move to Recycle Bin", True, "primary")),
                    icon="clean", width=600, build=build).show()
        chosen = [i for i in items if i.checked]
        if ok and chosen:
            self.app.run_bg(lambda: recycle(chosen), lambda r: show_result(self.app, r))


def show_result(app, res):
    from .app import open_recycle_bin
    if res.moved:
        app.toast.show(f"Moved {len(res.moved)} item{'s' if len(res.moved) != 1 else ''} "
                       f"({human_size(res.bytes_moved)}) to the Recycle Bin.", "success",
                       action=("Open Recycle Bin", open_recycle_bin) if sys.platform == "win32" else None)
    if res.failed:
        lines = "\n".join(f"• {os.path.basename(p) or p}: {why}" for p, why in res.failed[:12])
        more = f"\n…and {len(res.failed) - 12} more" if len(res.failed) > 12 else ""
        inform(app, "Some items were left in place", lines + more, icon="warning", icon_color=th.P.warning)


# ====================================================================== Clean Up

class CleanPage(Page):
    def build(self):
        P = th.P
        actions = self.header("Clean Up", "Caches, old build folders and data from apps you removed.")
        self.rescan_btn = Button(actions, "Scan again", icon="refresh", kind="secondary",
                                 command=self.app.start_scan)
        self.rescan_btn.pack(side="right")

        self.stack = tk.Frame(self, bg=P.window)
        self.stack.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(24)))

        # Empty / scanning state
        self.empty = Card(self.stack, padding=40, stretch=True)
        mid = tk.Frame(self.empty.body, bg=P.card)
        mid.place(relx=0.5, rely=0.45, anchor="center")
        icon_chip(mid, "clean", size=56).pack()
        self.empty_title = label(mid, "", "heading")
        self.empty_title.pack(pady=(px(16), 0))
        self.empty_text = label(mid, "", "body", P.text2, wrap=px(420))
        self.empty_text.configure(justify="center", anchor="center")
        self.empty_text.pack(pady=(px(6), 0))
        self.empty_bar = ProgressBar(mid, height=4)
        self.empty_bar.configure(width=px(260))
        self.empty_btn = Button(mid, "Scan now", icon="sparkle", kind="primary", height=40, min_width=160,
                                command=self.app.start_scan)

        # Results
        self.results = tk.Frame(self.stack, bg=P.window)
        self.chips = tk.Frame(self.results, bg=P.window)
        self.chips.pack(fill="x", pady=(0, px(12)))
        foot = Card(self.results, padding=16)
        foot.pack(side="bottom", fill="x", pady=(px(12), 0))
        self.detail = tk.Frame(self.results, bg=P.window)
        self.detail.pack(side="bottom", fill="x", pady=(px(10), 0))
        card = Card(self.results, padding=6, stretch=True)
        card.pack(fill="both", expand=True)
        self.table = CheckTable(card.body, on_change=self.update_footer, on_select=self.show_detail,
                                confirm_check=self.confirm_check)
        self.table.pack(fill="both", expand=True)

        self.detail_path = label(self.detail, "", "caption", P.text2)
        self.detail_path.pack(side="left", fill="x", expand=True)
        self.ignore_btn = Button(self.detail, "Don’t suggest again", kind="subtle", height=28,
                                 command=self.ignore_selected)
        self.reveal_btn = Button(self.detail, "Show in Explorer", icon="open", kind="subtle", height=28,
                                 command=self.reveal)

        fb = foot.body
        self.clean_btn = Button(fb, "Move to Recycle Bin", icon="delete", kind="primary", min_width=190,
                                command=self.clean)
        self.clean_btn.pack(side="right")
        Button(fb, "Select safe items", kind="subtle", command=lambda: self.table.tick(lambda i: i.level == SAFE)) \
            .pack(side="right", padx=(0, px(8)))
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.sel_caption = label(info, "Removed items go to the Recycle Bin. Empty it to get the space back.",
                                 "caption")
        self.sel_caption.pack(anchor="w")
        self._shown_items = None

    def on_show(self):
        self.refresh()

    def on_event(self, event):
        if event in ("scan", "permissions"):
            self.refresh()

    def refresh(self):
        app = self.app
        scanning = app.scan_state == "scanning"
        self.rescan_btn.set_text("Scanning…" if scanning else "Scan again")
        self.rescan_btn.set_disabled(scanning)
        if app.scan_items:
            self.empty.pack_forget()
            self.results.pack(fill="both", expand=True)
            if self._shown_items is not app.scan_items:
                self._shown_items = app.scan_items
                self.table.set_items(app.scan_items, human_size)
                self.show_detail(None)
            self.update_chips()
            return
        self.results.pack_forget()
        self.empty.pack(fill="both", expand=True)
        self.empty_bar.pack_forget()
        self.empty_btn.pack_forget()
        self.rescan_btn.pack_forget() if not scanning and app.scan_state != "done" else self.rescan_btn.pack(side="right")
        if scanning:
            self.empty_title.configure(text="Scanning your PC…")
            self.empty_text.configure(text="Looking through caches, old build folders and data from removed apps.")
            self.empty_bar.pack(pady=(px(18), 0))
            self.empty_bar.start()
        elif app.scan_state == "done":
            self.empty_bar.stop()
            self.empty_title.configure(text="Nothing to clean")
            self.empty_text.configure(text="Your PC is tidy. Scan again any time.")
            self.empty_btn.set_text("Scan again")
            self.empty_btn.pack(pady=(px(18), 0))
        else:
            self.empty_bar.stop()
            reason = app.scan_blocked_reason()
            self.empty_title.configure(text="Nothing scanned yet")
            self.empty_text.configure(text=reason or "Run Smart Scan to find caches, old build folders and data "
                                                     "left by apps you removed. Nothing is removed until you choose.")
            self.empty_btn.set_text("Open Settings" if reason else "Scan now")
            self.empty_btn.command = (lambda: app.show("settings")) if reason else app.start_scan
            self.empty_btn.pack(pady=(px(18), 0))

    def update_chips(self):
        P = th.P
        for w in self.chips.winfo_children():
            w.destroy()
        totals: dict[str, int] = {}
        for i in self.table.items.values():
            totals[i.category] = totals.get(i.category, 0) + i.size
        icons = {"Caches": "clean", "Old projects": "folder", "Unused app data": "apps", "Leftovers": "apps"}
        for cat, size in totals.items():
            c = Card(self.chips, padding=12, fit_width=True)
            c.pack(side="left", padx=(0, px(10)))
            icon_chip(c.body, icons.get(cat, "clean"), size=28).pack(side="left")
            t = tk.Frame(c.body, bg=P.card)
            t.pack(side="left", padx=(px(10), px(6)))
            label(t, human_size(size), "strong").pack(anchor="w")
            label(t, cat, "caption").pack(anchor="w")

    def update_footer(self):
        ticked = self.table.checked()
        size = sum(i.size for i in ticked)
        self.sel_title.configure(text=f"{len(ticked)} selected  ·  {human_size(size)}" if ticked
                                 else "Nothing selected")
        self.clean_btn.set_disabled(not ticked)

    def show_detail(self, item):
        for b in (self.ignore_btn, self.reveal_btn):
            b.pack_forget()
        if not item:
            self.detail_path.configure(text="Select an item to see where it is and what it holds.")
            return
        text = item.path + (f"\n{item.note}" if item.note else "")
        self.detail_path.configure(text=text, wraplength=px(620))
        self.ignore_btn.pack(side="right")
        if sys.platform == "win32" and item.kind == "path":
            self.reveal_btn.pack(side="right", padx=(0, px(4)))

    def reveal(self):
        from .app import show_in_explorer
        it = self.table.selected()
        if it:
            show_in_explorer(it.path)

    def ignore_selected(self):
        it = self.table.selected()
        if not it:
            return
        self.app.ignore.add(it.path)
        self.app.scan_items = [i for i in self.app.scan_items if i.path != it.path]
        self._shown_items = self.app.scan_items
        self.table.remove_paths({it.path})
        self.show_detail(None)
        self.update_chips()
        self.app.toast.show("Hidden. You can show hidden items again in Settings.", "info")

    def confirm_check(self, item):
        return ask(self, "Check first", (item.note or "This may hold data you want to keep.") +
                   "\n\nSelect it anyway?", ok="Select it", icon="warning")

    def clean(self):
        items = self.table.checked()
        if not items:
            return
        size = human_size(sum(i.size for i in items))
        if not ask(self, f"Move {len(items)} item{'s' if len(items) != 1 else ''} to the Recycle Bin?",
                   f"That’s about {size}. You can restore anything from the Recycle Bin until you empty it, "
                   "and the space comes back when you do.", ok="Move to Recycle Bin", icon="delete"):
            return
        self.clean_btn.set_text("Cleaning…")
        self.clean_btn.set_disabled(True)

        def done(res):
            self.clean_btn.set_text("Move to Recycle Bin")
            moved = set(res.moved)
            self.table.remove_paths(moved)
            self.app.scan_items = [i for i in self.app.scan_items
                                   if i.path not in moved or i.extra.get("contents_only")]
            self._shown_items = self.app.scan_items
            for i in self.app.scan_items:
                if i.path in moved:
                    i.checked = False
            self.update_chips()
            self.update_footer()
            self.app.notify("scan")
            show_result(self.app, res)
        self.app.run_bg(lambda: recycle(items), done, lambda e: self.update_footer())


# ====================================================================== Privacy

class PrivacyPage(Page):
    def build(self):
        actions = self.header("Privacy", "See what Windows shares about you, and change it in one place.")
        self.private_btn = Button(actions, "Make everything private", icon="shield", kind="primary",
                                  command=self.make_private)
        self.private_btn.pack(side="right")
        self.restore_btn = Button(actions, "Restore originals", icon="undo", kind="subtle", command=self.restore)
        self.restore_btn.pack(side="right", padx=(0, px(8)))
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=(px(PAD), px(PAD) - px(12)))
        self._rendered = None

    def on_show(self):
        self.render()

    def on_event(self, event):
        if event in ("privacy", "permissions"):
            self.render()

    def render(self):
        app, P = self.app, th.P
        body = self.scroll.inner
        for w in body.winfo_children():
            w.destroy()
        self.restore_btn.set_disabled(app.privacy_backup.empty)
        allowed_ = app.can("privacy")
        self.private_btn.set_disabled(not allowed_ or app.privacy_statuses is None)
        if not allowed_:
            c = Card(body, padding=28)
            c.pack(fill="x", padx=(0, px(12)))
            row = tk.Frame(c.body, bg=P.card)
            row.pack(fill="x")
            icon_chip(row, "lock", size=44).pack(side="left", anchor="n")
            t = tk.Frame(row, bg=P.card)
            t.pack(side="left", fill="x", expand=True, padx=(px(16), 0))
            label(t, "Privacy settings are turned off", "heading").pack(anchor="w")
            label(t, "Turn on “Show and change Windows privacy settings” in Settings to see what this PC "
                     "shares with Microsoft and change it here.", "body", P.text2, wrap=px(560)).pack(anchor="w", pady=(px(4), 0))
            Button(row, "Open Settings", kind="secondary", command=lambda: app.show("settings")).pack(side="right")
            return
        st = app.privacy_statuses
        if st is None:
            label(body, "Reading privacy settings…", "body", P.text2).pack(anchor="w", pady=px(20))
            return
        admin = is_admin()
        n = sum(s.is_private for s in st)

        score = Card(body, padding=24)
        score.pack(fill="x", padx=(0, px(12)))
        sb = score.body
        top = tk.Frame(sb, bg=P.card)
        top.pack(fill="x")
        icon_chip(top, "shield", P.success if n == len(st) else P.accent,
                  P.success_soft if n == len(st) else P.accent_soft, size=44).pack(side="left")
        t = tk.Frame(top, bg=P.card)
        t.pack(side="left", padx=(px(16), 0))
        label(t, f"{n} of {len(st)} settings are private", "big").pack(anchor="w")
        edition = f"Windows {app.privacy_edition}. " if app.privacy_edition else ""
        label(t, edition + "Changes apply right away and your originals are saved. Some take effect after you "
                 "sign out.", "caption", wrap=px(600)).pack(anchor="w", pady=(px(2), 0))
        bar = ProgressBar(sb, height=6)
        bar.pack(fill="x", pady=(px(16), 0))
        bar.set(n / len(st), P.success if n == len(st) else P.accent)

        locked = [s for s in st if s.setting.admin]
        if locked and not admin:
            ban = Card(body, padding=16, fill=P.warning_soft, outline=P.warning_soft)
            ban.pack(fill="x", padx=(0, px(12)), pady=(px(12), 0))
            icon_label(ban.body, "admin", 13, P.warning).pack(side="left")
            label(ban.body, f"{len(locked)} settings need administrator rights to change.", "body",
                  P.text).pack(side="left", padx=(px(10), 0))
            Button(ban.body, "Restart as administrator", icon="admin", kind="secondary",
                   command=app.restart_as_admin).pack(side="right")

        groups: dict[str, list] = {}
        for s in st:
            groups.setdefault(s.setting.group, []).append(s)
        for group, rows in groups.items():
            label(body, group, "heading").pack(anchor="w", pady=(px(24), px(8)))
            card = Card(body, padding=20)
            card.pack(fill="x", padx=(0, px(12)))
            for i, s in enumerate(rows):
                if i:
                    divider(card.body, 10)
                self.privacy_row(card.body, s, admin)
        tk.Frame(body, bg=P.window, height=px(24)).pack()

    def privacy_row(self, parent, status, admin):
        P = th.P
        s = status.setting
        locked = s.admin and not admin
        keys = [o.key for o in s.options]
        state_text = ("Private" if status.is_private else "Not private") + (
            f"  ·  {status.label}" if status.current not in ("on", "off") else "")
        color = P.success if status.is_private else P.warning

        def control(parent_):
            if set(keys) == {"on", "off"}:
                t = Toggle(parent_, value=status.current == "on",
                           command=lambda v: self.change(s, "on" if v else "off"))
                t.set_disabled(locked)
                return t
            d = Dropdown(parent_, [(o.key, o.label) for o in s.options], status.current,
                         command=lambda k: self.change(s, k), min_width=200)
            d.set_disabled(locked)
            return d
        desc = s.detail + (f" {s.note}" if s.note else "")
        setting_row(parent, s.title, desc, control, badge=("Admin", "neutral") if s.admin else None,
                    status=(state_text, color))

    def change(self, setting, option_key):
        app = self.app
        admin = is_admin()

        def done(res):
            app.load_privacy()
            if res.failed:
                inform(self, "Couldn’t change that setting", "\n".join(f"{n}: {w}" for n, w in res.failed),
                       icon="warning", icon_color=th.P.warning)
            else:
                app.toast.show(f"{setting.title}: {setting.option(option_key).label}.")
        app.run_bg(lambda: apply({setting.key: option_key}, app.privacy_backend, app.privacy_backup, admin), done)

    def make_private(self):
        app = self.app
        admin = is_admin()
        st = app.privacy_statuses or []
        changes = {s.setting.key: s.setting.private for s in st
                   if not s.is_private and (admin or not s.setting.admin)}
        if not changes:
            app.toast.show("Everything you can change here is already private.", "info")
            return
        names = "\n".join(f"• {s.setting.title}" for s in st if s.setting.key in changes)
        if not ask(self, f"Make {len(changes)} setting{'s' if len(changes) != 1 else ''} private?",
                   f"{names}\n\nYour current values are saved, so you can put them back with Restore originals.",
                   ok="Make private", icon="shield"):
            return

        def done(res):
            app.load_privacy()
            if res.failed:
                inform(self, "Some settings weren’t changed", "\n".join(f"{n}: {w}" for n, w in res.failed),
                       icon="warning", icon_color=th.P.warning)
            if res.changed:
                app.toast.show(f"Changed {len(res.changed)} settings. Some take effect after you sign out.")
        app.run_bg(lambda: apply(changes, app.privacy_backend, app.privacy_backup, admin), done)

    def restore(self):
        app = self.app
        if not ask(self, "Restore your original settings?",
                   "Every privacy setting WinPurge changed goes back to what it was before.", ok="Restore",
                   icon="undo"):
            return
        admin = is_admin()
        from .privacy import default_backend
        if app.privacy_backend is None:
            app.privacy_backend = default_backend()

        def done(res):
            app.load_privacy()
            if res.failed:
                inform(self, "Some settings weren’t restored", "\n".join(f"{n}: {w}" for n, w in res.failed),
                       icon="warning", icon_color=th.P.warning)
            else:
                app.toast.show("Your original privacy settings are back.")
        app.run_bg(lambda: restore(app.privacy_backend, app.privacy_backup, admin), done)


# ====================================================================== Settings

class SettingsPage(Page):
    def build(self):
        self.header("Settings", "Choose what WinPurge can do and how it looks.")
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=(px(PAD), px(PAD) - px(12)))
        self.render()

    def on_show(self):
        self.render()

    def section(self, title, desc=None):
        P = th.P
        body = self.scroll.inner
        label(body, title, "heading").pack(anchor="w", pady=(px(20), px(2)))
        if desc:
            label(body, desc, "caption", wrap=px(680)).pack(anchor="w", pady=(0, px(8)))
        card = Card(body, padding=20)
        card.pack(fill="x", padx=(0, px(12)), pady=(px(6) if not desc else 0, 0))
        return card.body

    def render(self):
        app, P = self.app, th.P
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        data = app.settings.data

        b = self.section("Appearance")
        setting_row(b, "Theme", "Follow Windows, or always use light or dark.",
                    lambda p: Dropdown(p, [("system", "Use Windows setting"), ("light", "Light"), ("dark", "Dark")],
                                       data.get("theme", "system"), command=self.set_theme))

        b = self.section("What WinPurge can do", "Each of these only reads. Removing anything always needs your "
                                                 "confirmation.")
        perms = data.setdefault("permissions", {})
        for i, p in enumerate(PERMISSIONS):
            if i:
                divider(b, 8)
            setting_row(b, p.title, p.detail,
                        lambda parent, p=p: Toggle(parent, value=perms.get(p.key, p.default),
                                                   command=lambda v, k=p.key: self.set_permission(k, v)))

        b = self.section("Project folders", "Smart Scan looks for node_modules, build and cache folders only "
                                            "inside these folders, in projects you haven’t edited for a while.")
        roots = data["project_roots"]
        if not app.can("scan_projects"):
            label(b, "Turn on “Look inside project folders you choose” above to use this.", "caption",
                  P.warning).pack(anchor="w", pady=(0, px(10)))
        for r in roots:
            row = tk.Frame(b, bg=P.card)
            row.pack(fill="x", pady=px(2))
            icon_label(row, "folder", 11, P.text2).pack(side="left")
            label(row, r, "body").pack(side="left", padx=(px(10), 0))
            Button(row, icon="delete", kind="subtle", height=28,
                   command=lambda r=r: self.remove_root(r)).pack(side="right")
        if not roots:
            label(b, "No folders yet.", "caption", P.text3).pack(anchor="w")
        bar = tk.Frame(b, bg=P.card)
        bar.pack(fill="x", pady=(px(12), 0))
        Button(bar, "Add folder", icon="add", kind="secondary", command=self.add_root).pack(side="left")
        ages = [(str(d), f"Not edited for {d} days") for d in (14, 30, 60, 90)]
        Dropdown(bar, ages, str(data.get("project_age_days", 30)), command=self.set_age, min_width=200) \
            .pack(side="right")

        b = self.section("Hidden items")
        n = app.ignore.count()
        setting_row(b, f"{n} item{'s' if n != 1 else ''} hidden from scans",
                    "Items you chose “Don’t suggest again” for.",
                    lambda p: self._clear_button(p, n))

        b = self.section("Administrator")
        if is_admin():
            setting_row(b, "Running as administrator", "WinPurge can remove apps installed for everyone and "
                        "change all privacy settings.", lambda p: Badge(p, "Active", "success"))
        else:
            setting_row(b, "Running as a standard user", "Some leftovers in Program Files and a few privacy "
                        "settings need administrator rights.",
                        lambda p: Button(p, "Restart as administrator", icon="admin", kind="secondary",
                                         command=app.restart_as_admin))

        b = self.section("About")
        row = tk.Frame(b, bg=P.card)
        row.pack(fill="x")
        tk.Label(row, image=gfx.logo_img(px(48)), bg=P.card).pack(side="left")
        t = tk.Frame(row, bg=P.card)
        t.pack(side="left", padx=(px(14), 0))
        label(t, "WinPurge", "big").pack(anchor="w")
        label(t, f"Version {__version__}  ·  Works offline. Sends nothing anywhere.", "caption").pack(anchor="w")
        btns = tk.Frame(row, bg=P.card)
        btns.pack(side="right")
        from .app import open_path
        Button(btns, "Data folder", icon="folder", kind="subtle",
               command=lambda: open_path(str(app_data_dir()))).pack(side="left")
        Button(btns, "Log folder", icon="folder", kind="subtle",
               command=lambda: open_path(str(crashlog.log_dir()))).pack(side="left", padx=(px(4), 0))
        tk.Frame(self.scroll.inner, bg=P.window, height=px(28)).pack()

    def _clear_button(self, parent, n):
        b = Button(parent, "Show them again", kind="secondary", command=self.clear_hidden)
        b.set_disabled(n == 0)
        return b

    def set_theme(self, mode):
        self.app.settings.data["theme"] = mode
        self.app.settings.save()
        self.app.after(10, self.app.rebuild)

    def set_permission(self, key, value):
        app = self.app
        app.settings.data.setdefault("permissions", {})[key] = value
        app.settings.save()
        if key == "read_apps":
            app.load_apps()
        if key == "privacy":
            app.load_privacy()
        app.notify("permissions")
        self.app.after(10, self.render)

    def add_root(self):
        d = filedialog.askdirectory(parent=self, title="Choose a folder that holds your projects")
        if d:
            d = os.path.normpath(d)
            roots = self.app.settings.data["project_roots"]
            if d not in roots:
                roots.append(d)
                self.app.settings.save()
            self.render()

    def remove_root(self, r):
        self.app.settings.data["project_roots"].remove(r)
        self.app.settings.save()
        self.render()

    def set_age(self, value):
        self.app.settings.data["project_age_days"] = int(value)
        self.app.settings.save()

    def clear_hidden(self):
        self.app.ignore.clear()
        self.app.toast.show("Hidden items will show up in your next scan.", "info")
        self.render()
