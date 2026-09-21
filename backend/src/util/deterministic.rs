//! Deterministic random number utilities.
//!
//! This module provides helpers to create a reproducible random number generator
//! from a simple `u64` seed. It is useful for generating deterministic data in
//! tests, simulations, or any scenario where repeatability is required.

use rand::rngs::StdRng;
use rand::{RngCore, SeedableRng};

/// Create a `StdRng` seeded with the given `u64`.
///
/// `StdRng` expects a 32‑byte seed. We expand the supplied `u64` by copying it
/// into the first 8 bytes of the seed array and zero‑filling the rest. This
/// approach guarantees that the same `seed` always yields the same RNG state.
pub fn seeded_rng(seed: u64) -> StdRng {
    let mut seed_bytes = [0u8; 32];
    seed_bytes[0..8].copy_from_slice(&seed.to_le_bytes());
    StdRng::from_seed(seed_bytes)
}

/// Generate a deterministic `u64` value from the provided `seed`.
///
/// This is a thin wrapper around `seeded_rng` that immediately draws a single
/// `u64` from the RNG. The function is pure: given the same `seed` it will
/// always return the same output.
pub fn deterministic_u64(seed: u64) -> u64 {
    let mut rng = seeded_rng(seed);
    rng.next_u64()
}

/// Generate a deterministic `f64` in the range `[0, 1)` from the provided `seed`.
///
/// Useful for reproducible floating‑point data such as probabilities or
/// normalized values.
pub fn deterministic_f64(seed: u64) -> f64 {
    let mut rng = seeded_rng(seed);
    // `next_u64` yields a full 64‑bit integer; we convert it to a float in [0,1).
    const MAX_U64_PLUS_ONE: f64 = (u64::MAX as f64) + 1.0;
    (rng.next_u64() as f64) / MAX_U64_PLUS_ONE
}
