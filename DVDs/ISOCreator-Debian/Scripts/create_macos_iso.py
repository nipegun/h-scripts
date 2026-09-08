#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Interactive, verified Apple recovery ISO builder for Debian."""

import sys

if sys.version_info < (3, 13):
  raise SystemExit('Python 3.13 or newer is required (Debian 13).')

sys.dont_write_bytecode = True

from macos_iso.cli import fMain

if __name__ == '__main__':
  raise SystemExit(fMain())
