//! `zb auth` — login (browser OAuth flow), status (report stored creds),
//! refresh (force a token refresh), logout (clear storage).

use std::io::{self, Write};
use std::time::Duration;

use clap::{Args, Subcommand};
use serde_json::json;

use crate::auth::{self, DEFAULT_SCOPES};
use crate::cli::Ctx;
use crate::config::{self, SaveTokens};
use crate::errors::{Result, ZohoError};
use crate::output;
use crate::regions;

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// Run the OAuth authorization-code flow and store tokens.
    Login(LoginArgs),
    /// Report whether credentials are present and when the access token expires.
    Status,
    /// Force an access-token refresh using the stored refresh token.
    Refresh,
    /// Clear stored tokens from keyring and config file.
    Logout,
}

#[derive(Args, Debug)]
pub struct LoginArgs {
    /// OAuth client ID from the Zoho API Console (or ZOHO_CLIENT_ID env var).
    #[arg(long = "client-id", env = "ZOHO_CLIENT_ID")]
    pub client_id: Option<String>,
    /// OAuth client secret (or ZOHO_CLIENT_SECRET env var).
    #[arg(long = "client-secret", env = "ZOHO_CLIENT_SECRET")]
    pub client_secret: Option<String>,
    /// Zoho data-center region: us, eu, in, au, jp, ca, sa.
    #[arg(long, env = "ZOHO_REGION", default_value = "us")]
    pub region: String,
    /// Space-separated OAuth scopes.
    #[arg(long, default_value = DEFAULT_SCOPES)]
    pub scope: String,
    /// Do not try to open a browser automatically; print the URL instead.
    #[arg(long)]
    pub no_browser: bool,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::Login(args) => login(args, ctx),
        Sub::Status => status(ctx),
        Sub::Refresh => refresh(ctx),
        Sub::Logout => logout(ctx),
    }
}

fn login(args: LoginArgs, ctx: &mut Ctx) -> Result<()> {
    let client_id = args.client_id.ok_or_else(|| {
        ZohoError::validation(
            "Missing --client-id (or ZOHO_CLIENT_ID env var). Create OAuth credentials at https://api-console.zoho.com",
        )
    })?;
    let client_secret = args.client_secret.ok_or_else(|| {
        ZohoError::validation("Missing --client-secret (or ZOHO_CLIENT_SECRET env var).")
    })?;
    let region = regions::resolve(&args.region)?;

    let token = auth::authorize(
        &client_id,
        &client_secret,
        region,
        &args.scope,
        !args.no_browser,
        Duration::from_secs(300),
    )?;
    let refresh_token = token.refresh_token.clone().ok_or_else(|| {
        ZohoError::auth_failed(
            "Zoho did not return a refresh token. Ensure access_type=offline and prompt=consent on the authorize URL.",
        )
    })?;
    let expires_at = unix_now() + token.expires_in as f64;

    config::save_tokens(
        &*ctx.storage,
        SaveTokens {
            client_id: &client_id,
            client_secret: &client_secret,
            access_token: &token.access_token,
            refresh_token: &refresh_token,
            expires_at,
            region: region.code,
        },
    )?;

    let data = json!({
        "authenticated": true,
        "region": region.code,
        "expires_at": expires_at,
    });
    emit_success(&data, ctx)
}

fn status(ctx: &mut Ctx) -> Result<()> {
    let stored = ctx.storage.load()?.unwrap_or_default();
    let authed = stored
        .refresh_token
        .as_deref()
        .filter(|s| !s.is_empty())
        .is_some()
        && stored
            .client_id
            .as_deref()
            .filter(|s| !s.is_empty())
            .is_some();
    let data = json!({
        "authenticated": authed,
        "region": stored.region,
        "org_id": stored.org_id,
        "expires_at": stored.expires_at,
    });
    emit_success(&data, ctx)
}

fn refresh(ctx: &mut Ctx) -> Result<()> {
    config::require_auth(&ctx.client.cfg)?;
    let client_id = ctx.client.cfg.client_id.as_deref().unwrap();
    let client_secret = ctx.client.cfg.client_secret.as_deref().unwrap();
    let refresh_token = ctx.client.cfg.refresh_token.as_deref().unwrap();
    let region = ctx.client.cfg.region;
    let body = auth::refresh_access_token(client_id, client_secret, refresh_token, region)?;
    let expires_at = unix_now() + body.expires_in as f64;
    config::update_access_token(&*ctx.storage, &body.access_token, expires_at)?;
    ctx.client.cfg.access_token = Some(body.access_token);
    ctx.client.cfg.expires_at = Some(expires_at);
    let data = json!({ "refreshed": true, "expires_at": expires_at });
    emit_success(&data, ctx)
}

fn logout(ctx: &mut Ctx) -> Result<()> {
    ctx.storage.clear()?;
    let data = json!({ "cleared": true });
    emit_success(&data, ctx)
}

fn emit_success(data: &serde_json::Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    output::emit_success(data, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

fn unix_now() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}
