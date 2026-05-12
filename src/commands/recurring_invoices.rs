//! `zb recurring-invoices` — CRUD + stop/resume + history + templates over
//! `/recurringinvoices`.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::client::RequestOptions;
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;
use crate::shared::Query;

const BASE: &str = "/recurringinvoices";
const ID_FIELD: &str = "recurring_invoice_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List recurring invoices.
    List(ListArgs),
    /// Create a recurring invoice.
    Create(BodyArgs),
    /// Get a single recurring invoice by ID.
    Get(IdArgs),
    /// Update a recurring invoice by ID.
    Update(UpdateArgs),
    /// Update a recurring invoice by a custom field's unique value.
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    /// Delete a recurring invoice by ID.
    Delete(IdArgs),
    /// Stop a recurring invoice.
    Stop(IdArgs),
    /// Resume a stopped recurring invoice.
    Resume(IdArgs),
    /// List history / comments for a recurring invoice (read-only).
    History(IdArgs),
    /// Per-recurring-invoice template assignment.
    Templates(TemplatesCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub recurring_invoice_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub recurring_invoice_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct TemplatesCmd {
    #[command(subcommand)]
    pub sub: TemplatesSub,
}

#[derive(Subcommand, Debug)]
pub enum TemplatesSub {
    /// Apply a PDF template to a recurring invoice.
    Apply(ApplyArgs),
}

#[derive(Args, Debug)]
pub struct ApplyArgs {
    pub recurring_invoice_id: String,
    pub template_id: String,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "recurring_invoices"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.recurring_invoice_id)),
        Sub::Update(args) => common::update(
            ctx,
            &format!("{BASE}/{}", args.recurring_invoice_id),
            &args.body,
        ),
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.recurring_invoice_id);
            common::delete(ctx, &path, ID_FIELD, &args.recurring_invoice_id)
        }
        Sub::Stop(args) => {
            let path = format!("{BASE}/{}/status/stop", args.recurring_invoice_id);
            common::action(ctx, &path, ID_FIELD, &args.recurring_invoice_id)
        }
        Sub::Resume(args) => {
            let path = format!("{BASE}/{}/status/resume", args.recurring_invoice_id);
            common::action(ctx, &path, ID_FIELD, &args.recurring_invoice_id)
        }
        Sub::History(args) => {
            let path = format!("{BASE}/{}/comments", args.recurring_invoice_id);
            let resp = ctx.client.get(&path, &Query::new())?;
            common::emit_list_flat(&resp, "comments", ctx)
        }
        Sub::Templates(t) => match t.sub {
            TemplatesSub::Apply(args) => {
                let path = format!(
                    "{BASE}/{}/templates/{}",
                    args.recurring_invoice_id, args.template_id
                );
                let resp = ctx.client.put(&path, RequestOptions::default())?;
                common::emit_action(ID_FIELD, &args.recurring_invoice_id, &resp, ctx)
            }
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn list_targets_recurringinvoices() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/recurringinvoices")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"recurring_invoices":[]}"#)
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
