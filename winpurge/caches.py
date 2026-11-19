"""App Caches and Dev Tools scans.

App Caches: Windows system junk, browser caches, and every app's own cache
folders (found automatically, merged into one row per app).
Dev Tools: developer tool caches, Android emulators and SDK images, Docker's
disk, and build/dependency folders in projects you haven't touched."""
from __future__ import annotations

import glob
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .common import CHECK, SAFE, Item, folder_size, is_link_or_junction, is_protected

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
