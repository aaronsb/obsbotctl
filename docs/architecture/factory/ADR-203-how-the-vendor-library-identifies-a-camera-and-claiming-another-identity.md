---
contract: adr/v1
kind: evidence
capability: verification
status: accepted
date: 2026-11-25
deciders:
  - aaronsb
related: []
---

# ADR-203: How the vendor library identifies a camera, and claiming another identity

## Method

The trace shim `factory/oracle/xu_trace.c` sits between the pinned vendor library `libdev_v2.1.0_8` and the attached Meet 2 (firmware 4.4.2.2). Besides logging, it can rewrite bytes of the device-information reply and recompute its CRC-16/USB checks (ADR-202), log the library's reads of `/sys`, and substitute the USB product ID the library reads there. The library's product table was read through its relocations, and its identity types from its debug information. The read-only getter probe ran under each change. Nothing was decompiled or disassembled.

```bash
python3 -I factory/oracle/oracle.py build
B=~/.cache/libobsbot/factory/oracle/bin/libdev_v2.1.0_8 T=~/.cache/libobsbot/factory/oracle
XU_FAKE_DEVINFO="0=2,2=2" XU_TRACE_FILE=$T/devinfo.log LD_PRELOAD=$B/xu_trace.so $B/probe_readonly 6000
XU_TRACE_SYSFS=1 XU_TRACE_FILE=$T/sysfs.log LD_PRELOAD=$B/xu_trace.so $B/probe_readonly 6000
grep -c 'fopen.*idProduct' $T/sysfs.log
nm ~/.local/share/libobsbot/sdk/libdev_v2.1.0_8/lib/libdev.so.1.0.0 | grep kProductType   # products reads it
python3 -I factory/oracle/oracle.py sweep fefb fefb    # control: the Meet 2's own ID
python3 -I factory/oracle/oracle.py sweep fef8 fef8    # the Tiny 2's ID, from its firmware
```

## Facts

1. **The device-information reply is a record of identity fields.** The library builds its "device info is: …" log line from the payload of `UG_GET_DEV_INFO` (opcode `0x1948`), and accepts a rewritten reply:

   | Byte | Meet 2 | Effect of a change |
   |---|---|---|
   | 0 | 10 | product name, through `kProductType` (2 → `Obsbot_tiny_2P`) |
   | 2 | 10 | chip name (10 → `PW203`, 2 → `Hi3516DV300`) |
   | 3 | 2 | build type (2 → `debug`, 0 → `release`) |
   | 4–7 | `02 02 04 04` | firmware version 4.4.2.2 |
   | 26–31 | the device ID | also carried in the UUID reply |

2. **`kProductType`** (declared in `libdev/dev/dev-info.hpp:60`) maps byte 0 to a name: 0 `Obsbot_tail_3P`, 1 `Obsbot_tail_2P`, 2 `Obsbot_tiny_2P`, 3 `Obsbot_me_1P`, 4 `Obsbot_meet`, 5 `Obsbot_tailair`, 6 `Obsbot_tiny2`, 7 `Obsbot_hdmibox`, 8 `Obsbot_ty2lite`, 9 `Obsbot_ndibox`, 10 `Obsbot_meet2`, 11 `Obsbot_tail2`, 12 `Obsbot_tinyse`, 13 `Obsbot_meetse`, 16 `Obsbot_tail2s`, 18 `Obsbot_tiny3`, 19 `Obsbot_tiny3lite`, 25 `Obsbot_meetflip`; the other indices up to 26 are NULL. Most of these names are also the product names in the firmware image headers (`factory/identity/*.json`); the numbers differ from the SDK header's `ObsbotProductType`.
3. **`productType()` comes from the USB IDs, not the record.** It stayed 10 under every device-information rewrite. The debug information declares `DevicePrivate::getProductTypeById(DeviceId const&)`, where `DeviceId` holds `v_device_path_`, `vid_`, `pid_` and `busID_`.
4. **The USB IDs are read with `fopen`.** One probe run logged 204 `fopen`s each of `/sys/bus/usb/devices/*/idVendor` and `idProduct`, 15 each of `bDeviceClass` and `bDeviceSubClass`, and 3 of `/sys/class/video4linux/videoN/device/modalias`; none went through `open` or `openat`. The shim's `fopen` hook (`XU_FAKE_PID`) is where an ID is substituted.
5. **A claimed identity initialises normally.** With the substitution, the library reports the claimed product and initialises it in the same dialect as the Meet 2: the control `fefb` gives product type 10, `fef8` (from the Tiny 2 firmware 6.0.13.1) gives 2 and `fefe` (from the Meet SE firmware 4.6.5.1) gives 13. ADR-204 extends this to every ID.
6. **Fallback when no product ID is readable.** The library then sends `UG_GET_UUID` as `aa 00 0c 12 00 00 67 f5 00 e8 80 60 …`, which the Meet 2 does not answer, logs `error occurred in getDevUuidR, ret_val = -3` and `uvc device init failed`, and drops the device.
7. **Correction (2026-11-25).** An earlier reading claimed that the product ID selects an older protocol dialect for the Tiny 2 and Meet SE. That was an artefact of the shim: its first substitution returned an `fmemopen()` stream, which has no file descriptor, so the library could not read the ID at all and took the fallback of fact 6. A control run claiming the Meet 2's own ID reproduced the failure and exposed the fault; the shim now returns a real file.

## Hypotheses

- The fallback request of fact 6 is the protocol for products the library cannot identify. One such request does not fit CRC-16/USB at any 2-byte position in its first 18 bytes. The Meet Flip failure reported in [obsbot-camera-control PR #71](https://github.com/aaronsb/obsbot-camera-control/pull/71), on an SDK older than the Meet Flip, looks the same.
