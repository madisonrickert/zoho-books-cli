//! `zb expenses` — CRUD + receipts + attachments + comments. Receipt and
//! attachments are the binary-upload commands that motivated the CLI.

use std::fs;
use std::path::PathBuf;

use clap::{Args, Subcommand};
use serde_json::{Value, json};

use crate::cli::Ctx;
use crate::client::{FileUpload, RequestOptions};
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;
use crate::shared::Query;
use crate::uploads;

const BASE: &str = "/expenses";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List expenses.
    List(ListArgs),
    /// Create an expense.
    Create(BodyArgs),
    /// Get a single expense by ID.
    Get(IdArgs),
    /// Update an expense by ID.
    Update(UpdateArgs),
    /// Update an expense by a custom field's unique value.
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    /// Delete an expense by ID.
    Delete(IdArgs),
    /// Single-image receipt per expense.
    Receipt(ReceiptCmd),
    /// Multiple supplementary attachments per expense.
    Attachments(AttachmentsCmd),
    /// Expense history and comments (read-only).
    Comments(CommentsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub expense_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub expense_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct ReceiptCmd {
    #[command(subcommand)]
    pub sub: ReceiptSub,
}

#[derive(Subcommand, Debug)]
pub enum ReceiptSub {
    /// Upload a receipt to an expense. Replaces any existing receipt.
    Upload(ReceiptUploadArgs),
    /// Download the receipt file attached to an expense.
    Get(ReceiptGetArgs),
    /// Delete the receipt attached to an expense.
    Delete(IdArgs),
}

#[derive(Args, Debug)]
pub struct ReceiptUploadArgs {
    pub expense_id: String,
    /// Path to a PDF, JPG, JPEG, PNG, or GIF (≤10 MB).
    pub file: PathBuf,
}

#[derive(Args, Debug)]
pub struct ReceiptGetArgs {
    pub expense_id: String,
    /// Path to write the downloaded receipt file.
    #[arg(short = 'o', long)]
    pub output: PathBuf,
}

#[derive(Args, Debug)]
pub struct AttachmentsCmd {
    #[command(subcommand)]
    pub sub: AttachmentsSub,
}

#[derive(Subcommand, Debug)]
pub enum AttachmentsSub {
    /// Attach one or more supplementary files to an expense.
    Add(AttachmentsAddArgs),
    /// Delete all attachments from an expense.
    Delete(IdArgs),
}

#[derive(Args, Debug)]
pub struct AttachmentsAddArgs {
    pub expense_id: String,
    /// One or more files (PDF, JPG, JPEG, PNG, GIF; ≤10 MB each).
    pub files: Vec<PathBuf>,
}

#[derive(Args, Debug)]
pub struct CommentsCmd {
    #[command(subcommand)]
    pub sub: CommentsSub,
}

#[derive(Subcommand, Debug)]
pub enum CommentsSub {
    /// List history and comments for an expense (read-only).
    List(IdArgs),
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "expenses"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.expense_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.expense_id), &args.body)
        }
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.expense_id);
            common::delete(ctx, &path, "expense_id", &args.expense_id)
        }
        Sub::Receipt(r) => match r.sub {
            ReceiptSub::Upload(args) => receipt_upload(args, ctx),
            ReceiptSub::Get(args) => receipt_get(args, ctx),
            ReceiptSub::Delete(args) => {
                let path = format!("{BASE}/{}/receipt", args.expense_id);
                let resp = ctx.client.delete(&path, &Query::new())?;
                let data = json!({
                    "expense_id": args.expense_id,
                    "deleted": true,
                    "response": resp,
                });
                common::emit_success_raw(&data, ctx)
            }
        },
        Sub::Attachments(a) => match a.sub {
            AttachmentsSub::Add(args) => attachments_add(args, ctx),
            AttachmentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/attachment", args.expense_id);
                let resp = ctx.client.delete(&path, &Query::new())?;
                let data = json!({
                    "expense_id": args.expense_id,
                    "deleted": true,
                    "response": resp,
                });
                common::emit_success_raw(&data, ctx)
            }
        },
        Sub::Comments(c) => match c.sub {
            CommentsSub::List(args) => {
                let path = format!("{BASE}/{}/comments", args.expense_id);
                let resp = ctx.client.get(&path, &Query::new())?;
                common::emit_list_flat(&resp, "comments", ctx)
            }
        },
    }
}

fn receipt_upload(args: ReceiptUploadArgs, ctx: &mut Ctx) -> Result<()> {
    uploads::validate(&args.file)?;
    let size = fs::metadata(&args.file)?.len();
    let filename = args
        .file
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();
    let opts = RequestOptions {
        files: vec![FileUpload {
            field: "receipt".into(),
            path: args.file.clone(),
        }],
        ..RequestOptions::default()
    };
    let resp = ctx
        .client
        .post(&format!("{BASE}/{}/receipt", args.expense_id), opts)?;
    let data = json!({
        "expense_id": args.expense_id,
        "uploaded": filename,
        "size_bytes": size,
        "response": resp,
    });
    common::emit_success_raw(&data, ctx)
}

fn receipt_get(args: ReceiptGetArgs, ctx: &mut Ctx) -> Result<()> {
    let (bytes, content_type) = ctx.client.get_bytes(
        &format!("{BASE}/{}/receipt", args.expense_id),
        &Query::new(),
    )?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&args.output, &bytes)?;
    let data = json!({
        "expense_id": args.expense_id,
        "saved_to": args.output.display().to_string(),
        "size_bytes": bytes.len(),
        "content_type": content_type,
    });
    common::emit_success_raw(&data, ctx)
}

fn attachments_add(args: AttachmentsAddArgs, ctx: &mut Ctx) -> Result<()> {
    let mut results: Vec<Value> = Vec::new();
    for file in &args.files {
        let mut entry = serde_json::Map::new();
        entry.insert("file".into(), Value::String(file.display().to_string()));
        match upload_one_attachment(&args.expense_id, file, ctx) {
            Ok(resp) => {
                entry.insert("ok".into(), Value::Bool(true));
                entry.insert("response".into(), resp);
            }
            // DryRunOk is a sentinel — the client already emitted the preview to
            // stdout. Propagate it to short-circuit the loop (invariant 12: dry-run
            // exits at the FIRST internal call) and avoid a second stdout write
            // from emit_success_raw (invariant 14: stdout exactly once).
            Err(e) if crate::errors::ErrorKind::DryRunOk == e.kind => return Err(e),
            Err(e) => {
                entry.insert("ok".into(), Value::Bool(false));
                entry.insert(
                    "error".into(),
                    json!({
                        "code": e.code(),
                        "message": e.message,
                        "details": e.details.clone().unwrap_or_else(|| json!({})),
                    }),
                );
            }
        }
        results.push(Value::Object(entry));
    }
    let data = json!({
        "expense_id": args.expense_id,
        "results": results,
    });
    common::emit_success_raw(&data, ctx)
}

fn upload_one_attachment(expense_id: &str, file: &std::path::Path, ctx: &mut Ctx) -> Result<Value> {
    uploads::validate(file)?;
    let opts = RequestOptions {
        files: vec![FileUpload {
            field: "attachment".into(),
            path: file.to_path_buf(),
        }],
        ..RequestOptions::default()
    };
    ctx.client
        .post(&format!("{BASE}/{expense_id}/attachment"), opts)
}
