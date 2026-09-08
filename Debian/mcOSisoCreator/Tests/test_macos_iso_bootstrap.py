#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Distribution integrity and real stdin-pipeline launcher regressions."""

import hashlib
import io
import json
import os
from pathlib import Path
import pty
import select
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

cRoot = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(cRoot))
sys.path.insert(0, str(cRoot / 'Scripts'))

import mcOSisoCreator as launcher
import package_macos_iso as packager


class BootstrapTests(unittest.TestCase):
  def mSetUp(pSelf):
    (cRoot / '_/temp').mkdir(parents=True, exist_ok=True)
    pSelf.vTemporary = tempfile.TemporaryDirectory(dir=cRoot / '_/temp', prefix='bootstrap-tests-')
    pSelf.vWork = Path(pSelf.vTemporary.name)
    pSelf.dFiles = packager.fRuntimeFiles()
    pSelf.vArchive = packager.fArchive(pSelf.dFiles)
    pSelf.vDigest = hashlib.sha256(pSelf.vArchive).hexdigest()
    pSelf.vBundle = pSelf.vWork / 'bundle.zip'
    pSelf.vBundle.write_bytes(pSelf.vArchive)

  def mTearDown(pSelf):
    pSelf.vTemporary.cleanup()

  setUp = mSetUp
  tearDown = mTearDown

  def mTestArchiveIsReproducible(pSelf):
    pSelf.assertEqual(pSelf.vArchive, packager.fArchive(pSelf.dFiles))

  def mTestPackageMatchesLauncher(pSelf):
    pSelf.assertEqual(pSelf.vDigest, launcher.cBundleSha256)
    pSelf.assertTrue(launcher.cRequired.issubset(pSelf.dFiles))

  def mTestWrongDigestIsRejectedBeforeExtraction(pSelf):
    with pSelf.assertRaisesRegex(launcher.LauncherError, 'SHA-256'):
      launcher.fInstall(pSelf.vWork, pSelf.vBundle, '0' * 64)
    pSelf.assertFalse(list(pSelf.vWork.glob('runtime-*')))

  def mTestArchiveTraversalAndLinksAreRejected(pSelf):
    for vName, vMode in [('../escaped', stat.S_IFREG), ('/absolute', stat.S_IFREG),
        ('Scripts/../../escaped', stat.S_IFREG), ('link', stat.S_IFLNK),
        ('Scripts\\escape', stat.S_IFREG), ('Scripts//escape', stat.S_IFREG)]:
      vBuffer = io.BytesIO()
      with zipfile.ZipFile(vBuffer, 'w') as vZip:
        vInfo = zipfile.ZipInfo(vName)
        vInfo.external_attr = (vMode | 0o644) << 16
        vZip.writestr(vInfo, b'bad')
      with pSelf.subTest(path=vName), pSelf.assertRaises(launcher.LauncherError):
        launcher.fArchive(vBuffer.getvalue())
    pSelf.assertFalse((pSelf.vWork.parent / 'escaped').exists())

  def mTestModifiedOrInjectedCachedCodeIsRejected(pSelf):
    vRuntime = launcher.fInstall(pSelf.vWork, pSelf.vBundle, pSelf.vDigest)
    vExtra = vRuntime / 'Scripts/macos_iso/__init__.py'
    vExtra.write_text('raise SystemExit("injected")')
    with pSelf.assertRaisesRegex(launcher.LauncherError, 'modified'):
      launcher.fInstall(pSelf.vWork, pSelf.vBundle, pSelf.vDigest)
    vExtra.unlink()
    (vRuntime / 'Scripts/macos_iso/cli.py').write_text('raise SystemExit("changed")')
    with pSelf.assertRaisesRegex(launcher.LauncherError, 'modified'):
      launcher.fInstall(pSelf.vWork, pSelf.vBundle, pSelf.vDigest)

  def mTestIncompleteRuntimeIsRejected(pSelf):
    vRuntime = launcher.fInstall(pSelf.vWork, pSelf.vBundle, pSelf.vDigest)
    (vRuntime / 'Scripts/macos_iso/crypto.py').unlink()
    with pSelf.assertRaisesRegex(launcher.LauncherError, 'incomplete'):
      launcher.fInstall(pSelf.vWork, pSelf.vBundle, pSelf.vDigest)

  def mTestSymlinkWorkspaceCacheIsRejected(pSelf):
    (pSelf.vWork / '_').symlink_to(cRoot, target_is_directory=True)
    with pSelf.assertRaisesRegex(launcher.LauncherError, 'Unsafe directory'):
      launcher.fDirectory(pSelf.vWork, '_/temp/bootstrap')

  def mTestHttpsPolicy(pSelf):
    launcher.fGithubUrl(launcher.cBaseUrl + '/file.zip')
    for vUrl in ('http://raw.githubusercontent.com/file', 'https://example.com/file',
        'https://user@raw.githubusercontent.com/file', 'https://raw.githubusercontent.com:444/file'):
      with pSelf.subTest(url=vUrl), pSelf.assertRaises(launcher.LauncherError):
        launcher.fGithubUrl(vUrl)

  def mTestDownloadedDigestFailureLeavesNoPublishedFile(pSelf):
    vResponse = io.BytesIO(b'modified archive')
    vResponse.status = 200
    vDestination = pSelf.vWork / 'downloaded.zip'
    with mock.patch.object(launcher.urllib.request, 'build_opener') as vOpener:
      vOpener.return_value.open.return_value = vResponse
      with pSelf.assertRaisesRegex(launcher.LauncherError, 'SHA-256'):
        launcher.fDownload(launcher.cBaseUrl + '/file.zip', vDestination, pSelf.vDigest)
    pSelf.assertFalse(vDestination.exists())
    pSelf.assertFalse(list(pSelf.vWork.glob('download-*')))

  def mTestVerifiedCacheNeedsNoNetwork(pSelf):
    with mock.patch.object(launcher.urllib.request, 'build_opener', side_effect=AssertionError('Unexpected network')):
      launcher.fDownload(launcher.cBaseUrl + '/file.zip', pSelf.vBundle, pSelf.vDigest)

  def mPipeline(pSelf, pArguments):
    vWorkspace = pSelf.vWork / 'workspace with spaces'
    vCache = vWorkspace / '_/temp/bootstrap'
    vCache.mkdir(parents=True, exist_ok=True)
    (vCache / f'runtime-{pSelf.vDigest}.zip').write_bytes(pSelf.vArchive)
    (vWorkspace / 'ISOs').mkdir(exist_ok=True)
    (vWorkspace / 'ISOs/existing.iso').write_bytes(b'existing output')
    vResult = subprocess.run([sys.executable, '-B', '-', '--directory', str(vWorkspace), *pArguments],
      input=(cRoot / 'mcOSisoCreator.py').read_text(), capture_output=True, text=True, timeout=30,
      env=dict(os.environ, MCOS_ISO_CREATOR_WORKSPACE='/invalid/inherited/workspace'))
    pSelf.assertEqual((vWorkspace / 'ISOs/existing.iso').read_bytes(), b'existing output')
    return vWorkspace, vResult

  def mTestActualStdinPipelineForwardsArgumentsAndKeepsOutputs(pSelf):
    vWorkspace, vResult = pSelf.mPipeline(['--os', 'Tahoe', '--dry-run', '--json', '--non-interactive'])
    pSelf.assertEqual(vResult.returncode, 0, vResult.stderr)
    dResult = json.loads(vResult.stdout)
    pSelf.assertEqual(dResult['output_directory'], str(vWorkspace / 'ISOs'))
    pSelf.assertEqual(dResult['work_directory'], str(vWorkspace / '_/temp/macos-iso'))
    pSelf.assertFalse(dResult['network_accessed'])
    for vName in ('AGENTS.md', 'CLAUDE.md', 'ReglasParaEsteProyecto.md'):
      pSelf.assertTrue((vWorkspace / vName).is_file())

  def mTestActualStdinPipelineWithoutSelectionFailsClearly(pSelf):
    vWorkspace, vResult = pSelf.mPipeline(['--non-interactive', '--language', 'es-ES'])
    pSelf.assertEqual(vResult.returncode, 1)
    pSelf.assertIn('--os', vResult.stderr)
    pSelf.assertNotIn('Traceback', vResult.stderr)

  def mTestActualPipeWithControllingTerminalSelectsVersion(pSelf):
    vWorkspace = pSelf.vWork / 'interactive'
    vCache = vWorkspace / '_/temp/bootstrap'
    vCache.mkdir(parents=True)
    (vCache / f'runtime-{pSelf.vDigest}.zip').write_bytes(pSelf.vArchive)
    vRead, vWrite = os.pipe()
    vPid, vTerminal = pty.fork()
    if vPid == 0:
      os.close(vWrite)
      os.dup2(vRead, 0)
      os.close(vRead)
      os.execv(sys.executable, [sys.executable, '-B', '-', '--directory', str(vWorkspace),
        '--language', 'es-ES', '--dry-run'])
    os.close(vRead)
    vReaped, vOutput = False, b''
    try:
      vSource = (cRoot / 'mcOSisoCreator.py').read_bytes()
      while vSource:
        vSource = vSource[os.write(vWrite, vSource):]
      os.close(vWrite)
      vWrite = None
      os.write(vTerminal, b'Tahoe\n')
      vDeadline = time.monotonic() + 15
      while time.monotonic() < vDeadline:
        if select.select([vTerminal], [], [], .1)[0]:
          try:
            vData = os.read(vTerminal, 65536)
          except OSError:
            break
          if not vData:
            break
          vOutput += vData
        vWaitPid, vStatus = os.waitpid(vPid, os.WNOHANG)
        if vWaitPid:
          vReaped = True
          break
      while not vReaped and time.monotonic() < vDeadline:
        vWaitPid, vStatus = os.waitpid(vPid, os.WNOHANG)
        vReaped = bool(vWaitPid)
        if not vReaped:
          time.sleep(.01)
      pSelf.assertTrue(vReaped, 'Interactive pipeline did not finish: ' + vOutput.decode(errors='replace'))
      pSelf.assertEqual(os.waitstatus_to_exitcode(vStatus), 0, vOutput.decode(errors='replace'))
      pSelf.assertIn(str(vWorkspace / 'ISOs').encode(), vOutput)
    finally:
      if vWrite is not None:
        os.close(vWrite)
      os.close(vTerminal)
      if not vReaped:
        os.kill(vPid, 9)
        os.waitpid(vPid, 0)

  def mTestTerminalIsReopenedForPipedInteractiveExecution(pSelf):
    vTerminal = io.StringIO()
    with mock.patch.object(launcher.sys.stdin, 'isatty', return_value=False), \
         mock.patch('builtins.open', return_value=vTerminal) as vOpen, \
         mock.patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as vRun:
      vCode = launcher.fLaunch(pSelf.vWork, pSelf.vWork, ['--dry-run'])
    vOpen.assert_called_once_with('/dev/tty', 'r', encoding='utf-8')
    pSelf.assertIs(vRun.call_args.kwargs['stdin'], vTerminal)
    pSelf.assertEqual(vCode, 7)

  def mTestBootstrapLocalesMatchEmbeddedMessages(pSelf):
    for vLocale in ('en-GB', 'en-US', 'es-AR', 'es-ES'):
      dSource = json.loads((cRoot / 'Locales/bootstrap' / f'{vLocale}.json').read_text())
      pSelf.assertEqual(launcher.dMessages[vLocale], dSource)
      pSelf.assertEqual(set(dSource), set(launcher.dMessages['en-US']))


def fLoadTests(pLoader, pTests, pPattern):
  pLoader.testMethodPrefix = 'mTest'
  return pLoader.loadTestsFromTestCase(BootstrapTests)


load_tests = fLoadTests

if __name__ == '__main__':
  unittest.main()
