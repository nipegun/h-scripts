# macOS Recovery ISO Builder for Debian

## Run directly with curl

```sh
curl -fsSL https://raw.githubusercontent.com/nipegun/h-scripts/main/Debian/mcOSisoCreator/mcOSisoCreator.py | python3 - --language en-US --install-deps
```

Requires Debian 13 and Python 3.13 or newer. If curl is missing: `sudo apt install curl ca-certificates python3`. The launcher downloads the code bundle from this repository, verifies its embedded SHA-256 and opens the menu on `/dev/tty`. ISOs go to `./mcOSisoCreator/ISOs/`; reusable downloads stay in `./mcOSisoCreator/_/temp/macos-iso/`. No repository clone or pip packages are needed. `--install-deps` allows xorriso and 7zip installation through apt/sudo.

Add `--directory /path/mcOSisoCreator` to choose another workspace or `--os Tahoe --non-interactive` for automation. Options follow `python3 -`. Use `--launcher-help` for launcher options and `--help` for builder options.

Run the interactive builder from the project directory:

```sh
python3 Scripts/create_macos_iso.py --install-deps
```

Select a macOS family or enter a version. The program requests recovery files directly from Apple, checks Apple's RSA signature and every authenticated image chunk, reads the actual version, builds an optical ISO, and verifies the HFS+ content inside the finished ISO.

**These are recovery ISOs.** Installation needs Internet and a separate OpenCore EFI suitable for the VM. This Debian workflow does not create Apple's full offline installer and does not generate a universal EFI.

## Requirements

Debian 13, Python 3.13+, `xorriso` and current `7zip`. No pip packages or macOS installation are needed. `--install-deps` allows apt to install missing packages, using sudo when needed. Ordinary builds do not need root and never format a disk or partition.

```sh
sudo apt install python3 xorriso 7zip
```

## What is automated

1. Interactive selection or CLI selection by family, codename or exact point release.
2. Apple-only discovery, signed chunklist verification and resumed downloads from verified chunk boundaries.
3. Actual version detection, rejecting another family or a different explicitly requested point release.
4. ISO9660/APM/HFS+ creation and verification of the HFS+ boot volume, including Apple's signatures again.
5. Output SHA-256 and JSON provenance, cache reuse, independent ISO verification, diagnostics and four interface languages.

## Version coverage

The catalog has Apple recovery selectors for Lion 10.7, Mountain Lion, Mavericks, Yosemite, El Capitan, Sierra, High Sierra, Mojave, Catalina, Big Sur, Monterey, Ventura, Sonoma, Sequoia and Tahoe 26. Apple's server controls availability; historical selectors may stop working.

**10.0–10.6 are explicitly unavailable for automatic Internet Recovery download.** The program explains that original media is needed instead of substituting an unverified download. Exact historical patch releases are not all offered by Apple. `--os 26.6.2` requires the recovery itself to contain 26.6.2; `--os 26` accepts the available Tahoe recovery revision and names the output using its detected version.

## Examples

```sh
python3 Scripts/create_macos_iso.py --language es-ES
python3 Scripts/create_macos_iso.py --list
python3 Scripts/create_macos_iso.py --os 26.6.2 --non-interactive
python3 Scripts/create_macos_iso.py --os Mojave --probe --json
python3 Scripts/create_macos_iso.py --verify ISOs/macOS_Tahoe_26.6.2_25G83_Recovery.iso
```

Results go to `ISOs/`; temporary files and reusable downloads stay in `_/temp/macos-iso/`. Keep the whole tool directory together, including `Scripts/macos_iso`, `Sources/macos-recovery-versions.json` and `Locales/macos_iso`.

## Verification status

Real Apple recovery images for **10.7.5 (11G63), 10.14.6 (18G87) and 26.6.2 (25G83)** were downloaded, authenticated and packaged successfully on Debian. The finished Tahoe ISO was independently verified, and OpenCore detected its recovery entry in QEMU/OVMF. A complete guest installation was not tested locally. **38 automated tests pass**, covering tampering, resume boundaries, URL policy and version mismatches.

Apple supplies some recovery assets over HTTP. Discovery uses HTTPS; the signed chunklist and authenticated chunks provide content authentication. `--https-only` rejects HTTP assets; the program never disables TLS certificate validation. Server fields `AH` and `CH` are not used as file checksums.

[Manual](MANUAL.md) · [Technical reference](CODE.md) · [Español de España](README.es-ES.md) · [Español de Argentina](README.es-AR.md)
