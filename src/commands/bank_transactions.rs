//! `zb bank-transactions` — CRUD + match/unmatch/exclude/restore/uncategorize
//! + categorize sub-app + statements sub-app.
//!
//! Generic categorize body (verified against Zoho v3 docs): the manual
//! `categorize generic` endpoint is double-entry and requires
//! `transaction_type` + `from_account_id` + `to_account_id` + `amount` +
//! `date`. `transaction_type` ∈ {deposit, refund (credit-card only),
//! transfer_fund, card_payment, sales_without_invoices, expense_refund,
//! owner_contribution, interest_income, other_income, owner_drawings,
//! sales_return}. expense / vendor_payment / customer_payment are rejected
//! here and route through the dedicated categorize sub-commands instead.

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
    /// Manual ("generic") categorization (POST .../categorize).
    ///
    /// This posts a double-entry transaction, so the body needs BOTH accounts
    /// plus the type, amount, and date. A single `account_id` is NOT a valid
    /// field (that mistake yields "Invalid value passed for Transaction Type"
    /// or "Account does not exist"):
    ///
    ///   --body '{"transaction_type":"other_income",
    ///            "from_account_id":"<source_account_id>",
    ///            "to_account_id":"<bank_account_id>",
    ///            "amount":100.0,"date":"YYYY-MM-DD"}'
    ///
    /// `from_account_id` is where the money came from; `to_account_id` is where
    /// it landed. For money arriving in the bank (deposit, interest_income,
    /// other_income, owner_contribution, sales_without_invoices) the bank
    /// account is `to_account_id`; for money leaving it (owner_drawings,
    /// card_payment, transfer_fund) the bank account is `from_account_id`.
    ///
    /// transaction_type is one of: deposit, refund (credit-card accounts only),
    /// transfer_fund, card_payment, sales_without_invoices, expense_refund,
    /// owner_contribution, interest_income, other_income, owner_drawings,
    /// sales_return. Categorizing as an expense, vendor payment, or customer
    /// payment is NOT supported here: use `categorize expense`,
    /// `categorize vendor-payment`, or `categorize customer-payment`.
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn list_targets_banktransactions() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/banktransactions")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"banktransactions":[]}"#)
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
