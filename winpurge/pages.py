"""Overview, App Caches, Dev Tools and Large Files pages, plus shared page parts."""
from __future__ import annotations

import os
import shutil
import sys
import time
import tkinter as tk

from . import theme as th
from .common import SAFE, human_size
from .theme import px
from .widgets import (Badge, Button, Card, CheckTable, Dropdown, ProgressBar, ScrollFrame, SearchBox, Segmented,
                      ask, icon_label, label, rounded_rect)

PAD = 32
SEGMENT_COLORS = {"caches": "#3B82F6", "dev": "#8B5CF6", "large": "#F59E0B", "apps": "#14B8A6",
                  "leftovers": "#EC4899"}


class Page(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=th.P.window)
        self.app = app
        self.build()

    def header(self, title, subtitle):
        P = th.P
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
    P = th.P
    cv = tk.Canvas(parent, width=px(size), height=px(size), bg=parent.cget("bg"), highlightthickness=0, bd=0)
    rounded_rect(cv, 0, 0, px(size), px(size), px(8), soft or P.accent_soft)
    cv.create_text(px(size) / 2, px(size) / 2, text=th.icon(name), font=th.icon_font(size * 0.38),
                   fill=color or P.accent)
    return cv


def divider(parent, pady=10):
    tk.Frame(parent, bg=th.P.divider, height=1).pack(fill="x", pady=px(pady))


def setting_row(parent, title, desc, control_factory, badge=None, status=None):
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


def empty_state(parent, icon):
    """Centered icon, title, text, progress bar and button in a card."""
    P = th.P
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
        P = th.P
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
        kicker.configure(font=th.font(8, "semibold"))
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
        from .app import open_recycle_bin
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
        P = th.P
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
        P, app = th.P, self.app
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
            tk.Label(f, text="●", fg=color, bg=P.card, font=th.font(10)).pack(side="left")
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


# ====================================================================== App Caches / Dev Tools

TAB_TEXT = {
    "caches": ("App Caches", "Cache and junk that Windows and your apps pile up on their own.", "clean"),
    "dev": ("Dev Tools", "Developer caches, emulators and build folders in projects you haven't touched.", "code"),
}
SORTS = [("size", "Sort by size"), ("date", "Sort by date"), ("name", "Sort by name")]


class CleanTabPage(Page):
    def __init__(self, parent, app, tab):
        self.tab = tab
        self.filter, self.sort = "all", "size"
        super().__init__(parent, app)

    def build(self):
        P = th.P
        title, sub, icon = TAB_TEXT[self.tab]
        actions = self.header(title, sub)
        self.scan_btn = Button(actions, "Scan", icon="refresh", kind="secondary", command=self.rescan)
        self.scan_btn.pack(side="right")
        Dropdown(actions, SORTS, self.sort, command=self.set_sort, min_width=150).pack(side="right", padx=(0, px(8)))
        self.seg = Segmented(actions, [("all", "All"), ("safe", "Safe"), ("check", "Check First")], self.filter,
                             command=self.set_filter_key)
        self.seg.pack(side="right", padx=(0, px(12)))

        self.stack = tk.Frame(self, bg=P.window)
        self.stack.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(22)))
        self.empty = empty_state(self.stack, icon)
        self.results = tk.Frame(self.stack, bg=P.window)
        foot = Card(self.results, padding=14)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        self.detail = tk.Frame(self.results, bg=P.window)
        self.detail.pack(side="bottom", fill="x", pady=(px(8), 0))
        card = Card(self.results, padding=6, stretch=True)
        card.pack(fill="both", expand=True)
        self.table = CheckTable(card.body, on_change=self.update_footer, on_select=self.show_detail,
                                confirm_check=self.confirm_check,
                                columns=(("date", "Changed", 110, "w"), ("rating", "Rating", 100, "w"),
                                         ("size", "Size", 90, "e")),
                                values=lambda i: (when(i.mtime), i.level, human_size(i.size)))
        self.table.pack(fill="both", expand=True)
        self.detail_text = label(self.detail, "", "caption", P.text2, wrap=px(640))
        self.detail_text.pack(side="left", fill="x", expand=True)
        self.ignore_btn = Button(self.detail, "Don’t suggest again", kind="subtle", height=28,
                                 command=self.ignore_selected)
        self.reveal_btn = Button(self.detail, "Show in Explorer", icon="open", kind="subtle", height=28,
                                 command=self.reveal)
        fb = foot.body
        self.clean_btn = Button(fb, "Move to Recycle Bin", icon="delete", kind="primary", min_width=190,
                                command=self.clean)
        self.clean_btn.pack(side="right")
        Button(fb, "Select safe items", kind="subtle",
               command=lambda: self.table.tick(lambda i: i.level == SAFE)).pack(side="right", padx=(0, px(8)))
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        cap = "Removed items go to the Recycle Bin. Empty it to get the space back."
        if self.tab == "dev":
            cap = "Projects count as stale after the time you choose in Settings. Projects in use never appear."
        label(info, cap, "caption").pack(anchor="w")
        self._shown = None

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
        if self.filter == "safe":
            items = [i for i in items if i.level == SAFE]
        elif self.filter == "check":
            items = [i for i in items if i.level != SAFE]
        key = {"size": lambda i: -i.size, "date": lambda i: i.mtime, "name": lambda i: i.label.lower()}[self.sort]
        order = {}
        for i in sorted(items, key=key):
            order.setdefault(i.category, []).append(i)
        return [i for group in sorted(order.values(), key=lambda g: -sum(x.size for x in g)) for i in group]

    def refresh(self, force=False):
        app = self.app
        state = app.tab_state[self.tab]
        scanning = state == "scanning"
        self.scan_btn.set_text("Scanning…" if scanning else "Scan")
        self.scan_btn.set_disabled(scanning)
        items = app.results.get(self.tab)
        if items:
            self.empty.pack_forget()
            self.results.pack(fill="both", expand=True)
            if force or self._shown is not items:
                self._shown = items
                self.table.set_items(self.visible_items(), human_size)
                self.show_detail(None)
            return
        self.results.pack_forget()
        self.empty.pack(fill="both", expand=True)
        e = self.empty
        e.bar.pack_forget()
        e.button.pack_forget()
        e.bar.stop()
        title = TAB_TEXT[self.tab][0]
        if scanning:
            e.title.configure(text=f"Scanning {title}…")
            e.text.configure(text="This usually takes under a minute.")
            e.bar.pack(pady=(px(18), 0))
            e.bar.start()
        elif not app.tab_allowed(self.tab):
            e.title.configure(text=f"{title} is turned off")
            e.text.configure(text="Turn it on under “What WinPurge can do” in Settings.")
            e.button.set_text("Open Settings")
            e.button.command = lambda: app.show("settings")
            e.button.pack(pady=(px(18), 0))
        elif state == "done":
            e.title.configure(text="Nothing to clean here")
            e.text.configure(text="Your PC is tidy. Scan again any time.")
            e.button.set_text("Scan again")
            e.button.command = self.rescan
            e.button.pack(pady=(px(18), 0))
        else:
            e.title.configure(text=f"{title} not scanned yet")
            e.text.configure(text="Nothing is removed until you choose.")
            e.button.set_text("Scan now")
            e.button.command = self.rescan
            e.button.pack(pady=(px(18), 0))

    def update_footer(self):
        ticked = self.table.checked()
        self.sel_title.configure(text=f"{len(ticked)} selected  ·  {human_size(sum(i.size for i in ticked))}"
                                 if ticked else "Nothing selected")
        self.clean_btn.set_disabled(not ticked)

    def show_detail(self, item):
        for b in (self.ignore_btn, self.reveal_btn):
            b.pack_forget()
        if not item:
            self.detail_text.configure(text="Select a row to see where it is and why it's rated the way it is.")
            return
        paths = item.paths
        where = paths[0] + (f"  (+{len(paths) - 1} more folders)" if len(paths) > 1 else "")
        lines = [where]
        if item.note:
            lines.append(item.note)
        if item.locked:
            lines.append(item.locked)
        if item.extra.get("_counted_in"):
            lines.append(f"Its size is counted here, not again under {item.extra['_counted_in']}.")
        self.detail_text.configure(text="\n".join(lines))
        self.ignore_btn.pack(side="right")
        if sys.platform == "win32":
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
        self.app.results[self.tab] = [i for i in self.app.results[self.tab] if i is not it]
        self.refresh(force=True)
        self.app.toast.show("Excluded. Manage excluded folders in Settings.", "info")

    def confirm_check(self, item):
        return ask(self, "Check first", (item.note or "This may hold data you want to keep.") +
                   "\n\nSelect it anyway?", ok="Select it", icon="warning")

    def clean(self):
        items = self.table.checked()
        if not items:
            return
        size = human_size(sum(i.size for i in items))
        if not ask(self, f"Move {len(items)} item{'s' if len(items) != 1 else ''} to the Recycle Bin?",
                   f"That’s about {size}. You can restore anything from the Recycle Bin until you empty it.",
                   ok="Move to Recycle Bin", icon="delete"):
            return
        self.app.clean_items(items, self)


# ====================================================================== Large Files

KIND_CHOICES = ["All", "Videos", "Audio", "Images", "PDFs", "Documents", "Archives", "Installers",
                "Disk images and VMs", "AI models", "Unfinished downloads", "Other"]
SIZE_CHOICES = [("5", "5 MB or more"), ("50", "50 MB or more"), ("100", "100 MB or more"),
                ("500", "500 MB or more"), ("1024", "1 GB or more")]
AGE_CHOICES = [("0", "Used any time"), ("30", "Not used for 1 month"), ("90", "Not used for 3 months"),
               ("180", "Not used for 6 months"), ("365", "Not used for 1 year")]


class LargeFilesPage(Page):
    def build(self):
        P = th.P
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
        self.kind_dd = Dropdown(bar, [(k, k) for k in KIND_CHOICES], self.kind, command=self.set_kind, min_width=170)
        self.kind_dd.pack(side="left", padx=(px(12), 0))
        Dropdown(bar, SIZE_CHOICES, self.min_mb, command=self.set_size, min_width=150).pack(side="left", padx=(px(8), 0))
        Dropdown(bar, AGE_CHOICES, self.age, command=self.set_age, min_width=190).pack(side="left", padx=(px(8), 0))
        Dropdown(bar, SORTS, self.sort, command=self.set_sort, min_width=140).pack(side="right")

        self.stack = tk.Frame(self, bg=P.window)
        self.stack.pack(fill="both", expand=True, padx=px(PAD), pady=(0, px(22)))
        self.empty = empty_state(self.stack, "folder")
        self.results = tk.Frame(self.stack, bg=P.window)
        foot = Card(self.results, padding=14)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        self.detail = tk.Frame(self.results, bg=P.window)
        self.detail.pack(side="bottom", fill="x", pady=(px(8), 0))
        card = Card(self.results, padding=6, stretch=True)
        card.pack(fill="both", expand=True)
        self.card_body = card.body
        self.make_table()
        self.detail_text = label(self.detail, "", "caption", P.text2, wrap=px(680))
        self.detail_text.pack(side="left", fill="x", expand=True)
        self.reveal_btn = Button(self.detail, "Show in Explorer", icon="open", kind="subtle", height=28,
                                 command=self.reveal)
        fb = foot.body
        self.clean_btn = Button(fb, "Move to Recycle Bin", icon="delete", kind="primary", min_width=190,
                                command=self.clean)
        self.clean_btn.pack(side="right")
        self.extra_btn = Button(fb, "Select extra copies", icon="copy", kind="subtle", command=self.select_extra)
        info = tk.Frame(fb, bg=P.card)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = label(info, "", "strong")
        self.sel_title.pack(anchor="w")
        self.sel_caption = label(info, "These are your own files. Nothing here is ever cleaned automatically.",
                                 "caption")
        self.sel_caption.pack(anchor="w")
        self._shown = None

    def make_table(self):
        for w in self.card_body.winfo_children():
            w.destroy()
        dups = self.mode == "dups"

        def values(i):
            tag = i.extra.get("tag", "")
            keep = "Keep" if dups and i.extra.get("dup_keep") else ""
            return (i.extra.get("source", ""), keep or tag, when(i.extra.get("atime", i.mtime)), human_size(i.size))
        self.table = CheckTable(self.card_body, on_change=self.update_footer, on_select=self.show_detail,
                                grouped=dups, group_of=lambda i: f"Copy set {i.extra.get('dup_group')}",
                                columns=(("where", "Location", 130, "w"), ("tag", "", 130, "w"),
                                         ("used", "Last used", 110, "w"), ("size", "Size", 90, "e")),
                                values=values, headings=not dups,
                                on_open=lambda i: sys.platform == "win32" and os.path.exists(i.path) and os.startfile(i.path))
        self.table.pack(fill="both", expand=True)

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
        self.make_table()
        self.extra_btn.pack_forget()
        if m == "dups":
            self.extra_btn.pack(side="right", padx=(0, px(8)), before=self.clean_btn)
        self.refresh(force=True)

    def set_kind(self, k):
        self.kind = k
        self.refresh(force=True)

    def set_size(self, v):
        self.min_mb = v
        self.refresh(force=True)

    def set_age(self, v):
        self.age = v
        self.refresh(force=True)

    def set_sort(self, v):
        self.sort = v
        self.refresh(force=True)

    def visible_items(self):
        items = self.app.results.get("large") or []
        q = self.search.get().lower().strip()
        min_size = int(self.min_mb) * 1024 * 1024
        cutoff = time.time() - int(self.age) * 86400 if int(self.age) else None
        out = []
        for i in items:
            if i.size < min_size and i.category != "AI models":
                continue
            if self.kind != "All" and i.category != self.kind:
                continue
            if cutoff and i.extra.get("atime", i.mtime) > cutoff:
                continue
            if q and q not in i.label.lower() and q not in i.extra.get("folder", "").lower() \
                    and q not in i.extra.get("source", "").lower():
                continue
            if self.mode == "dups" and not i.extra.get("dup_group"):
                continue
            out.append(i)
        key = {"size": lambda i: -i.size, "date": lambda i: i.extra.get("atime", i.mtime),
               "name": lambda i: i.label.lower()}[self.sort]
        if self.mode == "dups":
            return sorted(out, key=lambda i: (i.extra["dup_group"], not i.extra.get("dup_keep")))
        return sorted(out, key=key)

    def refresh(self, force=False):
        app = self.app
        state = app.tab_state["large"]
        scanning = state == "scanning"
        self.scan_btn.set_text("Scanning…" if scanning else "Scan")
        self.scan_btn.set_disabled(scanning)
        items = app.results.get("large")
        n_dups = len({i.extra.get("dup_group") for i in items or [] if i.extra.get("dup_group")})
        self.seg.set_text("dups", f"Duplicates ({n_dups})" if n_dups else "Duplicates")
        if items:
            self.empty.pack_forget()
            self.results.pack(fill="both", expand=True)
            if force or self._shown is not items:
                self._shown = items
                self.table.set_items(self.visible_items(), human_size)
                self.show_detail(None)
            return
        self.results.pack_forget()
        self.empty.pack(fill="both", expand=True)
        e = self.empty
        e.bar.pack_forget()
        e.button.pack_forget()
        e.bar.stop()
        if scanning:
            e.title.configure(text="Scanning your folders…")
            e.text.configure(text="Desktop, Documents, Downloads, Videos, Music and Pictures, plus folders you added.")
            e.bar.pack(pady=(px(18), 0))
            e.bar.start()
        elif not app.tab_allowed("large"):
            e.title.configure(text="Large Files is turned off")
            e.text.configure(text="Turn on “Look for large files in your folders” in Settings.")
            e.button.set_text("Open Settings")
            e.button.command = lambda: app.show("settings")
            e.button.pack(pady=(px(18), 0))
        else:
            e.title.configure(text="No large files found" if state == "done" else "Large Files not scanned yet")
            e.text.configure(text="Finds big videos, disk images, installers, AI models and duplicate copies. "
                                  "Your files are never removed without you choosing them.")
            e.button.set_text("Scan again" if state == "done" else "Scan now")
            e.button.command = self.rescan
            e.button.pack(pady=(px(18), 0))

    def update_footer(self):
        ticked = self.table.checked()
        self.sel_title.configure(text=f"{len(ticked)} selected  ·  {human_size(sum(i.size for i in ticked))}"
                                 if ticked else "Nothing selected")
        self.clean_btn.set_disabled(not ticked)

    def show_detail(self, item):
        self.reveal_btn.pack_forget()
        if not item:
            self.detail_text.configure(text="Double-click a file to open it. Tick files to move them to the Recycle Bin.")
            return
        lines = [item.extra.get("folder") or item.path]
        if item.note:
            lines.append(item.note)
        if item.extra.get("dup_group"):
            lines.append("WinPurge suggests keeping this copy (the oldest)." if item.extra.get("dup_keep")
                         else "An identical copy of another file, byte for byte.")
        self.detail_text.configure(text="\n".join(lines))
        if sys.platform == "win32":
            self.reveal_btn.pack(side="right")

    def reveal(self):
        from .app import show_in_explorer
        it = self.table.selected()
        if it:
            show_in_explorer(it.path)

    def select_extra(self):
        self.table.tick(lambda i: bool(i.extra.get("dup_group")) and not i.extra.get("dup_keep"))

    def clean(self):
        items = self.table.checked()
        if not items:
            return
        keepers = [i for i in items if i.extra.get("dup_keep")]
        groups_all = {}
        for i in self.app.results.get("large") or []:
            if i.extra.get("dup_group"):
                groups_all.setdefault(i.extra["dup_group"], []).append(i)
        whole_sets = [g for g, members in groups_all.items() if all(m in items for m in members)]
        warn = ("\n\nEvery copy of at least one file is selected, so none would be left outside the Recycle Bin."
                if whole_sets else "")
        if not ask(self, f"Move {len(items)} file{'s' if len(items) != 1 else ''} to the Recycle Bin?",
                   f"That’s {human_size(sum(i.size for i in items))} of your own files. You can restore them "
                   f"from the Recycle Bin until you empty it.{warn}",
                   ok="Move to Recycle Bin", icon="delete", danger=bool(whole_sets or keepers)):
            return
        self.app.clean_items(items, self)
