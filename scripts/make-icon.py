#!/usr/bin/env python3
"""Draws assets/monitor-t2.png (256x256): a dark rounded square with a usage ring. Own artwork, MIT licensed."""
import math
import os

import cairo

S = 256
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
cr = cairo.Context(surf)


def rounded(x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


g = cairo.LinearGradient(0, 0, 0, S)
g.add_color_stop_rgb(0, 0.17, 0.18, 0.23)
g.add_color_stop_rgb(1, 0.08, 0.08, 0.11)
rounded(8, 8, S - 16, S - 16, 52)
cr.set_source(g)
cr.fill()
cr.set_line_cap(cairo.LINE_CAP_ROUND)
cr.set_line_width(22)
start, sweep = 0.75 * math.pi, 1.5 * math.pi
cr.set_source_rgba(1, 1, 1, 0.12)
cr.arc(S / 2, S / 2 + 6, 78, start, start + sweep)
cr.stroke()
for frac, (r, gr, b) in ((0.72, (0.25, 0.52, 1.0)),):
    cr.set_source_rgb(r, gr, b)
    cr.arc(S / 2, S / 2 + 6, 78, start, start + sweep * frac)
    cr.stroke()
cr.set_source_rgb(0.2, 0.78, 0.35)
cr.set_line_width(10)
cr.arc(S / 2, S / 2 + 6, 52, start, start + sweep * 0.45)
cr.stroke()
cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
cr.set_font_size(58)
cr.set_source_rgb(0.95, 0.95, 0.97)
ext = cr.text_extents("T2")
cr.move_to(S / 2 - ext.width / 2 - ext.x_bearing, S / 2 + 6 + ext.height / 2)
cr.show_text("T2")
out = os.path.join(os.path.dirname(__file__), "..", "assets", "monitor-t2.png")
surf.write_to_png(out)
print("wrote", os.path.normpath(out))
