//! One module per Zoho v3 resource. Each module exposes a clap `Args`-derived
//! `Cmd` struct (which wraps a `Sub` `Subcommand` enum), a `pub fn run(cmd:
//! Cmd, ctx: &mut Ctx) -> Result<()>` for dispatch, and inline tests.
//!
//! The shared kit at `common.rs` (arg structs + request-building + emit
//! shortcuts) keeps every domain module focused on endpoint mapping.

pub mod auth_cmd;
pub mod bank_rules;
pub mod bank_transactions;
pub mod bills;
pub mod chart_of_accounts;
pub mod common;
pub mod contacts;
pub mod customer_payments;
pub mod documents;
pub mod expenses;
pub mod invoices;
pub mod org;
pub mod projects;
pub mod raw;
pub mod recurring_expenses;
pub mod recurring_invoices;
