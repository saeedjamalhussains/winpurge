"""Command-line tools installed globally by npm, pipx, uv, Cargo or dotnet.
They are removed by that manager's own uninstall command, which deletes them
permanently (not to the Recycle Bin); the confirmation says so."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from .common import CHECK, IS_WINDOWS, Item, folder_size

NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


@dataclass(frozen=True)
class Manager:
    key: str
    name: str
    exe: str
    uninstall: tuple[str, ...]   # command; the tool name is appended


MANAGERS = (
    Manager("npm", "npm", "npm", ("uninstall", "-g")),
    Manager("pipx", "pipx", "pipx", ("uninstall",)),
    Manager("uv", "uv", "uv", ("tool", "uninstall")),
    Manager("cargo", "Cargo", "cargo", ("uninstall",)),
    Manager("dotnet", ".NET tools", "dotnet", ("tool", "uninstall", "-g")),
)
BY_KEY = {m.key: m for m in MANAGERS}
# npm ships these; removing them breaks npm itself.
NPM_KEEP = {"npm", "corepack"}


def _run(args: list[str], timeout=60) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                           encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _item(manager: Manager, name: str, version: str, path: str | None) -> Item:
    size = folder_size(path, limit_seconds=5) if path and os.path.exists(path) else 0
    return Item(path=path or f"{manager.key}:{name}", label=f"{name} {version}".strip(), category=manager.name,
                level=CHECK, size=size, kind="command", tab="cli",
                note=f"Removed with “{manager.exe} {' '.join(manager.uninstall)} {name}”. "
                     "This deletes it permanently; it doesn't go to the Recycle Bin.",
                extra={"manager": manager.key, "name": name})


def parse_npm(out: str, root: str) -> list[tuple[str, str, str]]:
    deps = json.loads(out or "{}").get("dependencies", {}) if out.strip() else {}
    return [(n, d.get("version", ""), os.path.join(root, n)) for n, d in deps.items() if n not in NPM_KEEP]


def parse_pipx(out: str) -> list[tuple[str, str, str]]:
    venvs = json.loads(out or "{}").get("venvs", {}) if out.strip() else {}
    res = []
    for name, v in venvs.items():
        meta = v.get("metadata", {}).get("main_package", {})
        res.append((name, meta.get("package_version", ""), ""))
    return res


def parse_uv(out: str) -> list[tuple[str, str, str]]:
    # "ruff v0.6.9\n- ruff.exe\nblack v24.8.0\n- black.exe"
    return [(m.group(1), m.group(2), "") for m in re.finditer(r"^(\S+) v(\S+)", out, re.M)]


def parse_cargo(out: str) -> list[tuple[str, str, str]]:
    # "ripgrep v14.1.0:\n    rg.exe"
    return [(m.group(1), m.group(2), "") for m in re.finditer(r"^(\S+) v([^\s:]+)(?: \([^)]*\))?:", out, re.M)]


def parse_dotnet(out: str) -> list[tuple[str, str, str]]:
    # Package Id      Version      Commands\n-----\ndotnet-ef 8.0.8 dotnet-ef
    rows = []
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1], ""))
    return rows


def scan_cli_tools(env=None) -> list[Item]:
    env = os.environ if env is None else env
    items: list[Item] = []
    which = {m.key: shutil.which(m.exe) for m in MANAGERS}
    if which["npm"]:
        root = _run([which["npm"], "root", "-g"]).strip()
        for n, v, p in parse_npm(_run([which["npm"], "ls", "-g", "--depth=0", "--json"]), root):
            items.append(_item(BY_KEY["npm"], n, v, p))
    if which["pipx"]:
        venvs = _run([which["pipx"], "environment", "--value", "PIPX_LOCAL_VENVS"]).strip()
        for n, v, _ in parse_pipx(_run([which["pipx"], "list", "--json"])):
            items.append(_item(BY_KEY["pipx"], n, v, os.path.join(venvs, n) if venvs else None))
    if which["uv"]:
        tdir = _run([which["uv"], "tool", "dir"]).strip()
        for n, v, _ in parse_uv(_run([which["uv"], "tool", "list"])):
            items.append(_item(BY_KEY["uv"], n, v, os.path.join(tdir, n) if tdir else None))
    if which["cargo"]:
        for n, v, _ in parse_cargo(_run([which["cargo"], "install", "--list"])):
            items.append(_item(BY_KEY["cargo"], n, v, None))
    if which["dotnet"]:
        for n, v, _ in parse_dotnet(_run([which["dotnet"], "tool", "list", "-g"])):
            items.append(_item(BY_KEY["dotnet"], n, v, None))
    return items


def uninstall_tools(items: list[Item]) -> tuple[list[str], list[tuple[str, str]]]:
    """Run each tool's own uninstall. Returns (removed labels, [(label, why)])."""
    removed, failed = [], []
    for it in items:
        m = BY_KEY.get(it.extra.get("manager"))
        exe = m and shutil.which(m.exe)
        if not exe:
            failed.append((it.label, "Its package manager isn't available any more."))
            continue
        try:
            r = subprocess.run([exe, *m.uninstall, it.extra["name"]], capture_output=True, text=True, timeout=300,
                               creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as e:
            failed.append((it.label, str(e)))
            continue
        if r.returncode == 0:
            removed.append(it.label)
        else:
            lines = (r.stderr or r.stdout or "").strip().splitlines()
            failed.append((it.label, lines[-1] if lines else f"Exit code {r.returncode}."))
    return removed, failed
