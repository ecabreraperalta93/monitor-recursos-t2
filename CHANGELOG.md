# Changelog

## 1.1.0 - 2026-10-18 - Power consumption

Everything in this release is about watts.

### Added
- **"Consumo" (watts) module** with its own tray icon (`WATT`, total system watts) and popup.
- Popup with the **applications first**: name, proportional bar and estimated watts for the top 12, then totals (system, charger input, CPU package, RAM, dedicated GPU) and a history chart.
- **Watts per application (estimate).** The whole CPU-package power is shared among applications by their share of CPU time; the dedicated/integrated GPU power by per-process GPU engine time read from `/proc/<pid>/fdinfo` (your own processes, scanned only while the popup is open). Linux has no per-process power meter, so these are shares, and idle power is spread over the busy applications.
- The root helper now reads **SMC power keys** (`PSTR` system total, `PDTR` charger input, `PCPT`/`PCPC`/`PCPG` CPU package/cores/graphics, `PPBR`) and **RAPL** energy counters (package, core, uncore, DRAM) and serves them through the new `power` command.
- If the helper is not running the popup says so and falls back to GPU and battery watts.

### Fixed
- The Power popup was 834 px wide instead of 300 because its wrapped explanation text had no maximum width, which pushed the watts column off the right edge of the screen. Wrapped labels are now limited (also in Sensors).
- The app itself used about 60 % of a CPU core: building the tray icon `GLib.Variant` from 16 KB of pixels took ~100 ms and Plasma asks for it several times per second. It is now built from the raw bytes (~0.05 ms, identical value) and unchanged icons are not redrawn. Measured on the reference machine: ~62 % to ~6.5 % of one core.
- A first version of the per-application split left almost every application below the display threshold at idle; the split was reworked.

### Not verified
- The 95 degC safeguard after its earlier fix, fan 2 on its own, the Turbo switch, the GPU/Disk/Clock popups on screen, and anything on other hardware. See the README.

## 1.0.0 - 2026-10-18 - First release

CPU, GPU, RAM, disk, network, battery, sensors and clock modules; tray icon per module; popups; fan control (automatic, manual percentage per fan, 100 %) through a root helper; battery percentage computed as `charge_now / charge_full`.
