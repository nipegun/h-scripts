# Technical reference

## Contents

[Architecture](#architecture) · [Modules](#modules) · [Key symbols](#key-symbols) · [Flows](#flows) · [CLI routes](#cli-routes) · [Impact](#impact) · [Extensions](#extensions)

## Architecture

The standalone `mcOSisoCreator.py` launcher works from stdin: it downloads a SHA-256-named ZIP and checks the embedded digest before extracting or executing code. Unsafe paths, links, excessive sizes and modified cached code are rejected. Each runtime is extracted to a separate `_/temp/bootstrap` directory. `cRoot` identifies resources; `cWorkspace` identifies the persistent workspace selected through `MCOS_ISO_CREATOR_WORKSPACE` in the child process. Without that variable, the local entry point retains its project-directory behavior. An isolated Python process (`-I -B`) and `/dev/tty` support execution through curl. The builder exit status is returned to the shell. Package trust depends on this repository; Apple signatures subsequently cover the recovery payload.

`Scripts/create_macos_iso.py` is the executable entry point. `Scripts/macos_iso/` is an implicit namespace package; there are no `__init__.py` files. Python 3.13 is required by the project. The implementation uses the Python standard library plus the external Debian tools xorriso and 7-Zip. Source, comments and metadata keys are English; interface text lives in four JSON locale files, with en-US as default.

The scope is native Debian construction of **recovery** optical images. Complete offline Apple installers require a different macOS-based workflow. The catalog includes recovery selectors for 10.7–26 and explicit unavailable entries for earlier systems. Board identifiers and generic serial templates are pinned to the OpenCorePkg 1.0.7 recovery reference. The Apple service chooses what it serves; the authenticated image's actual SystemVersion.plist determines output naming. A requested exact point version is enforced separately from the family.

Discovery uses HTTPS. Asset URLs are restricted to known Apple hosts; legacy HTTP is permitted only for oscdn.apple.com, as used by Apple's recovery service. HTTPS redirects cannot downgrade, TLS validation is never disabled, and access cookies are stripped on cross-host redirects. `--https-only` provides a stricter transport policy. Authentication comes from the pinned Apple EFI ROM RSA key and signed chunklist, not from the service's opaque AH/CH session references or a checksum supplied alongside an untrusted ISO.

The CNKL parser uses explicit checks instead of `assert`: fixed header layout, offsets, supported methods, count/size bounds, exact file length and RSA PKCS#1 v1.5 SHA-256 verification. Unsigned method-2 chunklists are rejected. Image data is checked in bounded buffers against authenticated chunk hashes. A resumed file is truncated only to the end of its last complete valid chunk; bad range responses cannot cause data to be appended blindly. An integrity failure never triggers a fallback to an unchecked source.

The ISO is generated from a fixed four-file staging tree: unmodified BaseSystem.dmg, its signed chunklist, a constrained OpenCore label and BUILDINFO.json. xorriso emits ISO9660 and HFS+ plus APM; no firmware executable is embedded. Verification parses the APM to find the **actual HFS+ boot volume**, rejects an unexpected file set or embedded boot record, and verifies the Apple image from that filesystem. This avoids verifying only an ISO9660 view that might differ from what OpenCore reads. Independent `--verify` also extracts the authenticated DMG to inspect its actual OS version.

The Apple signature covers the recovery payload, not the wrapper ISO or a separate EFI. The project relies on the local Python runtime, native parsing tools and machine integrity. There is no claim of third-party security auditing, trusted-execution attestation or exact reproducibility across timestamps and tool releases. Sidecars record content hashes and source data; they are not a replacement for verification. ISO files are published only after validation using a no-overwrite hard link from a same-filesystem temporary file. Existing matching ISOs are reverified and reused.

## Modules

| Module | Path | Responsibility | Depends on | Used by |
| --- | --- | --- | --- | --- |
| Curl launcher | `mcOSisoCreator.py` | Verified runtime download, cache and terminal forwarding | Python standard library, runtime ZIP | curl, user |
| Packager | `Scripts/package_macos_iso.py` | Reproducible ZIP, pinned launcher and distribution tree | Source, locales, docs | Maintainer |
| Entry point | `Scripts/create_macos_iso.py` | Version guard and CLI launch | cli | User, automation |
| CLI | `Scripts/macos_iso/cli.py` | Menu, operation routing, dependencies, build flow | All modules | Entry point |
| Shared | `Scripts/macos_iso/common.py` | Errors, localization, progress, locking and file helpers | Standard library, locales | All modules |
| Catalog | `Scripts/macos_iso/catalog.py` | Resolve families/names and enforce versions | Catalog JSON, common | CLI |
| Crypto | `Scripts/macos_iso/crypto.py` | RSA/CNKL and image-chunk verification | Standard library, common | Network, media, tests |
| Network | `Scripts/macos_iso/network.py` | HTTPS discovery, URL policy, retries and resume | urllib, crypto, common | CLI |
| Media | `Scripts/macos_iso/media.py` | Version inspection, APM/HFS+ ISO construction and verification | xorriso, 7-Zip, crypto | CLI |

## Key symbols

| Symbol | File:line | Purpose |
| --- | --- | --- |
| `fMain`, `fDownload`, `fInstall`, `fLaunch` | `mcOSisoCreator.py:211`, `:84`, `:165`, `:195` | Verified runtime and execution from curl |
| `fMain`, `fArchive` | `Scripts/package_macos_iso.py:93`, `:47` | Reproducible distribution |
| `fMain`, `fRun`, `fBuild` | `Scripts/macos_iso/cli.py:245`, `:162`, `:127` | Parse CLI, dispatch operations and coordinate the build |
| `fSelect`, `fCheckVersion` | `Scripts/macos_iso/catalog.py:23`, `:38` | Normalize selections and prevent mislabeled releases |
| `fParseChunklist`, `fVerifyReader` | `Scripts/macos_iso/crypto.py:32`, `:89` | Authenticate metadata and stream-check a payload |
| `fDiscover`, `fDownload` | `Scripts/macos_iso/network.py:89`, `:154` | Obtain Apple asset metadata and resume authenticated downloads |
| `fDetectVersion`, `fVerifyIso`, `fBuildIso` | `Scripts/macos_iso/media.py:118`, `:229`, `:297` | Inspect SystemVersion, check HFS+ media, publish the ISO |
| `Context`, `fLock` | `Scripts/macos_iso/common.py:92`, `:78` | Localized progress and per-workspace exclusion |

## Flows

`curl → mcOSisoCreator.fMain → fDownload (SHA-256) → fInstall → fVerifyRuntime → fLaunch (/dev/tty) → cli.fMain`.

Interactive: `fMain → fParser → fRun → fMenu → fBuild`.

Download: `fBuild → fRemoteInputs → fDiscover → fManifest → fParseChunklist → fDownload → fVerifiedPrefix/fVerifyImage`.

Local inputs: `fBuild → fLocalInputs → fParseChunklist → fVerifyImage`. This path makes no discovery request.

Packaging: `fDetectVersion → fCheckVersion → fBuildIso → xorriso → fVerifyIso → fApmHfs → fIsoMembers → fVerifyReader → atomic publication + sidecars`.

Independent verification: `fRun --verify → fVerifyIso → HFS+ extraction → signed manifest + image verification → fDetectVersion → metadata/label comparison → report`.

## CLI routes

| Command | Handler | File |
| --- | --- | --- |
| No arguments / `--os VERSION` | `fRun → fBuild` | `cli.py` |
| `curl … \| python3 - [--directory DIR]` | `fMain → fLaunch` | `mcOSisoCreator.py` |
| `--list [--json]` | Catalog listing | `cli.py`, `catalog.py` |
| `--doctor [--json]` | Local dependency and space report | `cli.py` |
| `--probe --os VERSION` | Discovery and signed-manifest check | `cli.py`, `network.py` |
| `--verify ISO [--json]` | Independent HFS+ payload verification | `cli.py`, `media.py` |
| `--from-image DMG --chunklist FILE --os VERSION` | Verified local input path | `cli.py` |
| `--dry-run --os VERSION` | Network-free plan | `cli.py` |

Timeouts are 5–300 seconds per network operation, with 1–8 configured attempts. Native tool operations have a bounded execution timer. Exit status is 0 for success, 1 for a build/validation failure, 2 for argument parsing and 130 for cancellation. Output and working directories are constrained to the project and its `_/temp` subtree respectively. A completed `.iso`, `.json` and `.iso.sha256` form the user-facing result. Signature/download caches are retained for reuse; transient extraction and partial output ISO files are cleaned in finally blocks.

## Impact

Crypto, URL policy and media parsing are security-critical. Changes require tamper tests and real Apple input verification. Changes to HFS+ layout require verification of the boot volume and an OpenCore detection check; checking an ISO file listing alone is insufficient. Changes to family matching must cover mismatched major and minor versions. Every interface key and placeholder must exist consistently across four locales.

Tests are in `Tests/test_macos_iso.py`. Their `mTest*` method prefix follows the project's naming convention; the standard unittest `load_tests` hook selects that prefix. The small Apple-signed fixture is a chunklist, not a macOS installer. Tests cover signature/hash modifications, malformed/unsigned manifests, Python optimization, URL/redirect policy, partial downloads, ignored/lying ranges, exact-version handling, symlink outputs and locale parity. Live end-to-end media were generated for 10.7.5, 10.14.6 and 26.6.2. Full OS installation is outside the local validation performed.

## Extensions

To add a new recovery family, add documented Apple board/serial selectors to `Sources/macos-recovery-versions.json`, run `--probe`, download and inspect a real signed image, and test actual-version enforcement. Do not infer a revision from a filename or label another recovery as the requested OS. Supporting a new chunklist signature format requires an independently trusted key and verification implementation; never introduce a skip-verification fallback.

To add a locale, provide all JSON keys and matching format placeholders, update `cLanguages`, and run locale tests. To support another media layout, preserve Apple payload bytes and verify the filesystem OpenCore will actually read. Updating the pinned trust anchor or relaxing URL policy requires review of the source and the trust boundary. Keep README, CODE and MANUAL in their three documentation languages synchronized.

To publish changes, run `python3 Scripts/package_macos_iso.py`. It updates symbol line references, generates `Releases/mcOSisoCreator/` and pins its ZIP in the launcher. Publish that directory’s complete contents to `Debian/mcOSisoCreator` and retain runtime ZIPs from previous releases. Never publish `ISOs/`, caches, EFI or private VM configurations. Additional tests in `Tests/test_macos_iso_bootstrap.py` cover real execution through stdin and persistence of outputs.
