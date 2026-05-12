//! `zb bank-transactions` — CRUD + match/unmatch/exclude/restore/uncategorize
//! + categorize sub-app + statements sub-app.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, ListArgs};
use crate::errors::Result;

const BASE: &str = "/banktransactions";
const UNCAT_PREFIX: &str = "/banktransactions/uncategorized";
const TID: &str = "transaction_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    List(ListArgs),
    Create(BodyArgs),
    Get(IdArgs),
    Update(UpdateArgs),
    Delete(IdArgs),
    /// Match an uncategorized transaction (POST .../uncategorized/{id}/match).
    Match(MatchArgs),
    /// List candidate matching transactions (GET .../uncategorized/{id}/match).
    Matches(MatchesArgs),
    /// Unmatch a matched transaction (POST /banktransactions/{id}/unmatch).
    Unmatch(IdArgs),
    /// Exclude a transaction (POST .../uncategorized/{id}/exclude).
    Exclude(IdArgs),
    /// Restore an excluded transaction (POST .../uncategorized/{id}/restore).
    Restore(IdArgs),
    /// Uncategorize a categorized transaction.
    Uncategorize(IdArgs),
    /// Categorize sub-app (one subcommand per target type).
    Categorize(CategorizeCmd),
    /// Bulk bank statement import operations.
    Statements(StatementsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub transaction_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub transaction_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct MatchArgs {
    pub transaction_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct MatchesArgs {
    pub transaction_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct CategorizeCmd {
    #[command(subcommand)]
    pub sub: CategorizeSub,
}

#[derive(Subcommand, Debug)]
pub enum CategorizeSub {
    /// Manual categorization (POST .../categorize).
    Generic(CategorizeArgs),
    /// POST .../categorize/expenses
    Expense(CategorizeArgs),
    /// POST .../categorize/vendorpayments
    #[command(name = "vendor-payment")]
    VendorPayment(CategorizeArgs),
    /// POST .../categorize/customerpayments
    #[command(name = "customer-payment")]
    CustomerPayment(CategorizeArgs),
    /// POST .../categorize/creditnoterefunds
    #[command(name = "credit-note-refund")]
    CreditNoteRefund(CategorizeArgs),
    /// POST .../categorize/vendorcreditrefunds
    #[command(name = "vendor-credit-refund")]
    VendorCreditRefund(CategorizeArgs),
    /// POST .../categorize/paymentrefunds
    #[command(name = "payment-refund")]
    PaymentRefund(CategorizeArgs),
    /// POST .../categorize/vendorpaymentrefunds
    #[command(name = "vendor-payment-refund")]
    VendorPaymentRefund(CategorizeArgs),
}

#[derive(Args, Debug)]
pub struct CategorizeArgs {
    pub transaction_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct StatementsCmd {
    #[command(subcommand)]
    pub sub: StatementsSub,
}

#[derive(Subcommand, Debug)]
pub enum StatementsSub {
    /// Import a bank/credit-card statement (POST /bankstatements).
    Import(BodyArgs),
    /// Fetch the last imported statement for an account.
    #[command(name = "last-imported")]
    LastImported(AccountIdArgs),
    /// Delete a specific imported statement.
    Delete(StatementDeleteArgs),
}

#[derive(Args, Debug)]
pub struct AccountIdArgs {
    pub account_id: String,
}

#[derive(Args, Debug)]
pub struct StatementDeleteArgs {
    pub account_id: String,
    pub statement_id: String,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "banktransactions"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.transaction_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.transaction_id), &args.body)
        }
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.transaction_id);
            common::delete(ctx, &path, TID, &args.transaction_id)
        }
        Sub::Match(args) => {
            let path = format!("{UNCAT_PREFIX}/{}/match", args.transaction_id);
            common::action_with_body(ctx, &path, &args.body, TID, &args.transaction_id)
        }
        Sub::Matches(args) => {
            let path = format!("{UNCAT_PREFIX}/{}/match", args.transaction_id);
            common::list(ctx, &path, &args.list, "matching_transactions")
        }
        Sub::Unmatch(args) => {
            let path = format!("{BASE}/{}/unmatch", args.transaction_id);
            common::action(ctx, &path, TID, &args.transaction_id)
        }
        Sub::Exclude(args) => {
            let path = format!("{UNCAT_PREFIX}/{}/exclude", args.transaction_id);
            common::action(ctx, &path, TID, &args.transaction_id)
        }
        Sub::Restore(args) => {
            let path = format!("{UNCAT_PREFIX}/{}/restore", args.transaction_id);
            common::action(ctx, &path, TID, &args.transaction_id)
        }
        Sub::Uncategorize(args) => {
            let path = format!("{BASE}/{}/uncategorize", args.transaction_id);
            common::action(ctx, &path, TID, &args.transaction_id)
        }
        Sub::Categorize(c) => match c.sub {
            CategorizeSub::Generic(args) => categorize(ctx, &args, ""),
            CategorizeSub::Expense(args) => categorize(ctx, &args, "expenses"),
            CategorizeSub::VendorPayment(args) => categorize(ctx, &args, "vendorpayments"),
            CategorizeSub::CustomerPayment(args) => categorize(ctx, &args, "customerpayments"),
            CategorizeSub::CreditNoteRefund(args) => categorize(ctx, &args, "creditnoterefunds"),
            CategorizeSub::VendorCreditRefund(args) => {
                categorize(ctx, &args, "vendorcreditrefunds")
            }
            CategorizeSub::PaymentRefund(args) => categorize(ctx, &args, "paymentrefunds"),
            CategorizeSub::VendorPaymentRefund(args) => {
                categorize(ctx, &args, "vendorpaymentrefunds")
            }
        },
        Sub::Statements(s) => match s.sub {
            StatementsSub::Import(args) => common::create(ctx, "/bankstatements", &args),
            StatementsSub::LastImported(args) => common::get(
                ctx,
                &format!("/bankaccounts/{}/statement/lastimported", args.account_id),
            ),
            StatementsSub::Delete(args) => {
                let path = format!(
                    "/bankaccounts/{}/statement/{}",
                    args.account_id, args.statement_id
                );
                common::delete(ctx, &path, "statement_id", &args.statement_id)
            }
        },
    }
}

fn categorize(ctx: &mut Ctx, args: &CategorizeArgs, suffix: &str) -> Result<()> {
    let path = if suffix.is_empty() {
        format!("{UNCAT_PREFIX}/{}/categorize", args.transaction_id)
    } else {
        format!("{UNCAT_PREFIX}/{}/categorize/{suffix}", args.transaction_id)
    };
    common::action_with_body(ctx, &path, &args.body, TID, &args.transaction_id)
}
