"""Settings: General, Cleaning, Uninstalling, permissions, history, About and
Uninstall WinPurge."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog

from . import __version__, crashlog, gfx, shell
from . import history as hist
from . import theme as th
from .caches import STALE_CHOICES
from .common import folder_size, human_size
from .pages import PAD, Page, divider, setting_row, when
from .permissions import PERMISSIONS
from .theme import px
from .trash import app_data_dir, is_admin
from .widgets import Badge, Button, Dialog, Dropdown, ScrollFrame, Toggle, ask, icon_label, inform, label

STALE_LABELS = {30: "1 month", 90: "3 months", 180: "6 months", 365: "1 year", 730: "2 years", 0: "Show all"}
FREQ = [("7", "Every week"), ("14", "Every 2 weeks"), ("30", "Every month"), ("91", "Every 3 months"),
        ("182", "Every 6 months")]


class SettingsPage(Page):
    def build(self):
        self.header("Settings", "How WinPurge looks, what it may do, and how it cleans.")
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=(px(PAD), px(PAD) - px(12)))
        self.excluded_sizes: dict[str, int] = {}

    def on_show(self):
        self.render()
        self.measure_excluded()

    def on_event(self, event):
        if event == "cleaned" and self.winfo_ismapped():
            self.render()

    def section(self, title, desc=None):
        from .widgets import Card
        body = self.scroll.inner
        label(body, title, "heading").pack(anchor="w", pady=(px(20), px(2)))
        if desc:
            label(body, desc, "caption", wrap=px(700)).pack(anchor="w", pady=(0, px(8)))
        card = Card(body, padding=20)
        card.pack(fill="x", padx=(0, px(12)), pady=(px(6) if not desc else 0, 0))
        return card.body

    def render(self):
        app, P = self.app, th.P
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        data = app.settings.data

        # ---------------------------------------------------------------- General
        b = self.section("General")
        setting_row(b, "Appearance", "Follow Windows, or always use light or dark.",
                    lambda p: Dropdown(p, [("system", "Use Windows setting"), ("light", "Light"), ("dark", "Dark")],
                                       data.get("theme", "system"), command=self.set_theme))
        divider(b, 8)
        setting_row(b, "Scan everything when WinPurge opens",
                    "Categories are scanned one at a time. Nothing is removed until you choose.",
                    lambda p: Toggle(p, value=data.get("scan_on_open", True),
                                     command=lambda v: self.save("scan_on_open", v)))

        # ---------------------------------------------------------------- Cleaning
        b = self.section("Cleaning")
        sched = hist.schedule(data)
        due = hist.next_due(data)
        setting_row(b, "Clean automatically",
                    "When a clean is due, WinPurge moves the Safe items in App Caches and Dev Tools to the Recycle "
                    "Bin the next time it opens. It never cleans in the background, and never touches Large Files "
                    "or Check First items." + (f" Next clean: {time.strftime('%d %B %Y', time.localtime(due))}."
                                               if due else ""),
                    lambda p: Toggle(p, value=sched.get("enabled", False), command=self.set_auto))
        if sched.get("enabled"):
            divider(b, 8)
            setting_row(b, "How often", None,
                        lambda p: Dropdown(p, FREQ, str(sched.get("every_days", 7)), command=self.set_freq))
        divider(b, 8)
        setting_row(b, "Projects count as stale after",
                    "Dev Tools lists build and dependency folders only in projects unchanged for this long, "
                    "counting git activity. Projects in use never appear.",
                    lambda p: Dropdown(p, [(str(d), STALE_LABELS[d]) for d in STALE_CHOICES],
                                       str(data.get("stale_days", 30)), command=self.set_stale))
        divider(b, 8)
        label(b, "Other folders to scan", "strong").pack(anchor="w")
        label(b, "Large Files and Dev Tools look here as well as in your user folders.", "caption").pack(anchor="w")
        for r in data["project_roots"]:
            self.path_row(b, r, lambda r=r: self.remove_root(r))
        Button(b, "Add folder", icon="add", kind="secondary", command=self.add_root).pack(anchor="w", pady=(px(10), 0))
        divider(b, 10)
        label(b, "Excluded folders", "strong").pack(anchor="w")
        label(b, "Folders you told WinPurge to leave alone with “Don’t suggest again”.",
              "caption").pack(anchor="w")
        excluded = app.ignore.active()
        for p in excluded:
            size = self.excluded_sizes.get(p)
            self.path_row(b, p, lambda p=p: self.unexclude(p), human_size(size) if size is not None else "")
        if not excluded:
            label(b, "None.", "caption", P.text3).pack(anchor="w", pady=(px(6), 0))

        # ---------------------------------------------------------------- Uninstalling
        b = self.section("Uninstalling")
        setting_row(b, "Uninstall from the right-click menu",
                    "Right-click a program or shortcut and choose “Uninstall with WinPurge”. On Windows 11 "
                    "it's under “Show more options”. You can also drop a program onto WinPurge.",
                    lambda p: Toggle(p, value=shell.context_menu_enabled(), command=self.set_menu))
        divider(b, 8)
        setting_row(b, "Review leftovers when an app is uninstalled",
                    "A small background watcher notices when any app is uninstalled, even with WinPurge closed, and "
                    "opens a review of just that app's leftovers. Nothing moves without that review. It also "
                    "reminds you when a scheduled clean is due.",
                    lambda p: Toggle(p, value=shell.watcher_enabled(), command=self.set_watch))
        divider(b, 8)
        if is_admin():
            setting_row(b, "Running as administrator", "Apps installed for everyone, their leftovers and every "
                        "privacy setting can be changed.", lambda p: Badge(p, "Active", "success"))
        else:
            setting_row(b, "Running as a standard user", "Apps installed for everyone, their leftovers in Program "
                        "Files and system junk need administrator rights.",
                        lambda p: Button(p, "Restart as administrator", icon="admin", kind="secondary",
                                         command=app.restart_as_admin))

        # ---------------------------------------------------------------- Permissions
        b = self.section("What WinPurge can do", "Each of these only reads. Removing anything always needs your "
                                                 "confirmation.")
        perms = data.setdefault("permissions", {})
        for i, p in enumerate(PERMISSIONS):
            if i:
                divider(b, 8)
            setting_row(b, p.title, p.detail,
                        lambda parent, p=p: Toggle(parent, value=perms.get(p.key, p.default),
                                                   command=lambda v, k=p.key: self.set_permission(k, v)))

        # ---------------------------------------------------------------- History
        b = self.section("Cleaning history")
        entries = app.history.entries
        total = app.history.total_freed()
        label(b, f"{human_size(total)} cleaned with WinPurge so far" if total else "No cleans yet.", "strong").pack(anchor="w")
        for e in entries[:12]:
            row = tk.Frame(b, bg=P.card)
            row.pack(fill="x", pady=(px(8), 0))
            kind = "Scheduled" if e["kind"] == "scheduled" else "Manual"
            label(row, time.strftime("%d %b %Y, %H:%M", time.localtime(e["time"])), "body").pack(side="left")
            label(row, f"   {kind}  ·  {human_size(e['freed'])}  ·  {e['items']} items", "caption").pack(side="left")
            Button(row, "Details", kind="subtle", height=26, command=lambda e=e: self.history_details(e)).pack(side="right")

        # ---------------------------------------------------------------- About
        b = self.section("About")
        row = tk.Frame(b, bg=P.card)
        row.pack(fill="x")
        tk.Label(row, image=gfx.logo_img(px(48)), bg=P.card).pack(side="left")
        t = tk.Frame(row, bg=P.card)
        t.pack(side="left", padx=(px(14), 0))
        label(t, "WinPurge", "big").pack(anchor="w")
        label(t, f"Version {__version__}  ·  Works offline. Sends nothing anywhere.", "caption").pack(anchor="w")
        label(t, "Shortcuts: Ctrl+1–7 sections  ·  Ctrl+R scan  ·  Ctrl+Shift+R scan everything  "
                 "·  Ctrl+F search  ·  Alt+1–3 filters  ·  Ctrl+, settings", "caption",
              P.text3).pack(anchor="w", pady=(px(4), 0))
        btns = tk.Frame(row, bg=P.card)
        btns.pack(side="right")
        from .app import open_path
        Button(btns, "Data folder", icon="folder", kind="subtle", command=lambda: open_path(str(app_data_dir()))).pack(side="left")
        Button(btns, "Log folder", icon="folder", kind="subtle",
               command=lambda: open_path(str(crashlog.log_dir()))).pack(side="left", padx=(px(4), 0))

        # ---------------------------------------------------------------- Uninstall WinPurge
        b = self.section("Uninstall WinPurge")
        setting_row(b, "Uninstall WinPurge",
                    "Turns off everything WinPurge runs in the background, checks it stopped, then removes WinPurge. "
                    "Your settings and history stay unless you choose to remove them.",
                    lambda p: Button(p, "Uninstall…", kind="danger", command=self.uninstall_self))
        tk.Frame(self.scroll.inner, bg=P.window, height=px(28)).pack()

    # ------------------------------------------------------------ helpers

    def path_row(self, parent, path, on_remove, right_text=""):
        P = th.P
        row = tk.Frame(parent, bg=P.card)
        row.pack(fill="x", pady=(px(6), 0))
        icon_label(row, "folder", 11, P.text2).pack(side="left")
        label(row, path, "body").pack(side="left", padx=(px(10), 0))
        Button(row, icon="delete", kind="subtle", height=28, command=on_remove).pack(side="right")
        if right_text:
            label(row, right_text, "caption").pack(side="right", padx=(0, px(10)))

    def save(self, key, value):
        self.app.settings.data[key] = value
        self.app.settings.save()

    def set_theme(self, mode):
        self.save("theme", mode)
        self.app.after(10, self.app.rebuild)

    def set_auto(self, on):
        s = hist.schedule(self.app.settings.data)
        s["enabled"] = on
        if on:
            s["last"] = time.time()   # first clean one interval from now
        self.app.settings.save()
        self.after(10, self.render)

    def set_freq(self, days):
        hist.schedule(self.app.settings.data)["every_days"] = int(days)
        self.app.settings.save()
        self.after(10, self.render)

    def set_stale(self, days):
        self.save("stale_days", int(days))
        self.app.toast.show("Scan Dev Tools again to apply the new age.", "info",
                            action=("Scan now", lambda: self.app.scan_tab("dev")))

    def set_permission(self, key, value):
        app = self.app
        app.settings.data.setdefault("permissions", {})[key] = value
        app.settings.save()
        if key == "read_apps":
            app.load_apps()
        if key == "privacy":
            app.load_privacy()
        app.notify("permissions")
        self.after(10, self.render)

    def set_menu(self, on):
        try:
            shell.set_context_menu(on)
        except OSError as e:
            inform(self, "Couldn’t change the right-click menu", str(e), icon="warning")
        self.after(10, self.render)

    def set_watch(self, on):
        try:
            shell.set_watcher(on)
        except OSError as e:
            inform(self, "Couldn’t change the watcher", str(e), icon="warning")
        self.after(10, self.render)

    def add_root(self):
        d = filedialog.askdirectory(parent=self, title="Choose a folder or drive to scan")
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

    def unexclude(self, p):
        self.app.ignore.remove(p)
        self.app.toast.show("It will show up again in your next scan.", "info")
        self.render()

    def measure_excluded(self):
        paths = [p for p in self.app.ignore.active() if p not in self.excluded_sizes]
        if not paths:
            return

        def work():
            return {p: folder_size(p, limit_seconds=2) if os.path.exists(p) else 0 for p in paths}

        def done(sizes):
            self.excluded_sizes.update(sizes)
            if self.winfo_ismapped():
                self.render()
        self.app.run_bg(work, done)

    def history_details(self, e):
        P = th.P

        def build(frame):
            text = tk.Text(frame, height=16, width=80, bd=0, highlightthickness=0, bg=P.card, fg=P.text,
                           font=th.caption_font(), wrap="none")
            sections = [("Moved to the Recycle Bin", e.get("moved", [])),
                        ("Removed permanently", e.get("permanent", [])),
                        ("Skipped", [f"{p} — {w}" for p, w in e.get("skipped", [])])]
            for title, rows in sections:
                if rows:
                    text.insert("end", f"{title} ({len(rows)})\n", ("h",))
                    text.insert("end", "\n".join(rows) + "\n\n")
            text.tag_configure("h", font=th.body_strong())
            text.configure(state="disabled")
            text.pack(fill="both", expand=True)
        when_ = time.strftime("%d %B %Y, %H:%M", time.localtime(e["time"]))
        Dialog(self, f"Clean on {when_}", f"{'Scheduled' if e['kind'] == 'scheduled' else 'Manual'} clean. "
               f"Freed {human_size(e['freed'])} from {e['items']} items.", (("Close", True, "primary"),),
               icon="history", width=620, build=build).show()

    def uninstall_self(self):
        parts = [n for n, on in (("The uninstall watcher", shell.watcher_enabled()),
                                 ("The right-click menu item", shell.context_menu_enabled())) if on]
        listing = ("WinPurge turns these off first:\n" + "\n".join(f"• {p}" for p in parts)) if parts else \
            "Nothing of WinPurge's is running in the background."
        if not ask(self, "Uninstall WinPurge?", listing + "\n\nThen Windows removes WinPurge. Privacy settings "
                   "you changed stay changed; use Restore originals on the Privacy page first if you want them back.",
                   ok="Uninstall", danger=True, icon="delete"):
            return
        shell.remove_integrations()
        left = [n for n, on in (("the watcher", shell.watcher_enabled() or not shell.stop_watcher()),
                                ("the right-click menu item", shell.context_menu_enabled())) if on]
        if left:
            inform(self, "Something is still running", f"Couldn’t turn off {', '.join(left)}. Restart Windows "
                   "and try again.", icon="warning", icon_color=th.P.warning)
            return
        cmd = shell.own_uninstaller()
        if cmd:
            subprocess.Popen(cmd, shell=True)
            self.app.destroy()
        else:
            inform(self, "Background parts are off",
                   "WinPurge is running from its source folder, not an installed copy. Delete that folder to "
                   "remove it.", icon="check")
