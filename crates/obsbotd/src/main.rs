//! obsbotd — D-Bus system daemon for OBSBOT camera control.
//!
//! # Scaffold phase
//!
//! This binary is a no-op skeleton that prints a banner and exits. The
//! intended runtime shape is:
//!
//! 1. Register `com.obsbot.Control1` on the system bus (via `zbus`).
//! 2. Listen for udev hotplug events matching OBSBOT USB VID/PIDs.
//! 3. Publish one D-Bus object per connected camera under
//!    `/com/obsbot/Control1/Device/N`, with properties for model/capabilities
//!    and methods for PTZ, focus, HDR, AI mode.
//! 4. Forward `REMO_*` events from the camera as D-Bus signals.

#![deny(rust_2018_idioms)]

use tracing::info;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    info!(
        version = obsbot::VERSION,
        "obsbotd scaffold — daemon shell only, nothing to do yet"
    );
}
