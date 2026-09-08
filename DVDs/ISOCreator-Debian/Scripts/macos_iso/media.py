"""Inspect signed Apple images and build/verify HFS+ optical recovery media."""

import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import tempfile
import threading

from .common import cBuilderVersion, cIoSize, fFail, fHash, fRegularOrMissing, fSpace, fWriteJson
from .crypto import cAppleKey, cImageLimit, cManifestLimit, fParseChunklist, fVerifyReader

cRecoveryDir = 'com.apple.recovery.boot'
cAllowedFiles = {f'{cRecoveryDir}/BaseSystem.dmg', f'{cRecoveryDir}/BaseSystem.chunklist',
                  f'{cRecoveryDir}/.contentDetails', 'BUILDINFO.json'}
cSystemVersionSuffix = 'System/Library/CoreServices/SystemVersion.plist'


def fTool(pName):
  vTool = shutil.which(pName)
  if vTool:
    return vTool
  if pName == '7z':
    vTool = shutil.which('7zz')
    if vTool:
      return vTool
  fFail('missing_tool', tool=pName)


@contextlib.contextmanager
def fProcess(pContext, pCommand, pTimeout=900):
  """Bound execution and keep diagnostic output away from binary stdout."""
  vProcess = None
  vTimer = None
  vFinished = False
  vExpired = threading.Event()
  with tempfile.TemporaryFile(dir=pContext.vWork) as vErrors:
    try:
      vProcess = subprocess.Popen(pCommand, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=vErrors, env={**os.environ, 'LC_ALL': 'C.UTF-8', 'TMPDIR': str(pContext.vWork)})

      def fTimeout():
        vExpired.set()
        if vProcess.poll() is None:
          vProcess.kill()

      vTimer = threading.Timer(pTimeout, fTimeout)
      vTimer.daemon = True
      vTimer.start()
      yield vProcess.stdout
      vFinished = True
    finally:
      if vTimer is not None:
        vTimer.cancel()
      if vProcess is not None:
        if vProcess.stdout is not None:
          vProcess.stdout.close()
        if not vFinished and vProcess.poll() is None:
          vProcess.kill()
        try:
          vCode = vProcess.wait(timeout=10)
        except subprocess.TimeoutExpired:
          vProcess.kill()
          vCode = vProcess.wait(timeout=10)
      if vFinished:
        if vExpired.is_set():
          fFail('tool_timeout', tool=Path(pCommand[0]).name)
        if vCode != 0:
          vErrors.seek(0)
          vDetail = vErrors.read(2048).decode('utf-8', errors='replace').strip()
          fFail('tool_failed', tool=Path(pCommand[0]).name, code=vCode, detail=vDetail)


def fCommand(pContext, pCommand, pLimit=32 * 1024 * 1024):
  with fProcess(pContext, pCommand) as vOutput:
    vData = vOutput.read(pLimit + 1)
    if len(vData) > pLimit:
      fFail('tool_output_large', tool=Path(pCommand[0]).name)
  return vData


def fListArchive(pContext, pPath, pType=None):
  lCommand = [fTool('7z'), 'l', '-slt', '-ba', '-bd']
  if pType:
    lCommand.append(f'-t{pType}')
  lCommand += ['--', str(pPath)]
  vData = fCommand(pContext, lCommand).decode('utf-8', errors='replace')
  lEntries = []
  dEntry = {}
  for vLine in vData.splitlines() + ['']:
    if not vLine:
      if 'Path' in dEntry:
        lEntries.append(dEntry)
      dEntry = {}
    elif ' = ' in vLine:
      vKey, vValue = vLine.split(' = ', 1)
      if vKey == 'Path' and 'Path' in dEntry:
        lEntries.append(dEntry)
        dEntry = {}
      dEntry[vKey] = vValue
  return lEntries


def fReadMember(pContext, pArchive, pMember, pLimit, pType=None):
  lCommand = [fTool('7z'), 'e', '-so', '-bd', '-spd']
  if pType:
    lCommand.append(f'-t{pType}')
  return fCommand(pContext, lCommand + ['--', str(pArchive), pMember], pLimit)


def fDetectVersion(pContext, pImage):
  lEntries = fListArchive(pContext, pImage)
  lCandidates = sorted(
    [dEntry for dEntry in lEntries if dEntry['Path'].endswith(cSystemVersionSuffix)
      and dEntry.get('Folder') != '+' and dEntry.get('Alternate Stream') != '+'],
    key=lambda pEntry: (pEntry['Path'].count('/'), len(pEntry['Path'])))
  if not lCandidates:
    fFail('version_unreadable')
  dCandidate = lCandidates[0]
  try:
    if int(dCandidate.get('Size', '0')) > 1024 * 1024:
      fFail('version_unreadable')
    dPlist = plistlib.loads(fReadMember(pContext, pImage, dCandidate['Path'], 1024 * 1024))
  except (ValueError, plistlib.InvalidFileException):
    fFail('version_unreadable')
  if not isinstance(dPlist, dict):
    fFail('version_unreadable')
  vVersion = dPlist.get('ProductUserVisibleVersion') or dPlist.get('ProductVersion', '')
  vBuild = dPlist.get('ProductBuildVersion', '')
  if (not isinstance(vVersion, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', vVersion)
      or not isinstance(vBuild, str) or not re.fullmatch(r'[A-Za-z0-9.-]{1,32}', vBuild)):
    fFail('version_unreadable')
  return {'version': vVersion, 'build': vBuild, 'product_name': dPlist.get('ProductName', 'macOS'),
          'version_plist_member': dCandidate['Path']}


def fApmHfs(pIso):
  vIsoSize = pIso.stat().st_size
  if not 65536 <= vIsoSize <= cImageLimit + 256 * 1024 * 1024:
    fFail('iso_layout')
  with pIso.open('rb') as vFile:
    vHeader = vFile.read(512)
    if len(vHeader) < 512 or vHeader[:2] != b'ER':
      fFail('iso_layout')
    vBlockSize = struct.unpack_from('>H', vHeader, 2)[0]
    if vBlockSize not in (512, 2048):
      fFail('iso_layout')
    vFile.seek(vBlockSize)
    vFirst = vFile.read(512)
    if vFirst[:2] != b'PM':
      fFail('iso_layout')
    vCount = struct.unpack_from('>I', vFirst, 4)[0]
    if not 1 <= vCount <= 4096:
      fFail('iso_layout')
    lHfs = []
    for vIndex in range(1, vCount + 1):
      vFile.seek(vBlockSize * vIndex)
      vEntry = vFile.read(512)
      if len(vEntry) != 512 or vEntry[:2] != b'PM':
        fFail('iso_layout')
      vStart, vSize = struct.unpack_from('>II', vEntry, 8)
      vType = vEntry[48:80].split(b'\0', 1)[0]
      if vType == b'Apple_HFS':
        vOffset, vLength = vStart * vBlockSize, vSize * vBlockSize
        if vOffset < 32768 or vLength < 2048 or vOffset + vLength > vIsoSize:
          fFail('iso_layout')
        vFile.seek(vOffset + 1024)
        if vFile.read(2) not in (b'H+', b'HX'):
          fFail('iso_layout')
        lHfs.append((vOffset, vLength))
    # This builder emits no embedded firmware or El Torito executable.
    vHasPvd = False
    for vSector in range(16, 64):
      vFile.seek(vSector * 2048)
      vDescriptor = vFile.read(2048)
      if len(vDescriptor) != 2048 or vDescriptor[1:6] != b'CD001':
        fFail('iso_layout')
      if vDescriptor[0] == 0:
        fFail('iso_extra_boot')
      if vDescriptor[0] == 1:
        vHasPvd = True
      if vDescriptor[0] == 255:
        break
    else:
      fFail('iso_layout')
    if not vHasPvd or len(lHfs) != 1:
      fFail('iso_layout')
  return lHfs[0]


def fCopyRegion(pSource, pOutput, pOffset, pLength):
  with pSource.open('rb') as vInput, pOutput.open('xb') as vOutput:
    vInput.seek(pOffset)
    vRemaining = pLength
    while vRemaining:
      vData = vInput.read(min(cIoSize, vRemaining))
      if not vData:
        fFail('iso_layout')
      vOutput.write(vData)
      vRemaining -= len(vData)


def fIsoMembers(pContext, pHfs):
  lEntries = fListArchive(pContext, pHfs, 'HFS')
  dMembers = {}
  for dEntry in lEntries:
    if dEntry.get('Folder') == '+':
      continue
    vPath = dEntry['Path']
    vRelative = vPath.split('/', 1)[1] if '/' in vPath else ''
    # 7-Zip HFS includes its volume name as the first component.
    if vRelative not in cAllowedFiles or dEntry.get('Alternate Stream') == '+':
      fFail('iso_extra_file', path=vPath)
    if vRelative in dMembers:
      fFail('iso_layout')
    dMembers[vRelative] = dEntry
  if set(dMembers) != cAllowedFiles:
    fFail('iso_layout')
  return dMembers


def fVerifyIso(pContext, pIso, pExpected=None):
  vOffset, vLength = fApmHfs(pIso)
  fSpace(pContext.vWork, vLength + 64 * 1024 * 1024)
  with tempfile.TemporaryDirectory(dir=pContext.vWork, prefix='verify-iso-') as vDirectory:
    vWork = Path(vDirectory)
    vHfs = vWork / 'recovery.hfs'
    fCopyRegion(pIso, vHfs, vOffset, vLength)
    dMembers = fIsoMembers(pContext, vHfs)
    vChunkMember = dMembers[f'{cRecoveryDir}/BaseSystem.chunklist']['Path']
    vChunkData = fReadMember(pContext, vHfs, vChunkMember, cManifestLimit, 'HFS')
    vManifest = fParseChunklist(vChunkData)
    dDmg = dMembers[f'{cRecoveryDir}/BaseSystem.dmg']
    if int(dDmg.get('Size', '-1')) != vManifest.vImageSize:
      fFail('iso_layout')
    lCommand = [fTool('7z'), 'e', '-so', '-bd', '-spd', '-tHFS', '--', str(vHfs), dDmg['Path']]
    vExtracted = vWork / 'BaseSystem.dmg'
    with contextlib.ExitStack() as vStack:
      vSource = vStack.enter_context(fProcess(pContext, lCommand))
      vDestination = None
      if pExpected is None:
        fSpace(vWork, vManifest.vImageSize + 64 * 1024 * 1024)
        vDestination = vStack.enter_context(vExtracted.open('xb'))

      def fRead(pSize):
        vData = vSource.read(pSize)
        if vDestination is not None:
          vDestination.write(vData)
        return vData

      vImageSha = fVerifyReader(fRead, vManifest, pContext.mProgress)
    pContext.mEndProgress()
    if pExpected is None:
      dVersion = fDetectVersion(pContext, vExtracted)
    else:
      if (vImageSha != pExpected['image_sha256']
          or vManifest.vSha256 != pExpected['chunklist_sha256']):
        fFail('iso_payload_mismatch')
      dVersion = pExpected['detected']
    vDetails = fReadMember(pContext, vHfs, dMembers[f'{cRecoveryDir}/.contentDetails']['Path'], 4096, 'HFS')
    if vDetails != f'macOS {dVersion["version"]} Recovery'.encode('ascii'):
      fFail('iso_payload_mismatch')
    vBuildInfo = fReadMember(pContext, vHfs, dMembers['BUILDINFO.json']['Path'], 1024 * 1024, 'HFS')
    try:
      dBuildInfo = json.loads(vBuildInfo)
    except (ValueError, UnicodeDecodeError):
      fFail('iso_layout')
    if (not isinstance(dBuildInfo, dict) or dBuildInfo.get('kind') != 'recovery' or dBuildInfo.get('detected') != dVersion
        or dBuildInfo.get('image_sha256') != vImageSha
        or dBuildInfo.get('chunklist_sha256') != vManifest.vSha256):
      fFail('iso_payload_mismatch')
  return {'iso_sha256': fHash(pIso), 'image_sha256': vImageSha,
          'chunklist_sha256': vManifest.vSha256, 'detected': dVersion,
          'apple_signature_verified': True, 'hfs_payloads_verified': True,
          'apm_offset': vOffset, 'apm_size': vLength,
          'iso_created_utc': dBuildInfo.get('created_utc')}


def fSaveIsoMetadata(pOutput, pMetadata, pVerification):
  pMetadata['created_utc'] = pVerification['iso_created_utc']
  pMetadata['iso'] = {'filename': pOutput.name, 'size': pOutput.stat().st_size,
                      'sha256': pVerification['iso_sha256'], 'filesystems': ['ISO9660', 'HFS+'], 'partition_map': 'APM'}
  pMetadata['verification'] = pVerification
  fWriteJson(pOutput.with_suffix('.json'), pMetadata)
  vChecksum = pOutput.with_suffix('.iso.sha256')
  fRegularOrMissing(vChecksum)
  vChecksum.write_text(f'{pVerification["iso_sha256"]}  {pOutput.name}\n', encoding='ascii')


def fBuildIso(pContext, pImage, pChunklist, pVersion, pSelected, pSource):
  vName = re.sub(r'[^A-Za-z0-9]+', '_', pSelected['name']).strip('_')
  vFileName = f'macOS_{vName}_{pVersion["version"]}_{pVersion["build"]}_Recovery.iso'
  vOutput = pContext.vOutput / vFileName
  fRegularOrMissing(vOutput)
  vSidecar = vOutput.with_suffix('.json')
  fRegularOrMissing(vSidecar)
  dMetadata = {'schema_version': 1, 'builder_version': cBuilderVersion, 'kind': 'recovery',
    'created_utc': datetime.now(timezone.utc).isoformat(), 'requested_family': pSelected['id'],
    'detected': pVersion, 'requires_network_for_installation': True,
    'requires_compatible_opencore': True, 'opencore_included': False,
    'source': pSource, 'image_sha256': fHash(pImage), 'image_size': pImage.stat().st_size,
    'chunklist_sha256': fHash(pChunklist), 'apple_signature_verified': True,
    'trust_anchor': 'Apple EFI ROM public key 1, pinned from OpenCorePkg 1.0.7',
    'trust_anchor_sha256': hashlib.sha256(cAppleKey.to_bytes(256, 'big')).hexdigest(),
    'scope': 'Apple signature covers the recovery image, not this locally generated ISO wrapper or an external EFI'}
  if vOutput.exists():
    pContext.mLog('existing_iso', path=str(vOutput))
    dVerification = fVerifyIso(pContext, vOutput, dMetadata)
    fSaveIsoMetadata(vOutput, dMetadata, dVerification)
    return vOutput, dVerification, True
  fSpace(pContext.vOutput, pImage.stat().st_size + 128 * 1024 * 1024)
  with tempfile.TemporaryDirectory(dir=pContext.vWork, prefix='iso-staging-') as vDirectory:
    vStaging = Path(vDirectory)
    vRecovery = vStaging / cRecoveryDir
    vRecovery.mkdir()
    try:
      os.link(pImage, vRecovery / 'BaseSystem.dmg')
    except OSError:
      fSpace(vStaging, pImage.stat().st_size + 64 * 1024 * 1024)
      shutil.copyfile(pImage, vRecovery / 'BaseSystem.dmg')
    shutil.copyfile(pChunklist, vRecovery / 'BaseSystem.chunklist')
    (vRecovery / '.contentDetails').write_text(f'macOS {pVersion["version"]} Recovery', encoding='ascii')
    fWriteJson(vStaging / 'BUILDINFO.json', dMetadata)
    # Temporary ISO is on the destination filesystem, making publication atomic.
    vFd, vTemporaryName = tempfile.mkstemp(dir=pContext.vOutput, prefix='.macos-', suffix='.iso.part')
    os.close(vFd)
    vTemporary = Path(vTemporaryName)
    try:
      lCommand = [fTool('xorriso'), '-as', 'mkisofs', '-quiet', '-hfsplus', '-apm-block-size', '2048',
        '-iso-level', '3', '-R', '-J', '-V', 'MACOS_RECOVERY', '-o', str(vTemporary), str(vStaging)]
      fCommand(pContext, lCommand)
      pContext.mStage(6, 'stage_verify_iso')
      dVerification = fVerifyIso(pContext, vTemporary, dMetadata)
      # link() refuses to overwrite an output created concurrently.
      os.link(vTemporary, vOutput)
      fSaveIsoMetadata(vOutput, dMetadata, dVerification)
    finally:
      vTemporary.unlink(missing_ok=True)
  return vOutput, dVerification, False
