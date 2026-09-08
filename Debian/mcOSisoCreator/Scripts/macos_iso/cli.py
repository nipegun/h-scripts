"""Interactive and automated entry points for the Debian recovery ISO builder."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .catalog import fCatalog, fCheckVersion, fMenu, fSelect
from .common import BuildError, cBuilderVersion, cLanguages, cWorkspace, fContext, fFail, fLock, fSize
from .crypto import cManifestLimit, fParseChunklist, fVerifyImage
from .media import fBuildIso, fDetectVersion, fTool, fVerifyIso
from .network import fDiscover, fDownload, fManifest, fPublicSource


def fParser(pContext):
  vParser = argparse.ArgumentParser(description=pContext.mText('program_description'))
  vParser.add_argument('--os', '--macos', dest='vOs', metavar='VERSION', help=pContext.mText('help_os'))
  vOperations = vParser.add_mutually_exclusive_group()
  vOperations.add_argument('--list', action='store_true', dest='vList', help=pContext.mText('help_list'))
  vOperations.add_argument('--doctor', action='store_true', dest='vDoctor', help=pContext.mText('help_doctor'))
  vOperations.add_argument('--verify', type=Path, dest='vVerify', metavar='ISO', help=pContext.mText('help_verify'))
  vOperations.add_argument('--probe', action='store_true', dest='vProbe', help=pContext.mText('help_probe'))
  vParser.add_argument('--from-image', type=Path, dest='vImage', metavar='DMG', help=pContext.mText('help_image'))
  vParser.add_argument('--chunklist', type=Path, dest='vChunklist', metavar='CHUNKLIST', help=pContext.mText('help_chunklist'))
  vParser.add_argument('--output-dir', type=Path, default=cWorkspace / 'ISOs', dest='vOutput', metavar='DIR', help=pContext.mText('help_output'))
  vParser.add_argument('--work-dir', type=Path, default=cWorkspace / '_/temp/macos-iso', dest='vWork', metavar='DIR', help=pContext.mText('help_work'))
  vParser.add_argument('--language', choices=cLanguages, default=pContext.vLanguage, help=pContext.mText('help_language'))
  vParser.add_argument('--install-deps', action='store_true', dest='vInstall', help=pContext.mText('help_install'))
  vParser.add_argument('--non-interactive', action='store_true', dest='vNonInteractive', help=pContext.mText('help_noninteractive'))
  vParser.add_argument('--https-only', action='store_true', dest='vHttpsOnly', help=pContext.mText('help_https'))
  vParser.add_argument('--timeout', type=int, default=45, dest='vTimeout', metavar='SECONDS', help=pContext.mText('help_timeout'))
  vParser.add_argument('--retries', type=int, default=4, dest='vRetries', metavar='COUNT', help=pContext.mText('help_retries'))
  vParser.add_argument('--dry-run', action='store_true', dest='vDry', help=pContext.mText('help_dry'))
  vParser.add_argument('--quiet', action='store_true', dest='vQuiet', help=pContext.mText('help_quiet'))
  vParser.add_argument('--json', action='store_true', dest='vJson', help=pContext.mText('help_json'))
  vParser.add_argument('--full', action='store_true', dest='vFull', help=argparse.SUPPRESS)
  vParser.add_argument('--version', action='version', version=pContext.mText('program_version', version=cBuilderVersion))
  return vParser


def fDirectories(pContext, pArguments):
  pContext.vWork = pArguments.vWork.resolve()
  pContext.vOutput = pArguments.vOutput.resolve()
  if not (cWorkspace / '_/temp').resolve().is_relative_to(cWorkspace):
    fFail('work_outside', path=str(pContext.vWork))
  if not pContext.vWork.is_relative_to((cWorkspace / '_/temp').resolve()):
    fFail('work_outside', path=str(pContext.vWork))
  if not pContext.vOutput.is_relative_to(cWorkspace):
    fFail('output_outside', path=str(pContext.vOutput))
  pContext.vWork.mkdir(parents=True, exist_ok=True)
  pContext.vOutput.mkdir(parents=True, exist_ok=True)


def fDependencies(pContext, pArguments):
  lMissing = []
  if not shutil.which('xorriso'):
    lMissing.append('xorriso')
  if not (shutil.which('7z') or shutil.which('7zz')):
    lMissing.append('7zip')
  if not lMissing:
    return
  vInstall = pArguments.vInstall
  if not vInstall and not pArguments.vNonInteractive and sys.stdin.isatty():
    vReply = input(pContext.mText('install_prompt')).strip().lower()
    vInstall = vReply in pContext.mText('yes_answers').split(',')
  if not vInstall:
    fFail('missing_tool', tool=', '.join(lMissing))
  if not shutil.which('apt-get'):
    fFail('deps_unavailable')
  lPrefix = []
  if os.geteuid() != 0:
    if not shutil.which('sudo'):
      fFail('deps_unavailable')
    lPrefix = ['sudo'] + (['-n'] if pArguments.vNonInteractive else [])
  pContext.mLog('installing_deps', packages=', '.join(lMissing))
  for lCommand in [['apt-get', 'update'], ['apt-get', 'install', '-y', '--no-install-recommends', *lMissing]]:
    vResult = subprocess.run(lPrefix + lCommand, check=False)
    if vResult.returncode:
      fFail('deps_failed')


def fLocalInputs(pContext, pArguments):
  for vPath in [pArguments.vImage, pArguments.vChunklist]:
    if not vPath.is_file():
      fFail('input_file', path=str(vPath))
  if pArguments.vChunklist.stat().st_size > cManifestLimit:
    fFail('manifest_structure')
  pContext.mLog('local_inputs')
  pContext.mStage(2, 'stage_signature')
  vManifest = fParseChunklist(pArguments.vChunklist.read_bytes())
  pContext.mLog('signature_ok', size=fSize(vManifest.vImageSize))
  pContext.mStage(3, 'stage_download')
  fVerifyImage(pArguments.vImage, vManifest, pContext.mProgress)
  pContext.mEndProgress()
  return pArguments.vImage.resolve(), pArguments.vChunklist.resolve(), {
    'type': 'local Apple-signature-verified recovery files',
    'image_filename': pArguments.vImage.name, 'chunklist_filename': pArguments.vChunklist.name}


def fRemoteInputs(pContext, pSelector, pProbe=False):
  pContext.mStage(1, 'stage_discover')
  dInfo = fDiscover(pContext, pSelector)
  pContext.mStage(2, 'stage_signature')
  vData, vManifest = fManifest(pContext, dInfo)
  pContext.mLog('signature_ok', size=fSize(vManifest.vImageSize))
  dSource = fPublicSource(dInfo, pSelector)
  if pProbe:
    return {'source': dSource, 'apple_signature_verified': True,
            'image_size': vManifest.vImageSize, 'chunklist_sha256': vManifest.vSha256,
            'macos_version_verified': False}
  vCache = pContext.vWork / 'cache' / vManifest.vSha256
  if not vCache.resolve().is_relative_to(pContext.vWork.resolve()):
    fFail('work_outside', path=str(vCache))
  vCache.mkdir(parents=True, exist_ok=True)
  vChunklist = vCache / 'BaseSystem.chunklist'
  from .common import fRegularOrMissing
  fRegularOrMissing(vChunklist)
  vChunklist.write_bytes(vData)
  pContext.mStage(3, 'stage_download')
  vImage = fDownload(pContext, dInfo, vManifest, vCache / 'BaseSystem.dmg')
  return vImage, vChunklist, dSource


def fBuild(pContext, pArguments, pSelected, pExact):
  if pArguments.vImage:
    vImage, vChunklist, dSource = fLocalInputs(pContext, pArguments)
    pContext.mStage(4, 'stage_version')
    dDetected = fDetectVersion(pContext, vImage)
    fCheckVersion(pSelected, dDetected['version'], pExact)
  else:
    vLastError = None
    for vIndex, dSelector in enumerate(pSelected['selectors']):
      try:
        if pArguments.vProbe:
          return fRemoteInputs(pContext, dSelector, True)
        vImage, vChunklist, dSource = fRemoteInputs(pContext, dSelector)
        pContext.mStage(4, 'stage_version')
        dDetected = fDetectVersion(pContext, vImage)
        fCheckVersion(pSelected, dDetected['version'], pExact)
        break
      except BuildError as vError:
        # Never retry or bypass signature/image-integrity failures with another source.
        if str(vError) not in ('http_error', 'apple_response', 'version_mismatch', 'exact_mismatch'):
          raise
        vLastError = vError
        if vIndex + 1 < len(pSelected['selectors']):
          pContext.mLog('fallback_selector')
    else:
      if vLastError is not None:
        raise vLastError
      fFail('unavailable_version', name=pSelected['name'], version=pSelected['id'])
  pContext.mLog('detected', **{vKey: dDetected[vKey] for vKey in ('version', 'build')})
  pContext.mStage(5, 'stage_iso')
  vIso, dVerification, vReused = fBuildIso(pContext, vImage, vChunklist, dDetected, pSelected, dSource)
  return {'iso': str(vIso), 'manifest': str(vIso.with_suffix('.json')), 'kind': 'recovery',
          'requires_network_for_installation': True, 'reused': vReused, **dVerification}


def fRun(pContext, pArguments):
  if not sys.platform.startswith('linux') or sys.version_info < (3, 13):
    fFail('unsupported_platform')
  if not 5 <= pArguments.vTimeout <= 300 or not 1 <= pArguments.vRetries <= 8:
    fFail('invalid_limits')
  pContext.vTimeout, pContext.vRetries = pArguments.vTimeout, pArguments.vRetries
  pContext.vHttpsOnly = pArguments.vHttpsOnly
  pContext.vQuiet = pArguments.vQuiet or pArguments.vJson
  if pArguments.vFull:
    fFail('full_not_supported')
  if bool(pArguments.vImage) != bool(pArguments.vChunklist):
    fFail('input_pair')
  if ((pArguments.vProbe and pArguments.vImage) or (pArguments.vVerify and (pArguments.vImage or pArguments.vDry))):
    fFail('invalid_arguments')
  if pArguments.vList:
    if pArguments.vJson:
      print(json.dumps(fCatalog(), ensure_ascii=False, indent=2))
    else:
      print(pContext.mText('recovery_notice'))
      for dVersion in fCatalog():
        print(f'{dVersion["id"]:8} {dVersion["name"]:18} ' + pContext.mText('mode_apple' if dVersion['selectors'] else 'mode_unavailable'))
    return 0
  if pArguments.vDoctor:
    dDoctor = {'python': sys.version.split()[0], 'xorriso': shutil.which('xorriso'),
                '7zip': shutil.which('7z') or shutil.which('7zz'), 'free_bytes': shutil.disk_usage(cWorkspace).free}
    if pArguments.vJson:
      print(json.dumps(dDoctor, indent=2))
    else:
      pContext.mLog('doctor_title')
      for vTool in ('python', 'xorriso', '7zip'):
        pContext.mLog('doctor_item', tool=vTool, path=dDoctor[vTool] or '-')
      pContext.mLog('doctor_free', size=fSize(dDoctor['free_bytes']))
    return 0 if dDoctor['xorriso'] and dDoctor['7zip'] else 1
  if pArguments.vVerify:
    if not pArguments.vVerify.is_file():
      fFail('input_file', path=str(pArguments.vVerify))
    fDirectories(pContext, pArguments)
    fDependencies(pContext, pArguments)
    with fLock(pContext.vWork / 'builder.lock'):
      dResult = fVerifyIso(pContext, pArguments.vVerify.resolve())
    if pArguments.vJson:
      print(json.dumps(dResult, indent=2))
    else:
      pContext.mLog('verification_ok', version=dResult['detected']['version'], build=dResult['detected']['build'], sha256=dResult['iso_sha256'])
      pContext.mLog('verification_scope')
    return 0
  if pArguments.vOs:
    dSelected, vExact = fSelect(pArguments.vOs)
  elif pArguments.vNonInteractive or not sys.stdin.isatty():
    fFail('interactive_required')
  else:
    dSelected, vExact = fMenu(pContext)
  if not dSelected['selectors'] and not pArguments.vImage:
    fFail('unavailable_version', name=dSelected['name'], version=dSelected['id'])
  pContext.mLog('selected', name=dSelected['name'], version=vExact or dSelected['id'])
  if pArguments.vDry:
    if pArguments.vJson:
      print(json.dumps({'operation': 'plan', 'requested': vExact or dSelected['id'],
        'kind': 'recovery', 'local_inputs': bool(pArguments.vImage), 'network_accessed': False,
        'work_directory': str(pArguments.vWork), 'output_directory': str(pArguments.vOutput)}, indent=2))
    else:
      vKey = 'dry_run_local' if pArguments.vImage else 'dry_run'
      print(pContext.mText(vKey, name=dSelected['name'], work=pArguments.vWork, output=pArguments.vOutput))
    return 0
  fDirectories(pContext, pArguments)
  if not pArguments.vProbe:
    fDependencies(pContext, pArguments)
  with fLock(pContext.vWork / 'builder.lock'):
    dResult = fBuild(pContext, pArguments, dSelected, vExact)
  if pArguments.vJson:
    print(json.dumps(dResult, ensure_ascii=False, indent=2))
  elif pArguments.vProbe:
    pContext.mLog('probe_ok')
    print(json.dumps(dResult, ensure_ascii=False, indent=2))
  else:
    pContext.mLog('completed', path=dResult['iso'])
    pContext.mLog('checksum_output', sha256=dResult['iso_sha256'])
    pContext.mLog('sidecar_output', path=dResult['manifest'])
    pContext.mLog('mount_hint')
    pContext.mLog('version_scope')
  return 0


def fMain(pArguments=None):
  vEarly = argparse.ArgumentParser(add_help=False)
  vEarly.add_argument('--language', choices=cLanguages, default='en-US')
  vLanguage, lRemaining = vEarly.parse_known_args(pArguments)
  vContext = fContext(vLanguage.language)
  try:
    vArguments = fParser(vContext).parse_args(pArguments)
    return fRun(vContext, vArguments)
  except KeyboardInterrupt:
    vContext.mEndProgress()
    print(vContext.mText('cancelled'), file=sys.stderr)
    return 130
  except BuildError as vError:
    vContext.mEndProgress()
    print(vContext.mText('error_prefix', message=vContext.mText(str(vError), **getattr(vError, 'dFields', {}))), file=sys.stderr)
    return 1
  except (OSError, ValueError, subprocess.SubprocessError) as vError:
    vContext.mEndProgress()
    print(vContext.mText('io_error', detail=str(vError)), file=sys.stderr)
    return 1
