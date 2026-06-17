//! `zb raw <METHOD> <path>` — escape hatch to any Zoho v3 endpoint.
//! Accepts the same `--body` / `--query` / `--params` / `--file` flags as
//! the typed wrappers but bypasses path/method validation entirely. The
//! envelope wraps Zoho's response in `{method, path, response}`.
//!
//! `--output <file>` (GET only) is the binary sink: it streams the raw response
//! bytes straight to disk and emits `{method, path, saved_to, size_bytes,
//! content_type}` instead, so binary endpoints (e.g. `GET /documents/{id}`)
//! download without the JSON envelope corrupting them.

use std::fs;
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
    /// Write the raw response bytes to this file instead of wrapping the body
    /// in the JSON envelope. Binary-safe (PDFs, images). GET only.
    #[arg(short = 'o', long)]
    pub output: Option<PathBuf>,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    let method = HttpMethod::from_str(&cmd.method)?;
    let query = shared::parse_query_pairs(&cmd.query, cmd.params.as_deref())?;

    // Binary-safe sink: write the raw response bytes to a file instead of
    // wrapping them in the JSON envelope (which corrupts non-UTF8 content such
    // as a `GET /documents/{id}` PDF). Reuses the tested `get_bytes` path, so
    // it inherits dry-run short-circuiting and 401/429 handling.
    if let Some(out_path) = cmd.output.as_ref() {
        if !matches!(method, HttpMethod::Get) {
            return Err(ZohoError::validation(
                "--output is only supported with GET (binary downloads).",
            ));
        }
        let (bytes, content_type) = ctx.client.get_bytes(&cmd.path, &query)?;
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent).map_err(ZohoError::from)?;
        }
        fs::write(out_path, &bytes).map_err(ZohoError::from)?;
        let data = json!({
            "method": method.as_str(),
            "path": cmd.path,
            "saved_to": out_path.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        });
        let mut stdout = io::stdout().lock();
        output::emit_success(&data, ctx.format, &mut stdout)
            .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
        let _ = stdout.flush();
        return Ok(());
    }

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    fn cmd(method: &str, path: &str, output: Option<PathBuf>) -> Cmd {
        Cmd {
            method: method.into(),
            path: path.into(),
            query: vec![],
            params: None,
            body: None,
            file: vec![],
            output,
        }
    }

    #[test]
    fn output_writes_raw_bytes_no_json_wrapping() {
        // Non-UTF8 bytes prove the file is the raw body, not a JSON-wrapped string.
        let body: Vec<u8> = vec![0x25, 0x50, 0x44, 0x46, 0x00, 0xFF, 0xFE, 0x0A];
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents/123")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_header("content-type", "application/pdf")
            .with_body(&body)
            .create();
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("blob.bin");
        let mut ctx = Ctx::new_for_test(&server.url());
        run(cmd("GET", "/documents/123", Some(out.clone())), &mut ctx).unwrap();
        m.assert();
        assert_eq!(std::fs::read(&out).unwrap(), body);
    }

    #[test]
    fn output_rejects_non_get() {
        let server = mockito::Server::new();
        let mut ctx = Ctx::new_for_test(&server.url());
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("blob.bin");
        let err = run(cmd("POST", "/documents/123", Some(out.clone())), &mut ctx).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(!out.exists(), "no file should be written when rejected");
    }

    #[test]
    fn output_404_writes_no_file_and_no_parent_dir() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents/123")
            .match_query(mockito::Matcher::Any)
            .with_status(404)
            .with_body(r#"{"code":4,"message":"not found"}"#)
            .create();
        let tmp = tempfile::tempdir().unwrap();
        let parent = tmp.path().join("nested");
        let out = parent.join("blob.bin");
        let mut ctx = Ctx::new_for_test(&server.url());
        run(cmd("GET", "/documents/123", Some(out.clone())), &mut ctx)
            .expect_err("404 must propagate as an error");
        m.assert();
        assert!(!out.exists(), "no partial file on failure");
        assert!(
            !parent.exists(),
            "parent dir must not be created on failure"
        );
    }
}
