# OBSBOT device catalog

The intended coverage list for `obsbotctl`. The goal is to scaffold for the
full OBSBOT camera family, not only the ones any single contributor owns.

## Coverage levels

| Level | Meaning |
|---|---|
| **owned** | A contributor has this device and can test against it |
| **known** | Public model; we're building a profile for it |
| **speculated** | Model name seen in the wild, details still to confirm |

## Catalog

| Model | Family | USB PID | Level | Notes |
|---|---|---|---|---|
| Tiny (original) | Tiny | _tbd_ | known | pending profile |
| Tiny 4K | Tiny | _tbd_ | known | pending profile |
| Tiny SE | Tiny | _tbd_ | known | pending profile |
| Tiny 2 | Tiny | _tbd_ | known | pending profile |
| Tiny 2 Lite | Tiny | _tbd_ | known | pending profile |
| Tiny 3 | Tiny | _tbd_ | known | V4L2-only at release |
| Me | Me | _tbd_ | known | pending profile |
| Me 2 | Me | _tbd_ | known | pending profile |
| Meet (original) | Meet | _tbd_ | known | pending profile |
| Meet 2 | Meet | _tbd_ | **owned** | reference device |
| Meet 4K | Meet | _tbd_ | known | pending profile |
| Meet SE | Meet | _tbd_ | known | pending profile |
| Tail Air | Tail | _tbd_ | known | Bluetooth control surface likely |
| Tail 2 | Tail | _tbd_ | known | pending profile |
| Tail 2S | Tail | _tbd_ | speculated | pending info |
| HDMI Box | Accessory | _tbd_ | known | pending profile |
| NDI Box | Accessory | _tbd_ | known | pending profile |

## Open questions

1. **USB vendor + product IDs.** Need to be cataloged per model.
2. **Protocol dispatch per model.** How much varies between models within a
   family?
3. **Tiny 3.** First V4L2-only model in the wild. Does it accept any vendor
   control surface beyond standard UVC?
4. **Tail Air Bluetooth surface.** Which operations are Bluetooth-only vs
   USB-only vs both?

## Contributing a new model

Once the capability probe tool exists (tracked in issues):

1. Plug in your OBSBOT device
2. Run the probe tool while exercising settings from the vendor app
3. Submit the resulting probe output as an issue or PR
4. A per-model profile gets merged
5. Coverage level for that model moves up
