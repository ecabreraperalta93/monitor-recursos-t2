import copy
import json
import os
import shutil

DIR = os.path.expanduser("~/.config/monitor-t2")
PATH = DIR + "/config.json"
AUTOSTART = os.path.expanduser("~/.config/autostart/monitor-t2.desktop")

MODULES = ["CPU", "GPU", "RAM", "Disk", "Network", "Battery", "Power", "Sensors", "Clock"]

DEFAULT = {
    "interval": 1.0,
    "theme": "auto",          # auto | dark | light
    "modules": {m: True for m in MODULES},
    "tray": {m: (m != "Clock") for m in MODULES},
    "fahrenheit": False,
    "fans": {},               # "1": {"mode": "auto|manual|curve", "rpm": 3000, "curve": {...}}
    "restore_fans": True,
}
DEFAULT_CURVE = {"tmin": 55.0, "tmax": 90.0, "pmin": 0.0, "pmax": 100.0}


OLD_PATH = os.path.expanduser("~/.config/stats-linux/config.json")  # name used by earlier local builds


class Config:
    def __init__(self):
        if not os.path.exists(PATH) and os.path.exists(OLD_PATH):  # one-time migration of earlier settings
            os.makedirs(DIR, exist_ok=True)
            shutil.copyfile(OLD_PATH, PATH)
        self.d = copy.deepcopy(DEFAULT)
        try:
            with open(PATH) as f:
                self._merge(self.d, json.load(f))
        except (OSError, ValueError):
            pass

    @staticmethod
    def _merge(base, new):
        for k, v in new.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def save(self):
        os.makedirs(DIR, exist_ok=True)
        with open(PATH, "w") as f:
            json.dump(self.d, f, indent=2)

    def __getitem__(self, k):
        return self.d[k]

    def __setitem__(self, k, v):
        self.d[k] = v
        self.save()

    def temp(self, c):
        return (f"{c * 9 / 5 + 32:.0f}°F" if self.d["fahrenheit"] else f"{c:.0f}°C")

    # launch at login
    def autostart(self):
        return os.path.exists(AUTOSTART)

    def set_autostart(self, on):
        if on:
            os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
            with open(AUTOSTART, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Monitor de Recursos T2\nExec=monitor-t2\n"
                        "Icon=monitor-t2\nX-GNOME-Autostart-enabled=true\n")
        else:
            try:
                os.unlink(AUTOSTART)
            except OSError:
                pass
