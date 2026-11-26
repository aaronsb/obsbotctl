#!/usr/bin/env python3
"""Generate crates/obsbot-proto/src/opcodes.rs from the factory's extracted data.

Inputs, all committed:
  factory/identity/*.json         firmware route tables ("route_enums"): the
                                  DEVICE and CMDSET enums each firmware names
  factory/oracle/commands/*.json  what the vendor library sent for each product
                                  it recognises: libdev names, opcode,
                                  destination, request flags

Output: crates/obsbot-proto/src/opcodes.rs, committed, so the crate builds and
packages without this directory. The crate's test tests/opcodes_up_to_date.rs
runs this script with --check and fails when the committed file differs.

Usage:
  python3 -I factory/proto_tables.py           write the file
  python3 -I factory/proto_tables.py --check   exit 1 if the file is out of date

The output is passed through rustfmt, so it needs a Rust toolchain on PATH.

Checks made while generating, each fatal:
  - a DEVICE or CMDSET name has the same value in every route table naming it
  - each command's opcode equals (camera_number << 6) | camera_set
  - a libdev command has one opcode, destination and request flags across
    every product that sent it
  - every product's USB vendor ID is 0x3564
"""
import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "crates", "obsbot-proto", "src", "opcodes.rs")
VENDOR_ID = "3564"


def route_tables():
    """Yield every non-empty route_enums object in factory/identity/*.json."""
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "route_enums":
                    if v:
                        yield v
                else:
                    yield from walk(v)
        elif isinstance(o, list):
            for x in o:
                yield from walk(x)

    for path in sorted(glob.glob(os.path.join(HERE, "identity", "*.json"))):
        with open(path) as f:
            yield from walk(json.load(f))


def enum_names(tables, key, strip=""):
    """Map each name to (value, number of distinct tables naming it)."""
    distinct = {json.dumps(t[key], sort_keys=True) for t in tables}
    names = {}
    for blob in sorted(distinct):
        for name, value in json.loads(blob).items():
            name = name[len(strip):] if strip and name.startswith(strip) else name
            prev = names.get(name)
            if prev and prev[0] != value:
                sys.exit(f"{key} {name} has values {prev[0]} and {value} in different route tables")
            names[name] = (value, (prev[1] if prev else 0) + 1)
    return names, len(distinct)


def load_commands():
    products, commands, unlogged = [], {}, {}
    for path in sorted(glob.glob(os.path.join(HERE, "oracle", "commands", "*.json"))):
        with open(path) as f:
            d = json.load(f)
        vid, pid = d["usb_id"].split(":")
        if vid != VENDOR_ID:
            sys.exit(f"{path}: vendor ID {vid}, expected {VENDOR_ID}")
        pid = int(pid, 16)
        products.append((pid, d["product_type"], d["grade"]))
        for c in d["commands"]:
            op = int(c["opcode"], 16)
            if op != (c["camera_number"] << 6) | c["camera_set"]:
                sys.exit(f"{path}: {c['libdev_cmd']} opcode {op:#06x} disagrees with set/number")
            key = c["libdev_cmd"]
            fields = (c["libdev_set"], op, c["destination"], c["request_flags"])
            entry = commands.setdefault(key, {"fields": fields, "products": set()})
            if entry["fields"] != fields:
                sys.exit(f"{key}: {entry['fields']} in one product, {fields} in {path}")
            entry["products"].add(pid)
        for u in d["unlogged_requests"]:
            op = int(u["opcode"], 16)
            if op != (u["camera_number"] << 6) | u["camera_set"]:
                sys.exit(f"{path}: unlogged opcode {op:#06x} disagrees with set/number")
            fields = (u["destination"], u["request_flags"])
            entry = unlogged.setdefault(op, {"fields": fields, "products": set()})
            if entry["fields"] != fields:
                sys.exit(f"unlogged {op:#06x}: {entry['fields']} in one product, {fields} in {path}")
            entry["products"].add(pid)
    return products, commands, unlogged


def pids(s):
    return "&[" + ", ".join(f"{p:#06x}" for p in sorted(s)) + "]"


def generate():
    tables = list(route_tables())
    if not tables:
        sys.exit("no route_enums in factory/identity; run factory/identity.py first")
    devices, n_dev = enum_names(tables, "DEVICE")
    sets, n_set = enum_names(tables, "CMDSET", "CMDSET_")
    products, commands, unlogged = load_commands()
    set_names = {v: k for k, (v, _) in sets.items()}
    dev_names = {}
    for k, (v, _) in devices.items():
        dev_names.setdefault(v, []).append(k)

    def dev_expr(v):
        names = sorted(dev_names.get(v, []))
        return f"Device::{names[0]}" if len(names) == 1 else f"Device({v})"

    o = []
    w = o.append
    w("// @generated by factory/proto_tables.py from factory/identity/*.json and")
    w("// factory/oracle/commands/*.json. Do not edit; rerun the script.")
    w("")
    w("//! Opcode, device and command-set constants, and which products each")
    w("//! opcode was recorded for.")
    w("//!")
    w("//! Opcodes are named by the vendor library's enum names. A product listed")
    w("//! for an opcode is one whose identity the vendor library was given while")
    w("//! it sent that opcode; see each [`TracedProduct`] for the evidence grade.")
    w("")
    w("use crate::{CommandInfo, CommandSet, Device, Flags, Opcode, TracedProduct, UnloggedRequest};")
    w("")
    w("impl Device {")
    for name, (value, count) in sorted(devices.items(), key=lambda kv: (kv[1][0], kv[0])):
        others = [n for n in dev_names[value] if n != name]
        note = f" Shares its value with `{'`, `'.join(sorted(others))}`." if others else ""
        w(f"    /// `DEVICE` entry `{name}` = {value}, in {count} of {n_dev} distinct firmware route tables.{note}")
        w(f"    pub const {name}: Device = Device({value});")
    w("}")
    w("")
    w("impl CommandSet {")
    for name, (value, count) in sorted(sets.items(), key=lambda kv: (kv[1][0], kv[0])):
        w(f"    /// `CMDSET_{name}` = {value}, in {count} of {n_set} distinct firmware route tables.")
        w(f"    pub const {name}: CommandSet = CommandSet({value});")
    w("}")
    w("")
    order = sorted(commands.items(), key=lambda kv: (kv[1]["fields"][1] & 0x3F, kv[1]["fields"][1] >> 6))
    for name, e in order:
        libdev_set, op, dest, _ = e["fields"]
        cs = set_names.get(op & 0x3F, str(op & 0x3F))
        w(f"/// `{libdev_set}` / `{name}`: camera set {cs} ({op & 0x3F}), number {op >> 6}.")
        w(f"pub const {name}: Opcode = Opcode::from_raw({op:#06x});")
    w("")
    w("/// The products the vendor library was traced as, with the grade of that evidence.")
    w("pub const TRACED_PRODUCTS: &[TracedProduct] = &[")
    for pid, ptype, grade in sorted(products):
        w(f"    TracedProduct {{ product_id: {pid:#06x}, product_type: {ptype}, grade: {json.dumps(grade)} }},")
    w("];")
    w("")
    w("/// Every named opcode, with the products whose traces showed it.")
    w("pub const COMMANDS: &[CommandInfo] = &[")
    for name, e in order:
        libdev_set, op, dest, flags = e["fields"]
        w("    CommandInfo {")
        w(f"        name: {json.dumps(name)},")
        w(f"        libdev_set: {json.dumps(libdev_set)},")
        w(f"        opcode: {name},")
        w(f"        destination: {dev_expr(dest)},")
        w(f"        request_flags: Flags({flags:#04x}),")
        w(f"        products: {pids(e['products'])},")
        w("    },")
    w("];")
    w("")
    w("/// Requests the vendor library sent with no command log line, so with no name.")
    w("pub const UNLOGGED_REQUESTS: &[UnloggedRequest] = &[")
    for op, e in sorted(unlogged.items()):
        dest, flags = e["fields"]
        w("    UnloggedRequest {")
        w(f"        opcode: Opcode::from_raw({op:#06x}),")
        w(f"        destination: {dev_expr(dest)},")
        w(f"        request_flags: Flags({flags:#04x}),")
        w(f"        products: {pids(e['products'])},")
        w("    },")
    w("];")
    src = "\n".join(o) + "\n"
    r = subprocess.run(["rustfmt", "--edition", "2021"], input=src, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"rustfmt failed:\n{r.stderr}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed file is out of date")
    args = ap.parse_args()
    src = generate()
    rel = os.path.relpath(OUT, ROOT)
    if args.check:
        try:
            with open(OUT) as f:
                current = f.read()
        except FileNotFoundError:
            current = None
        if current != src:
            sys.exit(f"{rel} is out of date; run python3 -I factory/proto_tables.py")
        print(f"{rel} is up to date")
        return
    with open(OUT, "w") as f:
        f.write(src)
    print(f"wrote {rel}")


if __name__ == "__main__":
    main()
