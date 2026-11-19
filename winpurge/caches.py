"""Caches that rebuild themselves, and build/dependency folders in old projects."""
from __future__ import annotations

import glob
import os
import time
from pathlib import Path

from .common import CHECK, SAFE, Item, folder_size, is_link_or_junction, is_protected

# (label, base env var, relative path (may contain * globs), level, note)
CACHES: list[tuple[str, str, str, str, str]] = [
    # Windows
    ("Temporary files", "TEMP", "", SAFE, "Files programs left in your Temp folder. Files in use are skipped."),
    ("Crash dumps", "LOCALAPPDATA", "CrashDumps", SAFE, ""),
    ("DirectX shader cache", "LOCALAPPDATA", "D3DSCache", SAFE, ""),
    ("Windows error reports", "LOCALAPPDATA", r"Microsoft\Windows\WER\ReportArchive", SAFE, ""),
    ("Windows INet cache", "LOCALAPPDATA", r"Microsoft\Windows\INetCache", SAFE, ""),
    # Browsers (cache only, never profiles, history, passwords or cookies)
    ("Chrome cache", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Cache", SAFE, ""),
    ("Chrome code cache", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Code Cache", SAFE, ""),
    ("Chrome GPU cache", "LOCALAPPDATA", r"Google\Chrome\User Data\*\GPUCache", SAFE, ""),
    ("Chrome Service Worker cache", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Service Worker\CacheStorage", SAFE, ""),
    ("Edge cache", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Cache", SAFE, ""),
    ("Edge code cache", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Code Cache", SAFE, ""),
    ("Edge Service Worker cache", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Service Worker\CacheStorage", SAFE, ""),
    ("Brave cache", "LOCALAPPDATA", r"BraveSoftware\Brave-Browser\User Data\*\Cache", SAFE, ""),
    ("Firefox cache", "LOCALAPPDATA", r"Mozilla\Firefox\Profiles\*\cache2", SAFE, ""),
    # Chat and productivity apps built on Electron
    ("Discord cache", "APPDATA", r"discord\Cache", SAFE, ""),
    ("Discord code cache", "APPDATA", r"discord\Code Cache", SAFE, ""),
    ("Slack cache", "APPDATA", r"Slack\Cache", SAFE, ""),
    ("Teams cache", "APPDATA", r"Microsoft\Teams\Cache", SAFE, ""),
    ("Spotify cache", "LOCALAPPDATA", r"Spotify\Data", SAFE, ""),
    ("VS Code cache", "APPDATA", r"Code\Cache", SAFE, ""),
    ("VS Code cached data", "APPDATA", r"Code\CachedData", SAFE, ""),
    ("VS Code extension downloads", "APPDATA", r"Code\CachedExtensionVSIXs", SAFE, ""),
    ("Cursor cache", "APPDATA", r"Cursor\Cache", SAFE, ""),
    # Developer tools
    ("npm cache", "LOCALAPPDATA", "npm-cache", SAFE, ""),
    ("Yarn cache", "LOCALAPPDATA", r"Yarn\Cache", SAFE, ""),
    ("pnpm cache", "LOCALAPPDATA", "pnpm-cache", SAFE, ""),
    ("Bun cache", "USERPROFILE", r".bun\install\cache", SAFE, ""),
    ("pip cache", "LOCALAPPDATA", r"pip\Cache", SAFE, ""),
    ("uv cache", "LOCALAPPDATA", r"uv\cache", SAFE, ""),
    ("Poetry cache", "LOCALAPPDATA", r"pypoetry\Cache", SAFE, ""),
    ("NuGet HTTP cache", "LOCALAPPDATA", r"NuGet\v3-cache", SAFE, ""),
    ("NuGet packages", "USERPROFILE", r".nuget\packages", CHECK, "Re-downloaded on next build, which needs internet and takes time."),
    ("Gradle caches", "USERPROFILE", r".gradle\caches", SAFE, ""),
    ("Maven repository", "USERPROFILE", r".m2\repository", CHECK, "Re-downloaded on next build."),
    ("Go build cache", "LOCALAPPDATA", "go-build", SAFE, ""),
    ("Cargo registry cache", "USERPROFILE", r".cargo\registry\cache", SAFE, ""),
    ("Playwright browsers", "LOCALAPPDATA", "ms-playwright", CHECK, "Tests need them; reinstall with npx playwright install."),
    ("Puppeteer browsers", "USERPROFILE", r".cache\puppeteer", CHECK, ""),
    ("Hugging Face models", "USERPROFILE", r".cache\huggingface\hub", CHECK, "Downloaded AI models. Large to download again."),
    ("Electron download cache", "LOCALAPPDATA", r"electron\Cache", SAFE, ""),
    ("Android build cache", "USERPROFILE", r".android\build-cache", SAFE, ""),
    ("Docker Desktop logs", "LOCALAPPDATA", r"Docker\log", SAFE, ""),
]

# Folders inside a project that a build or install command recreates.
PROJECT_JUNK = {
    "node_modules": "npm/yarn/pnpm install",
    ".next": "next build",
    ".nuxt": "nuxt build",
    ".turbo": "turbo",
    ".parcel-cache": "parcel",
    ".angular": "ng build",
    "__pycache__": "Python",
    ".pytest_cache": "pytest",
    ".mypy_cache": "mypy",
    ".ruff_cache": "ruff",
    ".tox": "tox",
    ".venv": "python -m venv",
    ".gradle": "gradle",
    "bin": "dotnet build",
    "obj": "dotnet build",
    "target": "cargo/maven build",
}
# These generic names only count as junk next to the file that proves it.
NEEDS_MARKER = {
    "bin": ("*.csproj", "*.fsproj", "*.vbproj", "*.sln"),
    "obj": ("*.csproj", "*.fsproj", "*.vbproj", "*.sln"),
    "target": ("Cargo.toml", "pom.xml"),
    ".venv": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"),
}
PROJECT_MARKERS = (".git", "package.json", "pyproject.toml", "Cargo.toml", "pom.xml",
                   "build.gradle", "build.gradle.kts", "go.mod", "*.sln", "*.csproj")


def scan_caches(env=None) -> list[Item]:
    env = os.environ if env is None else env
    items = []
    seen = set()
    for label, var, rel, level, note in CACHES:
        base = env.get(var)
        if not base:
            continue
        rel = rel.replace("\\", os.sep)
        pattern = os.path.join(base, rel) if rel else base
        for path in glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]:
            key = os.path.normcase(os.path.normpath(path))
            if key in seen or not os.path.isdir(path):
                continue
            seen.add(key)
            if is_protected(path, env):
                continue  # e.g. TEMP set to C:\Windows\Temp or the profile itself
            size = folder_size(path, limit_seconds=10)
            if size < 1024 * 1024:  # skip anything under 1 MB
                continue
            profile = ""
            if "*" in rel:
                parts = Path(path).parts
                star_index = Path(rel).parts.index("*")
                profile = f" ({parts[len(Path(base).parts) + star_index]})"
            items.append(Item(path=path, label=label + profile, category="Caches",
                              level=level, size=size, note=note, checked=(level == SAFE),
                              extra={"contents_only": True}))
    return sorted(items, key=lambda i: -i.size)


def _has(folder: str, patterns) -> bool:
    return any(glob.glob(os.path.join(glob.escape(folder), p)) for p in patterns)


def _newest_mtime(folder: str, limit: int = 2000) -> float:
    """Newest modification time among a project's own files (skipping junk folders)."""
    newest = 0.0
    count = 0
    stack = [folder]
    while stack and count < limit:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    if is_link_or_junction(e):
                        continue
                    count += 1
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name not in PROJECT_JUNK and e.name != ".git":
                                stack.append(e.path)
                        else:
                            newest = max(newest, e.stat(follow_symlinks=False).st_mtime)
                    except OSError:
                        pass
        except OSError:
            pass
    return newest


def scan_projects(roots: list[str], min_age_days: int = 30, max_depth: int = 5) -> list[Item]:
    """Build and dependency folders in projects not edited for `min_age_days`."""
    cutoff = time.time() - min_age_days * 86400
    items = []

    def walk(folder: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        is_project = _has(folder, PROJECT_MARKERS)
        project_old = None
        for e in entries:
            if is_link_or_junction(e) or not e.is_dir(follow_symlinks=False):
                continue
            if e.name in PROJECT_JUNK and is_project:
                if e.name in NEEDS_MARKER and not _has(folder, NEEDS_MARKER[e.name]):
                    continue
                if project_old is None:
                    project_old = _newest_mtime(folder) < cutoff
                if project_old:
                    days = int((time.time() - _newest_mtime(folder)) / 86400)
                    level = CHECK if e.name == ".venv" else SAFE
                    items.append(Item(
                        path=e.path, label=f"{e.name}  in {Path(folder).name}",
                        category="Old projects", level=level, size=folder_size(e.path, limit_seconds=10),
                        note=f"Project not edited for {days} days. Recreate with: {PROJECT_JUNK[e.name]}.",
                        checked=(level == SAFE),
                    ))
                continue  # never descend into junk folders
            if e.name.startswith(".") or e.name in PROJECT_JUNK:
                continue
            walk(e.path, depth + 1)

    for r in roots:
        if os.path.isdir(r):
            walk(r, 0)
    return sorted(items, key=lambda i: -i.size)
