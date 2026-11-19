"""WinPurge window: an Apps tab for uninstalling, and a Clean Up tab for caches,
old project folders and data left by apps that are gone."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .apps import App, list_installed_apps, run_uninstaller
from .caches import scan_caches, scan_projects
from .common import CHECK, IS_WINDOWS, SAFE, Item, human_size
from .leftovers import find_leftovers, find_orphans, find_registry_leftovers
from . import crashlog
from .permissions import allowed, needs_setup
from .privacy_tab import PrivacyTab
from .setup_wizard import SetupWizard
from .trash import IgnoreList, Result, app_data_dir, is_admin, recycle, relaunch_as_admin

BOX_ON, BOX_OFF = "☑", "☐"


class Settings:
    def __init__(self):
        self.path = app_data_dir() / "settings.json"
        try:
            self.data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("project_roots", [])
        self.data.setdefault("project_age_days", 30)

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=1), "utf-8")


def open_in_explorer(path: str):
    if IS_WINDOWS and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


class CheckList(ttk.Frame):
    """A tree of Items with a tick box per row, grouped by category."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        cols = ("level", "size")
        self.tree = ttk.Treeview(self, columns=cols, selectmode="browse")
        self.tree.heading("#0", text="Item")
        self.tree.heading("level", text="Rating")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=520)
        self.tree.column("level", width=100, anchor="center")
        self.tree.column("size", width=90, anchor="e")
        self.tree.tag_configure("check", foreground="#9a5b00")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.items: dict[str, Item] = {}
        self.on_change = on_change
        self.tree.bind("<Button-1>", self._click)
        self.tree.bind("<space>", lambda e: self._toggle(self.tree.focus()))

    def set_items(self, items: list[Item]):
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        groups: dict[str, str] = {}
        for it in items:
            if it.category not in groups:
                groups[it.category] = self.tree.insert("", "end", text=it.category, open=True)
            iid = self.tree.insert(groups[it.category], "end", text=self._text(it),
                                   values=(it.level, human_size(it.size)),
                                   tags=("check",) if it.level == CHECK else ())
            self.items[iid] = it
        self._refresh_groups()

    def _text(self, it: Item) -> str:
        return f"{BOX_ON if it.checked else BOX_OFF}  {it.label}"

    def _refresh_groups(self):
        for g in self.tree.get_children():
            kids = [self.items[k] for k in self.tree.get_children(g)]
            total = sum(k.size for k in kids)
            name = kids[0].category if kids else ""
            self.tree.item(g, text=f"{name}  ({len(kids)})", values=("", human_size(total)))
        if self.on_change:
            self.on_change()

    def _click(self, event):
        if self.tree.identify_region(event.x, event.y) != "tree":
            return
        iid = self.tree.identify_row(event.y)
        # Toggle when the click lands on the tick box at the start of the label.
        bbox = self.tree.bbox(iid, "#0")
        if iid in self.items and bbox and event.x < bbox[0] + 60:
            self._toggle(iid)

    def _toggle(self, iid):
        it = self.items.get(iid)
        if not it:
            return
        if not it.checked and it.level == CHECK:
            if not messagebox.askyesno("Check first",
                                       f"{it.label}\n\n{it.note or 'This may hold data you want.'}\n\nTick it anyway?"):
                return
        it.checked = not it.checked
        self.tree.item(iid, text=self._text(it))
        self._refresh_groups()

    def selected(self) -> Item | None:
        return self.items.get(self.tree.focus())

    def checked(self) -> list[Item]:
        return [i for i in self.items.values() if i.checked]

    def tick_safe(self):
        for iid, it in self.items.items():
            it.checked = it.level == SAFE
            self.tree.item(iid, text=self._text(it))
        self._refresh_groups()

    def remove(self, paths: set[str]):
        for iid, it in list(self.items.items()):
            if it.path in paths and not it.extra.get("contents_only"):
                self.tree.delete(iid)
                del self.items[iid]
        for g in self.tree.get_children():
            if not self.tree.get_children(g):
                self.tree.delete(g)
        self._refresh_groups()


class WinPurgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"WinPurge {__version__}" + ("  (Administrator)" if is_admin() else ""))
        self.geometry("900x620")
        self.minsize(720, 480)
        self.settings = Settings()
        self.ignore = IgnoreList()
        self.jobs: queue.Queue = queue.Queue()
        self.installed: list[App] = []

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        nb.add(self._build_apps_tab(nb), text="  Apps  ")
        nb.add(self._build_clean_tab(nb), text="  Clean Up  ")
        self.privacy_tab = PrivacyTab(nb, self)
        nb.add(self.privacy_tab, text="  Privacy  ")

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="left")
        if IS_WINDOWS and not is_admin():
            ttk.Button(bar, text="Restart as administrator", command=self._elevate).pack(side="right")
        ttk.Button(bar, text="Settings\u2026", command=lambda: self.open_setup(first_run=False)).pack(side="right", padx=6)

        self.after(100, self._poll)
        if needs_setup(self.settings.data):
            self.after(50, lambda: self.open_setup(first_run=True))
        else:
            self.load_apps()
            self.privacy_tab.refresh()

    # ------------------------------------------------------------ setup

    def can(self, key: str) -> bool:
        return allowed(self.settings.data, key)

    def open_setup(self, first_run: bool):

        def done(_):
            self.settings.save()
            self.clean_list.set_items([])
            self.load_apps()
            self.privacy_tab.refresh()

        def cancel():
            if needs_setup(self.settings.data):
                # Setup was never finished: nothing is allowed, so close.
                self.destroy()

        SetupWizard(self, self.settings.data, done, cancel)

    # ------------------------------------------------------------ threading

    def run_bg(self, work, done, busy_text):
        """Run `work()` off the UI thread, then `done(result)` on it."""
        self.status.config(text=busy_text)
        self.config(cursor="watch")

        def target():
            try:
                self.jobs.put((done, work(), None))
            except Exception as e:  # report, don't crash the window
                crashlog.report(type(e), e, e.__traceback__, where=busy_text)
                self.jobs.put((done, None, e))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, result, err = self.jobs.get_nowait()
                self.config(cursor="")
                if err:
                    self.status.config(text="")
                    messagebox.showerror("WinPurge", f"Something went wrong:\n{err}\n\n"
                                         f"Details are saved in:\n{crashlog.log_path()}")
                else:
                    done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _elevate(self):
        if relaunch_as_admin():
            self.destroy()

    # ------------------------------------------------------------ Apps tab

    def _build_apps_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self._fill_apps())
        ttk.Entry(top, textvariable=self.search, width=40).pack(side="left", padx=6)
        ttk.Button(top, text="Refresh", command=self.load_apps).pack(side="left")
        ttk.Button(top, text="Uninstall…", command=self.uninstall_selected).pack(side="right")

        cols = (("name", "Name", 300), ("publisher", "Publisher", 200), ("version", "Version", 110),
                ("size", "Size", 90), ("scope", "Installed for", 100))
        self.apps_tree = ttk.Treeview(f, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for c, label, w in cols:
            self.apps_tree.heading(c, text=label)
            self.apps_tree.column(c, width=w, anchor="e" if c == "size" else "w")
        self.apps_tree.pack(fill="both", expand=True, pady=(8, 0))
        self.apps_tree.bind("<Double-1>", lambda e: self.uninstall_selected())
        return f

    def load_apps(self):
        if not self.can("read_apps"):
            self.installed = []
            self._fill_apps()
            self.status.config(text="Reading installed apps is turned off. Turn it on in Settings.")
            return

        def done(apps):
            self.installed = apps
            self._fill_apps()
            self.status.config(text=f"{len(apps)} apps installed")
        self.run_bg(list_installed_apps, done, "Reading installed apps…")

    def _fill_apps(self):
        q = self.search.get().lower().strip()
        self.apps_tree.delete(*self.apps_tree.get_children())
        for i, a in enumerate(self.installed):
            if q and q not in a.name.lower() and q not in a.publisher.lower():
                continue
            self.apps_tree.insert("", "end", iid=str(i), values=(
                a.name, a.publisher, a.version,
                human_size(a.size_kb * 1024) if a.size_kb else "",
                "Everyone" if a.scope == "machine" else "Only you"))

    def uninstall_selected(self):
        sel = self.apps_tree.focus()
        if not sel:
            messagebox.showinfo("WinPurge", "Select an app first.")
            return
        app = self.installed[int(sel)]
        look_files, look_registry = self.can("scan_leftovers"), self.can("registry_cleanup")
        if not messagebox.askyesno("Uninstall", f"Run the uninstaller for {app.name}?\n\n"
                                   "Its own uninstaller opens first. Afterwards WinPurge looks for files "
                                   "it left behind, and shows them before moving anything."):
            return

        def work():
            code = run_uninstaller(app)
            remaining = list_installed_apps()
            gone = not any(a.key_name == app.key_name and a.norm == app.norm for a in remaining)
            items = (find_leftovers(app, remaining) if look_files else []) + \
                (find_registry_leftovers(app, remaining) if look_registry else [])
            items = [i for i in items if not self.ignore.contains(i.path)]
            return code, gone, remaining, items

        def done(result):
            code, gone, remaining, items = result
            self.installed = remaining
            self._fill_apps()
            if not gone:
                self.status.config(text=f"{app.name} is still installed (uninstaller exit code {code}).")
                messagebox.showinfo("WinPurge", f"{app.name} is still installed. The uninstaller may have "
                                    "been cancelled, or it needs a restart to finish.")
                return
            if not items:
                self.status.config(text=f"{app.name} removed. No leftovers found.")
                return
            LeftoversDialog(self, app, items)
        self.run_bg(work, done, f"Uninstalling {app.name}… (finish the uninstaller window)")

    # ------------------------------------------------------------ Clean tab

    def _build_clean_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text="Scan", command=self.scan).pack(side="left")
        ttk.Button(top, text="Project folders…", command=self.edit_project_roots).pack(side="left", padx=6)
        self.total = ttk.Label(top, text="")
        self.total.pack(side="left", padx=12)
        ttk.Button(top, text="Move Ticked to Recycle Bin", command=self.clean_ticked).pack(side="right")
        ttk.Button(top, text="Tick Safe Items", command=lambda: self.clean_list.tick_safe()).pack(side="right", padx=6)

        self.clean_list = CheckList(f, on_change=self._update_total)
        self.clean_list.pack(fill="both", expand=True, pady=8)
        self.note = ttk.Label(f, text="Click Scan to look for caches, old build folders and data from removed apps.",
                              wraplength=820, justify="left")
        self.note.pack(fill="x")
        self.clean_list.tree.bind("<<TreeviewSelect>>", self._show_note)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Show in Explorer", command=lambda: self._with_sel(lambda i: open_in_explorer(i.path)))
        menu.add_command(label="Don't suggest again", command=self._ignore_selected)
        self.clean_list.tree.bind("<Button-3>", lambda e: (self.clean_list.tree.focus(self.clean_list.tree.identify_row(e.y)),
                                                            menu.tk_popup(e.x_root, e.y_root)))
        return f

    def _with_sel(self, fn):
        it = self.clean_list.selected()
        if it:
            fn(it)

    def _show_note(self, _=None):
        it = self.clean_list.selected()
        if it:
            self.note.config(text=f"{it.path}\n{it.note}" if it.note else it.path)

    def _ignore_selected(self):
        it = self.clean_list.selected()
        if it:
            self.ignore.add(it.path)
            self.clean_list.remove({it.path})

    def _update_total(self):
        ticked = self.clean_list.checked()
        self.total.config(text=f"{len(ticked)} ticked, {human_size(sum(i.size for i in ticked))}")

    def edit_project_roots(self):
        if not self.can("scan_projects"):
            messagebox.showinfo("Project folders", "Looking in project folders is turned off. "
                                "Turn it on in Settings.")
            return
        roots = self.settings.data["project_roots"]
        msg = "WinPurge looks for node_modules, build and cache folders in projects inside these folders:\n\n" + \
              ("\n".join(roots) if roots else "(none yet)") + "\n\nAdd a folder?"
        if messagebox.askyesno("Project folders", msg):
            d = filedialog.askdirectory(title="Choose a folder that holds your projects")
            if d and d not in roots:
                roots.append(os.path.normpath(d))
                self.settings.save()
        elif roots and messagebox.askyesno("Project folders", "Clear the list?"):
            roots.clear()
            self.settings.save()

    def scan(self):
        roots = list(self.settings.data["project_roots"])
        age = self.settings.data["project_age_days"]
        do_caches, do_projects = self.can("scan_caches"), self.can("scan_projects")
        # Unused app data is only judged against the installed-app list.
        do_orphans = self.can("scan_leftovers") and self.can("read_apps")
        if not (do_caches or do_projects or do_orphans):
            messagebox.showinfo("WinPurge", "All scans are turned off. Turn some on in Settings.")
            return

        def work():
            items = []
            if do_caches:
                items += scan_caches()
            if do_projects:
                items += scan_projects(roots, min_age_days=age)
            if do_orphans:
                items += find_orphans(self.installed or list_installed_apps())
            return [i for i in items if not self.ignore.contains(i.path)]

        def done(items):
            self.clean_list.set_items(items)
            total = sum(i.size for i in items)
            self.status.config(text=f"Found {len(items)} items, {human_size(total)} in all.")
        self.run_bg(work, done, "Scanning…")

    def clean_ticked(self):
        items = self.clean_list.checked()
        if not items:
            messagebox.showinfo("WinPurge", "Nothing is ticked.")
            return
        size = human_size(sum(i.size for i in items))
        if not messagebox.askyesno("Move to Recycle Bin",
                                   f"Move {len(items)} items ({size}) to the Recycle Bin?\n\n"
                                   "You can restore them until you empty the Recycle Bin. "
                                   "Disk space comes back when you empty it."):
            return
        self.run_bg(lambda: recycle(items), self._after_clean, "Moving to Recycle Bin…")

    def _after_clean(self, res: Result):
        self.clean_list.remove(set(res.moved))
        show_result(self, res)


class LeftoversDialog(tk.Toplevel):
    def __init__(self, master: WinPurgeApp, app: App, items: list[Item]):
        super().__init__(master)
        self.master_app = master
        self.title(f"Leftovers from {app.name}")
        self.geometry("760x420")
        self.transient(master)
        ttk.Label(self, text=f"{app.name} was removed, but these files are still on your PC. "
                  "Ticked items move to the Recycle Bin, so you can put them back until you empty it.",
                  wraplength=720, justify="left").pack(fill="x", padx=10, pady=8)
        self.list = CheckList(self)
        self.list.pack(fill="both", expand=True, padx=10)
        self.list.set_items(items)
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Button(bar, text="Move Ticked to Recycle Bin", command=self.go).pack(side="right")
        ttk.Button(bar, text="Keep All", command=self.destroy).pack(side="right", padx=6)

    def go(self):
        items = self.list.checked()
        if not items:
            self.destroy()
            return
        self.destroy()
        self.master_app.run_bg(lambda: recycle(items), lambda r: show_result(self.master_app, r),
                               "Moving leftovers to Recycle Bin…")


def show_result(app: WinPurgeApp, res: Result):
    app.status.config(text=f"Moved {len(res.moved)} items ({human_size(res.bytes_moved)}) to the Recycle Bin. "
                           "Empty it to get the space back.")
    if res.failed:
        lines = "\n".join(f"• {os.path.basename(p) or p}: {why}" for p, why in res.failed[:15])
        more = f"\n…and {len(res.failed) - 15} more" if len(res.failed) > 15 else ""
        messagebox.showwarning("Some items were left in place", lines + more)


def main():
    WinPurgeApp().mainloop()
