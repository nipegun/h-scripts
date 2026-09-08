"""Apple recovery selectors from the pinned OpenCore 1.0.7 documentation."""

import re

from .common import BuildError, cRoot, fFail, fJson


def fCatalog():
  return fJson(cRoot / 'Sources/macos-recovery-versions.json')['versions']


def fFamily(pVersion):
  lParts = pVersion.split('.')
  if not all(vPart.isdigit() for vPart in lParts):
    fFail('invalid_version', version=pVersion)
  if lParts[0] == '10':
    if len(lParts) < 2:
      fFail('invalid_version', version=pVersion)
    return f'10.{int(lParts[1])}'
  return str(int(lParts[0]))


def fSelect(pValue):
  vInput = pValue.strip().lower().replace('_', ' ').replace('-', ' ')
  vInput = re.sub(r'^(macos|mac os x|os x)\s+', '', vInput)
  for dVersion in fCatalog():
    if vInput in [dVersion['id'].lower(), dVersion['name'].lower(), dVersion['name'].lower().replace(' ', '')] + dVersion.get('aliases', []):
      return dVersion, ''
  if re.fullmatch(r'\d+(?:\.\d+){1,2}', vInput):
    vCanonical = '.'.join(str(int(vPart)) for vPart in vInput.split('.'))
    vFamily = fFamily(vCanonical)
    for dVersion in fCatalog():
      if dVersion['id'] == vFamily:
        return dVersion, vCanonical
  fFail('unknown_version', version=pValue)


def fCheckVersion(pSelected, pDetected, pExact=''):
  if fFamily(pDetected) != pSelected['id'] and pSelected['id'] != 'latest':
    fFail('version_mismatch', requested=pSelected['id'], actual=pDetected)
  if pExact and pDetected != pExact:
    fFail('exact_mismatch', requested=pExact, actual=pDetected)


def fMenu(pContext):
  lVersions = fCatalog()
  print(pContext.mText('menu_title'))
  print(pContext.mText('recovery_notice'))
  vLastGroup = None
  for vIndex, dVersion in enumerate(lVersions, 1):
    vGroup = dVersion.get('group')
    if vGroup and vGroup != vLastGroup:
      print('\n' + pContext.mText('group_' + vGroup))
      vLastGroup = vGroup
    vMode = pContext.mText('mode_apple' if dVersion.get('selectors') else 'mode_unavailable')
    print(f'{vIndex:2}. {dVersion["id"]:8} {dVersion["name"]:18} {vMode}')
  while True:
    try:
      vAnswer = input(pContext.mText('menu_prompt')).strip()
    except EOFError:
      fFail('interactive_required')
    if vAnswer == '0':
      raise KeyboardInterrupt
    if vAnswer.isdigit() and 1 <= int(vAnswer) <= len(lVersions):
      return lVersions[int(vAnswer) - 1], ''
    try:
      return fSelect(vAnswer)
    except BuildError:
      print(pContext.mText('menu_invalid'))
