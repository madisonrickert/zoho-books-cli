mod cli;
mod commands;
mod config;
mod errors;
mod regions;
mod storage;
mod uploads;

use clap::Parser;

fn main() {
    let parsed = cli::Cli::parse();
    cli::run(parsed);
}
