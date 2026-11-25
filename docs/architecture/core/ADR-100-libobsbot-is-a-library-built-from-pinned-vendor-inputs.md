---
contract: adr/v1
kind: decision
verb: add
capability: library
basis:
  - operator: aaronsb
    level: directed
    said: "I'm thinking about renaming obsbotctl to libobsbot so we can continue building an open version of their library."
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "let's keep it simple - libobsbot becomes something a future obsbotd would use"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "we should make sure that for now the repo 'obsbot-camera-control' remains functional and independent."
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "dbus isn't really a primary target any more … it's nice to have that as an accessory probably. but not every linux distro is going to use that"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "I don't want to distribute the vendor blob libary, but we can make a requires for it and name the version."
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "none of the firmware ever gets put into the repo, but we include scripts that can do that to hydrate for a developer/user"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "we could essentially build a factory - pin all the firmware versions we support, then pull all the uvc commands and then we build against them"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "then we have test harnesses that compare the output of their crap library against ours looking for call consistency"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: guided
    said: "a per-product code assembly is probably the right shape here. I can't afford to buy every camera they have … I only have a meet 2"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: guided
    said: "what do you  think of having a crate per camera and then a common set of crates to make it so someone doesn't need to take every feature from every camera just to do things"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "ok i like your split better"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "we need to be able to recreate the corpus from scratch even if it takes some time"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "I think it's fair to pull device identifiers from all the firmware files, then we can specifically claim which devices we're trying out and build a truthful reference that way"
    via: chat session, 2026-11-25
  - operator: aaronsb
    level: directed
    said: "sdk isn't a straightforward download - you have to request it via email or be given the file. there's no charge or gate other than having contacted obsbot … anyone who does not have to have a copy should visit https://www.obsbot.com/sdk to inquire to get a copy of it"
    via: chat session, 2026-11-25
  - evidence: "The debug information in OBSBOT's Linux SDK library (libdev.so.1.0.2 and libdev.so.1.0.0) lists 76 source files; 16 of them, under dev/, control cameras, and the rest are bundled compression, firmware-update, file-transfer and networking code. Extracted with readelf --debug-dump=info."
  - evidence: "SDK package libdev_v2.1.0_8 ships libdev.so.1.0.0, while the older libdev_v2.1.0_7 ships libdev.so.1.0.2, so the library's own version numbers cannot order releases. SHA256 values are in docs/compliance/2026-11-23-obsbot-license-evidence/SHA256SUMS."
  - evidence: "In Meet 2 firmware v4.4.7.1, the GPL kernel module remo_multi_usb.ko holds the camera's USB IDs (3564:fefb) and its extension-unit GUID, and the closed application /root/app/bin/camera names 52 Remo_Uvc_Event handlers. Recorded with reproducing commands in notes/investigation/003-device-side-extension-unit.md (local, not published)."
  - evidence: "OBSBOT's download pages list firmware for about 29 products, more than the 17 the SDK header names. The CDN refuses unsigned requests with HTTP 403; the page obtains a signed link by POSTing the file URL to remo-api.obsbot.com/fms/v1/files/cdn/authorization."
observable:
  - 'run: cargo metadata --no-deps --format-version 1 | python3 -c "import sys,json;print(sorted(p[\"name\"] for p in json.load(sys.stdin)[\"packages\"]))"   # prints [''obsbot'', ''obsbotctl'']'
  - 'see: no file in the repository has the SHA256 of a pinned vendor SDK file or firmware image'
  - 'see: each camera listed as supported names the evidence grade behind each of its controls'
agent:
  name: claude
  model: claude-opus-5-5
considered:
  - operator: aaronsb
    said: "sdk isn't a straightforward download - you have to request it via email or be given the file. there's no charge or gate other than having contacted obsbot"
    via: chat session, 2026-11-25, answering whether the SDK stays a hand-fetched file the script only verifies
  - operator: aaronsb
    said: "let's keep it simple - libobsbot becomes something a future obsbotd would use"
    via: chat session, 2026-11-25, answering whether obsbotd stays in this repository as an optional crate
  - operator: aaronsb
    said: "ok i like your split better"
    via: chat session, 2026-11-25, choosing layered crates with per-product Cargo features over one crate per camera
  - operator: aaronsb
    said: "we need to be able to recreate the corpus from scratch even if it takes some time"
    via: chat session, 2026-11-25, adding the rebuildable-corpus requirement to D3
status: proposed
date: 2026-11-25
deciders:
  - aaronsb
related: []
---

# ADR-100: libobsbot is a library built from pinned vendor inputs

## Summary

- **Decided:** libobsbot is an open library that applications link in place of OBSBOT's closed `libdev`. Its camera support is generated from facts extracted from pinned copies of OBSBOT's own files (SDK packages and camera firmware), which are kept outside the repository and fetched by scripts. Recordings of the vendor library's behaviour check it. A system service such as a D-Bus daemon is a separate project built on the library.
- **Trades away:** an early first release (the extraction and generation tooling comes before most camera features), a runtime fallback to the vendor library, and certainty for cameras nobody on the project owns. The tooling also depends on OBSBOT keeping its downloads public.
- **One-way?** No. It is reversible now, and becomes expensive once applications ship against the C API.
- **Probes:** *Confident:* no vendor file is ever committed or packaged. *Not confident:* that the older firmware images, which may not run Linux, give up their command names the way the Meet 2's does.
- **Inversion:** The choice sits between wrapping the vendor library and reimplementing it by hand from observation. This decision does neither: it generates the implementation from the vendor's own files and checks it against the vendor's own behaviour.

## Context

OBSBOT's Linux SDK is a single closed library of about 25 MB. Only a small part of it controls cameras, and the rest is statically linked code a desktop application does not need. Some of that code is LGPL and ships without its licence texts. Its version numbers go backwards between releases. Applications that link it inherit all of this and cannot fix any of it.

A camera is controlled through the kernel's generic UVC driver. Vendor-specific commands travel through a UVC extension unit that the camera's firmware defines, so all the vendor logic on the computer side runs in userspace.

The project owns one camera. OBSBOT sells about 29, and their firmware changes the command set between releases. Per-product support therefore needs a source of truth other than owning each camera. OBSBOT's own files can provide one: the SDK library names its commands and carries debug information, and each firmware image names the commands the camera accepts and carries its USB identity.

## Decision

### D1. The library is the product

The `obsbot` crate, built as `libobsbot`, is the public surface. Rust applications use its Rust API. C, C++ and Qt applications use a C API generated with `cbindgen` from a `cdylib` build. The `obsbotctl` CLI links the library directly. This repository holds only the library and the CLI. A system service that owns the cameras, such as a future `obsbotd` D-Bus daemon, would be a separate project that uses the library like any other application.

obsbot-camera-control, the Qt application developed alongside libobsbot, stays independent of it for now. It keeps building against the vendor SDK, and no libobsbot change requires a change there. It switches to libobsbot only when libobsbot can replace the vendor SDK for it, as a decision of its own.

### D2. Vendor files are inputs, never contents

No OBSBOT SDK file or firmware image is committed to the repository or included in any package built from it. A manifest in the repository pins each supported input: the product or SDK package, its version, the file name, its SHA256 and where it is obtained.

Hydration scripts fetch each pinned input into a local store outside the repository (`$OBSBOT_SDK_DIR` and `$OBSBOT_FIRMWARE_DIR`, by default under `~/.local/share/libobsbot/`). They refuse any file whose hash does not match its pin. The scripts download firmware only through OBSBOT's public download flow, and never forge or bypass its link signatures.

The SDK is not a download. OBSBOT supplies the SDK library by email, at no cost, to anyone who asks at https://www.obsbot.com/sdk, and the library is all this project uses. A developer who needs it and has no copy requests one there, places the files in the store, and the script verifies them against their pins. The project never passes SDK copies between people.

### D3. Extraction reads the inputs without decompiling them

Extractors read the pinned inputs with symbol tables, strings, debug information, byte searches and documented container formats, and record the camera traffic they observe. They do not decompile or disassemble vendor code. Their output is committed as data: USB IDs, extension-unit GUIDs, command names, and command numbers and payload layouts where a source states them.

The committed data, which this record calls the corpus, can be rebuilt from scratch. A factory command regenerates every item from the pinned inputs, the reference camera and any contributed recordings, however long that takes. No item is written by hand without a script that reproduces it. Each item records the inputs it came from, by SHA256, so a rebuild that changes an item shows which input moved.

When a recording claims to come from a product the project does not own, it is made by giving the vendor library that product's identity, taken from that product's own pinned firmware: its USB IDs and its device-information fields. The recording names the firmware its identity came from, and carries the vendor-oracle grade (D5).

### D4. Camera support is generated from a catalog

A product catalog is the single source for what libobsbot supports. Each entry is keyed by USB vendor and product ID and a firmware version range, and states the protocol dialect, the commands, their value ranges and any quirks. Every fact in it records the source it came from.

The sources name the same command differently. A reviewed mapping table joins them, and each mapping is a claim with a source. A build script generates the Rust command and capability tables from the catalog, so an inconsistent catalog fails the build.

Each protocol dialect is a code module. Product-specific code exists only for quirks the catalog cannot express.

The workspace splits into crates by layer and by dependency weight, not by product:

| Crate | Holds |
|---|---|
| `obsbot-proto` | Message types, enums and packet framing generated from the extracted schemas, with no I/O, so other projects can reuse them |
| `obsbot-transport` | Access to UVC extension units on Linux; heavier transports, such as Bluetooth, get crates of their own |
| `obsbot-catalog` | The generated per-product tables, with one Cargo feature per product |
| `obsbot` | The high-level camera API, which re-exports the layers below and passes the product features through |
| `obsbot-capi` | The C library (`libobsbot.so`) and its header |
| `obsbotctl` | The command-line tool |

A consumer selects the products it needs with Cargo features, for example `features = ["meet2"]`, and code for unselected products is not compiled. Each product feature enables the protocol dialect it needs. The default feature set includes every product. Each crate is created when its first code lands.

### D5. Support claims carry an evidence grade

Each control on each product carries one of these grades, strongest first:

1. **Hardware-verified**: tested on the camera.
2. **Owner-captured**: recorded from a contributor's camera.
3. **Vendor-oracle**: recorded from the vendor library talking to a simulated camera that identifies as the product.
4. **Firmware-declared**: named in the product's firmware.
5. **Vendor-documented**: stated only in vendor headers or documentation.

Documentation and release notes state the grade behind each support claim.

### D6. Profiles follow the firmware version

On connecting, libobsbot reads the camera's firmware version and selects the catalog profile for that version range. For a firmware version newer than any profile, it uses the nearest older profile and reports that it did so.

### D7. Recorded vendor behaviour is the test oracle

A comparison harness runs each test scenario through the vendor library and records, in order, the requests it sends and the replies it receives. The recordings are committed. The test suite replays them against libobsbot and needs no vendor files.

Recording new scenarios, or comparing a libobsbot build with the vendor library directly, needs the hydrated SDK. Comparisons check each request field by field and ignore sequence numbers. A reviewed list records known, intended differences, each with its reason.

## Consequences

### Positive

- Applications get camera control without linking a 25 MB closed library.
- A camera nobody on the project owns can still be supported, at a stated grade, from its firmware and the vendor library.
- Adding a product or firmware version is mostly a data change that the build checks.
- When OBSBOT changes a command between firmware releases, the change shows up as a difference in the extracted data, not as a field report.
- The repository can be cloned, built and tested by anyone without vendor files.

### Negative

- The extraction, hydration and generation tooling must exist before most camera features do.
- Each firmware container format needs its own unpacker. Images that are not Linux-based may yield less, or nothing.
- The tooling depends on OBSBOT's download flow, which can change without notice.
- Lower grades describe what the vendor's files say, not what a camera does. Users of unowned cameras carry that risk until someone records from real hardware.

### Neutral

- The catalog is plain data, not Rust source, so other consumers can be generated from it as well: a separate daemon, or, hypothetically, kernel-side handling of OBSBOT's extension units. That stays an option, not a commitment.
- Contributors who own other cameras become the main source of grade-2 evidence, so recording from a camera has to be one command.
- The compliance evidence and this tooling read the same files. A compliance report that relies on the comparison harness has to state that it ran vendor code.

## Alternatives Considered

- **A system D-Bus daemon as the primary interface.** This was the project's first design. It was rejected because not every distribution or user wants a system daemon, and desktop users already have access to their camera's device node without one. A daemon remains possible as a separate project on top of the library (D1).
- **Wrap `libdev` behind an open API.** This would have been the fastest route to working features. It was rejected because applications would still load the closed library and inherit its size, its licence problems and its platform limits, and nobody outside OBSBOT could fix it.
- **One crate per camera on top of a set of common crates.** This would let a consumer take only the cameras it needs. It was rejected because cameras share most of their protocol, so each product crate would hold little more than catalog data, and about 29 crates would each need releasing whenever the shared protocol changed. Cargo features on `obsbot-catalog` give the same selection without the extra crates (D4).
- **Hand-written code per product, without a catalog or factory.** This was rejected because the project owns one of about 29 products and has no other way to learn the rest's command sets. Hand-written code would also drift silently from each firmware release.
- **Commit the vendor files for reproducibility.** This was rejected because it redistributes OBSBOT's copyrighted binaries. Pinning by SHA256 gives the same reproducibility without redistribution (D2).
- **Use the vendor library as a runtime fallback.** This was rejected because it keeps applications coupled to the closed library, which is the problem the project exists to remove.
