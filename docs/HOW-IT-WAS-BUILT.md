# How it was built

Notes on how Monitor de Recursos T2 was put together. Everything here was observed on one machine (MacBookPro16,1, CachyOS, KDE Plasma 6.7 on Wayland, October 2026).

## Starting point

The idea was to get the look and the information of an open-source macOS menu-bar monitor on a T2 Mac running Linux. The macOS app is a universal Mach-O binary written in Swift (one framework per module: CPU, GPU, RAM, disk, network, battery, sensors, ...), so it cannot run on Linux. Instead of porting it, the binary's symbols and strings were used only to learn *what each module reads*, and each reading was re-implemented with the Linux interface that provides the same information. No code or artwork from that app is included.

## What replaces what

| Module | macOS call seen in the binary | Linux source used here |
| --- | --- | --- |
| CPU | `host_processor_info`, IOReport | `psutil` and `/proc`; temperatures from the SMC |
| RAM | `host_statistics64`, memory pressure | `psutil`; `/proc/pressure/memory` |
| Disk | IOBlockStorage, `statfs` | `psutil.disk_usage`, `disk_io_counters` |
| Network | `getifaddrs` | `psutil.net_io_counters` |
| Battery | `AppleSmartBattery` | `/sys/class/power_supply/BAT0` |
| GPU | `PerformanceStatistics` | `/sys/class/drm/card*/device/gpu_busy_percent` and the `amdgpu` hwmon power file |
| Sensors, fans | SMC | `applesmc_t2` files under `/sys/class/hwmon/hwmon*/device/` (`temp*_input`, `fan*_manual`, `fan*_output`) |
| Watts | SMC power keys | SMC keys through `key_at_index*` (read by the root helper), RAPL energy counters in `/sys/class/powercap` |

## Design decisions

- **A root helper for what needs root.** Fan writes, SMC key reads and RAPL counters need root. `monitor-t2-fand` is a small systemd service on a unix socket; the GUI runs as the user. Every connection is checked with `SO_PEERCRED`.
- **Fan control rules.** Requested speeds are clamped to the SMC's min/max. Manual mode is re-asserted every 2 s because the firmware can take control back. At 95 °C all fans go to maximum while keeping the chosen mode.
- **Battery percentage.** The kernel's `capacity` is relative to the *design* capacity. On a worn battery that reads 84 % when it is full, so the app uses `charge_now / charge_full`.
- **Watts per application.** There is no per-process power meter. CPU-package watts are split by each application's CPU use; GPU watts by per-process engine time from `/proc/<pid>/fdinfo` (DRM clients, own processes only). The fdinfo scan costs about 0.1 s, so it only runs while the "Consumo" popup is open.
- **SMC power keys** (`PSTR` system total, `PDTR` charger input, `PCPT` CPU package, `PCPC` cores, `PCPG` integrated graphics, `PPBR` battery) were read on this machine and gave plausible values (system about 32 W at light load). Other models may expose different keys.

## Traps found on KDE Plasma + Wayland

- `AppIndicator3` only gives a menu, not a left-click event. The tray icons are implemented directly with the `StatusNotifierItem` D-Bus protocol.
- Registering several items on the same D-Bus connection fails ("an object is already exported for the interface"). Each icon uses its own private bus connection.
- Plasma squeezes non-square tray icons, so every module gets its own square icon instead of one wide widget.
- Popups are anchored to the panel edge with `gtk-layer-shell`; a plain GTK window cannot position itself on Wayland.
- Taking a screenshot of a GTK window with `Gdk.pixbuf_get_from_window` returns a blank image on Wayland; `Gtk.OffscreenWindow.get_pixbuf()` works for tests.
- A manual fan mode that starts at the SMC minimum looks like "nothing happened"; the slider is in percent and starts at the current speed.
- A safeguard that falls back to automatic at 95 °C is the opposite of safe on a machine that already runs hot: automatic spins slower than "maximum". It forces maximum instead.
