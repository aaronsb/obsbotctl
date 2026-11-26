#!/usr/bin/env python3
"""Record what OBSBOT's vendor library sends to each camera it supports.

The oracle runs read-only probes against the vendor library (libdev) with an
LD_PRELOAD shim (xu_trace.c) between the library and the attached camera.
The shim records every UVC extension-unit request and reply, and can make
the library believe it has a different product: it substitutes the USB
product ID the library reads from /sys, and rewrites the product field of
the device-information reply (recomputing its CRC-16/USB checks). The
attached camera only ever receives requests the library sends itself. The
trace probes call getters only; the setters probe writes, under its own
identity, and restores every value it changes.

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
  setters            WRITES TO THE ATTACHED CAMERA. Refuses if another
                     process holds it. Calls image and control setters the
                     library can read back (probe_setters), each with the
                     value read or a neighbour then the value read, and
                     writes the "setters" section of commands/<pid>.json:
                     each setter's command, payload bytes and lengths, its
                     getter, V4L2 controls and other requests it sent, and
                     the final read-back of every setting. Payloads that
                     hold bytes of the camera's identity replies are refused.
                     --replay PID re-reads the last recorded run instead.
  run             build, enums, sweep fe00-feff and ff00-ff0f, products,
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
PROBES = ("probe_readonly", "probe_collect", "probe_collect_varied", "probe_setters")
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


def timeline(tr, xlate):
    """Walk one trace in order and pair each logged library command with the
    request it sent.

    The shim writes the library's command log lines and the probe's result
    lines into the trace with timestamps, in order with the packets. A logged
    command ("sendMsgSync, cmd_id = …; cmd_set = …") waits for the next
    request in the camera command set its library set translates to (joined
    by name), and pairs with it. A request that arrives while no logged
    command waits for its set was sent without a log line.

    Yields ("log", line) for each captured log line, after queueing the
    commands it announces; ("pair", (lib_set, lib_cmd), request) when a
    selector-2 request pairs; ("unlogged", request) when none waits for it;
    ("other", line) for every other trace line."""
    waiting = []
    for line in tr:
        if " log " in line:
            for m in re.finditer(r"cmd_id = (\d+); cmd_set = (\d+)", line):
                waiting.append((int(m.group(2)), int(m.group(1))))
            yield "log", line
            continue
        m = re.search(r" xu .*sel=2 SET_CUR.*data=([0-9a-f]+)", line)
        if not m:
            yield "other", line
            continue
        q = bytes.fromhex(m.group(1))
        op = q[10] | q[11] << 8
        match = next((w for w in waiting if xlate.get(w[0], op & 0x3F) == op & 0x3F), None)
        if match is None:
            yield "unlogged", q
            continue
        waiting.remove(match)
        yield "pair", match, q


def opcode_of(q):
    return f"{q[10] | q[11] << 8:#06x}"


def payload_len(q):
    """A packet's payload length. A 12-byte-header packet with flag bit 0x20
    or 0x40 carries a payload section: its length at bytes 12-13 and a
    CRC-16/USB at 14-15 over bytes 12..16+len-1 (14-15 zeroed); every such
    packet in the recorded traces passes that check. Without either bit
    (plain 0x01 requests) bytes 12-15 are stale, and the length is 0."""
    return (q[12] | q[13] << 8) if q[4] == 12 and q[1] & 0x60 else 0


def command_entry(sets, per_set, cs, ci, q, rep):
    """A command's names, opcode and lengths, from its request and reply."""
    op = q[10] | q[11] << 8
    return {
        "libdev_set": sets.get(cs), "libdev_cmd": per_set.get(cs, {}).get(ci),
        "libdev_ids": [cs, ci], "opcode": f"{op:#06x}", "camera_set": op & 0x3F, "camera_number": op >> 6,
        "destination": q[9], "request_flags": q[1], "request_header_len": q[4],
        "request_payload_len": payload_len(q),
        "reply_flags": rep[1] if rep else None, "reply_header_len": rep[4] if rep else None,
        "reply_payload_len": payload_len(rep) if rep and rep[4] == 12 else None,
        "seen_in": [],
    }


def unlogged_entry(q):
    op = q[10] | q[11] << 8
    return {"opcode": f"{op:#06x}", "camera_set": op & 0x3F, "camera_number": op >> 6, "destination": q[9],
            "request_flags": q[1]}


def write_commands(pid, rec):
    """Write commands/<pid>.json. Its "setters" section is recorded only by
    the setters command, so a rewrite without one keeps the file's."""
    path = os.path.join(HERE, "commands", f"{pid}.json")
    if "setters" not in rec and os.path.exists(path):
        old = json.load(open(path))
        if "setters" in old:
            rec["setters"] = old["setters"]
    json.dump(rec, open(path, "w"), indent=1)
    return path


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
            # Paired commands are labelled with the probe result line that
            # follows them: "initialisation" before the probe's "product="
            # line, then the getter's name.
            paired = []

            def label(name):
                for cs, ci, q in paired:
                    entry = cmds.setdefault(f"{cs}/{ci}", command_entry(sets, per_set, cs, ci, q, reps.get(q[2])))
                    if name not in entry["seen_in"]:
                        entry["seen_in"].append(name)
                paired.clear()

            for ev in timeline(tr, xlate):
                if ev[0] == "log":
                    if re.search(r"\[(?:collect|varied)\] product=", ev[1]):
                        label("initialisation")
                    m = re.search(r"\[(?:collect|varied)\] r=\d+ (\S+) rc=", ev[1])
                    if m:
                        label(m.group(1))
                elif ev[0] == "unlogged":
                    unlogged.setdefault(opcode_of(ev[1]), unlogged_entry(ev[1]))
                elif ev[0] == "pair":
                    (cs, ci), q = ev[1], ev[2]
                    set_map.setdefault(cs, q[10] & 0x3F)
                    paired.append((cs, ci, q))
        rec = {"usb_id": p["usb_id"], "sdk": args.sdk, "product_type": p["product_type"],
               "identity_from": sorted({f["image"] for f in p["firmware"]}) or ["recognised by the SDK only; no firmware declares this ID"],
               "grade": "vendor-oracle" if pid != "fefb" else "hardware-verified transport (attached Meet 2)",
               "library_to_camera_set": {str(k): v for k, v in sorted(set_map.items())},
               "set_translation_from_names": {str(k): v for k, v in sorted(xlate.items())},
               "commands": [cmds[k] for k in sorted(cmds, key=lambda k: tuple(map(int, k.split("/"))))],
               "unlogged_requests": sorted(unlogged.values(), key=lambda u: u["opcode"])}
        path = write_commands(pid, rec)
        print(f"  {pid}: {len(cmds)} distinct commands -> {os.path.relpath(path)}")


# --- setters -----------------------------------------------------------------

V4L2_S_CTRL, V4L2_S_EXT_CTRLS = 0xC008561C, 0xC0205648
V4L2_CONTROLS = {0x00980900: "brightness", 0x00980901: "contrast", 0x00980902: "saturation", 0x00980903: "hue",
                 0x0098090C: "white_balance_automatic", 0x00980913: "gain", 0x00980918: "power_line_frequency",
                 0x0098091A: "white_balance_temperature", 0x0098091B: "sharpness",
                 0x0098091C: "backlight_compensation", 0x009A0901: "auto_exposure",
                 0x009A0902: "exposure_time_absolute", 0x009A0908: "pan_absolute", 0x009A0909: "tilt_absolute",
                 0x009A090A: "focus_absolute", 0x009A090C: "focus_automatic_continuous", 0x009A090D: "zoom_absolute"}


def attached_pid():
    """The USB product ID of the attached OBSBOT camera (vendor 3564), from sysfs."""
    for dev in sorted(glob.glob("/sys/class/video4linux/video*")):
        usb = os.path.realpath(os.path.join(dev, "device", ".."))
        try:
            vid = open(os.path.join(usb, "idVendor")).read().strip()
            pid = open(os.path.join(usb, "idProduct")).read().strip()
        except OSError:
            continue
        if vid == "3564":
            return pid
    sys.exit("no OBSBOT camera (USB vendor 3564) attached")


def camera_in_use():
    nodes = sorted(glob.glob("/dev/video*"))
    r = subprocess.run(["fuser", *nodes], capture_output=True, text=True) if nodes else None
    return r.stdout.strip() if r and r.stdout.strip() else None


def secret_windows(tr):
    """Every 4-byte run, with at least three distinct bytes, of the replies
    that carry the camera's identity (UUID, serial, device info). A recorded
    payload must not contain one."""
    out = set()
    for d in packets(tr, "GET_CUR"):
        if d[0] == 0xAA and opcode_of(d) in ("0x1808", "0x18c8", "0x1948"):
            p = d[16:16 + (d[12] | d[13] << 8)]
            out |= {p[i:i + 4] for i in range(len(p) - 3) if len(set(p[i:i + 4])) >= 3}
    return out


def setter_windows(tr, xlate):
    """Split a probe_setters trace into its setter calls.

    Each call sits in a window the probe marks: "[setter] write name=N
    call=F value=V" before it, "[setter] sent name=N rc=R" after, and the
    window holds that one library call. The library logs no "sendMsgSync"
    line for a setter (on the Meet 2 none did), so a selector-2 request in
    a window is the setter's whether or not a logged command claims it; a
    claimed one keeps its library IDs. V4L2 control sets and requests on
    other selectors in the window are the setter's too, and so is a reply
    the library reads before the window closes (the Meet 2's setters read
    none). The read-back between the first window of a setting and its
    result line ("[setter] name=N before=… after=…") is N's getter: the
    logged requests and the V4L2 controls it reads.

    Returns the windows (dicts) and {setting: {"requests": [paired request
    {"cs", "ci", "q"}, …], "v4l2": [control id, …]}}."""
    windows, getter_of, cur, done = [], {}, None, None
    awaiting = {}  # sequence byte -> request in the open window still without its reply
    for ev in timeline(tr, xlate):
        if ev[0] == "log":
            m = re.search(r"\[setter\] write name=(\S+) call=(\S+) value=(-?\d+)", ev[1])
            if m:
                awaiting.clear()
                cur = {"name": m.group(1), "setting": m.group(1).split(".")[0], "call": m.group(2),
                       "value": int(m.group(3)), "requests": [], "v4l2": [], "other_xu": []}
            m = re.search(r"\[setter\] sent name=(\S+) rc=(-?\d+)", ev[1])
            if m and cur:
                cur["rc"] = int(m.group(2))
                windows.append(cur)
                done, cur = cur, None
                awaiting.clear()
                if done["setting"] in getter_of:
                    done = None  # a later write of the same setting: its getter is known
                else:
                    getter_of[done["setting"]] = {"requests": [], "v4l2": []}
            m = re.search(r"\[setter\] name=(\S+) before=(\S+) wrote=-?\d+ after=(\S+) rc=", ev[1])
            if m:
                for w in windows[-1:]:
                    if w["name"] == m.group(1):
                        w["before"], w["after"] = m.group(2), m.group(3)
                done = None
        elif ev[0] in ("pair", "unlogged"):
            lib, q = (ev[1], ev[2]) if ev[0] == "pair" else ((None, None), ev[1])
            r = {"cs": lib[0], "ci": lib[1], "q": q, "rep": None}
            if cur:
                cur["requests"].append(r)
                awaiting[q[2]] = r
            elif done and ev[0] == "pair":
                getter_of[done["setting"]]["requests"].append(r)
        else:
            m = re.search(r" ioctl .*req=0x([0-9a-f]+) ret=-?\d+ errno=\d+((?: ctrl=0x[0-9a-f]+:\S+)+)", ev[1])
            if m:
                ctrls = [(int(i, 16), v) for i, v in re.findall(r"ctrl=0x([0-9a-f]+):(\S+)", m.group(2))]
                if cur and int(m.group(1), 16) in (V4L2_S_CTRL, V4L2_S_EXT_CTRLS):
                    cur["v4l2"].extend(ctrls)
                elif done and not cur:
                    seen = getter_of[done["setting"]]["v4l2"]
                    seen.extend(c for c, _ in ctrls if c not in seen)
                continue
            m = re.search(r" xu .*sel=(\d+) (SET_CUR|GET_CUR) size=(\d+).*data=([0-9a-f]+)", ev[1])
            if not m:
                continue
            sel, query, data = int(m.group(1)), m.group(2), bytes.fromhex(m.group(4))
            if sel != 2 and query == "SET_CUR" and cur:
                cur["other_xu"].append((sel, int(m.group(3)), data))
            elif sel == 2 and query == "GET_CUR" and data[0] == 0xAA and data[2] in awaiting:
                awaiting.pop(data[2])["rep"] = data  # the first reply after the request
    return windows, getter_of


def setters(args):
    """Call the vendor setters on the attached camera (probe_setters), pair
    each with what it sent, and write the "setters" section of
    commands/<pid>.json. With --replay PID, re-read that product's last
    recorded setters trace instead; nothing is sent to a camera."""
    sets, per_set = load_enums(args.sdk)
    xlate = set_translation(sets)
    if args.replay:
        pid = args.replay
        trace_path = os.path.join(WORK, "traces", args.sdk, f"setters-{pid}.log")
        if not os.path.exists(trace_path):
            sys.exit(f"{trace_path} missing: run setters with the camera attached first")
        tr = open(trace_path).read().splitlines()
        out = open(trace_path + ".stdout").read().splitlines()
    else:
        held = camera_in_use()
        if held:
            sys.exit(f"the camera is in use (fuser: {held}); not opening it")
        pid = attached_pid()
    path = os.path.join(HERE, "commands", f"{pid}.json")
    if not os.path.exists(path):
        sys.exit(f"{path} missing: run trace {pid} first")
    if not args.replay:
        tr, out = run_probe(args.sdk, "probe_setters", f"setters-{pid}", {"XU_TRACE_LOG": "1"}, ["6000"], timeout=600)
    text = "\n".join(out)
    if not re.search(r"^\[setter\] product=", text, re.M):
        sys.exit("probe_setters found no device:\n" + text[-2000:])
    windows, getter_of = setter_windows(tr, xlate)
    rec = json.load(open(path))
    rec["setters"] = setter_section(windows, getter_of, secret_windows(tr), sets, per_set, text, pid)
    write_commands(pid, rec)
    st = rec["setters"]
    print(f"  {pid}: {len(st['commands'])} XU setters, {len(st['v4l2'])} V4L2 setters, "
          f"{len(st['other_requests'])} other requests, {len(st['no_request_seen'])} calls sent nothing "
          f"-> {os.path.relpath(path)}; restored all: {st['restored']['all']}")


def describe_getter(g, per_set):
    """The getter's first logged command, if any, and the V4L2 controls it read."""
    if not g or not (g["requests"] or g["v4l2"]):
        return None
    out = {}
    if g["requests"]:
        r = g["requests"][0]
        out = {"libdev_cmd": per_set.get(r["cs"], {}).get(r["ci"]), "opcode": opcode_of(r["q"]),
               "camera_number": (r["q"][10] | r["q"][11] << 8) >> 6}
    if g["v4l2"]:
        out["v4l2_controls"] = [f"{c:#010x}" for c in g["v4l2"]]
    return out


def setter_section(windows, getter_of, secrets, sets, per_set, text, pid):
    """The "setters" section of commands/<pid>.json, from the setter windows
    and the probe's result lines. Payloads are refused if they hold any run
    of the identity replies' bytes.

    Selector-2 setters are keyed by opcode; their library IDs are null when
    the library logged nothing for them, and "libdev_cmd_from_getter_name"
    then gives the library's name for the getter's CAM_GET_ with SET for
    GET, where the library has one (inferred, not observed). Null reply
    fields mean the library read no reply. Requests on other selectors keep
    all their data bytes."""
    def payload(b):
        if any(x in b for x in secrets):
            sys.exit("a setter payload holds bytes of the camera's identity; not recording it")
        return b.hex()

    cmds, v4l2, other, silent = {}, {}, {}, []
    for w in windows:
        g = getter_of.get(w["setting"])
        getter = describe_getter(g, per_set)
        write = {"setting": w["name"], "value": w["value"], "rc": w["rc"], "before": w.get("before"),
                 "after": w.get("after")}
        for r in w["requests"]:
            q, n = r["q"], payload_len(r["q"])
            e = cmds.get(opcode_of(q))
            if e is None:
                e = cmds[opcode_of(q)] = dict(command_entry(sets, per_set, r["cs"], r["ci"], q, r["rep"]),
                                              logged=r["cs"] is not None, sdk_calls=[], getter=getter, writes=[])
                if getter and getter.get("libdev_cmd"):
                    want = getter["libdev_cmd"].replace("_GET_", "_SET_", 1)
                    gset = g["requests"][0]["cs"]
                    e["libdev_cmd_from_getter_name"] = want if want in per_set.get(gset, {}).values() else None
            if w["call"] not in e["sdk_calls"]:
                e["sdk_calls"].append(w["call"])
            if w["setting"] not in e["seen_in"]:
                e["seen_in"].append(w["setting"])
            e["writes"].append(dict(write, payload=payload(q[16:16 + n]), payload_len=n))
        for cid, val in w["v4l2"]:
            e = v4l2.setdefault((w["call"], cid), {"sdk_call": w["call"], "setting": w["setting"],
                                                   "v4l2_control": f"{cid:#010x}", "v4l2_name": V4L2_CONTROLS.get(cid),
                                                   "getter": getter, "writes": []})
            e["writes"].append(dict(write, control_value=int(val) if re.fullmatch(r"-?\d+", val) else val))
        for sel, size, data in w["other_xu"]:
            e = other.setdefault((w["call"], sel), {"sdk_call": w["call"], "setting": w["setting"], "selector": sel,
                                                    "size": size, "getter": getter, "writes": []})
            e["writes"].append(dict(write, data=payload(data)))
        if not (w["requests"] or w["v4l2"] or w["other_xu"]) and w["call"] not in silent:
            silent.append(w["call"])
    for e in cmds.values():
        g = e["getter"]
        e["getter_plus_one"] = e["camera_number"] == g["camera_number"] + 1 if g and "camera_number" in g else None

    finals = {m.group(1): {"start": m.group(2), "now": m.group(3), "ok": m.group(4) == "1"}
              for m in re.finditer(r"^\[setter\] final name=(\S+) start=(\S+) now=(\S+) ok=(\d)", text, re.M)}
    restored = re.search(r"^\[setter\] restored all=(\d)", text, re.M)
    version = re.search(r"^\[setter\] product=\d+ version=(\S+)", text, re.M)
    return {
        "evidence": "observed-on-device",
        "observed_on": f"3564:{pid}, the attached camera, only; no other product is observed",
        "firmware_version": version.group(1) if version else None,
        "recorded": datetime.date.today().isoformat(),
        "method": "probe_setters: read each setting, write the value read (or a neighbour, then the value read "
                  "again), read back; every setting is read again at the end",
        "restored": {"all": bool(restored and restored.group(1) == "1"), "settings": finals},
        "skipped": [{"setting": n, "why": why} for n, why in re.findall(r"^\[setter\] skip name=(\S+) (.*)$", text, re.M)],
        "commands": sorted(cmds.values(), key=lambda e: (e["camera_set"], e["camera_number"])),
        "v4l2": sorted(v4l2.values(), key=lambda e: e["v4l2_control"]),
        "other_requests": sorted(other.values(), key=lambda e: (e["selector"], e["sdk_call"])),
        "no_request_seen": silent,
    }


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
    s = sub.add_parser("setters"); s.add_argument("--replay", metavar="PID"); s.set_defaults(func=setters)
    sub.add_parser("run").set_defaults(func=run_all)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
