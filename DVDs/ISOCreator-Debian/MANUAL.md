# User manual

## Run directly with curl

```sh
curl -fsSL https://raw.githubusercontent.com/nipegun/h-scripts/main/Debian/ISOCreator/ISOCreator.py | python3 - --language en-US --install-deps
```

Requires Debian 13 and Python 3.13 or newer. If curl is missing: `sudo apt install curl ca-certificates python3`. The launcher downloads the code bundle from this repository, verifies its embedded SHA-256 and opens the menu on `/dev/tty`. ISOs go to `./ISOCreator/ISOs/`; reusable downloads stay in `./ISOCreator/_/temp/macos-iso/`. No repository clone or pip packages are needed. `--install-deps` allows xorriso and 7zip installation through apt/sudo.

Add `--directory /path/ISOCreator` to choose another workspace or `--os Tahoe --non-interactive` for automation. Options follow `python3 -`. Use `--launcher-help` for launcher options and `--help` for builder options.

The program is stored by content in `ISOCreator/_/temp/bootstrap/runtime-<SHA256>/`. Repeated runs verify and reuse it; a new release uses another directory while preserving ISO outputs and Apple downloads. Do not edit that verified copy; use repository sources for development. If cached code is damaged, the launcher stops and identifies the file. A new `--directory` downloads a clean copy.

The bundle SHA-256 checks the code declared by this launcher; it is not an independent Apple signature. Running the command trusts this repository and the launcher delivered by GitHub over HTTPS. Apple signatures are checked later on the recovery payload. No GitHub token is needed. Without a terminal, specify `--os` and `--non-interactive`.

## Interactive use

Run `python3 Scripts/create_macos_iso.py --install-deps` from the extracted project directory. Choose a numbered entry, a codename such as `Tahoe`, or an exact version such as `10.7.5`. Default interface language is en-US; use `--language en-GB`, `--language es-ES` or `--language es-AR` if desired. Enter `0` to cancel the menu.

After selection the program performs six stages: Apple discovery, signed-manifest verification, download and image verification, version inspection, ISO creation, and verification of the finished HFS+ payload. If dependencies are missing it offers apt installation on an interactive terminal. `--install-deps` authorizes that step beforehand; sudo may request your local password. No GitHub account is used.

This is a **recovery ISO creator**. A recovery environment installs macOS using an Internet connection. It does not build a complete offline installer. A compatible OpenCore EFI remains necessary for Proxmox; the script never claims to generate a universal EFI.

## Version selection and availability

Use `--list` to list the catalog. Apple download selectors cover OS X Lion 10.7 through macOS Tahoe 26. Older systems appear with an explicit unavailable status because they predate Internet Recovery. Supplying an already signed recovery DMG and chunklist is also supported, but the program has no unsigned-image bypass.

Selecting a family such as `26` means accepting the available recovery revision within that family. Selecting `26.6.2` requires that exact version inside the authenticated image. Apple may offer a different point release or retire a selector. The script rejects a mismatched family or exact revision and never renames an unrelated image to the requested version. `latest` asks for the newest recovery Apple offers for the documented Intel Mac model; always read the detected version. The version of the recovery environment is not a promise about the point release Apple's installer will subsequently offer.

## Common commands

```sh
# Interactive Spanish interface
python3 Scripts/create_macos_iso.py --language es-ES --install-deps

# Exact recovery version, without questions
python3 Scripts/create_macos_iso.py --os 26.6.2 --non-interactive

# Network-free plan
python3 Scripts/create_macos_iso.py --os 10.14 --dry-run

# Metadata and Apple signature only, without downloading the DMG
python3 Scripts/create_macos_iso.py --os 10.7 --probe --json

# Local dependency check
python3 Scripts/create_macos_iso.py --doctor
```

In noninteractive mode missing dependencies cause a clear error unless `--install-deps` is supplied. If sudo would need a password, the noninteractive installation fails rather than waiting for hidden input.

## Output and cache

Each completed build produces these files in `ISOs/`:

| File | Purpose |
| --- | --- |
| `macOS_NAME_VERSION_BUILD_Recovery.iso` | Optical ISO containing a recovery environment and signed Apple files |
| Same basename ending in `.json` | Actual version/build, source URLs without access tokens, signature scope and checksums |
| Same filename plus `.sha256` | ISO transfer-integrity checksum |

The ISO has ISO9660 and HFS+ filesystems with an Apple Partition Map. Its HFS+ volume contains only `com.apple.recovery.boot/BaseSystem.dmg`, its signed `.chunklist`, a picker label and `BUILDINFO.json`. The DMG is not modified. No OpenCore executable is embedded.

Verified downloads remain under `_/temp/macos-iso/cache/`, keyed by the signed chunklist's SHA-256. Interrupted downloads have a `.part` suffix. Rerun the same command to resume: existing complete chunks are authenticated, an incomplete or corrupt tail is discarded, and the server's byte-range response is checked. Completed cache files are verified again before use. Temporary ISO staging and extraction files are removed automatically. To reclaim download space after all jobs finish, remove only the builder's cache directory; keep the resulting ISO and JSON. Temporary data for other project tools is separate.

`--work-dir` must remain inside the project's `_/temp`; `--output-dir` must remain inside the project. Move the entire extracted tool directory to another disk if more space is needed. Paths outside these limits, symlink output files and attempts to overwrite an existing ISO are rejected. An existing matching ISO is cryptographically verified and reused; missing sidecars are regenerated. A lock prevents concurrent builds in the same work directory.

Allow approximately four times the compressed recovery image size as free space for the cache, ISO and verification copies. Space is checked before large writes. A full verification of an existing ISO also needs temporary extraction space. `Ctrl+C` preserves resumable downloads and removes an unfinished output ISO.

## Verify an ISO independently

```sh
python3 Scripts/create_macos_iso.py --verify ISOs/macOS_Tahoe_26.6.2_25G83_Recovery.iso
```

This reads the **HFS+ boot volume** identified by the APM, checks its expected file set, verifies Apple's RSA signature and all DMG chunks again, extracts the actual SystemVersion.plist, and compares the metadata and picker label. It does not simply accept a `verified=true` flag from a JSON report. `--json` gives machine-readable results.

The `.iso.sha256` file checks whether your copy matches the built ISO; it is not an Apple signature. Apple's signature authenticates BaseSystem's contents against the pinned Apple EFI ROM key distributed with OpenCorePkg 1.0.7. It does not authenticate the locally generated ISO wrapper or your separate EFI. You must trust the builder source, Python, 7-Zip, xorriso and your local machine. The project does not claim an independently audited implementation or protection from a malicious administrator on that machine.

## Using previously downloaded Apple files

```sh
python3 Scripts/create_macos_iso.py --os 26.6.2 --from-image /path/BaseSystem.dmg --chunklist /path/BaseSystem.chunklist
```

Both files are required. The signature and image checks are mandatory even in this mode. This allows building and checking the ISO without another download request, but the eventual macOS installation still needs Internet. This mode accepts recovery images, not InstallAssistant.pkg or an arbitrary full installation DVD.

## Network policy

Discovery goes to `https://osrecovery.apple.com`. Recovery asset requests are limited to the known Apple endpoints. HTTPS certificates are validated normally; redirects cannot downgrade HTTPS. Apple currently supplies some signed assets on `http://oscdn.apple.com`, whose HTTPS endpoint did not have a matching certificate in the tested environment. The script follows Apple's supplied HTTP asset URL with mandatory independent signature checks; it never uses an insecure TLS context or `curl -k`.

Use `--https-only` to reject HTTP entirely. That policy can make Apple's current recovery downloads unavailable. `AH` and `CH` returned by the service are session references and are not compared with file hashes. The authenticated hashes come from the RSA-signed chunklist. Access cookies/tokens are not saved in the public report. Use `--timeout 60 --retries 6` for slow or unreliable connections. If Apple's temporary download token expires, rerunning obtains new metadata and reuses authenticated chunks.

## Use in Proxmox

1. Upload the generated ISO to a Proxmox storage that supports ISO images.
2. Attach it as a CD/DVD drive, for example SATA0, keeping `media=cdrom`.
3. Put the disk containing your compatible OpenCore EFI first in the boot order, and keep the CD/DVD enabled in that order.
4. Start OpenCore and select `macOS VERSION Recovery`.
5. Connect the guest network and use Disk Utility/Install macOS on the intended system disk.

The EFI needs HFS+ and Apple partition-map support, normally `OpenHfsPlus.efi` and `OpenPartitionDxe.efi`, with installer/recovery scanning enabled. The ISO creator never edits the Proxmox host or guest disks. `efidisk0` stores OVMF variables and is separate from an EFI System Partition containing boot files. Actual guest installation and suitable CPU, disk and network models remain VM configuration tasks.

## Troubleshooting

| Result | Action |
| --- | --- |
| Missing xorriso or 7zip | Run again with `--install-deps` or install the packages manually |
| Wrong offered version | Choose the available family or use verified files for the exact requested release |
| Signature or chunk hash failure | Stop; do not bypass verification or use the failed image |
| Cannot read SystemVersion.plist | Install current Debian 7zip with DMG/HFS+/APFS support |
| Existing ISO differs | Preserve it and choose another output directory; it is not overwritten |
| Only OpenShell appears | Check the attached ISO, boot-order checkboxes and the EFI's filesystem drivers |

`--probe` establishes availability of a signed recovery product, not its OS version; that requires downloading and inspecting the DMG. Apple may stop serving older recoveries or the network installation services they need.

## Validation scope

Real downloads, signature verification, version extraction and ISO generation succeeded for Lion 10.7.5 (11G63), Mojave 10.14.6 (18G87) and Tahoe 26.6.2 (25G83). Tahoe was independently reverified from its final ISO and detected by OpenCore in QEMU/OVMF. No full guest installation was completed locally. The builder and launcher tests run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Tests -p 'test_macos_iso*.py' -v
```
