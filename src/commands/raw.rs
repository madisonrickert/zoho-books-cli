//! `zb raw <METHOD> <path>` — escape hatch to any Zoho v3 endpoint.
//! Accepts the same `--body` / `--query` / `--params` / `--file` flags as
//! the typed wrappers but bypasses path/method validation entirely. The
//! envelope wraps Zoho's response in `{method, path, response}`.

use std::io::{self, Write};
use std::path::PathBuf;
use std::str::FromStr;

use clap::Args;
use serde_json::json;

use crate::cli::Ctx;
use crate::client::{FileUpload, RequestOptions};
use crate::errors::{Result, ZohoError};
use crate::output;
use crate::shared;

#[derive(Args, Debug)]
pub struct Cmd {
    /// HTTP method: GET, POST, PUT, DELETE.
    pub method: String,
    /// Path under /books/v3 (leading slash optional).
    pub path: String,
    /// Query params as key=value. May be repeated.
    #[arg(short = 'q', long, value_name = "K=V")]
    pub query: Vec<String>,
    /// Optional --params JSON object merged on top of --query pairs.
    #[arg(long, value_name = "JSON")]
    pub params: Option<String>,
    /// JSON body. Either a literal string or @path/to/file.json.
    #[arg(short = 'b', long)]
    pub body: Option<String>,
    /// Multipart file upload as field=path. May be repeated.
    #[arg(short = 'f', long, value_name = "FIELD=PATH")]
    pub file: Vec<String>,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    let method = HttpMethod::from_str(&cmd.method)?;
    let query = shared::parse_query_pairs(&cmd.query, cmd.params.as_deref())?;
    let body_bytes =
        shared::parse_body(cmd.body.as_deref())?.map(|raw| raw.get().as_bytes().to_vec());

    let mut files = Vec::new();
    for spec in &cmd.file {
        let (field, path) = spec.split_once('=').ok_or_else(|| {
            ZohoError::validation(format!("--file must be field=path, got: {spec}"))
        })?;
        if field.is_empty() {
            return Err(ZohoError::validation(format!(
                "--file field must be non-empty, got: {spec}"
            )));
        }
        files.push(FileUpload {
            field: field.to_owned(),
            path: PathBuf::from(path),
        });
    }

    let opts = RequestOptions {
        query: query.clone(),
        body: body_bytes,
        files,
        ..RequestOptions::default()
    };

    let resp = match method {
        HttpMethod::Get => ctx.client.get(&cmd.path, &query)?,
        HttpMethod::Post => ctx.client.post(&cmd.path, opts)?,
        HttpMethod::Put => ctx.client.put(&cmd.path, opts)?,
        HttpMethod::Delete => ctx.client.delete(&cmd.path, &query)?,
    };

    let data = json!({
        "method": method.as_str(),
        "path": cmd.path,
        "response": resp,
    });
    let mut stdout = io::stdout().lock();
    output::emit_success(&data, ctx.format, &mut stdout)
        .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
    let _ = stdout.flush();
    Ok(())
}

#[derive(Clone, Copy)]
enum HttpMethod {
    Get,
    Post,
    Put,
    Delete,
}

impl HttpMethod {
    fn as_str(self) -> &'static str {
        match self {
            Self::Get => "GET",
            Self::Post => "POST",
            Self::Put => "PUT",
            Self::Delete => "DELETE",
        }
    }
}

impl FromStr for HttpMethod {
    type Err = ZohoError;
    fn from_str(s: &str) -> std::result::Result<Self, ZohoError> {
        match s.to_ascii_uppercase().as_str() {
            "GET" => Ok(Self::Get),
            "POST" => Ok(Self::Post),
            "PUT" => Ok(Self::Put),
            "DELETE" => Ok(Self::Delete),
            other => Err(ZohoError::validation(format!(
                "Unsupported method: {other}. Use GET, POST, PUT, or DELETE."
            ))),
        }
    }
}
