"""Look and feel: colours, fonts and icons, drawn graphics (anti-aliased shapes,
the logo), and the widget kit every page is built from."""
from __future__ import annotations

import base64
import math
import struct
import sys
import tkinter as tk
import zlib
from dataclasses import dataclass
from tkinter import ttk



# ============================================================================
# theme
# Colours, fonts, icons and sizes for the WinPurge window, in light and dark.
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


# ============================================================================
# gfx
# Pixel graphics made in code: smooth (anti-aliased) rounded corners,
# circles, check boxes and the WinPurge logo. Tk's canvas has no
# anti-aliasing on Windows, so smooth curves are drawn as small PNG images.
# Pure Python: a tiny PNG/ICO writer, no image files or libraries.
SS = 4  # supersampling per axis


# ---------------------------------------------------------------- encoders

def png_bytes(w: int, h: int, rgba: bytearray) -> bytes:
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))



def ico_bytes(pngs: list[tuple[int, bytes]]) -> bytes:
    """ICO file holding PNG images (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        s = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    return header + entries + blobs


# ---------------------------------------------------------------- helpers

def hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _render(w, h, sample) -> bytearray:
    """sample(x, y) -> (r, g, b, a) floats 0..1 at a sub-pixel point.
    Averages SS*SS samples per pixel with premultiplied alpha."""
    out = bytearray(w * h * 4)
    n = SS * SS
    offs = [(i + 0.5) / SS for i in range(SS)]
    i = 0
    for py in range(h):
        for px in range(w):
            r = g = b = a = 0.0
            for oy in offs:
                for ox in offs:
                    sr, sg, sb, sa = sample(px + ox, py + oy)
                    r += sr * sa
                    g += sg * sa
                    b += sb * sa
                    a += sa
            if a > 0:
                out[i] = min(255, round(r / a * 255))
                out[i + 1] = min(255, round(g / a * 255))
                out[i + 2] = min(255, round(b / a * 255))
                out[i + 3] = min(255, round(a / n * 255))
            i += 4
    return out


def _rgbf(c):
    r, g, b = hex_rgb(c)
    return r / 255, g / 255, b / 255


# ---------------------------------------------------------------- shapes

def corner(radius: int, fill: str, outline: str | None, which: str) -> tuple[int, int, bytearray]:
    """One quarter of a rounded rectangle. which: 'nw', 'ne', 'sw', 'se'."""
    r = radius
    fr = _rgbf(fill)
    ol = _rgbf(outline) if outline else None
    cx = r if "w" in which else 0
    cy = r if "n" in which else 0

    def sample(x, y):
        dx = (cx - x) if "w" in which else (x - cx)
        dy = (cy - y) if "n" in which else (y - cy)
        if dx <= 0 or dy <= 0:
            d = max(dx, dy, 0)
        else:
            d = math.hypot(dx, dy)
        if d > r:
            return (0, 0, 0, 0)
        if ol and d > r - 1:
            return (*ol, 1)
        return (*fr, 1)
    return r, r, _render(r, r, sample)


def circle(diameter: int, fill: str, outline: str | None = None, ring: float = 1.0):
    d = diameter
    c = d / 2
    fr = _rgbf(fill)
    ol = _rgbf(outline) if outline else None

    def sample(x, y):
        dist = math.hypot(x - c, y - c)
        if dist > c:
            return (0, 0, 0, 0)
        if ol and dist > c - ring:
            return (*ol, 1)
        return (*fr, 1)
    return d, d, _render(d, d, sample)


def checkbox(size: int, checked: bool, accent: str, border: str, fill: str, mark: str = "#FFFFFF"):
    """A rounded check box, ticked or not."""
    s = size
    r = max(3, s // 5)
    bfill = _rgbf(accent if checked else fill)
    bline = _rgbf(accent if checked else border)
    m = _rgbf(mark)
    # Tick: two segments, in box coordinates 0..1
    p1, p2, p3 = (0.25, 0.52), (0.43, 0.70), (0.76, 0.34)
    width = 0.09

    def seg_dist(px, py, a, b):
        ax, ay = a
        bx, by = b
        vx, vy = bx - ax, by - ay
        t = max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
        return math.hypot(px - ax - t * vx, py - ay - t * vy)

    def inside_round(x, y, inset):
        lo, hi = inset, s - inset
        rr = r - inset
        cx = min(max(x, lo + rr), hi - rr)
        cy = min(max(y, lo + rr), hi - rr)
        return math.hypot(x - cx, y - cy) <= rr and lo <= x <= hi and lo <= y <= hi

    def sample(x, y):
        if not inside_round(x, y, 0.5):
            return (0, 0, 0, 0)
        if checked:
            u, v = x / s, y / s
            if min(seg_dist(u, v, p1, p2), seg_dist(u, v, p2, p3)) < width:
                return (*m, 1)
            return (*bfill, 1)
        if not inside_round(x, y, 1.75):
            return (*bline, 1)
        return (*bfill, 1)
    return s, s, _render(s, s, sample)


def logo(size: int, top: str = "#3B82F6", bottom: str = "#06B6D4") -> tuple[int, int, bytearray]:
    """WinPurge logo: a soft square with a blue-to-cyan gradient and two
    white sparkles."""
    s = size
    r = s * 0.24
    c1, c2 = _rgbf(top), _rgbf(bottom)

    def astroid(x, y, cx, cy, rad):
        dx, dy = abs(x - cx) / rad, abs(y - cy) / rad
        return dx ** (2 / 3) + dy ** (2 / 3) <= 1 if dx <= 1 and dy <= 1 else False

    def sample(x, y):
        # rounded square
        cx = min(max(x, r), s - r)
        cy = min(max(y, r), s - r)
        if math.hypot(x - cx, y - cy) > r:
            return (0, 0, 0, 0)
        if astroid(x, y, s * 0.44, s * 0.56, s * 0.30) or astroid(x, y, s * 0.72, s * 0.27, s * 0.13):
            return (1, 1, 1, 1)
        t = (x + y) / (2 * s)
        return (c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t, c1[2] + (c2[2] - c1[2]) * t, 1)
    return s, s, _render(s, s, sample)


def write_ico(path: str, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)):
    pngs = []
    for sz in sizes:
        w, h, px = logo(sz)
        pngs.append((sz, png_bytes(w, h, px)))
    with open(path, "wb") as f:
        f.write(ico_bytes(pngs))


def write_build_files(folder: str):
    """For build.bat: the app icon and WinPurge.exe's file details (Right-click >
    Properties > Details), both made from the code so nothing is kept in sync by hand."""
    import os
    from . import __version__
    os.makedirs(folder, exist_ok=True)
    write_ico(os.path.join(folder, "winpurge.ico"))
    nums = tuple(int(n) for n in (__version__.split(".") + ["0", "0", "0"])[:4])
    strings = {"CompanyName": "WinPurge", "FileDescription": "WinPurge: app uninstaller, cleaner and privacy settings",
               "FileVersion": __version__, "InternalName": "WinPurge", "OriginalFilename": "WinPurge.exe",
               "ProductName": "WinPurge", "ProductVersion": __version__}
    table = ",\n".join(f"      StringStruct('{k}', '{v}')" for k, v in strings.items())
    text = (f"VSVersionInfo(\n  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,\n"
            "                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
            f"  kids=[\n    StringFileInfo([StringTable('040904B0', [\n{table},\n    ])]),\n"
            "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)\n")
    with open(os.path.join(folder, "version_info.txt"), "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- Tk images

_FONTS: dict = {}
_WIDTHS: dict = {}


def text_width(font_spec, text: str) -> int:
    """Width of text in pixels. One Tk font object per font, and each result
    is remembered, so redrawing a button never creates a font again."""
    key = (font_spec, text)
    w = _WIDTHS.get(key)
    if w is None:
        f = _FONTS.get(font_spec)
        if f is None:
            from tkinter import font as tkfont
            f = _FONTS[font_spec] = tkfont.Font(font=font_spec)
        w = _WIDTHS[key] = f.measure(text) if text else 0
    return w


class ImageCache:
    """Keeps PhotoImages alive (Tk drops images that Python forgets)."""

    VERSION = "1"   # bump when a shape's drawing code changes

    def __init__(self):
        self._cache: dict = {}
        self._dir = None

    def _folder(self):
        if self._dir is None:
            import os
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
            self._dir = os.path.join(base, "WinPurge", "cache", "gfx")
            try:
                os.makedirs(self._dir, exist_ok=True)
            except OSError:
                self._dir = ""
        return self._dir

    def get(self, key, make):
        """A PhotoImage for `key`. Drawn once ever: after the first launch it's
        read from a small PNG on disk instead of being drawn pixel by pixel."""
        img = self._cache.get(key)
        if img is None:
            import hashlib
            import os
            import tkinter as tk
            folder = self._folder()
            name = hashlib.sha1(repr((self.VERSION, key)).encode()).hexdigest() + ".png"
            path = os.path.join(folder, name) if folder else ""
            if path and os.path.exists(path):
                try:
                    img = tk.PhotoImage(file=path)
                except tk.TclError:
                    img = None
            if img is None:
                w, h, pixels = make()
                data = png_bytes(w, h, pixels)
                img = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
                if path:
                    try:
                        with open(path, "wb") as f:
                            f.write(data)
                    except OSError:
                        pass
            self._cache[key] = img
        return img

    def clear(self):
        self._cache.clear()


IMAGES = ImageCache()


def corner_img(radius, fill, outline, which):
    return IMAGES.get(("corner", radius, fill, outline, which), lambda: corner(radius, fill, outline, which))


def circle_img(d, fill, outline=None):
    return IMAGES.get(("circle", d, fill, outline), lambda: circle(d, fill, outline))


def checkbox_img(size, checked, accent, border, fill):
    return IMAGES.get(("check", size, checked, accent, border, fill), lambda: checkbox(size, checked, accent, border, fill))


def logo_img(size):
    return IMAGES.get(("logo", size), lambda: logo(size))


# ============================================================================
# widgets
# WinPurge's widget kit: rounded cards, buttons, toggles, drop-downs, a search
# box, progress bars, badges, a scrolling area, a check-box table, dialogs and
# toasts. All drawn on Tk canvases with the current theme palette.
def rounded_rect(cv: tk.Canvas, x0, y0, x1, y1, r, fill, outline=None, tag="bg"):
    """Smooth rounded rectangle: flat rectangles plus anti-aliased corner images."""
    w, h = x1 - x0, y1 - y0
    r = max(1, min(r, w // 2, h // 2))
    cv.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, width=0, tags=tag)
    cv.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, width=0, tags=tag)
    if outline:
        cv.create_line(x0 + r, y0, x1 - r, y0, fill=outline, tags=tag)
        cv.create_line(x0 + r, y1 - 1, x1 - r, y1 - 1, fill=outline, tags=tag)
        cv.create_line(x0, y0 + r, x0, y1 - r, fill=outline, tags=tag)
        cv.create_line(x1 - 1, y0 + r, x1 - 1, y1 - r, fill=outline, tags=tag)
    for which, x, y, anchor in (("nw", x0, y0, "nw"), ("ne", x1, y0, "ne"),
                                ("sw", x0, y1, "sw"), ("se", x1, y1, "se")):
        cv.create_image(x, y, image=corner_img(r, fill, outline, which), anchor=anchor, tags=tag)


def bg_of(widget) -> str:
    try:
        return widget.cget("bg")
    except tk.TclError:
        return P.window


def label(parent, text="", kind="body", color=None, wrap=0, **kw):
    fonts = {"title": title_font(), "heading": heading_font(), "body": body_font(),
             "strong": body_strong(), "caption": caption_font(),
             "display": font(26, "semibold"), "big": font(16, "semibold")}
    colors = {"caption": P.text2}
    return tk.Label(parent, text=text, font=fonts[kind], fg=color or colors.get(kind, P.text),
                    bg=bg_of(parent), wraplength=wrap, justify="left", anchor="w", **kw)


def icon_label(parent, name, size=14, color=None, **kw):
    return tk.Label(parent, text=icon(name), font=icon_font(size), fg=color or P.text2,
                    bg=bg_of(parent), **kw)


# ---------------------------------------------------------------- Card

class Card(tk.Canvas):
    """Rounded panel. Put children in .body. With stretch=True the body
    fills the card's height (for tables); otherwise the card fits its body."""

    def __init__(self, parent, padding=16, radius=8, fill=None, outline="", stretch=False, fit_width=False, **kw):
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0, height=px(40), **kw)
        self.fill = fill or P.card
        self.outline = P.border if outline == "" else outline
        self.pad = px(padding)
        self.radius = px(radius)
        self.stretch = stretch
        self.fit_width = fit_width
        self.body = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(self.pad, self.pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._redraw)
        if not stretch:
            self.body.bind("<Configure>", self._fit)

    def _redraw(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        self.delete("bg")
        rounded_rect(self, 0, 0, w, h, self.radius, self.fill, self.outline)
        self.tag_lower("bg")
        if not self.fit_width:
            self.itemconfigure(self._win, width=max(1, w - 2 * self.pad))
        if self.stretch:
            self.itemconfigure(self._win, height=max(1, h - 2 * self.pad))

    def _fit(self, e=None):
        h = self.body.winfo_reqheight() + 2 * self.pad
        if self.winfo_reqheight() != h:
            self.configure(height=h)
        if self.fit_width:
            w = self.body.winfo_reqwidth() + 2 * self.pad
            if self.winfo_reqwidth() != w:
                self.configure(width=w)

    def set_colors(self, fill=None, outline=None):
        if fill:
            self.fill = fill
            self.body.configure(bg=fill)
        if outline is not None:
            self.outline = outline
        self._redraw()


# ---------------------------------------------------------------- Button

class Button(tk.Canvas):
    KINDS = ("primary", "secondary", "subtle", "danger")

    def __init__(self, parent, text="", icon=None, kind="secondary", command=None,
                 height=32, min_width=0, tooltip=None):
        self._bgc = bg_of(parent)
        super().__init__(parent, bg=self._bgc, highlightthickness=0, bd=0, height=px(height),
                         cursor="hand2", takefocus=1)
        self.text, self.icon, self.kind, self.command = text, icon, kind, command
        self.min_width = px(min_width)
        self.state_ = "normal"     # normal, hover, press
        self.disabled = False
        self.focused = False
        self._font = body_strong() if kind in ("primary", "danger", "link") else body_font()
        self._measure()
        for ev, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                       ("<ButtonPress-1>", self._press), ("<ButtonRelease-1>", self._release),
                       ("<FocusIn>", self._focus_in), ("<FocusOut>", self._focus_out),
                       ("<Return>", self._key), ("<space>", self._key)):
            self.bind(ev, fn)
        self.bind("<Configure>", lambda e: self._draw())

    def _measure(self):
        tw = text_width(self._font, self.text)
        iw = px(16) if self.icon else 0
        gap = px(8) if self.icon and self.text else 0
        pad = 0 if self.kind == "link" else px(16) if self.text else px(8)
        self.configure(width=max(self.min_width, tw + iw + gap + 2 * pad))

    def _colors(self):
        if self.disabled:
            return P.control, P.text3, None
        k, s = self.kind, self.state_
        if k == "primary":
            return {"normal": P.accent, "hover": P.accent_hover, "press": P.accent_press}[s], P.on_accent, None
        if k == "danger":
            return {"normal": P.danger, "hover": P.danger_hover, "press": P.danger}[s], "#FFFFFF", None
        if k == "link":
            return self._bgc, {"normal": P.accent, "hover": P.accent_hover, "press": P.accent_press}[s], None
        if k == "subtle":
            return {"normal": self._bgc, "hover": P.control_hover, "press": P.control}[s], P.text, None
        return {"normal": P.card, "hover": P.card_hover, "press": P.control}[s], P.text, P.border

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        fill, fg, outline = self._colors()
        if self.focused and not self.disabled:
            outline = P.accent
        if self.kind != "link":
            rounded_rect(self, 0, 0, w, h, px(6), fill, outline)
        tw = text_width(self._font, self.text)
        iw = px(16) if self.icon else 0
        gap = px(8) if self.icon and self.text else 0
        x = (w - (tw + iw + gap)) / 2
        if self.icon:
            self.create_text(x + iw / 2, h / 2, text=icon(self.icon), font=icon_font(11), fill=fg)
            x += iw + gap
        if self.text:
            self.create_text(x, h / 2, text=self.text, font=self._font, fill=fg, anchor="w")

    def _enter(self, e):
        if not self.disabled:
            self.state_ = "hover"
            self._draw()

    def _leave(self, e):
        self.state_ = "normal"
        self._draw()

    def _press(self, e):
        if not self.disabled:
            self.state_ = "press"
            self._draw()

    def _release(self, e):
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        self.state_ = "hover" if inside else "normal"
        self._draw()
        if inside and not self.disabled and self.command:
            self.command()

    def _key(self, e):
        if not self.disabled and self.command:
            self.command()

    def _focus_in(self, e):
        self.focused = True
        self._draw()

    def _focus_out(self, e):
        self.focused = False
        self._draw()

    def set_disabled(self, disabled: bool):
        self.disabled = disabled
        self.configure(cursor="arrow" if disabled else "hand2")
        self._draw()

    def set_text(self, text):
        self.text = text
        self._measure()
        self._draw()


# ---------------------------------------------------------------- Toggle

class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None):
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0,
                         width=px(40), height=px(20), cursor="hand2", takefocus=1)
        self.value, self.command, self.disabled = value, command, False
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<space>", self._click)
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        self.delete("all")
        w, h = px(40), px(20)
        if self.disabled:
            track, knob, outline = P.control, P.text3, P.border
        elif self.value:
            track, knob, outline = P.accent, "#FFFFFF", None
        else:
            track, knob, outline = P.card, P.text2, P.text3
        rounded_rect(self, 0, 0, w, h, h // 2, track, outline)
        d = h - px(8) if not self.value else h - px(6)
        cx = w - h / 2 if self.value else h / 2
        self.create_image(cx, h / 2, image=circle_img(d, knob))

    def _click(self, e=None):
        if self.disabled:
            return
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)

    def set(self, value: bool):
        self.value = value
        self._draw()

    def set_disabled(self, disabled: bool):
        self.disabled = disabled
        self.configure(cursor="arrow" if disabled else "hand2")
        self._draw()


# ---------------------------------------------------------------- Dropdown

class Dropdown(Button):
    """A button showing the current choice; click for a menu of options."""

    def __init__(self, parent, options: list[tuple[str, str]], value: str | None, command=None, min_width=180):
        self.options = options
        self.value = value
        self.on_pick = command
        super().__init__(parent, text=self._label(), icon=None, kind="secondary",
                         command=self._open, min_width=min_width)

    def _label(self):
        return next((lbl for key, lbl in self.options if key == self.value), "Custom")

    def _draw(self):
        # Left-aligned text with a chevron on the right.
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if w < 4:
            return
        fill, fg, outline = self._colors()
        if self.focused and not self.disabled:
            outline = P.accent
        rounded_rect(self, 0, 0, w, h, px(6), fill, outline)
        self.create_text(px(12), h / 2, text=self.text, font=self._font, fill=fg, anchor="w")
        self.create_text(w - px(14), h / 2, text=icon("chevron_down"), font=icon_font(9),
                         fill=P.text2 if not self.disabled else P.text3)

    def _measure(self):
        widest = max((text_width(self._font, lbl) for _, lbl in getattr(self, "options", [])),
                     default=text_width(self._font, self.text))
        self.configure(width=max(self.min_width, widest + px(48)))

    def _open(self):
        m = tk.Menu(self, tearoff=0, bg=P.card, fg=P.text, activebackground=P.selection,
                    activeforeground=P.text, bd=0, relief="flat", font=body_font())
        var = tk.StringVar(value=self.value or "")
        for key, lbl in self.options:
            m.add_radiobutton(label=lbl, value=key, variable=var, command=lambda k=key: self._pick(k))
        m.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + px(2))

    def _pick(self, key):
        if key == self.value:
            return
        self.value = key
        self.set_text(self._label())
        if self.on_pick:
            self.on_pick(key)


# ---------------------------------------------------------------- Search box

class SearchBox(Card):
    def __init__(self, parent, placeholder="Search", command=None, width=260):
        super().__init__(parent, padding=0, radius=6, fill=P.card, outline=P.border)
        self.configure(width=px(width), height=px(34))
        self.placeholder = placeholder
        self.var = tk.StringVar()
        self.body.configure(padx=px(4))
        icon_label(self.body, "search", 10, P.text3).pack(side="left")
        self.entry = tk.Entry(self.body, textvariable=self.var, bd=0, highlightthickness=0, relief="flat",
                              bg=P.card, fg=P.text3, insertbackground=P.text, font=body_font())
        self.entry.pack(side="left", fill="x", expand=True, padx=(px(8), 0), pady=px(7))
        self.entry.insert(0, placeholder)
        self._showing_placeholder = True
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<Escape>", lambda e: self.clear())
        self.var.trace_add("write", lambda *_: command(self.get()) if command and not self._showing_placeholder else None)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.delete("bg")
        rounded_rect(self, 0, 0, w, h, self.radius, self.fill, self.outline)
        self.tag_lower("bg")
        inset = self.radius
        self.itemconfigure(self._win, width=w - 2 * inset, height=h - 2)
        self.coords(self._win, inset, 1)

    def _focus_in(self, e):
        if self._showing_placeholder:
            self._showing_placeholder = False
            self.entry.delete(0, "end")
            self.entry.configure(fg=P.text)
        self.set_colors(outline=P.accent)

    def _focus_out(self, e):
        if not self.entry.get():
            self._showing_placeholder = True
            self.entry.insert(0, self.placeholder)
            self.entry.configure(fg=P.text3)
        self.set_colors(outline=P.border)

    def get(self) -> str:
        return "" if self._showing_placeholder else self.var.get()

    def clear(self):
        if not self._showing_placeholder:
            self.var.set("")


# ---------------------------------------------------------------- Progress

class ProgressBar(tk.Canvas):
    def __init__(self, parent, height=6, color=None):
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0, height=px(height))
        self.value, self.color = 0.0, color
        self._anim = None
        self._pos = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        rounded_rect(self, 0, 0, w, h, h // 2, P.divider)
        color = self.color or P.accent
        if self._anim:
            seg = w * 0.3
            x = (self._pos % 1.3 - 0.3) * w
            x0, x1 = max(0, x), min(w, x + seg)
            if x1 - x0 > h:
                rounded_rect(self, int(x0), 0, int(x1), h, h // 2, color)
        elif self.value > 0:
            rounded_rect(self, 0, 0, max(h, int(w * min(1, self.value))), h, h // 2, color)

    def set(self, value: float, color=None):
        self.stop()
        self.value = value
        if color:
            self.color = color
        self._draw()

    def start(self):
        if self._anim:
            return

        # 25 frames a second is smooth enough for a bar, and it doesn't draw
        # at all while its page is hidden.
        def step():
            self._pos += 0.03
            if self.winfo_ismapped():
                self._draw()
            self._anim = self.after(40, step)
        self._anim = self.after(40, step)

    def stop(self):
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        self._draw()


# ---------------------------------------------------------------- Badge

class Badge(tk.Canvas):
    def __init__(self, parent, text, kind="neutral"):
        colors = {"success": (P.success_soft, P.success), "warning": (P.warning_soft, P.warning),
                  "accent": (P.accent_soft, P.accent), "danger": (P.danger_soft, P.danger),
                  "neutral": (P.control, P.text2)}
        self.fill, self.fg = colors[kind]
        f = font(8, "semibold")
        w = text_width(f, text) + px(16)
        super().__init__(parent, bg=bg_of(parent), highlightthickness=0, bd=0, width=w, height=px(20))
        rounded_rect(self, 0, 0, w, px(20), px(10), self.fill)
        self.create_text(w / 2, px(10), text=text, font=f, fill=self.fg)


# ---------------------------------------------------------------- Scroll area

class ScrollFrame(tk.Frame):
    """A vertically scrolling area. Put children in .inner."""

    def __init__(self, parent, bg=None):
        bg = bg or bg_of(parent)
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="WP.Vertical.TScrollbar")
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._update)
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width), self._update()))
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def _update(self, e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height()
        if need and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y")
        elif not need and self.bar.winfo_ismapped():
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def _wheel(self, e):
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        step = -int(e.delta / 120) if abs(e.delta) >= 120 else -e.delta
        self.canvas.yview_scroll(step, "units")


# ---------------------------------------------------------------- ttk styles

def apply_ttk_styles(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("WP.Treeview", background=P.card, fieldbackground=P.card, foreground=P.text,
                rowheight=px(36), borderwidth=0, relief="flat", font=body_font())
    s.map("WP.Treeview", background=[("selected", P.selection)], foreground=[("selected", P.text)])
    s.layout("WP.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("WP.Treeview.Heading", background=P.card, foreground=P.text2, relief="flat",
                borderwidth=0, font=caption_font(), padding=(px(8), px(8)))
    s.map("WP.Treeview.Heading", background=[("active", P.card_hover)])
    s.configure("WP.Vertical.TScrollbar", troughcolor=P.card, background=P.track_off, bordercolor=P.card,
                lightcolor=P.track_off, darkcolor=P.track_off, arrowsize=0, gripcount=0, relief="flat")
    s.map("WP.Vertical.TScrollbar", background=[("active", P.text3)])
    s.layout("WP.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    # Rows without the expand/collapse arrow.
    s.layout("Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Treeitem.image", {"side": "left", "sticky": ""}),
        ("Treeitem.text", {"side": "left", "sticky": ""})]})])


# ---------------------------------------------------------------- Check table

def default_values(item, size_fmt):
    size = "Registry" if item.kind == "registry" else size_fmt(item.size)
    return (item.level, size)


class CheckTable(tk.Frame):
    """Rows of Items with check boxes.
    grouped=True: bold group rows by item.category, with a tick box for the group.
    columns: [(key, heading, width, anchor)] after the name column; values(item) fills them.
    Locked items (item.locked) are shown greyed and can't be ticked."""

    def __init__(self, parent, on_change=None, on_select=None, confirm_check=None, grouped=True,
                 columns=(("rating", "Rating", 110, "w"), ("size", "Size", 90, "e")), values=None,
                 headings=False, on_open=None, group_of=None):
        super().__init__(parent, bg=bg_of(parent))
        self.on_change, self.on_select, self.on_open = on_change, on_select, on_open
        self.confirm_check = confirm_check   # fn(item) -> bool, for "Check first" items
        self.grouped = grouped
        self.group_of = group_of or (lambda it: it.category)
        self.values = values
        self.size_fmt = lambda n: str(n)
        self.tree = ttk.Treeview(self, style="WP.Treeview", columns=[c[0] for c in columns],
                                 show=("tree", "headings") if headings else "tree", selectmode="browse")
        self.tree.column("#0", minwidth=px(240), stretch=True)
        if headings:
            self.tree.heading("#0", text="Name", anchor="w")
        for key, title, width, anchor in columns:
            self.tree.column(key, width=px(width), anchor=anchor, stretch=False)
            if headings:
                self.tree.heading(key, text=title, anchor=anchor)
        self.tree.tag_configure("group", font=body_strong())
        self.tree.tag_configure("check", foreground=P.warning)
        self.tree.tag_configure("locked", foreground=P.text3)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview, style="WP.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.items: dict[str, object] = {}
        self.groups: dict[str, list[str]] = {}
        self.tree.bind("<Button-1>", self._click, add="+")
        self.tree.bind("<space>", lambda e: self._toggle(self.tree.focus()))
        self.tree.bind("<Double-1>", lambda e: self.on_open and self.selected() and self.on_open(self.selected()))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select and self.on_select(self.selected()))

    def _img(self, state):
        if state == "mixed":
            return checkbox_img(px(18), True, P.text3, P.text3, P.card)
        if state == "locked":
            return checkbox_img(px(18), False, P.border, P.border, P.control)
        return checkbox_img(px(18), state, P.accent, P.text3, P.card)

    def _row_values(self, it):
        return self.values(it) if self.values else default_values(it, self.size_fmt)

    def _tags(self, it):
        if it.locked:
            return ("locked",)
        return ("check",) if it.level != "Safe" else ()

    def set_items(self, items, size_fmt):
        self.size_fmt = size_fmt
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.groups.clear()
        for it in items:
            parent = ""
            g = self.group_of(it) if self.grouped else None
            if self.grouped:
                if g not in self.groups:
                    gid = self.tree.insert("", "end", text=f"  {g}", open=True, tags=("group",))
                    self.groups[g] = [gid]
                parent = self.groups[g][0]
            iid = self.tree.insert(parent, "end", text=f"  {it.label}",
                                   image=self._img("locked" if it.locked else it.checked),
                                   values=self._row_values(it), tags=self._tags(it))
            self.items[iid] = it
            if self.grouped:
                self.groups[g].append(iid)
        self._refresh()

    def _refresh(self):
        for cat, ids in self.groups.items():
            gid, kids = ids[0], [self.items[i] for i in ids[1:] if i in self.items]
            free = [k for k in kids if not k.locked]
            n_on = sum(k.checked for k in free)
            state = True if free and n_on == len(free) else False if n_on == 0 else "mixed"
            n = len(kids)
            vals = [""] * len(self.tree["columns"])
            if vals:
                vals[-1] = self.size_fmt(sum(k.size for k in kids))
            self.tree.item(gid, image=self._img(state),
                           text=f"  {cat}   \u00B7   {n} item{'s' if n != 1 else ''}", values=vals)
        if self.on_change:
            self.on_change()

    def _click(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if "image" in str(self.tree.identify_element(e.x, e.y)):
            self._toggle(iid)
            return "break"

    def _toggle(self, iid):
        if iid in self.items:
            it = self.items[iid]
            if it.locked:
                return
            if not it.checked and it.level != "Safe" and self.confirm_check and not self.confirm_check(it):
                return
            it.checked = not it.checked
            self.tree.item(iid, image=self._img(it.checked))
        else:
            cat = next((c for c, ids in self.groups.items() if ids[0] == iid), None)
            if cat is None:
                return
            kids = [self.items[i] for i in self.groups[cat][1:] if not self.items[i].locked]
            turn_on = not all(k.checked for k in kids)
            for i in self.groups[cat][1:]:
                k = self.items[i]
                if k.locked or (turn_on and k.level != "Safe"):
                    continue   # "Check first" items are only ticked one by one
                k.checked = turn_on
                self.tree.item(i, image=self._img(k.checked))
        self._refresh()

    def checked(self):
        return [i for i in self.items.values() if i.checked and not i.locked]

    def selected(self):
        return self.items.get(self.tree.focus())

    def tick(self, predicate):
        for iid, it in self.items.items():
            it.checked = bool(predicate(it)) and not it.locked
            self.tree.item(iid, image=self._img("locked" if it.locked else it.checked))
        self._refresh()

    def remove_paths(self, paths: set[str]):
        for iid, it in list(self.items.items()):
            if it.path in paths and not it.extra.get("contents_only"):
                self.tree.delete(iid)
                del self.items[iid]
                for ids in self.groups.values():
                    if iid in ids:
                        ids.remove(iid)
        for cat in [c for c, ids in self.groups.items() if len(ids) == 1]:
            self.tree.delete(self.groups[cat][0])
            del self.groups[cat]
        self._refresh()


# ---------------------------------------------------------------- Segmented control

class Segmented(tk.Frame):
    """A row of choices, one active (filters and sub-tabs)."""

    def __init__(self, parent, options: list[tuple[str, str]], value: str, command=None):
        super().__init__(parent, bg=bg_of(parent))
        self.value, self.command = value, command
        self.buttons = {}
        for key, text in options:
            b = Button(self, text, kind="primary" if key == value else "subtle", height=30,
                       command=lambda k=key: self.set(k, notify=True))
            b.pack(side="left", padx=(0, px(4)))
            self.buttons[key] = b

    def set(self, key, notify=False):
        self.value = key
        for k, b in self.buttons.items():
            b.kind = "primary" if k == key else "subtle"
            b._font = body_strong() if k == key else body_font()
            b._measure()
            b._draw()
        if notify and self.command:
            self.command(key)

    def set_text(self, key, text):
        if key in self.buttons:
            self.buttons[key].set_text(text)


# ---------------------------------------------------------------- Dialog

class Dialog(tk.Toplevel):
    """Modal dialog. buttons: [(label, value, kind)]; the last one is the default.
    show() returns the value of the button pressed (None for Esc/close)."""

    def __init__(self, parent, title, message="", buttons=(("Cancel", None, "secondary"), ("OK", True, "primary")),
                 icon=None, icon_color=None, width=440, build=None):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=P.card)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.result = None
        body = tk.Frame(self, bg=P.card, padx=px(24), pady=px(22))
        body.pack(fill="both", expand=True)
        head = tk.Frame(body, bg=P.card)
        head.pack(fill="x")
        if icon:
            icon_label(head, icon, 16, icon_color or P.accent).pack(side="left", padx=(0, px(10)))
        label(head, title, "heading").pack(side="left")
        if message:
            label(body, message, "body", P.text2, wrap=px(width)).pack(fill="x", pady=(px(10), 0))
        if build:
            extra = tk.Frame(body, bg=P.card)
            extra.pack(fill="both", expand=True, pady=(px(12), 0))
            build(extra)
        foot = tk.Frame(self, bg=P.window, padx=px(24), pady=px(16))
        foot.pack(fill="x")
        default = None
        for text, value, kind in reversed(buttons):
            b = Button(foot, text=text, kind=kind, min_width=96, command=lambda v=value: self._close(v))
            b.pack(side="right", padx=(px(8), 0))
            default = default or (value, b)
        self.bind("<Escape>", lambda e: self._close(None))
        self.bind("<Return>", lambda e: self._close(default[0]))
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(None))
        set_dark_title_bar(self, P.name == "dark")

    def _close(self, value):
        self.result = value
        self.grab_release()
        self.destroy()

    def show(self):
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        self.grab_set()
        self.focus_force()
        self.wait_window()
        return self.result


def ask(parent, title, message, ok="OK", cancel="Cancel", danger=False, icon=None) -> bool:
    buttons = ((cancel, False, "secondary"), (ok, True, "danger" if danger else "primary"))
    return bool(Dialog(parent, title, message, buttons, icon=icon,
                       icon_color=P.danger if danger else None).show())


def inform(parent, title, message, icon="info", icon_color=None):
    Dialog(parent, title, message, (("OK", True, "primary"),), icon=icon, icon_color=icon_color).show()


# ---------------------------------------------------------------- Toast

class Toast:
    """A short message that slides in at the bottom of `host` and hides itself."""

    def __init__(self, host):
        self.host = host
        self.card = None
        self._after = None

    def show(self, text, kind="success", action=None, seconds=6):
        self.hide()
        colors = {"success": P.success, "warning": P.warning, "info": P.accent, "danger": P.danger}
        icons = {"success": "check", "warning": "warning", "info": "info", "danger": "warning"}
        self.card = Card(self.host, padding=12, radius=10, fill=P.card, outline=P.border, fit_width=True)
        b = self.card.body
        icon_label(b, icons[kind], 12, colors[kind]).pack(side="left", padx=(px(2), px(10)))
        label(b, text, "body", wrap=px(520)).pack(side="left")
        tk.Label(b, text=icon("close"), font=icon_font(9), fg=P.text3, bg=P.card,
                 cursor="hand2").pack(side="right", padx=(px(12), px(2)))
        b.winfo_children()[-1].bind("<Button-1>", lambda e: self.hide())
        if action:
            text_, fn = action
            Button(b, text=text_, kind="subtle", command=lambda: (fn(), self.hide()), height=28).pack(side="right", padx=(px(12), 0))
        self.card.place(relx=0.5, rely=1.0, y=-px(20), anchor="s")
        # Card is a Canvas, whose own lift() raises canvas drawings, not the
        # widget. Call the general widget version to bring the toast to the front.
        tk.Misc.lift(self.card)
        self._after = self.host.after(seconds * 1000, self.hide)

    def hide(self):
        if self._after:
            self.host.after_cancel(self._after)
            self._after = None
        if self.card:
            self.card.destroy()
            self.card = None
