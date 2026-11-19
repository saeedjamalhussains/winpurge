"""The window: Overview, App Caches, Dev Tools, Large Files, Uninstaller, Privacy and
Settings pages, the welcome page, the watcher's pop-ups, and the main window."""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

from . import ui, __version__, core, windows
from .core import (allowed, app_data_dir, CHECK, complete_setup, folder_size, human_size, IgnoreList, is_admin, is_protected, Item, needs_setup, PERMISSIONS, recycle, relaunch_as_admin, SAFE, Settings)
from .scan import (App, mark_duplicates, uninstall_tools, find_dot_folders, find_leftovers, find_registry_leftovers, list_installed_apps, run_uninstaller, STALE_CHOICES)
from .windows import apply, Backup, default_backend, read_all, restore
from .ui import (apply_ttk_styles, ask, Badge, bg_of, Button, Card, CheckTable, Dialog, Dropdown, icon_label, inform, label, ProgressBar, px, rounded_rect, ScrollFrame, SearchBox, Segmented, Toast, Toggle)


# ============================================================================
# pages
# Overview, App Caches, Dev Tools and Large Files pages, plus shared page parts.
PAD = 32
SEGMENT_COLORS = {"caches": "#3B82F6", "dev": "#8B5CF6", "large": "#F59E0B", "apps": "#14B8A6",
                  "leftovers": "#EC4899"}


class Page(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=ui.P.window)
        self.app = app
        self.build()

    def header(self, title, subtitle):
        P = ui.P
        h = tk.Frame(self, bg=P.window)
        h.pack(fill="x", padx=px(PAD), pady=(px(26), px(16)))
        left = tk.Frame(h, bg=P.window)
        left.pack(side="left", fill="x", expand=True)
        label(left, title, "title").pack(anchor="w")
        label(left, subtitle, "body", P.text2).pack(anchor="w", pady=(px(2), 0))
        actions = tk.Frame(h, bg=P.window)
        actions.pack(side="right", anchor="s")
        return actions

    # Hooks the main window calls
    def build(self):
        pass

    def on_show(self):
        pass

    def on_event(self, event):
        pass

    def rescan(self):
        pass

    def focus_search(self):
        pass

    def set_filter(self, n):
        pass


def icon_chip(parent, name, color=None, soft=None, size=36):
    P = ui.P
    cv = tk.Canvas(parent, width=px(size), height=px(size), bg=parent.cget("bg"), highlightthickness=0, bd=0)
    rounded_rect(cv, 0, 0, px(size), px(size), px(8), soft or P.accent_soft)
    cv.create_text(px(size) / 2, px(size) / 2, text=ui.icon(name), font=ui.icon_font(size * 0.38),
                   fill=color or P.accent)
    return cv


def divider(parent, pady=10):
    tk.Frame(parent, bg=ui.P.divider, height=1).pack(fill="x", pady=px(pady))


def setting_row(parent, title, desc, control_factory, badge=None, status=None):
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
        tk.Label(s, text="●", font=ui.font(8), fg=color, bg=row.cget("bg")).pack(side="left")
        label(s, text, "caption", color).pack(side="left", padx=(px(4), 0))
    return control


def empty_state(parent, icon):
    """Centered icon, title, text, progress bar and button in a card."""
    P = ui.P
    card = Card(parent, padding=40, stretch=True)
    mid = tk.Frame(card.body, bg=P.card)
    mid.place(relx=0.5, rely=0.45, anchor="center")
    icon_chip(mid, icon, size=56).pack()
    card.title = label(mid, "", "heading")
    card.title.pack(pady=(px(16), 0))
    card.text = label(mid, "", "body", P.text2, wrap=px(440))
    card.text.configure(justify="center", anchor="center")
    card.text.pack(pady=(px(6), 0))
    card.bar = ProgressBar(mid, height=4)
    card.bar.configure(width=px(260))
    card.button = Button(mid, "Scan", icon="refresh", kind="primary", height=40, min_width=160)
    return card


def when(ts: float) -> str:
    if not ts:
        return ""
    days = (time.time() - ts) / 86400
    if days < 1:
        return "Today"
    if days < 2:
        return "Yesterday"
    if days < 31:
        return f"{int(days)} days ago"
    if days < 365:
        return f"{int(days / 30)} months ago"
    return f"{days / 365:.1f} years ago"


# ====================================================================== Overview

class OverviewPage(Page):
    def build(self):
        P = ui.P
        actions = self.header("Overview", "Where your space went, and what you can safely get back.")
        self.scan_btn = Button(actions, "Scan Everything", icon="refresh", kind="secondary",
                               command=self.app.scan_everything)
        self.scan_btn.pack(side="right")
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True, padx=(px(PAD), px(PAD) - px(12)))
        body = scroll.inner

        # Disk breakdown
        disk = Card(body, padding=24)
        disk.pack(fill="x", padx=(0, px(12)))
        top = tk.Frame(disk.body, bg=P.card)
        top.pack(fill="x")
        icon_chip(top, "drive").pack(side="left")
        t = tk.Frame(top, bg=P.card)
        t.pack(side="left", padx=(px(14), 0))
        self.disk_title = label(t, "", "big")
        self.disk_title.pack(anchor="w")
        self.disk_caption = label(t, "", "caption")
        self.disk_caption.pack(anchor="w")
        self.bar = tk.Canvas(disk.body, height=px(12), bg=P.card, highlightthickness=0, bd=0)
        self.bar.pack(fill="x", pady=(px(18), px(14)))
        self.bar.bind("<Configure>", lambda e: self.draw_bar())
        self.rows = tk.Frame(disk.body, bg=P.card)
        self.rows.pack(fill="x")

        # Clean Safe Items
        safe = Card(body, padding=24)
        safe.pack(fill="x", padx=(0, px(12)), pady=(px(14), 0))
        sb = safe.body
        sb.columnconfigure(0, weight=1)
        left = tk.Frame(sb, bg=P.card)
        left.grid(row=0, column=0, sticky="we")
        kicker = label(left, "CLEAN SAFE ITEMS", "caption", P.accent)
        kicker.configure(font=ui.font(8, "semibold"))
        kicker.pack(anchor="w")
        self.safe_title = label(left, "", "display")
        self.safe_title.pack(anchor="w", pady=(px(4), 0))
        self.safe_text = label(left, "", "body", P.text2, wrap=px(560))
        self.safe_text.pack(anchor="w", pady=(px(4), 0))
        self.safe_bar = ProgressBar(left, height=4)
        right = tk.Frame(sb, bg=P.card)
        right.grid(row=0, column=1, sticky="e", padx=(px(24), 0))
        self.safe_btn = Button(right, "Clean Safe Items", icon="clean", kind="primary", height=40, min_width=180,
                               command=self.clean_safe)
        self.safe_btn.pack(anchor="e")
        self.review_btn = Button(right, "Review first", kind="link", height=28, command=lambda: self.app.show("caches"))
        self.review_btn.pack(anchor="center", pady=(px(10), 0))

        # Recycle Bin and history
        row = tk.Frame(body, bg=P.window)
        row.pack(fill="x", pady=(px(14), px(16)), padx=(0, px(12)))
        row.columnconfigure(0, weight=1, uniform="r")
        row.columnconfigure(1, weight=1, uniform="r")
        bin_card = Card(row, padding=20)
        bin_card.grid(row=0, column=0, sticky="nsew", padx=(0, px(7)))
        hdr = tk.Frame(bin_card.body, bg=P.card)
        hdr.pack(fill="x")
        icon_chip(hdr, "delete", size=32).pack(side="left")
        label(hdr, "Recycle Bin", "strong", P.text2).pack(side="left", padx=(px(10), 0))
        self.bin_value = label(bin_card.body, "", "big")
        self.bin_value.pack(anchor="w", pady=(px(12), 0))
        label(bin_card.body, "WinPurge never empties it. Empty it in File Explorer when you're sure.", "caption",
              wrap=px(330)).pack(anchor="w")
        Button(bin_card.body, "Open Recycle Bin  ›", kind="link", height=24,
               command=open_recycle_bin).pack(anchor="w", pady=(px(10), 0))
        hist_card = Card(row, padding=20)
        hist_card.grid(row=0, column=1, sticky="nsew", padx=(px(7), 0))
        hdr = tk.Frame(hist_card.body, bg=P.card)
        hdr.pack(fill="x")
        icon_chip(hdr, "history", P.success, P.success_soft, size=32).pack(side="left")
        label(hdr, "Cleaned with WinPurge", "strong", P.text2).pack(side="left", padx=(px(10), 0))
        self.hist_value = label(hist_card.body, "", "big")
        self.hist_value.pack(anchor="w", pady=(px(12), 0))
        self.hist_caption = label(hist_card.body, "", "caption", wrap=px(330))
        self.hist_caption.pack(anchor="w")
        Button(hist_card.body, "Cleaning history  ›", kind="link", height=24,
               command=lambda: self.app.show("settings")).pack(anchor="w", pady=(px(10), 0))

    def on_show(self):
        self.refresh()

    def on_event(self, event):
        if event in ("scan", "cleaned", "apps", "trash", "permissions"):
            self.refresh()

    def rescan(self):
        self.app.scan_everything()

    # ------------------------------------------------------------ data

    def drive(self):
        return (os.environ.get("SystemDrive", "C:") + "\\") if sys.platform == "win32" else "/"

    def segments(self):
        app = self.app
        segs = []
        for key, name, page in (("caches", "App Caches", "caches"), ("dev", "Dev Tools", "dev"),
                                ("large", "Large Files", "large"), ("leftovers", "Leftovers", "apps")):
            items = app.results.get(key)
            segs.append((key, name, sum(i.size for i in items) if items else 0, page, items is not None))
        apps_size = sum(a.size_kb for a in app.installed) * 1024 if app.apps_state == "ready" else 0
        segs.insert(3, ("apps", "Installed apps", apps_size, "apps", app.apps_state == "ready"))
        return segs

    def draw_bar(self):
        P = ui.P
        cv = self.bar
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 10:
            return
        try:
            du = shutil.disk_usage(self.drive())
        except OSError:
            return
        cv.create_rectangle(0, 0, w, h, fill=P.divider, width=0)
        x = 0.0
        known = 0
        for key, name, size, page, ready in self.segments():
            if not size:
                continue
            seg = w * size / du.total
            known += size
            cv.create_rectangle(int(x), 0, int(x + seg), h, fill=SEGMENT_COLORS[key], width=0)
            x += seg
        other = max(0, du.used - known)
        seg = w * other / du.total
        cv.create_rectangle(int(x), 0, int(x + seg), h, fill=P.track_off, width=0)

    def refresh(self):
        P, app = ui.P, self.app
        try:
            du = shutil.disk_usage(self.drive())
            self.disk_title.configure(text=f"{human_size(du.free)} free of {human_size(du.total)}")
            self.disk_caption.configure(text=f"{human_size(du.used)} used on {self.drive().rstrip(chr(92))}")
        except OSError:
            du = None
        self.draw_bar()
        for w in self.rows.winfo_children():
            w.destroy()
        self.rows.columnconfigure(0, weight=1, uniform="c")
        self.rows.columnconfigure(1, weight=1, uniform="c")
        known = 0
        entries = []
        for key, name, size, page, ready in self.segments():
            known += size
            entries.append((SEGMENT_COLORS[key], name, size, page, ready, key))
        if du:
            entries.append((P.track_off, "Everything else", max(0, du.used - known), None, True, ""))
        for n, (color, name, size, page, ready, key) in enumerate(entries):
            f = tk.Frame(self.rows, bg=P.card, cursor="hand2" if page else "")
            f.grid(row=n // 2, column=n % 2, sticky="we", padx=(0, px(16)), pady=px(5))
            tk.Label(f, text="●", fg=color, bg=P.card, font=ui.font(10)).pack(side="left")
            label(f, name, "body").pack(side="left", padx=(px(6), 0))
            scanning = app.tab_state.get(key) == "scanning" if key in app.tab_state else False
            value = "Scanning…" if scanning else human_size(size) if ready else "Not scanned"
            pct = f"   {size / du.total * 100:.1f}%" if du and ready and size else ""
            label(f, value + pct, "caption", P.text2).pack(side="right")
            if page:
                for wdg in [f] + f.winfo_children():
                    wdg.bind("<Button-1>", lambda e, p=page: app.show(p))

        # Clean Safe Items card
        for w in (self.safe_bar,):
            w.pack_forget()
        self.safe_bar.stop()
        items = app.safe_items()
        total = sum(i.size for i in items)
        if app.everything == "scanning":
            self.safe_title.configure(text="Scanning…")
            self.safe_text.configure(text=f"Looking through {app.everything_current or 'your PC'}. "
                                          "Categories are scanned one at a time so your PC stays responsive.")
            self.safe_bar.pack(fill="x", pady=(px(14), 0))
            self.safe_bar.start()
            self.safe_btn.set_disabled(True)
            self.scan_btn.set_text("Scanning…")
            self.scan_btn.set_disabled(True)
        else:
            self.scan_btn.set_text("Scan Everything")
            self.scan_btn.set_disabled(False)
            if any(app.results[t] is not None for t in ("caches", "dev")):
                self.safe_title.configure(text=f"{human_size(total)} is safe to clean" if items
                                          else "Nothing safe to clean")
                self.safe_text.configure(
                    text=(f"{len(items)} items in App Caches and Dev Tools that rebuild themselves. "
                          "They move to the Recycle Bin, so you can put them back.") if items else
                    "Everything rebuildable is already clean. Check First items are never included.")
            else:
                self.safe_title.configure(text="Scan to see what's safe to clean")
                self.safe_text.configure(text="Press Scan Everything. Nothing is touched until you choose.")
            self.safe_btn.set_disabled(not items)

        size, n = app.trash
        self.bin_value.configure(text=human_size(size) if n else "Empty")
        total_freed = app.history.total_freed()
        last = app.history.last()
        self.hist_value.configure(text=human_size(total_freed) if total_freed else "Nothing yet")
        self.hist_caption.configure(
            text=f"Last clean: {when(last['time']).lower()}, {human_size(last['freed'])} from {last['items']} items."
            if last else "Your cleans and what they freed are listed in Settings.")

    def clean_safe(self):
        items = self.app.safe_items()
        if not items:
            return
        if not ask(self, f"Clean {len(items)} safe items?",
                   f"About {human_size(sum(i.size for i in items))} of caches and build folders that rebuild "
                   "themselves move to the Recycle Bin. Check First items are left alone.",
                   ok="Clean Safe Items", icon="clean"):
            return
        self.app.clean_items(items, self)


# ====================================================================== shared results list

def confirm_check(parent):
    """Asks before a Check First item is ticked."""
    return lambda item: ask(parent, "Check first", (item.note or "This may hold data you want to keep.") +
                            "\n\nSelect it anyway?", ok="Select it", icon="warning")


def recycle_after_confirm(page, items, what="item", note=""):
    """The one confirmation every section shows before moving items to the Recycle Bin."""
    if not items:
        return
    n = len(items)
    size = sum(i.size for i in items)
    if ask(page, f"Move {n} {what}{'s' if n != 1 else ''} to the Recycle Bin?",
           (f"That’s about {human_size(size)}. " if size else "") +
           "You can restore anything from the Recycle Bin until you empty it." + note,
           ok="Move to Recycle Bin", icon="delete", danger=bool(note)):
        page.app.clean_items(items, page)


class ItemsPanel(tk.Frame):
    """The list every scan section uses: an empty or scanning state, a table of
    items with tick boxes, a detail line for the selected row, and a footer with
    what's selected and the main action. App Caches, Dev Tools, Large Files,
    Leftovers and Command-line tools are all built from this."""

    def __init__(self, parent, app, icon, action_text, action, *, action_kind="primary", caption="",
                 hint="Select a row to see where it is and why it's rated the way it is.", ignore=True, table=None):
        P = ui.P
        super().__init__(parent, bg=P.window)
        self.app, self.hint, self.table_kw, self._shown = app, hint, dict(table or {}), None
        self.empty = empty_state(self, icon)
        self.results = tk.Frame(self, bg=P.window)
        foot = Card(self.results, padding=14)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        detail = tk.Frame(self.results, bg=P.window)
        detail.pack(side="bottom", fill="x", pady=(px(8), 0))
        self.card = Card(self.results, padding=6, stretch=True)
        self.card.pack(fill="both", expand=True)
        self.make_table()
        self.detail_text = label(detail, "", "caption", P.text2, wrap=px(660))
        self.detail_text.pack(side="left", fill="x", expand=True)
        self.ignore_btn = Button(detail, "Don’t suggest again", kind="subtle", height=28,
                                 command=self.ignore_selected) if ignore else None
        self.reveal_btn = Button(detail, "Show in Explorer", icon="open", kind="subtle", height=28, command=self.reveal)
        fb = foot.body
        self.action_btn = Button(fb, action_text, icon="delete", kind=action_kind, min_width=190,
                                 command=lambda: action(self.table.checked()))
        self.action_btn.pack(side="right")
        self.buttons = tk.Frame(fb, bg=P.card)        # pages add extra buttons here
        self.buttons.pack(side="right", padx=(0, px(8)))
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.caption = label(info, caption, "caption", wrap=px(600))
        self.caption.pack(anchor="w")

    def make_table(self, **changes):
        self.table_kw.update(changes)
        for w in self.card.body.winfo_children():
            w.destroy()
        self.table = CheckTable(self.card.body, on_change=self.update_footer, on_select=self.show_detail,
                                **self.table_kw)
        self.table.pack(fill="both", expand=True)
        self._shown = None

    def show(self, source, visible, force=False, untick=False):
        """Show items. `source` is the scan's list (redrawn only when it changes);
        `visible` makes the filtered, sorted rows."""
        self.empty.pack_forget()
        self.results.pack(fill="both", expand=True)
        if force or self._shown is not source:
            if untick and self._shown is not source:
                for i in source:
                    i.checked = False          # nothing is selected for you here
            self._shown = source
            self.table.set_items(visible() if callable(visible) else visible, human_size)
            self.show_detail(None)

    def show_state(self, tab, name, describe, rescan):
        """Scanning, turned off, nothing found, or not scanned yet."""
        app, e = self.app, self.empty
        state = app.tab_state[tab]
        self.results.pack_forget()
        self.empty.pack(fill="both", expand=True)
        e.bar.pack_forget()
        e.button.pack_forget()
        e.bar.stop()
        if state == "scanning":
            title, text, btn = f"Scanning {name}…", "This usually takes under a minute.", None
        elif not app.tab_allowed(tab):
            title, text = f"{name} is turned off", "Turn it on under “What WinPurge can do” in Settings."
            btn = ("Open Settings", lambda: app.show("settings"))
        elif state == "done":
            title, text, btn = f"Nothing found in {name}", describe, ("Scan again", rescan)
        else:
            title, text, btn = f"{name} not scanned yet", describe, ("Scan now", rescan)
        e.title.configure(text=title)
        e.text.configure(text=text)
        if btn:
            e.button.set_text(btn[0])
            e.button.command = btn[1]
            e.button.pack(pady=(px(18), 0))
        else:
            e.bar.pack(pady=(px(18), 0))
            e.bar.start()
        self._shown = None

    def update_footer(self):
        ticked = self.table.checked()
        size = sum(i.size for i in ticked)
        self.sel_title.configure(text=(f"{len(ticked)} selected" + (f"  ·  {human_size(size)}" if size else ""))
                                 if ticked else "Nothing selected")
        self.action_btn.set_disabled(not ticked)

    def show_detail(self, item):
        for b in (self.ignore_btn, self.reveal_btn):
            if b:
                b.pack_forget()
        if not item:
            self.detail_text.configure(text=self.hint)
            return
        paths = item.paths
        lines = [item.extra.get("folder") or paths[0] + (f"  (+{len(paths) - 1} more folders)" if len(paths) > 1 else "")]
        if item.note:
            lines.append(item.note)
        if item.locked:
            lines.append(item.locked)
        if item.extra.get("_counted_in"):
            lines.append(f"Its size is counted here, not again under {item.extra['_counted_in']}.")
        if item.extra.get("dup_group"):
            lines.append("WinPurge suggests keeping this copy (the oldest)." if item.extra.get("dup_keep")
                         else "An identical copy of another file, byte for byte.")
        self.detail_text.configure(text="\n".join(lines))
        if self.ignore_btn and item.kind == "path":
            self.ignore_btn.pack(side="right")
        if sys.platform == "win32" and os.path.exists(item.path):
            self.reveal_btn.pack(side="right", padx=(0, px(4)))

    def reveal(self):
        it = self.table.selected()
        if it:
            show_in_explorer(it.path)

    def ignore_selected(self):
        it = self.table.selected()
        if not it:
            return
        self.app.ignore.add(it.path)
        for tab, items in self.app.results.items():
            if items and it in items:
                self.app.results[tab] = [i for i in items if i is not it]
        self.app.notify("scan")
        self.app.toast.show("Excluded. Manage excluded folders in Settings.", "info")


# ====================================================================== App Caches / Dev Tools

TAB_TEXT = {
    "caches": ("App Caches", "Cache and junk that Windows and your apps pile up on their own.", "clean",
               "Windows junk, browser caches and every app's own cache folders. Nothing is removed until you choose."),
    "dev": ("Dev Tools", "Developer caches, emulators and build folders in projects you haven't touched.", "code",
            "Package caches, emulators and build folders in projects you haven't changed for a while."),
}
SORTS = [("size", "Sort by size"), ("date", "Sort by date"), ("name", "Sort by name")]
SORT_KEYS = {"size": lambda i: -i.size, "date": lambda i: i.extra.get("atime", i.mtime), "name": lambda i: i.label.lower()}


class CleanTabPage(Page):
    def __init__(self, parent, app, tab):
        self.tab = tab
        self.filter, self.sort = "all", "size"
        super().__init__(parent, app)

    def build(self):
        title, sub, icon, _ = TAB_TEXT[self.tab]
        actions = self.header(title, sub)
        self.scan_btn = Button(actions, "Scan", icon="refresh", kind="secondary", command=self.rescan)
        self.scan_btn.pack(side="right")
        Dropdown(actions, SORTS, self.sort, command=self.set_sort, min_width=150).pack(side="right", padx=(0, px(8)))
        self.seg = Segmented(actions, [("all", "All"), ("safe", "Safe"), ("check", "Check First")], self.filter,
                             command=self.set_filter_key)
        self.seg.pack(side="right", padx=(0, px(12)))
        caption = ("Projects count as stale after the time you choose in Settings. Projects in use never appear."
                   if self.tab == "dev" else "Removed items go to the Recycle Bin. Empty it to get the space back.")
        self.panel = ItemsPanel(self, self.app, icon, "Move to Recycle Bin",
                                lambda items: recycle_after_confirm(self, items), caption=caption,
                                table=dict(confirm_check=confirm_check(self),
                                           columns=(("date", "Changed", 110, "w"), ("rating", "Rating", 100, "w"),
                                                    ("size", "Size", 90, "e")),
                                           values=lambda i: (when(i.mtime), i.level, human_size(i.size))))
        self.panel.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(22)))
        Button(self.panel.buttons, "Select safe items", kind="subtle",
               command=lambda: self.panel.table.tick(lambda i: i.level == SAFE)).pack(side="right")

    def on_show(self):
        self.refresh()

    def on_event(self, event):
        if event in ("scan", "cleaned", "permissions"):
            self.refresh(force=event == "cleaned")

    def rescan(self):
        self.app.scan_tab(self.tab)

    def set_filter(self, n):
        self.set_filter_key(("all", "safe", "check")[n - 1])
        self.seg.set(self.filter)

    def set_filter_key(self, key):
        self.filter = key
        self.refresh(force=True)

    def set_sort(self, key):
        self.sort = key
        self.refresh(force=True)

    def visible_items(self):
        items = self.app.results.get(self.tab) or []
        if self.filter != "all":
            items = [i for i in items if (i.level == SAFE) == (self.filter == "safe")]
        groups: dict[str, list] = {}
        for i in sorted(items, key=SORT_KEYS[self.sort]):
            groups.setdefault(i.category, []).append(i)
        return [i for g in sorted(groups.values(), key=lambda g: -sum(x.size for x in g)) for i in g]

    def refresh(self, force=False):
        scanning = self.app.tab_state[self.tab] == "scanning"
        self.scan_btn.set_text("Scanning…" if scanning else "Scan")
        self.scan_btn.set_disabled(scanning)
        items = self.app.results.get(self.tab)
        if items:
            self.panel.show(items, self.visible_items, force)
        else:
            self.panel.show_state(self.tab, TAB_TEXT[self.tab][0], TAB_TEXT[self.tab][3], self.rescan)


# ====================================================================== Large Files

KIND_CHOICES = ["All", "Videos", "Audio", "Images", "PDFs", "Documents", "Archives", "Installers",
                "Disk images and VMs", "AI models", "Unfinished downloads", "Other"]
SIZE_CHOICES = [("5", "5 MB or more"), ("50", "50 MB or more"), ("100", "100 MB or more"),
                ("500", "500 MB or more"), ("1024", "1 GB or more")]
AGE_CHOICES = [("0", "Used any time"), ("30", "Not used for 1 month"), ("90", "Not used for 3 months"),
               ("180", "Not used for 6 months"), ("365", "Not used for 1 year")]


class LargeFilesPage(Page):
    def build(self):
        P = ui.P
        self.kind, self.min_mb, self.age, self.sort, self.mode = "All", "50", "0", "size", "files"
        actions = self.header("Large Files", "Big personal files in your user folders, downloaded AI models and "
                                             "duplicate copies.")
        self.scan_btn = Button(actions, "Scan", icon="refresh", kind="secondary", command=self.rescan)
        self.scan_btn.pack(side="right")
        self.search = SearchBox(actions, "Search files", command=lambda q: self.refresh(force=True), width=240)
        self.search.pack(side="right", padx=(0, px(8)))
        bar = tk.Frame(self, bg=P.window)
        bar.pack(fill="x", padx=px(PAD), pady=(0, px(10)))
        self.seg = Segmented(bar, [("files", "All files"), ("dups", "Duplicates")], self.mode, command=self.set_mode)
        self.seg.pack(side="left")
        for options, attr, width in (([(k, k) for k in KIND_CHOICES], "kind", 170), (SIZE_CHOICES, "min_mb", 150),
                                     (AGE_CHOICES, "age", 190)):
            Dropdown(bar, options, getattr(self, attr), min_width=width,
                     command=lambda v, a=attr: self.set_option(a, v)).pack(side="left", padx=(px(8), 0))
        Dropdown(bar, SORTS, self.sort, command=lambda v: self.set_option("sort", v), min_width=140).pack(side="right")
        self.panel = ItemsPanel(self, self.app, "folder", "Move to Recycle Bin", self.clean,
                                caption="These are your own files. Nothing here is ever cleaned automatically.",
                                hint="Double-click a file to open it. Tick files to move them to the Recycle Bin.",
                                ignore=False, table=self.table_options())
        self.panel.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(22)))
        self.extra_btn = Button(self.panel.buttons, "Select extra copies", icon="copy", kind="subtle",
                                command=self.select_extra)

    def table_options(self):
        dups = self.mode == "dups"

        def values(i):
            keep = "Keep" if dups and i.extra.get("dup_keep") else ""
            return (i.extra.get("source", ""), keep or i.extra.get("tag", ""), when(i.extra.get("atime", i.mtime)),
                    human_size(i.size))
        return dict(grouped=dups, group_of=lambda i: f"Copy set {i.extra.get('dup_group')}", values=values,
                    headings=not dups, columns=(("where", "Location", 130, "w"), ("tag", "", 130, "w"),
                                                ("used", "Last used", 110, "w"), ("size", "Size", 90, "e")),
                    on_open=lambda i: sys.platform == "win32" and os.path.exists(i.path) and os.startfile(i.path))

    def on_show(self):
        self.refresh()

    def on_event(self, event):
        if event in ("scan", "cleaned", "permissions"):
            self.refresh(force=event == "cleaned")

    def rescan(self):
        self.app.scan_tab("large")

    def focus_search(self):
        self.search.entry.focus_set()

    def set_mode(self, m):
        self.mode = m
        if m == "dups" and self.app.find_duplicates_if_needed(lambda: self.set_mode("dups")):
            return        # duplicates are checked only when asked for; refresh follows
        self.panel.make_table(**self.table_options())
        self.extra_btn.pack_forget()
        if m == "dups":
            self.extra_btn.pack(side="right")
        self.refresh(force=True)

    def set_option(self, attr, value):
        setattr(self, attr, value)
        self.refresh(force=True)

    def visible_items(self):
        q = self.search.get().lower().strip()
        min_size = int(self.min_mb) * 1024 * 1024
        cutoff = time.time() - int(self.age) * 86400 if int(self.age) else None
        out = [i for i in self.app.results.get("large") or []
               if (i.size >= min_size or i.category == "AI models")
               and (self.kind == "All" or i.category == self.kind)
               and not (cutoff and i.extra.get("atime", i.mtime) > cutoff)
               and not (q and q not in f"{i.label} {i.extra.get('folder', '')} {i.extra.get('source', '')}".lower())
               and (self.mode != "dups" or i.extra.get("dup_group"))]
        if self.mode == "dups":
            return sorted(out, key=lambda i: (i.extra["dup_group"], not i.extra.get("dup_keep")))
        return sorted(out, key=SORT_KEYS[self.sort])

    def refresh(self, force=False):
        scanning = self.app.tab_state["large"] == "scanning"
        self.scan_btn.set_text("Scanning…" if scanning else "Scan")
        self.scan_btn.set_disabled(scanning)
        items = self.app.results.get("large")
        n = len({i.extra.get("dup_group") for i in items or [] if i.extra.get("dup_group")})
        self.seg.set_text("dups", f"Duplicates ({n})" if n else "Duplicates")
        if items:
            self.panel.show(items, self.visible_items, force)
        else:
            self.panel.show_state("large", "Large Files", "Finds big videos, disk images, installers, AI models and "
                                  "duplicate copies. Your files are never removed without you choosing them.", self.rescan)

    def select_extra(self):
        self.panel.table.tick(lambda i: bool(i.extra.get("dup_group")) and not i.extra.get("dup_keep"))

    def clean(self, items):
        groups: dict = {}
        for i in self.app.results.get("large") or []:
            if i.extra.get("dup_group"):
                groups.setdefault(i.extra["dup_group"], []).append(i)
        whole = any(all(m in items for m in g) for g in groups.values())
        recycle_after_confirm(self, items, "file", "\n\nEvery copy of at least one file is selected." if whole else "")


# ====================================================================== Uninstaller
# Installed apps (one or several at once), leftovers from apps that are already
# gone, and command-line tools.

class UninstallerPage(Page):
    COLS = (("name", "Name", 300), ("publisher", "Publisher", 200), ("version", "Version", 110), ("size", "Size", 90))
    LISTS = {"leftovers": ("Leftovers", "Folders in AppData and ProgramData that no installed app claims."),
             "cli": ("Command-line tools", "Tools installed globally with npm, pipx, uv, Cargo or dotnet.")}

    def build(self):
        P = ui.P
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
        self.uninstall_btn = Button(fb, "Uninstall\u2026", icon="delete", kind="danger", min_width=150,
                                    command=self.uninstall)
        self.uninstall_btn.pack(side="right")
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.sel_caption = label(info, "", "caption")
        self.sel_caption.pack(anchor="w")

        # Leftovers and command-line tools use the shared list
        self.panels = {
            "leftovers": ItemsPanel(self.stack, self.app, "apps", "Move to Recycle Bin",
                                    lambda items: recycle_after_confirm(self, items, "leftover folder"),
                                    caption="Data left by apps that are already gone. Nothing is selected for you: "
                                            "it's app data, not a cache, so it won't come back.",
                                    table=dict(confirm_check=lambda i: True)),
            "cli": ItemsPanel(self.stack, self.app, "terminal", "Uninstall selected", self.remove_tools,
                              action_kind="danger", ignore=False,
                              caption="Removed by npm, pipx, uv, Cargo or dotnet's own uninstall. That deletes them "
                                      "permanently, not to the Recycle Bin.",
                              table=dict(confirm_check=lambda i: True)),
        }
        self.set_view("apps")

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
        for w in [self.apps_view, *self.panels.values()]:
            w.pack_forget()
        if view == "apps":
            if not self.search.winfo_ismapped():
                self.search.pack(side="right", padx=(0, px(8)), before=self.refresh_btn)
            self.apps_view.pack(fill="both", expand=True)
        else:
            self.search.pack_forget()
            self.panels[view].pack(fill="both", expand=True)
        self.refresh_all(force=True)

    def refresh_all(self, force=False):
        app = self.app
        for key, (name, _) in self.LISTS.items():
            n = len(app.results.get(key) or [])
            self.seg.set_text(key, f"{name} ({n})" if n else name)
        n = len(app.installed)
        self.seg.set_text("apps", f"Installed apps ({n})" if n else "Installed apps")
        if self.view == "apps":
            self.fill()
            return
        items = app.results.get(self.view)
        name, describe = self.LISTS[self.view]
        if items:
            self.panels[self.view].show(items, items, force, untick=True)
        else:
            self.panels[self.view].show_state(self.view, name, describe, self.rescan)

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
        from .core import close_gracefully, processes_inside
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
            from .windows import mark_handled
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
        from .windows import match_app
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

    def remove_tools(self, items):
        if not items:
            return
        by_mgr: dict[str, list[str]] = {}
        for i in items:
            by_mgr.setdefault(i.category, []).append(i.label)
        lines = "\n".join(f"{m}: {', '.join(n)}" for m, n in by_mgr.items())
        if not ask(self, f"Uninstall {len(items)} command-line tool{'s' if len(items) != 1 else ''}?",
                   f"{lines}\n\nEach is removed by its own package manager, which deletes it permanently. It doesn't "
                   "go to the Recycle Bin.", ok="Uninstall", danger=True, icon="delete"):
            return

        def done(result):
            removed, failed = result
            self.app.history.add("manual", 0, [], permanent=removed, skipped=failed)
            if removed:
                self.app.toast.show(f"Uninstalled {', '.join(removed)}.")
            if failed:
                inform(self, "Some tools weren\u2019t removed", "\n".join(f"\u2022 {n}: {w}" for n, w in failed),
                       icon="warning", icon_color=ui.P.warning)
            self.app.scan_tab("cli")
        self.panels["cli"].action_btn.set_disabled(True)
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


# ============================================================================
# page_privacy
# Privacy page: Windows telemetry and privacy settings in one place.
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
        app, P = self.app, ui.P
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
        P = ui.P
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
                       icon="warning", icon_color=ui.P.warning)
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
                       icon="warning", icon_color=ui.P.warning)
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
        from .windows import default_backend
        if app.privacy_backend is None:
            app.privacy_backend = default_backend()

        def done(res):
            app.load_privacy()
            if res.failed:
                inform(self, "Some settings weren’t restored", "\n".join(f"{n}: {w}" for n, w in res.failed),
                       icon="warning", icon_color=ui.P.warning)
            else:
                app.toast.show("Your original privacy settings are back.")
        app.run_bg(lambda: restore(app.privacy_backend, app.privacy_backup, admin), done)


# ============================================================================
# page_settings
# Settings: General, Cleaning, Uninstalling, permissions, history, About and
# Uninstall WinPurge.
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
        from .ui import Card
        body = self.scroll.inner
        label(body, title, "heading").pack(anchor="w", pady=(px(20), px(2)))
        if desc:
            label(body, desc, "caption", wrap=px(700)).pack(anchor="w", pady=(0, px(8)))
        card = Card(body, padding=20)
        card.pack(fill="x", padx=(0, px(12)), pady=(px(6) if not desc else 0, 0))
        return card.body

    def render(self):
        app, P = self.app, ui.P
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
        sched = core.schedule(data)
        due = core.next_due(data)
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
                    lambda p: Toggle(p, value=windows.context_menu_enabled(), command=self.set_menu))
        divider(b, 8)
        setting_row(b, "Review leftovers when an app is uninstalled",
                    "A small background watcher notices when any app is uninstalled, even with WinPurge closed, and "
                    "opens a review of just that app's leftovers. Nothing moves without that review. It also "
                    "reminds you when a scheduled clean is due.",
                    lambda p: Toggle(p, value=windows.watcher_enabled(), command=self.set_watch))
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
        tk.Label(row, image=ui.logo_img(px(48)), bg=P.card).pack(side="left")
        t = tk.Frame(row, bg=P.card)
        t.pack(side="left", padx=(px(14), 0))
        label(t, "WinPurge", "big").pack(anchor="w")
        label(t, f"Version {__version__}  ·  Works offline. Sends nothing anywhere.", "caption").pack(anchor="w")
        label(t, "Shortcuts: Ctrl+1–7 sections  ·  Ctrl+R scan  ·  Ctrl+Shift+R scan everything  "
                 "·  Ctrl+F search  ·  Alt+1–3 filters  ·  Ctrl+, settings", "caption",
              P.text3).pack(anchor="w", pady=(px(4), 0))
        btns = tk.Frame(row, bg=P.card)
        btns.pack(side="right")
        Button(btns, "Data folder", icon="folder", kind="subtle", command=lambda: open_path(str(app_data_dir()))).pack(side="left")
        Button(btns, "Log folder", icon="folder", kind="subtle",
               command=lambda: open_path(str(core.log_dir()))).pack(side="left", padx=(px(4), 0))

        # ---------------------------------------------------------------- Uninstall WinPurge
        b = self.section("Uninstall WinPurge")
        setting_row(b, "Uninstall WinPurge",
                    "Turns off everything WinPurge runs in the background, checks it stopped, then removes WinPurge. "
                    "Your settings and history stay unless you choose to remove them.",
                    lambda p: Button(p, "Uninstall…", kind="danger", command=self.uninstall_self))
        tk.Frame(self.scroll.inner, bg=P.window, height=px(28)).pack()

    # ------------------------------------------------------------ helpers

    def path_row(self, parent, path, on_remove, right_text=""):
        P = ui.P
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
        s = core.schedule(self.app.settings.data)
        s["enabled"] = on
        if on:
            s["last"] = time.time()   # first clean one interval from now
        self.app.settings.save()
        self.after(10, self.render)

    def set_freq(self, days):
        core.schedule(self.app.settings.data)["every_days"] = int(days)
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
            windows.set_context_menu(on)
        except OSError as e:
            inform(self, "Couldn’t change the right-click menu", str(e), icon="warning")
        self.after(10, self.render)

    def set_watch(self, on):
        try:
            windows.set_watcher(on)
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
        P = ui.P

        def build(frame):
            text = tk.Text(frame, height=16, width=80, bd=0, highlightthickness=0, bg=P.card, fg=P.text,
                           font=ui.caption_font(), wrap="none")
            sections = [("Moved to the Recycle Bin", e.get("moved", [])),
                        ("Removed permanently", e.get("permanent", [])),
                        ("Skipped", [f"{p} — {w}" for p, w in e.get("skipped", [])])]
            for title, rows in sections:
                if rows:
                    text.insert("end", f"{title} ({len(rows)})\n", ("h",))
                    text.insert("end", "\n".join(rows) + "\n\n")
            text.tag_configure("h", font=ui.body_strong())
            text.configure(state="disabled")
            text.pack(fill="both", expand=True)
        when_ = time.strftime("%d %B %Y, %H:%M", time.localtime(e["time"]))
        Dialog(self, f"Clean on {when_}", f"{'Scheduled' if e['kind'] == 'scheduled' else 'Manual'} clean. "
               f"Freed {human_size(e['freed'])} from {e['items']} items.", (("Close", True, "primary"),),
               icon="history", width=620, build=build).show()

    def uninstall_self(self):
        parts = [n for n, on in (("The uninstall watcher", windows.watcher_enabled()),
                                 ("The right-click menu item", windows.context_menu_enabled())) if on]
        listing = ("WinPurge turns these off first:\n" + "\n".join(f"• {p}" for p in parts)) if parts else \
            "Nothing of WinPurge's is running in the background."
        if not ask(self, "Uninstall WinPurge?", listing + "\n\nThen Windows removes WinPurge. Privacy settings "
                   "you changed stay changed; use Restore originals on the Privacy page first if you want them back.",
                   ok="Uninstall", danger=True, icon="delete"):
            return
        windows.remove_integrations()
        left = [n for n, on in (("the watcher", windows.watcher_enabled() or not windows.stop_watcher()),
                                ("the right-click menu item", windows.context_menu_enabled())) if on]
        if left:
            inform(self, "Something is still running", f"Couldn’t turn off {', '.join(left)}. Restart Windows "
                   "and try again.", icon="warning", icon_color=ui.P.warning)
            return
        cmd = windows.own_uninstaller()
        if cmd:
            subprocess.Popen(cmd, shell=True)
            self.app.destroy()
        else:
            inform(self, "Background parts are off",
                   "WinPurge is running from its source folder, not an installed copy. Delete that folder to "
                   "remove it.", icon="check")


# ============================================================================
# welcome
# First start: one page that explains how WinPurge keeps the PC safe and
# asks what it may look at. Nothing is scanned before Get started.
# The safety promises shown on the welcome page.
POINTS = [
    ("offline", "Works offline", "Never connects to the internet, so there’s nothing to allow in your firewall."),
    ("check", "Asks before it acts", "Scans only read. Nothing changes until you confirm."),
    ("recycle", "Recycle Bin first", "Anything removed can be put back until you empty the Recycle Bin."),
    ("shield", "Leaves Windows alone", "System folders can never be removed."),
    ("undo", "Your settings are saved", "Privacy changes can be undone in one click."),
]


class Welcome(tk.Frame):
    def __init__(self, parent, app):
        P = ui.P
        super().__init__(parent, bg=P.window)
        self.app = app
        current = app.settings.data.get("permissions") or {}
        self.choices = {p.key: current.get(p.key, p.default) for p in PERMISSIONS}

        # Left: brand and safety promises
        left = tk.Frame(self, bg=P.sidebar, width=px(420))
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        inner = tk.Frame(left, bg=P.sidebar)
        inner.pack(fill="both", expand=True, padx=px(40), pady=px(44))
        tk.Label(inner, image=ui.logo_img(px(64)), bg=P.sidebar).pack(anchor="w")
        label(inner, "Welcome to\nWinPurge", "display").pack(anchor="w", pady=(px(20), 0))
        label(inner, "Remove apps completely, clear out junk and take control of what Windows shares.",
              "body", P.text2, wrap=px(330)).pack(anchor="w", pady=(px(8), px(28)))
        for icon, title, text in POINTS:
            row = tk.Frame(inner, bg=P.sidebar)
            row.pack(fill="x", pady=px(7))
            icon_label(row, icon, 13, P.accent).pack(side="left", anchor="n", pady=(px(1), 0))
            t = tk.Frame(row, bg=P.sidebar)
            t.pack(side="left", fill="x", expand=True, padx=(px(12), 0))
            label(t, title, "strong").pack(anchor="w")
            label(t, text, "caption", wrap=px(300)).pack(anchor="w")
        tk.Frame(self, bg=P.divider, width=1).pack(side="left", fill="y")

        # Right: permissions
        right = tk.Frame(self, bg=P.window)
        right.pack(side="left", fill="both", expand=True)
        foot = tk.Frame(right, bg=P.window)
        foot.pack(side="bottom", fill="x", padx=px(40), pady=(px(12), px(28)))
        Button(foot, "Get started", icon="chevron_right", kind="primary", height=40, min_width=170,
               command=self.finish).pack(side="right")
        Button(foot, "Not now", kind="subtle", height=40, command=app.destroy).pack(side="right", padx=(0, px(8)))
        label(foot, "You can change these any time in Settings.", "caption", P.text3).pack(side="left")

        scroll = ScrollFrame(right)
        scroll.pack(fill="both", expand=True, padx=(px(40), px(28)), pady=(px(44), 0))
        body = scroll.inner
        label(body, "What can WinPurge look at?", "title").pack(anchor="w")
        label(body, "These only read. Nothing is removed or changed until you confirm it.", "body",
              P.text2).pack(anchor="w", pady=(px(4), px(18)))
        card = Card(body, padding=20)
        card.pack(fill="x", padx=(0, px(12)))
        for i, p in enumerate(PERMISSIONS):
            if i:
                tk.Frame(card.body, bg=P.divider, height=1).pack(fill="x", pady=px(10))
            row = tk.Frame(card.body, bg=P.card)
            row.pack(fill="x")
            Toggle(row, value=self.choices[p.key],
                   command=lambda v, k=p.key: self.choices.__setitem__(k, v)).pack(side="right", padx=(px(16), 0))
            t = tk.Frame(row, bg=P.card)
            t.pack(side="left", fill="x", expand=True)
            label(t, p.title, "strong").pack(anchor="w")
            label(t, p.detail, "caption", wrap=px(500)).pack(anchor="w", pady=(px(2), 0))
        tk.Frame(body, bg=P.window, height=px(12)).pack()

    def finish(self):
        complete_setup(self.app.settings.data, self.choices, self.app.settings.data.get("project_roots", []))
        self.app.finish_welcome()


# ============================================================================
# prompts
# Small windows the watcher opens on its own:
#
# LeftoversPrompt: an app was just uninstalled; review only its leftovers.
#   If there are none (or looking for leftovers is turned off), nothing appears.
# ReminderPrompt: a scheduled clean is due; open WinPurge to run it.
class _Small(tk.Tk):
    def __init__(self, title, w, h):
        super().__init__(className="WinPurge")
        self.withdraw()
        self.settings = Settings()
        ui.init(self, self.settings.data.get("theme", "system"))
        apply_ttk_styles(self)
        self.title(title)
        self.configure(bg=ui.P.window)
        self.iconphoto(True, ui.logo_img(32), ui.logo_img(16))
        self.resizable(False, False)
        W, H = px(w), px(h)
        x = self.winfo_screenwidth() - W - px(24)
        y = self.winfo_screenheight() - H - px(72)
        self.geometry(f"{W}x{H}+{max(0, x)}+{max(0, y)}")
        self.attributes("-topmost", True)
        ui.set_dark_title_bar(self, ui.P.name == "dark")

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
        P = ui.P
        body = tk.Frame(self, bg=P.window, padx=px(22), pady=px(18))
        body.pack(fill="both", expand=True)
        top = tk.Frame(body, bg=P.window)
        top.pack(fill="x")
        tk.Label(top, image=ui.logo_img(px(36)), bg=P.window).pack(side="left")
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
        core.History().add("manual", res.bytes_moved, res.moved, skipped=res.failed)
        if res.failed:
            from .ui import inform
            inform(self, "Some items were left in place",
                   "\n".join(f"• {p}: {w}" for p, w in res.failed[:10]), icon="warning")
        self.destroy()


class ReminderPrompt(_Small):
    def __init__(self):
        super().__init__("WinPurge", 440, 190)
        if not core.is_due(self.settings.data):
            self.after(10, self.destroy)
            return
        P = ui.P
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
        from .windows import launch
        launch()        # WinPurge runs a due clean when it opens
        self.destroy()


# ============================================================================
# app
# The WinPurge main window: sidebar, pages, scanning, cleaning, history.
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
        from .ui import rounded_rect
        P = ui.P
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        if self.active or self.hover:
            rounded_rect(self, 0, 0, w, h, px(6), P.card if self.active else P.control_hover,
                         P.border if self.active else None)
        if self.active:
            rounded_rect(self, px(1), h // 2 - px(8), px(4), h // 2 + px(8), px(2), P.accent)
        self.create_text(px(22), h / 2, text=ui.icon(self.icon), font=ui.icon_font(12),
                         fill=P.accent if self.active else P.text2)
        self.create_text(px(42), h / 2, text=self.text, anchor="w",
                         font=ui.body_strong() if self.active else ui.body_font(), fill=P.text if self.active else P.text2)
        if self.badge:
            self.create_text(w - px(12), h / 2, text=self.badge, anchor="e", font=ui.caption_font(), fill=P.text3)


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
        ui.init(self, self.settings.data["theme"])
        self.title("WinPurge")
        w, h = px(1180), px(760)
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(px(1000), px(660))
        self.iconphoto(True, ui.logo_img(64), ui.logo_img(32), ui.logo_img(16))

        self.ignore = IgnoreList()
        self.history = core.History()
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

        self.pending = 0                  # background jobs running; polled only while > 0
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
            self.after(400, lambda: self.page("apps").uninstall_from_path(path))
        elif self.settings.data.get("scan_on_open", True) or core.is_due(self.settings.data):
            self.after(300, self.scan_everything)

    # ------------------------------------------------------------ layout

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()
        self.pages.clear()

    def build(self):
        self._clear()
        P = ui.P
        apply_ttk_styles(self)
        self.configure(bg=P.window)
        ui.set_dark_title_bar(self, P.name == "dark")

        side = tk.Frame(self, bg=P.sidebar, width=px(236))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=P.sidebar)
        brand.pack(fill="x", padx=px(18), pady=(px(22), px(22)))
        tk.Label(brand, image=ui.logo_img(px(30)), bg=P.sidebar).pack(side="left")
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
        # Sections are built the first time they're opened, so the window
        # appears straight away.
        self.page_makers = {
            "home": lambda: OverviewPage(self.content, self),
            "caches": lambda: CleanTabPage(self.content, self, "caches"),
            "dev": lambda: CleanTabPage(self.content, self, "dev"),
            "large": lambda: LargeFilesPage(self.content, self),
            "apps": lambda: UninstallerPage(self.content, self),
            "privacy": lambda: PrivacyPage(self.content, self),
            "settings": lambda: SettingsPage(self.content, self),
        }
        self.pages = {}
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

    def page(self, key):
        """The section `key`, built now if it hasn't been opened yet."""
        if key not in self.pages:
            self.pages[key] = self.page_makers[key]()
        return self.pages[key]

    def show(self, key):
        if key not in getattr(self, "page_makers", {}):
            return
        self.page(key)
        self.current = key
        for page in self.pages.values():
            page.pack_forget()
        for k, item in self.nav.items():
            item.set_active(k == key)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        page.on_show()

    def rebuild(self):
        ui.init(self, self.settings.data["theme"])
        ui.IMAGES.clear()
        self.build()

    def show_welcome(self):
        self._clear()
        apply_ttk_styles(self)
        self.configure(bg=ui.P.window)
        ui.set_dark_title_bar(self, ui.P.name == "dark")
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
        """Run work() on a background thread at low priority (Windows' background
        mode lowers its CPU and disk priority, so the PC stays responsive), then
        done(result) on the window's thread."""
        def target():
            core.background_priority()
            try:
                self.jobs.put((done, work(), None, on_error))
            except Exception as e:
                core.report(type(e), e, e.__traceback__, where=getattr(work, "__name__", "background"))
                self.jobs.put((done, None, e, on_error))
        self.pending += 1
        if self.pending == 1:
            self.after(50, self._poll)
        threading.Thread(target=target, daemon=True).start()

    def _poll(self):
        """Hand finished work back to the window. Runs only while jobs are
        pending, so an idle WinPurge uses no CPU at all."""
        try:
            while True:
                done, result, err, on_error = self.jobs.get_nowait()
                self.pending -= 1
                if err:
                    if on_error:
                        on_error(err)
                    self.error(err)
                else:
                    done(result)
        except queue.Empty:
            pass
        if self.pending > 0:
            self.after(50, self._poll)

    def error(self, err):
        Dialog(self, "Something went wrong", f"{err}\n\nDetails are saved in {core.log_path()}",
               (("OK", True, "primary"),), icon="warning", icon_color=ui.P.danger).show()

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
            from .windows import windows_edition
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
        from .core import recycle_bin_size
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
        from .scan import count_once, default_project_roots, scan_app_caches, scan_dev_tools
        from .scan import scan_cli_tools
        from .scan import default_roots, scan_ai_models, scan_large_files
        from .scan import find_orphans
        from .core import running_exes
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
                # Duplicates are found only when you open the Duplicates view:
                # comparing file contents is the heaviest part of a scan.
                items = scan_large_files(default_roots() + extra) + scan_ai_models()
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

    def find_duplicates_if_needed(self, then) -> bool:
        """Compare Large Files for exact duplicates once per scan, at low
        priority. Returns True if it started (then() runs when it's done)."""
        items = self.results.get("large")
        if not items or getattr(self, "_dups_for", None) is items:
            return False
        self._dups_for = items
        self.toast.show("Checking for duplicates\u2026", "info", seconds=4)
        self.run_bg(lambda: mark_duplicates(items), lambda groups: then())
        return True

    def safe_items(self) -> list:
        """What Clean Safe Items takes: Safe rows in App Caches and Dev Tools."""
        return [i for t in ("caches", "dev") for i in (self.results[t] or [])
                if i.level == SAFE and not i.locked]

    # ------------------------------------------------------------ cleaning

    def clean_items(self, items, parent=None, kind="manual", done=None):
        """Move items to the Recycle Bin. Running programs that use them are
        asked to close first (manual) or their items are skipped (scheduled)."""
        from .core import close_gracefully, owners_running
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
        from .ui import inform
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
            inform(self, "Some items were left in place", lines + more, icon="warning", icon_color=ui.P.warning)

    def run_scheduled_clean_if_due(self):
        if not core.is_due(self.settings.data):
            return
        items = self.safe_items()
        core.mark_done(self.settings.data)
        self.settings.save()
        if items:
            self.clean_items(items, kind="scheduled")
