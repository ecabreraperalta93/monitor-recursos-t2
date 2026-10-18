"""Module popups, laid out like a macOS menu-bar monitor: header, rings, charts, details, top processes."""
import datetime
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import draw
from .data import SMC_NAMES, category, fand, human
from .draw import BLUE, GRAY, GREEN, ORANGE, PURPLE, RED, T, TEAL, Canvas

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell as LS
except (ValueError, ImportError):
    LS = None

WIDTH = 300

CSS = """
window.t2-popup { background: transparent; }
.card { border-radius: 14px; padding: 12px 12px 14px 12px; }
.card.dark { background: rgba(32,32,37,0.97); border: 1px solid rgba(255,255,255,0.10); color: #f0f0f5; }
.card.light { background: rgba(246,246,248,0.98); border: 1px solid rgba(0,0,0,0.12); color: #1a1a1f; }
.title { font-weight: 700; font-size: 13px; }
.sec { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; opacity: 0.55; margin-top: 8px; }
.k { font-size: 12px; opacity: 0.80; }
.v { font-size: 12px; font-weight: 600; }
.sub { font-size: 11px; opacity: 0.6; }
button.gear { background: none; border: none; box-shadow: none; padding: 2px; min-width: 0; min-height: 0; opacity: 0.6; }
button.seg { padding: 2px 8px; font-size: 11px; min-height: 0; }
button.turbo { padding: 0px 9px; min-height: 0; min-width: 0; font-size: 10px; font-weight: 700; border-radius: 9px; }
button.turbo.on { background-image: none; background-color: #e5322d; color: #ffffff; border: 1px solid #b3201c; }
button.turbo.off { background-image: none; background-color: #ffffff; color: #1a1a1f; border: 1px solid rgba(0,0,0,0.30); }
"""


def apply_css():
    p = Gtk.CssProvider()
    p.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def lbl(text="", cls=None, xalign=0.0):
    l = Gtk.Label(label=text, xalign=xalign)
    if cls:
        l.get_style_context().add_class(cls)
    return l


class KV(Gtk.Grid):
    def __init__(self):
        super().__init__(column_spacing=8, row_spacing=3)
        self.vals, self.n = [], 0

    def add(self, key, dot=None):
        row = self.n
        self.n += 1
        if dot is not None:
            d = Canvas(10, 10, lambda cr, w, h, c=dot: (draw.rgba(cr, c), cr.arc(5, 5, 4, 0, 6.3), cr.fill()))
            d.set_valign(Gtk.Align.CENTER)
            self.attach(d, 0, row, 1, 1)
        k = lbl(key, "k")
        k.set_hexpand(True)
        self.attach(k, 1, row, 1, 1)
        v = lbl("–", "v", 1.0)
        v.set_ellipsize(3)
        v.set_max_width_chars(26)
        self.attach(v, 2, row, 1, 1)
        self.vals.append(v)
        return row

    def set(self, i, s):
        self.vals[i].set_text(s)


class TopList(Gtk.Grid):
    def __init__(self, n=5):
        super().__init__(column_spacing=8, row_spacing=3)
        self.rows = []
        for i in range(n):
            a, b = lbl("", "k"), lbl("", "v", 1.0)
            a.set_hexpand(True)
            a.set_ellipsize(3)
            a.set_max_width_chars(24)
            self.attach(a, 0, i, 1, 1)
            self.attach(b, 1, i, 1, 1)
            self.rows.append((a, b))

    def set(self, items):
        for (a, b), it in zip(self.rows, items + [("", "")] * len(self.rows)):
            a.set_text(it[0])
            b.set_text(it[1])


class AppPowerList(Gtk.Grid):
    """Rows of: application name, proportional bar, watts."""

    def __init__(self, n=12):
        super().__init__(column_spacing=8, row_spacing=5)
        self.rows = []
        for i in range(n):
            name = lbl("", "k")
            name.set_hexpand(True)
            name.set_ellipsize(3)
            name.set_max_width_chars(20)
            st = {"f": 0.0, "c": BLUE}

            def paint(cr, w, h, st=st):
                draw.rounded(cr, 0, 0, w, h, h / 2)
                draw.rgba(cr, T["track"])
                cr.fill()
                if st["f"] > 0:
                    draw.rounded(cr, 0, 0, max(h, w * min(1.0, st["f"])), h, h / 2)
                    draw.rgba(cr, st["c"])
                    cr.fill()
            bar = Canvas(70, 8, paint)
            bar.set_valign(Gtk.Align.CENTER)
            bar.set_no_show_all(True)  # empty rows keep no bar, show_all() must not bring it back
            val = lbl("", "v", 1.0)
            val.set_width_chars(7)
            self.attach(name, 0, i, 1, 1)
            self.attach(bar, 1, i, 1, 1)
            self.attach(val, 2, i, 1, 1)
            self.rows.append((name, bar, val, st))

    def show_rows(self, rows):
        """rows: list of (name, watts, colour). The longest bar is the biggest consumer."""
        top = max([r[1] for r in rows] + [0.001])
        for i, (name, bar, val, st) in enumerate(self.rows):
            if i < len(rows):
                n, w, c = rows[i]
                name.set_text(n)
                val.set_text(f"{w:.1f} W")
                st["f"], st["c"] = w / top, c
            else:
                name.set_text("")
                val.set_text("")
                st["f"] = 0.0
            bar.set_visible(i < len(rows))
            bar.queue_draw()

    def show_message(self, text):
        self.show_rows([])
        self.rows[0][0].set_text(text)


class Module:
    name = ""
    title = ""

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.sampler = app.sampler
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvases = []
        self.build()

    def sec(self, t):
        self.box.pack_start(lbl(t.upper(), "sec"), False, False, 0)

    def canvas(self, h, fn):
        c = Canvas(WIDTH - 24, h, fn)
        self.box.pack_start(c, False, False, 0)
        self.canvases.append(c)
        return c

    def redraw(self):
        for c in self.canvases:
            c.queue_draw()

    def build(self):
        pass

    def update(self, s):
        self.redraw()

    # value shown in the tray icon: returns (label, value_text, fraction, color)
    def tray(self, s):
        return (self.name, "–", 0.0, BLUE)


def mem_color(p):
    return GREEN if p < 60 else ORANGE if p < 85 else RED


class TurboButton(Gtk.Button):
    """Small CPU-turbo switch: red = turbo on, white = off. Click toggles it through the monitor-t2-fand daemon."""

    def __init__(self):
        super().__init__(label="Turbo")
        self.get_style_context().add_class("turbo")
        self.on = None
        self.err = None
        self.set_no_show_all(True)  # only shown once the CPU reports that turbo can be controlled
        self.connect("clicked", self._clicked)

    def _paint(self, on):
        self.on = bool(on)
        sc = self.get_style_context()
        sc.remove_class("off" if on else "on")
        sc.add_class("on" if on else "off")
        self.set_label("Turbo ⚠" if self.err else "Turbo")
        tip = ("Modo Turbo del CPU: " + ("ENCENDIDO (rojo)" if on else "APAGADO (blanco)")
               + ". Clic para " + ("apagarlo." if on else "encenderlo.") + " Se restablece al reiniciar.")
        if self.err:
            tip += f"\n⚠ {self.err}. ¿Está activo monitor-t2-fand?"
        self.set_tooltip_text(tip)

    def _clicked(self, _b):
        if self.on is None:
            return
        want = not self.on
        r = fand({"cmd": "turbo", "enabled": want})
        ok = bool(r and r.get("ok"))
        self.err = None if ok else (r or {}).get("error", "monitor-t2-fand no responde")
        self._paint(want if ok else self.on)

    def sync(self, state):
        """state: True/False from the system, None if turbo can't be controlled (button hidden)."""
        if state is None:
            self.on = None
            self.hide()
            return
        if not self.get_visible():
            self.show()
        self._paint(state)


class CPU(Module):
    name, title = "CPU", "CPU"

    def build(self):
        self.s = {}
        head = Gtk.Box(spacing=6)
        head.pack_start(lbl("USO DEL PROCESADOR", "sec"), True, True, 0)
        self.turbo = TurboButton()
        head.pack_end(self.turbo, False, False, 0)
        self.box.pack_start(head, False, False, 0)
        self.canvas(92, self.rings)
        self.sec("Historial")
        self.canvas(70, lambda cr, w, h: draw.chart(
            cr, w, h, [(self.sampler.h["cpu_sys"], RED), (self.sampler.h["cpu_user"], BLUE)], 100, stacked=True))
        self.sec("Detalles")
        self.kv = KV()
        self.i_sys = self.kv.add("Sistema", RED)
        self.i_usr = self.kv.add("Usuario", BLUE)
        self.i_idle = self.kv.add("Inactivo", GRAY)
        self.i_freq = self.kv.add("Frecuencia")
        self.i_core = self.kv.add("Núcleos")
        self.i_up = self.kv.add("Tiempo activo")
        self.box.pack_start(self.kv, False, False, 0)
        self.sec("Carga media")
        self.load = KV()
        for k in ("1 minuto", "5 minutos", "15 minutos"):
            self.load.add(k)
        self.box.pack_start(self.load, False, False, 0)
        self.sec("Procesos principales")
        self.top = TopList()
        self.box.pack_start(self.top, False, False, 0)

    def rings(self, cr, w, h):
        s = self.s
        if not s:
            return
        t = s.get("cpu_temp")
        draw.ring(cr, 48, 46, 28, (t or 0) / 110.0, ORANGE if (t or 0) > 80 else GREEN, 6,
                  self.cfg.temp(t) if t else "–", "Temperatura", 13)
        draw.ring(cr, w / 2, 44, 38, s["cpu"] / 100.0, BLUE, 8, f"{s['cpu']:.0f}%", "Uso total", 20)
        ld = s["load"][0] / s["ncpu"]
        draw.ring(cr, w - 48, 46, 28, ld, PURPLE, 6, f"{s['load'][0]:.2f}", "Carga", 13)

    def update(self, s):
        self.s = s
        self.turbo.sync(s.get("turbo"))
        self.kv.set(self.i_sys, f"{s['cpu_sys']:.1f}%")
        self.kv.set(self.i_usr, f"{s['cpu_user']:.1f}%")
        self.kv.set(self.i_idle, f"{s['cpu_idle']:.1f}%")
        self.kv.set(self.i_freq, f"{s['freq'] / 1000:.2f} GHz" if s["freq"] else "–")
        self.kv.set(self.i_core, f"{s['phys']} físicos / {s['ncpu']} lógicos")
        up = int(s["uptime"])
        self.kv.set(self.i_up, f"{up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m")
        for i, v in enumerate(s["load"]):
            self.load.set(i, f"{v:.2f}")
        self.top.set([(n, f"{v:.1f}%") for n, v in s["top_cpu"]])
        self.redraw()

    def tray(self, s):
        return ("CPU", f"{s['cpu']:.0f}%", s["cpu"] / 100, BLUE)


class GPU(Module):
    name, title = "GPU", "GPU"

    def build(self):
        self.s = {}
        self.canvas(92, self.rings)
        self.sec("Historial")
        self.canvas(70, lambda cr, w, h: draw.chart(cr, w, h, [(self.sampler.h["gpu"], GREEN)], 100))
        self.sec("Detalles")
        self.kv = KV()
        self.i_name = self.kv.add("Modelo")
        self.i_use = self.kv.add("Utilización", GREEN)
        self.i_vram = self.kv.add("Memoria de vídeo")
        self.i_clk = self.kv.add("Frecuencia")
        self.i_pw = self.kv.add("Consumo")
        self.box.pack_start(self.kv, False, False, 0)

    def rings(self, cr, w, h):
        s = self.s
        g = s.get("gpu") if s else None
        if not g:
            draw.text(cr, "GPU no detectada", w / 2, 46, 13, T["sub"], False, "c", "m")
            return
        t = s.get("gpu_temp")
        draw.ring(cr, 48, 46, 28, (t or 0) / 110.0, ORANGE if (t or 0) > 80 else GREEN, 6,
                  self.cfg.temp(t) if t else "–", "Temperatura", 13)
        draw.ring(cr, w / 2, 44, 38, g["usage"] / 100, GREEN, 8, f"{g['usage']:.0f}%", "Utilización", 20)
        vp = 100.0 * g["vram_used"] / g["vram_total"] if g.get("vram_total") else 0
        draw.ring(cr, w - 48, 46, 28, vp / 100, TEAL, 6, f"{vp:.0f}%", "VRAM", 13)

    def update(self, s):
        self.s = s
        g = s.get("gpu")
        if g:
            self.kv.set(self.i_name, g["name"])
            self.kv.set(self.i_use, f"{g['usage']:.0f}%")
            self.kv.set(self.i_vram, f"{human(g['vram_used'])} / {human(g['vram_total'])}" if g.get("vram_total") else "–")
            self.kv.set(self.i_clk, f"{g['clock']:.0f} MHz" if g.get("clock") else "–")
            self.kv.set(self.i_pw, f"{g['power']:.1f} W" if g.get("power") else "–")
        self.redraw()

    def tray(self, s):
        g = s.get("gpu")
        u = g["usage"] if g else 0
        return ("GPU", f"{u:.0f}%", u / 100, GREEN)


class RAM(Module):
    name, title = "RAM", "RAM"

    def build(self):
        self.s = {}
        self.canvas(92, self.rings)
        self.canvas(10, self.bar)
        self.sec("Historial")
        self.canvas(70, lambda cr, w, h: draw.chart(cr, w, h, [(self.sampler.h["ram"], BLUE)], 100))
        self.sec("Detalles")
        self.kv = KV()
        self.i_used = self.kv.add("Usada", BLUE)
        self.i_cache = self.kv.add("Caché y búferes", ORANGE)
        self.i_free = self.kv.add("Libre", GRAY)
        self.i_tot = self.kv.add("Total")
        self.i_swap = self.kv.add("Swap")
        self.box.pack_start(self.kv, False, False, 0)
        self.sec("Procesos principales")
        self.top = TopList()
        self.box.pack_start(self.top, False, False, 0)

    def rings(self, cr, w, h):
        s = self.s
        if not s:
            return
        psi = s["psi"]
        lvl, col = ("Normal", GREEN) if psi < 5 else ("Media", ORANGE) if psi < 20 else ("Crítica", RED)
        draw.ring(cr, 60, 46, 30, min(1.0, psi / 40.0), col, 6, lvl, "Presión", 11)
        draw.ring(cr, w - 70, 44, 38, s["vm"].percent / 100, mem_color(s["vm"].percent), 8,
                  f"{s['vm'].percent:.0f}%", "Uso", 20)

    def bar(self, cr, w, h):
        s = self.s
        if not s:
            return
        vm = s["vm"]
        cache = getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)
        draw.segbar(cr, w, h, [((vm.total - vm.available) / vm.total, BLUE), (cache / vm.total, ORANGE)])

    def update(self, s):
        self.s = s
        vm, sw = s["vm"], s["sw"]
        cache = getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)
        self.kv.set(self.i_used, human(vm.total - vm.available))
        self.kv.set(self.i_cache, human(cache))
        self.kv.set(self.i_free, human(vm.available))
        self.kv.set(self.i_tot, human(vm.total))
        self.kv.set(self.i_swap, f"{human(sw.used)} / {human(sw.total)}")
        self.top.set([(n, human(v)) for n, v in s["top_mem"]])
        self.redraw()

    def tray(self, s):
        p = s["vm"].percent
        return ("RAM", f"{p:.0f}%", p / 100, mem_color(p))


class Disk(Module):
    name, title = "Disk", "Disco"

    def build(self):
        self.s = {}
        self.sec("Almacenamiento")
        self.canvas(10, self.bar)
        self.kv = KV()
        self.i_name = self.kv.add("Dispositivo")
        self.i_used = self.kv.add("Usado", BLUE)
        self.i_free = self.kv.add("Libre", GRAY)
        self.i_tot = self.kv.add("Total")
        self.box.pack_start(self.kv, False, False, 0)
        self.sec("Actividad")
        self.canvas(80, lambda cr, w, h: draw.chart(
            cr, w, h, [(self.sampler.h["disk_r"], BLUE)], mirror=[(self.sampler.h["disk_w"], RED)]))
        self.io = KV()
        self.i_r = self.io.add("Lectura", BLUE)
        self.i_w = self.io.add("Escritura", RED)
        self.box.pack_start(self.io, False, False, 0)

    def bar(self, cr, w, h):
        if self.s:
            draw.segbar(cr, w, h, [(self.s["disk"].percent / 100, BLUE)])

    def update(self, s):
        self.s = s
        d = s["disk"]
        self.kv.set(self.i_name, s["disk_name"])
        self.kv.set(self.i_used, f"{human(d.used)} ({d.percent:.0f}%)")
        self.kv.set(self.i_free, human(d.free))
        self.kv.set(self.i_tot, human(d.total))
        self.io.set(self.i_r, human(s["disk_r"], True))
        self.io.set(self.i_w, human(s["disk_w"], True))
        self.redraw()

    def tray(self, s):
        p = s["disk"].percent
        return ("SSD", f"{p:.0f}%", p / 100, BLUE)


class Network(Module):
    name, title = "Network", "Red"

    def build(self):
        self.s = {}
        self.sec("Actividad")
        self.canvas(90, lambda cr, w, h: draw.chart(
            cr, w, h, [(self.sampler.h["down"], BLUE)], mirror=[(self.sampler.h["up"], RED)]))
        self.kv = KV()
        self.i_d = self.kv.add("Bajada", BLUE)
        self.i_u = self.kv.add("Subida", RED)
        self.box.pack_start(self.kv, False, False, 0)
        self.sec("Detalles")
        self.det = KV()
        self.i_td = self.det.add("Total descargado")
        self.i_tu = self.det.add("Total subido")
        self.i_if = self.det.add("Interfaz")
        self.i_ip = self.det.add("IP local")
        self.i_st = self.det.add("Estado")
        self.box.pack_start(self.det, False, False, 0)

    def update(self, s):
        self.kv.set(self.i_d, human(s["down"], True))
        self.kv.set(self.i_u, human(s["up"], True))
        self.det.set(self.i_td, human(s["net_total"][0]))
        self.det.set(self.i_tu, human(s["net_total"][1]))
        self.det.set(self.i_if, s["iface"] or "–")
        self.det.set(self.i_ip, s["ip"] or "–")
        self.det.set(self.i_st, "Conectado" if s["iface"] else "Sin conexión")
        self.redraw()

    def tray(self, s):
        return ("NET", f"↓{short(s['down'])}\n↑{short(s['up'])}", 0.0, BLUE)


def short(n):
    for u in ("B", "K", "M", "G"):
        if n < 1000 or u == "G":
            return f"{n:.0f}{u}" if n >= 10 or u == "B" else f"{n:.1f}{u}"
        n /= 1024


class Battery(Module):
    name, title = "Battery", "Batería"

    def build(self):
        self.s = {}
        self.canvas(96, self.big)
        self.sec("Detalles")
        self.kv = KV()
        self.i_src = self.kv.add("Fuente")
        self.i_t = self.kv.add("Tiempo restante")
        self.i_pw = self.kv.add("Potencia")
        self.i_v = self.kv.add("Voltaje")
        self.i_a = self.kv.add("Corriente")
        self.i_h = self.kv.add("Salud")
        self.i_c = self.kv.add("Ciclos")
        self.i_tmp = self.kv.add("Temperatura")
        self.box.pack_start(self.kv, False, False, 0)

    def big(self, cr, w, h):
        b = self.s.get("battery") if self.s else None
        if not b:
            draw.text(cr, "Sin batería", w / 2, 46, 13, T["sub"], False, "c", "m")
            return
        col = GREEN if b["percent"] > 20 or b["charging"] else RED
        x, y, bw, bh = w / 2 - 56, 22, 100, 50
        draw.rounded(cr, x, y, bw, bh, 10)
        draw.rgba(cr, T["track"])
        cr.fill()
        draw.rounded(cr, x + 4, y + 4, (bw - 8) * b["percent"] / 100, bh - 8, 7)
        draw.rgba(cr, col)
        cr.fill()
        draw.rounded(cr, x + bw + 2, y + 16, 7, 18, 3)
        draw.rgba(cr, T["track"])
        cr.fill()
        draw.text(cr, ("⚡ " if b["charging"] else "") + f"{b['percent']:.0f}%", x + bw / 2, y + bh / 2, 20,
                  (0.05, 0.05, 0.05) if b["percent"] > 45 else T["fg"], True, "c", "m")

    def update(self, s):
        self.s = s
        b = s.get("battery")
        if b:
            self.kv.set(self.i_src, "Corriente alterna" if b["ac"] else "Batería")
            secs = b["secs"]
            self.kv.set(self.i_t, f"{secs // 3600}:{secs % 3600 // 60:02d} h" if secs else
                        ("Cargada" if b["full_state"] else "Cargando" if b["charging"] else "Conectada" if b["ac"] else "–"))
            self.kv.set(self.i_pw, f"{b['watts']:.2f} W")
            self.kv.set(self.i_v, f"{b['volt']:.2f} V")
            self.kv.set(self.i_a, f"{b['amps'] * 1000:.0f} mA")
            self.kv.set(self.i_h, f"{b['health']:.0f}%" if b["health"] else "–")
            self.kv.set(self.i_c, str(b["cycles"]) if b["cycles"] is not None else "–")
            self.kv.set(self.i_tmp, self.cfg.temp(b["temp"]) if b["temp"] else "–")
        self.redraw()

    def tray(self, s):
        b = s.get("battery")
        if not b:
            return ("BAT", "–", 0.0, GREEN)
        return ("BAT", ("⚡" if b["charging"] else "") + f"{b['percent']:.0f}%", b["percent"] / 100,
                GREEN if b["percent"] > 20 or b["charging"] else RED)


class Sensors(Module):
    name, title = "Sensors", "Sensores"

    def build(self):
        self.s = {}
        self.fan_ui = {}
        self.sec("Ventiladores")
        self.fan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.pack_start(self.fan_box, False, False, 0)
        self.temp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.sec("Temperaturas")
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(200)
        sc.set_max_content_height(260)
        sc.set_propagate_natural_height(True)
        sc.add(self.temp_box)
        self.box.pack_start(sc, False, False, 0)
        self.rows = {}
        self.built = False

    # ---- fans -----------------------------------------------------------
    def fan_cfg(self, i):
        d = self.cfg["fans"].setdefault(str(i), {})
        d.setdefault("mode", "auto")
        return d

    def apply_fan(self, i, fan):
        d = self.fan_cfg(i)
        if d["mode"] == "manual":
            rpm = fan["min"] + (fan["max"] - fan["min"]) * d.get("pct", 50) / 100.0
            req = {"cmd": "set", "fan": i, "mode": "manual", "rpm": int(rpm)}
        elif d["mode"] == "cool":
            req = {"cmd": "set", "fan": i, "mode": "manual", "rpm": fan["max"]}
        else:
            req = {"cmd": "set", "fan": i, "mode": "auto"}
        self.cfg.save()
        r = fand(req)
        self.app.fan_error = None if (r and r.get("ok")) else (r or {}).get("error", "monitor-t2-fand no responde")
        return r

    def build_fan(self, fan):
        i = fan["id"]
        d = self.fan_cfg(i)
        if d["mode"] not in ("auto", "manual", "cool"):
            d["mode"] = "auto"
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head = Gtk.Box(spacing=6)
        name = lbl(f"Ventilador {fan['name']}", "k")
        name.set_hexpand(True)
        rpm = lbl("", "v", 1.0)
        head.pack_start(name, True, True, 0)
        head.pack_end(rpm, False, False, 0)
        box.pack_start(head, False, False, 0)
        seg = Gtk.Box(spacing=0)
        seg.get_style_context().add_class("linked")
        btns = {}
        first = None
        for mode, text in (("auto", "Automático"), ("manual", "Manual"), ("cool", "Frío (100%)")):
            b = Gtk.RadioButton.new_with_label_from_widget(first, text)
            b.set_mode(False)
            b.get_style_context().add_class("seg")
            first = first or b
            btns[mode] = b
            seg.pack_start(b, True, True, 0)
        box.pack_start(seg, False, False, 0)
        mrow = Gtk.Box(spacing=6)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(False)
        scale.set_value(d.get("pct", 50))
        sval = lbl("", "v", 1.0)
        sval.set_width_chars(13)
        mrow.pack_start(scale, True, True, 0)
        mrow.pack_end(sval, False, False, 0)
        box.pack_start(mrow, False, False, 0)
        mrow.set_no_show_all(True)
        ui = {"rpm": rpm, "btns": btns, "mrow": mrow, "scale": scale, "sval": sval, "fan": fan,
              "timer": None, "lock": False}

        def show_mode(mode):
            mrow.set_visible(mode == "manual")

        def sval_update(*_):
            pct = scale.get_value()
            sval.set_text(f"{pct:.0f}% · {fan['min'] + (fan['max'] - fan['min']) * pct / 100:.0f} RPM")

        def on_mode(b, mode):
            if ui["lock"] or not b.get_active():
                return
            d["mode"] = mode
            if mode == "manual" and "pct" not in d:
                cur = 100.0 * (fan["rpm"] - fan["min"]) / max(1, fan["max"] - fan["min"])
                d["pct"] = max(0, min(100, round(cur)))
                ui["lock"] = True
                scale.set_value(d["pct"])
                ui["lock"] = False
            sval_update()
            show_mode(mode)
            self.apply_fan(i, fan)

        def fire():
            ui["timer"] = None
            self.apply_fan(i, fan)
            return False

        def on_scale(_s):
            sval_update()
            if ui["lock"]:
                return
            d["pct"] = int(scale.get_value())
            if d["mode"] == "manual":
                if ui["timer"]:
                    GLib.source_remove(ui["timer"])
                ui["timer"] = GLib.timeout_add(250, fire)

        for mode, b in btns.items():
            b.connect("toggled", on_mode, mode)
        scale.connect("value-changed", on_scale)
        ui["lock"] = True
        btns[d["mode"]].set_active(True)
        ui["lock"] = False
        sval_update()
        box.show_all()
        show_mode(d["mode"])
        self.fan_box.pack_start(box, False, False, 0)
        ui["show_mode"] = show_mode
        self.fan_ui[i] = ui

    def build_rows(self, s):
        for fan in s["fans"]:
            self.build_fan(fan)
        if not s["fans"]:
            self.fan_box.pack_start(lbl("No se detectaron ventiladores", "sub"), False, False, 0)
        self.err = lbl("", "sub")
        self.err.set_line_wrap(True)
        self.err.set_max_width_chars(40)
        self.fan_box.pack_start(self.err, False, False, 0)
        groups = {}
        for key, _v in s["temps"]:
            groups.setdefault(category(key), []).append(key)
        for g in ("CPU", "GPU", "Batería", "Almacenamiento", "Sistema"):
            if g not in groups:
                continue
            self.temp_box.pack_start(lbl(g, "sub"), False, False, 2)
            kv = KV()
            for key in groups[g]:
                self.rows[key] = (kv, kv.add(SMC_NAMES.get(key, key)))
            self.temp_box.pack_start(kv, False, False, 0)
        self.box.show_all()
        for ui_ in self.fan_ui.values():
            ui_["show_mode"](self.fan_cfg(ui_["fan"]["id"])["mode"])
        self.built = True

    def update(self, s):
        if not self.built and (s["temps"] or s["fans"]):
            self.build_rows(s)
        for f in s["fans"]:
            ui = self.fan_ui.get(f["id"])
            if ui:
                ui["rpm"].set_text(f"{f['rpm']} RPM")
        if self.built:
            self.err.set_text(f"⚠ {self.app.fan_error}. ¿Está activo monitor-t2-fand?" if self.app.fan_error else "")
            for key, v in s["temps"]:
                if key in self.rows:
                    kv, i = self.rows[key]
                    kv.set(i, self.cfg.temp(v))

    def tray(self, s):
        t = s.get("cpu_temp")
        return ("TEMP", self.cfg.temp(t) if t else "–", (t or 0) / 110.0, ORANGE if (t or 0) > 80 else GREEN)


def watts(v, digits=1):
    return "–" if v is None else f"{v:.{digits}f} W"


class Power(Module):
    """Watts per application first, then the totals (the total system power is also the tray icon)."""
    name, title = "Power", "Consumo"
    REF_W = 100.0  # tray bar scale; the 16-inch MacBook Pro charger is 96 W

    def build(self):
        self.s = {}
        self.sec("Aplicaciones (estimado)")
        self.apps = AppPowerList(12)
        self.box.pack_start(self.apps, False, False, 0)
        self.how = lbl("Estimación: reparte los vatios medidos del procesador y de la GPU entre las aplicaciones "
                       "según su uso (incluye el consumo en reposo). Pantalla, SSD y ventiladores no se asignan.", "sub")
        self.how.set_line_wrap(True)
        self.how.set_max_width_chars(40)
        self.box.pack_start(self.how, False, False, 0)
        self.sec("Totales")
        self.kv = KV()
        self.i_sys = self.kv.add("Sistema total", ORANGE)
        self.i_dc = self.kv.add("Entrada del cargador")
        self.i_cpu = self.kv.add("CPU (paquete)")
        self.i_dram = self.kv.add("Memoria RAM")
        self.i_gpu = self.kv.add("GPU dedicada")
        self.box.pack_start(self.kv, False, False, 0)
        self.sec("Historial (sistema)")
        self.canvas(60, lambda cr, w, h: draw.chart(cr, w, h, [(self.sampler.h["power"], ORANGE)], self.REF_W))
        self.note = lbl("", "sub")
        self.note.set_line_wrap(True)
        self.note.set_max_width_chars(40)
        self.box.pack_start(self.note, False, False, 0)

    def update(self, s):
        self.s = s
        p = s["power"]
        self.kv.set(self.i_sys, watts(p["system"]))
        self.kv.set(self.i_dc, watts(p["dc_in"]))
        self.kv.set(self.i_cpu, watts(p["cpu_pkg"]))
        self.kv.set(self.i_dram, watts(p["dram"]))
        self.kv.set(self.i_gpu, watts(p["gpu"]))
        apps = p["apps"]
        if not apps["has_cpu"]:
            self.apps.show_message("Sin vatios de CPU (falta monitor-t2-fand)")
        elif not apps["rows"]:
            self.apps.show_message("Ninguna aplicación destaca")
        else:
            self.apps.show_rows([(r["name"], r["w"], GREEN if r["gpu"] > r["cpu"] else BLUE) for r in apps["rows"]])
        if not p["daemon"]:
            self.note.set_text("El servicio monitor-t2-fand no responde: sin CPU, RAM ni sistema total. "
                               "Se muestran solo la GPU dedicada y la batería.")
        elif p["system"] is None:
            self.note.set_text("Este equipo no expone el consumo total del sistema; se muestra '–'.")
        else:
            self.note.set_text(f"Sistema total: {p['system_src']}.")
        self.redraw()

    def tray(self, s):
        sysw = s["power"]["system"]
        return ("WATT", "–" if sysw is None else f"{sysw:.0f}W", (sysw or 0) / self.REF_W,
                GREEN if (sysw or 0) < 50 else ORANGE if (sysw or 0) < 80 else RED)


class Clock(Module):
    name, title = "Clock", "Reloj"

    def build(self):
        self.time = lbl("", "title")
        self.time.set_markup("")
        self.box.pack_start(self.time, False, False, 0)
        self.cal = Gtk.Calendar()
        self.box.pack_start(self.cal, False, False, 0)
        self.utc = KV()
        self.i_utc = self.utc.add("UTC")
        self.box.pack_start(self.utc, False, False, 0)

    def update(self, s):
        n = datetime.datetime.now()
        self.time.set_markup(f"<span size='28000' weight='bold'>{n:%H:%M:%S}</span>")
        self.utc.set(self.i_utc, datetime.datetime.utcnow().strftime("%H:%M:%S"))

    def tray(self, s):
        return ("", datetime.datetime.now().strftime("%H:%M"), 0.0, BLUE)


MODULE_CLASSES = {"CPU": CPU, "GPU": GPU, "RAM": RAM, "Disk": Disk, "Network": Network,
                  "Battery": Battery, "Power": Power, "Sensors": Sensors, "Clock": Clock}


class Popup(Gtk.Window):
    """Frameless popup anchored under/over the tray icon (layer-shell on Wayland)."""

    def __init__(self, app, module):
        super().__init__(title=f"Monitor T2 – {module.title}")
        self.app, self.module = app, module
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.set_resizable(False)
        scr = self.get_screen()
        if scr.get_rgba_visual():
            self.set_visual(scr.get_rgba_visual())
        self.get_style_context().add_class("t2-popup")
        self.layer = bool(LS and LS.is_supported())
        if self.layer:
            LS.init_for_window(self)
            LS.set_layer(self, LS.Layer.TOP)
            LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.card.get_style_context().add_class("card")
        self.set_theme(draw.T["name"])
        head = Gtk.Box()
        head.pack_start(lbl(module.title, "title"), True, True, 0)
        gear = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.MENU)
        gear.get_style_context().add_class("gear")
        gear.connect("clicked", lambda *_: (self.hide(), app.show_settings()))
        head.pack_end(gear, False, False, 0)
        self.card.pack_start(head, False, False, 0)
        self.card.pack_start(module.box, True, True, 0)
        self.card.set_size_request(WIDTH, -1)
        self.add(self.card)
        self.connect("focus-out-event", lambda *_: self.dismiss())
        self.connect("key-press-event", lambda w, e: self.dismiss() if e.keyval == Gdk.KEY_Escape else None)
        self.hidden_at = 0.0

    def set_theme(self, name):
        ctx = self.card.get_style_context()
        ctx.remove_class("dark")
        ctx.remove_class("light")
        ctx.add_class(name)

    def dismiss(self):
        if self.get_visible():
            self.hidden_at = time.time()
            self.hide()
        return False

    def toggle(self, x, y):
        if self.get_visible():
            self.dismiss()
            return
        if time.time() - self.hidden_at < 0.3:
            return
        self.place(x, y)
        self.show_all()
        self.present()

    def place(self, x, y):
        disp = Gdk.Display.get_default()
        mon = disp.get_monitor_at_point(x, y) or disp.get_primary_monitor() or disp.get_monitor(0)
        g = mon.get_geometry()
        left = max(6, min(x - WIDTH // 2, g.x + g.width - WIDTH - 6 - g.x))
        if self.layer:
            for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
                LS.set_anchor(self, e, False)
            LS.set_monitor(self, mon)
            bottom = y > g.y + g.height / 2
            LS.set_anchor(self, LS.Edge.BOTTOM if bottom else LS.Edge.TOP, True)
            LS.set_anchor(self, LS.Edge.LEFT, True)
            LS.set_margin(self, LS.Edge.LEFT, left)
            LS.set_margin(self, LS.Edge.BOTTOM if bottom else LS.Edge.TOP, 6)
        else:
            self.move(left, 40 if y < g.height / 2 else max(0, y - 500))
