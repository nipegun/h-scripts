# Referencia técnica

## Índice

[Arquitectura](#arquitectura) · [Módulos](#módulos) · [Símbolos clave](#símbolos-clave) · [Flujos](#flujos) · [Comandos](#comandos) · [Impacto](#impacto) · [Extensiones](#extensiones)

## Arquitectura

El lanzador independiente `mcOSisoCreator.py` funciona desde stdin: descarga un ZIP nombrado por SHA-256 y comprueba el digest incorporado antes de extraer o ejecutar código. Se rechazan rutas inseguras, enlaces, tamaños excesivos y cambios en código ya instalado. Cada versión se extrae a una carpeta independiente de `_/temp/bootstrap`. `cRoot` identifica los recursos; `cWorkspace` identifica la carpeta persistente de trabajo, seleccionada por `MCOS_ISO_CREATOR_WORKSPACE` al lanzar el proceso. Sin esa variable, el ejecutable local conserva su carpeta de proyecto habitual. Se usa un proceso Python aislado (`-I -B`) y `/dev/tty` para la interacción al ejecutar por curl. El código de salida del creador se devuelve al shell. La confianza en el paquete depende de este repositorio; la firma de Apple cubre posteriormente la recuperación.

`Scripts/create_macos_iso.py` es el punto de entrada ejecutable. `Scripts/macos_iso/` es un paquete de espacio de nombres implícito, sin archivos `__init__.py`. El proyecto requiere Python 3.13. Se utiliza la biblioteca estándar de Python y las herramientas Debian xorriso y 7-Zip. Código, comentarios y claves de metadatos están en inglés; los textos de interfaz viven en cuatro archivos JSON, con en-US como idioma predeterminado.

El alcance es la construcción nativa en Debian de medios ópticos de **recuperación**. Los instaladores completos sin conexión de Apple requieren otro flujo con macOS. El catálogo contiene identificadores para 10.7–26 y entradas explícitamente no disponibles para los anteriores. Las placas y plantillas de serie proceden de la referencia de recuperación de OpenCorePkg 1.0.7. Apple decide qué devuelve; el SystemVersion.plist de la imagen autenticada determina el nombre de salida. La revisión exacta se comprueba por separado de la familia.

La consulta utiliza HTTPS. Las URL de archivos se restringen a servidores conocidos de Apple; se permite HTTP antiguo solo en oscdn.apple.com, tal como lo utiliza el servicio de recuperación. No se permiten redirecciones de HTTPS a HTTP ni desactivar TLS; se retiran cookies al cambiar de servidor en una redirección. `--https-only` aplica una política más estricta. La autenticación depende de la clave RSA Apple EFI ROM fijada y de la chunklist firmada, no de las referencias de sesión AH/CH ni de un checksum publicado junto a una ISO de origen desconocido.

El lector CNKL utiliza comprobaciones explícitas, sin `assert`: cabecera, offsets, métodos admitidos, límites, longitud exacta y firma RSA PKCS#1 v1.5 con SHA-256. Rechaza las chunklists de método 2 sin firma digital. La imagen se verifica en búferes acotados frente a los hashes autenticados. Para reanudar, se trunca únicamente el temporal hasta el último bloque completo válido; una respuesta de rango errónea no permite añadir datos a ciegas. Un fallo de integridad nunca activa una descarga alternativa sin verificar.

La ISO se genera desde cuatro archivos: BaseSystem.dmg intacto, su chunklist firmada, una etiqueta acotada para OpenCore y BUILDINFO.json. xorriso produce ISO9660 y HFS+ con APM; no se incrusta firmware. La verificación analiza el APM y comprueba el **volumen HFS+ que se utiliza para arrancar**, rechazando archivos o registros de arranque inesperados y verificando la imagen Apple desde ese sistema de archivos. Así se evita comprobar solo una vista ISO9660 que pueda diferir de lo que lee OpenCore. `--verify` también extrae el DMG autenticado para leer su versión real.

La firma de Apple cubre la recuperación, no el contenedor ISO ni una EFI independiente. Se confía en Python, las herramientas nativas y la integridad del equipo. No se afirma una auditoría externa de seguridad, una atestación de ejecución fiable ni reproducibilidad exacta entre fechas y versiones de herramientas. Los archivos auxiliares registran hashes y procedencia; no sustituyen a la verificación. La ISO solo se publica después de comprobarla, mediante un enlace duro que no sobrescribe destinos existentes. Una ISO existente que coincida se verifica y reutiliza.

## Módulos

| Módulo | Ruta | Responsabilidad | Depende de | Usado por |
| --- | --- | --- | --- | --- |
| Lanzador curl | `mcOSisoCreator.py` | Descarga verificada, caché y terminal | Biblioteca estándar, ZIP runtime | curl, usuario |
| Empaquetador | `Scripts/package_macos_iso.py` | ZIP reproducible, lanzador fijado y distribución | Fuentes, idiomas y documentos | Mantenimiento |
| Entrada | `Scripts/create_macos_iso.py` | Comprobar Python y lanzar la interfaz | cli | Usuario y automatizaciones |
| Interfaz | `Scripts/macos_iso/cli.py` | Menú, operaciones, dependencias y flujo | Todos los módulos | Entrada |
| Compartido | `Scripts/macos_iso/common.py` | Errores, traducción, progreso, bloqueos y archivos | Biblioteca estándar e idiomas | Todos |
| Catálogo | `Scripts/macos_iso/catalog.py` | Selección y validación de versiones | JSON de versiones y common | Interfaz |
| Criptografía | `Scripts/macos_iso/crypto.py` | Verificación RSA/CNKL y de bloques | Biblioteca estándar y common | Red, medios y pruebas |
| Red | `Scripts/macos_iso/network.py` | Consulta, política de URL, reintentos y reanudación | urllib, crypto y common | Interfaz |
| Medios | `Scripts/macos_iso/media.py` | Versión, construcción y verificación APM/HFS+ | xorriso, 7-Zip y crypto | Interfaz |

## Símbolos clave

| Símbolo | Archivo:línea | Función |
| --- | --- | --- |
| `fMain`, `fDownload`, `fInstall`, `fLaunch` | `mcOSisoCreator.py:211`, `:84`, `:165`, `:195` | Paquete verificado y ejecución desde curl |
| `fMain`, `fArchive` | `Scripts/package_macos_iso.py:93`, `:47` | Distribución reproducible |
| `fMain`, `fRun`, `fBuild` | `Scripts/macos_iso/cli.py:245`, `:162`, `:127` | Argumentos, operaciones y coordinación |
| `fSelect`, `fCheckVersion` | `Scripts/macos_iso/catalog.py:23`, `:38` | Selección normalizada y rechazo de versiones incorrectas |
| `fParseChunklist`, `fVerifyReader` | `Scripts/macos_iso/crypto.py:32`, `:89` | Autenticar metadatos y verificar un flujo de imagen |
| `fDiscover`, `fDownload` | `Scripts/macos_iso/network.py:89`, `:154` | Solicitar archivos Apple y reanudar descargas autenticadas |
| `fDetectVersion`, `fVerifyIso`, `fBuildIso` | `Scripts/macos_iso/media.py:118`, `:229`, `:297` | Leer SystemVersion, verificar HFS+ y publicar la ISO |
| `Context`, `fLock` | `Scripts/macos_iso/common.py:92`, `:78` | Progreso traducido y exclusión por carpeta de trabajo |

## Flujos

`curl → mcOSisoCreator.fMain → fDownload (SHA-256) → fInstall → fVerifyRuntime → fLaunch (/dev/tty) → cli.fMain`.

Interactivo: `fMain → fParser → fRun → fMenu → fBuild`.

Descarga: `fBuild → fRemoteInputs → fDiscover → fManifest → fParseChunklist → fDownload → fVerifiedPrefix/fVerifyImage`.

Archivos locales: `fBuild → fLocalInputs → fParseChunklist → fVerifyImage`. No realiza una consulta de descarga.

Empaquetado: `fDetectVersion → fCheckVersion → fBuildIso → xorriso → fVerifyIso → fApmHfs → fIsoMembers → fVerifyReader → publicación atómica y archivos auxiliares`.

Verificación independiente: `fRun --verify → fVerifyIso → extracción HFS+ → firma y bloques → fDetectVersion → comparación de etiqueta/metadatos → informe`.

## Comandos

| Comando | Handler | Archivo |
| --- | --- | --- |
| Sin argumentos / `--os VERSION` | `fRun → fBuild` | `cli.py` |
| `curl … \| python3 - [--directory DIR]` | `fMain → fLaunch` | `mcOSisoCreator.py` |
| `--list [--json]` | Listado del catálogo | `cli.py`, `catalog.py` |
| `--doctor [--json]` | Dependencias y espacio | `cli.py` |
| `--probe --os VERSION` | Consulta y firma de metadatos | `cli.py`, `network.py` |
| `--verify ISO [--json]` | Verificación HFS+ independiente | `cli.py`, `media.py` |
| `--from-image DMG --chunklist FILE --os VERSION` | Archivos locales verificados | `cli.py` |
| `--dry-run --os VERSION` | Plan sin red | `cli.py` |

El tiempo de red admite 5–300 segundos por operación y entre 1 y 8 intentos. Las herramientas nativas tienen un límite de ejecución. Códigos de salida: 0 correcto, 1 fallo de creación/verificación, 2 argumentos incorrectos y 130 cancelación. La salida se limita al proyecto y los temporales a su subcarpeta `_/temp`. El resultado consta de `.iso`, `.json` e `.iso.sha256`. Las descargas se conservan para reanudar; las extracciones e ISO incompletas se limpian en bloques finally.

## Impacto

La criptografía, la política de URL y el análisis de medios son componentes críticos para la seguridad. Sus cambios requieren pruebas de manipulación y archivos reales firmados de Apple. Cambiar HFS+ exige verificar el volumen de arranque y comprobar su detección con OpenCore; un listado ISO9660 no basta. Cambiar la selección de versión requiere probar discrepancias de familia y revisión. Las claves y campos de formato deben coincidir entre los cuatro idiomas.

Las pruebas están en `Tests/test_macos_iso.py`. Sus métodos `mTest*` siguen las convenciones del proyecto; el hook estándar `load_tests` configura ese prefijo. La muestra firmada pequeña es una chunklist, no un instalador de macOS. Se prueban firmas y hashes modificados, cabeceras malformadas, archivos sin firma, Python optimizado, URL/redirecciones, descargas parciales, rangos ignorados o falsos, versiones, enlaces simbólicos e idiomas. Se generaron medios reales completos de recuperación para 10.7.5, 10.14.6 y 26.6.2. La instalación completa del sistema invitado no forma parte de la validación local realizada.

## Extensiones

Para añadir otra familia, incorporá identificadores de Apple documentados a `Sources/macos-recovery-versions.json`, ejecutá `--probe`, descargá e inspeccioná una imagen real firmada y probá la comprobación de versión. No deduzcas la revisión del nombre del archivo ni etiquetes otra recuperación como la solicitada. Un formato de firma nuevo requiere una clave de confianza independiente y una implementación de verificación; nunca añadas una opción para saltarla.

Para otro idioma, incluí todas las claves JSON y sus campos, actualizá `cLanguages` y ejecutá las pruebas de traducción. Otro formato de medio debe conservar los bytes Apple y comprobar el sistema de archivos que leerá OpenCore. Actualizar la clave de confianza o relajar las URL permitidas requiere revisar el origen y los límites de confianza. Mantené sincronizados README, CODE y MANUAL en sus tres idiomas documentales.

Para publicar cambios: ejecuta `python3 Scripts/package_macos_iso.py`. Se actualizan las líneas de símbolos, se genera `Releases/mcOSisoCreator/` y se fija su ZIP en el lanzador. Publica el contenido completo de esa carpeta en `Debian/mcOSisoCreator` y conserva los ZIP runtime de publicaciones anteriores. Nunca publiques `ISOs/`, cachés, EFI ni configuraciones privadas de VM. Las pruebas adicionales están en `Tests/test_macos_iso_bootstrap.py`; incluyen la ejecución real del script por stdin y la persistencia de resultados.
