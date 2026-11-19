"""What the user allowed WinPurge to do, chosen in the first-run setup.
Kept free of Tk so it can be tested anywhere."""
from __future__ import annotations

from dataclasses import dataclass

SETUP_VERSION = 1  # bump to show setup again when permissions change meaning


@dataclass(frozen=True)
class Permission:
    key: str
    title: str
    detail: str
    default: bool


PERMISSIONS: list[Permission] = [
    Permission(
        "read_apps", "Read the list of installed apps",
        "Reads the same registry list that Settings > Apps shows. Needed for the Apps tab and "
        "to tell which leftover folders belong to apps that are still installed.",
        True),
    Permission(
        "scan_caches", "Look in cache and temporary folders",
        "Reads folder sizes in Temp, browser caches (never history, cookies or passwords), "
        "and developer tool caches such as npm and pip. Nothing is removed without you ticking it.",
        True),
    Permission(
        "scan_leftovers", "Look for files left by removed apps",
        "Reads folder names in AppData, ProgramData and Program Files after an uninstall, and "
        "finds app data folders unchanged for 90 days whose app is gone.",
        True),
    Permission(
        "scan_projects", "Look inside project folders you choose",
        "Finds node_modules, build and cache folders in coding projects you haven't edited "
        "for 30 days. Only inside the folders you pick on the next page.",
        False),
    Permission(
        "registry_cleanup", "Offer to remove an app's registry settings",
        "After an uninstall, offers the app's own keys under HKEY_CURRENT_USER\\Software. "
        "Each key is saved to a .reg backup file first, and is never ticked for you.",
        False),
]

PERMISSION_KEYS = {p.key for p in PERMISSIONS}


def defaults() -> dict[str, bool]:
    return {p.key: p.default for p in PERMISSIONS}


def needs_setup(settings: dict) -> bool:
    return settings.get("setup_version", 0) < SETUP_VERSION


def allowed(settings: dict, key: str) -> bool:
    """Before setup is finished nothing is allowed."""
    if key not in PERMISSION_KEYS:
        raise KeyError(key)
    if needs_setup(settings):
        return False
    return bool(settings.get("permissions", {}).get(key, False))


def complete_setup(settings: dict, chosen: dict[str, bool], project_roots: list[str]) -> dict:
    unknown = set(chosen) - PERMISSION_KEYS
    if unknown:
        raise KeyError(", ".join(sorted(unknown)))
    perms = defaults()
    perms.update({k: bool(v) for k, v in chosen.items()})
    settings["permissions"] = perms
    settings["project_roots"] = list(project_roots) if perms["scan_projects"] else []
    settings["setup_version"] = SETUP_VERSION
    return settings


SAFETY_POINTS = [
    ("Works offline",
     "WinPurge never connects to the internet. It sends no data, has no updates or analytics, "
     "and opens no network ports, so Windows Firewall has nothing to block and needs no rule."),
    ("Asks before removing anything",
     "Scans only read. Nothing moves until you tick it and confirm."),
    ("Uses the Recycle Bin",
     "Files and folders go to the Recycle Bin, so you can restore them until you empty it. "
     "Registry settings are backed up to a .reg file first."),
    ("Leaves Windows alone",
     "The Windows folder, Program Files, ProgramData, AppData and your user folder themselves "
     "can never be removed."),
    ("Runs without administrator rights",
     "Only folders an administrator installed need it. WinPurge asks for it only when you press "
     "Restart as administrator."),
]
