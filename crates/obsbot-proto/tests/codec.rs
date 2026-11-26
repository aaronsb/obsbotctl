//! Codec tests against packets recorded from an OBSBOT Meet 2.
//!
//! # How the fixtures were derived
//!
//! Source: the factory oracle's raw traces
//! (`~/.cache/libobsbot/factory/oracle/traces/libdev_v2.1.0_8/`, written by
//! `factory/oracle/xu_trace.c`, never committed). Every packet in them was
//! exchanged with the one attached Meet 2; in the `sweep-*` traces the vendor
//! library had been told it was another product. Each fixture is the first
//! packet in the named trace that matches:
//!
//! | Fixture | Trace | Match |
//! |---|---|---|
//! | `REQUEST_UG_GET_UUID` | trace-fefb-probe_collect | selector 2 write, flags 0x01, opcode 0x1808 |
//! | `REPLY_UG_GET_UUID` | trace-fefb-probe_collect | selector 2 read, flags 0x29, opcode 0x1808 |
//! | `REPLY_UG_GET_SN` | trace-fefb-probe_collect | selector 2 read, flags 0x29, opcode 0x18c8 |
//! | `REQUEST_CAM_GET_IQ_PARAMETER` | trace-fefb-probe_collect_varied | selector 2 write, flags 0x41 |
//! | `MODULE_REPLY_CAM_GET_FACE_AE` | trace-fefb-probe_collect | selector 2 read, flags 0x89, opcode 0x2242 |
//! | `REQUEST_SYS_MG_GET_NETWORK_NIC_MAC` | sweep-fef6 | selector 2 write, flags 0x21 |
//! | `MODULE_REPLY_SYS_MG_GET_NETWORK_NIC_MAC` | sweep-fef6 | selector 2 read, flags 0xa9 |
//! | `REQUEST_UNLOGGED_0X1AC8` | sweep-fef8 | selector 2 write, flags 0x25, opcode 0x1ac8 |
//! | `UNRECOGNISED_PRODUCT_PROBE` | sweep-fe04 | selector 2 write, flags 0x00 |
//! | `STATUS_BLOCK` | trace-fefb-probe_collect | selector 6 read |
//!
//! Masking, applied to every `0xaa` packet above:
//!
//! 1. Within the CRC-covered bytes (the header, and the payload section when
//!    there is one), the camera's 14-byte ASCII serial number is replaced by
//!    `SERIALMASKED00` and its 6-byte device ID by `02 00 00 00 00 01`.
//! 2. The padding after those bytes, which holds stale bytes from earlier
//!    packets (fragments of the serial and device ID among them), is replaced
//!    by `0xee` in `REQUEST_CAM_GET_IQ_PARAMETER` and
//!    `MODULE_REPLY_CAM_GET_FACE_AE`, to test that decoding ignores it, and by
//!    `0x00` everywhere else.
//! 3. Both CRCs are recomputed over the masked bytes.
//!
//! `UNRECOGNISED_PRODUCT_PROBE` and `STATUS_BLOCK` held no identifiers and are
//! as recorded.

use obsbot_proto::opcodes::{self, CAM_GET_FACE_AE, CAM_GET_IQ_PARAMETER, UG_GET_SN, UG_GET_UUID};
use obsbot_proto::{
    crc16_usb, CommandSet, DecodeError, Device, EncodeError, Flags, Header, Opcode, Packet,
    StatusBlock, PACKET_LEN,
};

const fn hex(s: &str) -> [u8; PACKET_LEN] {
    const fn nibble(c: u8) -> u8 {
        match c {
            b'0'..=b'9' => c - b'0',
            b'a'..=b'f' => c - b'a' + 10,
            _ => panic!("not lowercase hex"),
        }
    }
    let s = s.as_bytes();
    assert!(s.len() == 2 * PACKET_LEN);
    let mut out = [0u8; PACKET_LEN];
    let mut i = 0;
    while i < PACKET_LEN {
        out[i] = nibble(s[2 * i]) << 4 | nibble(s[2 * i + 1]);
        i += 1;
    }
    out
}

const REQUEST_UG_GET_UUID: [u8; 60] = hex("aa0100000c00915c0a0d0818000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000");
const REPLY_UG_GET_UUID: [u8; 60] = hex("aa2900000c00a0490d0a08181800aef70000000000000000000000000000000000000200000000010000000000000000000000000000000000000000");
const REPLY_UG_GET_SN: [u8; 60] = hex("aa2903000c0000460d0ac8180e00452353455249414c4d41534b45443030000000000000000000000000000000000000000000000000000000000000");
const REQUEST_CAM_GET_IQ_PARAMETER: [u8; 60] = hex("aa4106000c0072390a0282380200f8050804eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee");
const MODULE_REPLY_CAM_GET_FACE_AE: [u8; 60] = hex("aa89050010004fa0020a42220002fdffeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee");
const REQUEST_SYS_MG_GET_NETWORK_NIC_MAC: [u8; 60] = hex("aa2106000c0029f70a120d61010027fa0d00000000000000000000000000000000000000000000000000000000000000000000000000000000000000");
const MODULE_REPLY_SYS_MG_GET_NETWORK_NIC_MAC: [u8; 60] = hex("aaa9060010006767120a0d610002ff0006006fe700000000000000000000000000000000000000000000000000000000000000000000000000000000");
const REQUEST_UNLOGGED_0X1AC8: [u8; 60] = hex("aa2504000c00bfb80a0dc81a2200dfdf746f756368202f6170702f707269766174652f7265736f6c7574696f6e2e636f6e6600000000000000000000");
const UNRECOGNISED_PRODUCT_PROBE: [u8; 60] = hex("aa000c12000067f500e88060000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000");
const STATUS_BLOCK: [u8; 60] = hex("240000020300010101037800000101140003000001002100010103000100001e11031000000000000000000000000000000000000000000000000000");

/// The fixtures whose padding is all zero, so encoding the decoded packet
/// must give back every byte.
const ZERO_PADDED: [&[u8; 60]; 6] = [
    &REQUEST_UG_GET_UUID,
    &REPLY_UG_GET_UUID,
    &REPLY_UG_GET_SN,
    &REQUEST_SYS_MG_GET_NETWORK_NIC_MAC,
    &MODULE_REPLY_SYS_MG_GET_NETWORK_NIC_MAC,
    &REQUEST_UNLOGGED_0X1AC8,
];

fn decode(b: &[u8; 60]) -> Packet {
    Packet::decode(b).expect("fixture decodes")
}

#[test]
fn crc16_usb_check_value() {
    assert_eq!(crc16_usb(b"123456789"), 0xb4c8);
}

#[test]
fn request_without_payload() {
    let p = decode(&REQUEST_UG_GET_UUID);
    let h = p.header();
    assert_eq!(h.flags, Flags::REQUEST);
    assert_eq!(h.sequence, 0);
    assert_eq!((h.reserved3, h.reserved5), (0, 0));
    assert_eq!(h.header_len(), 12);
    assert_eq!(h.source, Device::SDK);
    assert_eq!(h.destination, Device::UPGRADE);
    assert_eq!(h.opcode, UG_GET_UUID);
    assert_eq!(h.extension, None);
    assert_eq!(p.payload(), None);
}

#[test]
fn reply_with_payload() {
    let p = decode(&REPLY_UG_GET_UUID);
    let h = p.header();
    assert_eq!(h.flags, Flags::REPLY);
    assert_eq!(h.sequence, 0);
    assert_eq!(h.source, Device::UPGRADE);
    assert_eq!(h.destination, Device::SDK);
    assert_eq!(h.opcode, UG_GET_UUID);
    let mut want = [0u8; 24];
    want[18..24].copy_from_slice(&[0x02, 0, 0, 0, 0, 0x01]);
    assert_eq!(p.payload(), Some(&want[..]));

    let p = decode(&REPLY_UG_GET_SN);
    assert_eq!(p.header().sequence, 3);
    assert_eq!(p.header().opcode, UG_GET_SN);
    assert_eq!(p.payload(), Some(&b"SERIALMASKED00"[..]));
}

#[test]
fn request_with_payload_and_stale_padding() {
    let p = decode(&REQUEST_CAM_GET_IQ_PARAMETER);
    let h = p.header();
    assert_eq!(h.flags, Flags::REQUEST_WITH_PAYLOAD);
    assert_eq!(h.sequence, 6);
    assert_eq!(h.destination, Device::CAMERA);
    assert_eq!(h.opcode, CAM_GET_IQ_PARAMETER);
    assert_eq!(p.payload(), Some(&[0x08, 0x04][..]));
    let mut want = REQUEST_CAM_GET_IQ_PARAMETER;
    want[18..].fill(0);
    assert_eq!(p.encode(), want);
}

#[test]
fn module_reply_without_payload() {
    let p = decode(&MODULE_REPLY_CAM_GET_FACE_AE);
    let h = p.header();
    assert_eq!(h.flags, Flags::MODULE_REPLY);
    assert_eq!(h.sequence, 5);
    assert_eq!(h.header_len(), 16);
    assert_eq!(h.source, Device::CAMERA);
    assert_eq!(h.destination, Device::SDK);
    assert_eq!(h.opcode, CAM_GET_FACE_AE);
    assert_eq!(h.extension, Some([0x00, 0x02, 0xfd, 0xff]));
    assert_eq!(p.payload(), None);
    let mut want = MODULE_REPLY_CAM_GET_FACE_AE;
    want[16..].fill(0);
    assert_eq!(p.encode(), want);
}

#[test]
fn module_reply_with_payload() {
    let q = decode(&REQUEST_SYS_MG_GET_NETWORK_NIC_MAC);
    assert_eq!(q.header().flags, Flags::REQUEST_21);
    assert_eq!(q.header().destination, Device::SYSMG);
    assert_eq!(q.header().opcode, opcodes::SYS_MG_GET_NETWORK_NIC_MAC);
    assert_eq!(q.payload(), Some(&[0x0d][..]));

    let p = decode(&MODULE_REPLY_SYS_MG_GET_NETWORK_NIC_MAC);
    let h = p.header();
    assert_eq!(h.flags, Flags::MODULE_REPLY_WITH_PAYLOAD);
    assert_eq!(h.sequence, q.header().sequence);
    assert_eq!(h.source, Device::SYSMG);
    assert_eq!(h.opcode, opcodes::SYS_MG_GET_NETWORK_NIC_MAC);
    assert_eq!(h.extension, Some([0x00, 0x02, 0xff, 0x00]));
    assert_eq!(p.payload(), Some(&[0u8; 6][..]));
}

#[test]
fn unlogged_request() {
    let p = decode(&REQUEST_UNLOGGED_0X1AC8);
    assert_eq!(p.header().flags, Flags::REQUEST_25);
    assert_eq!(p.header().opcode, Opcode::from_raw(0x1ac8));
    assert_eq!(
        p.payload(),
        Some(&b"touch /app/private/resolution.conf"[..])
    );
    assert!(opcodes::UNLOGGED_REQUESTS
        .iter()
        .any(|u| u.opcode == p.header().opcode));
}

#[test]
fn encode_reproduces_recorded_bytes() {
    for fixture in ZERO_PADDED {
        assert_eq!(&decode(fixture).encode(), fixture);
    }
}

#[test]
fn encode_builds_a_request_like_the_vendor_library() {
    let h = Header::new(Flags::REQUEST, 0, Device::SDK, Device::UPGRADE, UG_GET_UUID);
    let p = Packet::new(h, None).unwrap();
    assert_eq!(p.encode(), REQUEST_UG_GET_UUID);

    let h = Header::new(
        Flags::REQUEST_WITH_PAYLOAD,
        6,
        Device::SDK,
        Device::CAMERA,
        CAM_GET_IQ_PARAMETER,
    );
    let p = Packet::new(h, Some(&[0x08, 0x04])).unwrap();
    assert_eq!(p.encode()[..18], REQUEST_CAM_GET_IQ_PARAMETER[..18]);
}

#[test]
fn status_block() {
    let s = StatusBlock::from_bytes(&STATUS_BLOCK).unwrap();
    assert_eq!(s.as_bytes(), &STATUS_BLOCK);
    assert_eq!(
        StatusBlock::from_bytes(&STATUS_BLOCK[..59]),
        Err(DecodeError::Length(59))
    );
    assert_eq!(Packet::decode(&STATUS_BLOCK), Err(DecodeError::Magic(0x24)));
}

#[test]
fn decode_errors() {
    assert_eq!(
        Packet::decode(&REPLY_UG_GET_UUID[..59]),
        Err(DecodeError::Length(59))
    );
    assert_eq!(
        Packet::decode(&UNRECOGNISED_PRODUCT_PROBE),
        Err(DecodeError::HeaderLength(0))
    );

    let mut b = REPLY_UG_GET_UUID;
    b[9] ^= 0x01;
    assert_eq!(
        Packet::decode(&b),
        Err(DecodeError::HeaderCrc {
            stored: 0x49a0,
            computed: 0x89f1
        })
    );

    let mut b = REPLY_UG_GET_UUID;
    b[20] = 0xff;
    assert!(matches!(
        Packet::decode(&b),
        Err(DecodeError::PayloadCrc { stored: 0xf7ae, .. })
    ));

    // A payload byte past the declared length is padding, not payload.
    let mut b = REPLY_UG_GET_UUID;
    b[16 + 24] = 0xff;
    assert!(Packet::decode(&b).is_ok());

    let mut b = REPLY_UG_GET_UUID;
    b[12] = 45;
    assert_eq!(
        Packet::decode(&b),
        Err(DecodeError::PayloadTooLong { len: 45, max: 44 })
    );
}

#[test]
fn new_checks_payload_against_flags() {
    let h = Header::new(
        Flags::REQUEST,
        0,
        Device::SDK,
        Device::CAMERA,
        CAM_GET_FACE_AE,
    );
    assert_eq!(
        Packet::new(h, Some(&[1])),
        Err(EncodeError::PayloadPresence {
            flags: Flags::REQUEST,
            payload: true
        })
    );
    let h = Header {
        flags: Flags::REPLY,
        ..h
    };
    assert!(Packet::new(h, None).is_err());
    assert_eq!(
        Packet::new(h, Some(&[0; 45])),
        Err(EncodeError::PayloadTooLong { len: 45, max: 44 })
    );
    assert_eq!(Packet::new(h, Some(&[0; 44])).unwrap().encode()[12], 44);
}

#[test]
fn opcode_fields() {
    // Values from factory/oracle/commands/fefb.json.
    assert_eq!(opcodes::CAM_GET_WDR_MODE.raw(), 0x02c2);
    assert_eq!(opcodes::CAM_GET_WDR_MODE.set(), CommandSet::CAMERA);
    assert_eq!(opcodes::CAM_GET_WDR_MODE.number(), 11);
    assert_eq!(UG_GET_UUID.set(), CommandSet::UPGRADE);
    assert_eq!(UG_GET_UUID.number(), 96);
    assert_eq!(opcodes::PRI_BLE_GET_MAC.set(), CommandSet::PRIMARY_BLE);
    assert_eq!(opcodes::SYS_MG_GET_DEVICE_NAME.set(), CommandSet::SYSMG);
    assert_eq!(
        Opcode::new(CommandSet::CAMERA, 11),
        Some(opcodes::CAM_GET_WDR_MODE)
    );
    assert_eq!(Opcode::new(CommandSet(64), 0), None);
    assert_eq!(Opcode::new(CommandSet::CAMERA, 1024), None);
}

#[test]
fn route_constants() {
    // Values the brief and the firmware route tables agree on.
    assert_eq!(
        [
            Device::CAMERA,
            Device::SDK,
            Device::UPGRADE,
            Device::SYSMG,
            Device::PRIMARY_BLE
        ],
        [Device(2), Device(10), Device(13), Device(18), Device(19)]
    );
    assert_eq!(
        [
            CommandSet::CAMERA,
            CommandSet::AI,
            CommandSet::UPGRADE,
            CommandSet::SYSMG
        ],
        [CommandSet(2), CommandSet(4), CommandSet(8), CommandSet(13)]
    );
}

#[test]
fn availability_tables() {
    assert_eq!(opcodes::COMMANDS.len(), 21);
    assert_eq!(opcodes::TRACED_PRODUCTS.len(), 13);
    let wdr = opcodes::COMMANDS
        .iter()
        .find(|c| c.name == "CAM_GET_WDR_MODE")
        .unwrap();
    assert_eq!(wdr.libdev_set, "CMD_SET_CAMERA");
    assert_eq!(wdr.destination, Device::CAMERA);
    assert_eq!(wdr.request_flags, Flags::REQUEST);
    assert!(wdr.products.contains(&0xfefb));
    let mac = opcodes::COMMANDS
        .iter()
        .find(|c| c.name == "PRI_BLE_GET_MAC")
        .unwrap();
    // grep -l PRI_BLE_GET_MAC factory/oracle/commands/*.json
    assert_eq!(mac.products, &[0xfef6, 0xfefc, 0xfefd]);
    for c in opcodes::COMMANDS {
        for pid in c.products {
            assert!(
                opcodes::TRACED_PRODUCTS
                    .iter()
                    .any(|p| p.product_id == *pid),
                "{} lists untraced product {pid:#06x}",
                c.name
            );
        }
    }
}
