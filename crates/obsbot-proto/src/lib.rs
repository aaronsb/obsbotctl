//! obsbot-proto: the packet codec for OBSBOT cameras' UVC extension unit.
//!
//! Pure data handling: no I/O and no `unsafe`. A transport writes the bytes
//! [`Packet::encode`] produces to the command selector, reads the reply back
//! from the same selector, and hands it to [`Packet::decode`].
//!
//! # Wire format
//!
//! Every command and reply is a 60-byte block ([`PACKET_LEN`]):
//!
//! | Bytes | Field |
//! |---|---|
//! | 0 | magic, `0xaa` |
//! | 1 | [`Flags`] |
//! | 2 | sequence number; a reply echoes its request's |
//! | 3 | unknown, 0 in every recorded packet |
//! | 4 | header length: 12, or 16 for camera-module replies |
//! | 5 | unknown, 0 in every recorded packet |
//! | 6–7 | CRC-16/USB of the header with these two bytes zeroed, little-endian |
//! | 8 | source [`Device`] |
//! | 9 | destination [`Device`] |
//! | 10–11 | [`Opcode`], little-endian |
//! | 12–15 | 16-byte headers only: an extension, `00 02 fd ff` or `00 02 ff 00` so far |
//!
//! When the flags carry a payload ([`Flags::has_payload`]), a payload section
//! follows the header: a little-endian length `L`, a CRC-16/USB over the
//! section's `4 + L` bytes with its own CRC bytes zeroed, then `L` bytes of
//! payload. The rest of the block is padding. The vendor library leaves stale
//! bytes from earlier packets in it, so [`Packet::decode`] ignores it and
//! [`Packet::encode`] writes zeros.
//!
//! The layout and the payload rule were checked against every packet in the
//! factory oracle's recordings from an attached Meet 2 (factory/oracle).

#![forbid(unsafe_code)]
#![deny(rust_2018_idioms)]
#![warn(missing_docs)]

use std::fmt;

use crc::{Crc, CRC_16_USB};
use thiserror::Error;

pub mod opcodes;

/// Size of every command, reply and status block.
pub const PACKET_LEN: usize = 60;

/// First byte of every command and reply.
pub const MAGIC: u8 = 0xaa;

/// Extension-unit selector that takes a command and returns its reply.
pub const SELECTOR_COMMAND: u8 = 2;

/// Extension-unit selector that returns the 60-byte [`StatusBlock`].
pub const SELECTOR_STATUS: u8 = 6;

/// Header length of ordinary packets.
pub const HEADER_LEN: usize = 12;

/// Header length of camera-module replies, which carry an extension.
pub const HEADER_LEN_EXTENDED: usize = 16;

/// Bytes a payload section spends on its length and CRC.
const SECTION_LEN: usize = 4;

const CRC16_USB: Crc<u16> = Crc::<u16>::new(&CRC_16_USB);

/// CRC-16/USB (reflected polynomial 0x8005, init and xorout 0xffff).
pub fn crc16_usb(bytes: &[u8]) -> u16 {
    CRC16_USB.checksum(bytes)
}

/// CRC-16/USB of `bytes` with the two bytes at `hole` read as zero.
fn crc16_usb_with_hole(bytes: &[u8], hole: usize) -> u16 {
    let mut digest = CRC16_USB.digest();
    digest.update(&bytes[..hole]);
    digest.update(&[0, 0]);
    digest.update(&bytes[hole + 2..]);
    digest.finalize()
}

fn le16(bytes: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([bytes[at], bytes[at + 1]])
}

/// Byte 1 of a packet, kept raw: only some values have been seen, and what
/// each bit means is not known.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct Flags(pub u8);

impl Flags {
    /// Request with no payload section, as the vendor library sends getters.
    pub const REQUEST: Flags = Flags(0x01);
    /// Request with a payload section; seen on `SYS_MG_GET_NETWORK_NIC_MAC`.
    pub const REQUEST_21: Flags = Flags(0x21);
    /// Request with a payload section; seen on requests sent with no log line.
    pub const REQUEST_25: Flags = Flags(0x25);
    /// Request with a payload section; seen on `CAM_GET_IQ_PARAMETER`.
    pub const REQUEST_WITH_PAYLOAD: Flags = Flags(0x41);
    /// Reply with a payload section and a 12-byte header.
    pub const REPLY: Flags = Flags(0x29);
    /// Camera-module reply: 16-byte header, no payload section.
    pub const MODULE_REPLY: Flags = Flags(0x89);
    /// Camera-module reply: 16-byte header and a payload section.
    pub const MODULE_REPLY_WITH_PAYLOAD: Flags = Flags(0xa9);

    /// Whether a payload section follows the header.
    ///
    /// Observed rule: in every recorded packet, a payload section with a valid
    /// CRC is present exactly when bit 0x20 or 0x40 is set.
    pub const fn has_payload(self) -> bool {
        self.0 & 0x60 != 0
    }
}

/// A source or destination device (bytes 8 and 9), from the firmware's
/// `DEVICE` enum. Named values are in [`opcodes`].
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct Device(pub u8);

/// A camera command set, the low six bits of an [`Opcode`], from the
/// firmware's `CMDSET` enum. Named values are in [`opcodes`].
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct CommandSet(pub u8);

/// A command opcode: `(number << 6) | set`, sent little-endian in bytes 10–11.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct Opcode(u16);

impl Opcode {
    /// The opcode with this wire value.
    pub const fn from_raw(raw: u16) -> Opcode {
        Opcode(raw)
    }

    /// The opcode for command `number` in `set`, or `None` when the set does
    /// not fit in six bits or the number in ten.
    pub const fn new(set: CommandSet, number: u16) -> Option<Opcode> {
        if set.0 >= 1 << 6 || number >= 1 << 10 {
            None
        } else {
            Some(Opcode(number << 6 | set.0 as u16))
        }
    }

    /// The wire value.
    pub const fn raw(self) -> u16 {
        self.0
    }

    /// The command set.
    pub const fn set(self) -> CommandSet {
        CommandSet((self.0 & 0x3f) as u8)
    }

    /// The command number within its set.
    pub const fn number(self) -> u16 {
        self.0 >> 6
    }
}

impl fmt::Debug for Opcode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Opcode({:#06x}: set {}, number {})",
            self.0,
            self.set().0,
            self.number()
        )
    }
}

/// The header fields of a packet. The CRC and lengths are computed, not stored.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Header {
    /// Byte 1.
    pub flags: Flags,
    /// Byte 2.
    pub sequence: u8,
    /// Byte 3, meaning unknown; 0 in every recorded packet.
    pub reserved3: u8,
    /// Byte 5, meaning unknown; 0 in every recorded packet.
    pub reserved5: u8,
    /// Byte 8.
    pub source: Device,
    /// Byte 9.
    pub destination: Device,
    /// Bytes 10–11.
    pub opcode: Opcode,
    /// Bytes 12–15 of a 16-byte header; `None` for a 12-byte header.
    pub extension: Option<[u8; 4]>,
}

impl Header {
    /// A 12-byte header with the unknown bytes zero.
    pub const fn new(
        flags: Flags,
        sequence: u8,
        source: Device,
        destination: Device,
        opcode: Opcode,
    ) -> Header {
        Header {
            flags,
            sequence,
            reserved3: 0,
            reserved5: 0,
            source,
            destination,
            opcode,
            extension: None,
        }
    }

    /// The encoded header length: 12, or 16 with an extension.
    pub const fn header_len(&self) -> usize {
        if self.extension.is_some() {
            HEADER_LEN_EXTENDED
        } else {
            HEADER_LEN
        }
    }

    /// The longest payload a packet with this header can carry.
    pub const fn max_payload_len(&self) -> usize {
        PACKET_LEN - self.header_len() - SECTION_LEN
    }
}

/// One 60-byte command or reply.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Packet {
    header: Header,
    payload: Option<Vec<u8>>,
}

impl Packet {
    /// A packet with `header` and, when its flags call for a payload section,
    /// `payload`.
    pub fn new(header: Header, payload: Option<&[u8]>) -> Result<Packet, EncodeError> {
        if payload.is_some() != header.flags.has_payload() {
            return Err(EncodeError::PayloadPresence {
                flags: header.flags,
                payload: payload.is_some(),
            });
        }
        if let Some(p) = payload {
            if p.len() > header.max_payload_len() {
                return Err(EncodeError::PayloadTooLong {
                    len: p.len(),
                    max: header.max_payload_len(),
                });
            }
        }
        Ok(Packet {
            header,
            payload: payload.map(<[u8]>::to_vec),
        })
    }

    /// The header.
    pub fn header(&self) -> &Header {
        &self.header
    }

    /// The payload, or `None` when the packet has no payload section.
    pub fn payload(&self) -> Option<&[u8]> {
        self.payload.as_deref()
    }

    /// The 60 bytes on the wire, with both CRCs computed and zero padding.
    pub fn encode(&self) -> [u8; PACKET_LEN] {
        let h = &self.header;
        let hlen = h.header_len();
        let mut b = [0u8; PACKET_LEN];
        b[0] = MAGIC;
        b[1] = h.flags.0;
        b[2] = h.sequence;
        b[3] = h.reserved3;
        b[4] = hlen as u8;
        b[5] = h.reserved5;
        b[8] = h.source.0;
        b[9] = h.destination.0;
        b[10..12].copy_from_slice(&h.opcode.0.to_le_bytes());
        if let Some(ext) = h.extension {
            b[12..16].copy_from_slice(&ext);
        }
        let crc = crc16_usb_with_hole(&b[..hlen], 6);
        b[6..8].copy_from_slice(&crc.to_le_bytes());
        if let Some(p) = &self.payload {
            let end = hlen + SECTION_LEN + p.len();
            b[hlen..hlen + 2].copy_from_slice(&(p.len() as u16).to_le_bytes());
            b[hlen + SECTION_LEN..end].copy_from_slice(p);
            let crc = crc16_usb_with_hole(&b[hlen..end], 2);
            b[hlen + 2..hlen + 4].copy_from_slice(&crc.to_le_bytes());
        }
        b
    }

    /// Parse and check 60 bytes read from the command selector.
    pub fn decode(bytes: &[u8]) -> Result<Packet, DecodeError> {
        if bytes.len() != PACKET_LEN {
            return Err(DecodeError::Length(bytes.len()));
        }
        if bytes[0] != MAGIC {
            return Err(DecodeError::Magic(bytes[0]));
        }
        let hlen = match bytes[4] as usize {
            n @ (HEADER_LEN | HEADER_LEN_EXTENDED) => n,
            n => return Err(DecodeError::HeaderLength(n as u8)),
        };
        let stored = le16(bytes, 6);
        let computed = crc16_usb_with_hole(&bytes[..hlen], 6);
        if stored != computed {
            return Err(DecodeError::HeaderCrc { stored, computed });
        }
        let header = Header {
            flags: Flags(bytes[1]),
            sequence: bytes[2],
            reserved3: bytes[3],
            reserved5: bytes[5],
            source: Device(bytes[8]),
            destination: Device(bytes[9]),
            opcode: Opcode(le16(bytes, 10)),
            extension: (hlen == HEADER_LEN_EXTENDED)
                .then(|| [bytes[12], bytes[13], bytes[14], bytes[15]]),
        };
        let payload = if header.flags.has_payload() {
            let len = le16(bytes, hlen) as usize;
            let max = header.max_payload_len();
            if len > max {
                return Err(DecodeError::PayloadTooLong { len, max });
            }
            let end = hlen + SECTION_LEN + len;
            let stored = le16(bytes, hlen + 2);
            let computed = crc16_usb_with_hole(&bytes[hlen..end], 2);
            if stored != computed {
                return Err(DecodeError::PayloadCrc { stored, computed });
            }
            Some(bytes[hlen + SECTION_LEN..end].to_vec())
        } else {
            None
        };
        Ok(Packet { header, payload })
    }
}

/// The 60-byte block read from the status selector. Its layout is not yet
/// decoded; this type only fixes its size.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct StatusBlock([u8; PACKET_LEN]);

impl StatusBlock {
    /// Wrap 60 bytes read from [`SELECTOR_STATUS`].
    pub fn from_bytes(bytes: &[u8]) -> Result<StatusBlock, DecodeError> {
        bytes
            .try_into()
            .map(StatusBlock)
            .map_err(|_| DecodeError::Length(bytes.len()))
    }

    /// The raw bytes.
    pub fn as_bytes(&self) -> &[u8; PACKET_LEN] {
        &self.0
    }
}

/// Why [`Packet::new`] refused a header and payload.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Error)]
pub enum EncodeError {
    /// A payload was given for flags without a payload section, or none for
    /// flags with one.
    #[error("flags {flags:?} and payload presence ({payload}) disagree")]
    PayloadPresence {
        /// The header's flags.
        flags: Flags,
        /// Whether a payload was given.
        payload: bool,
    },
    /// The payload does not fit in the packet.
    #[error("payload of {len} bytes exceeds the {max} that fit")]
    PayloadTooLong {
        /// Payload length given.
        len: usize,
        /// Longest that fits after this header.
        max: usize,
    },
}

/// Why [`Packet::decode`] or [`StatusBlock::from_bytes`] rejected some bytes.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Error)]
pub enum DecodeError {
    /// The input is not 60 bytes long.
    #[error("expected {PACKET_LEN} bytes, got {0}")]
    Length(usize),
    /// Byte 0 is not `0xaa`.
    #[error("bad magic byte {0:#04x}")]
    Magic(u8),
    /// Byte 4 is neither 12 nor 16.
    #[error("unsupported header length {0}")]
    HeaderLength(u8),
    /// Bytes 6–7 do not match the header.
    #[error("header CRC {stored:#06x}, computed {computed:#06x}")]
    HeaderCrc {
        /// CRC carried in the packet.
        stored: u16,
        /// CRC computed over the header.
        computed: u16,
    },
    /// The payload length runs past the end of the packet.
    #[error("payload length {len} exceeds the {max} that fit")]
    PayloadTooLong {
        /// Payload length carried in the packet.
        len: usize,
        /// Longest that fits after this header.
        max: usize,
    },
    /// The payload section's CRC does not match.
    #[error("payload CRC {stored:#06x}, computed {computed:#06x}")]
    PayloadCrc {
        /// CRC carried in the packet.
        stored: u16,
        /// CRC computed over the payload section.
        computed: u16,
    },
}

/// A product the vendor library was traced as (factory/oracle/commands).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct TracedProduct {
    /// USB product ID; the vendor ID is 0x3564 for all of them.
    pub product_id: u16,
    /// Product type the vendor library reported for this ID.
    pub product_type: u8,
    /// Evidence grade of the trace (ADR-100 D5).
    pub grade: &'static str,
}

/// A named command and the products whose traces showed it.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct CommandInfo {
    /// The vendor library's command name, such as `CAM_GET_WDR_MODE`.
    pub name: &'static str,
    /// The vendor library's command-set name, such as `CMD_SET_CAMERA`.
    pub libdev_set: &'static str,
    /// The opcode on the wire.
    pub opcode: Opcode,
    /// The device the request was addressed to.
    pub destination: Device,
    /// The flags the vendor library sent the request with.
    pub request_flags: Flags,
    /// USB product IDs of the [`TracedProduct`]s that sent it.
    pub products: &'static [u16],
}

/// A request the vendor library sent without logging a command name.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct UnloggedRequest {
    /// The opcode on the wire.
    pub opcode: Opcode,
    /// The device the request was addressed to.
    pub destination: Device,
    /// The flags the vendor library sent the request with.
    pub request_flags: Flags,
    /// USB product IDs of the [`TracedProduct`]s that sent it.
    pub products: &'static [u16],
}
