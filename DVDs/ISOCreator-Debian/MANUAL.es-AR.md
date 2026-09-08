# Manual de uso

## Ejecutar directamente con curl

```sh
curl -fsSL https://raw.githubusercontent.com/nipegun/h-scripts/main/Debian/ISOCreator/ISOCreator.py | python3 - --language es-AR --install-deps
```

Requiere Debian 13 y Python 3.13 o posterior. Si falta curl: `sudo apt install curl ca-certificates python3`. El lanzador descarga el paquete de código desde este repositorio, verifica el SHA-256 incorporado y abre el menú en `/dev/tty`. Las ISO quedan en `./ISOCreator/ISOs/` y las descargas reutilizables en `./ISOCreator/_/temp/macos-iso/`. No hace falta clonar el repositorio ni instalar paquetes de pip. `--install-deps` permite instalar xorriso y 7zip mediante apt/sudo.

Para elegir otra carpeta, añade `--directory /ruta/ISOCreator`; para automatizarlo, añade `--os Tahoe --non-interactive`. Las opciones se escriben después de `python3 -`. Con `--launcher-help` se muestran las opciones del lanzador y con `--help`, las del creador.

El programa se guarda por contenido en `ISOCreator/_/temp/bootstrap/runtime-<SHA256>/`. Al repetir el comando, verifica y reutiliza ese código; una versión nueva usa otra carpeta sin borrar las ISO ni la caché de Apple. No edites esa copia verificada: para desarrollar, usa los fuentes del repositorio. Si la copia del código está dañada, el lanzador se detiene e indica el archivo. Una carpeta nueva con `--directory` permite descargar una copia limpia.

El SHA-256 del paquete comprueba el código que declara este lanzador, no constituye una firma independiente de Apple. Ejecutar el comando confía en el repositorio y en el lanzador servido por GitHub mediante HTTPS. Las firmas de Apple se comprueban después sobre los archivos de recuperación. No se requiere token de GitHub. Sin terminal hay que especificar `--os` y `--non-interactive`.

## Uso interactivo

Ejecutá `python3 Scripts/create_macos_iso.py --language es-AR --install-deps` desde la carpeta extraída del proyecto. Elegí un número, un nombre como `Tahoe` o una versión exacta como `10.7.5`. El idioma predeterminado es en-US; también se admiten en-GB, es-ES y es-AR. Introducí `0` para cancelar el menú.

Después de seleccionar la versión se ejecutan seis etapas: consulta a Apple, verificación de la firma, descarga y verificación de la imagen, lectura de la versión, creación de ISO y comprobación del contenido HFS+ de la ISO terminada. Si faltan dependencias, se ofrece instalarlas mediante apt en una terminal interactiva. `--install-deps` autoriza ese paso de antemano; sudo puede pedir tu contraseña local. No se utiliza una cuenta de GitHub.

Es un **creador de ISO de recuperación**. Ese entorno instala macOS mediante Internet. No crea un instalador completo sin conexión. En Proxmox sigue siendo necesaria una EFI OpenCore adecuada para la VM; el script no genera una EFI universal.

## Selección y disponibilidad

`--list` muestra el catálogo. Hay identificadores de recuperación de Apple desde Lion 10.7 hasta Tahoe 26. Los sistemas anteriores aparecen como no disponibles porque preceden a Internet Recovery. También se admiten archivos DMG y chunklist de recuperación ya descargados y firmados; no existe una opción para saltarse la firma.

Seleccionar una familia, como `26`, permite usar la revisión de recuperación disponible de esa familia. Seleccionar `26.6.2` exige que esa sea la versión dentro de la imagen autenticada. Apple puede ofrecer otra revisión o retirar un identificador. El script rechaza familias o revisiones exactas que no coincidan y nunca cambia el nombre de otra imagen para simular la solicitada. `latest` pide la recuperación más reciente que Apple ofrece para el modelo Intel documentado; lee siempre la versión detectada. La versión del entorno de recuperación no garantiza qué revisión ofrecerá después el instalador de Apple.

## Comandos habituales

```sh
# Menú en español
python3 Scripts/create_macos_iso.py --language es-AR --install-deps

# Recuperación de una versión exacta, sin preguntas
python3 Scripts/create_macos_iso.py --os 26.6.2 --non-interactive --language es-AR

# Planificación sin acceder a la red
python3 Scripts/create_macos_iso.py --os 10.14 --dry-run --language es-AR

# Consultar los metadatos y verificar la firma sin descargar el DMG
python3 Scripts/create_macos_iso.py --os 10.7 --probe --json

# Comprobar herramientas locales
python3 Scripts/create_macos_iso.py --doctor --language es-AR
```

En modo no interactivo, las dependencias ausentes producen un error claro salvo que se indique `--install-deps`. Si sudo necesitara una contraseña, la instalación no interactiva falla en lugar de esperar una entrada oculta.

## Archivos de salida y caché

Cada creación terminada deja en `ISOs/`:

| Archivo | Contenido |
| --- | --- |
| `macOS_NOMBRE_VERSION_BUILD_Recovery.iso` | ISO óptica con la recuperación y los archivos firmados de Apple |
| Mismo nombre terminado en `.json` | Versión real, origen sin tokens, alcance de la firma y checksums |
| Mismo nombre más `.sha256` | Checksum de integridad de la ISO para copiarla a otro equipo |

La ISO incluye ISO9660 y HFS+ con un mapa de particiones Apple. En su HFS+ solo hay `com.apple.recovery.boot/BaseSystem.dmg`, su `.chunklist` firmada, una etiqueta para el menú y `BUILDINFO.json`. El DMG no se modifica. No se incrusta un ejecutable OpenCore.

Las descargas verificadas se conservan en `_/temp/macos-iso/cache/`, separadas por el SHA-256 de su chunklist firmada. Las incompletas terminan en `.part`. Repetí el mismo comando para reanudar: se autentican los bloques completos existentes, se descarta el tramo final incompleto o corrupto y se comprueba el rango devuelto por el servidor. Los archivos completos de caché se verifican antes de reutilizarlos. Los temporales de creación y extracción se limpian automáticamente. Para liberar las descargas al terminar todos los trabajos, elimina únicamente la carpeta de caché del creador; conserva la ISO y el JSON. Los temporales de otras herramientas del proyecto son independientes.

`--work-dir` debe estar dentro de `_/temp` del proyecto y `--output-dir` dentro del proyecto. Si necesitás otro disco, mové la carpeta completa de la herramienta. Se rechazan rutas fuera de esos límites, archivos de salida que sean enlaces simbólicos y la sobrescritura de una ISO existente. Si la ISO existente coincide, se verifica y reutiliza; los archivos auxiliares ausentes se regeneran. Un bloqueo impide dos creaciones simultáneas en la misma carpeta de trabajo.

Reservá aproximadamente cuatro veces el tamaño de la imagen comprimida para caché, ISO y copias de verificación. Se comprueba el espacio antes de las escrituras grandes. La verificación independiente también necesita espacio temporal. `Ctrl+C` conserva las descargas reanudables y elimina la ISO de salida incompleta.

## Verificar una ISO de forma independiente

```sh
python3 Scripts/create_macos_iso.py --verify ISOs/macOS_Tahoe_26.6.2_25G83_Recovery.iso --language es-AR
```

La operación lee el **volumen HFS+ de arranque** indicado por el APM, comprueba los archivos esperados, verifica de nuevo la firma RSA de Apple y todos los bloques del DMG, extrae el SystemVersion.plist real y compara los metadatos y la etiqueta. No se limita a aceptar un `verified=true` en un informe JSON. `--json` devuelve resultados estructurados.

El `.iso.sha256` permite comprobar si tu copia coincide con la ISO creada; no es una firma de Apple. La firma de Apple autentica BaseSystem frente a la clave Apple EFI ROM incluida en OpenCorePkg 1.0.7. No autentica el contenedor ISO generado aquí ni tu EFI independiente. Debés confiar en el código del creador, Python, 7-Zip, xorriso y tu equipo. El proyecto no afirma tener una auditoría de seguridad independiente ni proteger frente a un administrador malicioso del equipo.

## Usar archivos de Apple ya descargados

```sh
python3 Scripts/create_macos_iso.py --os 26.6.2 --from-image /ruta/BaseSystem.dmg --chunklist /ruta/BaseSystem.chunklist --language es-AR
```

Los dos archivos son obligatorios. Se comprueban las firmas y el contenido también en este modo. Permite crear la ISO sin otra descarga, aunque la instalación de macOS posterior requiere Internet. Acepta imágenes de recuperación, no InstallAssistant.pkg ni un DVD completo arbitrario.

## Política de red

La consulta se hace mediante `https://osrecovery.apple.com`. Las descargas se limitan a servidores de recuperación conocidos de Apple. Los certificados HTTPS se validan normalmente y se rechazan las redirecciones que rebajan HTTPS a HTTP. Apple entrega actualmente algunos archivos firmados desde `http://oscdn.apple.com`, cuyo endpoint HTTPS no presentó un certificado válido para ese nombre durante la prueba. El script utiliza la URL HTTP facilitada por Apple con comprobación criptográfica independiente obligatoria; nunca emplea un contexto TLS inseguro ni `curl -k`.

`--https-only` rechaza HTTP por completo; puede impedir las descargas de recuperación que Apple ofrece actualmente. Los valores `AH` y `CH` del servicio son referencias de sesión, no checksums de archivos. Los hashes autenticados proceden de la chunklist firmada. Los tokens y las cookies de acceso no se guardan en los informes públicos. Para conexiones lentas podés usar `--timeout 60 --retries 6`. Si caduca el token temporal de Apple, repetir el comando obtiene metadatos nuevos y reutiliza los bloques autenticados.

## Utilización en Proxmox

1. Subí la ISO al almacenamiento de Proxmox que admita imágenes ISO.
2. Conectala como CD/DVD, por ejemplo SATA0, conservando `media=cdrom`.
3. Poné primero el disco de tu EFI OpenCore compatible y mantén el CD/DVD activado en el orden de arranque.
4. Iniciá OpenCore y selecciona `macOS VERSION Recovery`.
5. Conectá la red del invitado y utiliza Utilidad de Discos/Instalar macOS sobre el disco de sistema elegido.

La EFI necesita soporte HFS+ y del mapa de particiones Apple, normalmente `OpenHfsPlus.efi` y `OpenPartitionDxe.efi`, y permitir detectar instaladores y recuperaciones. El creador de ISO no modifica el nodo ni los discos del invitado. `efidisk0` almacena variables OVMF y es distinto de la partición EFI que contiene los archivos de arranque. La instalación y la elección de CPU, disco y red siguen dependiendo de la configuración de la VM.

## Solución de problemas

| Resultado | Acción |
| --- | --- |
| Falta xorriso o 7zip | Repetí con `--install-deps` o instala los paquetes manualmente |
| Apple devuelve otra versión | Elegí la familia disponible o usa archivos verificados de la revisión exacta |
| Fallo de firma o hash | Detené el proceso; no omitas la verificación ni uses la imagen fallida |
| No se puede leer SystemVersion.plist | Instala un 7zip actual con soporte DMG/HFS+/APFS |
| La ISO existente no coincide | Conservala y elige otra carpeta de salida; no se sobrescribe |
| Solo aparece OpenShell | Comprobá la ISO conectada, el orden de arranque y los drivers de archivos de la EFI |

`--probe` comprueba la disponibilidad de un producto firmado, no su versión de macOS; para eso hay que descargar e inspeccionar el DMG. Apple puede dejar de ofrecer recuperaciones antiguas o los servicios que necesitan para instalarse.

## Alcance de las pruebas

Se completaron descargas reales, autenticación, lectura de versión y creación de ISO para Lion 10.7.5 (11G63), Mojave 10.14.6 (18G87) y Tahoe 26.6.2 (25G83). Tahoe también se verificó de nuevo desde su ISO final y OpenCore lo detectó en QEMU/OVMF. No se completó localmente una instalación del invitado. Las pruebas del creador y del lanzador se ejecutan con:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tests -p 'test_macos_iso*.py' -v
```
