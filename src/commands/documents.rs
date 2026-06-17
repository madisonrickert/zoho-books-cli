//! `zb documents` — the org-level Documents inbox (receipts and files uploaded
//! through the web UI or autoscan). Distinct from `invoices documents`, which
//! manages documents already attached to a specific invoice.
//!
//! Verified live against Zoho v3:
//! - `GET /documents` → list; collection key is `documents` (NOT `document`).
//! - `GET /documents/{id}` → the raw original file bytes (binary), NOT JSON
//!   metadata. There is no JSON single-object metadata endpoint; per-document
//!   metadata only appears in the list, so `get` looks the id up within the
//!   listing (bounded by `--page-limit`).
//! - `DELETE /documents/{id}` → standard `{code, message}` action response.

use std::fs;
use std::path::PathBuf;

use clap::{Args, Subcommand};
use serde_json::{Value, json};

use crate::cli::Ctx;
use crate::commands::common::{self, ListArgs};
use crate::errors::{Result, ZohoError};
use crate::shared::Query;

const BASE: &str = "/documents";
const DID: &str = "document_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List documents in the org's inbox (GET /documents).
    List(ListArgs),
    /// Look up one document's metadata by id.
    ///
    /// Zoho exposes no single-object metadata endpoint for inbox documents
    /// (GET /documents/{id} returns the file bytes), so this searches the
    /// listing. It scans from `--page` (default 1) up to `--page-limit` pages;
    /// narrow large inboxes with `--per-page` or `--query filter_by=...`.
    Get(GetArgs),
    /// Download a document's original file to --output (binary-safe).
    Download(DownloadArgs),
    /// Delete a document from the inbox (DELETE /documents/{id}).
    Delete(IdArgs),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub document_id: String,
}

#[derive(Args, Debug)]
pub struct GetArgs {
    pub document_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct DownloadArgs {
    pub document_id: String,
    /// File path to write the original document bytes to.
    #[arg(short = 'o', long)]
    pub output: PathBuf,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "documents"),
        Sub::Get(args) => get_document(args, ctx),
        Sub::Download(args) => download_document(args, ctx),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.document_id);
            common::delete(ctx, &path, DID, &args.document_id)
        }
    }
}

/// Look up a single document by scanning the listing. Zoho has no JSON
/// metadata single-get for inbox documents, so this pages through `/documents`
/// (from `--page`, up to `--page-limit` pages) and returns the first match as
/// `{document: ...}`.
fn get_document(args: GetArgs, ctx: &mut Ctx) -> Result<()> {
    let mut query = args.list.build_query()?;
    let start: u32 = query.get("page").and_then(|s| s.parse().ok()).unwrap_or(1);
    let limit = args.list.page_limit.max(1);
    let mut current = start;
    let mut scanned: u32 = 0;
    loop {
        query.insert("page".into(), current.to_string());
        let resp = ctx.client.get(BASE, &query)?;
        if let Some(doc) = find_document(&resp, &args.document_id) {
            return common::emit_object(&json!({ "document": doc }), ctx);
        }
        scanned += 1;
        let has_more = resp
            .get("page_context")
            .and_then(|p| p.get("has_more_page"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        if !has_more || scanned >= limit {
            break;
        }
        current += 1;
    }
    Err(ZohoError::not_found(format!(
        "No document with document_id={} in the Documents inbox (scanned {scanned} page(s) from page {start}). \
         Browse with `zb documents list`, or narrow with --per-page / --query filter_by=...",
        args.document_id
    )))
}

/// Stream a document's original file bytes straight to `--output` — binary-safe
/// (no JSON wrapping), so PDFs and images survive intact. Mirrors the
/// `invoices documents download` path.
fn download_document(args: DownloadArgs, ctx: &mut Ctx) -> Result<()> {
    let (bytes, content_type) = ctx
        .client
        .get_bytes(&format!("{BASE}/{}", args.document_id), &Query::new())?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(ZohoError::from)?;
    }
    fs::write(&args.output, &bytes).map_err(ZohoError::from)?;
    common::emit_success_raw(
        &json!({
            "document_id": args.document_id,
            "saved_to": args.output.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        }),
        ctx,
    )
}

/// Find a document by id within a `GET /documents` response. IDs come back as
/// JSON strings, so `as_str` is the right accessor (and stays clear of the
/// banned numeric accessors under `arbitrary_precision`).
fn find_document(resp: &Value, document_id: &str) -> Option<Value> {
    resp.get("documents")?
        .as_array()?
        .iter()
        .find(|d| d.get(DID).and_then(Value::as_str) == Some(document_id))
        .cloned()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn list_targets_documents() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"documents":[]}"#)
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

    #[test]
    fn get_returns_matching_document_from_listing() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(
                r#"{"documents":[
                    {"document_id":"1111111111111111111","file_name":"a.pdf"},
                    {"document_id":"2222222222222222222","file_name":"b.pdf"}
                ],"page_context":{"has_more_page":false}}"#,
            )
            .create();
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::Get(GetArgs {
                    document_id: "2222222222222222222".into(),
                    list: ListArgs::default(),
                }),
            },
            &mut ctx,
        )
        .unwrap();
        m.assert();
    }

    #[test]
    fn get_not_found_when_absent_from_listing() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/documents")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(
                r#"{"documents":[{"document_id":"1111111111111111111"}],"page_context":{"has_more_page":false}}"#,
            )
            .create();
        let mut ctx = Ctx::new_for_test(&server.url());
        let err = run(
            Cmd {
                sub: Sub::Get(GetArgs {
                    document_id: "9999999999999999999".into(),
                    list: ListArgs::default(),
                }),
            },
            &mut ctx,
        )
        .unwrap_err();
        assert_eq!(err.code(), "not_found");
    }

    #[test]
    fn get_stops_at_page_limit_when_more_pages_remain() {
        // has_more_page stays true and the id is never present; the search must
        // terminate at --page-limit rather than loop forever.
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/documents")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(
                r#"{"documents":[{"document_id":"1111111111111111111"}],"page_context":{"has_more_page":true}}"#,
            )
            .expect_at_least(1)
            .create();
        let mut ctx = Ctx::new_for_test(&server.url());
        let list = ListArgs {
            page_limit: 2,
            ..ListArgs::default()
        };
        let err = run(
            Cmd {
                sub: Sub::Get(GetArgs {
                    document_id: "9999999999999999999".into(),
                    list,
                }),
            },
            &mut ctx,
        )
        .unwrap_err();
        assert_eq!(err.code(), "not_found");
    }

    #[test]
    fn delete_targets_document() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("DELETE", "/books/v3/documents/1234567890123456789")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"code":0,"message":"success"}"#)
            .create();
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::Delete(IdArgs {
                    document_id: "1234567890123456789".into(),
                }),
            },
            &mut ctx,
        )
        .unwrap();
        m.assert();
    }

    #[test]
    fn download_writes_raw_bytes_to_output() {
        // Non-UTF8 bytes prove the path is binary-safe (no JSON/string round-trip).
        let body: Vec<u8> = vec![0x25, 0x50, 0x44, 0x46, 0x00, 0xFF, 0xFE, 0x0A];
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents/1234567890123456789")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_header("content-type", "application/pdf")
            .with_body(&body)
            .create();
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("receipt.pdf");
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::Download(DownloadArgs {
                    document_id: "1234567890123456789".into(),
                    output: out.clone(),
                }),
            },
            &mut ctx,
        )
        .unwrap();
        m.assert();
        let written = std::fs::read(&out).unwrap();
        assert_eq!(written, body, "file must contain the exact response bytes");
    }

    #[test]
    fn download_404_writes_no_file_and_no_parent_dir() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/documents/1234567890123456789")
            .match_query(mockito::Matcher::Any)
            .with_status(404)
            .with_body(r#"{"code":4,"message":"not found"}"#)
            .create();
        // Nested path whose parent does not exist: get_bytes must error before
        // create_dir_all/write run, leaving no partial file and no new dir.
        let tmp = tempfile::tempdir().unwrap();
        let parent = tmp.path().join("nested");
        let out = parent.join("doc.pdf");
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::Download(DownloadArgs {
                    document_id: "1234567890123456789".into(),
                    output: out.clone(),
                }),
            },
            &mut ctx,
        )
        .expect_err("404 must propagate as an error");
        m.assert();
        assert!(!out.exists(), "no partial file on failure");
        assert!(
            !parent.exists(),
            "parent dir must not be created on failure"
        );
    }
}
