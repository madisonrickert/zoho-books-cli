//! `zb bank-rules` — CRUD over `/bankaccounts/rules`. Bank rules drive
//! auto-categorization of imported transactions. List requires an `account_id`
//! query param.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, ListArgs};
use crate::errors::Result;

const BASE: &str = "/bankaccounts/rules";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List bank rules. Requires --query account_id=...
    List(ListArgs),
    /// Create a bank rule.
    Create(BodyArgs),
    /// Get a single bank rule by ID.
    Get(IdArgs),
    /// Update a bank rule by ID.
    Update(UpdateArgs),
    /// Delete a bank rule by ID.
    Delete(IdArgs),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    /// Zoho Books rule_id.
    pub rule_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub rule_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "rules"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.rule_id)),
        Sub::Update(args) => common::update(ctx, &format!("{BASE}/{}", args.rule_id), &args.body),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.rule_id);
            common::delete(ctx, &path, "rule_id", &args.rule_id)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn list_targets_bankaccounts_rules() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/bankaccounts/rules")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"rules":[]}"#)
            .create();
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::List(ListArgs::default()),
            },
            &mut ctx,
        )
        .unwrap();
        m.assert();
    }
}
