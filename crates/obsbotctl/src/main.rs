//! obsbotctl — command-line tool for OBSBOT cameras, built on the `obsbot` library.
//!
//! # Scaffold phase
//!
//! Prints a banner and exits. The intended shape is a small subcommand
//! dispatcher that calls the library directly, so it works without `obsbotd`:
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
    println!("obsbotctl scaffold (version {})", obsbot::VERSION);
}
