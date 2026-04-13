//! obsbotctl-core — open control library for OBSBOT cameras.
//!
//! This crate is the protocol + transport + catalog layer. It is UI-agnostic
//! and daemon-agnostic: a reference D-Bus server (`obsbotd`) and a reference
//! CLI (`obsbotctl`) are built on top of it in the same workspace.
//!
//! # Scaffold phase
//!
//! Nothing is implemented yet. See `docs/architecture.md` for the intended
//! layering and `docs/investigation/` for the reverse engineering notes that
//! seed the protocol layer.

#![deny(rust_2018_idioms)]

use thiserror::Error;

/// Library version string (pulled from Cargo.toml).
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Result alias used throughout the crate.
pub type Result<T> = std::result::Result<T, Error>;

/// Errors raised by obsbotctl-core.
#[derive(Debug, Error)]
pub enum Error {
    /// The requested device was not found on the system.
    #[error("device not found")]
    NotFound,

    /// The device exists but does not support the requested operation.
    #[error("operation not supported by this device")]
    NotSupported,

    /// Underlying transport I/O failure.
    #[error("transport I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// Operation is not yet implemented in this scaffold.
    #[error("not implemented in scaffold phase")]
    NotImplemented,
}

/// Device catalog — maps (USB VID, PID) tuples to model identity and
/// per-model capability profiles.
///
/// See `docs/devices.md` for the intended coverage list.
pub mod catalog {
    // to be populated
}

/// Transport layer — get bytes on and off the device.
///
/// Planned backends:
/// - UVC extension unit over `UVCIOC_CTRL_QUERY`
/// - V4L2 standard controls (brightness, contrast, PTZ, focus)
/// - Bluetooth RFCOMM (Tail Air)
pub mod transport {
    // to be populated
}

/// Protocol layer — encode and decode camera wire commands.
///
/// OBSBOT cameras expose several logical services:
///
/// - Camera control — PTZ, focus, exposure, white balance, HDR
/// - AI services — tracking, auto-framing, gimbal, gesture
/// - System management — LEDs, buzzer, WiFi (WiFi-equipped models)
/// - Event stream — async notifications
pub mod protocol {
    // to be populated
}
