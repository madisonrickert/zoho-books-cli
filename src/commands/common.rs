//! Shared infrastructure for domain command modules: arg structs, request-building
//! helpers, emit shortcuts. Each module re-uses these so the per-module file stays
//! focused on the actual endpoint mapping.

use std::io::{self, Write};

use clap::Args;
use serde_json::Value;

use crate::cli::Ctx;
use crate::client::RequestOptions;
use crate::errors::{Result, ZohoError};
use crate::output;
use crate::shared::{self, Query};

/// Common args for list endpoints.
#[derive(Args, Debug, Clone, Default)]
pub struct ListArgs {
    /// Query params as key=value. May be repeated.
    #[arg(short = 'q', long, value_name = "K=V")]
    pub query: Vec<String>,
    /// Query params as a JSON object. Merged on top of --query.
    #[arg(long, value_name = "JSON")]
    pub params: Option<String>,
    /// Page number (1-indexed).
    #[arg(long)]
    pub page: Option<u32>,
    /// Rows per page.
    #[arg(long = "per-page")]
    pub per_page: Option<u32>,
    /// Auto-paginate (NDJSON: one page per line).
    #[arg(long = "page-all")]
    pub page_all: bool,
    /// Max pages with --page-all.
    #[arg(long = "page-limit", default_value_t = 10)]
    pub page_limit: u32,
    /// Delay between pages in ms with --page-all.
    #[arg(long = "page-delay", default_value_t = 100)]
    pub page_delay: u64,
}

impl ListArgs {
    pub fn build_query(&self) -> Result<Query> {
        let mut q = shared::parse_query_pairs(&self.query, self.params.as_deref())?;
        if let Some(p) = self.page {
            q.insert("page".into(), p.to_string());
        }
        if let Some(pp) = self.per_page {
            q.insert("per_page".into(), pp.to_string());
        }
        Ok(q)
    }
}

/// Common args for endpoints that take a body (create / update / etc.) plus optional
/// query and params. Body is required for some, optional for others; callers decide.
#[derive(Args, Debug, Clone)]
pub struct BodyArgs {
    /// JSON body. Either a literal string or @path/to/file.json. IDs must be strings.
    #[arg(short = 'b', long)]
    pub body: Option<String>,
    /// Query params as key=value. May be repeated.
    #[arg(short = 'q', long, value_name = "K=V")]
    pub query: Vec<String>,
    /// Query params as a JSON object. Merged on top of --query.
    #[arg(long, value_name = "JSON")]
    pub params: Option<String>,
}

impl BodyArgs {
    pub fn build_query(&self) -> Result<Query> {
        shared::parse_query_pairs(&self.query, self.params.as_deref())
    }

    pub fn body_bytes(&self) -> Result<Option<Vec<u8>>> {
        Ok(shared::parse_body(self.body.as_deref())?.map(|raw| raw.get().as_bytes().to_vec()))
    }

    pub fn require_body_bytes(&self) -> Result<Vec<u8>> {
        self.body_bytes()?
            .ok_or_else(|| ZohoError::validation("--body is required"))
    }
}

/// Common args for `update-by-custom-field`-style endpoints. Adds --upsert plus
/// the unique-identifier key/value pair sent as headers.
#[derive(Args, Debug, Clone)]
pub struct CustomFieldUpdateArgs {
    /// Name of the custom field used to look up the record.
    #[arg(long = "unique-key")]
    pub unique_key: String,
    /// Value of the custom field used to look up the record.
    #[arg(long = "unique-value")]
    pub unique_value: String,
    /// Create the record if no match found (sets X-Upsert: true).
    #[arg(long)]
    pub upsert: bool,
    /// JSON body. Either a literal string or @path/to/file.json. IDs must be strings.
    #[arg(short = 'b', long)]
    pub body: String,
}

impl CustomFieldUpdateArgs {
    pub fn headers(&self) -> Vec<(String, String)> {
        let mut h = vec![
            ("X-Unique-Identifier-Key".into(), self.unique_key.clone()),
            (
                "X-Unique-Identifier-Value".into(),
                self.unique_value.clone(),
            ),
        ];
        if self.upsert {
            h.push(("X-Upsert".into(), "true".into()));
        }
        h
    }

    pub fn body_bytes(&self) -> Result<Vec<u8>> {
        let raw = shared::parse_body(Some(&self.body))?
            .ok_or_else(|| ZohoError::validation("--body is required"))?;
        Ok(raw.get().as_bytes().to_vec())
    }
}

// -------- Emit helpers ---------------------------------------------------

pub fn list(ctx: &mut Ctx, path: &str, args: &ListArgs, collection_key: &str) -> Result<()> {
    let query = args.build_query()?;
    let mut stdout = io::stdout().lock();
    // FnMut closure that captures &mut ctx.client.
    let format = ctx.format;
    let client = &mut ctx.client;
    let fetch = |q: &Query| client.get(path, q);
    shared::emit_list_paginated(
        fetch,
        query,
        collection_key,
        args.page_all,
        args.page_limit,
        args.page_delay,
        format,
        &mut stdout,
    )?;
    let _ = stdout.flush();
    Ok(())
}

pub fn create(ctx: &mut Ctx, path: &str, args: &BodyArgs) -> Result<()> {
    let opts = RequestOptions {
        query: args.build_query()?,
        body: Some(args.require_body_bytes()?),
        ..RequestOptions::default()
    };
    let resp = ctx.client.post(path, opts)?;
    emit_object(&resp, ctx)
}

pub fn get(ctx: &mut Ctx, path: &str) -> Result<()> {
    let resp = ctx.client.get(path, &Query::new())?;
    emit_object(&resp, ctx)
}

pub fn update(ctx: &mut Ctx, path: &str, args: &BodyArgs) -> Result<()> {
    let opts = RequestOptions {
        query: args.build_query()?,
        body: Some(args.require_body_bytes()?),
        ..RequestOptions::default()
    };
    let resp = ctx.client.put(path, opts)?;
    emit_object(&resp, ctx)
}

pub fn update_custom(ctx: &mut Ctx, path: &str, args: &CustomFieldUpdateArgs) -> Result<()> {
    let opts = RequestOptions {
        body: Some(args.body_bytes()?),
        headers: args.headers(),
        ..RequestOptions::default()
    };
    let resp = ctx.client.put(path, opts)?;
    emit_object(&resp, ctx)
}

pub fn delete(ctx: &mut Ctx, path: &str, id_field: &str, id_value: &str) -> Result<()> {
    let resp = ctx.client.delete(path, &Query::new())?;
    emit_action(id_field, id_value, &resp, ctx)
}

/// Action verbs (POST with no body, e.g. mark-active).
pub fn action(ctx: &mut Ctx, path: &str, id_field: &str, id_value: &str) -> Result<()> {
    let opts = RequestOptions::default();
    let resp = ctx.client.post(path, opts)?;
    emit_action(id_field, id_value, &resp, ctx)
}

pub fn action_with_body(
    ctx: &mut Ctx,
    path: &str,
    args: &BodyArgs,
    id_field: &str,
    id_value: &str,
) -> Result<()> {
    let opts = RequestOptions {
        query: args.build_query()?,
        body: args.body_bytes()?,
        ..RequestOptions::default()
    };
    let resp = ctx.client.post(path, opts)?;
    emit_action(id_field, id_value, &resp, ctx)
}

pub fn emit_object(resp: &Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    shared::emit_object(resp, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

pub fn emit_list_flat(resp: &Value, collection_key: &str, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    shared::emit_list(resp, collection_key, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

pub fn emit_action(id_field: &str, id_value: &str, resp: &Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    shared::emit_action(id_field, id_value, resp, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

pub fn emit_success_raw(data: &Value, ctx: &mut Ctx) -> Result<()> {
    let mut stdout = io::stdout().lock();
    output::emit_success(data, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}
