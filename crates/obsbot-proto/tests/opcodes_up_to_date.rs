//! Fails when src/opcodes.rs differs from what factory/proto_tables.py
//! generates from the committed factory data.
//!
//! The factory directory is outside the crate, so a packaged copy of the crate
//! has no generator to compare with; the test then reports itself skipped.

use std::path::Path;
use std::process::Command;

#[test]
fn opcodes_rs_matches_factory_data() {
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../factory/proto_tables.py");
    if !script.exists() {
        eprintln!("SKIPPED: {} not found (packaged crate)", script.display());
        return;
    }
    let out = Command::new("python3")
        .arg("-I")
        .arg(&script)
        .arg("--check")
        .output()
        .expect("python3 runs");
    assert!(
        out.status.success(),
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}
