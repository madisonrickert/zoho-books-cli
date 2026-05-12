use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::errors::{Result, ZohoError};

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    #[command(name = "__unimplemented", hide = true)]
    Unimplemented,
}

pub fn run(_cmd: Cmd, _ctx: &mut Ctx) -> Result<()> {
    Err(ZohoError::validation(
        "recurring-expenses not yet implemented in the Rust port",
    ))
}
