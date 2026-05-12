use std::io::{self, Write};
use std::sync::Arc;

use clap::{Parser, Subcommand, ValueEnum};
use serde_json::json;

use crate::client::Client;
use crate::commands;
use crate::config::{self, Overrides};
use crate::errors::{ErrorKind, Result, ZohoError};
use crate::output;
use crate::storage::{RealStorage, Storage};

#[derive(Parser, Debug)]
#[command(
    name = "zb",
    version,
    disable_version_flag = true,
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

    /// Show the CLI version as JSON and exit
    #[arg(long)]
    pub version: bool,

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

/// Shared context every command receives. Holds the HTTP client (which carries
/// the resolved RuntimeConfig + active access token), the underlying storage
/// (for commands that persist state like `org use`), and the output format.
///
/// `storage` is an `Arc<dyn Storage>` shared with the client — both refer to
/// the same on-disk file + keyring slot, so a token refresh inside a request
/// is immediately visible to commands that read storage afterwards. Storage
/// trait methods take `&self`, so concurrent Arc-clones are safe.
pub struct Ctx {
    pub client: Client,
    pub storage: Arc<dyn Storage>,
    pub format: OutputFormat,
}

impl Ctx {
    /// Test helper: build a Ctx pointing at a mockito server URL. Production
    /// code never calls this. The storage is in-memory; the client is wired
    /// with a fake access token that's far enough in the future to skip the
    /// refresh check, and both api_url and accounts_url are overridden to the
    /// server URL so all HTTP traffic stays on the local mock.
    #[cfg(test)]
    pub fn new_for_test(server_url: &str) -> Self {
        use crate::storage::MemoryStorage;
        let region = crate::regions::resolve("us").unwrap();
        let cfg = crate::config::RuntimeConfig {
            region,
            org_id: Some("123".into()),
            client_id: Some("cid".into()),
            client_secret: Some("csec".into()),
            refresh_token: Some("rt".into()),
            access_token: Some("at".into()),
            // Far future so ensure_access_token skips the refresh path.
            expires_at: Some(
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_secs_f64() + 3600.0)
                    .unwrap_or(3600.0),
            ),
        };
        let storage: Arc<dyn Storage> = Arc::new(MemoryStorage::new());
        let client = Client::new(cfg, Arc::clone(&storage), false, OutputFormat::Json)
            .unwrap()
            .with_api_override(server_url);
        Ctx {
            client,
            storage,
            format: OutputFormat::Json,
        }
    }

    /// Like `new_for_test`, but with `dry_run = true`. Used to verify that
    /// composed commands which loop with per-iteration error handlers
    /// propagate `DryRunOk` and short-circuit (invariants 12 + 14).
    #[cfg(test)]
    pub fn new_for_test_dry_run(server_url: &str) -> Self {
        use crate::storage::MemoryStorage;
        let region = crate::regions::resolve("us").unwrap();
        let cfg = crate::config::RuntimeConfig {
            region,
            org_id: Some("123".into()),
            client_id: Some("cid".into()),
            client_secret: Some("csec".into()),
            refresh_token: Some("rt".into()),
            access_token: Some("at".into()),
            expires_at: Some(
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_secs_f64() + 3600.0)
                    .unwrap_or(3600.0),
            ),
        };
        let storage: Arc<dyn Storage> = Arc::new(MemoryStorage::new());
        let client = Client::new(cfg, Arc::clone(&storage), true, OutputFormat::Json)
            .unwrap()
            .with_api_override(server_url);
        Ctx {
            client,
            storage,
            format: OutputFormat::Json,
        }
    }
}

pub fn effective_format(cli: &Cli) -> OutputFormat {
    if cli.pretty {
        OutputFormat::Table
    } else {
        cli.format
    }
}

pub fn run(cli: Cli) -> Result<()> {
    let format = effective_format(&cli);

    if cli.version {
        let mut out = io::stdout().lock();
        let data = json!({ "version": env!("CARGO_PKG_VERSION") });
        output::emit_success(&data, format, &mut out)
            .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
        return Ok(());
    }

    if cli.list_commands {
        let mut out = io::stdout().lock();
        let manifest = list_commands_manifest();
        let data = json!({ "commands": manifest });
        output::emit_success(&data, format, &mut out)
            .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
        return Ok(());
    }

    let Some(command) = cli.command else {
        eprintln!("zb: no subcommand given. Try `zb --help`.");
        return Err(ZohoError::validation("no subcommand given"));
    };

    let mut ctx = build_ctx(cli.dry_run, format)?;

    match command {
        Commands::Auth(c) => commands::auth_cmd::run(c, &mut ctx),
        Commands::Org(c) => commands::org::run(c, &mut ctx),
        Commands::Raw(c) => commands::raw::run(c, &mut ctx),
        Commands::Contacts(c) => commands::contacts::run(c, &mut ctx),
        Commands::Expenses(c) => commands::expenses::run(c, &mut ctx),
        Commands::Invoices(c) => commands::invoices::run(c, &mut ctx),
        Commands::Bills(c) => commands::bills::run(c, &mut ctx),
        Commands::Projects(c) => commands::projects::run(c, &mut ctx),
        Commands::CustomerPayments(c) => commands::customer_payments::run(c, &mut ctx),
        Commands::RecurringExpenses(c) => commands::recurring_expenses::run(c, &mut ctx),
        Commands::RecurringInvoices(c) => commands::recurring_invoices::run(c, &mut ctx),
        Commands::BankTransactions(c) => commands::bank_transactions::run(c, &mut ctx),
        Commands::BankRules(c) => commands::bank_rules::run(c, &mut ctx),
        Commands::ChartOfAccounts(c) => commands::chart_of_accounts::run(c, &mut ctx),
    }
}

fn build_ctx(dry_run: bool, format: OutputFormat) -> Result<Ctx> {
    let storage: Arc<dyn Storage> = Arc::new(RealStorage::new());
    let cfg = config::load(&*storage, &Overrides::default())?;
    let client = Client::new(cfg, Arc::clone(&storage), dry_run, format)?;
    Ok(Ctx {
        client,
        storage,
        format,
    })
}

fn list_commands_manifest() -> Vec<serde_json::Value> {
    use clap::CommandFactory;
    let cmd = Cli::command();
    let mut out = Vec::new();
    walk_subcommands(&cmd, "", &mut out);
    out
}

fn walk_subcommands(cmd: &clap::Command, prefix: &str, out: &mut Vec<serde_json::Value>) {
    let mut subs: Vec<&clap::Command> =
        cmd.get_subcommands().filter(|s| !s.is_hide_set()).collect();
    subs.sort_by_key(|c| c.get_name().to_owned());
    for sub in subs {
        let name = sub.get_name();
        let full = if prefix.is_empty() {
            name.to_string()
        } else {
            format!("{prefix} {name}")
        };
        if sub.get_subcommands().any(|c| !c.is_hide_set()) {
            walk_subcommands(sub, &full, out);
        } else {
            let summary = sub
                .get_about()
                .map(|s| s.to_string())
                .or_else(|| sub.get_long_about().map(|s| s.to_string()))
                .unwrap_or_default()
                .lines()
                .next()
                .unwrap_or("")
                .to_string();
            let params: Vec<serde_json::Value> = sub
                .get_arguments()
                .filter(|a| !a.is_hide_set())
                .map(|a| {
                    json!({
                        "name": a.get_id().as_str(),
                        "kind": if a.is_positional() { "argument" } else { "option" },
                        "required": a.is_required_set(),
                        "opts": a.get_long_and_visible_aliases().unwrap_or_default()
                            .into_iter()
                            .map(|s| format!("--{s}"))
                            .collect::<Vec<_>>(),
                        "help": a.get_help().map(|s| s.to_string()),
                    })
                })
                .collect();
            out.push(json!({
                "name": full,
                "summary": summary,
                "params": params,
            }));
        }
    }
}

pub fn emit_dispatch_error(err: &ZohoError, format: OutputFormat) {
    let mut stderr = io::stderr().lock();
    let _ = output::emit_error(&err.to_envelope(), format, &mut stderr);
    let _ = stderr.flush();
}

pub fn is_dry_run_ok(err: &ZohoError) -> bool {
    matches!(err.kind, ErrorKind::DryRunOk)
}
