# Open-source licence compliance in OBSBOT's Meet 2 firmware and software

Evidence report, 2026-11-23. This report records what OBSBOT's distributed files contain, and how anyone can check it. It is not legal advice, and it draws no legal conclusions.

## Summary

- The OBSBOT Meet 2 camera runs Linux. Its firmware v4.4.7.1 contains U-Boot, a Linux 5.10.61 kernel, BusyBox 1.35.0, glibc 2.33, the uMTP Responder and other GPL- and LGPL-licensed components, assembled with Buildroot 2022.02 and branded "Obsbot Linux".
- Some of these components carry their own short copyright lines inside their binaries (listed in Finding 2). But nowhere in the firmware is there a full text of the GPL or LGPL, a written offer for source code, or a pointer to where the source can be obtained. The search covered all three filesystems in the image, the kernel and the boot configuration, binaries included.
- Three kernel modules written by OBSBOT's parent company, Remo Tech (`remo_multi_usb.ko`, `remonetlink.ko`, `remo_drivers_gyro.ko`), declare `license=GPL`. Their source is not offered either.
- OBSBOT Center 2.0.16 for Windows and for macOS (whose download also holds a complete 2.0.10 copy) bundles an FFmpeg 6.0 build whose own licence string reads "GPL version 3 or later", built with x264. Both platforms also ship a library exposing the API of libobs, OBS Studio's core library (GPL-2.0-or-later), and the Windows build ships OBS Studio's game-capture plugin with its entry points renamed. The application's only licence file, the same on both platforms, says the application is licensed under the LGPL-3.0 and names only Qt.
- The Meet 2 user manual says nothing about open-source software, licences or source code.
- OBSBOT's Terms of Use, captured 2026-11-23, license its software as a "platform" that is "licensed and not sold", prohibit reverse engineering it without exception, name no open-source component and offer no source code. The LGPL (versions 2.1 and 3.0) allows its libraries to be combined into a work under the distributor's own terms only if those terms permit reverse engineering for debugging modifications (Finding 6).
- OBSBOT's SDK library, `libdev`, which OBSBOT also ships publicly inside OBSBOT Center, contains in its macOS and Linux builds code whose symbol names, source file names and directory layout match two LGPL-2.1 projects, ftplibpp and android-file-transfer-linux. It ships without a licence text or notice.

## Files examined

| File | How it was obtained | SHA256 (full values in `SHA256SUMS`) |
|---|---|---|
| `Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin`: Meet 2 firmware v4.4.7.1, 64,656,096 bytes | https://www.obsbot.com/download/obsbot-meet-2, "OBSBOT Meet 2 Firmware", listed as updated 2026-10-09; downloaded with a browser on 2026-11-23 | `240591d4…3fedd` |
| `Obsbot_Center_OA_E_MacOS_Intel_2.0.16.433_release.dmg`: OBSBOT Center 2.0.16.433 for macOS (Intel) | Same page, listed as updated 2026-11-10; downloaded 2026-11-23 | `5e1ce498…ae201` |
| `Obsbot_Center_OA_E_Win_x64_2.0.16.433_release.exe`: OBSBOT Center 2.0.16.433 for Windows (Inno Setup installer), 316,611,312 bytes | Same page, listed as updated 2026-11-10; downloaded 2026-11-23 | `65ad2476…f7d3d` |
| `OBSBOTMeet2UserManual_ENv1.1.pdf`: OBSBOT Meet 2 User Manual (EN) v1.1, 5 pages, created 2024-10-23 | Same page, "OBSBOT Meet 2 User Manual"; downloaded 2026-11-23 | `c48512c9…5d1` |
| OBSBOT Terms of Use, https://www.obsbot.com/service/docs/terms-of-use | Captured 2026-11-23 with curl: HTML, response headers and extracted text in `captures/` (server `Date: Mon, 23 Nov 2026 16:31:04 GMT`) | `5ee4ec01…a67eda` |
| `libdev_v2_1_0_7.zip`: OBSBOT SDK package (headers, libraries for Linux x86_64/arm64, macOS, Windows, sample program), 67,095,241 bytes | Linked from an email sent by OBSBOT (`store@obsbot.com`, "OBSBOT Center SDK Download", 2025-10-16) in reply to an SDK application at obsbot.com/sdk: https://resource-cdn.obsbothk.com/download/share/libdev_v2_1_0_7.zip?direct_download=1. On 2026-11-23 that link still served the file without a signature (`Last-Modified: Wed, 30 Jul 2025 08:53:14 GMT`; headers in `captures/`) | `53ef1825…8fde5a` |
| `remo_uvc_ctrl.en.h`: C header, 35,549 bytes, 1,459 lines | Linked from OBSBOT's second email of the same date (`store@obsbot.com`, "OBSBOT Linux SDK Download"), which calls it "the API file": a Google Drive file, ID `1PEv3qQGFoSjq5Ea88MN1sb8ogClOSDRo`. Downloaded without signing in on 2026-11-23 (`Last-Modified: Mon, 19 Aug 2024 06:06:20 GMT`; response headers in `captures/`) | `84787c58…dbb85e` |
| `libdev.so.1.0.2`: OBSBOT SDK library, Linux x86_64 | Inside `libdev_v2_1_0_7.zip` at `libdev_v2.1.0_7/linux(beta)/x86_64-release/`. The copy vendored in github.com/aaronsb/obsbot-camera-control (`sdk/v1.0.2/lib/`), and that repository's `dev.hpp`, are byte-identical to the zip's | `d9fc9cd7…4e7a4` |
| `libdev.so.1.0.0`: OBSBOT SDK v2.1.0_8, Linux x86_64 | Obtained from OBSBOT through the same application form by a contributor to github.com/aaronsb/obsbot-camera-control (pull request #71, which records the zip's name and this SHA256); vendored in `sdk/v2.1.0_8/lib/` of that repository | `3eef907f…08c55` |

The download page signs its links with a timestamp, so the files are fetched through the page's Download buttons. Hashes of the files cited inside the firmware and the application are printed by `reproduce.sh` and recorded in `expected-output.txt`.

## Method

No encryption was broken and no technical protection measure was circumvented to obtain any finding in this report.

- **Downloads:** each OBSBOT file was downloaded through the Download button on OBSBOT's own download page, in an ordinary web browser. The CDN rejects direct requests without the page's signed link; that check was not bypassed.
- **Firmware:** the image is not encrypted. It consists of standard formats (U-Boot legacy images, UBI images holding UBIFS filesystems), split along its own partition table and unpacked with the open-source `ubi_reader`.
- **macOS application:** the disk image is not encrypted and was opened with 7-Zip.
- **Windows application:** the Inno Setup installer is not encrypted and was unpacked with `innoextract`.
- **Libraries and programs:** read with `strings`, `llvm-objdump` and `sha256sum`. Nothing from OBSBOT's files was executed.
- **Web pages:** fetched with `curl`; one page was also rendered in a browser to read its visible text.

## Finding 1: the firmware is an embedded Linux system

The firmware image has a 0x200-byte header, then a partition table at offsets 0x300–0xB00 that names eight partitions. `carve_fw.py` splits the image along that table. The partitions run contiguously from offset 0xB00 to the end of the file.

| Partition | Size (bytes) | Content |
|---|---|---|
| `UBOOT0.bin`, `UBOOT1.bin` | 208,464 each | U-Boot legacy image header: OS "U-Boot firmware", ARM, name `MVX4##I6C#gb2a3761CM_UBT1501#XVM`, built 2026-10-07 21:28:04 UTC |
| `KERNEL.bin`, `RECOVERY.bin` | 3,804,960 each | U-Boot legacy image header: OS "Linux", ARM, name `MVX4##I6C#gb2a3761KL_LX510##[BR:`, built 2026-10-07 21:32:34 UTC |
| `ROOTFS.ubi` | 35,258,368 | UBI image, UBIFS root filesystem (576 files) |
| `UPDATERFS.ubi` | 13,500,416 | UBI image, UBIFS updater filesystem (218 files) |
| `AIFS.ubi` | 7,864,320 | UBI image, volume `ai` (31 files): OBSBOT's on-camera AI library |
| `config` | 3,328 | Shell script with the kernel command line |

The U-Boot identification rests on those image headers; the bootloader payload is compressed and was not unpacked.

Identity strings:

| Where | String |
|---|---|
| `KERNEL.bin` | `Linux version 5.10.61 (jenkins@ubuntu-server) (arm-linux-gnueabihf-sigmastar-11.1.0-gcc (GCC) 11.1.0, GNU ld (Linaro_Binutils-20210608-sigmastar-glibc-arm-linux-gnueabihf) 2.35.2.20210110) #8 PREEMPT Thu Oct 8 05:32:30 CST 2026` |
| `/etc/issue` | `Welcome to Obsbot Linux` |
| `/etc/os-release` | `NAME=Buildroot`, `VERSION=-gb2a3761-dirty`, `VERSION_ID=2022.02` |
| `/bin/busybox` | `BusyBox v1.35.0 (2026-10-08 05:01:45 CST)` |
| `/lib/libc-2.33.so` | `GNU C Library (GNU libc) release release version 2.33.` |
| `/usr/sbin/umtprd` | `uMTP Responder` |

The image headers give UTC; the kernel banner and BusyBox give China Standard Time (UTC+8). Both describe the same build, on 2026-10-07/08.

## Finding 2: GPL and LGPL components ship without licence texts or a source offer

Components in the firmware and their upstream licences:

| Component | Where | Upstream licence | Checked against |
|---|---|---|---|
| Linux kernel 5.10.61 | `KERNEL.bin`, `RECOVERY.bin` | GPL-2.0 with Linux-syscall-note | `COPYING`, github.com/torvalds/linux |
| U-Boot | `UBOOT0.bin`, `UBOOT1.bin` (image headers) | GPL-2.0 (most files GPL-2.0-or-later) | `Licenses/README`, github.com/u-boot/u-boot |
| BusyBox 1.35.0 | `/bin/busybox` | GPL-2.0 only | `LICENSE` in the BusyBox source |
| uMTP Responder | `/usr/sbin/umtprd` | GPL-3.0 | GitHub licence detection, github.com/viveris/uMTP-Responder |
| glibc 2.33 | `/lib/libc-2.33.so` | LGPL-2.1 | GitHub licence detection on github.com/bminor/glibc, a mirror of sourceware glibc |
| Avahi | `/usr/sbin`, `/usr/lib`, `/etc/avahi` | LGPL-2.1 | GitHub licence detection, github.com/avahi/avahi |
| alsa-lib | `libasound` | LGPL-2.1 | GitHub licence detection, github.com/alsa-project/alsa-lib |
| libnl | `libnl-3` | LGPL-2.1 | GitHub licence detection, github.com/thom311/libnl |

The firmware also contains `/app/lib/libzmq.so.5.1.3`. libzmq was licensed LGPL-3.0 with a static-linking exception until its move to MPL-2.0; this report did not determine which version ships, so it is not counted above.

### Notices that are present

| Where | Text |
|---|---|
| `/bin/busybox` | "BusyBox is copyrighted by many authors between 1998-2015." / "Licensed under GPLv2. See source distribution for detailed" |
| `/lib/libc-2.33.so` | "Copyright (C) 2021 Free Software Foundation, Inc." |
| `/usr/sbin/umtprd` | "(c) 2018 - 2021 Viveris Technologies" |
| `/etc/inittab` | "# Copyright (C) 2001 Erik Andersen" |
| `/etc/avahi/*`, `/usr/share/dbus-1/interfaces/org.freedesktop.Avahi.*.xml` | LGPL header comments (12 files) |
| `/lib/AEC_LICENSE_1.txt`, `/lib/APC_LICENSE_1.txt` | Permissive notice for Takuya Ooura's FFT code |
| `/lib/AEC_LICENSE_2.txt`, `/lib/APC_LICENSE_2.txt` | WebRTC's BSD licence, "Copyright (c) 2011, The WebRTC project authors" |

`/app/audioalgo/huoshan/speech_license.licbag` is a licence key for a speech library, not a licence text.

### What is absent

`reproduce.sh` (section 9) searches every file of the root, updater and AI filesystems, binaries included, plus `KERNEL.bin`, `UBOOT0.bin` and `config`:

- **Full licence texts:** none. The search looks for a phrase that appears only in each full text: the GPL-2.0/LGPL-2.1 preamble ("The licenses for most software are designed to take away your"), the GPL-3.0 preamble ("The GNU General Public License is a free, copyleft license") and the opening of the LGPL-3.0 ("This version of the GNU Lesser General Public License incorporates").
- **Source offers:** none. The search looks for "written offer", "source code is/are available", "corresponding source" and "complete source code".

Controls run in the same script: the full-text pattern matches the LGPL-3.0 text in OBSBOT Center's `LICENSE` file, and the same search tool finds the LGPL header phrase in Avahi's files. The UBI extraction reports no errors and its file counts are printed. The U-Boot payload is compressed, so for the bootloader only its header was searched.

## Finding 3: OBSBOT's own kernel modules declare the GPL

The root and updater filesystems both contain these modules in `/lib/modules/5.10.61/extra/`:

| Module | `author=` | `license=` |
|---|---|---|
| `remo_multi_usb.ko` | ChengQun.Zhong | GPL |
| `remonetlink.ko` | vianowu | GPL |
| `remo_drivers_gyro.ko` | Lv laiwei | GPL |
| `remo_sensor_imx582.ko` | SigmaStar | Proprietary |

The `license=GPL` value is the module's own declaration to the kernel. The source of these modules is not offered (Finding 2).

## Finding 4: OBSBOT Center bundles GPL FFmpeg, x264 and OBS Studio code under an LGPL-3.0 statement

### macOS

The DMG holds OBSBOT Center 2.0.16 (bundle id `com.obsbot.OBSBOT_Center`). Inside it, `Contents/Modules/OBSBOT_Center.app` is a complete second copy, version 2.0.10, with the same bundle id.

The outer bundle's only licence-like file is `Contents/license/LICENSE`. It begins:

> This project is licensed under the GNU Lesser General Public License v3.0 (LGPL-3.0).
> [...]
> This project incorporates Qt libraries, which are also licensed under the LGPLv3.

It goes on with the LGPL-3.0 text and names no component other than Qt. The nested 2.0.10 bundle has no licence file.

Both bundles contain:

| Library | Evidence from the library itself |
|---|---|
| `libavcodec.dylib` and the other FFmpeg libraries | `libavcodec license: GPL version 3 or later`; configure flags include `--enable-gpl`, `--enable-version3`, `--enable-libx264`; `FFmpeg version n6.0-12-ga6dc92968a` |
| `libx264.dylib` | `x264 - core … H.264/MPEG-4 AVC codec … http://www.videolan.org/x264.html`. Upstream x264 is GPL-2.0 (github.com/mirror/x264). x264 is also sold under commercial licences; whether OBSBOT holds one is not known. FFmpeg's own licence string above does not depend on that. |

The nested 2.0.10 bundle also contains `Frameworks/librm.framework`. Its symbol table holds 36 libobs API names (`gs_create`, `gs_effect_create_from_file`, `calldata_*`, `dstr_*`), and the bundle ships libobs's shader files, for example `bicubic_scale.effect` with the upstream comment "this shader is adapted from the GPL bsnes shader". libobs is GPL-2.0-or-later (header of `libobs/graphics/graphics.c`, github.com/obsproject/obs-studio). As in Finding 5, the match is by names and file contents, not by comparing compiled code.

A search of both bundles, binaries included, for source-offer wording finds only false positives, which `reproduce.sh` prints with the matched text: FFmpeg's MXF error messages ("no corresponding source track found") and the LGPL-3.0 text's own term "Corresponding Source".

### Windows

The installer is an Inno Setup package of 2,041 files. Its only licence-like file is `app/license/LICENSE`, the same text as the macOS `LICENSE` apart from line endings. It contains:

| File | Evidence from the file itself |
|---|---|
| `app/bin/avcodec-60.dll` and the other FFmpeg DLLs | `libavcodec license: GPL version 3 or later`; configure flags include `--enable-gpl`, `--enable-version3`, `--enable-libx264`; version `n6.0-12-ga6dc92968a`, the same FFmpeg build as on macOS |
| `app/bin/libx264-164.dll` | the x264 banner, as on macOS |
| `app/bin/rm.dll` and `app/data/librm/` | 35 libobs API names; libobs's `bicubic_scale.effect` with the upstream bsnes comment |
| `app/rmfunc/win-capture.dll` | Exports `rm_module_load`, `rm_module_unload`, `rm_module_ver`, `rm_module_set_pointer`, `rm_module_set_locale`, `rm_module_free_locale`, `rm_module_get_string` and `rm_module_description`: the set of `obs_module_*` entry points an OBS Studio plugin exports (`libobs/obs-module.h`), with `obs` replaced by `rm`. 52 of its log messages carry the prefix `[game-capture: '%s']`, which OBS Studio's `plugins/win-capture/game-capture.c` defines for its log output, and it loads `graphics-hook64.dll`, the name of OBS Studio's capture hook. OBS Studio is GPL-2.0 (GitHub licence detection, github.com/obsproject/obs-studio). |

The directory `app/rmfunc/` also holds `win-wasapi.dll`, `image-source.dll` and `rtmp-services.dll`, which carry the names of OBS Studio plugins; this report examined only `win-capture.dll`. A search of the whole install tree for source-offer wording finds only the same false positives as on macOS.

## Finding 5: OBSBOT's SDK library contains code matching two LGPL-2.1 projects

OBSBOT's camera-control library, `libdev`, is the core of its SDK. OBSBOT publishes it inside OBSBOT Center: the public macOS download contains `Contents/Frameworks/libdev.dylib` (SHA256 `a48d3fe9f34839def46dd39e7f236aa2189cdd02bf63abd35328f6f75139d92f`), which exports 288 `Device::camera…` functions, the SDK's camera API. This finding rests on that public file. The Linux builds of the same library, which OBSBOT supplies only on request, corroborate it.

| | `libdev.dylib` (public: macOS, OBSBOT Center 2.0.16) | `libdev.so.1.0.2` (Linux, in OBSBOT's SDK zip) | `libdev.so.1.0.0` (Linux, SDK v2.1.0_8) |
|---|---|---|---|
| Mangled `Device::camera…` API symbols | 288 | 617 | 871 |
| Mangled `mtp::` symbols (of which `mtp::Session`) | 239 (49) | not counted (229) | not counted (229) |
| Mangled `ftplib` symbols | 25 | 116 | 116 |
| Strings containing licence wording | 0 | 0 | 0 |
| Build path of the FTP code | — | `/home/qy/workspace/obsbot_device_new/obsbot_device/libdev/ftp/ftplib.cpp` | `/home/qy/workspace/make-target/2026-5-29/obsbot_device/libdev/ftp/ftplib.cpp` |
| Build path of the MTP code | — | `…/libdev/mtp/linux/mtp/backend/linux/usb/Context.cpp` | same |

Symbol counts include compiler-split variants (`.cold`), so they count symbol entries, not distinct functions.

The matches with upstream:

- **ftplibpp** (LGPL-2.1, github.com/mkulke/ftplibpp) ships `ftplib.cpp` and `ftplib.h`. Its header declares the private methods `FtpSendCmd(const char *cmd, char expresp, ftphandle *nControl)`, `readresp(char c, ftphandle *nControl)` and `CorrectPasvResponse(unsigned char *v)`. The public `libdev.dylib` contains `__ZN6ftplib10FtpSendCmdEPKccP9ftphandle`, `__ZN6ftplib8readrespEcP9ftphandle` and `__ZN6ftplib19CorrectPasvResponseEPh`: the same methods with the same parameter types.
- **android-file-transfer-linux** (LGPL-2.1, github.com/whoozle/android-file-transfer-linux) declares `mtp::Session` methods including `GetStorageInfo` and `GetPartialObject` in `mtp/ptp/Session.h`, and has the file `mtp/backend/linux/usb/Context.cpp`. The public `libdev.dylib` contains `__ZN3mtp7Session14GetStorageInfoENS_9StorageIdE`. Both Linux libraries contain it too, along with `_ZN3mtp7Session16GetPartialObjectENS_8ObjectIdEmj` and the build path above.

The match is by symbol names, parameter types, file names and directory layout; this report did not compare compiled code with the upstream sources. The public macOS download contains the library but no SDK headers. The Linux library `libdev.so.1.0.2` comes from OBSBOT's own SDK package, `libdev_v2_1_0_7.zip`, downloaded from the link in OBSBOT's email (see Files examined). That package contains headers, libraries for four platforms and a sample program, and no licence file, notice or README. OBSBOT's companion email of the same date, "OBSBOT Linux SDK Download", says: "The complete SDK files require a fee, and we will contact you via email as soon as possible." No further email from OBSBOT about the SDK was found in the applicant's mailbox. The "API file" that email links to is `remo_uvc_ctrl.en.h`: a header beginning "Copyright (C), 2024-2034, Remo Tech. Co., Ltd." that declares 122 `remo_uvc_ctrl_*` functions, includes a `remo_type.h` that is not supplied, comes with no library, and contains no licence text.

The Windows build, `app/bin/libdev.dll` in OBSBOT Center for Windows (SHA256 `a9707f18f6648b5ffe625ec70099fbeb1c89b8a6a37e7e4cd265991e9da0ab22`), exports 287 `Device::camera…` methods but contains no `ftplib` strings and no `mtp` namespace symbols; it references the Windows Portable Devices API instead. The matches in this finding are therefore limited to the macOS and Linux builds.


## Finding 6: OBSBOT's Terms of Use

Captured 2026-11-23 16:31 UTC from https://www.obsbot.com/service/docs/terms-of-use (`captures/terms-of-use.html`, SHA256 `5ee4ec01eb757055f0e4ab5661fd16bbd9a147d5c4435d0c5e2fb80065a67eda`; text in `captures/terms-of-use.txt`, with line numbers cited below). The page shows no revision date.

| Clause | Text |
|---|---|
| 1.i, the parties (lines 39–43) | "This Agreement is an agreement between you and Remo Intelligent Technology (Shenzhen) Co., Ltd. (OBSBOT) and its affiliated companies" |
| 2, updates (lines 117–120) | the right to announce "the modification, replacement and upgrade of any website content, software and firmware related to this Service" |
| 3, grant of licence (lines 129–135) | "We grant you a limited, personal, revocable, non-exclusive, non-commercial, non-transferable and non-sublicensable license to use the our platform […] You acknowledge and understand that our platform is licensed and not sold to you" |
| 6, Service Use Specifications, item (11) (lines 433–434) | "Do not reverse engineer, reverse assemble, decompile, or otherwise attempt to discover the source code of our platform;" |
| 6, Service Use Specifications, item (14) (lines 439–441) | "Do not remove, delete, alter, or obscure any trademarks or notices of any copyright, trademark, patent, or other intellectual property or proprietary rights, provided on or with the software" |
| 11.i, third-party software (lines 636–643) | "The use of such third-party software/links is subject to the terms provided by the licensor of that software". The section names no third-party or open-source component and contains no source offer. |
| 16, governing law (lines 738–745) | the laws of the mainland of the People's Republic of China; disputes to "the People's Court with jurisdiction in Nanshan District, Shenzhen" |

The LGPL on combining its libraries into a larger work:

- **LGPL-3.0, section 4 "Combined Works"**, as reproduced in OBSBOT Center's own `license/LICENSE` (lines 90–94): "You may convey a Combined Work under terms of your choice that, taken together, effectively do not restrict modification of the portions of the Library contained in the Combined Work and reverse engineering for debugging such modifications, if you also do each of the following: […]"
- **LGPL-2.1, section 6**, the licence of glibc, Avahi, alsa-lib, libnl, ftplibpp and android-file-transfer-linux (glibc's `COPYING.LIB`, copied to `captures/glibc-COPYING.LIB.txt`, lines 271–276): "you may also combine or link a \"work that uses the Library\" with the Library to produce a work containing portions of the Library, and distribute that work under terms of your choice, provided that the terms permit modification of the work for the customer's own use and reverse engineering for debugging such modifications."

OBSBOT's SDK page (https://www.obsbot.com/sdk, captured 2026-11-23 16:42 UTC, `captures/sdk-page.*`, SHA256 `41b598a4182f9d55675539e8f908de3bba7eeedf3074ffa8d230f9b56ee9ade2`) asks the visitor to sign in to an OBSBOT account ("Please sign in first, the SDK file will be sent to the email address that associated to your OBSBOT account") and then shows an application form with two questions, "Do you own an OBSBOT product?" and "Why you need the SDK?". Neither the page nor the form shows licence terms or asks for agreement to any. The report's owner signed in on 2026-11-23 and saw no terms or agreement step; signed in, the form adds only a "Which product you owned" field and a prompt to describe the use (owner's copy of the dialog text: `captures/sdk-form-signed-in.owner.txt`). The owner's OBSBOT account was verified by an emailed code at 2025-10-16 00:17:41 UTC, one minute before OBSBOT's two SDK emails; neither the verification email nor the SDK emails mention licence terms, and the SDK package and header carry none (Finding 5).

OBSBOT's "Intellectual Property Rights" page (https://www.obsbot.com/service/docs/intellectual-property-rights), linked from the same site, had no body text when captured on 2026-11-23, either as served or as rendered in a browser (`captures/ip-rights.*`).

## Not examined

- The printed materials in the box and the camera's own interfaces, which are places where a written offer could appear. OBSBOT's Privacy Policy page. (The Meet 2 user manual was examined: its only relevant line is "4K streaming requires compatible third-party software.")
- The other plugins in OBSBOT Center for Windows' `app/rmfunc/` directory.
- Other OBSBOT web pages, one by one. A web search on 2026-11-23 found no OBSBOT page offering source code.
- The compressed U-Boot payload, and a code-level comparison with any upstream project.

## Requests to OBSBOT

| Date | Channel | Request | Reply |
|---|---|---|---|
| 2026-02-11 | Email to the OBSBOT contact that OBSBOT's SDK email names for Linux SDK support | "Any chance obsbot would consider releasing sources to build the .so for better driver support on linux? I am using it in this camera control utility right now. https://github.com/aaronsb/obsbot-camera-control" | None found in the sender's mailbox as of 2026-11-23 |
| Not recorded | A message to OBSBOT through social media; the report's owner did not record the platform or date | A request for source code (as recalled by the report's owner) | None (as recalled by the report's owner) |

## Reproducing the findings

Requirements: bash, python3, `sha256sum`, GNU grep, GNU `strings` (binutils), `7z` (p7zip), `innoextract`, and `pdftotext`/`pdfinfo` (poppler). The script installs `ubi_reader` 0.8.16 into a virtual environment in its work directory. It reads and unpacks the downloads and runs nothing from them.

1. Download the firmware, the macOS application, the Windows installer and the user manual from https://www.obsbot.com/download/obsbot-meet-2 with a web browser.
2. Put them (and the two SDK libraries, if you have them) in one directory and run `sha256sum -c SHA256SUMS` there; files you don't have are reported as missing.
3. Run:

   ```
   ./reproduce.sh Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin \
                  Obsbot_Center_OA_E_MacOS_Intel_2.0.16.433_release.dmg \
                  --win Obsbot_Center_OA_E_Win_x64_2.0.16.433_release.exe \
                  --manual OBSBOTMeet2UserManual_ENv1.1.pdf \
                  --sdkzip libdev_v2_1_0_7.zip \
                  [--libdev libdev.so.1.0.2 --libdev libdev.so.1.0.0] \
                  --work /tmp/obsbot-evidence
   ```

4. Compare the output with `expected-output.txt`. Its paths are shortened to `<downloads>`, `<sdk>` and `<workdir>`. It was produced with GNU strings 2.47.

All five findings reproduce from OBSBOT's public downloads alone. The Linux SDK libraries add the corroborating columns of Finding 5. The upstream licence checks are links to the upstream projects, not script output.

## Files in this directory

| File | Purpose |
|---|---|
| `README.md` | This report |
| `reproduce.sh` | Reproduces the findings from the downloads |
| `carve_fw.py` | Splits the firmware image along its partition table |
| `SHA256SUMS` | Hashes of the eight examined files, checkable with `sha256sum -c` |
| `captures/` | Dated captures of OBSBOT's Terms of Use, Intellectual Property Rights and SDK pages, response headers of the SDK downloads (HTML, response headers, extracted text, capture notes), and the LGPL-2.1 text cited in Finding 6 |
| `expected-output.txt` | Output of `reproduce.sh` on 2026-11-23, including hashes of every cited file inside the downloads |
