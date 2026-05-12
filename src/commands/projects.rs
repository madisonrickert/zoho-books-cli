//! `zb projects` — CRUD + state + clone + invoices + users + tasks + comments.

use clap::{Args, Subcommand};

use crate::cli::Ctx;
use crate::commands::common::{self, BodyArgs, CustomFieldUpdateArgs, ListArgs};
use crate::errors::Result;
use crate::shared::Query;

const BASE: &str = "/projects";
const ID: &str = "project_id";

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
    #[command(name = "mark-active")]
    MarkActive(IdArgs),
    #[command(name = "mark-inactive")]
    MarkInactive(IdArgs),
    Clone(CloneArgs),
    /// List invoices associated with a project.
    Invoices(InvoicesArgs),
    Users(UsersCmd),
    Tasks(TasksCmd),
    Comments(CommentsCmd),
}

#[derive(Args, Debug)]
pub struct IdArgs {
    pub project_id: String,
}

#[derive(Args, Debug)]
pub struct UpdateArgs {
    pub project_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct CloneArgs {
    pub project_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct InvoicesArgs {
    pub project_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct UsersCmd {
    #[command(subcommand)]
    pub sub: UsersSub,
}

#[derive(Subcommand, Debug)]
pub enum UsersSub {
    /// List users assigned to a project (flat list, no pagination).
    List(IdArgs),
    Get(UserIdArgs),
    Add(UserAddArgs),
    Invite(UserAddArgs),
    Update(UserUpdateArgs),
    Delete(UserIdArgs),
}

#[derive(Args, Debug)]
pub struct UserIdArgs {
    pub project_id: String,
    pub user_id: String,
}

#[derive(Args, Debug)]
pub struct UserAddArgs {
    pub project_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct UserUpdateArgs {
    pub project_id: String,
    pub user_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct TasksCmd {
    #[command(subcommand)]
    pub sub: TasksSub,
}

#[derive(Subcommand, Debug)]
pub enum TasksSub {
    List(TasksListArgs),
    Get(TaskIdArgs),
    Add(TaskAddArgs),
    Update(TaskUpdateArgs),
    Delete(TaskIdArgs),
}

#[derive(Args, Debug)]
pub struct TasksListArgs {
    pub project_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct TaskIdArgs {
    pub project_id: String,
    pub task_id: String,
}

#[derive(Args, Debug)]
pub struct TaskAddArgs {
    pub project_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct TaskUpdateArgs {
    pub project_id: String,
    pub task_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct CommentsCmd {
    #[command(subcommand)]
    pub sub: CommentsSub,
}

#[derive(Subcommand, Debug)]
pub enum CommentsSub {
    List(CommentsListArgs),
    Add(CommentAddArgs),
    Delete(CommentIdArgs),
}

#[derive(Args, Debug)]
pub struct CommentsListArgs {
    pub project_id: String,
    #[command(flatten)]
    pub list: ListArgs,
}

#[derive(Args, Debug)]
pub struct CommentAddArgs {
    pub project_id: String,
    #[command(flatten)]
    pub body: BodyArgs,
}

#[derive(Args, Debug)]
pub struct CommentIdArgs {
    pub project_id: String,
    pub comment_id: String,
}

pub fn run(cmd: Cmd, ctx: &mut Ctx) -> Result<()> {
    match cmd.sub {
        Sub::List(args) => common::list(ctx, BASE, &args, "projects"),
        Sub::Create(args) => common::create(ctx, BASE, &args),
        Sub::Get(args) => common::get(ctx, &format!("{BASE}/{}", args.project_id)),
        Sub::Update(args) => {
            common::update(ctx, &format!("{BASE}/{}", args.project_id), &args.body)
        }
        Sub::UpdateByCustomField(args) => common::update_custom(ctx, BASE, &args),
        Sub::Delete(args) => {
            let path = format!("{BASE}/{}", args.project_id);
            common::delete(ctx, &path, ID, &args.project_id)
        }
        Sub::MarkActive(args) => {
            let path = format!("{BASE}/{}/active", args.project_id);
            common::action(ctx, &path, ID, &args.project_id)
        }
        Sub::MarkInactive(args) => {
            let path = format!("{BASE}/{}/inactive", args.project_id);
            common::action(ctx, &path, ID, &args.project_id)
        }
        Sub::Clone(args) => {
            let path = format!("{BASE}/{}/clone", args.project_id);
            // Clone returns the new project object — emit as object, not action.
            let opts = crate::client::RequestOptions {
                body: args.body.body_bytes()?,
                ..crate::client::RequestOptions::default()
            };
            let resp = ctx.client.post(&path, opts)?;
            common::emit_object(&resp, ctx)
        }
        Sub::Invoices(args) => {
            let path = format!("{BASE}/{}/invoices", args.project_id);
            common::list(ctx, &path, &args.list, "invoices")
        }
        Sub::Users(u) => match u.sub {
            UsersSub::List(args) => {
                let path = format!("{BASE}/{}/users", args.project_id);
                let resp = ctx.client.get(&path, &Query::new())?;
                common::emit_list_flat(&resp, "users", ctx)
            }
            UsersSub::Get(args) => common::get(
                ctx,
                &format!("{BASE}/{}/users/{}", args.project_id, args.user_id),
            ),
            UsersSub::Add(args) => common::create(
                ctx,
                &format!("{BASE}/{}/users", args.project_id),
                &args.body,
            ),
            UsersSub::Invite(args) => common::create(
                ctx,
                &format!("{BASE}/{}/users/invite", args.project_id),
                &args.body,
            ),
            UsersSub::Update(args) => common::update(
                ctx,
                &format!("{BASE}/{}/users/{}", args.project_id, args.user_id),
                &args.body,
            ),
            UsersSub::Delete(args) => {
                let path = format!("{BASE}/{}/users/{}", args.project_id, args.user_id);
                common::delete(ctx, &path, "user_id", &args.user_id)
            }
        },
        Sub::Tasks(t) => match t.sub {
            // Zoho returns singular "task" key for the list endpoint —
            // verified live in Python; preserved here.
            TasksSub::List(args) => {
                let path = format!("{BASE}/{}/tasks", args.project_id);
                common::list(ctx, &path, &args.list, "task")
            }
            TasksSub::Get(args) => common::get(
                ctx,
                &format!("{BASE}/{}/tasks/{}", args.project_id, args.task_id),
            ),
            TasksSub::Add(args) => common::create(
                ctx,
                &format!("{BASE}/{}/tasks", args.project_id),
                &args.body,
            ),
            TasksSub::Update(args) => common::update(
                ctx,
                &format!("{BASE}/{}/tasks/{}", args.project_id, args.task_id),
                &args.body,
            ),
            TasksSub::Delete(args) => {
                let path = format!("{BASE}/{}/tasks/{}", args.project_id, args.task_id);
                common::delete(ctx, &path, "task_id", &args.task_id)
            }
        },
        Sub::Comments(c) => match c.sub {
            CommentsSub::List(args) => {
                let path = format!("{BASE}/{}/comments", args.project_id);
                common::list(ctx, &path, &args.list, "comments")
            }
            CommentsSub::Add(args) => common::create(
                ctx,
                &format!("{BASE}/{}/comments", args.project_id),
                &args.body,
            ),
            CommentsSub::Delete(args) => {
                let path = format!("{BASE}/{}/comments/{}", args.project_id, args.comment_id);
                common::delete(ctx, &path, "comment_id", &args.comment_id)
            }
        },
    }
}
