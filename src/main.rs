mod auth;
mod cli;
mod client;
mod commands;
mod config;
mod errors;
mod output;
mod regions;
mod shared;
mod storage;
mod uploads;

use clap::Parser;

fn main() {
    let parsed = cli::Cli::parse();
    let format = cli::effective_format(&parsed);
    let exit = match cli::run(parsed) {
        Ok(()) => 0,
        Err(e) if cli::is_dry_run_ok(&e) => 0,
        Err(e) => {
            cli::emit_dispatch_error(&e, format);
            e.exit_code()
        }
    };
    std::process::exit(exit);
}
