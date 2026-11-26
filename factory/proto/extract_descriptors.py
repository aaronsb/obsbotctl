#!/usr/bin/env python3
"""Decode the protobuf schemas embedded in a pinned firmware image.

A program built with full (not lite) protobuf carries each .proto file it was
compiled from as a serialized FileDescriptorProto in its data. That message
begins with field 1 (name, a length-delimited string) ending in ".proto".
This script finds each such start in the image's libremo_pb2json.so, walks
the protobuf wire format while the field numbers stay within those that
FileDescriptorProto defines (1-14), which gives the blob's length, and
decodes the blob with protoc against Google's descriptor.proto.

For each image it writes factory/proto/<product>-<version>/:

  - <name>.txt     the decoded FileDescriptorProto, in protoc's text format
  - source.json    the image and its SHA256, the library's path in the image
                   and its SHA256, each blob's offset and length, and the
                   protoc version

The raw blobs go to $OBSBOT_FACTORY_WORK/proto/ (default
~/.cache/libobsbot/factory/proto/), outside the repository. It reads bytes
only: no vendor code is run, decompiled or disassembled.

Usage: extract_descriptors.py [IMAGE …]
       (default: Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin)
Needs: the image unpacked by factory/identity.py, and protoc with Google's
descriptor.proto (found under /usr/include, or set $PROTOC_INCLUDE).

References:
- ADR-100 D3: extraction reads inputs without decompiling them; each item
  records the inputs it came from by SHA256.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORY = os.path.dirname(HERE)
PINS = os.path.join(FACTORY, "firmware", "pins.json")
WORK = os.environ.get("OBSBOT_FACTORY_WORK", os.path.expanduser("~/.cache/libobsbot/factory"))
INCLUDE = os.environ.get("PROTOC_INCLUDE", "/usr/include")
LIBRARY = "usr/lib/libremo_pb2json.so"
DEFAULT = ["Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin"]


def read_varint(buf, i):
    shift = value = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, i
        shift += 7
        if shift > 63:
            break
    raise ValueError("bad varint")


def walk(buf, start, end_limit):
    """Return the end offset of a message made of fields 1-14."""
    i = start
    while i < end_limit:
        try:
            tag, j = read_varint(buf, i)
            field, wire = tag >> 3, tag & 7
            if not 1 <= field <= 14:
                break
            if wire == 0:
                _, j = read_varint(buf, j)
            elif wire == 2:
                length, j = read_varint(buf, j)
                j += length
            elif wire == 1:
                j += 8
            elif wire == 5:
                j += 4
            else:
                break
        except ValueError:
            break
        if j > end_limit:
            break
        i = j
    return i


def blobs(data):
    """Yield (name, offset, bytes) for each embedded FileDescriptorProto."""
    seen = set()
    for m in re.finditer(rb"\x0a([\x05-\x7f])([A-Za-z0-9_/.-]{1,120}\.proto)", data):
        if m.group(1)[0] != len(m.group(2)):
            continue
        name = m.group(2).decode()
        if name.startswith("google/") or name in seen:
            continue
        start = m.start()
        end = walk(data, start, min(len(data), start + 2_000_000))
        if end - start < 32:
            continue
        seen.add(name)
        yield name, start, data[start:end]


def extract(image, pin):
    m = re.match(r"Obsbot_(.+?)_OA_.*_([0-9.]+)_release\.bin$", image)
    if not m:
        sys.exit(f"{image}: cannot read product and version from the name")
    found = glob.glob(os.path.join(WORK, image, "ROOTFS.ubi.d", "*", "root", LIBRARY))
    if not found:
        sys.exit(f"{image}: {LIBRARY} not found under {WORK}/{image} (run factory/identity.py {image})")
    lib = found[0]
    data = open(lib, "rb").read()
    out = os.path.join(HERE, f"{m.group(1)}-{m.group(2)}")
    raw = os.path.join(WORK, "proto", image)
    os.makedirs(out, exist_ok=True)
    os.makedirs(raw, exist_ok=True)
    protoc = subprocess.run(["protoc", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    source = {"image": image, "image_sha256": pin["sha256"], "library": "/" + LIBRARY,
              "library_sha256": hashlib.sha256(data).hexdigest(), "protoc": protoc, "files": []}
    for name, offset, blob in blobs(data):
        stem = name.replace("/", "_")
        with open(os.path.join(raw, stem + ".pb"), "wb") as f:
            f.write(blob)
        r = subprocess.run(["protoc", f"-I{INCLUDE}", "--decode=google.protobuf.FileDescriptorProto",
                            "google/protobuf/descriptor.proto"], input=blob, capture_output=True, check=True)
        with open(os.path.join(out, stem + ".txt"), "wb") as f:
            f.write(r.stdout)
        source["files"].append({"name": name, "offset": f"{offset:#x}", "length": len(blob), "decoded": stem + ".txt"})
        print(f"{name}\t{offset:#x}\t{len(blob)} bytes")
    with open(os.path.join(out, "source.json"), "w") as f:
        json.dump(source, f, indent=1)
        f.write("\n")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    pins = json.load(open(PINS))
    for image in sys.argv[1:] or DEFAULT:
        if image not in pins:
            sys.exit(f"{image} is not pinned in {PINS}")
        extract(image, pins[image])


if __name__ == "__main__":
    main()
