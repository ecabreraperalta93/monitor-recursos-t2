# Monitor de Recursos T2

Monitor de recursos en la barra para **Macs con el chip Apple T2 que corren Linux**: un icono de bandeja por módulo (CPU, GPU, RAM, disco, red, batería, vatios, sensores) y, al hacer clic, un popup con anillos, gráficas y detalles. También controla los **ventiladores** (automático, porcentaje manual por ventilador o 100 %) y muestra el **consumo en vatios**, con una estimación por aplicación.

English: [README.md](README.md)

> Proyecto independiente, escrito desde cero. Se inspira en el aspecto de monitores de barra de macOS de código abierto como [Stats](https://github.com/exelban/stats) (MIT), pero no contiene su código ni sus gráficos y no tiene relación con ellos.

**Estado: probado en un solo equipo** - MacBookPro16,1 (16", 2019), CachyOS x86_64, kernel `7.2.9-2-cachyos`, KDE Plasma 6.7 en Wayland, octubre de 2026. Lo que no se verificó está en [Lo que se probó y lo que no](#lo-que-se-probó-y-lo-que-no).

## Qué incluye

| Módulo | Muestra |
| --- | --- |
| CPU | anillos de uso, historial, reparto usuario/sistema, frecuencia, carga media, procesos principales, interruptor de CPU Turbo |
| GPU | uso, VRAM, consumo (AMD con `amdgpu`; NVIDIA con `nvidia-smi`, sin probar) |
| RAM | uso, presión (PSI), caché, swap, procesos principales |
| Disco | uso, velocidad de lectura/escritura e historial |
| Red | bajada/subida e historial, interfaz, IP local |
| Batería | porcentaje (`charge_now / charge_full`), salud, ciclos, voltaje, corriente, potencia |
| Consumo (vatios) | potencia total del sistema, entrada del cargador, CPU, RAM, GPU dedicada y **vatios estimados por aplicación** |
| Sensores | ~50 temperaturas del SMC agrupadas (CPU / GPU / batería / almacenamiento / sistema) y **control de ventiladores** |
| Reloj | hora y calendario (desactivado en la barra por defecto) |

Modos de ventilador, independientes por ventilador: **Automático** (firmware), **Manual** (deslizador 0-100 %), **Frío** (100 %).

### Los vatios por aplicación son una estimación

Linux no tiene un medidor de consumo por proceso. La app reparte los vatios medidos del procesador según el uso de CPU de cada aplicación, y los de la GPU según el uso de GPU de cada una (se lee de `/proc/<pid>/fdinfo`, solo de tus procesos). Lo que ese reparto no explica (pantalla, SSD, ventiladores, reposo) no se asigna a nadie, así que la lista suma menos que el total del sistema.

## Requisitos

- Un Mac con **chip T2** y el controlador de kernel de t2linux `applesmc_t2` cargado (da los archivos de ventiladores, temperaturas y potencia en `/sys/class/hwmon/*/device/`).
- **Arch Linux o derivadas** (el paquete es un `PKGBUILD`): CachyOS, EndeavourOS, Manjaro...
- **KDE Plasma** en Wayland (los iconos usan el protocolo StatusNotifierItem; los popups usan `gtk-layer-shell`).
- Dependencias que instala `makepkg`: `python`, `python-gobject`, `python-cairo`, `python-psutil`, `gtk3`, `gtk-layer-shell`, `systemd`.

### ¿Funciona en otros sistemas?

| Sistema | Qué esperar | Probado |
| --- | --- | --- |
| MacBookPro16,1 + CachyOS + KDE Wayland | Todo lo anterior | Sí |
| Otros Mac con T2 (mismo `applesmc_t2`) | Probablemente todo; los nombres de sensores están escritos para el 16,1 y las claves desconocidas salen sin traducir | No |
| Mac Intel sin T2 (`applesmc` estándar) | Mismos nombres de archivo, así que podría funcionar | No |
| PC que no son Apple | El monitor básico (CPU, RAM, disco, red, batería, GPU AMD) probablemente funcione, pero el servicio root se cierra sin el SMC de Apple: sin ventiladores ni vatios | No |
| GNOME | La bandeja necesita una extensión AppIndicator; los popups no se anclan | No |
| Apple Silicon (Asahi) | No soportado | No |

## Instalación

```bash
sudo pacman -S --needed base-devel git
git clone https://github.com/ecabreraperalta93/monitor-recursos-t2.git
cd monitor-recursos-t2
makepkg -si
```

`makepkg -si` pide tu contraseña de sudo, instala las dependencias y el paquete, y activa el servicio `monitor-t2-fand` (el ayudante root para ventiladores y lecturas de potencia). Después abre la app desde el menú de aplicaciones («Monitor de Recursos T2») o ejecuta:

```bash
monitor-t2
```

Los iconos aparecen en la bandeja de Plasma. Los ajustes (intervalo, tema, qué módulos van en la barra, inicio con la sesión) se abren desde el engranaje de cualquier popup o desde la entrada del menú, y se guardan en `~/.config/monitor-t2/config.json`.

Para reiniciar la app tras una actualización:

```bash
pkill -f "python3 -m monitor_t2"; setsid monitor-t2 >/dev/null 2>&1 &
```

Para comprobar la instalación (solo lectura):

```bash
./scripts/check.sh
```

## El ayudante root (`monitor-t2-fand`)

Los ventiladores, las claves de potencia del SMC y los contadores de energía RAPL requieren root, así que un pequeño servicio de systemd hace ese trabajo:

- Escucha en `/run/monitor-t2/fand.sock`. El archivo del socket es escribible por todos a propósito; **cada conexión se comprueba con `SO_PEERCRED` y solo se atiende a root y a miembros de `wheel`**. Cambia `GROUP` en `app/monitor-t2-fand` si tu usuario no está en `wheel`.
- La velocidad de los ventiladores siempre se limita al mínimo y máximo que informa el SMC.
- Si el CPU llega a 95 °C, el servicio pone todos los ventiladores al máximo (y conserva el modo elegido para retomarlo al enfriarse).
- Al detenerse el servicio, devuelve los ventiladores a automático.
- Se cierra al arrancar si no existe el archivo `fan1_manual` (sin SMC de Apple).

**Úsalo bajo tu responsabilidad.** El servicio escribe en controles de hardware como root. No dejes los ventiladores por debajo de lo que tu equipo necesita.

## Lo que se probó y lo que no

Probado en el equipo de referencia (con la versión local anterior de este mismo código, antes del cambio de nombre):

- Instalación con `makepkg -si`; el servicio arranca y el socket responde.
- Iconos de bandeja registrados en Plasma (7 en ese momento, antes del módulo de vatios); los popups se abren anclados al panel.
- El ventilador 1 en manual a 3500 RPM llegó a ~3500 RPM en unos 12 s; volver a automático funcionó; pedir 999999 RPM se recortó al máximo.
- Lecturas reales con el servicio: potencia del sistema desde el SMC `PSTR` (unos 32 W), paquete de CPU desde `PCPT`, RAPL package/core/uncore/dram, potencia de la GPU dedicada desde `amdgpu`.
- Vatios por aplicación con esas lecturas reales, usando un proceso de prueba que consume CPU.
- Porcentaje de batería: el `capacity` del kernel es relativo a la capacidad de *diseño* y marcaba 84 % con la batería llena; la app usa `charge_now / charge_full`.

No probado, o no repetido tras los últimos cambios:

- **Esta versión renombrada ya instalada** (paquete `monitor-t2`, servicio `monitor-t2-fand`, migración de ajustes desde el nombre anterior). Solo se comprobó compilación, construcción del paquete y renderizado fuera de pantalla.
- El seguro de 95 °C tras corregirlo (una versión anterior volvía a automático y hacía que el modo «Frío» se apagara solo a los ~10 s).
- El ventilador 2 por separado, el modo «Manual» con el deslizador de porcentaje desde el popup, suspender/reanudar con ventiladores en manual, inicio con la sesión, Fahrenheit.
- El interruptor de CPU Turbo (escribe `/sys/devices/system/cpu/intel_pstate/no_turbo` a través del servicio).
- Los popups de GPU, Disco y Reloj solo se renderizaron fuera de pantalla.
- NVIDIA, cualquier otro modelo de Mac, cualquier otro escritorio.

## Desinstalar

```bash
sudo pacman -Rns monitor-t2     # también desactiva el servicio monitor-t2-fand
rm -r ~/.config/monitor-t2
```

Si un ventilador queda fuera de automático: `echo 0 | sudo tee /sys/class/hwmon/hwmon*/device/fan*_manual`.

## Cómo se hizo

Ver [docs/HOW-IT-WAS-BUILT.md](docs/HOW-IT-WAS-BUILT.md) (en inglés): qué interfaz de Linux sustituye cada lectura de macOS y las trampas encontradas en KDE con Wayland.

## Licencia

MIT - ver [LICENSE](LICENSE).
