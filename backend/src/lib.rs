//! Main library entry point for the Kickama backend.
//!
//! This file re‑exports the public modules that are intended for external use.
//! Adding the `util` module here makes the deterministic helpers available to
//! the rest of the codebase and to downstream crates.

pub mod ai;
pub mod config;
pub mod connector;
pub mod discovery;
pub mod legacy;
pub mod messaging;
pub mod protocol;
pub mod registry;

// New utility module
pub mod util;
