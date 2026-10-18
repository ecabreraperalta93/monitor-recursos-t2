"""Data layer: reads /proc, /sys and psutil. Equivalent of the Readers in Stats' modules."""
import glob
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections import deque

import psutil

HIST = 90
FAND_SOCKET = "/run/monitor-t2/fand.sock"

SMC_NAMES = {
    "TC0P": "CPU proximidad", "TC0E": "CPU 0E", "TC0F": "CPU 0F", "TCXC": "CPU PECI",
    "TCMX": "CPU máximo", "TCSA": "CPU System Agent", "TCGC": "CPU gráficos",
    "TG0P": "GPU proximidad", "TG1P": "GPU 1 proximidad", "TGDD": "GPU die", "TGDE": "GPU die E",
    "TGDF": "GPU die F", "TGVF": "GPU VRM F", "TGVP": "GPU VRM",
    "TB0T": "Batería 1", "TB1T": "Batería 2", "TB2T": "Batería 3",
    "TH0a": "SSD A", "TH0b": "SSD B", "TH1a": "SSD 1A", "TH1b": "SSD 1B", "TH0F": "SSD F", "TH0X": "SSD X",
    "TM0P": "Memoria", "Tm0P": "Placa base", "TPCD": "PCH", "TW0P": "Wi-Fi",
    "Ts0P": "Reposamuñecas izq.", "Ts1P": "Reposamuñecas der.", "Ts0S": "Superficie 0", "Ts1S": "Superficie 1",
    "Ts2S": "Superficie 2", "TaLC": "Aire izquierda", "TaRC": "Aire derecha", "TA0V": "Ambiente",
    "Th1H": "Heatpipe 1", "Th2H": "Heatpipe 2", "TTLD": "Thunderbolt izq.", "TTRD": "Thunderbolt der.",
}
for _i in range(1, 9):
    SMC_NAMES[f"TC{_i}C"] = f"CPU núcleo {_i}"


def rd(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def rd_int(path, default=None):
    v = rd(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def human(n, rate=False):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            s = f"{n:.0f}" if unit == "B" else f"{n:.1f}"
            return f"{s} {unit}" + ("/s" if rate else "")
        n /= 1024


def smc_dir():
    for p in glob.glob("/sys/class/hwmon/hwmon*/device/fan1_input"):
        return os.path.dirname(p)
    return None


def category(key):
    if key.startswith("TC"):
        return "CPU"
    if key.startswith("TG"):
        return "GPU"
    if key.startswith("TB"):
        return "Batería"
    if key.startswith("TH"):
        return "Almacenamiento"
    return "Sistema"


def turbo_state():
    """True if CPU turbo is on, False if off, None if it can't be controlled (not intel_pstate)."""
    try:
        with open("/sys/devices/system/cpu/intel_pstate/no_turbo") as f:
            v = f.read().strip()
    except OSError:
        return None
    return {"0": True, "1": False}.get(v)


def fand(request, timeout=1.5):
    """Send a request to the privileged fan daemon. Returns dict or None."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(FAND_SOCKET)
        s.sendall((json.dumps(request) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode())
    except (OSError, ValueError):
        return None


class Sampler:
    def __init__(self):
        self.lock = threading.Lock()
        self.snap = {}
        self.h = {k: deque([0.0] * HIST, maxlen=HIST) for k in (
            "cpu", "cpu_user", "cpu_sys", "gpu", "ram", "down", "up", "disk_r", "disk_w", "cpu_temp", "power")}
        self.smc = smc_dir()
        self._net = psutil.net_io_counters()
        self._dio = psutil.disk_io_counters()
        self._t = time.time()
        self._net_total = [0, 0]
        self._tick = 0
        self._procs = {}
        self.detail = False       # set by the UI while the Power popup is open (per-app GPU scan costs ~0.1 s)
        self._gpu_prev = (0.0, {})
        psutil.cpu_percent(None)
        self.running = True

    # --- readers -------------------------------------------------------
    def _smc_temps(self):
        out = []
        if not self.smc:
            return out
        for i in range(1, 80):
            lab = rd(f"{self.smc}/temp{i}_label")
            if lab is None:
                if not os.path.exists(f"{self.smc}/temp{i}_input"):
                    break
                continue
            v = rd_int(f"{self.smc}/temp{i}_input")
            if v is None or v <= 1000:
                continue
            out.append((lab, v / 1000.0))
        return out

    def _fans(self):
        out = []
        if not self.smc:
            return out
        for i in range(1, 6):
            if not os.path.exists(f"{self.smc}/fan{i}_input"):
                break
            out.append({
                "id": i,
                "name": ("Izquierdo", "Derecho")[i - 1] if i <= 2 else f"Ventilador {i}",
                "rpm": rd_int(f"{self.smc}/fan{i}_input", 0),
                "min": rd_int(f"{self.smc}/fan{i}_min", 0),
                "max": rd_int(f"{self.smc}/fan{i}_max", 0),
                "manual": rd_int(f"{self.smc}/fan{i}_manual", 0) == 1,
                "target": rd_int(f"{self.smc}/fan{i}_output", 0),
            })
        return out

    def _gpu(self):
        for card in sorted(glob.glob("/sys/class/drm/card[0-9]/device")):
            busy = rd(f"{card}/gpu_busy_percent")
            if busy is not None:
                vt, vu = rd_int(f"{card}/mem_info_vram_total"), rd_int(f"{card}/mem_info_vram_used")
                name = rd(f"{card}/product_name") or "AMD Radeon"
                slot = next((l.split("=", 1)[1] for l in (rd(f"{card}/uevent") or "").splitlines()
                             if l.startswith("PCI_SLOT_NAME=")), None)
                return {"name": name, "usage": float(busy), "vram_used": vu, "vram_total": vt, "pdev": slot,
                        "clock": (rd_int(glob.glob(f"{card}/hwmon/hwmon*/freq1_input")[0], 0) / 1e6)
                        if glob.glob(f"{card}/hwmon/hwmon*/freq1_input") else None,
                        "power": (rd_int(glob.glob(f"{card}/hwmon/hwmon*/power1_average")[0], 0) / 1e6)
                        if glob.glob(f"{card}/hwmon/hwmon*/power1_average") else None}
        if shutil.which("nvidia-smi"):
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2).stdout
                n, u, mu, mt = [x.strip() for x in o.splitlines()[0].split(",")]
                return {"name": n, "usage": float(u), "vram_used": int(mu) << 20, "vram_total": int(mt) << 20,
                        "clock": None, "power": None}
            except Exception:
                pass
        return None

    def _battery(self):
        base = next(iter(glob.glob("/sys/class/power_supply/BAT*")), None)
        if not base:
            return None
        cap = rd_int(f"{base}/capacity", 0)
        now_c = rd_int(f"{base}/energy_now") or rd_int(f"{base}/charge_now")
        full = rd_int(f"{base}/energy_full") or rd_int(f"{base}/charge_full")
        design = rd_int(f"{base}/energy_full_design") or rd_int(f"{base}/charge_full_design")
        volt = rd_int(f"{base}/voltage_now", 0) / 1e6
        cur = rd_int(f"{base}/current_now", 0) / 1e6
        pw = rd_int(f"{base}/power_now")
        watts = pw / 1e6 if pw is not None else abs(volt * cur)
        b = psutil.sensors_battery()
        ac = bool(b and b.power_plugged)
        status = rd(f"{base}/status", "")
        # `capacity` is relative to the design capacity; use charge_now / charge_full like KDE and UPower
        pct = 100.0 * now_c / full if now_c and full else cap
        if status == "Full":
            pct = 100.0
        return {
            "percent": max(0.0, min(pct, 100.0)), "ac": ac, "status": status, "full_state": status == "Full",
            "charging": status == "Charging", "secs": b.secsleft if b and b.secsleft > 0 else None,
            "health": 100.0 * full / design if full and design else None,
            "cycles": rd_int(f"{base}/cycle_count"), "volt": volt, "amps": abs(cur), "watts": watts,
            "temp": (rd_int(f"{base}/temp", 0) / 10.0) if rd(f"{base}/temp") else None,
            "full": full, "design": design,
        }

    def _active_iface(self):
        stats = psutil.net_if_stats()
        best, bestv = None, -1
        pern = psutil.net_io_counters(pernic=True)
        for n, st in stats.items():
            if n == "lo" or not st.isup or n.startswith(("docker", "veth", "br-", "virbr")):
                continue
            v = pern[n].bytes_recv + pern[n].bytes_sent if n in pern else 0
            if v > bestv:
                best, bestv = n, v
        return best

    # --- main sample -----------------------------------------------------
    def sample(self):
        now = time.time()
        dt = max(now - self._t, 1e-3)
        self._t = now
        self._tick += 1
        cpu_t = psutil.cpu_times_percent(None)
        cpu = 100.0 - cpu_t.idle
        per = psutil.cpu_percent(None, percpu=True)
        freq = psutil.cpu_freq()
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        net, dio = psutil.net_io_counters(), psutil.disk_io_counters()
        down, up = (net.bytes_recv - self._net.bytes_recv) / dt, (net.bytes_sent - self._net.bytes_sent) / dt
        dr = (dio.read_bytes - self._dio.read_bytes) / dt if dio else 0
        dw = (dio.write_bytes - self._dio.write_bytes) / dt if dio else 0
        self._net_total[0] += max(0, net.bytes_recv - self._net.bytes_recv)
        self._net_total[1] += max(0, net.bytes_sent - self._net.bytes_sent)
        self._net, self._dio = net, dio

        temps = self._smc_temps()
        td = dict(temps)
        cores = [td[k] for k in (f"TC{i}C" for i in range(1, 9)) if k in td]
        cpu_temp = sum(cores) / len(cores) if cores else td.get("TC0P")
        if cpu_temp is None:
            for h in glob.glob("/sys/class/hwmon/hwmon*"):
                if rd(f"{h}/name") == "coretemp":
                    cpu_temp = (rd_int(f"{h}/temp1_input", 0) or 0) / 1000.0

        procs_cpu, procs_mem = [], []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                i = p.info
                procs_cpu.append((i["name"], i["cpu_percent"] or 0.0))
                procs_mem.append((i["name"], i["memory_info"].rss if i["memory_info"] else 0))
            except psutil.Error:
                pass
        cpu_groups = {}
        for n, v in procs_cpu:
            cpu_groups[n] = cpu_groups.get(n, 0.0) + v
        procs_cpu.sort(key=lambda x: -x[1])
        procs_mem.sort(key=lambda x: -x[1])
        ncpu = psutil.cpu_count() or 1

        iface = self._active_iface()
        ip = None
        if iface:
            for a in psutil.net_if_addrs().get(iface, []):
                if a.family == socket.AF_INET:
                    ip = a.address
        gpu = self._gpu()
        bat = self._battery()
        power = self._power(gpu, bat, fand({"cmd": "power"}, timeout=0.8))
        power["apps"] = self._apps(power, gpu, cpu_groups, ncpu, now)
        disk = psutil.disk_usage("/")
        part = next((p for p in psutil.disk_partitions() if p.mountpoint == "/"), None)

        snap = {
            "cpu": cpu, "cpu_user": cpu_t.user + cpu_t.nice, "cpu_sys": cpu_t.system + cpu_t.irq + cpu_t.softirq,
            "cpu_idle": cpu_t.idle, "per": per, "freq": freq.current if freq else None, "ncpu": ncpu,
            "phys": psutil.cpu_count(logical=False), "load": os.getloadavg(), "cpu_temp": cpu_temp,
            "uptime": now - psutil.boot_time(),
            "top_cpu": [(n, v / ncpu) for n, v in procs_cpu[:5]], "top_mem": procs_mem[:5],
            "vm": vm, "sw": sw, "psi": self._psi(),
            "gpu": gpu, "gpu_temp": td.get("TG0P"),
            "disk": disk, "disk_name": (part.device if part else "/"), "disk_r": dr, "disk_w": dw,
            "down": down, "up": up, "net_total": tuple(self._net_total), "iface": iface, "ip": ip,
            "battery": bat, "power": power, "temps": temps, "fans": self._fans(), "turbo": turbo_state(),
        }
        for k, v in (("cpu", cpu), ("cpu_user", snap["cpu_user"]), ("cpu_sys", snap["cpu_sys"]),
                     ("gpu", gpu["usage"] if gpu else 0), ("ram", vm.percent), ("down", down), ("up", up),
                     ("disk_r", dr), ("disk_w", dw), ("cpu_temp", cpu_temp or 0),
                     ("power", power["system"] or 0)):
            self.h[k].append(v)
        with self.lock:
            self.snap = snap
        return snap

    @staticmethod
    def _power(gpu, bat, d):
        """Watts per source. Values missing on this machine stay None (the UI shows a dash).

        SMC keys (PSTR, PDTR, ...) and RAPL counters need root, so they come from the monitor-t2-fand daemon;
        the dGPU (amdgpu hwmon) and the battery (voltage x current) are read directly.
        """
        d = d if d and d.get("ok") else {}
        smc, rapl = d.get("smc", {}), d.get("rapl", {})
        batt_w = None
        if bat:
            batt_w = bat["watts"] if bat["charging"] else -bat["watts"] if bat["status"] == "Discharging" else 0.0
        system = smc.get("PSTR")
        src = "SMC (PSTR)" if system is not None else None
        if system is None and batt_w is not None and batt_w < 0:  # running on battery: its draw is the system power
            system, src = -batt_w, "batería"
        return {
            "daemon": bool(d), "system": system, "system_src": src, "dc_in": smc.get("PDTR"),
            "cpu_pkg": smc.get("PCPT", rapl.get("package")), "cpu_cores": smc.get("PCPC", rapl.get("core")),
            "cpu_igpu": smc.get("PCPG", rapl.get("uncore")), "dram": rapl.get("dram"),
            "gpu": gpu.get("power") if gpu else None,
            "battery": batt_w, "smc_keys": d.get("smc_keys_found", []), "smc": smc, "rapl": rapl,
        }

    def _gpu_procs(self, now):
        """Busy fraction per (GPU pci address, process name) from /proc/<pid>/fdinfo (own processes only)."""
        cur, names = {}, {}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                fds = os.listdir(f"/proc/{pid}/fdinfo")
            except OSError:
                continue
            for fd in fds:
                try:
                    txt = rd(f"/proc/{pid}/fdinfo/{fd}")
                except OSError:
                    continue
                if not txt or "drm-driver" not in txt:
                    continue
                info = {}
                for line in txt.splitlines():
                    k, _, v = line.partition(":")
                    info[k.strip()] = v.strip()
                ns = 0
                for k, v in info.items():
                    if k.startswith("drm-engine-") and not k.startswith("drm-engine-capacity"):
                        try:
                            ns += int(v.split()[0])
                        except (ValueError, IndexError):
                            pass
                key = (pid, info.get("drm-client-id", fd), info.get("drm-pdev", ""))
                cur[key] = ns
                if pid not in names:
                    names[pid] = rd(f"/proc/{pid}/comm") or pid
        pt, prev = self._gpu_prev
        self._gpu_prev = (now, cur)
        out = {}
        if pt and now > pt:
            for key, ns in cur.items():
                if key in prev and ns >= prev[key]:
                    busy = (ns - prev[key]) / 1e9 / (now - pt)
                    d = out.setdefault(key[2], {})
                    d[names[key[0]]] = d.get(names[key[0]], 0.0) + busy
        return out

    def _apps(self, power, gpu, cpu_groups, ncpu, now):
        """Estimated watts per application name: the whole CPU-package power is shared out by CPU use, the GPU
        power by GPU use.

        Linux has no per-process power meter, so these are shares of the measured watts (idle power is spread
        over the busy applications, so a share overstates what an app costs on top of an idle machine). Power
        that is neither CPU nor GPU (screen, SSD, fans) is not assigned to anyone.
        """
        pkg = power["cpu_pkg"]
        apps = {}
        total = sum(cpu_groups.values())
        if pkg is not None and total > 0:
            for n, v in cpu_groups.items():
                w = pkg * v / total
                if w >= 0.01:
                    apps[n] = [w, 0.0]
        if self.detail:
            dpdev = gpu.get("pdev") if gpu else None
            for pdev, per in self._gpu_procs(now).items():
                tot = sum(per.values())
                if tot <= 0:
                    continue
                if pdev == dpdev and gpu and gpu.get("power") is not None:
                    gw = gpu["power"] * gpu["usage"] / 100.0
                elif pdev != dpdev and power["cpu_igpu"] is not None:
                    gw = power["cpu_igpu"] * min(1.0, tot)
                else:
                    continue
                for n, b in per.items():
                    apps.setdefault(n, [0.0, 0.0])[1] += gw * b / tot
        rows = [{"name": n, "w": c + g, "cpu": c, "gpu": g} for n, (c, g) in apps.items() if c + g >= 0.05]
        rows.sort(key=lambda r: -r["w"])
        return {"rows": rows[:8], "has_cpu": pkg is not None, "gpu_scanned": self.detail}

    @staticmethod
    def _psi():
        txt = rd("/proc/pressure/memory")
        if txt:
            for line in txt.splitlines():
                if line.startswith("some"):
                    for part in line.split():
                        if part.startswith("avg10="):
                            return float(part[6:])
        return 0.0

    def get(self):
        with self.lock:
            return self.snap

    def start(self, interval_fn):
        def loop():
            while self.running:
                try:
                    self.sample()
                except Exception as e:  # keep sampling alive
                    print("sample error:", e)
                time.sleep(max(0.5, interval_fn()))
        threading.Thread(target=loop, daemon=True).start()
