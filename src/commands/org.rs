use std::io::{self, Write};

use clap::{Args, Subcommand};
use serde_json::{Value, json};

use crate::cli::Ctx;
use crate::client::RequestOptions;
use crate::config;
use crate::errors::{Result, ZohoError};
use crate::output;
use crate::shared::{self, Query};
use crate::storage::RealStorage;

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List organizations the authenticated user has access to.
    List,
    /// Persist an organization_id as the default for subsequent commands.
    Use(UseArgs),
    /// Show the currently selected organization_id.
    Current,
    /// Get full details of an organization.
    Get(GetArgs),
    /// Update an organization (PUT /organizations/{organization_id}).
    Update(UpdateArgs),
}

#[derive(Args, Debug)]
pub struct UseArgs {
    /// Organization ID to store as the default.
    pub org_id: String,
}

#[derive(Args, Debug)]
pub struct GetArgs {
    /// Zoho Books organization_id to fetch.
    pub organization_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    /// Zoho Books organization_id to update.
    pub organization_id: String,
    /// JSON body. IDs must be strings.
    #[arg(short = 'b', long)]
    pub body: String,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List => list(ctx),
        Sub::Use(args) => use_org(args, ctx),
        Sub::Current => current(ctx),
        Sub::Get(args) => get_org(args, ctx),
        Sub::Update(args) => update_org(args, ctx),
    }
}

fn list(ctx: &mut Ctx) -> Result<()> {
    let resp = ctx.client.get_no_org("/organizations", &Query::new())?;
    let empty = Value::Array(vec![]);
    let orgs = resp
        .get("organizations")
        .and_then(|v| v.as_array())
        .unwrap_or_else(|| empty.as_array().unwrap());
    let summary: Vec<Value> = orgs
        .iter()
        .map(|o| {
            json!({
                "organization_id": o.get("organization_id"),
                "name": o.get("name"),
                "currency_code": o.get("currency_code"),
                "is_default_org": o.get("is_default_org"),
            })
        })
        .collect();
    let data = json!({ "organizations": summary });
    emit(&data, ctx)
}

fn use_org(args: UseArgs, ctx: &mut Ctx) -> Result<()> {
    let org_id = args.org_id.trim();
    if org_id.is_empty() {
        return Err(ZohoError::validation(
            "org_id is required and must be non-empty.",
        ));
    }
    let storage = RealStorage::new();
    config::save_org(&storage, org_id)?;
    emit(&json!({ "org_id": org_id }), ctx)
}

fn current(ctx: &mut Ctx) -> Result<()> {
    let data = json!({
        "org_id": ctx.client.cfg.org_id,
        "region": ctx.client.cfg.region.code,
    });
    emit(&data, ctx)
}

fn get_org(args: GetArgs, ctx: &mut Ctx) -> Result<()> {
    let resp = ctx.client.get(
        &format!("/organizations/{}", args.organization_id),
        &Query::new(),
    )?;
    emit_object(&resp, ctx)
}

fn update_org(args: UpdateArgs, ctx: &mut Ctx) -> Result<()> {
    let body = shared::parse_body(Some(&args.body))?
        .ok_or_else(|| ZohoError::validation("--body is required for update"))?;
    let opts = RequestOptions {
        body: Some(body.get().as_bytes().to_vec()),
        ..RequestOptions::default()
    };
    let resp = ctx
        .client
        .put(&format!("/organizations/{}", args.organization_id), opts)?;
    emit_object(&resp, ctx)
}

fn emit_object(resp: &Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    shared::emit_object(resp, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

fn emit(data: &Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    output::emit_success(data, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}
