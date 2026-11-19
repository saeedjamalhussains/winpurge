"""What the user allowed WinPurge to do, chosen in the first-run setup.
Kept free of Tk so it can be tested anywhere."""
from __future__ import annotations

from dataclasses import dataclass

SETUP_VERSION = 3  # bump to show setup again when permissions change meaning


@dataclass(frozen=True)
class Permission:
    key: str
    title: str
    detail: str
    default: bool


PERMISSIONS: list[Permission] = [
    Permission(
        "read_apps", "Read installed apps and command-line tools",
        "Reads the same registry list that Settings > Apps shows, and asks npm, pipx, uv, Cargo and "
        "dotnet which tools they installed. Needed for the Uninstaller and to tell which leftover "
        "folders belong to apps that are still installed.",
        True),
    Permission(
        "scan_caches", "Look in cache, temporary and developer tool folders",
        "Reads folder sizes in Temp, Windows update and crash files, browser and app caches (never "
        "history, cookies or passwords), and developer tool caches such as npm and pip.",
        True),
    Permission(
        "scan_leftovers", "Look for files left by removed apps",
        "Reads folder names in AppData, ProgramData and Program Files after an uninstall, and "
        "finds app data folders unchanged for 90 days whose app is gone.",
        True),
    Permission(
        "scan_projects", "Look for build folders in your coding projects",
        "Finds node_modules, build and virtual environment folders in projects you haven't changed "
        "for a while, in your usual code folders and any you add in Settings.",
        True),
    Permission(
        "scan_large_files", "Look for large files in your folders",
        "Reads the names and sizes of big files in Desktop, Documents, Downloads, Videos, Music and "
        "Pictures, and compares same-size files to find exact duplicates. Files are never opened "
        "otherwise, and cloud-only OneDrive files are skipped.",
        True),
    Permission(
        "registry_cleanup", "Offer to remove an app's registry settings",
        "After an uninstall, offers the app's own keys under HKEY_CURRENT_USER\\Software. "
        "Each key is saved to a .reg backup file first, and is never ticked for you.",
        False),
    Permission(
        "privacy", "Show and change Windows privacy settings",
        "Shows what diagnostic data, ads, activity history, typing, speech and location settings "
        "this PC uses, and lets you change them from WinPurge. Nothing changes until you choose to, "
        "and your original settings are saved so you can restore them.",
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
