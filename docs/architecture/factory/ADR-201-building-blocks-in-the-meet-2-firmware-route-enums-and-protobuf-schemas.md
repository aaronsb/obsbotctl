---
contract: adr/v1
kind: evidence
capability: factory
status: accepted
date: 2026-11-25
deciders:
  - aaronsb
related: []
---

# ADR-201: Building blocks in the Meet 2 firmware: route enums and protobuf schemas

## Method

The Meet 2 firmware image v4.4.7.1, unpacked by `factory/identity.py`, was searched for files that name the camera's internal addresses and messages. The route tables are plain JSON. The message schemas are serialized protobuf `FileDescriptorProto` messages in a library's data; `factory/proto/extract_descriptors.py` finds each one by its leading `name` field, measures it by walking the protobuf wire format, and decodes it with `protoc` against Google's `descriptor.proto`. That is a documented Google format read as data: nothing was decompiled, disassembled or run. The decoded schemas are committed in `factory/proto/meet2-4.4.7.1/`, with their provenance in `factory/proto/README.md`.

```bash
python3 -I factory/identity.py Obsbot_meet2_OA_E_PW203_4.4.7.1_release.bin   # route_enums in the identity record
python3 -I factory/proto/extract_descriptors.py                              # factory/proto/meet2-4.4.7.1/
cat factory/proto/meet2-4.4.7.1/*.txt | grep -cE '^\s*(message_type|nested_type) \{'   # 282
cat factory/proto/meet2-4.4.7.1/*.txt | grep -cE '^\s*enum_type \{'                    # 112
cat factory/proto/meet2-4.4.7.1/*.txt | grep -cE '^\s*field \{'                        # 1192
grep -A1 -hE '^\s*(message_type|nested_type|enum_type) \{' factory/proto/meet2-4.4.7.1/*.txt \
  | grep -oP 'name: "\K[^"]+' | sort -u > /tmp/schema-names.txt                        # 394 names
strings ~/.local/share/libobsbot/sdk/libdev_v2.1.0_8/lib/libdev.so.1.0.0 | grep -oE '[A-Za-z_][A-Za-z0-9_]+' \
  | sort -u | comm -12 - /tmp/schema-names.txt                                         # prints nothing
```

## Facts

1. `/root/app/route/enum.json` numbers the camera's internal device addresses (`DEVICE`: BROADCAST=0, ROUTER=1, CAMERA=2, GIMBAL=3, AI=4, BATTERY=5, LENS=6, ROLL=7, PITCH=8, YAW=9, SDK=10, APP=11, PC=12, UPGRADE=13, FACTORY=14, WLS=15, MONITOR=16, OBOX=17, SYSMG=18, PRIMARY_BLE=19, BASE=20) and its command sets (`CMDSET`: UNIVERSAL=0, ROUTER=1, CAMERA=2, GIMBAL=3, AI=4, BATTERY=5, LENS=6, SDK=7, UPGRADE=8, FACTORY=9, WLS=10, MONITOR=11, OBOX=12, SYSMG=13, PRIMARY_BLE=14). `factory/identity.py` records both tables as `route_enums`. `/root/app/route/route_config.json` routes each address to a process over netlink, UDP port 9999, TCP port 26679 or a factory serial port.
2. `/usr/lib/libremo_pb2json.so` embeds 11 `proto3` schema files, `bp2j_tmp_remo_{cfg,common,device,media,pdt_cfg,pdt_status,pdt_ust,protocol,status,stream,ust}.proto`. Together they define 282 messages, 112 enums and 1,192 fields with names, numbers and types. `remo_protocol` alone holds 150 messages and 60 enums.
3. `/usr/lib/libremoproto.so.1.0.0.5` embeds no schema file, consistent with a protobuf-lite build.
4. None of the 394 message and enum names in the schemas appears in the strings of the vendor library `libdev.so.1.0.0` (SDK `libdev_v2.1.0_8`).

## Hypotheses

- Some of the 282 messages are the payloads that cross USB. `libdev` bundles nanopb-generated `camera.pb.c` and `dev.pb.c`; matching their field layouts against these schemas by structure, not by name, would show which.
