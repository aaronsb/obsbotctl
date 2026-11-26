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

# ADR-200: The camera side of OBSBOT's UVC extension unit

## Method

The attached Meet 2's USB descriptors were read with `lsusb`. The Meet 2 firmware image v4.4.7.1 was unpacked by `factory/identity.py`, which records each kernel module that sets USB IDs, with its declared licence and the extension-unit descriptors it contains. The camera's userspace application was read with `strings`. Nothing was decompiled or disassembled.

```bash
python3 -I factory/firmware.py hydrate
python3 -I factory/identity.py Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin   # writes factory/identity/<image>.json
lsusb -v -d 3564:fefb | grep -A12 EXTENSION_UNIT | grep -E 'bUnitID|guidExtensionCode|bNumControls|bmControls'
R=$(echo ~/.cache/libobsbot/factory/Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin/ROOTFS.ubi.d/*/root)
strings $R/lib/modules/5.10.61/extra/remo_multi_usb.ko | grep -E 'multi_uvc|rndis|uac_bind'
strings $R/app/bin/camera | grep -oE '^Remo_Uvc_Event[A-Za-z0-9]+' | sort -u
strings $R/app/bin/camera | grep 'Invalid XU cmd msg'
```

## Facts

1. The attached Meet 2 (USB ID `3564:fefb`) has one vendor extension unit: unit ID 2, GUID `{9a1e7291-6843-4683-6d92-39bc7906ee49}`, 7 controls (`bmControls` `0x7f`, selectors 1 to 7).
2. In the firmware, that unit and the USB ID are set by the gadget module `remo_multi_usb.ko`, which declares `license: GPL`, `author: ChengQun.Zhong`, `description: OBSBOT Meet 2` and depends on `libcomposite` and `u_ether`. The identity record `factory/identity/Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin.json` lists the same unit ID, GUID and control count. The module's strings show it builds a composite device of UVC video, UAC audio and an RNDIS Ethernet function, selected by a mode parameter.
3. The requests sent to the extension unit are handled in userspace by `/root/app/bin/camera`, a stripped 32-bit ARM executable that does not contain the GUID. Its strings name 52 handlers with the prefix `Remo_Uvc_Event` (for example `Remo_Uvc_EventAeModeSet`, `Remo_Uvc_EventCameraCmd`) and the error message `Invalid XU cmd msg`.
4. OBSBOT's "API file" `remo_uvc_ctrl.en.h` declares 122 `remo_uvc_ctrl_*` functions; its provenance is in `docs/compliance/2026-11-23-obsbot-license-evidence/README.md`.

## Hypotheses

- The GPL module defines the extension unit's descriptor, and the closed `camera` application interprets what is sent to it. If so, the module's source would show the descriptor but not the command protocol.
- The `Remo_Uvc_Event*` handler names, `libdev`'s command names and `remo_uvc_ctrl.en.h` are three views of one command set: the camera's, the host library's and the vendor's API documentation.
