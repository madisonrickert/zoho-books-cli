//! `zb invoices` — CRUD + state + email + reminders + payments + credits +
//! comments + documents + attachments + templates + bulk PDF export.
//!
//! `export` wraps `GET /invoices/pdf?invoice_ids=ID1,ID2` (bulk-export), which
//! returns one combined PDF binary — no JSON envelope key to verify.

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

const BASE: &str = "/invoices";
const ID: &str = "invoice_id";

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
    #[command(name = "mark-sent")]
    MarkSent(IdArgs),
    #[command(name = "mark-void")]
    MarkVoid(IdArgs),
    #[command(name = "mark-draft")]
    MarkDraft(IdArgs),
    #[command(name = "write-off")]
    WriteOff(IdArgs),
    #[command(name = "cancel-write-off")]
    CancelWriteOff(IdArgs),
    Email(EmailArgs),
    Reminders(RemindersCmd),
    Payments(PaymentsCmd),
    Credits(CreditsCmd),
    Comments(CommentsCmd),
    Documents(DocumentsCmd),
    Templates(TemplatesCmd),
    Attachments(AttachmentsCmd),
    /// Bulk-export multiple invoices into a single combined PDF.
    Export(ExportArgs),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub invoice_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub invoice_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct EmailArgs {
    pub invoice_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct RemindersCmd {
    #[command(subcommand)]
    pub sub: RemindersSub,
}

#[derive(Subcommand, Debug)]
pub enum RemindersSub {
    /// Send a payment reminder for an invoice.
    Send(EmailArgs),
}

#[derive(Args, Debug)]
pub struct PaymentsCmd {
    #[command(subcommand)]
    pub sub: PaymentsSub,
}

#[derive(Subcommand, Debug)]
pub enum PaymentsSub {
    /// List payments applied to an invoice (read-only).
    List(InvoiceListArgs),
}

#[derive(Args, Debug)]
pub struct InvoiceListArgs {
    pub invoice_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct CreditsCmd {
    #[command(subcommand)]
    pub sub: CreditsSub,
}

#[derive(Subcommand, Debug)]
pub enum CreditsSub {
    /// List credits applied to an invoice.
    List(InvoiceListArgs),
    /// Apply existing credits or unused payments to an invoice.
    Apply(CreditsApplyArgs),
    /// Unapply a credit row from an invoice.
    Delete(CreditDeleteArgs),
}

#[derive(Args, Debug)]
pub struct CreditsApplyArgs {
    pub invoice_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct CreditDeleteArgs {
    pub invoice_id: String,
    pub credit_id: String,
}

#[derive(Args, Debug)]
pub struct CommentsCmd {
    #[command(subcommand)]
    pub sub: CommentsSub,
}

#[derive(Subcommand, Debug)]
pub enum CommentsSub {
    List(InvoiceListArgs),
    Add(CommentAddArgs),
    Delete(CommentDeleteArgs),
}

#[derive(Args, Debug)]
pub struct CommentAddArgs {
    pub invoice_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct CommentDeleteArgs {
    pub invoice_id: String,
    pub comment_id: String,
}

#[derive(Args, Debug)]
pub struct DocumentsCmd {
    #[command(subcommand)]
    pub sub: DocumentsSub,
}

#[derive(Subcommand, Debug)]
pub enum DocumentsSub {
    Get(DocumentIdArgs),
    Download(DocumentDownloadArgs),
    Delete(DocumentIdArgs),
}

#[derive(Args, Debug)]
pub struct DocumentIdArgs {
    pub invoice_id: String,
    pub document_id: String,
}

#[derive(Args, Debug)]
pub struct DocumentDownloadArgs {
    pub invoice_id: String,
    pub document_id: String,
    #[arg(short = 'o', long)]
    pub output: PathBuf,
    /// Render format (Zoho's responseformat query): pdf or html.
    #[arg(long, default_value = "pdf")]
    pub format: String,
}

#[derive(Args, Debug)]
pub struct TemplatesCmd {
    #[command(subcommand)]
    pub sub: TemplatesSub,
}

#[derive(Subcommand, Debug)]
pub enum TemplatesSub {
    /// List the org's invoice PDF templates.
    List(ListArgs),
    /// Apply a PDF template to an invoice.
    Apply(TemplateApplyArgs),
}

#[derive(Args, Debug)]
pub struct TemplateApplyArgs {
    pub invoice_id: String,
    pub template_id: String,
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
    pub invoice_id: String,
    pub files: Vec<PathBuf>,
}

#[derive(Args, Debug)]
pub struct AttachmentsGetArgs {
    pub invoice_id: String,
    #[arg(short = 'o', long)]
    pub output: PathBuf,
}

#[derive(Args, Debug)]
pub struct ExportArgs {
    /// Invoice IDs to combine into a single PDF (at least one).
    #[arg(required = true)]
    pub invoice_ids: Vec<String>,
    /// Destination path for the combined PDF.
    #[arg(short = 'o', long)]
    pub output: PathBuf,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "invoices"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.invoice_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.invoice_id), &args.body)
        }
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.invoice_id);
            common::delete(ctx, &path, ID, &args.invoice_id)
        }
        Sub::MarkSent(args) => act(
            ctx,
            &format!("{BASE}/{}/status/sent", args.invoice_id),
            &args.invoice_id,
        ),
        Sub::MarkVoid(args) => act(
            ctx,
            &format!("{BASE}/{}/status/void", args.invoice_id),
            &args.invoice_id,
        ),
        Sub::MarkDraft(args) => act(
            ctx,
            &format!("{BASE}/{}/status/draft", args.invoice_id),
            &args.invoice_id,
        ),
        Sub::WriteOff(args) => act(
            ctx,
            &format!("{BASE}/{}/writeoff", args.invoice_id),
            &args.invoice_id,
        ),
        Sub::CancelWriteOff(args) => act(
            ctx,
            &format!("{BASE}/{}/writeoff/cancel", args.invoice_id),
            &args.invoice_id,
        ),
        Sub::Email(args) => act_with_body(
            ctx,
            &format!("{BASE}/{}/email", args.invoice_id),
            &args.body,
            &args.invoice_id,
        ),
        Sub::Reminders(r) => match r.sub {
            RemindersSub::Send(args) => act_with_body(
                ctx,
                &format!("{BASE}/{}/paymentreminder", args.invoice_id),
                &args.body,
                &args.invoice_id,
            ),
        },
        Sub::Payments(p) => match p.sub {
            PaymentsSub::List(args) => common::list(
                ctx,
                &format!("{BASE}/{}/payments", args.invoice_id),
                &args.list,
                "payments",
            ),
        },
        Sub::Credits(c) => match c.sub {
            CreditsSub::List(args) => common::list(
                ctx,
                &format!("{BASE}/{}/creditsapplied", args.invoice_id),
                &args.list,
                "credits",
            ),
            CreditsSub::Apply(args) => common::create(
                ctx,
                &format!("{BASE}/{}/credits", args.invoice_id),
                &args.body,
            ),
            CreditsSub::Delete(args) => {
                let path = format!(
                    "{BASE}/{}/creditsapplied/{}",
                    args.invoice_id, args.credit_id
                );
                common::delete(ctx, &path, "credit_id", &args.credit_id)
            }
        },
        Sub::Comments(c) => match c.sub {
            CommentsSub::List(args) => common::list(
                ctx,
                &format!("{BASE}/{}/comments", args.invoice_id),
                &args.list,
                "comments",
            ),
            CommentsSub::Add(args) => common::create(
                ctx,
                &format!("{BASE}/{}/comments", args.invoice_id),
                &args.body,
            ),
            CommentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/comments/{}", args.invoice_id, args.comment_id);
                common::delete(ctx, &path, "comment_id", &args.comment_id)
            }
        },
        Sub::Documents(d) => match d.sub {
            DocumentsSub::Get(args) => common::get(
                ctx,
                &format!("{BASE}/{}/documents/{}", args.invoice_id, args.document_id),
            ),
            DocumentsSub::Download(args) => download_document(args, ctx),
            DocumentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/documents/{}", args.invoice_id, args.document_id);
                common::delete(ctx, &path, "document_id", &args.document_id)
            }
        },
        Sub::Templates(t) => match t.sub {
            TemplatesSub::List(args) => {
                common::list(ctx, &format!("{BASE}/templates"), &args, "templates")
            }
            TemplatesSub::Apply(args) => {
                let path = format!("{BASE}/{}/templates/{}", args.invoice_id, args.template_id);
                let resp = ctx.client.put(&path, RequestOptions::default())?;
                common::emit_action(ID, &args.invoice_id, &resp, ctx)
            }
        },
        Sub::Attachments(a) => match a.sub {
            AttachmentsSub::Add(args) => attachments_add(args, ctx),
            AttachmentsSub::Get(args) => attachments_get(args, ctx),
            AttachmentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/attachment", args.invoice_id);
                let resp = ctx.client.delete(&path, &Query::new())?;
                common::emit_success_raw(
                    &json!({
                        "invoice_id": args.invoice_id,
                        "deleted": true,
                        "response": resp,
                    }),
                    ctx,
                )
            }
        },
        Sub::Export(args) => export_pdf(args, ctx),
    }
}

fn act(ctx: &mut Ctx, path: &str, invoice_id: &str) -> Result<()> {
    common::action(ctx, path, ID, invoice_id)
}

fn act_with_body(ctx: &mut Ctx, path: &str, body: &BodyArgs, invoice_id: &str) -> Result<()> {
    common::action_with_body(ctx, path, body, ID, invoice_id)
}

fn download_document(args: DocumentDownloadArgs, ctx: &mut Ctx) -> Result<()> {
    if args.format != "pdf" && args.format != "html" {
        return Err(ZohoError::validation("--format must be 'pdf' or 'html'."));
    }
    let mut q = Query::new();
    q.insert("responseformat".into(), args.format.clone());
    let (bytes, content_type) = ctx.client.get_bytes(
        &format!("{BASE}/{}/documents/{}", args.invoice_id, args.document_id),
        &q,
    )?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(ZohoError::from)?;
    }
    fs::write(&args.output, &bytes).map_err(ZohoError::from)?;
    common::emit_success_raw(
        &json!({
            "invoice_id": args.invoice_id,
            "document_id": args.document_id,
            "format": args.format,
            "saved_to": args.output.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        }),
        ctx,
    )
}

fn export_pdf(args: ExportArgs, ctx: &mut Ctx) -> Result<()> {
    let mut q = Query::new();
    q.insert("invoice_ids".into(), args.invoice_ids.join(","));
    let (bytes, content_type) = ctx.client.get_bytes(&format!("{BASE}/pdf"), &q)?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(ZohoError::from)?;
    }
    fs::write(&args.output, &bytes).map_err(ZohoError::from)?;
    common::emit_success_raw(
        &json!({
            "invoice_ids": args.invoice_ids,
            "count": args.invoice_ids.len(),
            "saved_to": args.output.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        }),
        ctx,
    )
}

fn attachments_add(args: AttachmentsAddArgs, ctx: &mut Ctx) -> Result<()> {
    let mut results: Vec<Value> = Vec::new();
    for file in &args.files {
        let mut entry = serde_json::Map::new();
        entry.insert("file".into(), Value::String(file.display().to_string()));
        match upload_one(&args.invoice_id, file, ctx) {
            Ok(resp) => {
                entry.insert("ok".into(), Value::Bool(true));
                entry.insert("response".into(), resp);
            }
            // DryRunOk is a sentinel — propagate to short-circuit. Invariant 12 + 14.
            Err(e) if matches!(e.kind, crate::errors::ErrorKind::DryRunOk) => return Err(e),
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
    common::emit_success_raw(
        &json!({"invoice_id": args.invoice_id, "results": results}),
        ctx,
    )
}

fn upload_one(invoice_id: &str, file: &std::path::Path, ctx: &mut Ctx) -> Result<Value> {
    uploads::validate(file)?;
    let opts = RequestOptions {
        files: vec![FileUpload {
            field: "attachment".into(),
            path: file.to_path_buf(),
        }],
        ..RequestOptions::default()
    };
    ctx.client
        .post(&format!("{BASE}/{invoice_id}/attachment"), opts)
}

fn attachments_get(args: AttachmentsGetArgs, ctx: &mut Ctx) -> Result<()> {
    let (bytes, content_type) = ctx.client.get_bytes(
        &format!("{BASE}/{}/attachment", args.invoice_id),
        &Query::new(),
    )?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent).map_err(ZohoError::from)?;
    }
    fs::write(&args.output, &bytes).map_err(ZohoError::from)?;
    common::emit_success_raw(
        &json!({
            "invoice_id": args.invoice_id,
            "saved_to": args.output.display().to_string(),
            "size_bytes": bytes.len(),
            "content_type": content_type,
        }),
        ctx,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn export_targets_invoices_pdf() {
        use std::fs;
        use tempfile::TempDir;

        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/invoices/pdf")
            .match_query(mockito::Matcher::UrlEncoded(
                "invoice_ids".into(),
                "123,456".into(),
            ))
            .with_status(200)
            .with_header("content-type", "application/pdf")
            .with_body(b"%PDF-1.4\ncombined")
            .create();

        let tmp = TempDir::new().unwrap();
        let out = tmp.path().join("invoices.pdf");
        let mut ctx = Ctx::new_for_test(&server.url());
        run(
            Cmd {
                sub: Sub::Export(ExportArgs {
                    invoice_ids: vec!["123".into(), "456".into()],
                    output: out.clone(),
                }),
            },
            &mut ctx,
        )
        .unwrap();
        m.assert();
        assert_eq!(fs::read(&out).unwrap(), b"%PDF-1.4\ncombined");
    }

    #[test]
    fn export_dry_run_short_circuits_before_send() {
        use crate::errors::ErrorKind;
        use tempfile::TempDir;

        let tmp = TempDir::new().unwrap();
        let out = tmp.path().join("invoices.pdf");
        // Unreachable URL: any real HTTP send errors with a connection error, so
        // the only way this returns DryRunOk is the pre-send short-circuit.
        let mut ctx = Ctx::new_for_test_dry_run("http://127.0.0.1:1");
        let err = export_pdf(
            ExportArgs {
                invoice_ids: vec!["123".into()],
                output: out.clone(),
            },
            &mut ctx,
        )
        .expect_err("dry-run must short-circuit before any HTTP send");
        assert!(
            matches!(err.kind, ErrorKind::DryRunOk),
            "expected DryRunOk, got {:?}",
            err.kind
        );
        assert!(!out.exists(), "dry-run must not write the output file");
    }

    #[test]
    fn export_404_writes_no_file_and_no_parent_dir() {
        use tempfile::TempDir;

        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/invoices/pdf")
            .match_query(mockito::Matcher::Any)
            .with_status(404)
            .with_body(r#"{"code":4,"message":"not found"}"#)
            .create();

        let tmp = TempDir::new().unwrap();
        // Nested path: the parent dir does not exist yet. On failure the handler
        // must error out of get_bytes before create_dir_all/write run.
        let parent = tmp.path().join("nested");
        let out = parent.join("invoices.pdf");
        let mut ctx = Ctx::new_for_test(&server.url());
        export_pdf(
            ExportArgs {
                invoice_ids: vec!["123".into()],
                output: out.clone(),
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

    #[test]
    fn list_targets_invoices() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/invoices")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"invoices":[]}"#)
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
}
