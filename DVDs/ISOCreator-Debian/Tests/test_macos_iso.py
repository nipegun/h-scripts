#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Security boundaries, interrupted downloads and version-selection regressions."""

import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.request import Request

cRoot = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(cRoot / 'Scripts'))

from macos_iso.catalog import fCheckVersion, fSelect
from macos_iso.common import BuildError, Context, fContext, fWriteJson
from macos_iso.crypto import Chunklist, fParseChunklist, fVerifiedPrefix, fVerifyImage, fVerifyReader
from macos_iso.network import AppleRedirect, fAppleUrl, fContentRange, fDownload, fManifest

cFixture = cRoot / 'Tests/fixtures/apple-tahoe-26.6.2.chunklist'


class RecoveryTests(unittest.TestCase):
  def mSetUp(pSelf):
    (cRoot / '_/temp').mkdir(parents=True, exist_ok=True)
    pSelf.vTemporary = tempfile.TemporaryDirectory(dir=cRoot / '_/temp', prefix='iso-tests-')
    pSelf.vWork = Path(pSelf.vTemporary.name)
    pSelf.vContext = Context(vQuiet=True, vWork=pSelf.vWork, vRetries=1)

  def mTearDown(pSelf):
    pSelf.vTemporary.cleanup()

  setUp = mSetUp
  tearDown = mTearDown

  def mManifest(pSelf):
    return Chunklist(((5, hashlib.sha256(b'abcde').digest()),
                      (5, hashlib.sha256(b'fghij').digest())), 10, 'test')

  def mTestActualAppleSignature(pSelf):
    vManifest = fParseChunklist(cFixture.read_bytes())
    pSelf.assertEqual(vManifest.vImageSize, 960530321)
    pSelf.assertEqual(len(vManifest.lChunks), 92)
    pSelf.assertEqual(vManifest.vSha256, '06f7c498f856341f467ba1faedf2717fb2c172ae0aff4658a1467cbf46b711f9')

  def mTestModifiedSignedHashIsRejected(pSelf):
    vData = bytearray(cFixture.read_bytes())
    vData[44] ^= 1
    with pSelf.assertRaisesRegex(BuildError, 'manifest_signature'):
      fParseChunklist(vData)

  def mTestModifiedSignatureIsRejected(pSelf):
    vData = bytearray(cFixture.read_bytes())
    vData[-30] ^= 1
    with pSelf.assertRaisesRegex(BuildError, 'manifest_signature'):
      fParseChunklist(vData)

  def mTestUnsignedChunklistIsRejected(pSelf):
    vData = bytearray(cFixture.read_bytes())
    vData[10] = 2
    with pSelf.assertRaisesRegex(BuildError, 'manifest_unsigned'):
      fParseChunklist(vData)

  def mTestMalformedChunklistBounds(pSelf):
    for vData in [b'CNKL', cFixture.read_bytes()[:-1], cFixture.read_bytes() + b'X']:
      with pSelf.subTest(size=len(vData)), pSelf.assertRaisesRegex(BuildError, 'manifest_structure'):
        fParseChunklist(vData)
    vData = bytearray(cFixture.read_bytes())
    struct.pack_into('<Q', vData, 12, 2 ** 63)
    with pSelf.assertRaisesRegex(BuildError, 'manifest_structure'):
      fParseChunklist(vData)

  def mTestVerificationSurvivesPythonOptimization(pSelf):
    vBad = pSelf.vWork / 'bad.chunklist'
    vData = bytearray(cFixture.read_bytes())
    vData[-1] ^= 1
    vBad.write_bytes(vData)
    vCode = (
      'import sys; from pathlib import Path; '
      'sys.path.insert(0, sys.argv[1]); '
      'from macos_iso.crypto import fParseChunklist; '
      'fParseChunklist(Path(sys.argv[2]).read_bytes())'
    )
    vResult = subprocess.run([sys.executable, '-O', '-B', '-c', vCode, str(cRoot / 'Scripts'), str(vBad)],
                            capture_output=True, text=True)
    pSelf.assertNotEqual(vResult.returncode, 0)
    pSelf.assertIn('manifest_signature', vResult.stderr)

  def mTestImageChunkTamper(pSelf):
    vImage = pSelf.vWork / 'image.dmg'
    vImage.write_bytes(b'abcdeXghij')
    with pSelf.assertRaisesRegex(BuildError, 'image_hash'):
      fVerifyImage(vImage, pSelf.mManifest())

  def mTestImageTrailingData(pSelf):
    vImage = pSelf.vWork / 'image.dmg'
    vImage.write_bytes(b'abcdefghijX')
    with pSelf.assertRaisesRegex(BuildError, 'image_size'):
      fVerifyImage(vImage, pSelf.mManifest())

  def mTestImageStreamVerification(pSelf):
    vData = io.BytesIO(b'abcdefghij')
    pSelf.assertEqual(fVerifyReader(vData.read, pSelf.mManifest()), hashlib.sha256(b'abcdefghij').hexdigest())
    with pSelf.assertRaisesRegex(BuildError, 'image_size'):
      fVerifyReader(io.BytesIO(b'abcdef').read, pSelf.mManifest())

  def mTestVerifiedResumePrefix(pSelf):
    vPartial = pSelf.vWork / 'part'
    vPartial.write_bytes(b'abcdeBAD')
    pSelf.assertEqual(fVerifiedPrefix(vPartial, pSelf.mManifest()), 5)
    vPartial.write_bytes(b'BAD')
    pSelf.assertEqual(fVerifiedPrefix(vPartial, pSelf.mManifest()), 0)

  def mTestResumedDownloadUsesAuthenticatedBoundary(pSelf):
    vDestination = pSelf.vWork / 'BaseSystem.dmg'
    vDestination.with_suffix('.dmg.part').write_bytes(b'abcdeBAD')
    vResponse = io.BytesIO(b'fghij')
    vResponse.headers = {'Content-Range': 'bytes 5-9/10'}
    vResponse.getcode = lambda: 206
    dInfo = {'AU': 'http://oscdn.apple.com/image.dmg', 'AT': 'temporary-token'}
    with mock.patch('macos_iso.network.fOpen', return_value=vResponse) as vOpen:
      fDownload(pSelf.vContext, dInfo, pSelf.mManifest(), vDestination)
    pSelf.assertEqual(vOpen.call_args.args[2]['Range'], 'bytes=5-')
    pSelf.assertEqual(vDestination.read_bytes(), b'abcdefghij')
    pSelf.assertFalse(vDestination.with_suffix('.dmg.part').exists())

  def mTestIgnoredRangeRestartsInsteadOfAppending(pSelf):
    vDestination = pSelf.vWork / 'BaseSystem.dmg'
    vDestination.with_suffix('.dmg.part').write_bytes(b'abcde')
    vResponse = io.BytesIO(b'abcdefghij')
    vResponse.headers = {}
    vResponse.getcode = lambda: 200
    with mock.patch('macos_iso.network.fOpen', return_value=vResponse):
      fDownload(pSelf.vContext, {'AU': 'http://oscdn.apple.com/image.dmg', 'AT': 'token'}, pSelf.mManifest(), vDestination)
    pSelf.assertEqual(vDestination.read_bytes(), b'abcdefghij')

  def mTestLyingRangeIsRejected(pSelf):
    vDestination = pSelf.vWork / 'BaseSystem.dmg'
    vDestination.with_suffix('.dmg.part').write_bytes(b'abcde')
    vResponse = io.BytesIO(b'fghij')
    vResponse.headers = {'Content-Range': 'bytes 5-7/10'}
    vResponse.getcode = lambda: 206
    with mock.patch('macos_iso.network.fOpen', return_value=vResponse), pSelf.assertRaisesRegex(BuildError, 'range_error'):
      fDownload(pSelf.vContext, {'AU': 'http://oscdn.apple.com/image.dmg', 'AT': 'token'}, pSelf.mManifest(), vDestination)
    pSelf.assertFalse(vDestination.exists())

  def mTestCorruptDownloadIsNeverPublished(pSelf):
    vDestination = pSelf.vWork / 'BaseSystem.dmg'
    vResponse = io.BytesIO(b'abcdeXXXXX')
    vResponse.headers = {}
    vResponse.getcode = lambda: 200
    with mock.patch('macos_iso.network.fOpen', return_value=vResponse), pSelf.assertRaisesRegex(BuildError, 'image_hash'):
      fDownload(pSelf.vContext, {'AU': 'http://oscdn.apple.com/image.dmg', 'AT': 'token'}, pSelf.mManifest(), vDestination)
    pSelf.assertFalse(vDestination.exists())

  def mTestSourceReferencesAreNotTreatedAsChecksums(pSelf):
    vResponse = io.BytesIO(cFixture.read_bytes())
    with mock.patch('macos_iso.network.fOpen', return_value=vResponse):
      vData, vManifest = fManifest(pSelf.vContext, {'CU': 'http://oscdn.apple.com/list', 'CT': 'token', 'CH': '0' * 64})
    pSelf.assertEqual(vManifest.vImageSize, 960530321)

  def mTestOnlyAppleEndpointsAccepted(pSelf):
    for vUrl in ['https://oscdn.apple.com.evil.test/x', 'https://apple.com@evil.test/x',
                'file:///etc/passwd', 'https://oscdn.apple.com:444/x', 'http://swcdn.apple.com/x']:
      with pSelf.subTest(url=vUrl), pSelf.assertRaises(BuildError):
        fAppleUrl(vUrl)
    pSelf.assertEqual(fAppleUrl('https://osrecovery.apple.com/'), 'https://osrecovery.apple.com/')

  def mTestHttpsOnlyAndRedirectDowngrade(pSelf):
    with pSelf.assertRaisesRegex(BuildError, 'http_forbidden'):
      fAppleUrl('http://oscdn.apple.com/x', True)
    with pSelf.assertRaisesRegex(BuildError, 'redirect_downgrade'):
      AppleRedirect().redirect_request(Request('https://osrecovery.apple.com/x'), None, 302, '', {}, 'http://oscdn.apple.com/x')

  def mTestRangeValidation(pSelf):
    pSelf.assertEqual(fContentRange('bytes 5-9/10', 5, 10), 5)
    for vHeader in ['bytes 0-9/10', 'bytes 5-9/11', 'bytes 5-10/10', 'nonsense']:
      with pSelf.subTest(header=vHeader), pSelf.assertRaisesRegex(BuildError, 'range_error'):
        fContentRange(vHeader, 5, 10)

  def mTestFamilyAndExactVersionSelection(pSelf):
    dTahoe, vExact = fSelect('macOS Tahoe')
    pSelf.assertEqual(dTahoe['id'], '26')
    pSelf.assertEqual(vExact, '')
    dLion, vExact = fSelect('10.7.5')
    pSelf.assertEqual((dLion['id'], vExact), ('10.7', '10.7.5'))
    dLion, vExact = fSelect('macOS 10.07.5')
    pSelf.assertEqual((dLion['id'], vExact), ('10.7', '10.7.5'))
    with pSelf.assertRaisesRegex(BuildError, 'version_mismatch'):
      fCheckVersion(dTahoe, '15.7.9')
    with pSelf.assertRaisesRegex(BuildError, 'exact_mismatch'):
      fCheckVersion(dLion, '10.7.4', '10.7.5')

  def mTestNoSymlinkOutputOverwrite(pSelf):
    vActual = pSelf.vWork / 'user-data.json'
    vActual.write_text('keep')
    vLink = pSelf.vWork / 'manifest.json'
    vLink.symlink_to(vActual)
    with pSelf.assertRaisesRegex(BuildError, 'unsafe_file'):
      fWriteJson(vLink, {'replace': True})
    pSelf.assertEqual(vActual.read_text(), 'keep')

  def mTestAllLocaleKeysAndPlaceholders(pSelf):
    import string
    dBase = json.loads((cRoot / 'Locales/macos_iso/en-US.json').read_text())
    for vFile in (cRoot / 'Locales/macos_iso').glob('*.json'):
      dLocale = json.loads(vFile.read_text())
      pSelf.assertEqual(set(dLocale), set(dBase))
      for vKey in dBase:
        sBase = {vField for vText, vField, vSpec, vConversion in string.Formatter().parse(dBase[vKey]) if vField}
        sLocale = {vField for vText, vField, vSpec, vConversion in string.Formatter().parse(dLocale[vKey]) if vField}
        pSelf.assertEqual(sBase, sLocale, f'{vFile.name}: {vKey}')

  def mTestCliRejectsUnsupportedAndFullModes(pSelf):
    for lFlags, vExpected in [(['--os', '10.6', '--non-interactive'], 'no Apple Internet Recovery selector'),
                              (['--os', '26', '--full'], 'full offline installer')]:
      vResult = subprocess.run([sys.executable, '-B', str(cRoot / 'Scripts/create_macos_iso.py'), *lFlags],
                              capture_output=True, text=True)
      pSelf.assertEqual(vResult.returncode, 1)
      pSelf.assertIn(vExpected, vResult.stderr)

  def mTestCliDryRunIsStructuredAndNetworkFree(pSelf):
    vResult = subprocess.run([sys.executable, '-B', str(cRoot / 'Scripts/create_macos_iso.py'),
      '--os', '26.6.2', '--dry-run', '--json'], capture_output=True, text=True)
    pSelf.assertEqual(vResult.returncode, 0, vResult.stderr)
    dResult = json.loads(vResult.stdout)
    pSelf.assertEqual(dResult['requested'], '26.6.2')
    pSelf.assertFalse(dResult['network_accessed'])


def fLoadTests(pLoader, pTests, pPattern):
  pLoader.testMethodPrefix = 'mTest'
  return pLoader.loadTestsFromTestCase(RecoveryTests)


load_tests = fLoadTests

if __name__ == '__main__':
  unittest.main()
