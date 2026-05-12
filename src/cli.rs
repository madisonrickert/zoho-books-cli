use clap::{Parser, Subcommand, ValueEnum};

use crate::commands;

#[derive(Parser, Debug)]
#[command(
    name = "zb",
    version,
    about = "Agent-first CLI for Zoho Books",
    long_about = "Thin 1:1 wrapper around Zoho Books v3, designed to be driven by Claude Code agents. JSON envelopes on stdout, JSON errors on stderr, stable exit codes."
)]
pub struct Cli {
    /// Output format
    #[arg(long, global = true, value_enum, default_value_t = OutputFormat::Json)]
    pub format: OutputFormat,

    /// Legacy alias for --format table
    #[arg(long, global = true)]
    pub pretty: bool,

    /// Print the would-be HTTP request as JSON and exit; do not call Zoho
    #[arg(long, global = true)]
    pub dry_run: bool,

    /// Emit the full command tree as JSON and exit
    #[arg(long)]
    pub list_commands: bool,

    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
pub enum OutputFormat {
    Json,
    Yaml,
    Table,
    Csv,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// Authentication: login, refresh, status, logout
    Auth(commands::auth_cmd::Cmd),
    /// Organization selection and metadata
    Org(commands::org::Cmd),
    /// Escape hatch — send any Zoho v3 request
    Raw(commands::raw::Cmd),
    /// Contacts: CRUD, addresses, persons, activation
    Contacts(commands::contacts::Cmd),
    /// Expenses: CRUD, receipts, attachments, comments
    Expenses(commands::expenses::Cmd),
    /// Invoices: CRUD, status, payments, credits, comments, documents, attachments, templates
    Invoices(commands::invoices::Cmd),
    /// Bills: CRUD, payments, attachments, status, email
    Bills(commands::bills::Cmd),
    /// Projects: CRUD, users, tasks, clone, comments
    Projects(commands::projects::Cmd),
    /// Customer payments and refunds
    #[command(name = "customer-payments")]
    CustomerPayments(commands::customer_payments::Cmd),
    /// Recurring expenses: CRUD, stop, resume, children, history
    #[command(name = "recurring-expenses")]
    RecurringExpenses(commands::recurring_expenses::Cmd),
    /// Recurring invoices: CRUD, stop, resume, history, templates
    #[command(name = "recurring-invoices")]
    RecurringInvoices(commands::recurring_invoices::Cmd),
    /// Bank transactions: CRUD, match, categorize, exclude, statements
    #[command(name = "bank-transactions")]
    BankTransactions(commands::bank_transactions::Cmd),
    /// Bank rules (auto-categorization)
    #[command(name = "bank-rules")]
    BankRules(commands::bank_rules::Cmd),
    /// Chart of accounts
    #[command(name = "chart-of-accounts")]
    ChartOfAccounts(commands::chart_of_accounts::Cmd),
}

pub fn run(cli: Cli) {
    if cli.list_commands {
        println!("{{\"ok\": true, \"data\": {{\"commands\": []}}}}");
        return;
    }
    match cli.command {
        None => {
            eprintln!("zb: no subcommand given. Try `zb --help`.");
            std::process::exit(3);
        }
        Some(Commands::Auth(c)) => commands::auth_cmd::run(c),
        Some(Commands::Org(c)) => commands::org::run(c),
        Some(Commands::Raw(c)) => commands::raw::run(c),
        Some(Commands::Contacts(c)) => commands::contacts::run(c),
        Some(Commands::Expenses(c)) => commands::expenses::run(c),
        Some(Commands::Invoices(c)) => commands::invoices::run(c),
        Some(Commands::Bills(c)) => commands::bills::run(c),
        Some(Commands::Projects(c)) => commands::projects::run(c),
        Some(Commands::CustomerPayments(c)) => commands::customer_payments::run(c),
        Some(Commands::RecurringExpenses(c)) => commands::recurring_expenses::run(c),
        Some(Commands::RecurringInvoices(c)) => commands::recurring_invoices::run(c),
        Some(Commands::BankTransactions(c)) => commands::bank_transactions::run(c),
        Some(Commands::BankRules(c)) => commands::bank_rules::run(c),
        Some(Commands::ChartOfAccounts(c)) => commands::chart_of_accounts::run(c),
    }
}
