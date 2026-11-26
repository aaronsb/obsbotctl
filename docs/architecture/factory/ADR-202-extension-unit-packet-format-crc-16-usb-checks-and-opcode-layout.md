---
contract: adr/v1
kind: evidence
capability: protocol
status: proposed
date: 2026-11-25
deciders:
  - aaronsb
related: []
---

# ADR-202: Extension-unit packet format, CRC-16/USB checks and opcode layout

## Method

The pinned vendor library `libdev_v2.1.0_8` ran read-only getter probes against an attached Meet 2 (firmware 4.4.2.2) with an `LD_PRELOAD` shim, `factory/oracle/xu_trace.c`, that logs every UVC extension-unit query and every other ioctl on `/dev/video*`. The library's command enums were read from its debug information. Nothing was decompiled or disassembled. The packet fields were first worked out by comparing request and reply pairs, and the check bytes by their linearity across about 200 distinct packets; that gave a Modbus CRC-16 with a different starting value per length. The CRC-16/USB parameters published by [Domatix/obsbot-control #22](https://github.com/Domatix/obsbot-control/issues/22) and [#23](https://github.com/Domatix/obsbot-control/pull/23) and by [nofuturekid/obsbot4linux #61](https://github.com/nofuturekid/obsbot4linux/issues/61) explain both checks with one rule, and this project verified them on its own traces (fact 5); the per-length starting values were the effect of the final inversion.

```bash
python3 -I factory/oracle/oracle.py run    # build, enums, sweep, products, trace; needs the Meet 2 attached
python3 -I - <<'EOF'                       # check fact 5 over every raw trace
import glob, os, re
def crc(b, c=0xFFFF):
    for x in b:
        c ^= x
        for _ in range(8): c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c ^ 0xFFFF
assert crc(b"123456789") == 0xB4C8
pk = {bytes.fromhex(m) for f in glob.glob(os.path.expanduser("~/.cache/libobsbot/factory/oracle/traces/*/*.log"))
      for m in re.findall(r" xu .*sel=2 [SG]ET_CUR .*data=([0-9a-f]+)", open(f, errors="replace").read())}
pk = [p for p in pk if p[0] == 0xAA and p[1]]             # flags 0 is the fallback request (ADR-203)
h = sum(crc(p[:6] + b"\0\0" + p[8:p[4]]) == p[6] | p[7] << 8 for p in pk)
dp = [p for p in pk if p[4] == 12 and 0 < (p[12] | p[13] << 8) <= 44]
d = sum(crc(p[12:14] + b"\0\0" + p[16:16 + (p[12] | p[13] << 8)]) == p[14] | p[15] << 8 for p in dp)
print(f"header {h}/{len(pk)}, data block {d}/{len(dp)}")
EOF
```

## Facts

1. **Finding the unit.** The library sends `GET_CUR` on selector 6 to units 0, 1 and 2. Units 0 and 1 fail with `ENOENT` and unit 2 answers, so it finds OBSBOT's unit by probing.
2. **Status block.** Selector 6 returns a 60-byte block, polled every 2 s. The library's `cameraStatus()` causes no traffic and reads the cached block.
3. **Commands.** A command is a 60-byte `SET_CUR` on unit 2, selector 2. The reply is a 60-byte `GET_CUR` on the same selector, about 40 ms later.
4. **Packet layout** (byte offsets; multi-byte fields little-endian):

   | Offset | Field |
   |---|---|
   | 0 | `aa`, start marker |
   | 1 | flags: `01` on a getter request and `29` on its reply; the traces also hold `21`, `25` and `41` with 12-byte headers, and `89` and `a9` with 16-byte headers |
   | 2 | sequence number, echoed in the reply |
   | 4–5 | header length: 12, or 16 for the camera module's replies |
   | 6–7 | header check (fact 5) |
   | 8, 9 | source and destination address, numbered as the firmware's `DEVICE` table (ADR-201): `0a` SDK, `0d` UPGRADE, `02` CAMERA |
   | 10–11 | opcode (fact 7) |
   | 12–13 | payload length |
   | 14–15 | data-block check (fact 5) |
   | 16… | payload |

   Payloads decode directly: the firmware-version reply is `02 02 04 04` (4.4.2.2, low byte first) and the serial-number reply is the serial in ASCII.
5. **Both checks are CRC-16/USB**: reflected polynomial 0x8005 (table value 0xA001), starting value 0xFFFF, result inverted; its check value for `"123456789"` is 0xB4C8. Each check is stored low byte first and computed with its own field zeroed. The header check covers bytes 0 to header length − 1. The data-block check covers bytes 12 to 16 + payload length − 1. Over the oracle's raw traces the snippet above prints `header 253/253, data block 62/62`. The camera module's 16-byte replies with flags `89` carry `00 02 fd ff` in bytes 12–15 whatever their payload (82 distinct replies), so they have no data-block check.
6. **Not a signature.** The `token` the library logs at startup changes every run, but the identical first request carries the same check bytes every run. `libdev`'s debug information declares `calc_crc16(uint16_t crc, const void *buf, size_t len)`, and the library holds the split CRC tables `crc16_high_tab` and `crc16_low_tab`.
7. **Opcode.** Bytes 10–11 hold `(camera command number << 6) | camera command set`. The low 6 bits are the firmware's `CMDSET` number (ADR-201: CAMERA=2, UPGRADE=8, SYSMG=13, PRIMARY_BLE=14), and the destination address agrees with it. All 221 commands in `factory/oracle/commands/*.json` satisfy the rule.
8. **Two numberings.** `libdev` numbers command sets and commands its own way and translates. Its debug information names `CmdSet` (16 values; CMD_SET_CAMERA=1, CMD_SET_UPGRADE=5) and per-set enums such as `CmdCamera` (194 values) and `CmdAi` (134), recorded in `factory/oracle/enums-libdev_v2.1.0_8.json`. No table of camera command numbers exists in the library's data sections, so the mapping from a `libdev` name to a camera number comes from traces: each traced call gives one entry, recorded per product in `factory/oracle/commands/<pid>.json`.
9. **Other traffic.** The image getters (brightness, contrast, hue, saturation) send no command packet and issue `VIDIOC_G_CTRL` instead, so they use standard V4L2 controls. With mDNS scanning disabled, the library still opens 26 sockets for mDNS queries and starts a Bluetooth thread.

## Hypotheses

- A setter's camera command number is its getter's plus one. Consecutive getter pairs (ISO limit, AE lock, face AE) land two apart (133, 135, 137), but mirror/flip (96) and exposure mode (144) break the odd/even pattern; one traced setter settles it.
- The body of a request to the CAMERA module is one of the protobuf messages in ADR-201.
