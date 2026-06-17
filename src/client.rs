//! HTTP plumbing around `reqwest::blocking`. Owns `RuntimeConfig` + access
//! token + storage handle (shared as `Arc<dyn Storage>` with the rest of
//! the program). Responsibilities:
//!
//! - Region routing (`cfg.region.api_url` -> request URL).
//! - `organization_id` auto-injection on every request unless
//!   `RequestOptions.skip_org_id`.
//! - 401 -> silent refresh -> retry-once. State carried in `RetryState`
//!   so a second 401 after the refresh can't loop.
//! - 429 -> up to 3 retries; honors numeric `Retry-After`, otherwise
//!   exponential `min(2**n, 30)` backoff.
//! - `--dry-run` short-circuit: emits a preview envelope to stdout
//!   (with `Authorization` scrubbed) and returns `Err(DryRunOk)`.
//! - Multipart upload path (separate `reqwest::blocking::Client` with a
//!   longer timeout).
//!
//! Request bodies are sent as raw `Vec<u8>` (never `.json(...)`) so
//! 19-digit Zoho IDs reach the wire byte-perfect.

use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::Method;
use reqwest::blocking::multipart;
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use serde_json::{Value, json};

use crate::auth;
use crate::cli::OutputFormat;
use crate::config::{self, RuntimeConfig};
use crate::errors::{ErrorKind, Result, ZohoError};
use crate::output;
use crate::shared::Query;
use crate::storage::Storage;
use crate::uploads;

pub const API_PREFIX: &str = "/books/v3";
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30);
pub const UPLOAD_TIMEOUT: Duration = Duration::from_secs(120);
pub const MAX_429_RETRIES: u32 = 3;
const REFRESH_BUFFER_SECS: f64 = 30.0;
const MAX_BACKOFF_SECS: u64 = 30;

/// A multipart-form upload field. `field` is the form-data name (e.g. "receipt"),
/// `path` is the file on disk. Extension and size are validated by uploads::validate
/// before send.
#[derive(Debug, Clone)]
pub struct FileUpload {
    pub field: String,
    pub path: PathBuf,
}

#[derive(Debug, Default)]
pub struct RequestOptions {
    pub query: Query,
    pub body: Option<Vec<u8>>,
    pub headers: Vec<(String, String)>,
    pub files: Vec<FileUpload>,
    pub raw_bytes: bool,
    /// When true, don't inject organization_id into the query params and don't
    /// require it to be set in config. Used by `zb org list` since /organizations
    /// is a top-level endpoint that doesn't filter by org.
    pub skip_org_id: bool,
}

pub enum ResponseBody {
    /// Parsed JSON response (default).
    Json(Value),
    /// Raw bytes + content-type (for receipt/attachment downloads).
    Bytes {
        content: Vec<u8>,
        content_type: Option<String>,
    },
}

impl ResponseBody {
    pub fn into_json(self) -> Result<Value> {
        match self {
            ResponseBody::Json(v) => Ok(v),
            ResponseBody::Bytes { .. } => {
                Err(ZohoError::api("expected JSON response, got binary body"))
            }
        }
    }
}

pub struct Client {
    pub cfg: RuntimeConfig,
    storage: Arc<dyn Storage>,
    http: reqwest::blocking::Client,
    upload_http: reqwest::blocking::Client,
    dry_run: bool,
    format: OutputFormat,
    /// If Some, all requests target this URL instead of cfg.region.api_url — for tests.
    override_base: Option<String>,
    /// If Some, refresh requests target this accounts URL instead of cfg.region.accounts_url
    /// — for tests that need to exercise the 401→refresh→retry path without hitting Zoho.
    override_accounts: Option<String>,
}

impl Client {
    pub fn new(
        cfg: RuntimeConfig,
        storage: Arc<dyn Storage>,
        dry_run: bool,
        format: OutputFormat,
    ) -> Result<Self> {
        let http = reqwest::blocking::Client::builder()
            .timeout(DEFAULT_TIMEOUT)
            .user_agent(concat!("zb/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| ZohoError::network(format!("HTTP client init failed: {e}")))?;
        let upload_http = reqwest::blocking::Client::builder()
            .timeout(UPLOAD_TIMEOUT)
            .user_agent(concat!("zb/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| ZohoError::network(format!("HTTP client init failed: {e}")))?;
        Ok(Self {
            cfg,
            storage,
            http,
            upload_http,
            dry_run,
            format,
            override_base: None,
            override_accounts: None,
        })
    }

    /// Test helper: replace the API base URL. Production code never calls this.
    #[cfg(test)]
    pub fn with_api_override(mut self, base: impl Into<String>) -> Self {
        self.override_base = Some(base.into());
        self
    }

    /// Test helper: replace the accounts URL used by the OAuth refresh path so
    /// the 401-refresh-retry-once state machine can be exercised against a
    /// single mockito server. Production code never calls this.
    #[cfg(test)]
    pub fn with_accounts_override(mut self, accounts: impl Into<String>) -> Self {
        self.override_accounts = Some(accounts.into());
        self
    }

    pub fn get(&mut self, path: &str, query: &Query) -> Result<Value> {
        let opts = RequestOptions {
            query: query.clone(),
            ..RequestOptions::default()
        };
        self.request(Method::GET, path, opts)?.into_json()
    }

    pub fn get_no_org(&mut self, path: &str, query: &Query) -> Result<Value> {
        let opts = RequestOptions {
            query: query.clone(),
            skip_org_id: true,
            ..RequestOptions::default()
        };
        self.request(Method::GET, path, opts)?.into_json()
    }

    pub fn get_bytes(&mut self, path: &str, query: &Query) -> Result<(Vec<u8>, Option<String>)> {
        let opts = RequestOptions {
            query: query.clone(),
            raw_bytes: true,
            ..RequestOptions::default()
        };
        match self.request(Method::GET, path, opts)? {
            ResponseBody::Bytes {
                content,
                content_type,
            } => Ok((content, content_type)),
            ResponseBody::Json(_) => Err(ZohoError::api("expected binary response, got JSON")),
        }
    }

    pub fn post(&mut self, path: &str, opts: RequestOptions) -> Result<Value> {
        self.request(Method::POST, path, opts)?.into_json()
    }

    pub fn put(&mut self, path: &str, opts: RequestOptions) -> Result<Value> {
        self.request(Method::PUT, path, opts)?.into_json()
    }

    pub fn delete(&mut self, path: &str, query: &Query) -> Result<Value> {
        let opts = RequestOptions {
            query: query.clone(),
            ..RequestOptions::default()
        };
        self.request(Method::DELETE, path, opts)?.into_json()
    }

    fn request(
        &mut self,
        method: Method,
        path: &str,
        opts: RequestOptions,
    ) -> Result<ResponseBody> {
        config::require_auth(&self.cfg)?;

        let url = self.build_url(path);
        let mut params: Vec<(String, String)> = Vec::new();
        if !opts.skip_org_id {
            let org_id = config::require_org(&self.cfg)?.to_string();
            params.push(("organization_id".into(), org_id));
        }
        for (k, v) in &opts.query {
            params.push((k.clone(), v.clone()));
        }

        if self.dry_run {
            self.emit_dry_run_preview(&method, &url, &params, &opts)?;
            return Err(ZohoError::new(
                ErrorKind::DryRunOk,
                "dry-run preview emitted",
            ));
        }

        self.request_with_retry(method, &url, &params, &opts, RetryState::default())
    }

    fn request_with_retry(
        &mut self,
        method: Method,
        url: &str,
        params: &[(String, String)],
        opts: &RequestOptions,
        mut state: RetryState,
    ) -> Result<ResponseBody> {
        loop {
            let access = self.ensure_access_token()?;
            let mut headers = HeaderMap::new();
            headers.insert(
                reqwest::header::AUTHORIZATION,
                HeaderValue::try_from(format!("Zoho-oauthtoken {access}"))
                    .map_err(|e| ZohoError::validation(format!("bad auth header: {e}")))?,
            );
            for (k, v) in &opts.headers {
                let name = HeaderName::try_from(k.as_bytes())
                    .map_err(|e| ZohoError::validation(format!("bad header name {k}: {e}")))?;
                let val = HeaderValue::try_from(v.as_bytes())
                    .map_err(|e| ZohoError::validation(format!("bad header value for {k}: {e}")))?;
                headers.insert(name, val);
            }

            let resp = if opts.files.is_empty() {
                let mut req = self.http.request(method.clone(), url).headers(headers);
                req = req.query(params);
                if let Some(body) = &opts.body {
                    req = req
                        .header(reqwest::header::CONTENT_TYPE, "application/json")
                        .body(body.clone());
                }
                req.send()
            } else {
                let mut form = multipart::Form::new();
                for upload in &opts.files {
                    uploads::validate(&upload.path)?;
                    let mime = uploads::guess_mime(&upload.path);
                    let part = multipart::Part::file(&upload.path)
                        .map_err(|e| {
                            ZohoError::validation(format!(
                                "failed to open {}: {e}",
                                upload.path.display()
                            ))
                        })?
                        .mime_str(mime)
                        .map_err(|e| ZohoError::validation(format!("bad MIME for upload: {e}")))?;
                    form = form.part(upload.field.clone(), part);
                }
                self.upload_http
                    .request(method.clone(), url)
                    .headers(headers)
                    .query(params)
                    .multipart(form)
                    .send()
            };

            let resp = match resp {
                Ok(r) => r,
                Err(e) if e.is_timeout() => {
                    return Err(ZohoError::network(format!("Request timed out: {e}")));
                }
                Err(e) => {
                    return Err(ZohoError::network(format!("Network error: {e}")));
                }
            };

            let status = resp.status();

            if status.as_u16() == 401 && !state.refreshed {
                self.refresh_token()?;
                state.refreshed = true;
                continue;
            }

            if status.as_u16() == 429 {
                if state.retries >= MAX_429_RETRIES {
                    return Err(
                        ZohoError::rate_limited("Rate limit exceeded; retries exhausted.")
                            .with_details(json!({
                                "max_retries": MAX_429_RETRIES,
                            })),
                    );
                }
                let retry_after = parse_retry_after(resp.headers());
                let delay = retry_after
                    .unwrap_or_else(|| (1u64 << state.retries.min(5)).min(MAX_BACKOFF_SECS));
                thread::sleep(Duration::from_secs(delay));
                state.retries += 1;
                continue;
            }

            if opts.raw_bytes && status.is_success() {
                let content_type = resp
                    .headers()
                    .get(reqwest::header::CONTENT_TYPE)
                    .and_then(|v| v.to_str().ok())
                    .map(str::to_owned);
                let bytes = resp
                    .bytes()
                    .map_err(|e| ZohoError::network(format!("Failed to read body: {e}")))?
                    .to_vec();
                return Ok(ResponseBody::Bytes {
                    content: bytes,
                    content_type,
                });
            }

            return parse_json_response(resp).map(ResponseBody::Json);
        }
    }

    fn build_url(&self, path: &str) -> String {
        let base = self
            .override_base
            .clone()
            .unwrap_or_else(|| self.cfg.region.api_url.to_string());
        let path = if path.starts_with('/') {
            path.to_owned()
        } else {
            format!("/{path}")
        };
        if path.starts_with(API_PREFIX) {
            format!("{base}{path}")
        } else {
            format!("{base}{API_PREFIX}{path}")
        }
    }

    fn ensure_access_token(&mut self) -> Result<String> {
        let now = now_unix_secs();
        if let (Some(at), Some(expires)) = (self.cfg.access_token.as_ref(), self.cfg.expires_at)
            && expires - REFRESH_BUFFER_SECS > now
        {
            return Ok(at.clone());
        }
        self.refresh_token()
    }

    fn refresh_token(&mut self) -> Result<String> {
        config::require_auth(&self.cfg)?;
        let client_id = self.cfg.client_id.as_deref().unwrap_or_default();
        let client_secret = self.cfg.client_secret.as_deref().unwrap_or_default();
        let refresh_token = self.cfg.refresh_token.as_deref().unwrap_or_default();
        let accounts_url = self
            .override_accounts
            .as_deref()
            .unwrap_or(self.cfg.region.accounts_url);
        let body =
            auth::refresh_access_token_at(accounts_url, client_id, client_secret, refresh_token)?;
        let access = body.access_token.clone();
        let expires_at = now_unix_secs() + body.expires_in as f64;
        self.cfg.access_token = Some(access.clone());
        self.cfg.expires_at = Some(expires_at);
        config::update_access_token(self.storage.as_ref(), &access, expires_at)?;
        Ok(access)
    }

    fn emit_dry_run_preview(
        &self,
        method: &Method,
        url: &str,
        params: &[(String, String)],
        opts: &RequestOptions,
    ) -> Result<()> {
        let mut query_obj = serde_json::Map::new();
        for (k, v) in params {
            query_obj.insert(k.clone(), Value::String(v.clone()));
        }
        let mut headers_obj = serde_json::Map::new();
        // Scrub Authorization (invariant 12).
        for (k, v) in &opts.headers {
            if k.eq_ignore_ascii_case("authorization") {
                continue;
            }
            headers_obj.insert(k.clone(), Value::String(v.clone()));
        }
        let body_value: Value = match &opts.body {
            None => Value::Null,
            Some(bytes) => serde_json::from_slice(bytes)
                .unwrap_or_else(|_| Value::String(String::from_utf8_lossy(bytes).into_owned())),
        };
        let files_value = if opts.files.is_empty() {
            Value::Null
        } else {
            let arr: Vec<Value> = opts
                .files
                .iter()
                .map(|f| {
                    json!({
                        "field": f.field,
                        "filename": f.path.file_name().and_then(|n| n.to_str()).unwrap_or(""),
                        "mime": uploads::guess_mime(&f.path),
                    })
                })
                .collect();
            Value::Array(arr)
        };
        let payload = json!({
            "dry_run": true,
            "method": method.to_string(),
            "url": url,
            "query": Value::Object(query_obj),
            "headers": Value::Object(headers_obj),
            "json_body": body_value,
            "files": files_value,
        });
        let mut stdout = std::io::stdout().lock();
        output::emit_success(&payload, self.format, &mut stdout)
            .map_err(|e| ZohoError::network(format!("stdout write failed: {e}")))?;
        let _ = stdout.flush();
        Ok(())
    }
}

#[derive(Debug, Default, Clone, Copy)]
struct RetryState {
    refreshed: bool,
    retries: u32,
}

fn now_unix_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// Numeric `Retry-After: <seconds>` parsing only. RFC 9110 also allows
/// HTTP-date form (`Retry-After: Wed, 21 Oct 2015 07:28:00 GMT`), but Zoho's
/// API docs (https://www.zoho.com/books/api/v3/introduction/#organization-id)
/// never mention `Retry-After` at all — they only describe the 429 status
/// codes (44, 45, 1070) with messages like "try again after some time."
/// In practice Zoho appears to send numeric seconds when it sends the header
/// at all; this matches Python's `int(raw)` behavior. Non-numeric values fall
/// through to exponential backoff (capped at MAX_BACKOFF_SECS).
fn parse_retry_after(headers: &HeaderMap) -> Option<u64> {
    let raw = headers.get(reqwest::header::RETRY_AFTER)?.to_str().ok()?;
    raw.trim().parse::<u64>().ok()
}

fn parse_json_response(resp: reqwest::blocking::Response) -> Result<Value> {
    let status = resp.status();
    let body_text = resp
        .text()
        .map_err(|e| ZohoError::network(format!("Failed to read response body: {e}")))?;
    let body: Value = serde_json::from_str(&body_text).unwrap_or(Value::String(body_text.clone()));

    if status.is_success() {
        return Ok(body);
    }

    let message = body
        .get("message")
        .and_then(|m| m.as_str())
        .map(str::to_owned);
    let zoho_code = body.get("code").cloned().unwrap_or(Value::Null);
    let hint = hint_for_zoho_code(&zoho_code);
    let mut details = json!({
        "http_status": status.as_u16(),
        "zoho_code": zoho_code,
        "body": body,
    });
    if let Some(h) = hint {
        details["hint"] = Value::String(h.to_owned());
    }

    if status.as_u16() == 404 {
        return Err(
            ZohoError::not_found(message.unwrap_or_else(|| "Resource not found.".into()))
                .with_details(details),
        );
    }

    Err(
        ZohoError::api(message.unwrap_or_else(|| format!("Zoho API returned {}", status.as_u16())))
            .with_details(details),
    )
}

/// Actionable hint for specific Zoho error codes, surfaced (when present) in the
/// error envelope's `details.hint`. This is additive: most codes have no hint and
/// the key is simply absent. The code is matched on its string form because
/// `arbitrary_precision` forbids the numeric `Number` accessors (see AGENTS.md).
fn hint_for_zoho_code(code: &Value) -> Option<&'static str> {
    let code_str = match code {
        Value::Number(n) => n.as_str(),
        Value::String(s) => s.as_str(),
        _ => return None,
    };
    match code_str {
        // 108004 fires when the account being matched differs from the
        // transaction's own bank/credit-card account. The common trigger is
        // categorizing a credit-card-account transaction as an expense without
        // telling Zoho the money came from the card.
        "108004" => Some(
            "The account being matched differs from the bank/credit-card account the transaction belongs to. \
             When categorizing a credit-card-account transaction as an expense, add \
             \"paid_through_account_id\":\"<card_account_id>\" (the card account) to the body. \
             If Zoho still rejects it, create the expense with that paid_through_account_id and then run \
             'bank-transactions match'. For 'bank-transactions match', pass --query account_id=<the transaction's own account>.",
        ),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::regions;
    use crate::storage::MemoryStorage;

    fn test_cfg(_api_override: Option<&str>) -> RuntimeConfig {
        RuntimeConfig {
            region: regions::resolve("us").unwrap(),
            org_id: Some("123".into()),
            client_id: Some("cid".into()),
            client_secret: Some("csec".into()),
            refresh_token: Some("rt".into()),
            access_token: Some("at".into()),
            expires_at: Some(now_unix_secs() + 3600.0),
        }
    }

    fn make_client(cfg: RuntimeConfig, base: &str) -> Client {
        let storage = Arc::new(MemoryStorage::new());
        Client::new(cfg, storage, false, OutputFormat::Json)
            .unwrap()
            .with_api_override(base)
    }

    #[test]
    fn get_includes_org_id_query_param() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/organizations")
            .match_query(mockito::Matcher::UrlEncoded(
                "organization_id".into(),
                "123".into(),
            ))
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"organizations":[{"organization_id":"123"}]}"#)
            .create();

        let mut client = make_client(test_cfg(None), &server.url());
        let resp = client.get("/organizations", &Query::new()).unwrap();
        assert!(resp.get("organizations").is_some());
        m.assert();
    }

    #[test]
    fn auth_header_uses_zoho_oauthtoken_format() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("GET", "/books/v3/organizations")
            .match_query(mockito::Matcher::Any)
            .match_header("authorization", "Zoho-oauthtoken at")
            .with_status(200)
            .with_body(r#"{"organizations":[]}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        client.get("/organizations", &Query::new()).unwrap();
        m.assert();
    }

    #[test]
    fn returns_typed_not_found_on_404() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/contacts/missing")
            .match_query(mockito::Matcher::Any)
            .with_status(404)
            .with_header("content-type", "application/json")
            .with_body(r#"{"code":2,"message":"Contact does not exist."}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let err = client.get("/contacts/missing", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "not_found");
        assert!(err.message.contains("Contact does not exist"));
    }

    #[test]
    fn returns_typed_api_error_on_500() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .with_status(500)
            .with_body(r#"{"message":"Internal Server Error","code":99}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "api_error");
    }

    // Zoho 108004 surfaces on categorize/match POSTs when the funding account
    // differs from the transaction's own account (e.g. categorizing a
    // credit-card-account transaction as an expense without paid_through_account_id).
    // parse_json_response is method-agnostic, so a GET fixture exercises the same path.
    #[test]
    fn api_error_108004_attaches_actionable_hint() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .with_status(400)
            .with_body(
                r#"{"code":108004,"message":"Transactions cannot be matched as the account you are trying to match it to, is different."}"#,
            )
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "api_error");
        let hint = err.details.as_ref().unwrap()["hint"]
            .as_str()
            .expect("108004 error should carry a hint string");
        assert!(
            hint.contains("paid_through_account_id"),
            "hint should name the field that fixes it, got: {hint}"
        );
    }

    #[test]
    fn api_error_other_code_has_no_hint() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .with_status(400)
            .with_body(r#"{"code":99,"message":"Some unrelated error."}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "api_error");
        assert!(
            err.details.as_ref().unwrap()["hint"].is_null(),
            "only known codes should carry a hint"
        );
    }

    #[test]
    fn rate_limit_exhausts_retries_with_max_3() {
        let mut server = mockito::Server::new();
        // Always return 429; client should give up after MAX_429_RETRIES attempts.
        let m = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .with_status(429)
            .with_header("retry-after", "0")
            .expect(MAX_429_RETRIES as usize + 1) // initial + 3 retries
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "rate_limited");
        m.assert();
    }

    #[test]
    fn url_builder_handles_path_with_and_without_prefix() {
        let cfg = test_cfg(None);
        let storage = Arc::new(MemoryStorage::new());
        let client = Client::new(cfg, storage, false, OutputFormat::Json).unwrap();
        assert_eq!(
            client.build_url("/contacts"),
            "https://www.zohoapis.com/books/v3/contacts"
        );
        assert_eq!(
            client.build_url("contacts"),
            "https://www.zohoapis.com/books/v3/contacts"
        );
        assert_eq!(
            client.build_url("/books/v3/contacts/123"),
            "https://www.zohoapis.com/books/v3/contacts/123"
        );
    }

    #[test]
    fn missing_org_id_fails_with_validation() {
        let mut cfg = test_cfg(None);
        cfg.org_id = None;
        let storage = Arc::new(MemoryStorage::new());
        let mut client = Client::new(cfg, storage, false, OutputFormat::Json).unwrap();
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "validation");
    }

    #[test]
    fn missing_refresh_token_fails_with_auth_required() {
        let mut cfg = test_cfg(None);
        cfg.refresh_token = None;
        let storage = Arc::new(MemoryStorage::new());
        let mut client = Client::new(cfg, storage, false, OutputFormat::Json).unwrap();
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        assert_eq!(err.code(), "auth_required");
    }

    #[test]
    fn dry_run_short_circuits_before_http_call() {
        // No mock — if the client tried to send, it'd fail with a connection error.
        // Dry-run must short-circuit before any send.
        let cfg = test_cfg(None);
        let storage = Arc::new(MemoryStorage::new());
        let mut client = Client::new(cfg, storage, true, OutputFormat::Json)
            .unwrap()
            .with_api_override("http://127.0.0.1:1"); // unreachable
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        // Dry-run emits preview and signals DryRunOk → exit 0 in main.
        assert!(matches!(err.kind, ErrorKind::DryRunOk));
    }

    #[test]
    fn nineteen_digit_id_in_post_body_preserved_on_wire() {
        // Invariant 11: 19-digit numeric IDs must reach the wire unchanged.
        let body = r#"{"contact_id":9820000005670010000}"#.as_bytes().to_vec();
        let mut server = mockito::Server::new();
        let m = server
            .mock("POST", "/books/v3/expenses")
            .match_query(mockito::Matcher::UrlEncoded(
                "organization_id".into(),
                "123".into(),
            ))
            .match_body(mockito::Matcher::Regex("9820000005670010000".into()))
            .with_status(200)
            .with_body(r#"{"expense":{"expense_id":"e1"}}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let opts = RequestOptions {
            body: Some(body),
            ..RequestOptions::default()
        };
        client.post("/expenses", opts).unwrap();
        m.assert();
    }

    #[test]
    fn twenty_digit_id_in_post_body_preserved_on_wire() {
        // The big-number case: 99999999999999999999 (20 nines) exceeds
        // u64::MAX. Because the body travels as Vec<u8> built from a
        // RawValue's bytes, the digits reach mockito unchanged regardless
        // of serde_json's Number representation.
        let body = r#"{"future_id":99999999999999999999}"#.as_bytes().to_vec();
        let mut server = mockito::Server::new();
        let m = server
            .mock("POST", "/books/v3/expenses")
            .match_query(mockito::Matcher::UrlEncoded(
                "organization_id".into(),
                "123".into(),
            ))
            .match_body(mockito::Matcher::Regex("99999999999999999999".into()))
            .with_status(200)
            .with_body(r#"{"expense":{"expense_id":"e1"}}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let opts = RequestOptions {
            body: Some(body),
            ..RequestOptions::default()
        };
        client.post("/expenses", opts).unwrap();
        m.assert();
    }

    #[test]
    fn custom_headers_forwarded_to_request() {
        let mut server = mockito::Server::new();
        let m = server
            .mock("PUT", "/books/v3/contacts/123")
            .match_query(mockito::Matcher::Any)
            .match_header("x-unique-identifier-key", "cf_invoice_no")
            .match_header("x-unique-identifier-value", "ABC-001")
            .match_header("x-upsert", "true")
            .with_status(200)
            .with_body(r#"{"contact":{"contact_id":"123"}}"#)
            .create();
        let mut client = make_client(test_cfg(None), &server.url());
        let opts = RequestOptions {
            body: Some(br#"{"contact_name":"x"}"#.to_vec()),
            headers: vec![
                ("X-Unique-Identifier-Key".into(), "cf_invoice_no".into()),
                ("X-Unique-Identifier-Value".into(), "ABC-001".into()),
                ("X-Upsert".into(), "true".into()),
            ],
            ..RequestOptions::default()
        };
        client.put("/contacts/123", opts).unwrap();
        m.assert();
    }

    #[test]
    fn refresh_on_401_then_retry_once() {
        // Invariant 9: a 401 silently refreshes the access token (POST to
        // accounts_url/oauth/v2/token) and retries the original request exactly
        // once with the new token. A subsequent 401 must NOT trigger a second
        // refresh.
        let mut server = mockito::Server::new();

        // First call: uses the stale token "at", returns 401.
        let m_first = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .match_header("authorization", "Zoho-oauthtoken at")
            .with_status(401)
            .with_body(r#"{"code":57,"message":"Invalid OAuth Token"}"#)
            .expect(1)
            .create();

        // Refresh exchange: returns a new access token.
        let m_refresh = server
            .mock("POST", "/oauth/v2/token")
            .match_body(mockito::Matcher::Regex("grant_type=refresh_token".into()))
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"access_token":"NEW","expires_in":3600}"#)
            .expect(1)
            .create();

        // Retry: same request, new token, succeeds.
        let m_retry = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .match_header("authorization", "Zoho-oauthtoken NEW")
            .with_status(200)
            .with_body(r#"{"contacts":[{"id":"1"}]}"#)
            .expect(1)
            .create();

        let mut client =
            make_client(test_cfg(None), &server.url()).with_accounts_override(server.url());
        let resp = client.get("/contacts", &Query::new()).unwrap();
        assert!(resp.get("contacts").is_some());

        m_first.assert();
        m_refresh.assert();
        m_retry.assert();

        // Side effect: cfg.access_token was updated to the new value.
        assert_eq!(client.cfg.access_token.as_deref(), Some("NEW"));
    }

    #[test]
    fn second_401_after_refresh_does_not_trigger_second_refresh() {
        // Invariant 9 corollary: the RetryState.refreshed flag prevents an
        // infinite refresh loop when the new token is also rejected.
        let mut server = mockito::Server::new();

        let m_first = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .match_header("authorization", "Zoho-oauthtoken at")
            .with_status(401)
            .with_body(r#"{"code":57,"message":"Invalid OAuth Token"}"#)
            .expect(1)
            .create();
        let m_refresh = server
            .mock("POST", "/oauth/v2/token")
            .with_status(200)
            .with_body(r#"{"access_token":"NEW","expires_in":3600}"#)
            .expect(1)
            .create();
        let m_retry = server
            .mock("GET", "/books/v3/contacts")
            .match_query(mockito::Matcher::Any)
            .match_header("authorization", "Zoho-oauthtoken NEW")
            .with_status(401)
            .with_body(r#"{"code":57,"message":"Still rejected"}"#)
            .expect(1)
            .create();

        let mut client =
            make_client(test_cfg(None), &server.url()).with_accounts_override(server.url());
        let err = client.get("/contacts", &Query::new()).unwrap_err();
        // After the second 401, the client gives up — surfaces as an API error
        // (Zoho returned 401 with code 57; the wrapper sees a non-2xx body).
        assert_eq!(err.code(), "api_error");

        m_first.assert();
        m_refresh.assert(); // refreshed exactly once
        m_retry.assert();
    }
}
