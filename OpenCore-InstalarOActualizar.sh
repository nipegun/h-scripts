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
  echo "  Descargando el archivo zip de la versión $vUltVersOpenCore"
  echo ""
  curl https://github.com/acidanthera/OpenCorePkg/releases/download/"$vUltVersOpenCore"/OpenCore-"$vUltVersOpenCore"-RELEASE.zip


