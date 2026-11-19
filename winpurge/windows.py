"""Windows integration: privacy settings, the right-click menu, starting the
watcher at sign-in, and the uninstall watcher itself."""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import app_data_dir, IS_WINDOWS, normalize
from .scan import App, list_installed_apps, UNINSTALL_KEY


# ============================================================================
# privacy
# Windows telemetry and privacy settings: read what this PC is set to, change
# it, and put back what it was. Uses the same registry values that
# Settings > Privacy & security writes, so changes show up there too.
#
# Every first change to a setting saves its original value, so
# "Restore my original settings" can undo everything WinPurge changed.
HKCU, HKLM = "HKCU", "HKLM"
DWORD, SZ = "dword", "sz"
DELETE = object()   # "value absent": Windows uses its built-in default


@dataclass(frozen=True)
class Write:
    hive: str
    path: str
    name: str
    value: object          # int, str, or DELETE
    type: str = DWORD


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    writes: tuple[Write, ...] = ()
    service_start: int | None = None   # for service settings: 2 auto, 3 manual, 4 disabled


@dataclass(frozen=True)
class Setting:
    key: str
    group: str
    title: str
    detail: str
    options: tuple[Option, ...]
    private: str               # key of the most private option
    admin: bool = False        # needs "Restart as administrator"
    service: str | None = None
    note: str = ""

    def option(self, key: str) -> Option:
        return next(o for o in self.options if o.key == key)


def _toggle(key, group, title, detail, hive, path, name, on=1, off=0, private="off", admin=False, note=""):
    """A setting stored as one on/off value. 'Windows default' removes the value."""
    return Setting(key, group, title, detail, (
        Option("on", "On", (Write(hive, path, name, on),)),
        Option("off", "Off", (Write(hive, path, name, off),)),
    ), private=private, admin=admin, note=note)


PRIV = r"Software\Microsoft\Windows\CurrentVersion\Privacy"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
DATACOLLECTION_POLICY = r"SOFTWARE\Policies\Microsoft\Windows\DataCollection"

SETTINGS: tuple[Setting, ...] = (
    # ---------------------------------------------------------- diagnostics
    Setting(
        "diagnostic_data", "Diagnostic data",
        "Diagnostic data sent to Microsoft",
        "Required sends basic device and error data. Optional adds which apps and websites you "
        "use, how features are used, and more detailed error reports.",
        (
            Option("required", "Required only", (Write(HKLM, DATACOLLECTION_POLICY, "AllowTelemetry", 1),)),
            Option("optional", "Optional (more data)", (Write(HKLM, DATACOLLECTION_POLICY, "AllowTelemetry", 3),)),
            Option("default", "Windows decides", (Write(HKLM, DATACOLLECTION_POLICY, "AllowTelemetry", DELETE),)),
        ),
        private="required", admin=True,
        note="Set as a policy, so Settings shows \"Some settings are managed by your organization\". "
             "Choose \"Windows decides\" to hand control back to Settings."),
    _toggle("tailored", "Diagnostic data", "Tailored experiences",
            "Lets Microsoft use your diagnostic data for personalised tips, ads and recommendations.",
            HKCU, PRIV, "TailoredExperiencesWithDiagnosticDataEnabled"),
    Setting(
        "feedback", "Diagnostic data", "Feedback requests",
        "How often Windows asks for your feedback.",
        (
            Option("never", "Never", (Write(HKCU, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0),
                                      Write(HKCU, r"Software\Microsoft\Siuf\Rules", "PeriodInNanoSeconds", DELETE))),
            Option("default", "Windows decides", (Write(HKCU, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", DELETE),
                                                  Write(HKCU, r"Software\Microsoft\Siuf\Rules", "PeriodInNanoSeconds", DELETE))),
        ),
        private="never"),
    Setting(
        "diagtrack", "Diagnostic data", "Telemetry service (Connected User Experiences and Telemetry)",
        "The background service, DiagTrack, that collects and uploads diagnostic data.",
        (
            Option("auto", "Running (Windows default)", service_start=2),
            Option("manual", "Starts only when needed", service_start=3),
            Option("disabled", "Disabled", service_start=4),
        ),
        private="disabled", admin=True, service="DiagTrack",
        note="Disabling it stops uploads but also the Diagnostic Data Viewer and some Windows "
             "Insider features. Set it back to Running if something depends on it."),
    # ---------------------------------------------------------- advertising & activity
    _toggle("advertising_id", "Ads and activity", "Advertising ID",
            "A per-user ID apps use to show you personalised ads.",
            HKCU, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled"),
    Setting(
        "activity_history", "Ads and activity", "Activity history",
        "Keeps a history of apps, files and websites you open on this PC.",
        (
            Option("on", "On", (Write(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", DELETE),
                                Write(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", DELETE))),
            Option("off", "Off", (Write(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", 0),
                                  Write(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "UploadUserActivities", 0))),
        ),
        private="off", admin=True),
    _toggle("app_launch_tracking", "Ads and activity", "Track app launches",
            "Windows records which apps you start to improve Start and search results.",
            HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "Start_TrackProgs"),
    Setting(
        "suggested_content", "Ads and activity", "Suggested content in Settings",
        "Shows suggestions and promotions inside the Settings app.",
        (
            Option("on", "On", tuple(Write(HKCU, CDM, f"SubscribedContent-{n}Enabled", 1) for n in (338393, 353694, 353696))),
            Option("off", "Off", tuple(Write(HKCU, CDM, f"SubscribedContent-{n}Enabled", 0) for n in (338393, 353694, 353696))),
        ),
        private="off"),
    _toggle("language_list", "Ads and activity", "Let websites see your language list",
            "Websites can read your language list to show local content.",
            HKCU, r"Control Panel\International\User Profile", "HttpAcceptLanguageOptOut",
            on=0, off=1),
    # ---------------------------------------------------------- typing, speech, location
    _toggle("inking_typing", "Typing, speech and location", "Improve inking and typing",
            "Sends what you type and write with a pen to Microsoft to improve recognition.",
            HKCU, r"Software\Microsoft\Input\TIPC", "Enabled"),
    _toggle("online_speech", "Typing, speech and location", "Online speech recognition",
            "Sends your voice to Microsoft's online speech service for dictation and voice typing.",
            HKCU, r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted"),
    Setting(
        "location", "Typing, speech and location", "Location for apps",
        "Lets apps you allow use your location.",
        (
            Option("on", "On", (Write(HKCU, CONSENT + r"\location", "Value", "Allow", SZ),)),
            Option("off", "Off", (Write(HKCU, CONSENT + r"\location", "Value", "Deny", SZ),)),
        ),
        private="off",
        note="Turning this off also stops Maps, Weather and Find my device from using your location."),
)


# ---------------------------------------------------------------- backends

class RegistryBackend:
    """The real Windows registry and Service Control Manager."""

    def __init__(self):
        import winreg
        self.w = winreg
        self.roots = {HKCU: winreg.HKEY_CURRENT_USER, HKLM: winreg.HKEY_LOCAL_MACHINE}

    def get(self, hive, path, name):
        try:
            with self.w.OpenKey(self.roots[hive], path, 0, self.w.KEY_READ | self.w.KEY_WOW64_64KEY) as k:
                return self.w.QueryValueEx(k, name)[0]
        except OSError:
            return DELETE

    def set(self, hive, path, name, value, type_):
        access = self.w.KEY_SET_VALUE | self.w.KEY_WOW64_64KEY
        if value is DELETE:
            try:
                with self.w.OpenKey(self.roots[hive], path, 0, access) as k:
                    self.w.DeleteValue(k, name)
            except FileNotFoundError:
                pass
            return
        with self.w.CreateKeyEx(self.roots[hive], path, 0, access) as k:
            kind = self.w.REG_DWORD if type_ == DWORD else self.w.REG_SZ
            self.w.SetValueEx(k, name, 0, kind, value)

    def service_start(self, name):
        v = self.get(HKLM, rf"SYSTEM\CurrentControlSet\Services\{name}", "Start")
        return None if v is DELETE else v

    def service_running(self, name):
        r = subprocess.run(["sc", "query", name], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return "RUNNING" in r.stdout

    def set_service(self, name, start):
        word = {2: "auto", 3: "demand", 4: "disabled"}[start]
        flags = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(["sc", "config", name, "start=", word], capture_output=True, text=True, creationflags=flags)
        if r.returncode != 0:
            raise OSError((r.stdout or r.stderr).strip() or f"sc config failed ({r.returncode})")
        if start == 4:
            subprocess.run(["sc", "stop", name], capture_output=True, creationflags=flags)
        elif start == 2:
            subprocess.run(["sc", "start", name], capture_output=True, creationflags=flags)


class FakeBackend:
    """In-memory registry for tests and for trying the logic off Windows."""

    def __init__(self, values=None, services=None):
        self.values = dict(values or {})
        self.services = dict(services or {})   # name -> start type
        self.fail_hklm = False

    def get(self, hive, path, name):
        return self.values.get((hive, path.lower(), name.lower()), DELETE)

    def set(self, hive, path, name, value, type_):
        if hive == HKLM and self.fail_hklm:
            raise PermissionError("Access is denied")
        k = (hive, path.lower(), name.lower())
        if value is DELETE:
            self.values.pop(k, None)
        else:
            self.values[k] = value

    def service_start(self, name):
        return self.services.get(name)

    def service_running(self, name):
        return self.services.get(name) == 2

    def set_service(self, name, start):
        if self.fail_hklm:
            raise PermissionError("Access is denied")
        self.services[name] = start


def default_backend():
    return RegistryBackend() if IS_WINDOWS else FakeBackend()


# ---------------------------------------------------------------- reading

def current_option(setting: Setting, backend) -> str | None:
    """Key of the option the PC matches now, or None if it's something else."""
    if setting.service:
        start = backend.service_start(setting.service)
        for o in setting.options:
            if o.service_start == start:
                return o.key
        return None
    for o in setting.options:
        if all(_same(backend.get(w.hive, w.path, w.name), w.value) for w in o.writes):
            return o.key
    # Nothing written yet means Windows' own default. Toggles default to On.
    if all(backend.get(w.hive, w.path, w.name) is DELETE for o in setting.options for w in o.writes):
        keys = [o.key for o in setting.options]
        return "default" if "default" in keys else "on" if "on" in keys else None
    return None


def _same(actual, wanted) -> bool:
    if wanted is DELETE or actual is DELETE:
        return actual is wanted
    return str(actual).lower() == str(wanted).lower()


@dataclass
class Status:
    setting: Setting
    current: str | None
    running: bool | None = None
    effective: str = ""     # what Windows actually uses when no policy is set

    @property
    def is_private(self) -> bool:
        return self.current == self.setting.private

    @property
    def label(self) -> str:
        if self.current is None:
            return "Custom"
        text = self.setting.option(self.current).label
        if self.effective:
            text += f" (now: {self.effective})"
        if self.running is not None:
            text += " (running now)" if self.running else " (stopped now)"
        return text


# Where the Settings app keeps the diagnostic data level when no policy is set.
SETTINGS_APP_DATACOLLECTION = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection"
TELEMETRY_LEVELS = {0: "Security", 1: "Required", 2: "Enhanced", 3: "Optional"}


def read_all(backend) -> list[Status]:
    out = []
    for s in SETTINGS:
        running = backend.service_running(s.service) if s.service else None
        st = Status(s, current_option(s, backend), running)
        if s.key == "diagnostic_data" and st.current == "default":
            level = backend.get(HKLM, SETTINGS_APP_DATACOLLECTION, "AllowTelemetry")
            st.effective = TELEMETRY_LEVELS.get(level, "Optional") if level is not DELETE else "Optional"
        out.append(st)
    return out


def windows_edition(backend) -> str:
    ed = backend.get(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "EditionID")
    return "" if ed is DELETE else str(ed)


# ---------------------------------------------------------------- changing

class Backup:
    """Original values, saved the first time WinPurge changes each one."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {"values": [], "services": {}}

    def remember(self, backend, setting: Setting, option: Option):
        if setting.service:
            if setting.service not in self.data["services"]:
                self.data["services"][setting.service] = backend.service_start(setting.service)
            return
        known = {(v["hive"], v["path"].lower(), v["name"].lower()) for v in self.data["values"]}
        for w in option.writes:
            if (w.hive, w.path.lower(), w.name.lower()) in known:
                continue
            old = backend.get(w.hive, w.path, w.name)
            self.data["values"].append({
                "hive": w.hive, "path": w.path, "name": w.name, "type": w.type,
                "value": None if old is DELETE else old, "absent": old is DELETE,
            })

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), "utf-8")

    @property
    def empty(self) -> bool:
        return not self.data["values"] and not self.data["services"]


@dataclass
class ApplyResult:
    changed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def apply(changes: dict[str, str], backend, backup: Backup, is_admin: bool) -> ApplyResult:
    """changes: setting key -> option key."""
    res = ApplyResult()
    by_key = {s.key: s for s in SETTINGS}
    for skey, okey in changes.items():
        s = by_key[skey]
        if s.admin and not is_admin:
            res.failed.append((s.title, "Needs administrator rights. Use Restart as administrator."))
            continue
        o = s.option(okey)
        try:
            backup.remember(backend, s, o)
            backup.save()   # saved before the change, so a crash can't lose the original
            if s.service:
                backend.set_service(s.service, o.service_start)
            else:
                for w in o.writes:
                    backend.set(w.hive, w.path, w.name, w.value, w.type)
            res.changed.append(s.title)
        except OSError as e:
            res.failed.append((s.title, str(e) or e.__class__.__name__))
    return res


def restore(backend, backup: Backup, is_admin: bool) -> ApplyResult:
    """Put back every original value WinPurge saved. Keeps the ones that fail."""
    res = ApplyResult()
    keep_values, keep_services = [], {}
    for v in backup.data["values"]:
        label = f'{v["hive"]}\\{v["path"]}\\{v["name"]}'
        if v["hive"] == HKLM and not is_admin:
            keep_values.append(v)
            res.failed.append((label, "Needs administrator rights."))
            continue
        try:
            backend.set(v["hive"], v["path"], v["name"], DELETE if v["absent"] else v["value"], v["type"])
            res.changed.append(label)
        except OSError as e:
            keep_values.append(v)
            res.failed.append((label, str(e)))
    for name, start in backup.data["services"].items():
        if start is None:
            continue
        if not is_admin:
            keep_services[name] = start
            res.failed.append((name, "Needs administrator rights."))
            continue
        try:
            backend.set_service(name, start)
            res.changed.append(f"{name} service")
        except OSError as e:
            keep_services[name] = start
            res.failed.append((name, str(e)))
    backup.data = {"values": keep_values, "services": keep_services}
    backup.save()
    return res


# ============================================================================
# shell
# Windows integration, all per-user (no administrator needed) and all off
# until you turn it on in Settings:
#
# - "Uninstall with WinPurge" in the right-click menu of programs (.exe) and
#   shortcuts (.lnk). On Windows 11 it's under "Show more options".
# - The uninstall watcher, started when you sign in (HKCU ...\Run).
#
# remove_integrations() turns everything off again; the uninstaller calls it.
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WinPurge Watcher"
MENU_KEYS = (r"Software\Classes\exefile\shell\WinPurge.Uninstall",
             r"Software\Classes\lnkfile\shell\WinPurge.Uninstall")
WATCHER_PID = "watcher.pid"


def self_command(*args: str) -> list[str]:
    """How to start WinPurge with `args`, installed or run from source.
    From source it uses pythonw.exe, so no console window opens."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    script = str(Path(__file__).resolve().parent.parent / "run_winpurge.pyw")
    return [w if os.path.exists(w) else exe, script, *args]


def launch(*args: str):
    """Start another WinPurge process, detached from this one."""
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0
    subprocess.Popen(self_command(*args), creationflags=flags, close_fds=True)


def _icon_path() -> str:
    return self_command()[0]


# ---------------------------------------------------------------- registry helpers

def _set(path: str, name: str, value: str):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _get(path: str, name: str) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _delete_tree(path: str):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    _delete_tree(path + "\\" + winreg.EnumKey(k, 0))
                except OSError:
                    break
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


# ---------------------------------------------------------------- right-click menu

def context_menu_enabled() -> bool:
    return IS_WINDOWS and _get(MENU_KEYS[0] + r"\command", "") is not None


def set_context_menu(enabled: bool):
    if not IS_WINDOWS:
        return
    for key in MENU_KEYS:
        if enabled:
            _set(key, "MUIVerb", "Uninstall with WinPurge")
            _set(key, "Icon", _icon_path())
            _set(key + r"\command", "", subprocess.list2cmdline(self_command("--uninstall")) + ' "%1"')
        else:
            _delete_tree(key)


# ---------------------------------------------------------------- watcher at sign-in

def watcher_enabled() -> bool:
    return IS_WINDOWS and _get(RUN_KEY, RUN_VALUE) is not None


def set_watcher(enabled: bool):
    if not IS_WINDOWS:
        return
    import winreg
    if enabled:
        _set(RUN_KEY, RUN_VALUE, subprocess.list2cmdline(self_command("--watch")))
        launch("--watch")   # start now too; a second copy exits by itself
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, RUN_VALUE)
        except OSError:
            pass
        stop_watcher()


def stop_watcher() -> bool:
    """Stop a running watcher. True if none is left running."""
    pid_file = app_data_dir() / WATCHER_PID
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return True
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        from .core import running_processes
        alive = any(p == pid for p, _ in running_processes())
    else:
        alive = False
    if not alive:
        try:
            pid_file.unlink()
        except OSError:
            pass
    return not alive


INSTALLER_ID = "{8F3C2A51-6D4E-4B8A-9E2F-5C1D7A3B9E40}_is1"


def own_uninstaller() -> str | None:
    """The command that uninstalls WinPurge, if it was installed with Setup."""
    if not IS_WINDOWS:
        return None
    return _get("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + INSTALLER_ID, "UninstallString")


def remove_integrations() -> list[str]:
    """Turn off everything WinPurge set up, and say what was turned off."""
    done = []
    if watcher_enabled() or (app_data_dir() / WATCHER_PID).exists():
        set_watcher(False)
        done.append("Uninstall watcher")
    if context_menu_enabled():
        set_context_menu(False)
        done.append("Right-click menu item")
    return done


# ---------------------------------------------------------------- shortcuts and matching

def shortcut_target(lnk: str) -> str | None:
    """The program a .lnk shortcut points to (reads the file directly)."""
    try:
        data = Path(lnk).read_bytes()
    except OSError:
        return None
    if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
        return None
    flags = struct.unpack_from("<I", data, 0x14)[0]
    pos = 0x4C
    if flags & 0x01:                      # HasLinkTargetIDList
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if not flags & 0x02:                  # HasLinkInfo
        return None
    info = pos
    header = struct.unpack_from("<I", data, info + 4)[0]
    base_off = struct.unpack_from("<I", data, info + 16)[0]
    if header >= 0x24:                    # Unicode path present
        uoff = struct.unpack_from("<I", data, info + 28)[0]
        if uoff:
            start = end = info + uoff
            while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                end += 2
            return data[start:end].decode("utf-16-le", "replace") or None
    if base_off:
        end = data.find(b"\x00", info + base_off)
        return data[info + base_off:end].decode("mbcs" if IS_WINDOWS else "latin-1", "replace") or None
    return None


def match_app(path: str, installed: list):
    """The installed app a program or shortcut belongs to, or None."""
    if path.lower().endswith(".lnk"):
        target = shortcut_target(path)
        by_name = normalize(Path(path).stem)
        if target:
            path = target
        else:
            return next((a for a in installed if a.norm == by_name), None)
    p = os.path.normcase(os.path.normpath(path))
    best = None
    for a in installed:
        for folder in (a.install_location, os.path.dirname(a.display_icon) if a.display_icon else ""):
            if not folder:
                continue
            f = os.path.normcase(os.path.normpath(folder))
            if p == f or p.startswith(f + os.sep):
                # The most specific folder wins (Program Files\Vendor\App over Program Files\Vendor).
                if best is None or len(f) > best[0]:
                    best = (len(f), a)
    if best:
        return best[1]
    stem = normalize(Path(path).stem)
    return next((a for a in installed if a.norm == stem), None)


# ============================================================================
# watcher
# The uninstall watcher: a small background process (no window) that notices
# when an app is uninstalled, however it was removed, and opens WinPurge with
# just that app's leftovers to review. It also reminds you when a scheduled
# clean is due. Off until you turn on "Review leftovers when an app is
# uninstalled" in Settings.
#
# It waits on Windows' own change notifications for the installed-apps registry
# keys, so it uses no CPU while nothing changes.
HANDLED_FILE = "handled-uninstalls.json"   # uninstalls WinPurge itself ran
HANDLED_FOR = 15 * 60


def encode_app(app: App) -> str:
    return base64.urlsafe_b64encode(json.dumps(dataclasses.asdict(app)).encode()).decode()


def decode_app(text: str) -> App:
    return App(**json.loads(base64.urlsafe_b64decode(text.encode())))


def mark_handled(app: App):
    """Called before WinPurge runs an uninstaller itself, so the watcher
    doesn't open a second review for the same app."""
    path = app_data_dir() / HANDLED_FILE
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    now = time.time()
    data = {k: t for k, t in data.items() if now - t < HANDLED_FOR}
    data[app.key_name] = now
    try:
        path.write_text(json.dumps(data), "utf-8")
    except OSError:
        pass


def recently_handled(app: App) -> bool:
    try:
        data = json.loads((app_data_dir() / HANDLED_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() - data.get(app.key_name, 0) < HANDLED_FOR


def removed_apps(before: list[App], after: list[App]) -> list[App]:
    still = {(a.key_name, a.norm) for a in after}
    return [a for a in before if (a.key_name, a.norm) not in still]


def run_watcher() -> int:
    if not IS_WINDOWS:
        return 1
    import ctypes
    import winreg
    from ctypes import wintypes

    from . import core

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32")
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateEventW.restype = wintypes.HANDLE
    k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
    k32.WaitForMultipleObjects.restype = wintypes.DWORD
    advapi.RegNotifyChangeKeyValue.argtypes = [wintypes.HKEY, wintypes.BOOL, wintypes.DWORD, wintypes.HANDLE, wintypes.BOOL]
    k32.CreateMutexW(None, False, "Local\\WinPurgeUninstallWatcher")
    if ctypes.get_last_error() == 183:     # ERROR_ALREADY_EXISTS: one is running
        return 0
    from .core import background_priority
    background_priority(whole_process=True)   # the watcher never competes for CPU or disk
    (app_data_dir() / WATCHER_PID).write_text(str(os.getpid()))

    REG_NOTIFY_CHANGE_NAME, REG_NOTIFY_CHANGE_LAST_SET = 0x1, 0x4
    sources = [(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
               (winreg.HKEY_CURRENT_USER, 0)]
    keys, events = [], []
    for root, view in sources:
        try:
            k = winreg.OpenKey(root, UNINSTALL_KEY, 0, winreg.KEY_NOTIFY | winreg.KEY_READ | view)
        except OSError:
            continue
        keys.append(k)
        events.append(k32.CreateEventW(None, False, False, None))

    def arm():
        for k, ev in zip(keys, events):
            advapi.RegNotifyChangeKeyValue(wintypes.HKEY(k.handle), True,
                                           REG_NOTIFY_CHANGE_NAME | REG_NOTIFY_CHANGE_LAST_SET, ev, True)

    if not events:
        return 1
    handles = (wintypes.HANDLE * len(events))(*events)
    snapshot = list_installed_apps()
    reminded_day = None
    arm()
    while True:
        # Sleeps until Windows reports a change; wakes every 30 minutes only to
        # see whether a scheduled clean is due.
        rc = k32.WaitForMultipleObjects(len(events), handles, False, 30 * 60_000)
        if rc < len(events):
            time.sleep(4)          # let the uninstaller finish removing its key
            arm()
            current = list_installed_apps()
            for app in removed_apps(snapshot, current):
                if not recently_handled(app):
                    launch("--leftovers", encode_app(app))
            snapshot = current
        else:
            # Is a scheduled clean due? Remind once a day.
            today = time.strftime("%Y-%m-%d")
            if reminded_day != today:
                s = core.Settings()
                if core.is_due(s.data):
                    launch("--clean-reminder")
                    reminded_day = today
