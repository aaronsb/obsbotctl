# Firmware protobuf schemas

These are the message schemas OBSBOT's camera firmware is built with, decoded from the firmware and committed as derived interface facts: message, enum and field names, field numbers and types. They are not OBSBOT source files, and no vendor file is stored here.

## Provenance

| | |
|---|---|
| Firmware image | `Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin` (Meet 2, v4.4.7.1) |
| Image SHA256 | `240591d4ab2dd39bf785e5fe289160af590138d83e0b011dac2fe4ca11b3fedd`, as pinned in `factory/firmware/pins.json` |
| File in the image | `/usr/lib/libremo_pb2json.so`, in the root filesystem (`ROOTFS.ubi`) |
| File SHA256 | `5785949edae2d7e09c5b17483a6a212c3d5f85044d6faf0f69927f9f182aed72` |
| Decoder | `protoc` 36.1, with Google's `descriptor.proto` |

`meet2-4.4.7.1/source.json` records the same, plus the offset and length of each schema inside the library.

## Method

A program built with full (not lite) protobuf carries each `.proto` file it was compiled from as a serialized `FileDescriptorProto` message in its data. `extract_descriptors.py` searches the library's bytes for the start of such a message (field 1, a name ending in `.proto`), measures it by walking the protobuf wire format, and decodes it with `protoc --decode=google.protobuf.FileDescriptorProto`. The output is protoc's text format of each descriptor. The script reads bytes only: no vendor code is run, decompiled or disassembled.

The Meet 2 image yields 11 `proto3` files, `bp2j_tmp_remo_*.proto`, which together define 282 messages, 112 enums and 1,192 fields.

## Regenerating

```bash
python3 -I factory/firmware.py hydrate                                         # fetch and verify the pinned image
python3 -I factory/identity.py Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin     # unpack it to ~/.cache/libobsbot/factory/
python3 -I factory/proto/extract_descriptors.py                                # rewrite factory/proto/meet2-4.4.7.1/
```

Pass other pinned image names to `extract_descriptors.py` to decode their schemas into `factory/proto/<product>-<version>/`. The raw descriptor blobs stay in `~/.cache/libobsbot/factory/proto/`, outside the repository.

## References

- ADR-100 D3: extraction reads the pinned inputs without decompiling them, and each item records the inputs it came from by SHA256.
- ADR-201: what the schemas hold, the firmware's other building blocks, and how both were found.
