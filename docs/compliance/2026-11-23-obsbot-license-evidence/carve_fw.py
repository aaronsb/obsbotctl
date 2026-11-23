"""Split an OBSBOT Meet 2 firmware image (.bin) into its partitions.

The image starts with a 0x200-byte header, then a partition table of
0x100-byte entries from offset 0x300 to 0xB00. Each entry holds
(type: u32, size: u32, offset: u32) little-endian at its start and a
NUL-terminated name at +0x1C. Offsets are relative to the end of the
0x200-byte header.

Usage: python3 -I carve_fw.py <firmware.bin> <output-dir>
Prints one line per partition: name, offset in the file, size.
"""
import os
import struct
import sys

HEADER = 0x200
TABLE_START, TABLE_END, ENTRY = 0x300, 0xB00, 0x100


def main(path, outdir):
    data = open(path, "rb").read()
    os.makedirs(outdir, exist_ok=True)
    for pos in range(TABLE_START, TABLE_END, ENTRY):
        entry = data[pos:pos + ENTRY]
        name = entry[0x1C:0x3C].split(b"\0")[0].decode("ascii")
        if not name:
            continue
        _type, size, offset = struct.unpack("<3I", entry[:12])
        start = HEADER + offset
        blob = data[start:start + size]
        if len(blob) != size:
            sys.exit(f"{name}: table says {size} bytes at {start:#x}, file has {len(blob)}")
        with open(os.path.join(outdir, name), "wb") as f:
            f.write(blob)
        print(f"{name:14s} file offset {start:#010x}  size {size:#010x} ({size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
