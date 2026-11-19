"""First start: one page that explains how WinPurge keeps the PC safe and
asks what it may look at. Nothing is scanned before Get started."""
from __future__ import annotations

import tkinter as tk

from . import gfx
from . import theme as th
from .permissions import PERMISSIONS, complete_setup
from .theme import px
from .widgets import Button, Card, ScrollFrame, Toggle, icon_label, label

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
        P = th.P
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
        tk.Label(inner, image=gfx.logo_img(px(64)), bg=P.sidebar).pack(anchor="w")
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
