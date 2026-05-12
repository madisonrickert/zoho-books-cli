//! `zb contacts` — CRUD + search + activation + comments + addresses + persons.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;
use crate::shared::Query;

const BASE: &str = "/contacts";
const ID: &str = "contact_id";

#[derive(Args, Debug)]
pub struct Cmd {
    #[command(subcommand)]
    pub sub: Sub,
}

#[derive(Subcommand, Debug)]
pub enum Sub {
    List(ListArgs),
    /// Search contacts by name substring.
    Search(SearchArgs),
    Create(BodyArgs),
    Get(IdArgs),
    Update(UpdateArgs),
    #[command(name = "update-by-custom-field")]
    UpdateByCustomField(CustomFieldUpdateArgs),
    Delete(IdArgs),
    #[command(name = "mark-active")]
    MarkActive(IdArgs),
    #[command(name = "mark-inactive")]
    MarkInactive(IdArgs),
    /// List recent activity and comments on a contact.
    Comments(CommentsArgs),
    /// Additional addresses (list / add / update / delete).
    Addresses(AddressesCmd),
    /// Contact persons (CRUD + mark-primary).
    Persons(PersonsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub contact_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub contact_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct SearchArgs {
    /// Substring to match on contact_name.
    pub term: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct CommentsArgs {
    pub contact_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct AddressesCmd {
    #[command(subcommand)]
    pub sub: AddressesSub,
}

#[derive(Subcommand, Debug)]
pub enum AddressesSub {
    List(IdArgs),
    Add(AddressAddArgs),
    Update(AddressUpdateArgs),
    Delete(AddressIdArgs),
}

#[derive(Args, Debug)]
pub struct AddressAddArgs {
    pub contact_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct AddressUpdateArgs {
    pub contact_id: String,
    pub address_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct AddressIdArgs {
    pub contact_id: String,
    pub address_id: String,
}

#[derive(Args, Debug)]
pub struct PersonsCmd {
    #[command(subcommand)]
    pub sub: PersonsSub,
}

#[derive(Subcommand, Debug)]
pub enum PersonsSub {
    List(PersonsListArgs),
    Get(PersonIdArgs),
    Create(BodyArgs),
    Update(PersonUpdateArgs),
    Delete(PersonIdArgs),
    #[command(name = "mark-primary")]
    MarkPrimary(PersonIdArgs),
}

#[derive(Args, Debug)]
pub struct PersonsListArgs {
    /// Zoho Books contact_id (required by Zoho).
    pub contact_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct PersonIdArgs {
    pub contact_person_id: String,
}

#[derive(Args, Debug)]
pub struct PersonUpdateArgs {
    pub contact_person_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "contacts"),
        Sub::Search(args) => {
            let mut q = args.list.build_query()?;
            q.insert("contact_name_contains".into(), args.term);
            search_with_query(ctx, q, &args.list)
        }
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.contact_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.contact_id), &args.body)
        }
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.contact_id);
            common::delete(ctx, &path, ID, &args.contact_id)
        }
        Sub::MarkActive(args) => {
            let path = format!("{BASE}/{}/active", args.contact_id);
            common::action(ctx, &path, ID, &args.contact_id)
        }
        Sub::MarkInactive(args) => {
            let path = format!("{BASE}/{}/inactive", args.contact_id);
            common::action(ctx, &path, ID, &args.contact_id)
        }
        Sub::Comments(args) => {
            let path = format!("{BASE}/{}/comments", args.contact_id);
            common::list(ctx, &path, &args.list, "comments")
        }
        Sub::Addresses(a) => match a.sub {
            AddressesSub::List(args) => {
                let path = format!("{BASE}/{}/address", args.contact_id);
                let resp = ctx.client.get(&path, &Query::new())?;
                common::emit_list_flat(&resp, "addresses", ctx)
            }
            AddressesSub::Add(args) => common::create(
                ctx,
                &format!("{BASE}/{}/address", args.contact_id),
                &args.body,
            ),
            AddressesSub::Update(args) => common::update(
                ctx,
                &format!("{BASE}/{}/address/{}", args.contact_id, args.address_id),
                &args.body,
            ),
            AddressesSub::Delete(args) => {
                let path = format!("{BASE}/{}/address/{}", args.contact_id, args.address_id);
                common::delete(ctx, &path, "address_id", &args.address_id)
            }
        },
        Sub::Persons(p) => match p.sub {
            PersonsSub::List(args) => {
                let mut q = args.list.build_query()?;
                q.insert("contact_id".into(), args.contact_id);
                persons_list_with_query(ctx, q, &args.list)
            }
            PersonsSub::Get(args) => common::get(
                ctx,
                &format!("{BASE}/contactpersons/{}", args.contact_person_id),
            ),
            PersonsSub::Create(args) => {
                common::create(ctx, &format!("{BASE}/contactpersons"), &args)
            }
            PersonsSub::Update(args) => common::update(
                ctx,
                &format!("{BASE}/contactpersons/{}", args.contact_person_id),
                &args.body,
            ),
            PersonsSub::Delete(args) => {
                let path = format!("{BASE}/contactpersons/{}", args.contact_person_id);
                common::delete(ctx, &path, "contact_person_id", &args.contact_person_id)
            }
            PersonsSub::MarkPrimary(args) => {
                let path = format!("{BASE}/contactpersons/{}/primary", args.contact_person_id);
                common::action(ctx, &path, "contact_person_id", &args.contact_person_id)
            }
        },
    }
}

fn search_with_query(ctx: &mut Ctx, q: Query, list_args: &ListArgs) -> Result<()> {
    let mut stdout = std::io::stdout().lock();
    let opts = crate::shared::PageOpts {
        collection_key: "contacts",
        page_all: list_args.page_all,
        page_limit: list_args.page_limit,
        page_delay_ms: list_args.page_delay,
        format: ctx.format,
    };
    let client = &mut ctx.client;
    crate::shared::emit_list_paginated(|query| client.get(BASE, query), q, &opts, &mut stdout)?;
    Ok(())
}

fn persons_list_with_query(ctx: &mut Ctx, q: Query, list_args: &ListArgs) -> Result<()> {
    let path = format!("{BASE}/contactpersons");
    let mut stdout = std::io::stdout().lock();
    let opts = crate::shared::PageOpts {
        collection_key: "contact_persons",
        page_all: list_args.page_all,
        page_limit: list_args.page_limit,
        page_delay_ms: list_args.page_delay,
        format: ctx.format,
    };
    let client = &mut ctx.client;
    crate::shared::emit_list_paginated(|query| client.get(&path, query), q, &opts, &mut stdout)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::Ctx;

    #[test]
    fn list_targets_contacts() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .with_status(200)
            .with_body(r#"{"contacts":[]}"#)
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
