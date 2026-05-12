use clap::{Args, Subcommand};

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

pub fn run(_cmd: Cmd) {
    eprintln!("zb: org not yet implemented in the Rust port");
    std::process::exit(2);
}
