#!/bin/sh
# Read-only check of a Monitor de Recursos T2 installation. Changes nothing.
fails=0
ok()  { printf '  OK    %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

echo "Package"
if pacman -Q monitor-t2 >/dev/null 2>&1; then ok "$(pacman -Q monitor-t2)"; else bad "monitor-t2 is not installed (run: makepkg -si)"; fi

echo "Apple SMC (applesmc_t2)"
smc=$(ls /sys/class/hwmon/hwmon*/device/fan1_manual 2>/dev/null | head -n 1)
if [ -n "$smc" ]; then ok "fan controls found: $smc"; else bad "no fan1_manual file: the kernel driver is not loaded or this is not an Apple SMC"; fi

echo "Root helper"
[ "$(systemctl is-active monitor-t2-fand 2>/dev/null)" = active ] && ok "monitor-t2-fand is active" || bad "monitor-t2-fand is not active"
[ "$(systemctl is-enabled monitor-t2-fand 2>/dev/null)" = enabled ] && ok "monitor-t2-fand is enabled at boot" || bad "monitor-t2-fand is not enabled"
[ -S /run/monitor-t2/fand.sock ] && ok "socket /run/monitor-t2/fand.sock exists" || bad "socket missing"

echo "Helper answers"
python3 -I - <<'PY' || fails=$((fails + 1))
import sys
sys.path.insert(0, '/usr/lib/monitor-t2')
try:
    from monitor_t2.data import fand
except ImportError:
    print('  FAIL  cannot import monitor_t2 (package not installed)'); sys.exit(1)
st, pw = fand({'cmd': 'status'}), fand({'cmd': 'power'})
if not (st and st.get('ok')):
    print('  FAIL  no answer to "status"'); sys.exit(1)
fans = ', '.join(f"fan {f['id']}: {f['rpm']} RPM ({f['min']}-{f['max']})" for f in st['fans'])
print(f"  OK    {len(st['fans'])} fan(s): {fans}")
smc = (pw or {}).get('smc', {})
if smc:
    print('  OK    SMC power readings: ' + ', '.join(f'{k}={v} W' for k, v in sorted(smc.items())))
else:
    print('  WARN  no SMC power keys read (yet): total system watts will show a dash')
PY

echo "Tray"
n=$(gdbus call --session --dest org.kde.StatusNotifierWatcher --object-path /StatusNotifierWatcher \
    --method org.freedesktop.DBus.Properties.Get org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems 2>/dev/null | grep -o "StatusNotifierItem'" | wc -l)
if [ "$n" -gt 0 ]; then ok "$n tray item(s) registered (includes other applications)"; else bad "no tray items (is the Plasma tray running?)"; fi
pgrep -f "python3 -m monitor_t2" >/dev/null && ok "app is running" || echo "  INFO  app is not running (start it with: monitor-t2)"

[ "$fails" -eq 0 ] && echo "All checks passed." || echo "$fails check(s) failed."
exit "$fails"
