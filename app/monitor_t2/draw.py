"""Cairo/Pango drawing primitives that reproduce a macOS menu-bar monitor look (rings, area charts, bars)."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo  # noqa: E402

BLUE = (0.25, 0.52, 1.0)
RED = (1.0, 0.27, 0.23)
GREEN = (0.20, 0.78, 0.35)
ORANGE = (1.0, 0.62, 0.04)
PURPLE = (0.69, 0.32, 0.87)
TEAL = (0.19, 0.69, 0.78)
GRAY = (0.56, 0.56, 0.58)

THEMES = {
    "dark": {"bg": (0.125, 0.125, 0.145), "fg": (0.94, 0.94, 0.96), "sub": (0.62, 0.62, 0.66),
             "track": (1, 1, 1, 0.10), "panel": (1, 1, 1, 0.05)},
    "light": {"bg": (0.96, 0.96, 0.97), "fg": (0.10, 0.10, 0.12), "sub": (0.45, 0.45, 0.50),
              "track": (0, 0, 0, 0.09), "panel": (0, 0, 0, 0.045)},
}
T = dict(THEMES["dark"])
T["name"] = "dark"


def set_theme(name):
    T.clear()
    T.update(THEMES[name])
    T["name"] = name


def rgba(cr, c, a=None):
    if len(c) == 4 and a is None:
        cr.set_source_rgba(*c)
    else:
        cr.set_source_rgba(c[0], c[1], c[2], 1.0 if a is None else a)


def text(cr, s, x, y, size, color, bold=False, align="l", valign="t", font="Sans"):
    lay = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription(f"{font} {'Bold' if bold else ''}")
    fd.set_absolute_size(size * Pango.SCALE)
    lay.set_font_description(fd)
    lay.set_text(s, -1)
    w, h = lay.get_pixel_size()
    ox = x - (w / 2 if align == "c" else w if align == "r" else 0)
    oy = y - (h / 2 if valign == "m" else h if valign == "b" else 0)
    cr.move_to(ox, oy)
    rgba(cr, color)
    PangoCairo.show_layout(cr, lay)
    return w, h


def rounded(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def ring(cr, cx, cy, r, frac, color, width=7, big=None, small=None, big_size=None):
    frac = max(0.0, min(1.0, frac))
    start = 0.75 * math.pi  # 270° sweep like circular gauges
    sweep = 1.5 * math.pi
    cr.set_line_width(width)
    cr.set_line_cap(1)
    rgba(cr, T["track"])
    cr.new_sub_path()
    cr.arc(cx, cy, r, start, start + sweep)
    cr.stroke()
    if frac > 0.003:
        rgba(cr, color)
        cr.new_sub_path()
        cr.arc(cx, cy, r, start, start + sweep * frac)
        cr.stroke()
    if big:
        text(cr, big, cx, cy - (3 if small else 0), big_size or r * 0.62, T["fg"], True, "c", "m")
    if small:
        text(cr, small, cx, cy + r * 0.78 + 4, 10, T["sub"], False, "c", "m")


def chart(cr, w, h, series, ymax=None, mirror=None, stacked=False):
    """series: list of (values, color). mirror: list drawn downwards from the middle (net/disk)."""
    rounded(cr, 0, 0, w, h, 8)
    rgba(cr, T["panel"])
    cr.fill_preserve()
    cr.clip()
    # grid
    rgba(cr, T["track"])
    cr.set_line_width(1)
    for i in (1, 2, 3):
        cr.move_to(0, h * i / 4)
        cr.line_to(w, h * i / 4)
    cr.stroke()

    def draw(vals, color, base, height, up=True, bottom_vals=None, vmax=1.0):
        n = len(vals)
        if n < 2:
            return
        dx = w / (n - 1)
        sgn = -1 if up else 1

        def y_of(v):
            return base + sgn * height * min(1.0, v / vmax)
        cr.move_to(0, y_of(bottom_vals[0]) if bottom_vals else base)
        pts = [(i * dx, y_of((vals[i] + (bottom_vals[i] if bottom_vals else 0)))) for i in range(n)]
        cr.new_path()
        cr.move_to(pts[0][0], base if not bottom_vals else y_of(bottom_vals[0]))
        for x, y in pts:
            cr.line_to(x, y)
        if bottom_vals:
            for i in range(n - 1, -1, -1):
                cr.line_to(i * dx, y_of(bottom_vals[i]))
        else:
            cr.line_to(w, base)
        cr.close_path()
        rgba(cr, color, 0.55)
        cr.fill_preserve()
        rgba(cr, color, 0.0)
        cr.new_path()
        cr.move_to(*pts[0])
        for x, y in pts[1:]:
            cr.line_to(x, y)
        rgba(cr, color, 1.0)
        cr.set_line_width(1.2)
        cr.stroke()

    if mirror is None:
        top = ymax or max([max(s[0]) for s in series] + [1e-9])
        if stacked:
            acc = [0.0] * len(series[0][0])
            for vals, col in series:
                lower = list(acc)
                draw(list(vals), col, h, h - 2, True, bottom_vals=lower, vmax=top)
                acc = [a + b for a, b in zip(acc, vals)]
        else:
            for vals, col in series:
                draw(list(vals), col, h, h - 2, True, vmax=top)
    else:
        peak = ymax or max([max(s[0]) for s in series + mirror] + [1.0])
        mid = h / 2
        for vals, col in series:
            draw(list(vals), col, mid, mid - 2, True, vmax=peak)
        for vals, col in mirror:
            draw(list(vals), col, mid, mid - 2, False, vmax=peak)
        rgba(cr, T["track"])
        cr.move_to(0, mid)
        cr.line_to(w, mid)
        cr.stroke()


def segbar(cr, w, h, segs):
    """segs: list of (fraction, color) laid left to right on a track."""
    rounded(cr, 0, 0, w, h, h / 2)
    rgba(cr, T["track"])
    cr.fill_preserve()
    cr.clip()
    x = 0
    for frac, col in segs:
        sw = w * max(0.0, frac)
        rgba(cr, col)
        cr.rectangle(x, 0, sw, h)
        cr.fill()
        x += sw


class Canvas(Gtk.DrawingArea):
    def __init__(self, w, h, fn):
        super().__init__()
        self.set_size_request(w, h)
        self.fn = fn
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        a = self.get_allocation()
        self.fn(cr, a.width, a.height)
        return False
