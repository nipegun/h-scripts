# Apple-signed test fixture

`apple-tahoe-26.6.2.chunklist` is the small signed manifest accompanying Apple's
Tahoe 26.6.2 recovery product 140-93589, downloaded on 2026-09-08 using the
OpenCorePkg 1.0.7 recovery protocol. It contains hashes and a signature, not the
operating system image.

Manifest SHA-256: `06f7c498f856341f467ba1faedf2717fb2c172ae0aff4658a1467cbf46b711f9`.

Its 92 chunks describe a 960,530,321-byte recovery DMG. The fixture tests a real
Apple RSA signature and rejects mutations without a test-only bypass or a fake
production signing key.

Protocol/key reference: [OpenCorePkg macrecovery.py 1.0.7](https://github.com/acidanthera/OpenCorePkg/blob/1.0.7/Utilities/macrecovery/macrecovery.py).
