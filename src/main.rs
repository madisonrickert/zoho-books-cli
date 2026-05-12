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
    install_panic_hook();
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

/// Catch panics and emit an `unknown` error envelope so the CLI's stable output
/// contract holds even when an internal invariant breaks. Without this, Rust's
/// default panic handler prints a multi-line "thread 'main' panicked..." trace
/// to stderr — useful for developers but not what agents parse.
fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .copied()
            .or_else(|| info.payload().downcast_ref::<String>().map(String::as_str))
            .unwrap_or("internal panic");
        let location = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_else(|| "unknown".into());
        let err = errors::ZohoError::new(
            errors::ErrorKind::Unknown,
            format!("internal panic at {location}: {message}"),
        );
        cli::emit_dispatch_error(&err, cli::OutputFormat::Json);
        std::process::exit(err.exit_code());
    }));
}
