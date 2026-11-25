# Architecture

`libobsbot` is a four-layer Rust library (the `obsbot` crate) plus a D-Bus daemon and CLI.
Applications don't link to anything camera-specific — the daemon owns the
hardware, and consumers talk to it over D-Bus.

## Layer 1: Transport

**Responsibility:** get bytes on and off the device.

Planned transports:

| Transport | Used by | Status |
|---|---|---|
| UVC Extension Unit over `UVCIOC_CTRL_QUERY` | USB cameras | primary target |
| V4L2 standard controls | baseline controls on all cameras | partially validated |
| Bluetooth RFCOMM | Tail Air, possibly BLE remotes | planned |
| mDNS + KCP | Tail Air networked mode | out of scope initially |

Built on `rustix` for raw ioctls, `nusb` for USB access, `udev` for hotplug
events, and `zbus` as a BlueZ client for the Bluetooth path.

## Layer 2: Protocol

**Responsibility:** frame packets, encode/decode commands, dispatch on
per-model dialects.

OBSBOT cameras expose several logical services:

- **Camera control** — PTZ, focus, exposure, white balance, HDR
- **AI services** — tracking modes, auto-framing, gimbal presets, gestures
- **System management** — LEDs, buzzer, WiFi/Ethernet (WiFi-equipped models)
- **Event stream** — async notifications (target lost, mode switch, battery, etc.)

Different models carry different variants of these services, so the
protocol layer dispatches by model — which is why the catalog layer is
load-bearing. Packed payloads are handled with `zerocopy` for safe
struct↔bytes conversion without `unsafe`.

## Layer 3: Catalog

**Responsibility:** given a (USB VID, PID) tuple (or Bluetooth MAC pattern),
return the model identity and capability profile.

Profiles tell the protocol layer:

- Which services the model supports
- Which command variants to use for shared actions
- Which capabilities require the XU path vs V4L2

Profiles live as data (TOML or similar), not Rust source, so contributors
can add new models by submitting profile files rather than patching code.

## Layer 4: Public surface

The library exposes a Rust API (`obsbot::...`) consumed by the
daemon and CLI in this workspace. External consumers have three options:

### Option A: D-Bus (primary)

`obsbotd` registers `com.obsbot.Control1` on the system bus. Applications
talk D-Bus via their native bindings — QtDBus, `gio` (GTK), `dbus-next`
(Python), etc.

This is the shape modern Linux userspace device stacks converge on — BlueZ,
UPower, fwupd, PipeWire, NetworkManager, bolt. The Rust precedent for
daemons in this shape is growing (`supergfxctl`, `asusctl`, `system76-power`).

**D-Bus tree (planned):**

```
System bus: com.obsbot.Control1

/com/obsbot/Control1/Manager
  interface com.obsbot.Control1.Manager
    method  ListDevices() -> (ao)
    signal  DeviceAdded(o)
    signal  DeviceRemoved(o)

/com/obsbot/Control1/Device/N
  interface org.freedesktop.DBus.Properties
  interface com.obsbot.Control1.Device  (identity + capabilities)
  interface com.obsbot.Control1.Camera  (PTZ, focus, HDR, AI, events)
```

### Option B: C FFI via cbindgen

For consumers that must be in-process (performance, sandboxing, daemon not
installed), the `obsbot` crate can compile as a `cdylib` with a
`cbindgen`-generated C header. Any C/C++/Qt application can then link it
directly.

### Option C: CXX-Qt in-process QObjects

[CXX-Qt](https://kdab.github.io/cxx-qt/) bridges Rust and Qt deeply enough
to expose Rust structs as QML-compatible `QObject` subclasses. Use this
if you want the camera library to be part of your Qt object graph — bound
directly to QML properties — rather than a separate system service.

None of the three options conflict. D-Bus is the default; the other two are
escape hatches for specific consumers.

## Crate layout

```
crates/
├── obsbot/             library — transport, protocol, catalog
├── obsbotd/            D-Bus system daemon
└── obsbotctl/          CLI client (talks to obsbotd over D-Bus)
```

The daemon and CLI both depend on the core library. They don't depend on
each other at the code level — communication is over D-Bus at runtime.

## What's intentionally not here

- **Firmware upgrade.** Out of scope — use vendor tools.
- **Video streaming.** The kernel UVC driver exposes cameras as `/dev/videoN`.
  Use GStreamer, V4L2, or OpenCV to read pixels. `libobsbot` is a control
  plane, not a data plane.
- **Virtual background upload.** Not part of the v1 scope.
- **Tail Air networked mode.** Deferred until the USB path is stable.
