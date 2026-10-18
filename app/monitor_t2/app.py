import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import draw, ui
from .config import MODULES, Config
from .data import Sampler, fand
from .tray import Item

LABELS = {"CPU": "CPU", "GPU": "GPU", "RAM": "Memoria RAM", "Disk": "Disco", "Network": "Red",
          "Battery": "Batería", "Power": "Consumo (vatios)", "Sensors": "Sensores y ventiladores", "Clock": "Reloj"}


def resolve_theme(setting):
    if setting in ("dark", "light"):
        return setting
    s = Gtk.Settings.get_default()
    name = (s.props.gtk_theme_name or "").lower()
    return "dark" if (s.props.gtk_application_prefer_dark_theme or "dark" in name) else "light"


class Settings(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Monitor T2 – Ajustes")
        self.app = app
        self.set_default_size(440, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("monitor-t2")
        nb = Gtk.Notebook()
        self.add(nb)
        cfg = app.cfg

        g = Gtk.Grid(column_spacing=12, row_spacing=10, margin=16)
        nb.append_page(g, Gtk.Label(label="General"))
        r = 0
        g.attach(Gtk.Label(label="Intervalo de actualización", xalign=0), 0, r, 1, 1)
        spin = Gtk.SpinButton.new_with_range(0.5, 10, 0.5)
        spin.set_value(cfg["interval"])
        spin.connect("value-changed", lambda s: cfg.__setitem__("interval", s.get_value()))
        g.attach(spin, 1, r, 1, 1)
        r += 1
        g.attach(Gtk.Label(label="Tema", xalign=0), 0, r, 1, 1)
        combo = Gtk.ComboBoxText()
        for k, t in (("auto", "Automático"), ("dark", "Oscuro"), ("light", "Claro")):
            combo.append(k, t)
        combo.set_active_id(cfg["theme"])
        combo.connect("changed", lambda c: (cfg.__setitem__("theme", c.get_active_id()), app.apply_theme()))
        g.attach(combo, 1, r, 1, 1)
        r += 1
        for text, key in (("Temperaturas en Fahrenheit", "fahrenheit"),
                          ("Restaurar el control de ventiladores al iniciar", "restore_fans")):
            g.attach(Gtk.Label(label=text, xalign=0), 0, r, 1, 1)
            sw = Gtk.Switch(halign=Gtk.Align.END)
            sw.set_active(cfg[key])
            sw.connect("notify::active", lambda s, _p, k=key: cfg.__setitem__(k, s.get_active()))
            g.attach(sw, 1, r, 1, 1)
            r += 1
        g.attach(Gtk.Label(label="Iniciar al arrancar la sesión", xalign=0), 0, r, 1, 1)
        sw = Gtk.Switch(halign=Gtk.Align.END)
        sw.set_active(cfg.autostart())
        sw.connect("notify::active", lambda s, _p: cfg.set_autostart(s.get_active()))
        g.attach(sw, 1, r, 1, 1)
        r += 1
        q = Gtk.Button(label="Salir")
        q.connect("clicked", lambda *_: app.quit())
        g.attach(q, 0, r + 1, 2, 1)

        m = Gtk.Grid(column_spacing=12, row_spacing=8, margin=16)
        nb.append_page(m, Gtk.Label(label="Módulos"))
        m.attach(Gtk.Label(label="Módulo", xalign=0, hexpand=True), 0, 0, 1, 1)
        m.attach(Gtk.Label(label="Activo"), 1, 0, 1, 1)
        m.attach(Gtk.Label(label="En la barra"), 2, 0, 1, 1)
        for i, name in enumerate(MODULES, 1):
            m.attach(Gtk.Label(label=LABELS[name], xalign=0), 0, i, 1, 1)
            for col, key in ((1, "modules"), (2, "tray")):
                sw = Gtk.Switch()
                sw.set_active(cfg[key][name])
                sw.connect("notify::active", lambda s, _p, k=key, n=name: app.set_flag(k, n, s.get_active()))
                m.attach(sw, col, i, 1, 1)

        f = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=16)
        nb.append_page(f, Gtk.Label(label="Ventiladores"))
        f.pack_start(Gtk.Label(label="El control de ventiladores se hace desde el popup de «Sensores»:\n"
                                     "Automático (firmware), Manual (porcentaje de velocidad por ventilador) o Frío (100 %).\n\n"
                                     "Requiere el servicio monitor-t2-fand (systemd). Si la CPU supera 95 °C el control\n"
                                     "vuelve a automático por seguridad.", xalign=0), False, False, 0)
        self.fand = Gtk.Label(xalign=0)
        f.pack_start(self.fand, False, False, 0)
        b = Gtk.Button(label="Devolver todos los ventiladores a automático")
        b.connect("clicked", lambda *_: self.reset_auto())
        f.pack_start(b, False, False, 0)
        self.refresh()

    def refresh(self):
        r = fand({"cmd": "status"})
        self.fand.set_text("Servicio monitor-t2-fand: activo ✔" if r and r.get("ok")
                           else "Servicio monitor-t2-fand: NO disponible ✘ (sudo systemctl enable --now monitor-t2-fand)")

    def reset_auto(self):
        fand({"cmd": "auto_all"})
        for k in self.app.cfg["fans"]:
            self.app.cfg["fans"][k]["mode"] = "auto"
        self.app.cfg.save()
        self.refresh()


class MonitorApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.MonitorT2", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.cfg = Config()
        self.sampler = Sampler()
        self.fan_error = None
        self.modules, self.popups, self.items = {}, {}, {}
        self.settings = None
        self.started = False

    # -- lifecycle -----------------------------------------------------------
    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        if not self.started:
            self.started = True
            self.setup()
        if "--settings" in args or (self.started and not args and self.items_ready()):
            pass
        if "--settings" in args:
            self.show_settings()
        self.hold_once()
        return 0

    _held = False

    def hold_once(self):
        if not self._held:
            self._held = True
            self.hold()

    def items_ready(self):
        return bool(self.items)

    def do_activate(self):
        pass

    def setup(self):
        ui.apply_css()
        self.apply_theme()
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sampler.sample()
        self.sampler.start(lambda: self.cfg["interval"])
        for name in MODULES:
            self.modules[name] = ui.MODULE_CLASSES[name](self)
            self.popups[name] = ui.Popup(self, self.modules[name])
        for name in MODULES:
            self.sync_tray(name)
        self.restore_fans()
        GLib.timeout_add(500, self.tick)
        self._last = 0.0

    def restore_fans(self):
        if not self.cfg["restore_fans"]:
            return
        sensors = self.modules["Sensors"]
        for fan in self.sampler.get().get("fans", []):
            if self.cfg["fans"].get(str(fan["id"]), {}).get("mode", "auto") != "auto":
                sensors.apply_fan(fan["id"], fan)

    def apply_theme(self):
        name = resolve_theme(self.cfg["theme"])
        draw.set_theme(name)
        for p in self.popups.values():
            p.set_theme(name)

    def set_flag(self, key, name, on):
        self.cfg[key][name] = on
        self.cfg.save()
        self.sync_tray(name)

    def sync_tray(self, name):
        want = self.cfg["modules"][name] and self.cfg["tray"][name]
        if want and name not in self.items:
            mod = self.modules[name]
            self.items[name] = Item(self.conn, name, mod.title,
                                    lambda x, y, n=name: self.toggle(n, x, y), self.show_settings)
        elif not want and name in self.items:
            self.items.pop(name).destroy()

    def toggle(self, name, x, y):
        if not self.cfg["modules"][name]:
            return False
        for n, p in self.popups.items():
            if n != name:
                p.dismiss()
        if not self.popups[name].get_visible():
            self.modules[name].update(self.sampler.get())
        self.popups[name].toggle(x, y)
        return False

    def show_settings(self, *_):
        if not self.settings:
            self.settings = Settings(self)
            self.settings.connect("delete-event", lambda w, e: (w.hide(), True)[1])
        self.settings.refresh()
        self.settings.show_all()
        self.settings.present()
        return False

    def tick(self):
        s = self.sampler.get()
        if not s:
            return True
        import time
        now = time.time()
        if now - self._last < self.cfg["interval"] - 0.05:
            return True
        self._last = now
        self.sampler.detail = self.popups["Power"].get_visible()
        for name, mod in self.modules.items():
            if name in self.items:
                label, value, frac, color = mod.tray(s)
                self.items[name].set(label, value, frac, color)
            if self.popups[name].get_visible():
                mod.update(s)
        return True

    def do_shutdown(self):
        Gtk.Application.do_shutdown(self)


def main():
    app = MonitorApp()
    return app.run(sys.argv)
