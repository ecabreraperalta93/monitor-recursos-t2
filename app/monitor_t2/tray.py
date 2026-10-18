"""StatusNotifierItem tray icons (one per module, like menu-bar widgets)."""
import os

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import draw

SNI_XML = """<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="OverlayIconName" type="s" access="read"/><property name="AttentionIconName" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="Menu" type="o" access="read"/>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewIcon"/><signal name="NewToolTip"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>"""
NODE = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
SIZE = 64


def render(label, value, frac, color):
    """Render the widget (label, value and usage bar) into raw ARGB32 bytes (network byte order)."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    cr = cairo.Context(surf)
    fg = draw.T["fg"]
    lines = value.split("\n")
    if len(lines) == 2:
        draw.text(cr, lines[0], SIZE / 2, 16, 25, fg, True, "c", "m")
        draw.text(cr, lines[1], SIZE / 2, 45, 25, fg, True, "c", "m")
    else:
        if label:
            draw.text(cr, label, SIZE / 2, 9, 17, draw.T["sub"], True, "c", "m")
        size = 30 if len(value) <= 3 else 25 if len(value) <= 4 else 20
        draw.text(cr, value, SIZE / 2, 33 if label else 30, size, fg, True, "c", "m")
        draw.rounded(cr, 4, 52, SIZE - 8, 7, 3.5)
        draw.rgba(cr, draw.T["track"])
        cr.fill()
        if frac > 0:
            draw.rounded(cr, 4, 52, max(7, (SIZE - 8) * min(1.0, frac)), 7, 3.5)
            draw.rgba(cr, color)
            cr.fill()
    surf.flush()
    d = surf.get_data()
    out = bytearray(len(d))
    out[0::4], out[1::4], out[2::4], out[3::4] = d[3::4], d[2::4], d[1::4], d[0::4]  # BGRA -> ARGB
    return bytes(out)


class Item:
    _n = 0

    def __init__(self, conn, module_name, title, on_activate, on_context):
        Item._n += 1
        # one private bus connection per item so each icon has its own (unique) bus name
        addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        conn = Gio.DBusConnection.new_for_address_sync(
            addr, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        self.conn = conn
        self.name = conn.get_unique_name()
        self.id = f"monitor-t2-{module_name}"
        self.title = f"Monitor T2 – {title}"
        self.key = None
        self.tip = title
        self.set_pixmap(render("", "…", 0, draw.BLUE))
        self.on_activate, self.on_context = on_activate, on_context
        self.reg = conn.register_object("/StatusNotifierItem", NODE.interfaces[0], self._call, self._get, None)
        GLib.timeout_add(300, self._register)

    def _register(self):
        try:
            self.conn.call_sync("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                                "org.kde.StatusNotifierWatcher", "RegisterStatusNotifierItem",
                                GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error as e:
            print("tray register failed:", e.message)
        return False

    def _call(self, conn, sender, path, iface, method, params, inv):
        if method == "Activate":
            x, y = params.unpack()
            GLib.idle_add(self.on_activate, x, y)
        elif method in ("ContextMenu", "SecondaryActivate"):
            GLib.idle_add(self.on_context)
        inv.return_value(None)

    def _get(self, conn, sender, path, iface, prop):
        V = GLib.Variant
        if prop == "Category":
            return V("s", "SystemServices")
        if prop == "Id":
            return V("s", self.id)
        if prop == "Title":
            return V("s", self.title)
        if prop == "Status":
            return V("s", "Active")
        if prop == "WindowId":
            return V("i", 0)
        if prop in ("IconName", "OverlayIconName", "AttentionIconName"):
            return V("s", "")
        if prop == "IconPixmap":
            return self.pixvar
        if prop == "ToolTip":
            return V("(sa(iiay)ss)", ("", [], self.tip, ""))
        if prop == "ItemIsMenu":
            return V("b", False)
        if prop == "Menu":
            return V("o", "/NO_DMENU")
        return None

    def set_pixmap(self, pix):
        # GLib.Variant("a(iiay)", ...) takes ~100 ms for a 16 KB icon (it walks the bytes in Python) and Plasma asks
        # for the property several times a second, which made the whole app use ~60 % of a core. Wrapping the
        # bytes directly costs ~0.05 ms and gives an identical value.
        ay = GLib.Variant.new_from_bytes(GLib.VariantType("ay"), GLib.Bytes.new(pix), True)
        tup = GLib.Variant.new_tuple(GLib.Variant("i", SIZE), GLib.Variant("i", SIZE), ay)
        self.pixvar = GLib.Variant.new_array(GLib.VariantType("(iiay)"), [tup])

    def set(self, label, value, frac, color, tip=""):
        key = (label, value, round(frac * 50), tuple(color), tip)  # skip redraws when nothing visible changed
        if key == self.key:
            return
        self.key = key
        self.set_pixmap(render(label, value, frac, color))
        self.tip = tip or self.title
        self.conn.emit_signal(None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewIcon", None)

    def destroy(self):
        try:
            self.conn.unregister_object(self.reg)
        except Exception:
            pass
