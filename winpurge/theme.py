"""Colours, fonts, icons and sizes for the WinPurge window, in light and dark."""
from __future__ import annotations

import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    sidebar: str
    card: str
    card_hover: str
    border: str
    divider: str
    text: str
    text2: str
    text3: str
    accent: str
    accent_hover: str
    accent_press: str
    accent_soft: str
    on_accent: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_hover: str
    danger_soft: str
    selection: str
    control: str
    control_hover: str
    track_off: str


LIGHT = Palette(
    "light", window="#F4F5F7", sidebar="#ECEEF2", card="#FFFFFF", card_hover="#F7F8FA",
    border="#E2E5EA", divider="#EAECEF", text="#1A1C20", text2="#5B616B", text3="#8A909A",
    accent="#2563EB", accent_hover="#1D55D6", accent_press="#1C47B3", accent_soft="#E9F0FE",
    on_accent="#FFFFFF", success="#15803D", success_soft="#E6F5EC", warning="#B45309",
    warning_soft="#FDF2E2", danger="#DC2626", danger_hover="#C21F1F", danger_soft="#FDECEC",
    selection="#E3ECFD", control="#F1F3F6", control_hover="#E7EAEF", track_off="#C9CED6",
)

DARK = Palette(
    "dark", window="#1B1C20", sidebar="#16171A", card="#24262B", card_hover="#2B2D33",
    border="#34373E", divider="#2F3137", text="#F1F2F4", text2="#B3B8C1", text3="#7F858F",
    accent="#4C8DFF", accent_hover="#6A9FFF", accent_press="#3A7AEB", accent_soft="#21304B",
    on_accent="#FFFFFF", success="#43BF73", success_soft="#1D3527", warning="#F2A54A",
    warning_soft="#3A2D1B", danger="#F26B6B", danger_hover="#FF8080", danger_soft="#3D2224",
    selection="#2A3A5C", control="#2E3036", control_hover="#373A41", track_off="#555A63",
)

P: Palette = LIGHT          # current palette; widgets read it when built
SCALE = 1.0                 # display scaling (1.0 = 100%)
FONT = "Segoe UI"
SEMIBOLD: str | None = None   # a real semibold family, if installed
ICON_FONT: str | None = None


def px(n: float) -> int:
    """Pixels scaled for the display (150% scaling makes 8 -> 12)."""
    return max(1, round(n * SCALE))


def windows_prefers_dark() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def init(root, mode: str = "system"):
    """Pick fonts, icon font, scaling and palette. Call once a Tk root exists,
    and again when the user changes the theme."""
    global P, SCALE, FONT, SEMIBOLD, ICON_FONT
    from tkinter import font as tkfont
    families = set(tkfont.families(root))
    for f in ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"):
        if f in families:
            FONT = f
            break
    SEMIBOLD = next((f for f in ("Segoe UI Variable Display Semib", "Segoe UI Semibold") if f in families), None)
    ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    dpi = root.winfo_fpixels("1i")
    SCALE = max(1.0, dpi / 96) if IS_WINDOWS else 1.0
    dark = windows_prefers_dark() if mode == "system" else mode == "dark"
    P = DARK if dark else LIGHT


def font(size: float, weight: str = "normal"):
    """size in points (Tk scales points for the display itself)."""
    if weight == "semibold":
        return (SEMIBOLD, round(size), "normal") if SEMIBOLD else (FONT, round(size), "bold")
    return (FONT, round(size), weight)


# Display fonts
def title_font():
    return font(20, "semibold")


def heading_font():
    return font(13, "semibold")


def body_font():
    return font(10)


def body_strong():
    return font(10, "semibold")


def caption_font():
    return font(9)


# ---------------------------------------------------------------- icons
# Segoe Fluent Icons (Windows 11) and Segoe MDL2 Assets (Windows 10) share
# these code points. Elsewhere a plain symbol stands in.
ICONS = {
    "home": ("", "⌂"),
    "apps": ("", "▦"),
    "clean": ("", "✨"),
    "privacy": ("", "⚿"),
    "settings": ("", "⚙"),
    "search": ("", "⌕"),
    "refresh": ("", "↻"),
    "delete": ("", "✖"),
    "folder": ("", "▤"),
    "add": ("", "+"),
    "check": ("", "✓"),
    "close": ("", "✕"),
    "info": ("", "ⓘ"),
    "warning": ("", "⚠"),
    "shield": ("", "⛨"),
    "drive": ("", "▭"),
    "sparkle": ("", "✦"),
    "chevron_down": ("", "▾"),
    "chevron_right": ("", "›"),
    "open": ("", "↗"),
    "undo": ("", "↶"),
    "offline": ("", "⊘"),
    "recycle": ("", "♻"),
    "lock": ("", "⚿"),
    "admin": ("", "⛨"),
    "code": ("\uE943", "\u2039\u203A"),
    "history": ("\uE81C", "\u29D6"),
    "copy": ("\uE8C8", "\u2750"),
    "terminal": ("\uE756", "\u276F"),
}


def icon(name: str) -> str:
    glyph, fallback = ICONS[name]
    return glyph if ICON_FONT else fallback


def icon_font(size: float = 12):
    return (ICON_FONT, round(size)) if ICON_FONT else (FONT, round(size))


def set_dark_title_bar(window, dark: bool):
    """Match the Windows title bar to the theme (Windows 10 2004+ / 11)."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except (AttributeError, OSError):
        pass
