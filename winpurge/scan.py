"""What WinPurge looks for: installed apps, App Caches and Dev Tools, leftovers,
Large Files (with duplicates and AI models) and command-line tools."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .core import (CHECK, env_path, folder_size, is_link_or_junction, is_protected, IS_WINDOWS, Item, known_folder, normalize, SAFE)


# ============================================================================
# apps
# Installed programs, read from the same registry keys that
# Settings > Apps and Control Panel > Programs use.
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


@dataclass
class App:
    key_name: str
    name: str
    publisher: str = ""
    version: str = ""
    install_location: str = ""
    display_icon: str = ""
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    size_kb: int = 0
    scope: str = ""          # "machine" or "user"
    registry_path: str = ""  # e.g. HKLM\Software\...\Uninstall\{GUID}

    @property
    def norm(self) -> str:
        return normalize(self.name)

    @property
    def is_msi(self) -> bool:
        return bool(re.match(r"^\{[0-9A-F-]{36}\}$", self.key_name, re.I)) or \
            "msiexec" in self.uninstall_string.lower()


def _read_key(winreg, root, path, view):
    apps = []
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
    except OSError:
        return apps
    with key:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, sub) as sk:
                    def val(n, default=""):
                        try:
                            return winreg.QueryValueEx(sk, n)[0]
                        except OSError:
                            return default
                    name = val("DisplayName")
                    if not name or val("SystemComponent", 0) == 1:
                        continue
                    if val("ParentKeyName") or val("ReleaseType") in ("Update", "Hotfix", "Security Update"):
                        continue  # patches belong to their parent product
                    uninst = val("UninstallString")
                    if not uninst:
                        continue
                    apps.append(App(
                        key_name=sub,
                        name=str(name).strip(),
                        publisher=str(val("Publisher")).strip(),
                        version=str(val("DisplayVersion")).strip(),
                        install_location=str(val("InstallLocation")).strip().strip('"'),
                        display_icon=str(val("DisplayIcon")).split(",")[0].strip().strip('"'),
                        uninstall_string=str(uninst).strip(),
                        quiet_uninstall_string=str(val("QuietUninstallString")).strip(),
                        size_kb=int(val("EstimatedSize", 0) or 0),
                    ))
            except OSError:
                continue
    return apps


def list_installed_apps() -> list[App]:
    """All programs with an uninstaller, from 64-bit, 32-bit and per-user keys."""
    if not IS_WINDOWS:
        return []
    import winreg
    seen: dict[tuple, App] = {}
    sources = [
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", winreg.KEY_WOW64_64KEY, "machine"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", winreg.KEY_WOW64_32KEY, "machine"),
        (winreg.HKEY_CURRENT_USER, "HKCU", 0, "user"),
    ]
    for root, root_name, view, scope in sources:
        for app in _read_key(winreg, root, UNINSTALL_KEY, view):
            app.scope = scope
            wow = "\\WOW6432Node" if view == winreg.KEY_WOW64_32KEY else ""
            app.registry_path = f"{root_name}\\Software{wow}\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app.key_name}"
            dedupe = (app.norm, app.version)
            seen.setdefault(dedupe, app)
    return sorted(seen.values(), key=lambda a: a.name.lower())


def build_uninstall_command(app: App) -> list[str] | str:
    """The command that runs the program's own uninstaller (interactive, so
    the user sees and answers its prompts)."""
    cmd = app.uninstall_string
    if app.is_msi:
        m = re.search(r"\{[0-9A-F-]{36}\}", cmd, re.I) or re.search(r"\{[0-9A-F-]{36}\}", app.key_name, re.I)
        if m:
            # /I would *repair or modify*; /X is uninstall.
            return ["msiexec.exe", "/X", m.group(0)]
    return cmd  # run through the shell as Windows stores it (often quoted path + args)


def run_uninstaller(app: App) -> int:
    """Run the program's uninstaller and wait for it. Returns its exit code."""
    cmd = build_uninstall_command(app)
    if isinstance(cmd, list):
        return subprocess.call(cmd)
    return subprocess.call(cmd, shell=True)


# ============================================================================
# caches
# App Caches and Dev Tools scans.
#
# App Caches: Windows system junk, browser caches, and every app's own cache
# folders (found automatically, merged into one row per app).
# Dev Tools: developer tool caches, Android emulators and SDK images, Docker's
# disk, and build/dependency folders in projects you haven't touched.
MB = 1024 * 1024

# Groups shown in the two tabs.
SYSTEM_JUNK, BROWSERS, APPS = "System junk", "Browsers", "Apps"
DEV_CACHES, EMULATORS, PROJECTS, DOCKER = "Dev tool caches", "Android emulators and SDK", "Developer projects", "Docker"


@dataclass(frozen=True)
class Rule:
    label: str
    var: str            # base environment variable
    rel: str            # relative path; may contain * globs
    level: str = SAFE
    note: str = ""
    tab: str = "caches"  # "caches" or "dev"
    group: str = APPS
    admin: bool = False  # system folder: needs Restart as administrator
    contents: bool = True  # empty the folder but keep it


RULES: tuple[Rule, ...] = (
    # ---------------------------------------------------------------- system junk
    Rule("Temporary files", "TEMP", "", note="Files programs left in your Temp folder. Files in use are skipped.",
         group=SYSTEM_JUNK),
    Rule("Windows temporary files", "SystemRoot", "Temp", note="Temp files left by Windows and installers.",
         group=SYSTEM_JUNK, admin=True),
    Rule("Windows Update downloads", "SystemRoot", r"SoftwareDistribution\Download", CHECK,
         "Update files Windows already installed. Windows downloads them again if an update still needs them.",
         group=SYSTEM_JUNK, admin=True),
    Rule("Delivery Optimization cache", "SystemRoot",
         r"ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache", SAFE,
         "Update pieces Windows keeps to share with other PCs.", group=SYSTEM_JUNK, admin=True),
    Rule("Crash dumps", "LOCALAPPDATA", "CrashDumps", group=SYSTEM_JUNK),
    Rule("Windows crash dumps", "SystemRoot", "Minidump", group=SYSTEM_JUNK, admin=True),
    Rule("Error reports", "LOCALAPPDATA", r"Microsoft\Windows\WER\ReportArchive", group=SYSTEM_JUNK),
    Rule("Error reports (all users)", "ProgramData", r"Microsoft\Windows\WER\ReportArchive", group=SYSTEM_JUNK, admin=True),
    Rule("Error reports waiting to send", "ProgramData", r"Microsoft\Windows\WER\ReportQueue", group=SYSTEM_JUNK, admin=True),
    Rule("DirectX shader cache", "LOCALAPPDATA", "D3DSCache", group=SYSTEM_JUNK),
    Rule("Internet cache", "LOCALAPPDATA", r"Microsoft\Windows\INetCache", group=SYSTEM_JUNK),
    # ---------------------------------------------------------------- browsers (cache only)
    Rule("Chrome", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Cache", group=BROWSERS),
    Rule("Chrome", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Code Cache", group=BROWSERS),
    Rule("Chrome", "LOCALAPPDATA", r"Google\Chrome\User Data\*\GPUCache", group=BROWSERS),
    Rule("Chrome", "LOCALAPPDATA", r"Google\Chrome\User Data\*\Service Worker\CacheStorage", group=BROWSERS),
    Rule("Edge", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Cache", group=BROWSERS),
    Rule("Edge", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Code Cache", group=BROWSERS),
    Rule("Edge", "LOCALAPPDATA", r"Microsoft\Edge\User Data\*\Service Worker\CacheStorage", group=BROWSERS),
    Rule("Brave", "LOCALAPPDATA", r"BraveSoftware\Brave-Browser\User Data\*\Cache", group=BROWSERS),
    Rule("Brave", "LOCALAPPDATA", r"BraveSoftware\Brave-Browser\User Data\*\Code Cache", group=BROWSERS),
    Rule("Vivaldi", "LOCALAPPDATA", r"Vivaldi\User Data\*\Cache", group=BROWSERS),
    Rule("Opera", "LOCALAPPDATA", r"Opera Software\Opera Stable\Cache", group=BROWSERS),
    Rule("Firefox", "LOCALAPPDATA", r"Mozilla\Firefox\Profiles\*\cache2", group=BROWSERS),
    Rule("Zen Browser", "LOCALAPPDATA", r"zen\Profiles\*\cache2", group=BROWSERS),
    Rule("Spotify", "LOCALAPPDATA", r"Spotify\Data"),
    # ---------------------------------------------------------------- dev tool caches
    *(Rule(lbl, var, rel, lvl, note, tab="dev", group=DEV_CACHES) for lbl, var, rel, lvl, note in (
        ("npm", "LOCALAPPDATA", "npm-cache", SAFE, ""),
        ("Yarn", "LOCALAPPDATA", r"Yarn\Cache", SAFE, ""),
        ("pnpm", "LOCALAPPDATA", "pnpm-cache", SAFE, ""),
        ("pnpm store", "LOCALAPPDATA", r"pnpm\store", CHECK, "Shared packages pnpm links into projects. Projects re-download them on the next install."),
        ("Bun", "USERPROFILE", r".bun\install\cache", SAFE, ""),
        ("Deno", "LOCALAPPDATA", "deno", SAFE, ""),
        ("pip", "LOCALAPPDATA", r"pip\Cache", SAFE, ""),
        ("uv", "LOCALAPPDATA", r"uv\cache", SAFE, ""),
        ("Poetry", "LOCALAPPDATA", r"pypoetry\Cache", SAFE, ""),
        ("Conda packages", "USERPROFILE", r"anaconda3\pkgs", SAFE, "Downloaded package archives. Installed environments are not touched."),
        ("Conda packages", "USERPROFILE", r"miniconda3\pkgs", SAFE, "Downloaded package archives. Installed environments are not touched."),
        ("NuGet HTTP cache", "LOCALAPPDATA", r"NuGet\v3-cache", SAFE, ""),
        ("NuGet packages", "USERPROFILE", r".nuget\packages", CHECK, "Re-downloaded on the next build, which needs internet and takes time."),
        ("Visual Studio component cache", "LOCALAPPDATA", r"Microsoft\VisualStudio\*\ComponentModelCache", SAFE, ""),
        ("Gradle", "USERPROFILE", r".gradle\caches", SAFE, ""),
        ("Maven repository", "USERPROFILE", r".m2\repository", CHECK, "Re-downloaded on the next build."),
        ("Go build cache", "LOCALAPPDATA", "go-build", SAFE, ""),
        ("Go modules", "USERPROFILE", r"go\pkg\mod", CHECK, "Downloaded Go modules. Re-downloaded on the next build."),
        ("Cargo registry", "USERPROFILE", r".cargo\registry\cache", SAFE, ""),
        ("Composer", "LOCALAPPDATA", r"Composer", SAFE, ""),
        ("Dart and Flutter pub cache", "LOCALAPPDATA", r"Pub\Cache", CHECK, "Packages Flutter projects use. Re-downloaded with flutter pub get."),
        ("Terraform plugins", "APPDATA", r"terraform.d\plugin-cache", SAFE, ""),
        ("JetBrains IDE caches", "LOCALAPPDATA", r"JetBrains\*\caches", SAFE, "Indexes the IDE rebuilds when you open a project."),
        ("VS Code", "APPDATA", r"Code\Cache", SAFE, ""),
        ("VS Code", "APPDATA", r"Code\CachedData", SAFE, ""),
        ("VS Code", "APPDATA", r"Code\CachedExtensionVSIXs", SAFE, ""),
        ("VS Code workspace storage", "APPDATA", r"Code\User\workspaceStorage", CHECK, "Per-project editor state such as open tabs. Not your code."),
        ("Cursor", "APPDATA", r"Cursor\Cache", SAFE, ""),
        ("Cursor", "APPDATA", r"Cursor\CachedData", SAFE, ""),
        ("Electron downloads", "LOCALAPPDATA", r"electron\Cache", SAFE, ""),
        ("Playwright browsers", "LOCALAPPDATA", "ms-playwright", CHECK, "Tests need them. Reinstall with npx playwright install."),
        ("Puppeteer browsers", "USERPROFILE", r".cache\puppeteer", CHECK, ""),
        ("Android build cache", "USERPROFILE", r".android\build-cache", SAFE, ""),
    )),
    Rule("Android system images", "LOCALAPPDATA", r"Android\Sdk\system-images\*", CHECK,
         "Emulator system images. Download them again in Android Studio's SDK Manager.", tab="dev",
         group=EMULATORS, contents=False),
    Rule("Docker Desktop disk", "LOCALAPPDATA", r"Docker\wsl", CHECK,
         "All Docker images, containers and volumes. Quit Docker Desktop first. It creates a new, empty disk "
         "next time it starts.", tab="dev", group=DOCKER, contents=False),
    Rule("Docker Desktop logs", "LOCALAPPDATA", r"Docker\log", SAFE, tab="dev", group=DOCKER),
)

# Folder names that hold an app's cache, wherever they sit under AppData.
CACHE_DIR_NAMES = {"cache", "caches", "code cache", "gpucache", "dawncache", "dawngraphitecache",
                   "dawnwebgpucache", "grshadercache", "graphitedawncache", "shadercache", "cacheddata",
                   "cachestorage", "cachedextensions", "cachedextensionvsixs", "crashpad"}
# Top-level AppData folders that belong to Windows or are covered by RULES.
DISCOVERY_SKIP = {"packages", "temp", "microsoft", "crashdumps", "d3dscache", "programs", "connecteddevicesplatform",
                  "comms", "npm-cache", "pip", "uv", "pypoetry", "nuget", "yarn", "pnpm-cache", "go-build",
                  "ms-playwright", "electron", "docker", "jetbrains", "deno", "composer", "pub", "android"}
# Vendor folders whose apps sit one level down (Google\Chrome, Mozilla\Firefox).
VENDORS = {"google", "mozilla", "bravesoftware", "adobe", "jetbrains", "opera software", "apple computer",
           "apple", "nvidia corporation", "autodesk", "corel", "valve", "electronic arts", "ubisoft", "riot games",
           "epic games", "mozilla firefox"}


def _expand(rule: Rule, env) -> list[str]:
    base = env.get(rule.var)
    if not base:
        return []
    rel = rule.rel.replace("\\", os.sep)
    pattern = os.path.join(base, rel) if rel else base
    paths = glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]
    return [p for p in paths if os.path.isdir(p)]


def system_junk_paths(env=None) -> set[str]:
    """Exact system folders that may be emptied even though they sit under
    C:\\Windows or ProgramData. Nothing else under those is ever touched."""
    env = os.environ if env is None else env
    out = set()
    for r in RULES:
        if r.admin:
            for p in _expand(r, env):
                out.add(os.path.normcase(os.path.normpath(p)))
    return out


def _profile_suffix(rule: Rule, path: str, base: str) -> str:
    if "*" not in rule.rel:
        return ""
    parts = Path(path).parts
    star = Path(rule.rel.replace("\\", "/")).parts.index("*")
    name = parts[len(Path(base).parts) + star]
    return "" if name.lower() == "default" else f" ({name})"


def _newest(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def scan_rules(tab: str, env=None, skip_admin=False) -> list[Item]:
    """Items for one tab from the known locations. Rows with the same label
    and group are merged (Chrome's four cache folders become one row)."""
    env = os.environ if env is None else env
    merged: dict[tuple, Item] = {}
    seen = set()
    for r in RULES:
        if r.tab != tab or (skip_admin and r.admin):
            continue
        base = env.get(r.var, "")
        for path in _expand(r, env):
            key = os.path.normcase(os.path.normpath(path))
            if key in seen:
                continue
            seen.add(key)
            if not r.admin and is_protected(path, env):
                continue  # e.g. TEMP set to the profile itself
            size = folder_size(path, limit_seconds=10)
            if size < MB:
                continue
            label = r.label + _profile_suffix(r, path, base)
            if r.group == EMULATORS:
                label = f"{r.label}: {Path(path).name}"
            mkey = (label, r.group) if r.contents else (path,)
            item = merged.get(mkey)
            if item:
                item.extra["paths"].append(path)
                item.size += size
                item.mtime = max(item.mtime, _newest(path))
                continue
            merged[mkey] = Item(
                path=path, label=label, category=r.group, level=r.level, size=size, note=r.note,
                checked=r.level == SAFE, tab=tab, mtime=_newest(path),
                extra={"contents_only": r.contents, "paths": [path], "admin": r.admin,
                       "system_junk": r.admin})
    return list(merged.values())


def _friendly(parts: list[str]) -> str:
    """'Google', 'Chrome' -> 'Google Chrome'; 'discord' -> 'Discord'."""
    name = " ".join(parts)
    return name if any(c.isupper() for c in name) else name.title()


def discover_app_caches(env=None, known: set[str] | None = None, max_depth: int = 5) -> list[Item]:
    """Every app's cache folders under AppData, one row per app."""
    env = os.environ if env is None else env
    known = known or set()
    by_app: dict[str, Item] = {}
    for var in ("LOCALAPPDATA", "APPDATA"):
        root = env.get(var)
        if not root or not os.path.isdir(root):
            continue
        try:
            tops = [e for e in os.scandir(root) if e.is_dir(follow_symlinks=False) and not is_link_or_junction(e)]
        except OSError:
            continue
        for top in tops:
            if top.name.lower() in DISCOVERY_SKIP or top.name.startswith((".", "{")):
                continue
            app_parts = [top.name]
            stack = [(top.path, 1)]
            if top.name.lower() in VENDORS:
                try:
                    stack = [(e.path, 2) for e in os.scandir(top.path)
                             if e.is_dir(follow_symlinks=False) and not is_link_or_junction(e)]
                except OSError:
                    continue
            while stack:
                folder, depth = stack.pop()
                if top.name.lower() in VENDORS and depth == 2:
                    app_parts = [top.name, Path(folder).name]
                try:
                    entries = list(os.scandir(folder))
                except OSError:
                    continue
                for e in entries:
                    if is_link_or_junction(e) or not e.is_dir(follow_symlinks=False):
                        continue
                    low = e.name.lower()
                    if low in CACHE_DIR_NAMES:
                        key = os.path.normcase(os.path.normpath(e.path))
                        if any(key == k or key.startswith(k + os.sep) for k in known):
                            continue
                        path = os.path.join(e.path, "reports") if low == "crashpad" else e.path
                        if not os.path.isdir(path):
                            continue
                        size = folder_size(path, limit_seconds=5)
                        if size < MB:
                            continue
                        name = _friendly(app_parts if top.name.lower() in VENDORS else [top.name])
                        item = by_app.get(name)
                        if item:
                            item.extra["paths"].append(path)
                            item.size += size
                            item.mtime = max(item.mtime, _newest(path))
                        else:
                            by_app[name] = Item(path=path, label=name, category=APPS, level=SAFE, size=size,
                                                checked=True, tab="caches", mtime=_newest(path),
                                                note="Cache files this app downloads or builds again when it needs them.",
                                                extra={"contents_only": True, "paths": [path]})
                    elif depth < max_depth and low not in ("node_modules", "extensions", "indexeddb"):
                        stack.append((e.path, depth + 1))
    return list(by_app.values())


def scan_app_caches(env=None, skip_admin=False) -> list[Item]:
    items = scan_rules("caches", env, skip_admin)
    known = {os.path.normcase(os.path.normpath(p)) for i in items for p in i.extra["paths"]}
    # Folders the dev-tools tab owns are not counted again here.
    env_ = os.environ if env is None else env
    known |= {os.path.normcase(os.path.normpath(p)) for r in RULES if r.tab == "dev" for p in _expand(r, env_)}
    return items + discover_app_caches(env, known)


# ====================================================================== Dev Tools

PROJECT_JUNK = {
    "node_modules": "npm, yarn or pnpm install",
    ".next": "next build", ".nuxt": "nuxt build", ".svelte-kit": "the dev server", ".turbo": "turbo",
    ".parcel-cache": "parcel", ".angular": "ng build", ".expo": "expo start", ".dart_tool": "flutter pub get",
    "__pycache__": "Python", ".pytest_cache": "pytest", ".mypy_cache": "mypy", ".ruff_cache": "ruff",
    ".tox": "tox", ".venv": "python -m venv .venv", "venv": "python -m venv venv", ".gradle": "gradle",
    "bin": "dotnet build", "obj": "dotnet build", "target": "cargo build or mvn package",
    "build": "the project's build command", "dist": "the project's build command",
}
NEEDS_MARKER = {
    "bin": ("*.csproj", "*.fsproj", "*.vbproj", "*.sln"),
    "obj": ("*.csproj", "*.fsproj", "*.vbproj", "*.sln"),
    "target": ("Cargo.toml", "pom.xml"),
    ".venv": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"),
    "venv": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"),
    "build": ("pubspec.yaml", "build.gradle", "build.gradle.kts", "CMakeLists.txt"),
    "dist": ("package.json", "pyproject.toml"),
    ".dart_tool": ("pubspec.yaml",),
}
LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "npm-shrinkwrap.json")
PROJECT_MARKERS = (".git", "package.json", "pyproject.toml", "Cargo.toml", "pom.xml", "pubspec.yaml",
                   "build.gradle", "build.gradle.kts", "go.mod", "*.sln", "*.csproj", "requirements.txt")
STALE_CHOICES = (30, 90, 180, 365, 730, 0)   # days; 0 = show all

# Usual places people keep code, inside the home folder.
DEFAULT_CODE_FOLDERS = ("source\\repos", "Documents\\GitHub", "Projects", "projects", "code", "Code", "dev",
                        "Dev", "src", "repos", "git", "workspace", "Desktop", "Documents")


def _has(folder: str, patterns) -> bool:
    return any(glob.glob(os.path.join(glob.escape(folder), p)) for p in patterns)


def project_last_change(folder: str, limit: int = 3000) -> float:
    """Newest change in the project: its own files plus git activity
    (commits, checkouts), never the build folders' own dates."""
    newest = 0.0
    for git_file in ("HEAD", "index", os.path.join("logs", "HEAD"), "FETCH_HEAD"):
        try:
            newest = max(newest, os.stat(os.path.join(folder, ".git", git_file)).st_mtime)
        except OSError:
            pass
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


def project_in_use(folder: str, running_exes: list[str]) -> str | None:
    """Why a project must be left alone right now, or None."""
    if os.path.exists(os.path.join(folder, ".git", "index.lock")):
        return "A git command is running in this project."
    key = os.path.normcase(os.path.normpath(folder)) + os.sep
    for exe in running_exes:
        if os.path.normcase(exe).startswith(key):
            return f"{os.path.basename(exe)} is running from this project."
    return None


def default_project_roots(env=None) -> list[str]:
    env = os.environ if env is None else env
    home = env.get("USERPROFILE")
    if not home:
        return []
    return [os.path.join(home, d.replace("\\", os.sep)) for d in DEFAULT_CODE_FOLDERS
            if os.path.isdir(os.path.join(home, d.replace("\\", os.sep)))]


def scan_projects(roots: list[str], stale_days: int = 30, max_depth: int = 5, env=None,
                  running_exes: list[str] | None = None, recent_minutes: int = 10) -> list[Item]:
    """Build and dependency folders in projects not changed for `stale_days`
    (0 = show all). Projects in use right now never appear."""
    env = os.environ if env is None else env
    home = os.path.normcase(os.path.normpath(env.get("USERPROFILE", "~"))) + os.sep
    running_exes = running_exes or []
    now = time.time()
    cutoff = now - stale_days * 86400 if stale_days else None
    items, seen = [], set()

    def walk(folder: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        is_project = _has(folder, PROJECT_MARKERS)
        info = None
        for e in entries:
            if is_link_or_junction(e) or not e.is_dir(follow_symlinks=False):
                continue
            if e.name in PROJECT_JUNK and is_project:
                if e.name in NEEDS_MARKER and not _has(folder, NEEDS_MARKER[e.name]):
                    continue
                key = os.path.normcase(os.path.normpath(e.path))
                if key in seen:
                    continue
                seen.add(key)
                if info is None:
                    last = project_last_change(folder)
                    busy = project_in_use(folder, running_exes) or (
                        "Changed in the last few minutes." if now - last < recent_minutes * 60 else None)
                    info = (last, busy)
                last, busy = info
                if busy or (cutoff and last >= cutoff):
                    continue
                days = int((now - last) / 86400)
                outside_home = not (os.path.normcase(os.path.normpath(folder)) + os.sep).startswith(home)
                level, note = SAFE, f"Not changed for {days} days. Recreate with {PROJECT_JUNK[e.name]}."
                if e.name in (".venv", "venv"):
                    level = CHECK
                    note += " Anything you installed by hand into it is lost."
                if e.name == "node_modules" and not _has(folder, LOCKFILES):
                    level = CHECK
                    note += " There's no lockfile, so a reinstall may pick newer package versions."
                if outside_home:
                    level = CHECK
                    note += " This project is outside your user folder."
                items.append(Item(path=e.path, label=f"{Path(folder).name}  \u00B7  {e.name}", category=PROJECTS,
                                  level=level, size=folder_size(e.path, limit_seconds=10), note=note,
                                  checked=level == SAFE, tab="dev", mtime=last,
                                  extra={"project": folder}))
                continue
            if e.name.startswith(".") or e.name in PROJECT_JUNK or e.name in ("AppData", "OneDrive"):
                continue
            walk(e.path, depth + 1)

    for r in roots:
        if os.path.isdir(r):
            walk(r, 0)
    return [i for i in items if i.size >= 1024 * 64]


def scan_android_avds(env=None, running_exes: list[str] | None = None) -> list[Item]:
    """One row per Android emulator. A running emulator is listed but can't be selected."""
    env = os.environ if env is None else env
    home = env.get("ANDROID_AVD_HOME") or (env.get("USERPROFILE") and os.path.join(env["USERPROFILE"], ".android", "avd"))
    if not home or not os.path.isdir(home):
        return []
    running = any(os.path.basename(e).lower().startswith(("qemu-system", "emulator")) for e in (running_exes or []))
    items = []
    for d in glob.glob(os.path.join(glob.escape(home), "*.avd")):
        name = Path(d).stem
        ini = os.path.join(home, name + ".ini")
        it = Item(path=d, label=f"Emulator: {name.replace('_', ' ')}", category=EMULATORS, level=CHECK,
                  size=folder_size(d, limit_seconds=10), tab="dev", mtime=_newest(d),
                  note="An Android emulator and everything installed on it. Create it again in Android Studio.",
                  extra={"paths": [d] + ([ini] if os.path.exists(ini) else [])})
        if running:
            it.extra["locked"] = "An emulator is running. Close it to remove this one."
        items.append(it)
    return items


def scan_dev_tools(roots: list[str], stale_days: int, env=None, running_exes=None, projects=True) -> list[Item]:
    items = scan_rules("dev", env) + scan_android_avds(env, running_exes)
    if projects:
        items += scan_projects(roots, stale_days, env=env, running_exes=running_exes)
    return items


def count_once(items: list[Item]) -> list[Item]:
    """Each byte is counted once: a folder inside another listed folder is
    subtracted from the outer one's size (the outer row keeps the rest)."""
    keyed = sorted(((os.path.normcase(os.path.normpath(p)), i) for i in items for p in i.extra.get("paths", [i.path])),
                   key=lambda t: t[0])
    for idx, (k, outer) in enumerate(keyed):
        for k2, inner in keyed[idx + 1:]:
            if not k2.startswith(k + os.sep):
                break
            if inner is not outer and not inner.extra.get("_counted_in"):
                outer.size = max(0, outer.size - inner.size)
                inner.extra["_counted_in"] = outer.label
    return items


# ============================================================================
# leftovers
# Files an app leaves behind: settings in AppData, data in ProgramData,
# shortcuts in the Start menu, and folders whose app is no longer installed.
# Top-level AppData/ProgramData folders that belong to Windows itself or are
# shared by many programs. Never treated as one app's leftovers.
SYSTEM_FOLDERS = {
    "microsoft", "packages", "temp", "tmp", "programs", "windows", "comms",
    "connecteddevicesplatform", "d3dscache", "crashdumps", "history",
    "publishers", "virtualstore", "peerdistrepub", "placeholdertilelogofolder",
    "packagecache", "packagemanagement", "microsoftedge", "microsoftwindows",
    "regidcommicrosoft", "ssh", "usoshared", "usoprivate", "softwaredistribution",
    "intel", "nvidia", "nvidiacorporation", "amd", "ati", "realtek", "dell", "hp", "lenovo",
    "chocolatey", "scoop", "winget", "npm", "npmcache", "pip", "nuget",
    "applicationdata", "desktop", "documents", "startmenu", "templates",
    "mozilla", "google", "adobe", "apple", "appleinc", "jetbrains",   # vendor folders shared by several apps
    "fontcache", "iconcache", "identities", "wer", "ssl", "vs", "visualstudio",
}


def _roots(env) -> list[tuple[Path, str]]:
    pairs = [
        (env_path("APPDATA", env=env), "AppData\\Roaming"),
        (env_path("LOCALAPPDATA", env=env), "AppData\\Local"),
        (env_path("LOCALAPPDATA", "Programs", env=env), "AppData\\Local\\Programs"),
        (env_path("ProgramData", env=env), "ProgramData"),
        (env_path("ProgramFiles", env=env), "Program Files"),
        (env_path("ProgramFiles(x86)", env=env), "Program Files (x86)"),
        (env_path("APPDATA", "Microsoft", "Windows", "Start Menu", "Programs", env=env), "Start menu"),
        (env_path("ProgramData", "Microsoft", "Windows", "Start Menu", "Programs", env=env), "Start menu (all users)"),
    ]
    return [(p, label) for p, label in pairs if p is not None and p.is_dir()]


def _children(folder: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as it:
            return list(it)
    except OSError:
        return []


def app_names(app: App) -> set[str]:
    """Normalized names a folder for this app might use."""
    names = {app.norm}
    pub = normalize(app.publisher)
    if pub and app.norm.startswith(pub) and len(app.norm) - len(pub) >= 3:
        names.add(app.norm[len(pub):])          # "Mozilla Firefox" -> "firefox"
    if app.install_location:
        names.add(normalize(Path(app.install_location).name))
    return {n for n in names if len(n) >= 3}


def _owned_by_other(folder_norm: str, app: App, installed: list[App]) -> bool:
    for other in installed:
        if other is app or other.key_name == app.key_name:
            continue
        if folder_norm in app_names(other):
            return True
    return False


def find_leftovers(app: App, installed: list[App], env=None) -> list[Item]:
    """Folders and shortcuts matching `app`. Call after the app's own
    uninstaller ran; `installed` is the list of apps still present."""
    env = os.environ if env is None else env
    names = app_names(app)
    pub = normalize(app.publisher)
    found: dict[str, Item] = {}

    def add(path: str, where: str, level: str = SAFE, note: str = ""):
        if is_protected(path, env) or not os.path.exists(path):
            return
        key = os.path.normcase(os.path.normpath(path))
        if key in found:
            return
        found[key] = Item(
            path=path, label=f"{Path(path).name}  ({where})", category="Leftovers",
            level=level, size=folder_size(path, limit_seconds=5), note=note,
            checked=(level == SAFE),
        )

    if app.install_location and os.path.isdir(app.install_location):
        add(app.install_location, "install folder")

    for root, where in _roots(env):
        for entry in _children(root):
            n = normalize(Path(entry.name).stem if entry.is_file() else entry.name)
            if n in names and not _owned_by_other(n, app, installed):
                add(entry.path, where)
            elif pub and n == pub and entry.is_dir():
                # Publisher folder: take the app's subfolder, or the whole
                # publisher folder only if nothing else from that publisher is installed.
                subs = _children(Path(entry.path))
                matching = [s for s in subs if normalize(s.name) in names]
                others_from_pub = any(normalize(o.publisher) == pub and o.key_name != app.key_name for o in installed)
                if matching and (len(matching) < len(subs) or others_from_pub):
                    for s in matching:
                        add(s.path, f"{where}\\{entry.name}")
                elif matching or (subs == [] and not others_from_pub):
                    add(entry.path, where)
    return sorted(found.values(), key=lambda i: -i.size)


# Hidden folders in the user folder that belong to one app (by its normalized
# name). Exact folders only: a folder a command-line tool keeps using after the
# app is gone (such as .android for adb, .docker for the docker CLI) is not listed.
DOT_FOLDERS = {
    "visualstudiocode": [".vscode"],
    "microsoftvisualstudiocode": [".vscode"],
    "visualstudiocodeinsiders": [".vscode-insiders"],
    "vscodium": [".vscode-oss"],
    "windsurf": [".windsurf"],
    "trae": [".trae"],
    "antigravity": [".antigravity"],
    "githubdesktop": [],
    "zed": [".zed"],
    "ollama": [".ollama"],
    "lmstudio": [".lmstudio"],
}


def find_dot_folders(app: App, env=None) -> list[Item]:
    """The app's hidden settings folder in your user folder. Always unticked:
    it holds settings and extensions, not a cache."""
    env = os.environ if env is None else env
    home = env.get("USERPROFILE")
    if not home:
        return []
    out = []
    for key, folders in DOT_FOLDERS.items():
        if app.norm == key or (len(key) >= 5 and app.norm.startswith(key)):
            for f in folders:
                p = os.path.join(home, f)
                if os.path.isdir(p):
                    out.append(Item(path=p, label=f"{f}  (your user folder)", category="Leftovers", level=CHECK,
                                    size=folder_size(p, limit_seconds=5),
                                    note=f"{app.name} keeps settings and extensions here, not a cache. Check it "
                                         "before removing."))
    return out


def find_registry_leftovers(app: App, installed: list[App]) -> list[Item]:
    """HKCU\\Software\\<Publisher>\\<App> or HKCU\\Software\\<App>. Registry keys
    cannot go to the Recycle Bin, so these are backed up to a .reg file first
    and are never ticked by default."""
    if not IS_WINDOWS:
        return []
    import winreg
    items = []
    names = app_names(app)
    pub = normalize(app.publisher)
    try:
        sw = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software")
    except OSError:
        return items
    with sw:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(sw, i)
            except OSError:
                break
            i += 1
            n = normalize(sub)
            if n in SYSTEM_FOLDERS or n in ("classes", "policies", "wow6432node"):
                continue
            if n in names and not _owned_by_other(n, app, installed):
                items.append(_reg_item(f"HKCU\\Software\\{sub}"))
            elif pub and n == pub:
                try:
                    with winreg.OpenKey(sw, sub) as pk:
                        j = 0
                        while True:
                            try:
                                child = winreg.EnumKey(pk, j)
                            except OSError:
                                break
                            j += 1
                            if normalize(child) in names:
                                items.append(_reg_item(f"HKCU\\Software\\{sub}\\{child}"))
                except OSError:
                    pass
    return items


def _reg_item(path: str) -> Item:
    return Item(path=path, label=path, category="Leftovers", level=CHECK, kind="registry",
                note="Registry settings. Backed up to a .reg file before removal.")


def _known_tokens(installed: list[App]) -> set[str]:
    tokens = set()
    for a in installed:
        tokens |= app_names(a)
        if a.publisher:
            tokens.add(normalize(a.publisher))
        first = normalize(a.name.split()[0]) if a.name.split() else ""
        if len(first) >= 4:
            tokens.add(first)
    return {t for t in tokens if t}


def find_orphans(installed: list[App], env=None, min_age_days: int = 90) -> list[Item]:
    """Top-level AppData/ProgramData folders that match no installed app and
    haven't changed for `min_age_days`. Always Check First: plenty of tools
    keep data there without registering an uninstaller."""
    env = os.environ if env is None else env
    tokens = _known_tokens(installed)
    cutoff = time.time() - min_age_days * 86400
    items = []
    roots = [r for r in _roots(env) if r[1] in ("AppData\\Roaming", "AppData\\Local", "ProgramData")]
    for root, where in roots:
        for entry in _children(root):
            if not entry.is_dir(follow_symlinks=False) or entry.name.startswith((".", "{")):
                continue
            n = normalize(entry.name)
            if not n or n in SYSTEM_FOLDERS:
                continue
            if n in tokens or any(len(t) >= 4 and (t.startswith(n) or n.startswith(t)) for t in tokens if len(n) >= 4):
                continue
            try:
                if entry.stat(follow_symlinks=False).st_mtime > cutoff:
                    continue
            except OSError:
                continue
            if is_protected(entry.path, env):
                continue
            items.append(Item(
                path=entry.path, label=f"{entry.name}  ({where})", category="Unused app data",
                level=CHECK, size=folder_size(entry.path, limit_seconds=3),
                note="No installed app matches this folder. It is app data, not a cache, "
                     "so it won't come back. Remove it only if you won't reinstall that app.",
            ))
    return sorted(items, key=lambda i: -i.size)


# ============================================================================
# largefiles
# Large Files: big personal files in Desktop, Documents, Downloads, Videos,
# Music and Pictures (plus folders you add), downloaded AI models, and
# byte-for-byte duplicates. These are your files, so nothing here is ever
# "Safe": they are never part of Clean Safe Items or a scheduled clean.
#
# Skipped: hidden and system folders, project/dependency folders (Dev Tools
# handles those), links and junctions, cloud-only files (opening them would
# download them), and OneDrive/Dropbox folders (deleting there deletes from
# every device).
MB = 1024 * 1024
USER_FOLDERS = ("Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures")

# Cloud placeholders: reading them makes OneDrive download the file.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

KINDS = {
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".flv", ".ts"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".aiff", ".opus"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".raw", ".cr2", ".nef",
               ".arw", ".dng", ".psd", ".webp"},
    "PDFs": {".pdf"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".cab"},
    "Documents": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".csv", ".txt",
                  ".epub", ".key", ".pages"},
    "Installers": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle"},
    "Disk images and VMs": {".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2", ".wim", ".esd"},
    "AI models": {".gguf", ".safetensors", ".ggml", ".pt", ".pth", ".ckpt", ".onnx"},
}
UNFINISHED = {".crdownload", ".part", ".partial", ".download", ".opdownload", ".!ut", ".!qb", ".tmp"}
SKIP_DIRS = {"node_modules", "$recycle.bin", "system volume information", "appdata", "windowsapps",
             "onedrive", "dropbox", "google drive", "icloud drive", "icloudrive"} | set(PROJECT_JUNK)


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in UNFINISHED:
        return "Unfinished downloads"
    for kind, exts in KINDS.items():
        if ext in exts:
            return kind
    return "Other"


def label_of(name: str, kind: str, folder: str) -> tuple[str, str]:
    """(tag, explanation) for files that carry one."""
    ext = os.path.splitext(name)[1].lower()
    if kind == "Unfinished downloads":
        return "Unfinished download", "A download that never finished. The browser can't resume it once it's closed."
    if ext in (".iso", ".img", ".wim", ".esd"):
        return "Disk image", "An installer or disk image. Only needed to set up Windows, a PC or a virtual machine."
    if ext in (".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2"):
        return "Virtual machine", ("A virtual machine's disk. If its app is still installed, remove the VM in that app, "
                                   "which keeps its own list.")
    if kind == "Installers" and os.path.basename(folder).lower() == "downloads":
        return "Installer", "A setup file you downloaded. Once the app is installed you no longer need it."
    return "", ""


def _cloud_roots(env) -> set[str]:
    roots = set()
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if env.get(var):
            roots.add(os.path.normcase(os.path.normpath(env[var])))
    return roots


def default_roots(env=None) -> list[str]:
    env = os.environ if env is None else env
    out = []
    for name in USER_FOLDERS:
        p = known_folder(name, env)
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    return out


def scan_large_files(roots: list[str], min_size: int = 50 * MB, env=None, max_files: int = 20000) -> list[Item]:
    env = os.environ if env is None else env
    cloud = _cloud_roots(env)
    items, seen = [], set()
    for root in roots:
        source = os.path.basename(os.path.normpath(root)) or root
        stack = [root]
        while stack and len(items) < max_files:
            folder = stack.pop()
            key = os.path.normcase(os.path.normpath(folder))
            if key in seen or any(key == c or key.startswith(c + os.sep) for c in cloud):
                continue
            seen.add(key)
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            if any(e.name in (".dropbox", ".dropbox.cache") for e in entries):
                continue   # a Dropbox folder: deleting here deletes everywhere
            for e in entries:
                if is_link_or_junction(e) or e.name.startswith(("." , "~$")):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                if stat.S_ISDIR(st.st_mode):
                    if e.name.lower() not in SKIP_DIRS and not attrs & 0x4:  # 0x4 = system
                        stack.append(e.path)
                    continue
                if st.st_size < min_size or attrs & CLOUD_ONLY:
                    continue
                kind = kind_of(e.name)
                tag, note = label_of(e.name, kind, folder)
                items.append(Item(
                    path=e.path, label=e.name, category=kind, level=CHECK, size=st.st_size, note=note,
                    tab="large", mtime=st.st_mtime,
                    extra={"source": source, "folder": folder, "tag": tag,
                           "atime": max(st.st_atime, st.st_mtime)}))
    return items


# ---------------------------------------------------------------- AI models

def _ollama_models(env) -> list[Item]:
    """One row per Ollama model. A model's size counts only the blobs no other
    model uses, so removing it frees exactly that much."""
    base = env.get("OLLAMA_MODELS") or (env.get("USERPROFILE") and os.path.join(env["USERPROFILE"], ".ollama", "models"))
    if not base or not os.path.isdir(os.path.join(base, "manifests")):
        return []
    blobs_dir = os.path.join(base, "blobs")
    models: list[tuple[str, str, set[str]]] = []
    for dirpath, _, files in os.walk(os.path.join(base, "manifests")):
        for f in files:
            mf = os.path.join(dirpath, f)
            try:
                data = json.loads(Path(mf).read_text("utf-8"))
            except (OSError, ValueError):
                continue
            digests = {l["digest"] for l in data.get("layers", []) + [data.get("config", {})] if l.get("digest")}
            rel = Path(os.path.relpath(mf, os.path.join(base, "manifests"))).parts
            name = f"{rel[-2]}:{rel[-1]}" if len(rel) >= 2 else rel[-1]
            models.append((name, mf, digests))
    use_count: dict[str, int] = {}
    for _, _, ds in models:
        for d in ds:
            use_count[d] = use_count.get(d, 0) + 1
    items = []
    for name, mf, ds in models:
        own = [os.path.join(blobs_dir, d.replace(":", "-")) for d in ds if use_count[d] == 1]
        own = [p for p in own if os.path.exists(p)]
        size = sum(os.path.getsize(p) for p in own)
        if size < MB:
            continue
        items.append(Item(path=mf, label=name, category="AI models", level=CHECK, size=size, tab="large",
                          mtime=os.path.getmtime(mf),
                          note="Downloaded by Ollama. Ollama will still list it until you run "
                               f"“ollama rm {name}”; download it again with “ollama pull {name}”.",
                          extra={"source": "Ollama", "paths": [mf] + own, "tag": "AI model"}))
    return items


def _model_folders(env) -> list[tuple[str, str, str]]:
    """(folder holding one model per subfolder, source name, note)."""
    home = env.get("USERPROFILE", "")
    local = env.get("LOCALAPPDATA", "")
    appdata = env.get("APPDATA", "")
    hf = env.get("HF_HUB_CACHE") or (env.get("HF_HOME") and os.path.join(env["HF_HOME"], "hub")) or \
        os.path.join(home, ".cache", "huggingface", "hub")
    return [
        (hf, "Hugging Face", "Downloaded through the Hugging Face Hub. It downloads again the next time a program asks for it."),
        (os.path.join(home, ".lmstudio", "models"), "LM Studio", "LM Studio may still list it as installed."),
        (os.path.join(home, ".cache", "lm-studio", "models"), "LM Studio", "LM Studio may still list it as installed."),
        (os.path.join(local, "nomic.ai", "GPT4All"), "GPT4All", ""),
        (os.path.join(appdata, "Jan", "data", "models"), "Jan", ""),
        (os.path.join(home, "jan", "models"), "Jan", ""),
        (os.path.join(home, ".cache", "whisper"), "Whisper", ""),
        (os.path.join(home, ".cache", "torch", "hub", "checkpoints"), "PyTorch Hub", ""),
    ]


def scan_ai_models(env=None) -> list[Item]:
    env = os.environ if env is None else env
    items = _ollama_models(env)
    for folder, source, note in _model_folders(env):
        if not folder or not os.path.isdir(folder):
            continue
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            if is_link_or_junction(e) or e.name.startswith("."):
                continue
            size = folder_size(e.path, limit_seconds=5) if e.is_dir(follow_symlinks=False) else e.stat().st_size
            if size < 100 * MB:
                continue
            name = e.name
            if name.startswith("models--"):
                name = name[8:].replace("--", "/")
            items.append(Item(path=e.path, label=name, category="AI models", level=CHECK, size=size, tab="large",
                              mtime=e.stat(follow_symlinks=False).st_mtime, note=note,
                              extra={"source": source, "tag": "AI model"}))
    return items


# ---------------------------------------------------------------- duplicates

def _hash(path: str, limit: int | None = None) -> str | None:
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as f:
            remaining = limit
            while True:
                chunk = f.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(items: list[Item]) -> list[list[Item]]:
    """Groups of byte-for-byte identical files: same size, then same first
    64 KB, then the same full content. Only real files (not model folders)."""
    by_size: dict[int, list[Item]] = {}
    for it in items:
        if it.category != "AI models" and os.path.isfile(it.path):
            by_size.setdefault(it.size, []).append(it)
    groups = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_head: dict[str, list[Item]] = {}
        for it in same_size:
            h = _hash(it.path, 64 * 1024)
            if h:
                by_head.setdefault(h, []).append(it)
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            by_full: dict[str, list[Item]] = {}
            for it in same_head:
                h = _hash(it.path)
                if h:
                    by_full.setdefault(h, []).append(it)
            groups += [g for g in by_full.values() if len(g) > 1]
    return groups


def suggest_keeper(group: list[Item]) -> Item:
    """Keep the oldest copy (usually the original); on a tie, the shortest path."""
    return min(group, key=lambda i: (i.mtime, len(i.path)))


def mark_duplicates(items: list[Item]) -> list[list[Item]]:
    groups = find_duplicates(items)
    for n, g in enumerate(groups, 1):
        keep = suggest_keeper(g)
        for it in g:
            it.extra["dup_group"] = n
            it.extra["dup_keep"] = it is keep
    return groups


# ============================================================================
# clitools
# Command-line tools installed globally by npm, pipx, uv, Cargo or dotnet.
# They are removed by that manager's own uninstall command, which deletes them
# permanently (not to the Recycle Bin); the confirmation says so.
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
