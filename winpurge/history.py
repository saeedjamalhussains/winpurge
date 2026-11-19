"""Cleaning history and the cleaning schedule.

History: every clean, manual or scheduled, with the space freed, what moved to
the Recycle Bin, what was removed permanently and what was skipped.
Schedule: WinPurge never cleans in the background. When a scheduled clean is
due, the next time WinPurge opens it scans and moves the Safe items in App
Caches and Dev Tools to the Recycle Bin (never Large Files, never Check First)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .trash import app_data_dir

KEEP = 200            # cleans kept in history
PATHS_PER_CLEAN = 300  # paths kept per clean

FREQUENCIES = (("7", "Every week"), ("30", "Every month"), ("91", "Every 3 months"))


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "history.json"
        try:
            self.entries: list[dict] = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.entries = []

    def add(self, kind: str, freed: int, moved: list[str], permanent: list[str] | None = None,
            skipped: list[tuple[str, str]] | None = None) -> dict:
        entry = {"time": time.time(), "kind": kind, "freed": int(freed), "items": len(moved) + len(permanent or []),
                 "moved": moved[:PATHS_PER_CLEAN], "permanent": (permanent or [])[:PATHS_PER_CLEAN],
                 "skipped": [list(s) for s in (skipped or [])][:PATHS_PER_CLEAN]}
        self.entries.insert(0, entry)
        del self.entries[KEEP:]
        try:
            self.path.write_text(json.dumps(self.entries, indent=1), "utf-8")
        except OSError:
            pass
        return entry

    def total_freed(self) -> int:
        return sum(e.get("freed", 0) for e in self.entries)

    def last(self) -> dict | None:
        return self.entries[0] if self.entries else None


def schedule(settings: dict) -> dict:
    return settings.setdefault("auto_clean", {"enabled": False, "every_days": 7, "last": 0})


def next_due(settings: dict) -> float | None:
    s = schedule(settings)
    if not s.get("enabled"):
        return None
    # Turning the schedule on sets "last" to now, so the first clean is one
    # interval later, not straight away.
    return (s.get("last") or time.time()) + int(s.get("every_days", 7)) * 86400


def is_due(settings: dict, now: float | None = None) -> bool:
    due = next_due(settings)
    return due is not None and (now or time.time()) >= due


def mark_done(settings: dict, now: float | None = None):
    schedule(settings)["last"] = now or time.time()
