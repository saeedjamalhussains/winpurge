"""Privacy tab: see this PC's telemetry and privacy settings and change them
without opening Windows Settings."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .privacy import SETTINGS, Backup, Status, apply, default_backend, read_all, restore, windows_edition
from .trash import app_data_dir, is_admin

GREEN, AMBER, GREY = "#1a7f37", "#9a5b00", "#777"


class PrivacyTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app          # main window: run_bg, status, can()
        self.backend = None
        self.backup = Backup(app_data_dir() / "privacy-backup.json")
        self.statuses: dict[str, Status] = {}
        self.choice: dict[str, tk.StringVar] = {}
        self.rows: dict[str, dict] = {}

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left")
        self.summary = ttk.Label(top, text="")
        self.summary.pack(side="left", padx=12)
        ttk.Button(top, text="Apply changes", command=self.apply_changes).pack(side="right")
        ttk.Button(top, text="Pick most private", command=self.pick_private).pack(side="right", padx=6)
        self.restore_btn = ttk.Button(top, text="Restore my original settings", command=self.restore_all)
        self.restore_btn.pack(side="right")

        self.info = ttk.Label(self, text="", foreground=GREY, wraplength=840, justify="left")
        self.info.pack(fill="x", pady=(8, 4))

        # Scrollable list of settings.
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

        self.locked = ttk.Label(self.inner, wraplength=760, justify="left",
                                text="Showing and changing privacy settings is turned off. "
                                     "Turn it on with Settings… at the bottom of the window.")
        self._update_restore()

    def _wheel(self, e):
        if self.winfo_ismapped():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

    # ------------------------------------------------------------ reading

    def refresh(self):
        for w in self.inner.winfo_children():
            if w is not self.locked:
                w.destroy()
        if not self.app.can("privacy"):
            self.locked.pack(anchor="w", pady=20)
            self.summary.config(text="")
            self.info.config(text="")
            return
        self.locked.pack_forget()

        def work():
            if self.backend is None:
                self.backend = default_backend()
            return read_all(self.backend), windows_edition(self.backend)
        self.app.run_bg(work, self._show, "Reading privacy settings…")

    def _show(self, result):
        statuses, edition = result
        self.statuses = {s.setting.key: s for s in statuses}
        admin = is_admin()
        group = None
        for st in statuses:
            s = st.setting
            if s.group != group:
                group = s.group
                ttk.Label(self.inner, text=group, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(14, 2))
                ttk.Separator(self.inner).pack(fill="x")
            row = ttk.Frame(self.inner, padding=(0, 6))
            row.pack(fill="x")
            row.columnconfigure(0, weight=1)
            ttk.Label(row, text=s.title + ("   \U0001F6E1 admin" if s.admin else ""),
                      font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
            ttk.Label(row, text=s.detail + (f"\n{s.note}" if s.note else ""), wraplength=520,
                      justify="left", foreground="#555").grid(row=1, column=0, sticky="w")
            now = ttk.Label(row, text=f"Now: {st.label}",
                            foreground=GREEN if st.is_private else AMBER, width=34)
            now.grid(row=0, column=1, sticky="w", padx=8)
            var = tk.StringVar(value=s.option(st.current).label if st.current else "")
            labels = [o.label for o in s.options]
            box = ttk.Combobox(row, textvariable=var, values=labels, state="readonly", width=30)
            box.grid(row=1, column=1, sticky="nw", padx=8)
            box.bind("<<ComboboxSelected>>", lambda e: self._update_summary())
            if s.admin and not admin:
                box.state(["disabled"])
            self.choice[s.key] = var
            self.rows[s.key] = {"now": now}

        private = sum(1 for st in statuses if st.is_private)
        ed = f"Windows edition: {edition}. " if edition else ""
        diag_note = ("On Home and Pro, the lowest diagnostic level is Required; only Enterprise and "
                     "Education can turn it off completely. ")
        admin_note = "" if admin else "Settings marked admin need Restart as administrator. "
        self.info.config(text=f"{ed}{diag_note}{admin_note}Some changes take effect after you sign out or restart.")
        self.app.status.config(text=f"{private} of {len(statuses)} privacy settings are at their most private.")
        self._update_summary()

    # ------------------------------------------------------------ changing

    def _pending(self) -> dict[str, str]:
        out = {}
        for key, var in self.choice.items():
            st = self.statuses.get(key)
            if not st or not var.get():
                continue
            opt = next(o for o in st.setting.options if o.label == var.get())
            if opt.key != st.current:
                out[key] = opt.key
        return out

    def _update_summary(self):
        n = len(self._pending())
        self.summary.config(text=f"{n} change{'s' if n != 1 else ''} not applied yet" if n else "")

    def _update_restore(self):
        self.restore_btn.state(["disabled"] if self.backup.empty else ["!disabled"])

    def pick_private(self):
        admin = is_admin()
        for key, var in self.choice.items():
            s = self.statuses[key].setting
            if s.admin and not admin:
                continue
            var.set(s.option(s.private).label)
        self._update_summary()

    def apply_changes(self):
        changes = self._pending()
        if not changes:
            messagebox.showinfo("WinPurge", "Nothing to change.")
            return
        by_key = {s.key: s for s in SETTINGS}
        lines = "\n".join(
            f"• {by_key[k].title}: {self.statuses[k].label} → {by_key[k].option(o).label}"
            for k, o in changes.items())
        if not messagebox.askyesno("Change Windows settings",
                                   f"Change these settings?\n\n{lines}\n\n"
                                   "Your current values are saved first, so you can put them back "
                                   "with Restore my original settings."):
            return
        admin = is_admin()
        self.app.run_bg(lambda: apply(changes, self.backend, self.backup, admin),
                        self._after_change, "Changing privacy settings…")

    def restore_all(self):
        if not messagebox.askyesno("Restore", "Put back every setting WinPurge changed to what it "
                                   "was before?"):
            return
        admin = is_admin()
        if self.backend is None:
            self.backend = default_backend()
        self.app.run_bg(lambda: restore(self.backend, self.backup, admin),
                        self._after_change, "Restoring privacy settings…")

    def _after_change(self, res):
        self._update_restore()
        if res.failed:
            text = "\n".join(f"• {name}: {why}" for name, why in res.failed[:15])
            messagebox.showwarning("Some settings were not changed", text)
        self.refresh()
        if res.changed:
            self.app.status.config(text=f"Changed {len(res.changed)} setting(s). "
                                        "Some take effect after you sign out or restart.")
