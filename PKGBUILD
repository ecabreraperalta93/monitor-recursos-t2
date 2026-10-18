# Maintainer: ecabreraperalta93
pkgname=monitor-t2
pkgver=1.0.0
pkgrel=1
pkgdesc="Menu-bar resource monitor for T2 Macs on Linux: CPU, GPU, RAM, disk, network, battery, watts, sensors and fan control"
arch=('any')
url="https://github.com/ecabreraperalta93/monitor-recursos-t2"
license=('MIT')
depends=('python' 'python-gobject' 'python-cairo' 'python-psutil' 'gtk3' 'gtk-layer-shell' 'systemd')
conflicts=('stats-linux')
replaces=('stats-linux')
install=monitor-t2.install

package() {
  cd "$startdir"
  install -d "$pkgdir/usr/lib/monitor-t2"
  cp -r app/monitor_t2 "$pkgdir/usr/lib/monitor-t2/"
  find "$pkgdir/usr/lib/monitor-t2" -name __pycache__ -prune -exec rm -rf {} +
  install -Dm755 app/monitor-t2-fand "$pkgdir/usr/lib/monitor-t2/monitor-t2-fand"
  install -Dm755 app/monitor-t2 "$pkgdir/usr/bin/monitor-t2"
  install -Dm644 app/monitor-t2-fand.service "$pkgdir/usr/lib/systemd/system/monitor-t2-fand.service"
  install -Dm644 app/monitor-t2.desktop "$pkgdir/usr/share/applications/monitor-t2.desktop"
  install -Dm644 assets/monitor-t2.png "$pkgdir/usr/share/icons/hicolor/256x256/apps/monitor-t2.png"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/monitor-t2/LICENSE"
}
