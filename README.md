# Monitor de Recursos T2

A menu-bar resource monitor for **Macs with the Apple T2 chip running Linux**: one tray icon per module (CPU, GPU, RAM, disk, network, battery, watts, sensors) and, when you click it, a popup with rings, charts and details. It also controls the **fans** (automatic, manual percentage per fan, or 100 %) and shows **power draw in watts**, including an estimate per application.

Español: [README.es.md](README.es.md)

> Independent project, written from scratch. It is inspired by the look of open-source macOS menu-bar monitors such as [Stats](https://github.com/exelban/stats) (MIT) but contains none of their code or artwork, and it is not affiliated with them.

**Status: tested on one machine only** - MacBookPro16,1 (16" 2019), CachyOS x86_64, kernel `7.2.9-2-cachyos`, KDE Plasma 6.7 on Wayland, October 2026. Anything not verified is listed under [What was and was not tested](#what-was-and-was-not-tested).

## What you get

| Module | Shows |
| --- | --- |
| CPU | usage rings, history, user/system split, frequency, load average, top processes, CPU Turbo switch |
| GPU | usage, VRAM, power (AMD through `amdgpu`; NVIDIA through `nvidia-smi`, untested) |
| RAM | usage, pressure (PSI), cache, swap, top processes |
| Disk | usage, read/write rate and history |
| Network | download/upload and history, interface, local IP |
| Battery | percentage (`charge_now / charge_full`), health, cycles, voltage, current, power |
| Power (watts) | total system power, charger input, CPU package, RAM, dGPU, and **estimated watts per application** |
| Sensors | ~50 SMC temperatures grouped by CPU / GPU / battery / storage / system, and **fan control** |
| Clock | time and calendar (off in the tray by default) |

Fan modes, per fan and independent: **Automatic** (firmware), **Manual** (slider 0-100 %), **Cool** (100 %).

### Watts per application is an estimate

Linux has no per-process power meter. The app shares out the measured CPU-package watts among applications by CPU use, and the measured GPU watts by GPU use (read from `/proc/<pid>/fdinfo`, your own processes only). Idle power is spread over the busy applications, so a share overstates what an app costs on top of an idle machine; power that is neither CPU nor GPU (screen, SSD, fans) is not assigned to anyone.

## Requirements

- A Mac with the **T2 chip** and the t2linux kernel driver `applesmc_t2` loaded (it provides the fan, temperature and power files under `/sys/class/hwmon/*/device/`).
- **Arch Linux or a derivative** (the package is a `PKGBUILD`): CachyOS, EndeavourOS, Manjaro...
- **KDE Plasma** on Wayland (tray icons use the StatusNotifierItem protocol; popups use `gtk-layer-shell`).
- Dependencies installed by `makepkg`: `python`, `python-gobject`, `python-cairo`, `python-psutil`, `gtk3`, `gtk-layer-shell`, `systemd`.

### Will it work on other systems?

| System | What to expect | Tested |
| --- | --- | --- |
| MacBookPro16,1 + CachyOS + KDE Wayland | Everything above | Yes |
| Other T2 Macs (same `applesmc_t2` driver) | Probably everything; sensor names are written for the 16,1 and unknown keys show raw | No |
| Intel Macs without T2 (mainline `applesmc`) | Same file names, so it may work | No |
| Non-Apple PCs | The basic monitor (CPU, RAM, disk, network, battery, AMD GPU) would probably work, but the root service exits without the Apple SMC, so no fans and no watts | No |
| GNOME | The tray needs an AppIndicator extension; popups are not anchored | No |
| Apple Silicon (Asahi) | Not supported | No |

## Install

```bash
sudo pacman -S --needed base-devel git
git clone https://github.com/ecabreraperalta93/monitor-recursos-t2.git
cd monitor-recursos-t2
makepkg -si
```

`makepkg -si` asks for your sudo password, installs the dependencies and the package, and enables the `monitor-t2-fand` service (the root helper for fans and power readings). Then start the app from the application menu ("Monitor de Recursos T2") or run:

```bash
monitor-t2
```

The tray icons appear in the Plasma system tray. Settings (interval, theme, which modules show in the tray, launch at login) open from the gear in any popup or from the menu entry, and are stored in `~/.config/monitor-t2/config.json`.

To restart the app after an update:

```bash
pkill -f "python3 -m monitor_t2"; setsid monitor-t2 >/dev/null 2>&1 &
```

Check the installation (read-only):

```bash
./scripts/check.sh
```

## The root helper (`monitor-t2-fand`)

Fans, SMC power keys and RAPL energy counters need root, so a small systemd service does that work:

- It listens on `/run/monitor-t2/fand.sock`. The socket file is world-writable on purpose; **each connection is checked with `SO_PEERCRED` and only root and members of `wheel` are served**. Change `GROUP` in `app/monitor-t2-fand` if your user is not in `wheel`.
- Fan speeds are always clamped to the minimum and maximum the SMC reports.
- If the CPU reaches 95 °C the daemon forces all fans to maximum speed (and keeps your chosen mode so it resumes when the CPU cools down).
- When the service stops, it hands the fans back to automatic.
- It exits at start-up if there is no `fan1_manual` file (no Apple SMC).

**Use at your own risk.** The service writes to hardware controls as root. Do not leave fans below what your machine needs.

## What was and was not tested

Tested on the reference machine (with the earlier local build of this same code, before the rename):

- Install with `makepkg -si`; the service starts and the socket answers.
- Tray icons registered with Plasma (7 at the time, before the watts module existed); popups open anchored to the panel.
- Fan 1 manual at 3500 RPM reached ~3500 RPM in about 12 s; going back to automatic worked; asking for 999999 RPM was clamped to the maximum.
- Real readings with the service: system power from SMC `PSTR` (about 32 W), CPU package from `PCPT`, RAPL package/core/uncore/dram, dGPU power from `amdgpu`.
- Per-application watts against those real readings, with a CPU-burning test process.
- Battery percentage: the kernel's `capacity` is relative to the *design* capacity and showed 84 % on a full battery; the app uses `charge_now / charge_full` instead.

Not tested, or not re-checked after the last changes:

- **This renamed build as installed** (package `monitor-t2`, service `monitor-t2-fand`, config migration from the earlier local name). Only compilation, a package build and offscreen rendering were checked.
- The 95 °C safeguard after it was fixed (an earlier version fell back to automatic, which made the "Cool" mode stop by itself after ~10 s).
- Fan 2 on its own, "Manual" with the percentage slider from the popup, suspend/resume with fans in manual, launch at login, Fahrenheit.
- The CPU Turbo switch (it writes `/sys/devices/system/cpu/intel_pstate/no_turbo` through the service).
- The GPU, Disk and Clock popups were only rendered offscreen.
- NVIDIA, any other Mac model, any other desktop.

## Uninstall

```bash
sudo pacman -Rns monitor-t2     # also disables the monitor-t2-fand service
rm -r ~/.config/monitor-t2
```

If a fan is stuck out of automatic: `echo 0 | sudo tee /sys/class/hwmon/hwmon*/device/fan*_manual`.

## How it was built

See [docs/HOW-IT-WAS-BUILT.md](docs/HOW-IT-WAS-BUILT.md): which Linux interface replaces each macOS reading, and the traps found on KDE Wayland.

## License

MIT - see [LICENSE](LICENSE).
