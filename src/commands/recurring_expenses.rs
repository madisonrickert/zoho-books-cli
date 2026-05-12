//! `zb recurring-expenses` — CRUD + stop/resume + children + history over
//! `/recurringexpenses`. Stop/resume use POST /status/{stop|resume}.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;

const BASE: &str = "/recurringexpenses";
const ID_FIELD: &str = "recurring_expense_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List recurring expenses.
    List(ListArgs),
    /// Create a recurring expense.
    Create(BodyArgs),
    /// Get a single recurring expense by ID.
    Get(IdArgs),
    /// Update a recurring expense by ID.
    Update(UpdateArgs),
    /// Update a recurring expense by a custom field's unique value.
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    /// Delete a recurring expense by ID.
    Delete(IdArgs),
    /// Stop a recurring expense.
    Stop(IdArgs),
    /// Resume a recurring expense.
    Resume(IdArgs),
    /// List child expenses created from a recurring expense.
    Children(ChildrenArgs),
    /// List history / comments for a recurring expense.
    History(IdArgs),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    /// Zoho Books recurring_expense_id.
    pub recurring_expense_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub recurring_expense_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct ChildrenArgs {
    pub recurring_expense_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "recurring_expenses"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.recurring_expense_id)),
        Sub::Update(args) => common::update(
            ctx,
            &format!("{BASE}/{}", args.recurring_expense_id),
            &args.body,
        ),
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.recurring_expense_id);
            common::delete(ctx, &path, ID_FIELD, &args.recurring_expense_id)
        }
        Sub::Stop(args) => {
            let path = format!("{BASE}/{}/status/stop", args.recurring_expense_id);
            common::action(ctx, &path, ID_FIELD, &args.recurring_expense_id)
        }
        Sub::Resume(args) => {
            let path = format!("{BASE}/{}/status/resume", args.recurring_expense_id);
            common::action(ctx, &path, ID_FIELD, &args.recurring_expense_id)
        }
        Sub::Children(args) => common::nested_list(
            ctx,
            BASE,
            &args.recurring_expense_id,
            "expenses",
            &args.list,
            "expenses",
        ),
        Sub::History(args) => {
            let path = format!("{BASE}/{}/comments", args.recurring_expense_id);
            let resp = ctx.client.get(&path, &crate::shared::Query::new())?;
            common::emit_list_flat(&resp, "comments", ctx)
        }
    }
}
