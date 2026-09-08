"""Shared errors, localization, progress and safe file operations."""

import contextlib
from dataclasses import dataclass, field
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

cRoot = Path(__file__).resolve().parents[2]
cWorkspace = Path(os.environ.get('MCOS_ISO_CREATOR_WORKSPACE', str(cRoot))).resolve()
cBuilderVersion = '1.1.0'
cLanguages = ('en-GB', 'en-US', 'es-AR', 'es-ES')
cIoSize = 1024 * 1024


class BuildError(Exception):
  """An error identified by a localizable key and structured parameters."""


def fFail(pKey, **pFields):
  vError = BuildError(pKey)
  vError.dFields = pFields
  raise vError


def fJson(pPath):
  return json.loads(pPath.read_text(encoding='utf-8'))


def fWriteJson(pPath, pValue):
  fRegularOrMissing(pPath)
  vTemporary = pPath.with_name(pPath.name + '.tmp')
  fRegularOrMissing(vTemporary)
  with vTemporary.open('w', encoding='utf-8') as vFile:
    json.dump(pValue, vFile, ensure_ascii=False, indent=2)
    vFile.write('\n')
    vFile.flush()
    os.fsync(vFile.fileno())
  os.replace(vTemporary, pPath)


def fHash(pPath):
  with pPath.open('rb') as vFile:
    return hashlib.file_digest(vFile, 'sha256').hexdigest()


def fRegularOrMissing(pPath):
  if pPath.is_symlink() or (pPath.exists() and not pPath.is_file()):
    fFail('unsafe_file', path=str(pPath))


def fSpace(pDirectory, pBytes):
  vAvailable = shutil.disk_usage(pDirectory).free
  if vAvailable < pBytes:
    fFail('disk_space', need=fSize(pBytes), available=fSize(vAvailable), path=str(pDirectory))


def fSize(pBytes):
  vValue = float(pBytes)
  for vUnit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
    if vValue < 1024 or vUnit == 'TiB':
      return f'{vValue:.1f} {vUnit}'
    vValue /= 1024


def fCleanUrl(pUrl):
  from urllib.parse import urlsplit, urlunsplit
  vParts = urlsplit(pUrl)
  return urlunsplit((vParts.scheme, vParts.netloc, vParts.path, '', ''))


@contextlib.contextmanager
def fLock(pPath):
  fRegularOrMissing(pPath)
  with pPath.open('a') as vFile:
    try:
      fcntl.flock(vFile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      fFail('locked', path=str(pPath))
    try:
      yield
    finally:
      fcntl.flock(vFile, fcntl.LOCK_UN)


@dataclass
class Context:
  vLanguage: str = 'en-US'
  vQuiet: bool = False
  vTimeout: int = 45
  vRetries: int = 4
  vHttpsOnly: bool = False
  vWork: Path = cWorkspace / '_/temp/macos-iso'
  vOutput: Path = cWorkspace / 'ISOs'
  dMessages: dict = field(default_factory=dict)
  vLastProgress: float = 0
  vProgressVisible: bool = False

  def mText(pSelf, pKey, **pFields):
    return pSelf.dMessages.get(pKey, pKey).format(**pFields)

  def mLog(pSelf, pKey, **pFields):
    pSelf.mEndProgress()
    if not pSelf.vQuiet:
      print(pSelf.mText(pKey, **pFields), flush=True)

  def mStage(pSelf, pNumber, pKey):
    pSelf.mLog('stage', number=pNumber, total=6, task=pSelf.mText(pKey))

  def mProgress(pSelf, pDone, pTotal, pForce=False):
    if pSelf.vQuiet:
      return
    vNow = time.monotonic()
    vInterval = .3 if sys.stdout.isatty() else 10
    if not pForce and vNow - pSelf.vLastProgress < vInterval:
      return
    pSelf.vLastProgress = vNow
    vPercent = 100 * pDone / pTotal if pTotal else 0
    vLine = pSelf.mText('progress', done=fSize(pDone), total=fSize(pTotal), percent=f'{vPercent:.1f}')
    print(('\r' if sys.stdout.isatty() else '') + vLine,
          end='' if sys.stdout.isatty() else '\n', flush=True)
    pSelf.vProgressVisible = sys.stdout.isatty()

  def mEndProgress(pSelf):
    if pSelf.vProgressVisible:
      print(flush=True)
      pSelf.vProgressVisible = False


def fContext(pLanguage='en-US', **pFields):
  if pLanguage not in cLanguages:
    pLanguage = 'en-US'
  dBase = fJson(cRoot / 'Locales/macos_iso/en-US.json')
  if pLanguage != 'en-US':
    dBase.update(fJson(cRoot / 'Locales/macos_iso' / f'{pLanguage}.json'))
  return Context(vLanguage=pLanguage, dMessages=dBase, **pFields)
