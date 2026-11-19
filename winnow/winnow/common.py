"""Shared types and helpers: paths, sizes, safety rules."""
from __future__ import annotations

import os
import re
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

SAFE = "Safe"            # rebuilds itself; fine to remove
CHECK = "Check First"    # real data or uncertain; never ticked by default

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass
class Item:
    """One removable thing shown in the UI."""
    path: str
    label: str
    category: str
    level: str = SAFE
    size: int = 0
    note: str = ""
    kind: str = "path"          # "path" or "registry"
    checked: bool = False
    extra: dict = field(default_factory=dict)


def env_path(var: str, *parts: str, env=None) -> Path | None:
    """Join an environment folder like LOCALAPPDATA with parts, or None if unset."""
    env = os.environ if env is None else env
    base = env.get(var)
    if not base:
        return None
    return Path(base, *parts)


def is_link_or_junction(entry: os.DirEntry) -> bool:
    """True for symlinks and Windows junctions. Never follow these: a junction
    can point at C:\\ and a size scan or delete would walk the whole disk."""
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def folder_size(path: str | Path, limit_seconds: float | None = None) -> int:
    """Total bytes under path, not following links or junctions."""
    import time
    start = time.monotonic()
    total = 0
    stack = [str(path)]
    try:
        st = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(st.st_mode):
            return st.st_size
    except OSError:
        return 0
    while stack:
        if limit_seconds and time.monotonic() - start > limit_seconds:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if is_link_or_junction(entry):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


_NOISE = re.compile(
    r"\(?\b(x64|x86|64-bit|32-bit|amd64|arm64|win64|win32|version|v?\d+(\.\d+)+|\d{4})\b\)?",
    re.I,
)


def normalize(name: str) -> str:
    """'Notepad++ (64-bit x64) 8.6.2' -> 'notepad++'. Used to match folders to apps."""
    name = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name or "")  # "(x64 en-US)", "[beta]"
    name = _NOISE.sub(" ", name)
    name = re.sub(r"[^a-z0-9+]+", "", name.lower())
    return name


# Folders that must never be offered for removal, however a match looks.
def protected_paths(env=None) -> set[str]:
    env = os.environ if env is None else env
    roots = [
        env.get("SystemRoot", r"C:\Windows"),
        env.get("ProgramFiles", r"C:\Program Files"),
        env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        env.get("ProgramData", r"C:\ProgramData"),
        env.get("USERPROFILE"),
        env.get("APPDATA"),
        env.get("LOCALAPPDATA"),
        env.get("SystemDrive", "C:") + "\\",
    ]
    return {os.path.normcase(os.path.normpath(r)) for r in roots if r}


def is_protected(path: str | Path, env=None) -> bool:
    p = os.path.normcase(os.path.normpath(str(path)))
    if p in protected_paths(env):
        return True
    # Nothing directly inside the Windows folder, and nothing under it at all.
    win = os.path.normcase(os.path.normpath((env or os.environ).get("SystemRoot", r"C:\Windows")))
    return p == win or p.startswith(win + os.sep)
