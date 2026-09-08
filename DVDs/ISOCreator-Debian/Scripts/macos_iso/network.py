"""Apple-only recovery discovery and authenticated, resumable downloads."""

import hashlib
import http.client
import http.cookies
import os
import re
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .common import BuildError, cIoSize, fCleanUrl, fFail, fRegularOrMissing, fSpace
from .crypto import cManifestLimit, fParseChunklist, fVerifiedPrefix, fVerifyImage

cRecoveryUrl = 'https://osrecovery.apple.com'
cAssetHosts = ('oscdn.apple.com', 'swcdn.apple.com', 'osrecovery.apple.com')
cTransientStatuses = (408, 429, 500, 502, 503, 504)


def fAppleUrl(pUrl, pHttpsOnly=False):
  if not pUrl or any(ord(vChar) < 32 for vChar in pUrl):
    fFail('unsafe_url')
  try:
    vParts = urllib.parse.urlsplit(pUrl)
    vPort = vParts.port
  except ValueError:
    fFail('unsafe_url')
  if (vParts.scheme not in ('http', 'https') or vParts.hostname not in cAssetHosts
      or vParts.username or vParts.password or vParts.fragment
      or vPort not in (None, 80 if vParts.scheme == 'http' else 443)):
    fFail('unsafe_url')
  if vParts.scheme == 'http' and (pHttpsOnly or vParts.hostname != 'oscdn.apple.com'):
    fFail('http_forbidden', host=vParts.hostname)
  return pUrl


class AppleRedirect(urllib.request.HTTPRedirectHandler):
  # This standard-library callback name is required by urllib.
  def redirect_request(pSelf, pRequest, pFile, pCode, pMessage, pHeaders, pNewUrl):
    fAppleUrl(pNewUrl, getattr(pSelf, 'vHttpsOnly', False))
    vOld = urllib.parse.urlsplit(pRequest.full_url)
    vNew = urllib.parse.urlsplit(pNewUrl)
    if vOld.scheme == 'https' and vNew.scheme != 'https':
      fFail('redirect_downgrade')
    vRequest = super().redirect_request(pRequest, pFile, pCode, pMessage, pHeaders, pNewUrl)
    if vRequest is not None and vOld.hostname != vNew.hostname:
      for vName in ('Cookie', 'Authorization'):
        vRequest.remove_header(vName)
    return vRequest


def fOpen(pContext, pUrl, pHeaders=None, pData=None):
  fAppleUrl(pUrl, pContext.vHttpsOnly)
  vHost = urllib.parse.urlsplit(pUrl).hostname
  dHeaders = {'User-Agent': 'InternetRecovery/1.0', 'Connection': 'close'}
  dHeaders.update(pHeaders or {})
  vRedirect = AppleRedirect()
  vRedirect.vHttpsOnly = pContext.vHttpsOnly
  vOpener = urllib.request.build_opener(vRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
  for vAttempt in range(pContext.vRetries):
    try:
      return vOpener.open(urllib.request.Request(pUrl, data=pData, headers=dHeaders), timeout=pContext.vTimeout)
    except urllib.error.HTTPError as vError:
      vStatus = vError.code
      vError.close()
      if vStatus not in cTransientStatuses or vAttempt + 1 == pContext.vRetries:
        fFail('http_error', host=vHost, status=vStatus)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as vError:
      vReason = getattr(vError, 'reason', vError)
      if isinstance(vReason, ssl.SSLCertVerificationError):
        fFail('tls_error', host=vHost)
      if vAttempt + 1 == pContext.vRetries:
        fFail('network_error', host=vHost)
    pContext.mLog('network_retry', attempt=vAttempt + 1, total=pContext.vRetries, host=vHost)
    time.sleep(min(2 ** vAttempt, 8))
  fFail('network_error', host=vHost)


def fReadBounded(pResponse, pLimit):
  vData = pResponse.read(pLimit + 1)
  if len(vData) > pLimit:
    fFail('response_large')
  return vData


def fDiscover(pContext, pSelector):
  if (not re.fullmatch(r'Mac-[0-9A-Fa-f]{16}', pSelector['board'])
      or not re.fullmatch(r'[A-Za-z0-9]{17}', pSelector['mlb'])
      or pSelector['os'] not in ('default', 'latest')):
    fFail('invalid_selector')
  with fOpen(pContext, cRecoveryUrl + '/') as vResponse:
    vCookies = http.cookies.SimpleCookie()
    try:
      for vCookie in vResponse.headers.get_all('Set-Cookie', []):
        vCookies.load(vCookie)
    except http.cookies.CookieError:
      fFail('apple_response')
  if 'session' not in vCookies:
    fFail('apple_response')
  dPost = {'cid': secrets.token_hex(8).upper(), 'sn': pSelector['mlb'],
            'bid': pSelector['board'], 'k': secrets.token_hex(32).upper(),
            'fg': secrets.token_hex(32).upper(), 'os': pSelector['os']}
  vBody = '\n'.join(f'{vKey}={vValue}' for vKey, vValue in dPost.items()).encode('ascii')
  dHeaders = {'Cookie': 'session=' + vCookies['session'].value, 'Content-Type': 'text/plain'}
  with fOpen(pContext, cRecoveryUrl + '/InstallationPayload/RecoveryImage', dHeaders, vBody) as vResponse:
    try:
      vText = fReadBounded(vResponse, 65536).decode('utf-8')
    except UnicodeDecodeError:
      fFail('apple_response')
  dInfo = {}
  for vLine in vText.splitlines():
    if ': ' in vLine:
      vKey, vValue = vLine.split(': ', 1)
      if vKey in dInfo:
        fFail('apple_response')
      dInfo[vKey] = vValue.strip()
  if any(not dInfo.get(vKey) for vKey in ('AP', 'AU', 'AH', 'AT', 'CU', 'CH', 'CT')):
    fFail('apple_response')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', dInfo['AP']):
    fFail('apple_response')
  for vKey in ('AT', 'CT'):
    if len(dInfo[vKey]) > 8192 or any(not 33 <= ord(vChar) <= 126 for vChar in dInfo[vKey]):
      fFail('apple_response')
  for vKey in ('AH', 'CH'):
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})', dInfo[vKey]):
      fFail('apple_response')
  fAppleUrl(dInfo['AU'], pContext.vHttpsOnly)
  fAppleUrl(dInfo['CU'], pContext.vHttpsOnly)
  if urllib.parse.urlsplit(dInfo['AU']).scheme == 'http' or urllib.parse.urlsplit(dInfo['CU']).scheme == 'http':
    pContext.mLog('http_signed_transport')
  return dInfo


def fManifest(pContext, pInfo):
  with fOpen(pContext, pInfo['CU'], {'Cookie': 'AssetToken=' + pInfo['CT']}) as vResponse:
    vData = fReadBounded(vResponse, cManifestLimit)
  # AH/CH are session references, not file digests. The signed CNKL is the trust anchor.
  return vData, fParseChunklist(vData)


def fContentRange(pValue, pStart, pSize):
  vMatch = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', pValue or '')
  if not vMatch:
    fFail('range_error')
  vStart, vEnd, vTotal = map(int, vMatch.groups())
  if vStart != pStart or vTotal != pSize or not vStart <= vEnd < vTotal:
    fFail('range_error')
  return vEnd - vStart + 1


def fDownload(pContext, pInfo, pManifest, pDestination):
  fRegularOrMissing(pDestination)
  vPartial = pDestination.with_suffix('.dmg.part')
  fRegularOrMissing(vPartial)
  if pDestination.exists():
    pContext.mLog('cached_image')
    fVerifyImage(pDestination, pManifest, pContext.mProgress)
    pContext.mEndProgress()
    return pDestination
  for vAttempt in range(pContext.vRetries):
    vOffset = fVerifiedPrefix(vPartial, pManifest, pContext.mProgress)
    pContext.mEndProgress()
    if vPartial.exists():
      with vPartial.open('r+b') as vFile:
        vFile.truncate(vOffset)
    if vOffset == pManifest.vImageSize:
      os.replace(vPartial, pDestination)
      return pDestination
    fSpace(pDestination.parent, pManifest.vImageSize - vOffset + 64 * 1024 * 1024)
    if vOffset:
      pContext.mLog('resuming', size=f'{vOffset / 1048576:.1f} MiB')
    dHeaders = {'Cookie': 'AssetToken=' + pInfo['AT']}
    if vOffset:
      dHeaders['Range'] = f'bytes={vOffset}-'
    try:
      with fOpen(pContext, pInfo['AU'], dHeaders) as vResponse:
        vStatus = vResponse.getcode()
        vResponseLength = None
        if vStatus == 206:
          vResponseLength = fContentRange(vResponse.headers.get('Content-Range'), vOffset, pManifest.vImageSize)
        elif vStatus == 200:
          if vOffset:
            pContext.mLog('range_restart')
          vOffset = 0
        else:
          fFail('range_error')
        vMode = 'r+b' if vPartial.exists() else 'w+b'
        with vPartial.open(vMode) as vFile:
          vFile.truncate(vOffset)
          vFile.seek(vOffset)
          vDone = vOffset
          while True:
            vData = vResponse.read(cIoSize)
            if not vData:
              break
            if vDone + len(vData) > pManifest.vImageSize:
              fFail('image_size', expected=pManifest.vImageSize, actual=vDone + len(vData))
            vFile.write(vData)
            vDone += len(vData)
            pContext.mProgress(vDone, pManifest.vImageSize)
          vFile.flush()
          os.fsync(vFile.fileno())
        if vResponseLength is not None and vDone - vOffset != vResponseLength:
          fFail('range_error')
      if vDone != pManifest.vImageSize:
        raise http.client.IncompleteRead(b'')
      pContext.mProgress(vDone, pManifest.vImageSize, True)
      pContext.mEndProgress()
      fVerifyImage(vPartial, pManifest, pContext.mProgress)
      pContext.mEndProgress()
      os.replace(vPartial, pDestination)
      return pDestination
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead, http.client.RemoteDisconnected):
      pContext.mEndProgress()
      if vAttempt + 1 == pContext.vRetries:
        fFail('download_interrupted', path=str(vPartial))
      pContext.mLog('download_retry', attempt=vAttempt + 1, total=pContext.vRetries)
      time.sleep(min(2 ** vAttempt, 8))
  fFail('download_interrupted', path=str(vPartial))


def fPublicSource(pInfo, pSelector):
  return {'type': 'Apple Internet Recovery', 'product_id': pInfo['AP'],
          'discovery_url': cRecoveryUrl + '/InstallationPayload/RecoveryImage',
          'image_url': fCleanUrl(pInfo['AU']), 'chunklist_url': fCleanUrl(pInfo['CU']),
          'board_id': pSelector['board'], 'request_type': pSelector['os']}
