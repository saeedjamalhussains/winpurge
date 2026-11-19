"""Uninstaller: installed apps (one or several at once), leftovers from apps
that are already gone, and command-line tools."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from . import theme as th
from .apps import list_installed_apps, run_uninstaller
from .common import CHECK, Item, human_size, is_protected
from .leftovers import find_dot_folders, find_leftovers, find_registry_leftovers
from .pages import PAD, Page, empty_state
from .theme import px
from .widgets import Button, Card, CheckTable, Dialog, SearchBox, Segmented, ask, inform, label


class UninstallerPage(Page):
    COLS = (("name", "Name", 300), ("publisher", "Publisher", 200), ("version", "Version", 110), ("size", "Size", 90))

    def build(self):
        P = th.P
        self.view = "apps"
        self.sort_key, self.sort_rev = "name", False
        actions = self.header("Uninstaller", "Remove apps completely, with the files and settings they leave behind.")
        self.refresh_btn = Button(actions, icon="refresh", kind="subtle", command=self.rescan)
        self.refresh_btn.pack(side="right")
        self.search = SearchBox(actions, "Search apps", command=lambda q: self.fill())
        self.search.pack(side="right", padx=(0, px(8)))

        bar = tk.Frame(self, bg=P.window)
        bar.pack(fill="x", padx=px(PAD), pady=(0, px(10)))
        self.seg = Segmented(bar, [("apps", "Installed apps"), ("leftovers", "Leftovers"),
                                   ("cli", "Command-line tools")], self.view, command=self.set_view)
        self.seg.pack(side="left")

        self.stack = tk.Frame(self, bg=P.window)
        self.stack.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(22)))

        # Installed apps
        self.apps_view = tk.Frame(self.stack, bg=P.window)
        foot = Card(self.apps_view, padding=14)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        card = Card(self.apps_view, padding=6, stretch=True)
        card.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(card.body, style="WP.Treeview", columns=[c[0] for c in self.COLS],
                                 show="headings", selectmode="extended")
        for key, text, width in self.COLS:
            self.tree.heading(key, text=text, anchor="e" if key == "size" else "w", command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=px(width), anchor="e" if key == "size" else "w",
                             stretch=key in ("name", "publisher"))
        sb = ttk.Scrollbar(card.body, orient="vertical", command=self.tree.yview, style="WP.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_footer())
        self.tree.bind("<Double-1>", lambda e: self.uninstall())
        self.tree.bind("<Delete>", lambda e: self.uninstall())
        self.overlay = label(card.body, "", "body", P.text2)
        fb = foot.body
        self.uninstall_btn = Button(fb, "Uninstall…", icon="delete", kind="danger", min_width=150,
                                    command=self.uninstall)
        self.uninstall_btn.pack(side="right")
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.sel_caption = label(info, "", "caption")
        self.sel_caption.pack(anchor="w")

        # Leftovers and command-line tools share one layout
        self.list_view = tk.Frame(self.stack, bg=P.window)
        lfoot = Card(self.list_view, padding=14)
        lfoot.pack(side="bottom", fill="x", pady=(px(10), 0))
        self.list_empty = empty_state(self.list_view, "apps")
        self.list_card = Card(self.list_view, padding=6, stretch=True)
        self.list_table = CheckTable(self.list_card.body, on_change=self.update_list_footer,
                                     on_select=self.list_detail, confirm_check=lambda i: True)
        self.list_table.pack(fill="both", expand=True)
        lb = lfoot.body
        self.list_btn = Button(lb, "Move to Recycle Bin", icon="delete", kind="primary", min_width=190,
                               command=self.list_action)
        self.list_btn.pack(side="right")
        info = tk.Frame(lb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.list_title = label(info, "", "strong")
        self.list_title.pack(anchor="w")
        self.list_caption = label(info, "", "caption", wrap=px(620))
        self.list_caption.pack(anchor="w")
        self.set_view("apps")

    # ------------------------------------------------------------ hooks

    def on_show(self):
        self.refresh_all()

    def on_event(self, event):
        if event in ("apps", "permissions", "scan", "cleaned"):
            self.refresh_all()

    def rescan(self):
        if self.view == "apps":
            self.app.load_apps()
        else:
            self.app.scan_tab(self.view)

    def focus_search(self):
        if self.view == "apps":
            self.search.entry.focus_set()

    def set_filter(self, n):
        self.set_view(("apps", "leftovers", "cli")[n - 1])
        self.seg.set(self.view)

    def set_view(self, view):
        self.view = view
        self.apps_view.pack_forget()
        self.list_view.pack_forget()
        if view == "apps":
            self.search.pack(side="right", padx=(0, px(8)), before=self.refresh_btn) if not self.search.winfo_ismapped() else None
            self.apps_view.pack(fill="both", expand=True)
        else:
            self.search.pack_forget()
            self.list_view.pack(fill="both", expand=True)
        self.refresh_all(force=True)

    def refresh_all(self, force=False):
        app = self.app
        for key, name in (("leftovers", "Leftovers"), ("cli", "Command-line tools")):
            n = len(app.results.get(key) or [])
            self.seg.set_text(key, f"{name} ({n})" if n else name)
        n = len(app.installed)
        self.seg.set_text("apps", f"Installed apps ({n})" if n else "Installed apps")
        if self.view == "apps":
            self.fill()
        else:
            self.fill_list(force)

    # ------------------------------------------------------------ installed apps

    def sort_by(self, key):
        self.sort_rev = not self.sort_rev if self.sort_key == key else key == "size"
        self.sort_key = key
        self.fill()

    def fill(self):
        app = self.app
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        msg = {"loading": "Reading installed apps…", "off": "Reading installed apps is turned off. "
               "Turn it on in Settings."}.get(app.apps_state, "")
        q = self.search.get().lower().strip()
        rows = [(i, a) for i, a in enumerate(app.installed) if not q or q in a.name.lower() or q in a.publisher.lower()]
        keyf = {"name": lambda r: r[1].name.lower(), "publisher": lambda r: r[1].publisher.lower(),
                "version": lambda r: r[1].version, "size": lambda r: r[1].size_kb}[self.sort_key]
        rows.sort(key=keyf, reverse=self.sort_rev)
        for i, a in rows:
            self.tree.insert("", "end", iid=str(i), values=(a.name, a.publisher or "—", a.version or "",
                                                            human_size(a.size_kb * 1024) if a.size_kb else ""))
        keep = [s for s in selected if self.tree.exists(s)]
        if keep:
            self.tree.selection_set(keep)
        if app.apps_state == "ready" and not rows:
            msg = f"No apps match “{q}”." if q else "No apps found."
        if msg:
            self.overlay.configure(text=msg)
            self.overlay.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.overlay.place_forget()
        self.update_footer()

    def selected_apps(self):
        return [self.app.installed[int(s)] for s in self.tree.selection() if int(s) < len(self.app.installed)]

    def update_footer(self):
        apps = self.selected_apps()
        if len(apps) == 1:
            a = apps[0]
            self.sel_title.configure(text=a.name)
            parts = [p for p in (a.publisher, f"Version {a.version}" if a.version else "",
                                 human_size(a.size_kb * 1024) if a.size_kb else "") if p]
            self.sel_caption.configure(text="  ·  ".join(parts))
            self.uninstall_btn.set_text("Uninstall…")
        elif apps:
            self.sel_title.configure(text=f"{len(apps)} apps selected")
            self.sel_caption.configure(text=f"About {human_size(sum(a.size_kb for a in apps) * 1024)} plus what "
                                            "they leave behind. Each app's own uninstaller runs in turn.")
            self.uninstall_btn.set_text(f"Uninstall {len(apps)} apps…")
        else:
            n = len(self.app.installed)
            self.sel_title.configure(text="Select apps to uninstall" if n else "Apps")
            self.sel_caption.configure(text="Ctrl-click or Shift-click to select several." if n else "")
            self.uninstall_btn.set_text("Uninstall…")
        self.uninstall_btn.set_disabled(not apps)

    def uninstall(self, apps=None):
        from .system import close_gracefully, processes_inside
        apps = apps or self.selected_apps()
        if not apps:
            return
        names = "\n".join(f"• {a.name}" for a in apps)
        steam = [a for a in apps if a.uninstall_string.lower().startswith(("steam://", '"steam://'))
                 or "steam.exe" in a.uninstall_string.lower()]
        note = ("\n\nSteam asks first, then deletes a game's files permanently, not to the Recycle Bin. "
                "Only saves synced to Steam Cloud are kept." if steam else "")
        title = f"Uninstall {apps[0].name}?" if len(apps) == 1 else f"Uninstall {len(apps)} apps?"
        msg = ("Each app's own uninstaller opens in turn. When they finish, WinPurge shows what they left behind "
               "before anything is removed." + ("" if len(apps) == 1 else f"\n\n{names}") + note)
        if not ask(self, title, msg, ok="Uninstall", danger=True, icon="delete"):
            return
        # Running apps are asked to quit first, gracefully. One that won't stays installed.
        folders = {a.key_name: [f for f in (a.install_location, os.path.dirname(a.display_icon)
                                            if a.display_icon else "") if f and not is_protected(f)] for a in apps}
        running = {a.key_name: processes_inside(folders[a.key_name]) for a in apps}
        busy = [a for a in apps if running[a.key_name]]
        if busy:
            who = ", ".join(a.name for a in busy)
            if not ask(self, f"Close {who} first?", "WinPurge asks it to close the way clicking X does, never by "
                       "force. If it doesn't close, it stays installed and the other apps still go ahead.",
                       ok="Close and continue", icon="warning"):
                return
        look_files, look_reg = self.app.can("scan_leftovers"), self.app.can("registry_cleanup")
        ignore = self.app.ignore

        def work():
            from .watcher import mark_handled
            kept = []
            for a in busy:
                pids = [p for ps in running[a.key_name].values() for p in ps]
                if close_gracefully(pids):
                    kept.append(a)
            to_run = [a for a in apps if a not in kept]
            for a in to_run:
                mark_handled(a)
                run_uninstaller(a)
            remaining = list_installed_apps()
            still = {(r.key_name, r.norm) for r in remaining}
            gone = [a for a in to_run if (a.key_name, a.norm) not in still]
            leftovers = []
            for a in gone:
                found = (find_leftovers(a, remaining) if look_files else []) + find_dot_folders(a) + \
                    (find_registry_leftovers(a, remaining) if look_reg else [])
                for it in found:
                    it.category = a.name
                    it.checked = it.level != CHECK
                leftovers += [i for i in found if not ignore.contains(i.path)]
            return kept, [a for a in to_run if a not in gone], gone, remaining, leftovers

        self.uninstall_btn.set_text("Uninstalling…")
        self.uninstall_btn.set_disabled(True)
        self.app.toast.show("Finish each uninstaller window to continue.", "info", seconds=8)

        def done(result):
            kept, failed, gone, remaining, leftovers = result
            self.app.installed = remaining
            self.app.notify("apps")
            problems = [f"• {a.name}: still running, so it was left installed." for a in kept] + \
                       [f"• {a.name}: still installed. Its uninstaller may have been cancelled or needs a restart."
                        for a in failed]
            if problems:
                inform(self, "Some apps weren’t removed", "\n".join(problems), icon="info")
            if gone and not leftovers:
                self.app.toast.show(f"{', '.join(a.name for a in gone)} removed. Nothing was left behind.")
            elif leftovers:
                review_leftovers(self, self.app, gone, leftovers)

        self.app.run_bg(work, done, lambda e: self.update_footer())

    def uninstall_from_path(self, path: str):
        """From the right-click menu or a program dropped onto WinPurge."""
        from .shell import match_app
        if self.app.apps_state != "ready":
            if self.app.apps_state == "off":
                inform(self, "Reading installed apps is turned off", "Turn it on in Settings to uninstall apps.")
                return
            self.after(300, lambda: self.uninstall_from_path(path))
            return
        app = match_app(path, self.app.installed)
        if app:
            idx = str(self.app.installed.index(app))
            self.set_view("apps")
            self.seg.set("apps")
            if self.tree.exists(idx):
                self.tree.selection_set(idx)
                self.tree.see(idx)
            self.uninstall([app])
            return
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        name = os.path.splitext(os.path.basename(path))[0]
        if not folder or is_protected(folder) or folder.rstrip("\\/").lower().endswith(("program files", "program files (x86)")):
            inform(self, f"{name} isn’t in Windows’ list of installed apps",
                   "Uninstall it from the app that installed it, or from Settings → Apps.")
            return
        if ask(self, f"{name} isn’t an installed app",
               f"It looks like a portable app that runs from its own folder:\n{folder}\n\nMove that whole folder "
               "to the Recycle Bin?", ok="Move to Recycle Bin", icon="delete"):
            self.app.clean_items([Item(path=folder, label=name, category="Apps", level=CHECK, checked=True)], self)

    # ------------------------------------------------------------ leftovers and CLI tools

    def fill_list(self, force=False):
        app, view = self.app, self.view
        items = app.results.get(view)
        state = app.tab_state[view]
        if view == "leftovers":
            self.list_btn.set_text("Move to Recycle Bin")
            self.list_btn.kind = "primary"
            self.list_caption.configure(text="Data left by apps that are already gone. Nothing is selected for you: "
                                             "it's app data, not a cache, so it won't come back.")
        else:
            self.list_btn.set_text("Uninstall selected")
            self.list_btn.kind = "danger"
            self.list_caption.configure(text="Removed by npm, pipx, uv, Cargo or dotnet's own uninstall. That "
                                             "deletes them permanently, not to the Recycle Bin.")
        self.list_btn._draw()
        if items:
            self.list_empty.pack_forget()
            self.list_card.pack(fill="both", expand=True)
            if force or getattr(self, "_list_shown", None) != (view, id(items)):
                self._list_shown = (view, id(items))
                for i in items:
                    i.checked = False      # nothing is selected for you here
                self.list_table.set_items(items, human_size)
            return
        self.list_card.pack_forget()
        self.list_empty.pack(fill="both", expand=True)
        e = self.list_empty
        e.bar.pack_forget()
        e.button.pack_forget()
        e.bar.stop()
        nice = "leftovers" if view == "leftovers" else "command-line tools"
        if state == "scanning":
            e.title.configure(text=f"Looking for {nice}…")
            e.text.configure(text="")
            e.bar.pack(pady=(px(18), 0))
            e.bar.start()
        elif not app.tab_allowed(view):
            e.title.configure(text=f"Looking for {nice} is turned off")
            e.text.configure(text="Turn it on under “What WinPurge can do” in Settings.")
            e.button.set_text("Open Settings")
            e.button.command = lambda: app.show("settings")
            e.button.pack(pady=(px(18), 0))
        else:
            e.title.configure(text=f"No {nice} found" if state == "done" else f"{nice.capitalize()} not scanned yet")
            e.text.configure(text="Leftovers are folders in AppData and ProgramData that no installed app claims."
                             if view == "leftovers" else "Tools installed globally with npm, pipx, uv, Cargo or dotnet.")
            e.button.set_text("Scan again" if state == "done" else "Scan now")
            e.button.command = self.rescan
            e.button.pack(pady=(px(18), 0))

    def update_list_footer(self):
        ticked = self.list_table.checked()
        self.list_title.configure(text=f"{len(ticked)} selected" + (f"  ·  {human_size(sum(i.size for i in ticked))}"
                                                                    if any(i.size for i in ticked) else "")
                                  if ticked else "Nothing selected")
        self.list_btn.set_disabled(not ticked)

    def list_detail(self, item):
        pass

    def list_action(self):
        items = self.list_table.checked()
        if not items:
            return
        if self.view == "leftovers":
            if ask(self, f"Move {len(items)} leftover folder{'s' if len(items) != 1 else ''} to the Recycle Bin?",
                   f"About {human_size(sum(i.size for i in items))}. You can put them back until you empty the "
                   "Recycle Bin.", ok="Move to Recycle Bin", icon="delete"):
                self.app.clean_items(items, self)
            return
        by_mgr: dict[str, list[str]] = {}
        for i in items:
            by_mgr.setdefault(i.category, []).append(i.label)
        lines = "\n".join(f"{m}: {', '.join(n)}" for m, n in by_mgr.items())
        if not ask(self, f"Uninstall {len(items)} command-line tool{'s' if len(items) != 1 else ''}?",
                   f"{lines}\n\nEach is removed by its own package manager, which deletes it permanently. It doesn't "
                   "go to the Recycle Bin.", ok="Uninstall", danger=True, icon="delete"):
            return
        from .clitools import uninstall_tools

        def done(result):
            removed, failed = result
            self.app.history.add("manual", 0, [], permanent=removed, skipped=failed)
            if removed:
                self.app.toast.show(f"Uninstalled {', '.join(removed)}.")
            if failed:
                inform(self, "Some tools weren’t removed", "\n".join(f"• {n}: {w}" for n, w in failed),
                       icon="warning", icon_color=th.P.warning)
            self.app.scan_tab("cli")
        self.list_btn.set_disabled(True)
        self.app.run_bg(lambda: uninstall_tools(items), done)


def review_leftovers(parent, app, gone, items):
    """One review for everything the uninstalled apps left behind."""

    def build(frame):
        box = Card(frame, padding=4, stretch=True)
        box.configure(width=px(640), height=px(320))
        box.pack(fill="both", expand=True)
        table = CheckTable(box.body, confirm_check=lambda it: ask(frame, "Check first", (it.note or
                           "This may hold data you want to keep.") + "\n\nSelect it anyway?", ok="Select it"))
        table.pack(fill="both", expand=True)
        table.set_items(items, human_size)
    names = gone[0].name if len(gone) == 1 else f"{len(gone)} apps"
    ok = Dialog(parent, f"{names} left files behind",
                "Ticked items move to the Recycle Bin, so you can put them back until you empty it. Settings folders "
                "and registry settings start unticked.",
                (("Keep all", False, "secondary"), ("Move to Recycle Bin", True, "primary")),
                icon="clean", width=640, build=build).show()
    chosen = [i for i in items if i.checked]
    if ok and chosen:
        app.clean_items(chosen, parent)
