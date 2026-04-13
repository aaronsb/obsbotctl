# obsbotctl

Open control library and D-Bus system daemon for OBSBOT cameras on Linux.

> **Status: scaffold.** Architecture and workspace structure are in place.
> No functional camera control yet — this repo currently compiles, but
> nothing talks to hardware.

## Goal

Treat OBSBOT cameras the way Linux treats any other complex device: a system
daemon owns the hardware, and applications talk to it over D-Bus. No
application needs to link against a vendor library or know anything
camera-specific — they just call D-Bus methods on `com.obsbot.Control1`, the
same way they'd talk to BlueZ, UPower, or fwupd.

Concrete outcomes this project is working toward:

- A `/dev/videoN` webcam continues to be a webcam — the kernel UVC driver
  already handles that.
- An `obsbotd` system daemon handles everything beyond standard UVC — AI
  tracking, auto-framing, HDR, presets, gimbal control, event notifications.
- Any Linux application (Qt, GTK, OBS plugin, CLI, Home Assistant, an MQTT
  bridge) can drive the camera by speaking D-Bus.
- Per-model capability profiles so new OBSBOT cameras can be added by
  submitting a data file rather than patching Rust source.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│          Any app (Qt, GTK, OBS, CLI, Home Assistant…)       │
└────────────────────────────┬────────────────────────────────┘
                             │  D-Bus (system bus)
                             │  com.obsbot.Control1
┌────────────────────────────▼────────────────────────────────┐
│                  obsbotd — Rust system daemon               │
│  udev hotplug │ polkit-gated methods │ event signals        │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                 obsbotctl-core — Rust library               │
│  transport  │  protocol   │  device catalog & quirks        │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│         Linux kernel (uvcvideo, bluez, usbfs)               │
└─────────────────────────────────────────────────────────────┘
```

Three binaries in one workspace:

- **`obsbotd`** — the system daemon
- **`obsbotctl`** — a CLI client (like `bluetoothctl` or `networkctl`)
- **`obsbotctl-core`** — the Rust library everything builds on

## Integration options

Applications have three ways to consume this stack, in increasing coupling:

1. **D-Bus (recommended).** Language-agnostic, zero linking. Any language
   with a D-Bus binding works.
2. **C FFI via cbindgen.** In-process linking for C/C++ consumers that can't
   afford a D-Bus round trip.
3. **CXX-Qt.** In-process Rust QObjects for deep Qt integration.

The D-Bus path is the primary target; the other two are escape hatches.

## Scope

**In scope**

- PTZ, focus, zoom, exposure, white balance, HDR
- AI modes: tracking, auto-framing, gestures, presets
- Event notifications (target lost, mode switch, battery, etc.)
- Per-model capability profiles for the full OBSBOT camera family

**Out of scope (for now)**

- Firmware upgrade
- Virtual background upload
- Video streaming — the kernel UVC driver already handles this; use
  GStreamer, V4L2, or OpenCV
- Tail Air networked / wireless streaming mode

See [`docs/devices.md`](docs/devices.md) for the intended device catalog.

## Related projects

- [obsbot-camera-control](https://github.com/aaronsb/obsbot-camera-control) —
  Qt GUI that will eventually consume `obsbotctl` over D-Bus.
- [bosectl](https://github.com/aaronsb/bosectl) — sibling project applying
  the same Linux-native system daemon pattern to Bose headphones.

## License

MIT — see [LICENSE](LICENSE).
