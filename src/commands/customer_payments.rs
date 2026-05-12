//! `zb customer-payments` — CRUD + update-by-custom-field + refunds sub-app.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;

const BASE: &str = "/customerpayments";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    /// List customer payments.
    List(ListArgs),
    /// Create a customer payment.
    Create(BodyArgs),
    /// Get a single customer payment by ID.
    Get(IdArgs),
    /// Update a customer payment by ID.
    Update(UpdateArgs),
    /// Update a customer payment by a custom field's unique value.
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    /// Delete a customer payment by ID.
    Delete(IdArgs),
    /// Refunds on a customer payment.
    Refunds(RefundsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub payment_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub payment_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct RefundsCmd {
    #[command(subcommand)]
    pub sub: RefundsSub,
}

#[derive(Subcommand, Debug)]
pub enum RefundsSub {
    /// List refunds issued against a customer payment.
    List(RefundsListArgs),
    /// Issue a refund against a customer payment.
    Create(RefundsCreateArgs),
    /// Get a single refund on a customer payment.
    Get(RefundIdArgs),
    /// Update a refund on a customer payment.
    Update(RefundsUpdateArgs),
    /// Delete a refund on a customer payment.
    Delete(RefundIdArgs),
}

#[derive(Args, Debug)]
pub struct RefundsListArgs {
    pub payment_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct RefundsCreateArgs {
    pub payment_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct RefundIdArgs {
    pub payment_id: String,
    pub refund_id: String,
}

#[derive(Args, Debug)]
pub struct RefundsUpdateArgs {
    pub payment_id: String,
    pub refund_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "customerpayments"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.payment_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.payment_id), &args.body)
        }
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.payment_id);
            common::delete(ctx, &path, "payment_id", &args.payment_id)
        }
        Sub::Refunds(r) => match r.sub {
            RefundsSub::List(args) => common::nested_list(
                ctx,
                BASE,
                &args.payment_id,
                "refunds",
                &args.list,
                "payment_refunds",
            ),
            RefundsSub::Create(args) => {
                let path = format!("{BASE}/{}/refunds", args.payment_id);
                common::create(ctx, &path, &args.body)
            }
            RefundsSub::Get(args) => {
                let path = format!("{BASE}/{}/refunds/{}", args.payment_id, args.refund_id);
                common::get(ctx, &path)
            }
            RefundsSub::Update(args) => {
                let path = format!("{BASE}/{}/refunds/{}", args.payment_id, args.refund_id);
                common::update(ctx, &path, &args.body)
            }
            RefundsSub::Delete(args) => {
                let path = format!("{BASE}/{}/refunds/{}", args.payment_id, args.refund_id);
                common::delete(ctx, &path, "refund_id", &args.refund_id)
            }
        },
    }
}
