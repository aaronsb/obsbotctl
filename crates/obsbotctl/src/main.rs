//! obsbotctl — command-line client for the obsbotd D-Bus service.
//!
//! # Scaffold phase
//!
//! Prints a banner and exits. The intended shape is a small subcommand
//! dispatcher that talks to `obsbotd` over D-Bus:
//!
//! ```text
//! obsbotctl list                      # enumerate managed cameras
//! obsbotctl status [device]           # current state
//! obsbotctl focus auto | <0..100>
//! obsbotctl hdr on | off
//! obsbotctl ai none|group|human|hand|whiteboard|desk
//! obsbotctl pan <delta>   | tilt <delta>   | zoom <factor>
//! ```

#![deny(rust_2018_idioms)]

fn main() {
    println!("obsbotctl scaffold (version {})", obsbotctl_core::VERSION);
}
