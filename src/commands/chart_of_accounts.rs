//! `zb chart-of-accounts` — CRUD over `/chartofaccounts` plus mark-active /
//! mark-inactive and a nested `transactions` sub-app (list + delete).

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, ListArgs};
use crate::errors::Result;

const BASE: &str = "/chartofaccounts";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List chart-of-accounts accounts.
    List(ListArgs),
    /// Create a chart-of-accounts account.
    Create(BodyArgs),
    /// Get a single chart-of-accounts account by ID.
    Get(IdArgs),
    /// Update a chart-of-accounts account by ID.
    Update(UpdateArgs),
    /// Delete a chart-of-accounts account by ID.
    Delete(IdArgs),
    /// Mark an account as active.
    #[command(name = "mark-active")]
    MarkActive(IdArgs),
    /// Mark an account as inactive.
    #[command(name = "mark-inactive")]
    MarkInactive(IdArgs),
    /// Transactions posted to chart-of-accounts accounts.
    Transactions(TransactionsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    /// Zoho Books account_id.
    pub account_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub account_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct TransactionsCmd {
    #[command(subcommand)]
    pub sub: TransactionsSub,
}

#[derive(Subcommand, Debug)]
pub enum TransactionsSub {
    /// List transactions posted to chart-of-accounts accounts.
    List(ListArgs),
    /// Delete a manually-posted chart-of-accounts transaction.
    Delete(TransactionIdArgs),
}

#[derive(Args, Debug)]
pub struct TransactionIdArgs {
    /// Zoho Books transaction_id.
    pub transaction_id: String,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "chartofaccounts"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.account_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.account_id), &args.body)
        }
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.account_id);
            common::delete(ctx, &path, "account_id", &args.account_id)
        }
        Sub::MarkActive(args) => {
            let path = format!("{BASE}/{}/active", args.account_id);
            common::action(ctx, &path, "account_id", &args.account_id)
        }
        Sub::MarkInactive(args) => {
            let path = format!("{BASE}/{}/inactive", args.account_id);
            common::action(ctx, &path, "account_id", &args.account_id)
        }
        Sub::Transactions(t) => match t.sub {
            TransactionsSub::List(args) => {
                common::list(ctx, &format!("{BASE}/transactions"), &args, "transactions")
            }
            TransactionsSub::Delete(args) => {
                let path = format!("{BASE}/transactions/{}", args.transaction_id);
                common::delete(ctx, &path, "transaction_id", &args.transaction_id)
            }
        },
    }
}
