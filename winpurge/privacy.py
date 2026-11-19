"""Windows telemetry and privacy settings: read what this PC is set to, change
it, and put back what it was. Uses the same registry values that
Settings > Privacy & security writes, so changes show up there too.

Every first change to a setting saves its original value, so
"Restore my original settings" can undo everything WinPurge changed."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .common import IS_WINDOWS

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
