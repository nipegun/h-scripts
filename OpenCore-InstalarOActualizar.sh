#!/bin/bash

# Pongo a disposición pública este script bajo el término de "software de dominio público".
# Puedes hacer lo que quieras con él porque es libre de verdad; no libre con condiciones como las licencias GNU y otras patrañas similares.
# Si se te llena la boca hablando de libertad entonces hazlo realmente libre.
# No tienes que aceptar ningún tipo de términos de uso o licencia para utilizarlo o modificarlo porque va sin CopyLeft.

# ----------
# Script de NiPeGun para instalar la última versión de OpenCore en un Hackintosh
#
# Ejecución remota:
#   sudo curl -sL https://raw.githubusercontent.com/nipegun/h-scripts/master/OpenCore-InstalarOActualizar.sh | bash
# ----------

# Determinar la última versión disponible en GitHub
  echo ""
  echo "  Determinando la última versión de OpenCore disponible en GitHub..."
  echo ""
  vUltVersOpenCore=$(curl -sL https://github.com/acidanthera/OpenCorePkg/releases/latest | grep "title>" | grep elease | cut -d'>' -f2 | cut -d' ' -f2 | sed 's- --g')
  echo "    La última versión es la $vUltVersOpenCore"
  echo ""

# Descargar el archivo de la última versión
  echo ""
  echo "  Descargando el archivo zip de la versión $vUltVersOpenCore..."
  echo ""
  curl -L -o ~/OpenCore.zip https://github.com/acidanthera/OpenCorePkg/releases/download/"$vUltVersOpenCore"/OpenCore-"$vUltVersOpenCore"-RELEASE.zip
  echo ""

# Descomprimir el zip
  echo ""
  echo "  Descomprimiendo el archivo zip..."
  echo ""
  unzip ~/OpenCore.zip -d ~/OpenCore
  echo ""

# Descargar OpenCore configurator
  echo ""
  echo "  Descargando la última versión de OpenCore configurator..."
  echo ""
  curl -L -o ~/OpenCoreConfigurator.zip https://mackie100projects.altervista.org/apps/opencoreconf/download-new-build.php?version=last
  echo ""

# Descomprimir el zip
  echo ""
  echo "  Descomprimiendo OpenCoreConfigurator.zip..."
  echo ""
  unzip ~/OpenCoreConfigurator.zip -d ~/OpenCoreConfigurator
  echo ""

# Determinar la última versión de Lilu.kext disponible en GitHub
  echo ""
  echo "  Determinando la última versión de Lilu.kext disponible en GitHub..."
  echo ""
  vUltVersLilu=$(curl -sL https://github.com/acidanthera/Lilu/releases/latest | grep "title>" | grep elease | cut -d'>' -f2 | cut -d' ' -f2 | sed 's- --g')
  echo "    La última versión es la $vUltVersLilu"
  echo ""

# Descargar el archivo de la última versión
  echo ""
  echo "  Descargando el archivo zip de la versión $vUltVersLilu..."
  echo ""
  curl -L -o ~/Lilu.zip https://github.com/acidanthera/Lilu/releases/download/"$vUltVersLilu"/Lilu-"$vUltVersLilu"-RELEASE.zip
  echo ""

# Descomprimir el zip
  echo ""
  echo "  Descomprimiendo Lilu.zip.zip..."
  echo ""
  unzip ~/Lilu.zip -d ~/Lilu
  echo ""

# Mover Lilu.kext a la carpeta OpenCore
  echo ""
  echo "  Moviendo Lilu.kext a la carpeta OpenCore..."
  echo ""
  mv ~/Lilu/Lilu.kext ~/OpenCore/X64/EFI/OC/Kexts/
  echo ""
