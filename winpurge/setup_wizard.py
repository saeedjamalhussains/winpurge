"""First-run setup: explains what WinPurge does, shows why it is safe, and asks
for each permission before anything is scanned."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk

from . import __version__
from .permissions import PERMISSIONS, SAFETY_POINTS, complete_setup


class SetupWizard(tk.Toplevel):
    """Modal wizard. Calls on_done(settings_dict) after Finish, or on_cancel()."""

    def __init__(self, master, settings: dict, on_done, on_cancel):
        super().__init__(master)
        self.title("Set up WinPurge")
        self.geometry("700x660")
        self.minsize(600, 500)
        self.resizable(True, True)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.settings = settings
        self.on_done, self.on_cancel = on_done, on_cancel

        current = settings.get("permissions") or {p.key: p.default for p in PERMISSIONS}
        self.vars = {p.key: tk.BooleanVar(value=current.get(p.key, p.default)) for p in PERMISSIONS}
        self.roots: list[str] = list(settings.get("project_roots", []))

        self.body = ttk.Frame(self, padding=(24, 20, 24, 8))
        self.body.pack(fill="both", expand=True)
        ttk.Separator(self).pack(fill="x")
        nav = ttk.Frame(self, padding=(24, 10))
        nav.pack(fill="x")
        self.step_label = ttk.Label(nav, foreground="#666")
        self.step_label.pack(side="left")
        self.next_btn = ttk.Button(nav, text="Next", command=self._next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(nav, text="Back", command=self._back)
        self.back_btn.pack(side="right", padx=6)
        ttk.Button(nav, text="Cancel", command=self._cancel).pack(side="right", padx=(0, 18))

        self.pages = [self._page_welcome, self._page_permissions, self._page_projects, self._page_ready]
        self.index = 0
        self._show()
        self.grab_set()
        self.focus_force()

    # ------------------------------------------------------------ navigation

    def _visible_pages(self):
        return [p for p in self.pages
                if p is not self._page_projects or self.vars["scan_projects"].get()]

    def _show(self):
        for w in self.body.winfo_children():
            w.destroy()
        pages = self._visible_pages()
        self.index = min(self.index, len(pages) - 1)
        pages[self.index]()
        self.step_label.config(text=f"Step {self.index + 1} of {len(pages)}")
        self.back_btn.state(["disabled"] if self.index == 0 else ["!disabled"])
        last = self.index == len(pages) - 1
        self.next_btn.config(text="Finish" if last else
                             "Allow and continue" if pages[self.index] is self._page_permissions else "Next")

    def _next(self):
        pages = self._visible_pages()
        if self.index == len(pages) - 1:
            complete_setup(self.settings, {k: v.get() for k, v in self.vars.items()}, self.roots)
            self.grab_release()
            self.destroy()
            self.on_done(self.settings)
            return
        self.index += 1
        self._show()

    def _back(self):
        self.index = max(0, self.index - 1)
        self._show()

    def _cancel(self):
        self.grab_release()
        self.destroy()
        self.on_cancel()

    # ------------------------------------------------------------ pages

    def _heading(self, title, sub=""):
        ttk.Label(self.body, text=title, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        if sub:
            ttk.Label(self.body, text=sub, wraplength=620, justify="left").pack(anchor="w", pady=(6, 12))

    def _page_welcome(self):
        self._heading(f"Welcome to WinPurge {__version__}",
                      "WinPurge removes apps completely and clears caches and old build folders. "
                      "Before it looks at anything, here is how it keeps your PC safe.")
        for title, text in SAFETY_POINTS:
            row = ttk.Frame(self.body)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text="✔", foreground="#1a7f37", font=("Segoe UI", 12, "bold")).pack(side="left", anchor="n")
            col = ttk.Frame(row)
            col.pack(side="left", fill="x", expand=True, padx=(10, 0))
            ttk.Label(col, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(col, text=text, wraplength=580, justify="left").pack(anchor="w")

    def _page_permissions(self):
        self._heading("What can WinPurge look at?",
                      "Tick what you allow. You can change this later with Settings. "
                      "Each of these only reads; removing always needs your confirmation.")
        for p in PERMISSIONS:
            box = ttk.Frame(self.body)
            box.pack(fill="x", pady=6)
            ttk.Checkbutton(box, text=p.title, variable=self.vars[p.key],
                            command=self._update_next).pack(anchor="w")
            ttk.Label(box, text=p.detail, wraplength=580, justify="left",
                      foreground="#555").pack(anchor="w", padx=(24, 0))
        self._update_next()

    def _update_next(self):
        # Finishing with nothing allowed would leave an app that can't do anything.
        any_on = any(v.get() for v in self.vars.values())
        self.next_btn.state(["!disabled"] if any_on else ["disabled"])

    def _page_projects(self):
        self._heading("Which folders hold your projects?",
                      "WinPurge looks only inside these folders for node_modules, build and cache "
                      "folders. You can skip this and add folders later.")
        self.roots_list = tk.Listbox(self.body, height=8)
        self.roots_list.pack(fill="both", expand=True)
        for r in self.roots:
            self.roots_list.insert("end", r)
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Add folder…", command=self._add_root).pack(side="left")
        ttk.Button(row, text="Remove", command=self._remove_root).pack(side="left", padx=6)

    def _add_root(self):
        d = filedialog.askdirectory(parent=self, title="Choose a folder that holds your projects")
        if d:
            d = os.path.normpath(d)
            if d not in self.roots:
                self.roots.append(d)
                self.roots_list.insert("end", d)

    def _remove_root(self):
        sel = self.roots_list.curselection()
        if sel:
            self.roots.pop(sel[0])
            self.roots_list.delete(sel[0])

    def _page_ready(self):
        self._heading("Ready", "WinPurge will use these settings:")
        for p in PERMISSIONS:
            on = self.vars[p.key].get()
            ttk.Label(self.body, text=f"{'✔' if on else '✖'}  {p.title}",
                      foreground="#1a7f37" if on else "#888").pack(anchor="w", pady=2)
        if self.vars["scan_projects"].get():
            text = "\n".join(self.roots) if self.roots else "No project folders yet."
            ttk.Label(self.body, text=f"\nProject folders:\n{text}", justify="left").pack(anchor="w")
        ttk.Label(self.body, wraplength=620, justify="left", foreground="#555",
                  text="\nThe Apps tab fills in when you press Finish, if allowed. Caches, leftovers "
                       "and projects are only looked at when you press Scan.").pack(anchor="w")
