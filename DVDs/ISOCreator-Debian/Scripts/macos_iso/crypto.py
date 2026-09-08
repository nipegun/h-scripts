"""Fail-closed Apple chunklist verification, independent of Python assertions.

Protocol and Apple EFI ROM key reference:
acidanthera/OpenCorePkg 1.0.7 Utilities/macrecovery/macrecovery.py,
Copyright (c) 2019 vit9696. Original license: ThirdParty/Licenses/OpenCore-LICENSE.txt.
"""

from dataclasses import dataclass
import hashlib
import hmac
import struct

from .common import cIoSize, fFail

cAppleKey = int(
  'C3E748CAD9CD384329E10E25A91E43E1A762FF529ADE578C935BDDF9B13F2179D4855E6FC89E9E29CA12517D17DFA1EDCE0BEBF0EA7B461FFE61D94E2BDF72C196F89ACD3536B644064014DAE25A15DB6BB0852ECBD120916318D1CCDEA3C84C92ED743FC176D0BACA920D3FCF3158AFF731F88CE0623182A8ED67E650515F75745909F07D415F55FC15A35654D118C55A462D37A3ACDA08612F3F3F6571761EFCCBCC299AEE99B3A4FD6212CCFFF5EF37A2C334E871191F7E1C31960E010A54E86FA3F62E6D6905E1CD57732410A3EB0C6B4DEFDABE9F59BF1618758C751CD56CEF851D1C0EAA1C558E37AC108DA9089863D20E2E7E4BF475EC66FE6B3EFDCF',
  16)
cHeader = struct.Struct('<4sIBBBxQQQ')
cChunk = struct.Struct('<I32s')
cManifestLimit = 40 * 1024 * 1024
cImageLimit = 32 * 1024 * 1024 * 1024
cDigestInfo = bytes.fromhex('3031300d060960864801650304020105000420')


@dataclass(frozen=True)
class Chunklist:
  lChunks: tuple
  vImageSize: int
  vSha256: str


def fParseChunklist(pData, pPublicKey=cAppleKey):
  if not cHeader.size + 256 <= len(pData) <= cManifestLimit:
    fFail('manifest_structure')
  vMagic, vHeader, vVersion, vChunkMethod, vSignatureMethod, vCount, vChunkOffset, vSignatureOffset = cHeader.unpack_from(pData)
  if vSignatureMethod != 1:
    fFail('manifest_unsigned')
  if (vMagic != b'CNKL' or vHeader != cHeader.size or vVersion != 1 or vChunkMethod != 1
      or not 1 <= vCount <= 1000000 or vChunkOffset != cHeader.size
      or vSignatureOffset != cHeader.size + vCount * cChunk.size
      or len(pData) != vSignatureOffset + 256):
    fFail('manifest_structure')
  vSignature = int.from_bytes(pData[vSignatureOffset:], 'little')
  if vSignature >= pPublicKey or pPublicKey.bit_length() != 2048:
    fFail('manifest_signature')
  vDigest = hashlib.sha256(pData[:vSignatureOffset]).digest()
  vEncoded = pow(vSignature, 65537, pPublicKey).to_bytes(256, 'big')
  vExpected = b'\x00\x01' + b'\xff' * (256 - 3 - len(cDigestInfo) - len(vDigest)) + b'\x00' + cDigestInfo + vDigest
  if not hmac.compare_digest(vEncoded, vExpected):
    fFail('manifest_signature')
  lChunks = tuple(cChunk.unpack_from(pData, cHeader.size + vIndex * cChunk.size) for vIndex in range(vCount))
  vSize = sum(vLength for vLength, vHash in lChunks)
  if any(vLength <= 0 for vLength, vHash in lChunks) or not 0 < vSize <= cImageLimit:
    fFail('manifest_structure')
  return Chunklist(lChunks, vSize, hashlib.sha256(pData).hexdigest())


def fVerifiedPrefix(pPath, pManifest, pProgress=None):
  """Return the end of the last complete, authenticated chunk in a partial file."""
  if not pPath.exists():
    return 0
  vVerified = 0
  with pPath.open('rb') as vFile:
    for vLength, vExpected in pManifest.lChunks:
      vHash = hashlib.sha256()
      vRemaining = vLength
      while vRemaining:
        vData = vFile.read(min(cIoSize, vRemaining))
        if not vData:
          return vVerified
        vHash.update(vData)
        vRemaining -= len(vData)
      if not hmac.compare_digest(vHash.digest(), vExpected):
        return vVerified
      vVerified += vLength
      if pProgress:
        pProgress(vVerified, pManifest.vImageSize)
  return vVerified


def fVerifyImage(pPath, pManifest, pProgress=None):
  if pPath.stat().st_size != pManifest.vImageSize:
    fFail('image_size', expected=pManifest.vImageSize, actual=pPath.stat().st_size)
  if fVerifiedPrefix(pPath, pManifest, pProgress) != pManifest.vImageSize:
    fFail('image_hash')
  return True


def fVerifyReader(pRead, pManifest, pProgress=None):
  """Verify an image stream and return its whole-image digest."""
  vTotal = 0
  vWhole = hashlib.sha256()
  for vLength, vExpected in pManifest.lChunks:
    vRemaining = vLength
    vHash = hashlib.sha256()
    while vRemaining:
      vData = pRead(min(cIoSize, vRemaining))
      if not vData or len(vData) > vRemaining:
        fFail('image_size', expected=pManifest.vImageSize, actual=vTotal)
      vHash.update(vData)
      vWhole.update(vData)
      vTotal += len(vData)
      vRemaining -= len(vData)
      if pProgress:
        pProgress(vTotal, pManifest.vImageSize)
    if not hmac.compare_digest(vHash.digest(), vExpected):
      fFail('image_hash')
  if pRead(1):
    fFail('image_size', expected=pManifest.vImageSize, actual=vTotal + 1)
  return vWhole.hexdigest()
