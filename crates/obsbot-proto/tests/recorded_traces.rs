//! Decodes every command and reply in the factory oracle's local raw traces.
//!
//! The traces hold the attached camera's serial number, so they live outside
//! the repository, in `$OBSBOT_FACTORY_WORK/oracle/traces` (default
//! `~/.cache/libobsbot/factory/oracle/traces`). Without them the test reports
//! itself skipped; the committed fixtures in tests/codec.rs cover the same
//! packet shapes.
//!
//! Each `xu` line for unit 2, selector 2, whose data starts with `0xaa` and has a 12-
//! or 16-byte header must decode, and re-encoding it must reproduce every byte
//! the CRCs cover. Packets the library sends for products it does not
//! recognise (header length 0) and all-zero reads are counted, not decoded.

use std::path::PathBuf;

use obsbot_proto::Packet;

fn traces_dir() -> Option<PathBuf> {
    let work = std::env::var_os("OBSBOT_FACTORY_WORK")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".cache/libobsbot/factory"))
        })?;
    let dir = work.join("oracle/traces");
    dir.is_dir().then_some(dir)
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(s.get(i..i + 2)?, 16).ok())
        .collect()
}

#[test]
fn every_recorded_packet_decodes() {
    let Some(dir) = traces_dir() else {
        eprintln!("SKIPPED: no oracle traces on this machine");
        return;
    };
    let (mut decoded, mut other) = (0usize, 0usize);
    let mut logs: Vec<PathBuf> = Vec::new();
    for sdk in std::fs::read_dir(&dir).unwrap() {
        for f in std::fs::read_dir(sdk.unwrap().path()).unwrap() {
            let p = f.unwrap().path();
            if p.extension().is_some_and(|e| e == "log") {
                logs.push(p);
            }
        }
    }
    for log in &logs {
        let text = std::fs::read_to_string(log).unwrap();
        for line in text.lines() {
            if !line.contains(" xu ") || !line.contains(" unit=2 sel=2 ") {
                continue;
            }
            let Some(data) = line.split("data=").nth(1).filter(|d| !d.is_empty()) else {
                continue;
            };
            let bytes = unhex(data).expect("trace data is hex");
            if bytes.len() != 60 || bytes[0] != 0xaa || !matches!(bytes[4], 12 | 16) {
                other += 1;
                continue;
            }
            let packet =
                Packet::decode(&bytes).unwrap_or_else(|e| panic!("{}: {e}: {data}", log.display()));
            let hlen = bytes[4] as usize;
            let covered = match packet.payload() {
                Some(p) => hlen + 4 + p.len(),
                None => hlen,
            };
            assert_eq!(
                packet.encode()[..covered],
                bytes[..covered],
                "{}: {data}",
                log.display()
            );
            decoded += 1;
        }
    }
    eprintln!(
        "decoded {decoded} packets from {} trace files; {other} other selector-2 blocks",
        logs.len()
    );
    assert!(decoded > 0, "traces found but no packets decoded");
}
