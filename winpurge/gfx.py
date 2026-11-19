"""Pixel graphics made in code: smooth (anti-aliased) rounded corners,
circles, check boxes and the WinPurge logo. Tk's canvas has no
anti-aliasing on Windows, so smooth curves are drawn as small PNG images.
Pure Python: a tiny PNG/ICO writer, no image files or libraries."""
from __future__ import annotations

import base64
import math
import struct
import zlib

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


def png_b64(w, h, rgba) -> str:
    return base64.b64encode(png_bytes(w, h, rgba)).decode("ascii")


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


# ---------------------------------------------------------------- Tk images

class ImageCache:
    """Keeps PhotoImages alive (Tk drops images that Python forgets)."""

    def __init__(self):
        self._cache: dict = {}

    def get(self, key, make):
        img = self._cache.get(key)
        if img is None:
            import tkinter as tk
            w, h, px = make()
            img = tk.PhotoImage(data=png_b64(w, h, px))
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
