mod cli;
mod commands;

use clap::Parser;

fn main() {
    let parsed = cli::Cli::parse();
    cli::run(parsed);
}
