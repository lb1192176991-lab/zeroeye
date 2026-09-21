//! Command line interface definitions for Kickama.
//! This module defines the CLI arguments using `clap` and provides a
//! conversion into the internal `Config` structure.

use clap::Parser;
use crate::config::Config;

/// Kickama command line arguments.
#[derive(Debug, Parser)]
#[command(name = "kickama")]
#[command(author = "Kickama Contributors")]
#[command(version, about = "Kickama – a risk‑trading platform", long_about = None)]
pub struct Cli {
    /// Activate dry‑run mode. No state‑changing operations will be persisted.
    #[arg(long, env = "KICKAMA_DRY_RUN", default_value_t = false)]
    pub dry_run: bool,

    /// Optional path to a custom configuration file.
    #[arg(short, long, env = "KICKAMA_CONFIG")]
    pub config: Option<String>,

    /// Verbosity level (can be used multiple times, e.g. -vv)
    #[arg(short, long, action = clap::ArgAction::Count)]
    pub verbose: u8,
}

impl Cli {
    /// Convert the parsed CLI arguments into a `Config` instance.
    ///
    /// This merges CLI flags with the configuration loaded from a file
    /// (if any) and environment variables.
    pub fn into_config(self) -> Config {
        // Load base configuration from file or defaults.
        let mut cfg = match self.config {
            Some(path) => Config::from_file(&path).unwrap_or_default(),
            None => Config::default(),
        };

        // Override with CLI supplied values.
        cfg.dry_run = self.dry_run;
        cfg.verbosity = self.verbose;

        cfg
    }
}
