//! `zb bills` — CRUD + state actions + email + payments + comments + attachments.

use std::fs;
use std::path::PathBuf;

use clap::{Args, Subcommand};
use serde_json::{Value, json};

use crate::cli::Ctx;
use crate::client::{FileUpload, RequestOptions};
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::{Result, ZohoError};
use crate::shared::Query;
use crate::uploads;

const BASE: &str = "/bills";
const ID: &str = "bill_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    List(ListArgs),
    Create(BodyArgs),
    Get(IdArgs),
    Update(UpdateArgs),
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    Delete(IdArgs),
    #[command(name = "mark-void")]
    MarkVoid(IdArgs),
    #[command(name = "mark-open")]
    MarkOpen(IdArgs),
    Email(EmailArgs),
    Payments(PaymentsCmd),
    Comments(CommentsCmd),
    Attachments(AttachmentsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub bill_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub bill_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct EmailArgs {
    pub bill_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct PaymentsCmd {
    #[command(subcommand)]
    pub sub: PaymentsSub,
}

#[derive(Subcommand, Debug)]
pub enum PaymentsSub {
    /// List payments applied to a bill.
    List(PaymentsListArgs),
    /// Apply existing payments or vendor credits to a bill.
    Apply(PaymentsApplyArgs),
    /// Unapply a payment from a bill.
    Delete(PaymentDeleteArgs),
}

#[derive(Args, Debug)]
pub struct PaymentsListArgs {
    pub bill_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct PaymentsApplyArgs {
    pub bill_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct PaymentDeleteArgs {
    pub bill_id: String,
    pub bill_payment_id: String,
}

#[derive(Args, Debug)]
pub struct CommentsCmd {
    #[command(subcommand)]
    pub sub: CommentsSub,
}

#[derive(Subcommand, Debug)]
pub enum CommentsSub {
    /// List recent activity and comments on a bill.
    List(CommentsListArgs),
}

#[derive(Args, Debug)]
pub struct CommentsListArgs {
    pub bill_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct AttachmentsCmd {
    #[command(subcommand)]
    pub sub: AttachmentsSub,
}

#[derive(Subcommand, Debug)]
pub enum AttachmentsSub {
    Add(AttachmentsAddArgs),
    Get(AttachmentsGetArgs),
    Delete(IdArgs),
}

#[derive(Args, Debug)]
pub struct AttachmentsAddArgs {
    pub bill_id: String,
    pub files: Vec<PathBuf>,
}

#[derive(Args, Debug)]
pub struct AttachmentsGetArgs {
    pub bill_id: String,
    #[arg(short = 'o', long)]
    pub output: PathBuf,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "bills"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.bill_id)),
        Sub::Update(args) => common::update(ctx, &format!("{BASE}/{}", args.bill_id), &args.body),
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.bill_id);
            common::delete(ctx, &path, ID, &args.bill_id)
        }
        Sub::MarkVoid(args) => {
            let path = format!("{BASE}/{}/status/void", args.bill_id);
            common::action(ctx, &path, ID, &args.bill_id)
        }
        Sub::MarkOpen(args) => {
            let path = format!("{BASE}/{}/status/open", args.bill_id);
            common::action(ctx, &path, ID, &args.bill_id)
        }
        Sub::Email(args) => {
            let path = format!("{BASE}/{}/email", args.bill_id);
            common::action_with_body(ctx, &path, &args.body, ID, &args.bill_id)
        }
        Sub::Payments(p) => match p.sub {
            PaymentsSub::List(args) => {
                let path = format!("{BASE}/{}/payments", args.bill_id);
                common::list(ctx, &path, &args.list, "payments")
            }
            PaymentsSub::Apply(args) => {
                let path = format!("{BASE}/{}/payments", args.bill_id);
                common::create(ctx, &path, &args.body)
            }
            PaymentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/payments/{}", args.bill_id, args.bill_payment_id);
                common::delete(ctx, &path, "bill_payment_id", &args.bill_payment_id)
            }
        },
        Sub::Comments(c) => match c.sub {
            CommentsSub::List(args) => {
                let path = format!("{BASE}/{}/comments", args.bill_id);
                common::list(ctx, &path, &args.list, "comments")
            }
        },
        Sub::Attachments(a) => match a.sub {
            AttachmentsSub::Add(args) => attachments_add(args, ctx),
            AttachmentsSub::Get(args) => attachments_get(args, ctx),
            AttachmentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/attachment", args.bill_id);
                let resp = ctx.client.delete(&path, &Query::new())?;
                common::emit_success_raw(
                    &json!({
                        "bill_id": args.bill_id,
                        "deleted": true,
                        "response": resp,
                    }),
                    ctx,
                )
            }
        },
    }
}

fn attachments_add(args: AttachmentsAddArgs, ctx: &mut Ctx) -> Result<()> {
    let mut results: Vec<Value> = Vec::new();
    for file in &args.files {
        let mut entry = serde_json::Map::new();
        entry.insert("file".into(), Value::String(file.display().to_string()));
        match upload_one(&args.bill_id, file, ctx) {
            Ok(resp) => {
                entry.insert("ok".into(), Value::Bool(true));
                entry.insert("response".into(), resp);
            }
            // DryRunOk is a sentinel — propagate to short-circuit. Invariant 12 + 14.
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
    common::emit_success_raw(&json!({"bill_id": args.bill_id, "results": results}), ctx)
}

fn upload_one(bill_id: &str, file: &std::path::Path, ctx: &mut Ctx) -> Result<Value> {
    uploads::validate(file)?;
    let opts = RequestOptions {
        files: vec![FileUpload {
            field: "attachment".into(),
            path: file.to_path_buf(),
        }],
        ..RequestOptions::default()
    };
    ctx.client
        .post(&format!("{BASE}/{bill_id}/attachment"), opts)
}

fn attachments_get(args: AttachmentsGetArgs, ctx: &mut Ctx) -> Result<()> {
    let (bytes, content_type) = ctx.client.get_bytes(
        &format!("{BASE}/{}/attachment", args.bill_id),
        &Query::new(),
    )?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(ZohoError::from)?;
    }
    fs::write(&args.output, &bytes).map_err(ZohoError::from)?;
    common::emit_success_raw(
        &json!({
            "bill_id": args.bill_id,
            "saved_to": args.output.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        }),
        ctx,
    )
}
