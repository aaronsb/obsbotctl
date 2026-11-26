---
contract: adr/v1
kind: evidence
capability: catalog
status: accepted
date: 2026-11-25
deciders:
  - aaronsb
related: []
---

# ADR-204: USB product IDs the vendor library recognises, against the firmware

## Method

`factory/oracle/oracle.py sweep` runs the read-only probe once per USB product ID, with the trace shim claiming that ID (ADR-203), against the attached Meet 2. It records whether a device survives initialisation, the `productType()` the library reports and the first request it sends, in `factory/oracle/sweep-<sdk>.tsv`. `oracle.py products` joins the sweep with the USB IDs that `factory/identity.py` reads from the gadget modules of the 28 pinned firmware images, into `factory/oracle/products.json`. Nothing was decompiled or disassembled.

```bash
python3 -I factory/identity.py                          # factory/identity/<image>.json
python3 -I factory/oracle/oracle.py sweep fe00 feff
python3 -I factory/oracle/oracle.py sweep ff00 ff0f
python3 -I factory/oracle/oracle.py products            # factory/oracle/products.json
python3 -I factory/oracle/oracle.py --sdk libdev_v2.1.0_7 build
for p in fef0 fef2 fef3 fef4 ff08 ff09; do python3 -I factory/oracle/oracle.py --sdk libdev_v2.1.0_7 sweep $p $p; done
```

## Facts

1. **`libdev_v2.1.0_8` recognises 13 product IDs** in `fe00`–`feff` and `ff00`–`ff0f`. Each initialises in the Meet 2's dialect (first request `aa 01 00 00 0c 00 91 5c 0a 0d 08 18`) and reports a product type. Every other ID in those ranges gets the fallback request `aa 00 0c 12 00 00 67 f5 00 e8 80 60` (ADR-203) and is dropped.

   | USB ID | `productType()` | SDK enum name | Firmware whose `remo_multi_usb.ko` declares the ID |
   |---|---|---|---|
   | `fef6` | 4 | TailAir | Tail Air 5.0.18.1 (which also declares `fef8`) |
   | `fef8` | 2 | Tiny2 | Tiny 2 6.0.13.1 |
   | `fef9` | 3 | Tiny2Lite | Tiny 2 Lite 6.2.8.1 |
   | `fefa` | 8 | HDMIBox | HDMI box 8.0.5.1 |
   | `fefb` | 10 | Meet2 | Meet 2 4.4.7.1; also the attached camera |
   | `fefc` | 11 | Tail2 | none (the Tail 2 images use another container format) |
   | `fefd` | 16 | Tail2S | none (the Tail 2S images use another container format) |
   | `fefe` | 13 | MeetSE | Meet SE 4.6.5.1 |
   | `feff` | 12 | TinySE | Tiny SE 6.4.4.1 |
   | `ff01` | 9 | NDIBox | none (the NDI box image unpacks, but no module sets an OBSBOT USB ID) |
   | `ff02` | 18 | Tiny3 | Tiny 3 6.6.11.1 |
   | `ff04` | 19 | Tiny3Lite | Tiny 3 Lite 6.5.11.1 |
   | `ff06` | 25 | (unnamed in the header; `kProductType` 25 is `Obsbot_meetflip`) | Meet Flip 4.5.5.1 |

2. **Firmware IDs the library does not recognise:** `fef0` and `fef4` (the original Tiny, 1.0.6.2 and 1.2.6.2), `fef2` and `fef3` (the Meet, 4.2.6.1 and 4.0.6.1), `ff08` (Meet 3 1.8.19.1) and `ff09` (Meet SE 2 1.4.13.1).
3. **The older SDK recognises none of these six either:** `libdev_v2.1.0_7` sends the fallback request for each.
4. **Extension units.** Every image that yields an ID declares OBSBOT's unit `9a1e7291-6843-4683-6d92-39bc7906ee49`. The four unrecognised original Tiny and Meet images also declare a second unit, `a29e7641-de04-47e3-8b2b-f4341aff003b`; no recognised image does.

## Hypotheses

- The Meet 3 and Meet SE 2 are newer than both SDKs, as the Meet Flip was newer than `libdev_v2.1.0_7`, and a later SDK would recognise them.
- The fallback request is the protocol of the original Tiny and Meet, whose firmware carries the second unit `a29e7641…`. The attached Meet 2 does not answer it, so this cannot be tested here.
- The Tail Air's second ID, `fef8`, the same as the Tiny 2's, is a mode or a reused ID; its gadget module would show under which condition each ID is set.
