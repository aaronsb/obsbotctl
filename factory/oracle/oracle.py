#!/usr/bin/env python3
"""Record what OBSBOT's vendor library sends to each camera it supports.

The oracle runs read-only probes against the vendor library (libdev) with an
LD_PRELOAD shim (xu_trace.c) between the library and the attached camera.
The shim records every UVC extension-unit request and reply, and can make
the library believe it has a different product: it substitutes the USB
product ID the library reads from /sys, and rewrites the product field of
the device-information reply (recomputing its CRC-16/USB checks). The
attached camera only ever receives requests the library sends itself; the
probes call getters only.

Commands:
  build              verify the pinned SDK files, compile the shim and probes
  enums              write factory/oracle/enums-<sdk>.json: the library's
                     command-set and command names, from its debug information
  sweep FIRST LAST   claim each USB product ID in the range (hex) and write
                     factory/oracle/sweep-<sdk>.tsv: whether the library
                     recognises it and which product type it reports
  products           join the sweep with factory/identity/*.json into
                     factory/oracle/products.json
  trace [PID …]      for each recognised product (default: all), run the
                     getter probes under its identity and write
                     factory/oracle/commands/<pid>.json: every command sent,
                     with its names, opcode and lengths (no payload bytes)
  run                build, enums, sweep fe00-feff and ff00-ff0f, products,
                     trace: the oracle's whole corpus, from scratch

Raw traces contain the attached camera's serial number and device ID, so
they stay in $OBSBOT_FACTORY_WORK/oracle (default
~/.cache/libobsbot/factory/oracle); only derived facts are committed.

Options: --sdk PACKAGE (default libdev_v2.1.0_8).

References:
- ADR-100 D3: identities for products the project does not own come from
  their own firmware; the corpus is rebuilt from scratch from pinned inputs.
- ADR-100 D7: recorded vendor behaviour is the test oracle.
"""
import argparse
import collections
import datetime
import glob
import hashlib
import json
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FACTORY = os.path.dirname(HERE)
SDK_DIR = os.environ.get("OBSBOT_SDK_DIR", os.path.expanduser("~/.local/share/libobsbot/sdk"))
WORK = os.path.join(os.environ.get("OBSBOT_FACTORY_WORK", os.path.expanduser("~/.cache/libobsbot/factory")), "oracle")
PROBES = ("probe_readonly", "probe_collect", "probe_collect_varied")
SWEEP_RANGES = (("fe00", "feff"), ("ff00", "ff0f"))


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def sdk_lib(sdk):
    pin = json.load(open(os.path.join(FACTORY, "sdk", "pins.json")))[sdk]
    path = os.path.join(SDK_DIR, sdk, pin["lib"])
    if not os.path.exists(path):
        sys.exit(f"{path} missing: {pin['obtain']}, then place it there")
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != pin["sha256"]:
        sys.exit(f"{path}: sha256 {digest} does not match the pin {pin['sha256']}")
    return path


def bindir(sdk):
    return os.path.join(WORK, "bin", sdk)


def build(args):
    lib = sdk_lib(args.sdk)
    out = bindir(args.sdk)
    os.makedirs(out, exist_ok=True)
    sh(["cc", "-shared", "-fPIC", "-O2", "-Wall", "-o", os.path.join(out, "xu_trace.so"), os.path.join(HERE, "xu_trace.c"), "-ldl"])
    inc = os.path.join(SDK_DIR, args.sdk, "include")
    libdir = os.path.dirname(lib)
    for p in PROBES:
        sh(["g++", "-std=c++17", "-O1", "-I" + inc, os.path.join(HERE, p + ".cpp"), "-L" + libdir, "-ldev",
            "-Wl,-rpath," + libdir, "-o", os.path.join(out, p)])
    print(f"built shim and {len(PROBES)} probes against {args.sdk} in {out}")


def run_probe(sdk, probe, tag, env_extra, probe_args, timeout=300):
    """Run one probe under the shim; return (trace lines, stdout lines)."""
    out = bindir(sdk)
    tdir = os.path.join(WORK, "traces", sdk)
    os.makedirs(tdir, exist_ok=True)
    trace = os.path.join(tdir, tag + ".log")
    if os.path.exists(trace):
        os.remove(trace)
    env = dict(os.environ, XU_TRACE_FILE=trace, LD_PRELOAD=os.path.join(out, "xu_trace.so"), **env_extra)
    try:
        r = subprocess.run([os.path.join(out, probe), *probe_args], env=env, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        stdout = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    with open(trace + ".stdout", "w") as f:
        f.write(stdout)
    lines = open(trace).read().splitlines() if os.path.exists(trace) else []
    return lines, stdout.splitlines()


def packets(trace, query):
    pat = re.compile(r" xu .*sel=2 " + query + r".*data=([0-9a-f]+)")
    return [bytes.fromhex(m.group(1)) for line in trace for m in [pat.search(line)] if m and m.group(1)]


# --- enums -------------------------------------------------------------------

def enums(args):
    lib = sdk_lib(args.sdk)
    want = re.compile(r"^Cmd[A-Z]")
    p = subprocess.Popen(["llvm-dwarfdump", "--debug-info", lib], stdout=subprocess.PIPE, text=True, errors="replace")
    found, cur, pend, top = {}, None, None, None
    def keep():
        if cur and cur[0] and want.match(cur[0]) and cur[1]:
            found.setdefault(cur[0], dict(cur[1]))

    for line in p.stdout:
        if "DW_TAG_enumeration_type" in line:
            keep()  # enums often follow one another directly
            cur, pend, top = [None, []], None, True
            continue
        if cur is None:
            continue
        if "DW_TAG_" in line and "DW_TAG_enumerator" not in line:
            keep()
            cur = None
            continue
        if "DW_TAG_enumerator" in line:
            top = False
        m = re.search(r'DW_AT_name\s+\("([^"]+)"\)', line)
        if m:
            if top and cur[0] is None:
                cur[0] = m.group(1)
            else:
                pend = m.group(1)
        m = re.search(r"DW_AT_const_value\s+\((0x[0-9a-f]+|-?\d+)\)", line)
        if m and pend and not top:
            cur[1].append((int(m.group(1), 0), pend))
            pend = None
    keep()
    p.wait()
    data = {name: {str(k): v for k, v in sorted(vals.items())} for name, vals in sorted(found.items())}
    path = os.path.join(HERE, f"enums-{args.sdk}.json")
    json.dump(data, open(path, "w"), indent=1)
    print(f"{len(data)} command enums -> {os.path.relpath(path)}: " + ", ".join(f"{k}({len(v)})" for k, v in data.items()))


def load_enums(sdk):
    path = os.path.join(HERE, f"enums-{sdk}.json")
    if not os.path.exists(path):
        sys.exit(f"{path} missing: run enums first")
    e = json.load(open(path))
    sets = {int(k): v for k, v in e["CmdSet"].items()}
    per_set = {}
    # CmdSet names (CMD_SET_CAMERA) map to per-set enums (CmdCamera) by name.
    for num, setname in sets.items():
        key = ("Cmd" + setname.replace("CMD_SET_", "").replace("_", "")).lower()
        for cand in e:
            if cand.lower() == key:
                per_set[num] = {int(k): v for k, v in e[cand].items()}
    return sets, per_set


# --- sweep / products --------------------------------------------------------

def probe_identity(sdk, pid):
    trace, out = run_probe(sdk, "probe_readonly", f"sweep-{pid}", {"XU_FAKE_PID": pid}, ["5000"], timeout=25)
    req = packets(trace, "SET_CUR")
    text = "\n".join(out)
    m = re.search(r"^\[probe\] (\d+) device", text, re.M)
    t = re.search(r"productType=(\d+)", text)
    return {"pid": pid, "recognised": bool(m and int(m.group(1)) > 0), "product_type": int(t.group(1)) if t else None,
            "first_request_head": req[0][:12].hex() if req else None}


def sweep(args):
    path = os.path.join(HERE, f"sweep-{args.sdk}.tsv")
    rows = {}
    if os.path.exists(path):
        for line in open(path).read().splitlines()[1:]:
            f = line.split("\t")
            rows[f[0]] = f
    for p in range(int(args.first, 16), int(args.last, 16) + 1):
        r = probe_identity(args.sdk, f"{p:04x}")
        rows[r["pid"]] = [r["pid"], str(int(r["recognised"])), str(r["product_type"] if r["product_type"] is not None else "-"), r["first_request_head"] or "-"]
        if r["recognised"]:
            print(f"  {r['pid']}: product type {r['product_type']}")
    with open(path, "w") as f:
        f.write("pid\trecognised\tproduct_type\tfirst_request_head\n")
        for k in sorted(rows):
            f.write("\t".join(rows[k]) + "\n")
    print(f"sweep {args.first}-{args.last} -> {os.path.relpath(path)}")


def kproducttype(lib):
    """The library's kProductType table: device-info product field -> name.
    Read from .data through its R_X86_64_RELATIVE relocations."""
    data = open(lib, "rb").read()
    sym = subprocess.run(["nm", lib], capture_output=True, text=True).stdout
    m = re.search(r"^([0-9a-f]+) [dD] kProductType$", sym, re.M)
    if not m:
        return {}
    base = int(m.group(1), 16)
    rel = {}
    for line in subprocess.run(["readelf", "-rW", lib], capture_output=True, text=True).stdout.splitlines():
        f = line.split()
        if len(f) >= 4 and f[2] == "R_X86_64_RELATIVE":
            rel[int(f[0], 16)] = int(f[3], 16)
    out, i = {}, 0
    while i < 64:
        addr = base + 8 * i
        if addr in rel:
            s = data[rel[addr]:data.index(b"\0", rel[addr])].decode()
            out[s] = i
        elif i > 0 and addr not in rel and (addr - 8) not in rel and (addr - 16) not in rel:
            break
        i += 1
    return out


def products(args):
    lib = sdk_lib(args.sdk)
    sweep_path = os.path.join(HERE, f"sweep-{args.sdk}.tsv")
    rec = {}
    for line in open(sweep_path).read().splitlines()[1:]:
        pid, ok, ptype, head = line.split("\t")
        rec[pid] = (ok == "1", None if ptype == "-" else int(ptype))
    names = kproducttype(lib)
    firmware = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(FACTORY, "identity", "*.json"))):
        r = json.load(open(path))
        for fs in (r.get("filesystems") or {}).values():
            for mod in fs["gadget_modules"]:
                for uid in mod["usb_ids"]:
                    pid = uid.split(":")[1]
                    entry = {"image": r["image"], "sha256": r["sha256"], "module": mod["path"], "description": mod["modinfo"].get("description")}
                    if entry not in firmware[pid]:
                        firmware[pid].append(entry)
    out = []
    for pid in sorted(set(firmware) | {p for p, (ok, _) in rec.items() if ok}):
        ok, ptype = rec.get(pid, (None, None))
        fw = firmware.get(pid, [])
        prefix = fw[0]["image"].split("_OA_")[0] if fw else None
        out.append({
            "usb_id": f"3564:{pid}",
            "recognised_by": args.sdk if ok else None,
            "product_type": ptype,
            "devinfo_product": names.get(prefix) if prefix else None,
            "devinfo_name": prefix if prefix in names else None,
            "firmware": fw,
        })
    path = os.path.join(HERE, "products.json")
    json.dump({"sdk": args.sdk, "generated": datetime.date.today().isoformat(), "products": out}, open(path, "w"), indent=1)
    print(f"{len(out)} product IDs -> {os.path.relpath(path)} "
          f"({sum(1 for p in out if p['recognised_by'] and p['firmware'])} recognised and confirmed by firmware)")


# --- trace -------------------------------------------------------------------

def camera_sets():
    """The camera's command-set numbers by name, from the firmware's
    route/enum.json as recorded in factory/identity/*.json."""
    out = {}
    for path in sorted(glob.glob(os.path.join(FACTORY, "identity", "*.json"))):
        for fs in (json.load(open(path)).get("filesystems") or {}).values():
            for name, num in ((fs.get("route_enums") or {}).get("CMDSET") or {}).items():
                out.setdefault(name.replace("CMDSET_", "").replace("_", ""), num)
    return out


def set_translation(sets):
    """Library set number -> camera set number, joined by name."""
    cam = camera_sets()
    xl = {}
    for num, name in sets.items():
        key = name.replace("CMD_SET_", "").replace("_", "")
        for cand in (key, key + "R"):  # CMD_SET_ROUTE ~ CMDSET_ROUTER
            if cand in cam:
                xl[num] = cam[cand]
                break
    return xl


def trace(args):
    sets, per_set = load_enums(args.sdk)
    xlate = set_translation(sets)
    if not xlate:
        sys.exit("no camera command-set table in factory/identity; run factory/identity.py first")
    prods = {p["usb_id"].split(":")[1]: p for p in json.load(open(os.path.join(HERE, "products.json")))["products"]}
    pids = args.pids or [pid for pid, p in prods.items() if p["recognised_by"]]
    os.makedirs(os.path.join(HERE, "commands"), exist_ok=True)
    for pid in pids:
        p = prods[pid]
        env = {"XU_FAKE_PID": pid}
        if p["devinfo_product"] is not None:
            env["XU_FAKE_DEVINFO"] = f"0={p['devinfo_product']}"
        env["XU_TRACE_LOG"] = "1"
        cmds, unlogged, set_map = {}, {}, {}
        for probe, pargs in (("probe_collect", ["3", "6000"]), ("probe_collect_varied", ["1", "6000"])):
            tr, _ = run_probe(args.sdk, probe, f"trace-{pid}-{probe}", env, pargs)
            reps = {}
            for d in packets(tr, "GET_CUR"):
                if d[0] == 0xAA:
                    reps.setdefault(d[2], d)
            # One timeline: the shim writes the library's command log lines and
            # the probe's result lines into the trace with timestamps, in order
            # with the packets. A logged command ("sendMsgSync, cmd_id = …;
            # cmd_set = …") waits for the next request in the camera command set
            # its library set translates to (joined by name), and pairs with it.
            # A request that arrives while no logged command waits for its set
            # was sent without a log line, and is recorded as unlogged. Paired
            # commands are labelled with the probe result line that follows
            # them: "initialisation" before the probe's "product=" line, then
            # the getter's name.
            waiting, paired = [], []

            def label(name):
                for cs, ci, q in paired:
                    op = q[10] | q[11] << 8
                    rep = reps.get(q[2])
                    entry = cmds.setdefault(f"{cs}/{ci}", {
                        "libdev_set": sets.get(cs), "libdev_cmd": per_set.get(cs, {}).get(ci),
                        "libdev_ids": [cs, ci], "opcode": f"{op:#06x}", "camera_set": op & 0x3F, "camera_number": op >> 6,
                        "destination": q[9], "request_flags": q[1], "request_header_len": q[4],
                        "request_payload_len": (q[12] | q[13] << 8) if q[4] == 12 and q[1] & 0x40 else 0,
                        "reply_flags": rep[1] if rep else None, "reply_header_len": rep[4] if rep else None,
                        "reply_payload_len": (rep[12] | rep[13] << 8) if rep and rep[4] == 12 else None,
                        "seen_in": [],
                    })
                    if name not in entry["seen_in"]:
                        entry["seen_in"].append(name)
                paired.clear()

            for line in tr:
                if " log " in line:
                    for m in re.finditer(r"cmd_id = (\d+); cmd_set = (\d+)", line):
                        waiting.append((int(m.group(2)), int(m.group(1))))
                    if re.search(r"\[(?:collect|varied)\] product=", line):
                        label("initialisation")
                    m = re.search(r"\[(?:collect|varied)\] r=\d+ (\S+) rc=", line)
                    if m:
                        label(m.group(1))
                    continue
                m = re.search(r" xu .*sel=2 SET_CUR.*data=([0-9a-f]+)", line)
                if not m:
                    continue
                q = bytes.fromhex(m.group(1))
                op = q[10] | q[11] << 8
                match = next((w for w in waiting if xlate.get(w[0], op & 0x3F) == op & 0x3F), None)
                if match is None:
                    unlogged.setdefault(f"{op:#06x}", {"opcode": f"{op:#06x}", "camera_set": op & 0x3F,
                                                      "camera_number": op >> 6, "destination": q[9], "request_flags": q[1]})
                    continue
                waiting.remove(match)
                set_map.setdefault(match[0], op & 0x3F)
                paired.append((match[0], match[1], q))
        rec = {"usb_id": p["usb_id"], "sdk": args.sdk, "product_type": p["product_type"],
               "identity_from": sorted({f["image"] for f in p["firmware"]}) or ["recognised by the SDK only; no firmware declares this ID"],
               "grade": "vendor-oracle" if pid != "fefb" else "hardware-verified transport (attached Meet 2)",
               "library_to_camera_set": {str(k): v for k, v in sorted(set_map.items())},
               "set_translation_from_names": {str(k): v for k, v in sorted(xlate.items())},
               "commands": [cmds[k] for k in sorted(cmds, key=lambda k: tuple(map(int, k.split("/"))))],
               "unlogged_requests": sorted(unlogged.values(), key=lambda u: u["opcode"])}
        path = os.path.join(HERE, "commands", f"{pid}.json")
        json.dump(rec, open(path, "w"), indent=1)
        print(f"  {pid}: {len(cmds)} distinct commands -> {os.path.relpath(path)}")


def run_all(args):
    build(args)
    enums(args)
    for a, b in SWEEP_RANGES:
        args.first, args.last = a, b
        sweep(args)
    products(args)
    args.pids = []
    trace(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sdk", default="libdev_v2.1.0_8")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(func=build)
    sub.add_parser("enums").set_defaults(func=enums)
    s = sub.add_parser("sweep"); s.add_argument("first"); s.add_argument("last"); s.set_defaults(func=sweep)
    sub.add_parser("products").set_defaults(func=products)
    t = sub.add_parser("trace"); t.add_argument("pids", nargs="*"); t.set_defaults(func=trace)
    sub.add_parser("run").set_defaults(func=run_all)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
