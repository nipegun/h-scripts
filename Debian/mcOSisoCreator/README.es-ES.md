# Creador de ISO Recovery de macOS para Debian

## Ejecutar directamente con curl

```sh
curl -fsSL https://raw.githubusercontent.com/nipegun/h-scripts/main/Debian/mcOSisoCreator/mcOSisoCreator.py | python3 - --language es-ES --install-deps
```

Requiere Debian 13 y Python 3.13 o posterior. Si falta curl: `sudo apt install curl ca-certificates python3`. El lanzador descarga el paquete de código desde este repositorio, verifica el SHA-256 incorporado y abre el menú en `/dev/tty`. Las ISO quedan en `./mcOSisoCreator/ISOs/` y las descargas reutilizables en `./mcOSisoCreator/_/temp/macos-iso/`. No hace falta clonar el repositorio ni instalar paquetes de pip. `--install-deps` permite instalar xorriso y 7zip mediante apt/sudo.

Para elegir otra carpeta, añade `--directory /ruta/mcOSisoCreator`; para automatizarlo, añade `--os Tahoe --non-interactive`. Las opciones se escriben después de `python3 -`. Con `--launcher-help` se muestran las opciones del lanzador y con `--help`, las del creador.

Ejecuta el creador interactivo desde la carpeta del proyecto:

```sh
python3 Scripts/create_macos_iso.py --language es-ES --install-deps
```

Selecciona una familia de macOS o escribe una versión. El programa solicita los archivos directamente a Apple, comprueba su firma RSA y todos los bloques de la imagen, lee la versión real, genera una ISO óptica y vuelve a verificar el contenido HFS+ de la ISO terminada.

**Son ISO de recuperación.** La instalación necesita Internet y una EFI OpenCore independiente adecuada para la VM. Este proceso de Debian no crea el instalador completo sin conexión de Apple ni una EFI universal.

## Requisitos

Debian 13, Python 3.13 o posterior, `xorriso` y `7zip` actual. No necesitas paquetes de pip ni tener macOS instalado. `--install-deps` permite instalar mediante apt los paquetes que falten, usando sudo cuando corresponda. La creación normal no requiere root y nunca formatea discos ni particiones.

```sh
sudo apt install python3 xorriso 7zip
```

## Funciones automatizadas

1. Selección interactiva o por comandos: familia, nombre o revisión exacta.
2. Consulta a Apple, verificación de la chunklist firmada y reanudación desde bloques autenticados.
3. Detección de la versión real, rechazando otra familia o una revisión distinta de la solicitada expresamente.
4. Creación ISO9660/APM/HFS+ y comprobación del volumen HFS+ de arranque, incluyendo de nuevo las firmas de Apple.
5. SHA-256 y procedencia JSON, reutilización de caché, verificación independiente, diagnóstico y cuatro idiomas.

## Versiones

El catálogo incluye identificadores de recuperación de Apple para Lion 10.7, Mountain Lion, Mavericks, Yosemite, El Capitan, Sierra, High Sierra, Mojave, Catalina, Big Sur, Monterey, Ventura, Sonoma, Sequoia y Tahoe 26. La disponibilidad depende de Apple; los identificadores antiguos pueden dejar de funcionar.

**10.0–10.6 no tienen descarga automática de recuperación por Internet.** El programa informa de que necesitas un medio original, sin sustituirlo por una descarga sin verificar. Apple tampoco ofrece todas las revisiones históricas. `--os 26.6.2` exige que la recuperación contenga exactamente 26.6.2; `--os 26` acepta la revisión disponible de Tahoe y nombra la ISO con la versión detectada.

## Ejemplos

```sh
python3 Scripts/create_macos_iso.py --language es-ES
python3 Scripts/create_macos_iso.py --list --language es-ES
python3 Scripts/create_macos_iso.py --os 26.6.2 --non-interactive --language es-ES
python3 Scripts/create_macos_iso.py --os Mojave --probe --json
python3 Scripts/create_macos_iso.py --verify ISOs/macOS_Tahoe_26.6.2_25G83_Recovery.iso --language es-ES
```

Los resultados se guardan en `ISOs/`; los temporales y las descargas reutilizables, en `_/temp/macos-iso/`. Conserva junta toda la carpeta de la herramienta, incluidos `Scripts/macos_iso`, `Sources/macos-recovery-versions.json` y `Locales/macos_iso`.

## Comprobaciones realizadas

Se han descargado, autenticado y empaquetado en Debian recuperaciones reales de Apple para **10.7.5 (11G63), 10.14.6 (18G87) y 26.6.2 (25G83)**. La ISO de Tahoe se verificó también de forma independiente y OpenCore detectó su entrada en QEMU/OVMF. No se probó localmente una instalación completa del invitado. **38 pruebas automáticas pasan**, incluidos archivos manipulados, reanudación, política de URL y versiones incorrectas.

Apple sirve algunos archivos de recuperación por HTTP. La consulta utiliza HTTPS; la chunklist firmada y los hashes autenticados proporcionan la verificación del contenido. `--https-only` rechaza archivos HTTP; nunca se desactiva la validación de certificados TLS. Los campos `AH` y `CH` del servicio no se utilizan como checksums de archivos.

[Manual](MANUAL.es-ES.md) · [Referencia técnica](CODE.es-ES.md) · [English](README.md) · [Español de Argentina](README.es-AR.md)
