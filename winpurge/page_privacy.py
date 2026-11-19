"""Privacy page: Windows telemetry and privacy settings in one place."""
from __future__ import annotations

import tkinter as tk

from . import theme as th
from .pages import PAD, Page, divider, icon_chip, setting_row
from .privacy import apply, restore
from .theme import px
from .trash import is_admin
from .widgets import Button, Card, Dropdown, ProgressBar, ScrollFrame, Toggle, ask, icon_label, inform, label


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
