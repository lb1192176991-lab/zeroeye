//! Tests for the deterministic random utilities.

#[cfg(test)]
mod tests {
    use crate::util::deterministic::{deterministic_f64, deterministic_u64};

    #[test]
    fn deterministic_u64_is_repeatable() {
        let seed = 0xDEADBEEFCAFEBABE;
        let first = deterministic_u64(seed);
        let second = deterministic_u64(seed);
        assert_eq!(first, second, "Deterministic u64 should be repeatable for the same seed");
    }

    #[test]
    fn deterministic_f64_is_repeatable_and_in_range() {
        let seed = 42u64;
        let value = deterministic_f64(seed);
        assert!(
            (0.0..1.0).contains(&value),
            "Deterministic f64 should be in [0, 1) range"
        );

        // Re‑run with the same seed and ensure the value matches.
        let value_again = deterministic_f64(seed);
        assert_eq!(value, value_again, "Deterministic f64 should be repeatable for the same seed");
    }

    #[test]
    fn different_seeds_produce_different_values() {
        let seed_a = 1u64;
        let seed_b = 2u64;
        assert_ne!(
            deterministic_u64(seed_a),
            deterministic_u64(seed_b),
            "Different seeds should yield different deterministic u64 values"
        );
        assert_ne!(
            deterministic_f64(seed_a),
            deterministic_f64(seed_b),
            "Different seeds should yield different deterministic f64 values"
        );
    }
}
