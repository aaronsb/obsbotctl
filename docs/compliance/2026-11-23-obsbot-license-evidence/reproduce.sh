#!/usr/bin/env bash
# Reproduce the findings in README.md from OBSBOT's downloads.
#
# Usage:
#   reproduce.sh <Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin> \
#                <Obsbot_Center_OA_E_MacOS_Intel_2.0.16.433_release.dmg> \
#                [--win Obsbot_Center_OA_E_Win_x64_2.0.16.433_release.exe] \
#                [--manual OBSBOTMeet2UserManual_ENv1.1.pdf] \
#                [--sdkzip libdev_v2_1_0_7.zip] [--libdev libdev.so ...] [--work workdir]
#
# --sdkzip takes OBSBOT's SDK package, linked from OBSBOT's SDK email:
# https://resource-cdn.obsbothk.com/download/share/libdev_v2_1_0_7.zip?direct_download=1
#
# --libdev takes Linux SDK libraries to check (repeatable). OBSBOT does not
# publish them; it supplies them in reply to an SDK enquiry. Copies are in
# github.com/aaronsb/obsbot-camera-control under sdk/*/lib/.
#
# Needs: bash, python3, sha256sum, GNU grep, GNU strings (binutils), 7z;
# innoextract for --win, pdftotext (poppler) for --manual.
# Installs ubi_reader (pinned) into a virtualenv in the work directory.
# Reads and unpacks the downloads; runs nothing from them.
#
# No -e or pipefail: `strings | grep -m1` ends strings with SIGPIPE, and a
# check that finds nothing is a result to print, not a reason to stop.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
FW=${1:?firmware .bin}; DMG=${2:?OBSBOT Center .dmg}; shift 2
LIBDEVS=(); WORK=""; WIN=""; MANUAL=""; SDKZIP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --win) WIN=$2; shift 2 ;;
    --manual) MANUAL=$2; shift 2 ;;
    --sdkzip) SDKZIP=$2; shift 2 ;;
    --libdev) LIBDEVS+=("$2"); shift 2 ;;
    --work) WORK=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
WORK=${WORK:-$(mktemp -d /tmp/obsbot-evidence.XXXX)}
mkdir -p "$WORK"
UBI_READER_VERSION=0.8.16
STR="strings -a"          # -a: scan whole files, including debug sections

say() { printf '\n== %s\n' "$*"; }
rel() { sed "s|$WORK/||"; }
first() { grep -m1 "$@"; }

say "0. Tools"
echo "work directory: $WORK"
strings --version | head -1
grep --version | head -1
python3 --version

say "1. Download hashes (compare with SHA256SUMS)"
sha256sum "$FW" "$DMG" ${WIN:+"$WIN"} ${MANUAL:+"$MANUAL"} ${SDKZIP:+"$SDKZIP"}

say "2. Firmware partition table"
python3 -I "$HERE/carve_fw.py" "$FW" "$WORK/fw"

say "3. Kernel and bootloader images (U-Boot legacy uImage headers; times in UTC)"
for p in KERNEL.bin RECOVERY.bin UBOOT0.bin UBOOT1.bin; do
  python3 -I - "$WORK/fw/$p" <<'EOF'
import struct, sys, time
h = open(sys.argv[1], "rb").read(64)
magic, _, ts, size, load, ep, _, os_, arch, typ, comp = struct.unpack(">7I4B", h[:32])
name = h[32:64].rstrip(b"\0").decode("latin-1")
osn = {5: "Linux", 17: "U-Boot firmware"}.get(os_, os_)
print(f"{sys.argv[1].rsplit('/',1)[-1]:13s} magic={magic:#x} os={osn} arch={arch} "
      f"built={time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts))} name(32 bytes)={name!r}")
EOF
done
echo "kernel version banner in KERNEL.bin:"
$STR "$WORK/fw/KERNEL.bin" | first 'Linux version'

say "4. Unpack the three UBI filesystems (ubi_reader $UBI_READER_VERSION; messages in ubi-*.log)"
if [ ! -x "$WORK/venv/bin/ubireader_extract_files" ]; then
  python3 -m venv "$WORK/venv" && "$WORK/venv/bin/pip" -q install "ubi_reader==$UBI_READER_VERSION" 2>/dev/null
fi
for v in ROOTFS UPDATERFS AIFS; do
  "$WORK/venv/bin/ubireader_extract_files" -o "$WORK/$v" "$WORK/fw/$v.ubi" >"$WORK/ubi-$v.log" 2>&1
  echo "$v: $(find "$WORK/$v" -type f | wc -l) files, $(grep -c -i -E 'error|fatal|fail' "$WORK/ubi-$v.log") error lines in log"
done
ROOT=$(find "$WORK/ROOTFS" -mindepth 2 -maxdepth 2 -type d | head -1)
UPD=$(find "$WORK/UPDATERFS" -mindepth 2 -maxdepth 2 -type d | head -1)
AI=$(find "$WORK/AIFS" -mindepth 2 -maxdepth 2 -type d | head -1)

say "5. Operating system identity (root filesystem)"
cat "$ROOT/etc/issue"
grep -E '^(NAME|VERSION|VERSION_ID)=' "$ROOT/etc/os-release"
echo "kernel modules dir: $(ls "$ROOT/lib/modules")"
$STR "$ROOT/bin/busybox" | first 'BusyBox v'
$STR "$ROOT/lib/libc-2.33.so" | first 'GNU C Library'
$STR "$ROOT/usr/sbin/umtprd" | first 'uMTP Responder'

say "6. Open-source components present (by file name), and hashes of cited files"
ls "$ROOT/usr/lib" "$ROOT/usr/sbin" "$ROOT/usr/bin" "$ROOT/sbin" "$ROOT/lib" "$ROOT/app/lib" 2>/dev/null \
  | grep -o -E '^(lib)?(avahi|dbus|asound|nl-3|ssl|crypto|z|jpeg|turbojpeg|protobuf|nanomsg|zmq|zmqpp|glog|gflags|boost_[a-z]+|umtprd|hostapd|wpa_supplicant)' \
  | sort -u | tr '\n' ' '; echo
(cd "$WORK" && sha256sum fw/*.bin fw/*.ubi fw/config \
  "${ROOT#$WORK/}/bin/busybox" "${ROOT#$WORK/}/lib/libc-2.33.so" "${ROOT#$WORK/}/usr/sbin/umtprd" \
  "${ROOT#$WORK/}/etc/os-release" "${ROOT#$WORK/}/etc/issue" "${ROOT#$WORK/}"/lib/*_LICENSE_*.txt)

say "7. Notices that do exist in the firmware"
echo "BusyBox:  $($STR "$ROOT/bin/busybox" | first 'copyrighted by') / $($STR "$ROOT/bin/busybox" | first 'Licensed under GPLv2')"
echo "glibc:    $($STR "$ROOT/lib/libc-2.33.so" | first 'Copyright (C)')"
echo "umtprd:   $($STR "$ROOT/usr/sbin/umtprd" | first -i 'Viveris')"
echo "inittab:  $(sed -n 3p "$ROOT/etc/inittab")"
echo "Avahi:    LGPL header comments in $(grep -rl 'GNU Lesser General Public License' "$ROOT/etc/avahi" "$ROOT/usr/share/dbus-1" | wc -l) config/interface files"
for f in "$ROOT"/lib/*_LICENSE_*.txt; do
  echo "$(basename "$f"): $(grep -m1 -i -E 'copyright|ooura' "$f" | sed 's/^[ *]*//' | cut -c1-80)"
done

say "8. Licence declarations of OBSBOT's own kernel modules (root and updater filesystems)"
find "$ROOT" "$UPD" -name '*.ko' | grep -i remo | sort | while read -r k; do
  echo "$(echo "$k" | rel): $($STR "$k" | grep -E '^(license|author)=' | sort | tr '\n' ' ')"
done

say "9. Full licence texts and source offers anywhere in the firmware"
# Each pattern is a phrase that appears only in a full licence text:
#   GPL-2.0 / LGPL-2.1 preamble, GPL-3.0 preamble, LGPL-3.0 opening sentence.
TEXTS='The licenses for most software are designed to take away your|The GNU General Public License is a free, copyleft license|This version of the GNU Lesser General Public License incorporates'
OFFERS='written offer|source code (is|are) available|corresponding source|complete source code'
SCOPE=("$ROOT" "$UPD" "$AI" "$WORK/fw/KERNEL.bin" "$WORK/fw/UBOOT0.bin" "$WORK/fw/config")
echo "searched: root fs, updater fs, AI fs (all files, binaries included), KERNEL.bin, UBOOT0.bin, config"
echo "positive control 1 - the text pattern finds the LGPL-3.0 text in the macOS app's LICENSE:"
echo "  (run in section 10)"
echo "positive control 2 - the phrase 'GNU Lesser General Public License' in Avahi's files:"
grep -rl -a 'GNU Lesser General Public License' "$ROOT/etc/avahi" | rel | head -2 | sed 's/^/  /'
echo "files with full licence text:"
grep -rl -a -E "$TEXTS" "${SCOPE[@]}" 2>/dev/null | rel | sed 's/^/  /'
echo "  (end of list)"
echo "files with source-offer wording:"
grep -rl -a -i -E "$OFFERS" "${SCOPE[@]}" 2>/dev/null | rel | sed 's/^/  /'
echo "  (end of list)"
echo "note: UBOOT0.bin's payload has no readable strings (compressed); the search covers its header only."

say "10. OBSBOT Center for macOS: both bundles in the DMG"
7z x -y -o"$WORK/dmg" "$DMG" >/dev/null 2>&1
OUTER=$(find "$WORK/dmg" -maxdepth 3 -name '*.app' -type d | head -1)
for APP in "$OUTER" "$OUTER/Contents/Modules/OBSBOT_Center.app"; do
  [ -d "$APP" ] || continue
  C="$APP/Contents"
  echo "--- $(echo "$APP" | rel)"
  echo "version: $(grep -A1 CFBundleShortVersionString "$C/Info.plist" | grep -o '<string>[^<]*' | cut -c9-)"
  echo "licence-like files (outside nested bundles):"
  find "$APP" -path "$APP/Contents/Modules" -prune -o \( -iname '*licen*' -o -iname '*acknowledg*' -o -iname '*notice*' -o -iname '*copying*' \) -type f -print | rel | sed 's/^/  /'
  echo "source-offer wording (whole bundle, binaries included), with the matched text:"
  grep -rl -a -i -E "$OFFERS" "$APP" --exclude-dir=Modules 2>/dev/null | while read -r f; do
    $STR "$f" | grep -i -o -E ".{0,40}($OFFERS).{0,40}" | sort -u | head -3 \
      | sed "s|^|  $(echo "$f" | rel | sed 's|.*/Contents/||'): |"
  done
  echo "  (end of list)"
  AV=$(ls "$C/Frameworks"/libavcodec*.dylib | head -1)
  echo "$($STR "$AV" | first 'libavcodec license')"
  $STR "$AV" | grep -m1 -o -E -- '--enable-[a-z0-9]+( --[a-z-]+[a-z0-9=._/-]*){0,80}' \
    | tr ' ' '\n' | grep -E -- '--enable-(gpl|version3|libx264)|--prefix' | sed 's/^/  /'
  $STR "$(ls "$C/Frameworks"/libavutil*.dylib | head -1)" | grep -m1 -o -E 'FFmpeg version [^ ]+'
  $STR "$(ls "$C/Frameworks"/libx264*.dylib | head -1)" | first 'x264 - core' | cut -c1-90
  (cd "$C" && sha256sum Frameworks/libavcodec*.dylib Frameworks/libx264*.dylib $(ls license/LICENSE Frameworks/libdev.dylib 2>/dev/null))
done
echo "positive control 1 - the full-text pattern matches the outer app's LICENSE:"
grep -l -a -E "$TEXTS" "$OUTER/Contents/license/LICENSE" | rel | sed 's/^/  /'
echo "first lines of the outer app's Contents/license/LICENSE:"
head -n 8 "$OUTER/Contents/license/LICENSE" | sed 's/^/  /'
N="$OUTER/Contents/Modules/OBSBOT_Center.app/Contents"
if [ -f "$N/Frameworks/librm.framework/librm" ]; then
  echo "nested librm: libobs API symbols = $($STR "$N/Frameworks/librm.framework/librm" | grep -c -E '^_(gs_create|gs_effect_create_from_file|calldata_[a-z_]+|dstr_[a-z_]+)$')"
  E=$(find "$N" -name bicubic_scale.effect | head -1)
  [ -n "$E" ] && echo "nested bicubic_scale.effect line 3: $(sed -n 3p "$E")"
fi

say "11. OBSBOT SDK library: MTP and FTP code"
D="$OUTER/Contents/Frameworks/libdev.dylib"
echo "macOS libdev.dylib (public download): $(sha256sum "$D" | cut -c1-64)"
echo "  mangled symbols: Device::camera API=$($STR "$D" | grep -c -E '^__ZN6Device[0-9]+camera')" \
     "mtp=$($STR "$D" | grep -c -E '^__ZN3mtp') mtp::Session=$($STR "$D" | grep -c -E '^__ZN3mtp7Session')" \
     "ftplib=$($STR "$D" | grep -c -E '^__ZN6ftplib')" \
     "licence-text strings=$($STR "$D" | grep -i -c -E 'GNU (Lesser )?General Public|LGPL')"
$STR "$D" | grep -E '^__ZN6ftplib(10FtpSendCmd|19CorrectPasv|8readresp)|^__ZN3mtp7Session14GetStorageInfo' | sed 's/^/  /'
for L in "${LIBDEVS[@]}"; do
  echo "$(sha256sum "$L")"
  echo "  mangled symbols: Device::camera API=$($STR "$L" | grep -c -E '^_ZN6Device[0-9]+camera')" \
       "mtp::Session=$($STR "$L" | grep -c -E '^_ZN3mtp7Session')" \
       "ftplib=$($STR "$L" | grep -c -E '^_ZN6ftplib')" \
       "licence-text strings=$($STR "$L" | grep -i -c -E 'GNU (Lesser )?General Public|LGPL')"
  $STR "$L" | grep -E '^_ZN3mtp7Session(16GetPartialObject|14GetStorageInfo)' | sed 's/^/  /'
  $STR "$L" | grep -E '/(mtp|ftp)/[A-Za-z_/]+\.(cpp|h)' | grep -E 'ftplib.cpp|usb/Context.cpp' | sort -u | sed 's/^/  build path: /'
done

if [ -n "$WIN" ]; then
  say "12. OBSBOT Center for Windows"
  innoextract -q -d "$WORK/win" "$WIN" >/dev/null 2>&1
  A="$WORK/win/app"
  echo "files unpacked: $(find "$WORK/win" -type f | wc -l)"
  echo "licence-like files:"
  find "$A" \( -iname '*licen*' -o -iname '*acknowledg*' -o -iname '*notice*' -o -iname '*copying*' \) -type f | rel | sed 's/^/  /'
  if cmp -s <(tr -d '\r' < "$A/license/LICENSE") "$OUTER/Contents/license/LICENSE"; then
    echo "app/license/LICENSE: same text as the macOS LICENSE (line endings aside)"
  fi
  echo "source-offer wording (whole install tree, binaries included), with the matched text:"
  grep -rl -a -i -E "$OFFERS" "$A" 2>/dev/null | while read -r f; do
    $STR "$f" | grep -i -o -E ".{0,40}($OFFERS).{0,40}" | sort -u | head -2 | sed "s|^|  $(echo "$f" | rel): |"
  done
  echo "  (end of list)"
  echo "$($STR "$A/bin/avcodec-60.dll" | first 'libavcodec license')"
  $STR "$A/bin/avcodec-60.dll" | grep -m1 -o -E -- '--enable-[a-z0-9]+( --[a-z-]+[a-z0-9=._/-]*){0,80}' \
    | tr ' ' '\n' | grep -E -- '--enable-(gpl|version3|libx264)' | sed 's/^/  /'
  echo "FFmpeg version: $($STR "$A/bin/avutil-58.dll" | grep -m1 -E '^n[0-9]+\.[0-9].*-g[0-9a-f]+$')"
  $STR "$A/bin/libx264-164.dll" | first 'x264 - core' | cut -c1-90
  echo "rm.dll: libobs API names = $($STR "$A/bin/rm.dll" | grep -c -E '^(gs_create|gs_effect_create_from_file|calldata_[a-z_]+|dstr_[a-z_]+|obs_[a-z_]+)$')"
  E=$(find "$A" -name bicubic_scale.effect | head -1)
  [ -n "$E" ] && echo "$(echo "$E" | rel) line 3: $(sed -n 3p "$E")"
  W="$A/rmfunc/win-capture.dll"
  echo "rmfunc/win-capture.dll: exported entry points:"
  $STR "$W" | grep -E '^rm_module_(load|unload|set_locale|free_locale|get_string|description|ver|set_pointer)$' | sort -u | tr '\n' ' ' | sed 's/^/  /'; echo
  echo "  log lines with OBS game-capture's prefix \"[game-capture: '%s']\": $($STR "$W" | grep -c "\[game-capture: '%s'\]")"
  echo "  references graphics-hook64.dll: $($STR "$W" | grep -c '^graphics-hook64.dll$')"
  D="$A/bin/libdev.dll"
  echo "bin/libdev.dll: $(sha256sum "$D" | cut -c1-64)"
  echo "  Device::camera methods=$($STR "$D" | grep -c -E '^\?camera[A-Za-z]+@Device@@')" \
       "ftplib strings=$($STR "$D" | grep -c -i ftplib) mtp-namespace symbols=$($STR "$D" | grep -c '@mtp@')" \
       "Windows Portable Devices strings=$($STR "$D" | grep -c -i PortableDevice)"
  (cd "$A" && sha256sum license/LICENSE bin/avcodec-60.dll bin/libx264-164.dll bin/rm.dll bin/libdev.dll rmfunc/win-capture.dll)
fi

if [ -n "$MANUAL" ]; then
  say "13. Meet 2 user manual"
  pdftotext -layout "$MANUAL" "$WORK/manual.txt"
  pdfinfo "$MANUAL" | grep -E '^(Title|Pages|CreationDate):'
  echo "lines mentioning open source, GPL, licences, copyright, source code or third parties:"
  grep -n -i -E 'open.?source|GPL|licen[cs]e|written offer|source code|third.?party|copyright|GNU' "$WORK/manual.txt" | sed 's/^/  /'
  echo "  (end of list)"
fi

if [ -n "$SDKZIP" ]; then
  say "14. OBSBOT SDK package"
  7z x -y -o"$WORK/sdkzip" "$SDKZIP" >/dev/null 2>&1
  Z=$(find "$WORK/sdkzip" -mindepth 1 -maxdepth 1 -type d | head -1)
  echo "top folder: $(basename "$Z"), files: $(find "$Z" -type f | wc -l)"
  echo "licence-like or readme files:"
  find "$Z" \( -iname '*licen*' -o -iname '*notice*' -o -iname '*copying*' -o -iname 'readme*' \) -type f | rel | sed 's/^/  /'
  echo "  (end of list)"
  L="$Z/linux(beta)/x86_64-release/libdev.so.1.0.2"
  (cd "$Z" && sha256sum "linux(beta)/x86_64-release/libdev.so.1.0.2" include/dev/dev.hpp)
  echo "  linux x86_64 libdev.so.1.0.2: mtp::Session=$($STR "$L" | grep -c -E '^_ZN3mtp7Session')" \
       "ftplib=$($STR "$L" | grep -c -E '^_ZN6ftplib')" \
       "licence-text strings=$($STR "$L" | grep -i -c -E 'GNU (Lesser )?General Public|LGPL')"
  for L2 in "${LIBDEVS[@]}"; do
    cmp -s "$L" "$L2" && echo "  identical to --libdev $(basename "$L2")"
  done
fi

say "done"
