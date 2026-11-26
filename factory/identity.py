#!/usr/bin/env python3
"""Extract each pinned firmware image's device identity for the factory.

For every image in factory/firmware/pins.json that is present in the local
firmware store, this writes factory/identity/<image>.json with:

  - the image header: product, region, firmware version, chip, build type
  - the partition table, when the image uses OBSBOT's partition format
    (offsets count from 0x100 bytes before the table; this covers plain
    camera images and bundles that contain one)
  - for each UBI filesystem, unpacked with ubi_reader: every kernel module
    that sets USB IDs (it carries idVendor/idProduct module parameters),
    with its declared description, license and author, the 0x3564 vendor
    ID / product ID pairs it contains, and the UVC extension-unit
    descriptors it contains (unit ID, GUID, number of controls)

An image the tool cannot unpack is recorded with the reason, never guessed.
It reads the files only: no vendor code is run, decompiled or disassembled.

Usage: identity.py [IMAGE …]        (default: every pinned image)
Needs: ubireader_extract_files from ubi_reader 0.8.16, found on PATH, in
$UBIREADER, or in factory/.venv (python3 -m venv factory/.venv &&
factory/.venv/bin/pip install ubi_reader==0.8.16).
Unpacked files go to $OBSBOT_FACTORY_WORK (default
~/.cache/libobsbot/factory/), outside the repository.

References:
- ADR-100 D3: extraction reads inputs without decompiling them, and the
  corpus can be rebuilt from scratch from the pinned inputs.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = os.path.join(HERE, "firmware", "pins.json")
OUT = os.path.join(HERE, "identity")
STORE = os.environ.get("OBSBOT_FIRMWARE_DIR", os.path.expanduser("~/.local/share/libobsbot/firmware"))
WORK = os.environ.get("OBSBOT_FACTORY_WORK", os.path.expanduser("~/.cache/libobsbot/factory"))
VENDOR = 0x3564
PART_NAMES = (b"ROOTFS.ubi", b"UPDATERFS.ubi", b"AIFS.ubi", b"KERNEL.bin", b"UBOOT0.bin")


def ubireader():
    for cand in (os.environ.get("UBIREADER"), shutil.which("ubireader_extract_files"),
                 os.path.join(HERE, ".venv", "bin", "ubireader_extract_files")):
        if cand and os.access(cand, os.X_OK):
            return cand
    sys.exit("ubireader_extract_files not found; see --help")


def cstr(b):
    return b.split(b"\0")[0].decode("ascii", "replace")


def header(d):
    """OBSBOT image header: magic 98 ec 20 ab, then fixed fields."""
    if d[:4] != bytes.fromhex("98ec20ab"):
        return None
    v = d[0x30:0x34]
    return {
        "product": cstr(d[0x10:0x20]),
        "region": cstr(d[0x20:0x30]),
        "version": f"{v[3]}.{v[2]}.{v[1]}.{v[0]}",
        "chip": cstr(d[0x48:0x58]),
        "build": cstr(d[0x58:0x68]),
    }


def partitions(d):
    """Find OBSBOT's partition table: 0x100-byte entries, name at +0x1c,
    (type, size, offset) u32 LE at +0; offsets from 0x100 before the table."""
    hits = [d.find(n) for n in PART_NAMES]
    hits = [h - 0x1C for h in hits if h >= 0x1C]
    if not hits:
        return None, []
    first = min(hits)
    while first >= 0x100 and re.fullmatch(rb"[A-Za-z0-9_.]{3,}", d[first - 0x100 + 0x1C:first - 0x100 + 0x3C].split(b"\0")[0] or b"-"):
        first -= 0x100
    base, pos, parts = first - 0x100, first, []
    while pos + 0x100 <= len(d):
        e = d[pos:pos + 0x100]
        name = cstr(e[0x1C:0x3C])
        if not re.fullmatch(r"[A-Za-z0-9_.]{3,}", name or "-"):
            break
        typ, size, off = struct.unpack("<3I", e[:12])
        start = base + off
        parts.append({"name": name, "type": typ, "offset": start, "size": size,
                      "magic": d[start:start + 4].hex() if start + 4 <= len(d) else None})
        pos += 0x100
    return base, parts


def modinfo(b):
    info = {}
    for key in ("description", "license", "author", "depends", "vermagic"):
        m = re.search(rb"(?:^|\0)" + key.encode() + rb"=([^\0]*)", b)
        if m:
            info[key] = m.group(1).decode("utf-8", "replace")
    return info


def xu_descriptors(b):
    """UVC extension-unit descriptors: bLength, 0x24, 0x06, bUnitID,
    guidExtensionCode[16], bNumControls, bNrInPins, …"""
    found = []
    for m in re.finditer(rb"[\x18-\x40]\x24\x06", b):
        i = m.start()
        length, unit = b[i], b[i + 3]
        if i + length > len(b) or unit == 0:
            continue
        g = b[i + 4:i + 20]
        guid = f"{g[3::-1].hex()}-{g[5:3:-1].hex()}-{g[7:5:-1].hex()}-{g[8:10].hex()}-{g[10:16].hex()}"
        found.append({"unit": unit, "guid": guid, "num_controls": b[i + 20], "at": i})
    return found


def usb_ids(b):
    return sorted({(VENDOR, b[m.end()] | b[m.end() + 1] << 8)
                   for m in re.finditer(re.escape(struct.pack("<H", VENDOR)), b) if m.end() + 1 < len(b)})


def route_enums(root):
    """The camera's route/enum.json: device addresses and command-set numbers
    (DEVICE, CMDSET), as plain JSON that may carry // comments."""
    for dirpath, _, files in os.walk(root):
        if "enum.json" in files and dirpath.endswith(os.path.join("app", "route")):
            text = re.sub(r"//[^\n]*", "", open(os.path.join(dirpath, "enum.json"), errors="replace").read())
            try:
                data = json.loads(text)
            except ValueError:
                return None
            return {k: {i["key"]: i["val"] for i in v.get("keysList", [])} for k, v in data.items() if k in ("DEVICE", "CMDSET")}
    return None


def gadget_modules(root):
    out = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".ko"):
                continue
            p = os.path.join(dirpath, f)
            b = open(p, "rb").read()
            if b"parm=idProduct" not in b and b"parmtype=idProduct" not in b:
                continue
            ids = usb_ids(b)
            out.append({
                "path": os.path.relpath(p, root),
                "sha256": hashlib.sha256(b).hexdigest(),
                "modinfo": modinfo(b),
                "usb_ids": [f"{v:04x}:{p_:04x}" for v, p_ in ids],
                "extension_units": [{k: v for k, v in x.items() if k != "at"} for x in xu_descriptors(b)],
            })
    return sorted(out, key=lambda m: m["path"])


def identify(name, pin, tool):
    path = os.path.join(STORE, name)
    d = open(path, "rb").read()
    rec = {"image": name, "sha256": pin["sha256"], "size": len(d), "header": header(d)}
    base, parts = partitions(d)
    rec["partition_table_base"] = base
    rec["partitions"] = parts
    if not parts:
        rec["unpacked"] = False
        rec["reason"] = "no OBSBOT partition table found"
        return rec
    work = os.path.join(WORK, name)
    os.makedirs(work, exist_ok=True)
    rec["filesystems"] = {}
    for p in parts:
        if p["magic"] != "55424923":  # "UBI#"
            continue
        blob = os.path.join(work, p["name"])
        with open(blob, "wb") as f:
            f.write(d[p["offset"]:p["offset"] + p["size"]])
        dest = os.path.join(work, p["name"] + ".d")
        shutil.rmtree(dest, ignore_errors=True)
        r = subprocess.run([tool, "-k", "-o", dest, blob], capture_output=True, text=True)
        files = sum(len(fs) for _, _, fs in os.walk(dest))
        rec["filesystems"][p["name"]] = {"exit": r.returncode, "files": files, "gadget_modules": gadget_modules(dest),
                                          "route_enums": route_enums(dest)}
    rec["unpacked"] = any(fs["files"] for fs in rec["filesystems"].values())
    if not rec["unpacked"]:
        rec["reason"] = "no UBI filesystem could be unpacked"
    return rec


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    tool = ubireader()
    pins = json.load(open(PINS))
    names = sys.argv[1:] or sorted(pins)
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        if not os.path.exists(os.path.join(STORE, name)):
            print(f"missing {name} (run firmware.py hydrate)")
            continue
        rec = identify(name, pins[name], tool)
        with open(os.path.join(OUT, name + ".json"), "w") as f:
            json.dump(rec, f, indent=1)
            f.write("\n")
        # The summary counts only modules that set an OBSBOT USB ID; the record
        # keeps every gadget module, including the SoC vendor's reference ones.
        own = [m for fs in rec.get("filesystems", {}).values() for m in fs["gadget_modules"] if m["usb_ids"]]
        ids = sorted({i for m in own for i in m["usb_ids"]})
        guids = sorted({x["guid"] for m in own for x in m["extension_units"]})
        h = rec["header"] or {}
        print(f"{name}: {h.get('product','?')} {h.get('version','?')} chip={h.get('chip','?')} "
              f"usb={ids or '-'} xu={guids or '-'}" + ("" if rec["unpacked"] else f" ({rec['reason']})"))


if __name__ == "__main__":
    main()
