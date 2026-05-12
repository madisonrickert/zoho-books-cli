mod cli;
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
    cli::run(parsed);
}
