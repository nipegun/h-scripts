#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Build the reproducible runtime and the GitHub distribution directory."""

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

cRoot = Path(__file__).resolve().parents[1]
cPublicRules = '''### Reglas extra

Este proyecto crea ISO de recuperación de macOS en Debian. Requiere Python 3.13 o superior. El ejecutable local es Scripts/create_macos_iso.py; ISOCreator.py permite ejecutarlo mediante curl y descarga el paquete de código fijado por SHA-256. Mantener todas las comprobaciones de firmas de Apple y distinguir recuperación de instalador completo sin conexión. No prometer revisiones que Apple no ofrece. Conservar los paquetes runtime antiguos en Releases para que los lanzadores anteriores sigan funcionando. Después de modificar código, datos o documentación, ejecutar Scripts/package_macos_iso.py y publicar el lanzador, los fuentes y el paquete juntos. Los temporales están en _/temp, separados de ISOs. No incluir imágenes de instalación, credenciales, configuraciones privadas de VM ni memorias de otros proyectos en la publicación.
'''


def fRuntimeFiles():
  lPaths = [cRoot / 'Scripts/create_macos_iso.py',
    cRoot / 'Sources/macos-recovery-versions.json',
    cRoot / 'Sources/project-files.json',
    cRoot / 'ThirdParty/Licenses/OpenCore-LICENSE.txt',
    cRoot / 'Tests/test_macos_iso.py',
    cRoot / 'Tests/fixtures/apple-tahoe-26.6.2.chunklist',
    cRoot / 'Tests/fixtures/README.md']
  for vPattern in ('Scripts/macos_iso/*.py', 'Locales/macos_iso/*.json',
      'README*.md', 'CODE*.md', 'MANUAL*.md'):
    lPaths.extend(cRoot.glob(vPattern))
  dFiles = {vPath.relative_to(cRoot).as_posix(): vPath.read_bytes() for vPath in lPaths}
  dTemplates = json.loads((cRoot / 'Sources/project-files.json').read_text())
  dFiles.update({vName: vText.encode() for vName, vText in dTemplates.items()})
  dFiles['ReglasParaEsteProyecto.md'] = cPublicRules.encode()
  dFiles['.gitignore'] = (dTemplates['.gitignore'].rstrip() + '\n\n# Generated recovery images\nISOs/\n').encode()
  for vName in ('README.md', 'README.es-ES.md', 'README.es-AR.md'):
    vText = dFiles[vName].decode()
    for vHeading in ('## Existing EFI workspace', '## Trabajo EFI existente'):
      vText = vText.split(vHeading)[0].rstrip() + '\n'
    dFiles[vName] = vText.encode()
  return dFiles


def fArchive(pFiles):
  vBuffer = io.BytesIO()
  with zipfile.ZipFile(vBuffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as vZip:
    for vName in sorted(pFiles):
      vInfo = zipfile.ZipInfo(vName, date_time=(1980, 1, 1, 0, 0, 0))
      vInfo.create_system = 3
      vInfo.external_attr = (stat.S_IFREG | 0o644) << 16
      vInfo.compress_type = zipfile.ZIP_DEFLATED
      vZip.writestr(vInfo, pFiles[vName], compresslevel=9)
  return vBuffer.getvalue()


def fSymbols():
  dSymbols = {}
  for vPath in [*sorted((cRoot / 'Scripts/macos_iso').glob('*.py')),
                cRoot / 'ISOCreator.py', cRoot / 'Scripts/package_macos_iso.py']:
    dSymbols[vPath.relative_to(cRoot).as_posix()] = {
      vNode.name: vNode.lineno for vNode in ast.parse(vPath.read_text()).body
      if isinstance(vNode, (ast.FunctionDef, ast.ClassDef))}
  for vPath in cRoot.glob('CODE*.md'):
    lLines = []
    for vLine in vPath.read_text().splitlines():
      lParts = vLine.split('|')
      if len(lParts) > 4:
        lNames = re.findall(r'`([^`]+)`', lParts[1])
        vMatch = re.search(r'`([^`]+\.py):\d+`', lParts[2])
        if vMatch and vMatch[1] in dSymbols and all(vName in dSymbols[vMatch[1]] for vName in lNames):
          lParts[2] = ' ' + ', '.join(f'`{vMatch[1] if vIndex == 0 else ""}:{dSymbols[vMatch[1]][vName]}`'
            for vIndex, vName in enumerate(lNames)) + ' '
          vLine = '|'.join(lParts)
      lLines.append(vLine)
    vPath.write_text('\n'.join(lLines) + '\n')


def fWrite(pRoot, pName, pData):
  vTarget = pRoot / pName
  vTarget.parent.mkdir(parents=True, exist_ok=True)
  if vTarget.is_symlink():
    raise ValueError(f'Refusing symbolic link: {vTarget}')
  if pName in ('AGENTS.md', 'CLAUDE.md', 'ReglasParaEsteProyecto.md') and vTarget.exists():
    if vTarget.read_bytes() != pData:
      raise ValueError(f'Refusing to overwrite project rules: {vTarget}')
    return
  vTarget.write_bytes(pData)


def fMain():
  vParser = argparse.ArgumentParser(description=__doc__)
  vParser.add_argument('--destination', type=Path, default=cRoot / 'Releases/ISOCreator', dest='vDestination')
  vArguments = vParser.parse_args()
  vDestination = vArguments.vDestination.resolve()
  if vDestination == cRoot or not vDestination.is_relative_to(cRoot):
    raise ValueError('The distribution must be a subdirectory of this project.')
  dMessages = {vPath.stem: json.loads(vPath.read_text()) for vPath in sorted((cRoot / 'Locales/bootstrap').glob('*.json'))}
  vLauncherPath = cRoot / 'ISOCreator.py'
  vLauncher = vLauncherPath.read_text()
  # Stable one-line metadata keeps CODE.md symbol locations independent of translations.
  vJson = json.dumps(dMessages, ensure_ascii=False, sort_keys=True)
  vMetadata = f"cBundleSha256 = '{{digest}}'\ndMessages = json.loads({vJson!r})"
  vLauncher = re.sub(r'# BEGIN GENERATED RELEASE\n.*?\n# END GENERATED RELEASE',
    lambda pMatch: '# BEGIN GENERATED RELEASE\n' + vMetadata.replace('{digest}', '0' * 64) + '\n# END GENERATED RELEASE',
    vLauncher, flags=re.DOTALL)
  vLauncherPath.write_text(vLauncher)
  fSymbols()
  dFiles = fRuntimeFiles()
  vData = fArchive(dFiles)
  vDigest = hashlib.sha256(vData).hexdigest()
  vLauncher = vLauncher.replace("cBundleSha256 = '" + '0' * 64 + "'", f"cBundleSha256 = '{vDigest}'")
  vLauncherPath.write_text(vLauncher)
  for vName, vContent in dFiles.items():
    fWrite(vDestination, vName, vContent)
  for vPath in [vLauncherPath, Path(__file__).resolve(), cRoot / 'Tests/test_macos_iso_bootstrap.py',
                *sorted((cRoot / 'Locales/bootstrap').glob('*.json'))]:
    fWrite(vDestination, vPath.relative_to(cRoot).as_posix(), vPath.read_bytes())
  vBundleName = f'Releases/runtime-{vDigest}.zip'
  fWrite(vDestination, vBundleName, vData)
  fWrite(vDestination, vBundleName + '.sha256', f'{vDigest}  runtime-{vDigest}.zip\n'.encode())
  print(json.dumps({'directory': str(vDestination), 'runtime_sha256': vDigest,
    'runtime_bytes': len(vData), 'runtime_files': len(dFiles)}, indent=2))
  return 0


if __name__ == '__main__':
  try:
    if sys.version_info < (3, 13):
      raise ValueError('Python 3.13 or newer is required.')
    sys.dont_write_bytecode = True
    raise SystemExit(fMain())
  except (OSError, ValueError) as vError:
    print(f'Packaging failed: {vError}', file=sys.stderr)
    raise SystemExit(1)
