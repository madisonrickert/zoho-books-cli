#![allow(dead_code)] // Plumbing module; consumers are commands::auth_cmd + client.rs.

use std::io::Write as _;
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::{Value, json};

use crate::errors::{Result, ZohoError};
use crate::regions::Region;

pub const REDIRECT_PORT: u16 = 8976;
pub const REDIRECT_URI: &str = "http://localhost:8976/callback";
pub const DEFAULT_SCOPES: &str = "ZohoBooks.fullaccess.all";
pub const HTTP_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Debug, Deserialize)]
pub struct TokenResponse {
    pub access_token: String,
    #[serde(default)]
    pub refresh_token: Option<String>,
    #[serde(default = "default_expires_in")]
    pub expires_in: u64,
}

fn default_expires_in() -> u64 {
    3600
}

/// Run the full authorization-code flow against Zoho. Opens a local HTTP server
/// on REDIRECT_PORT, prints the authorize URL to stderr (and opens it in the
/// browser when `open_browser` is true), waits up to `timeout` for the
/// callback, then exchanges the code for tokens.
pub fn authorize(
    client_id: &str,
    client_secret: &str,
    region: &Region,
    scope: &str,
    open_browser: bool,
    timeout: Duration,
) -> Result<TokenResponse> {
    use rand::distributions::{Alphanumeric, DistString};
    let state = Alphanumeric.sample_string(&mut rand::thread_rng(), 24);

    let server = tiny_http::Server::http(("127.0.0.1", REDIRECT_PORT)).map_err(|e| {
        ZohoError::auth_failed(format!(
            "Failed to bind loopback callback server on port {REDIRECT_PORT}: {e}. \
             Another `zb auth login` may already be running, or the port is in TIME_WAIT — wait ~30s and retry."
        ))
    })?;

    let auth_url = build_authorize_url(region, client_id, scope, &state);
    let mut stderr = std::io::stderr().lock();
    let _ = writeln!(stderr, "Open this URL to authorize:\n  {auth_url}\n");
    if open_browser {
        let _ = open_in_browser(&auth_url);
    }

    let captured = await_callback(&server, &state, timeout)?;

    let code = captured.get("code").cloned().ok_or_else(|| {
        ZohoError::auth_failed("OAuth callback returned no authorization code.")
            .with_details(json!({ "params": captured }))
    })?;

    exchange_code(&code, client_id, client_secret, region)
}

fn open_in_browser(url: &str) -> std::io::Result<()> {
    std::process::Command::new("open")
        .arg(url)
        .status()
        .map(|_| ())
}

#[derive(Debug, Default)]
struct CapturedParams(std::collections::BTreeMap<String, String>);

impl CapturedParams {
    fn get(&self, key: &str) -> Option<&String> {
        self.0.get(key)
    }
    fn as_json(&self) -> Value {
        let mut obj = serde_json::Map::new();
        for (k, v) in &self.0 {
            obj.insert(k.clone(), Value::String(v.clone()));
        }
        Value::Object(obj)
    }
}

impl serde::Serialize for CapturedParams {
    fn serialize<S: serde::Serializer>(&self, ser: S) -> std::result::Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = ser.serialize_map(Some(self.0.len()))?;
        for (k, v) in &self.0 {
            m.serialize_entry(k, v)?;
        }
        m.end()
    }
}

fn await_callback(
    server: &tiny_http::Server,
    expected_state: &str,
    timeout: Duration,
) -> Result<CapturedParams> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        let remaining = deadline.saturating_duration_since(Instant::now());
        let poll = remaining.min(Duration::from_millis(200));
        match server.recv_timeout(poll) {
            Ok(Some(request)) => {
                let url = request.url().to_string();
                let (path, query) = split_url(&url);
                if path != "/callback" {
                    respond(request, 404, "Not found.");
                    continue;
                }
                let params = parse_query_string(query);
                let state_match = params
                    .get("state")
                    .map(|s| s == expected_state)
                    .unwrap_or(false);
                if !state_match {
                    respond(
                        request,
                        400,
                        "Invalid state. Close this tab and retry `zb auth login`.",
                    );
                    return Err(ZohoError::auth_failed(
                        "OAuth callback returned an invalid state — possible cross-site request forgery, or stale callback from a previous attempt.",
                    ));
                }
                if let Some(err) = params.get("error") {
                    let err_clone = err.clone();
                    respond(request, 400, &format!("Authorization failed: {err_clone}"));
                    return Err(ZohoError::auth_failed(format!(
                        "Authorization denied by Zoho: {err_clone}"
                    )));
                }
                respond(
                    request,
                    200,
                    "Authorization complete. You can close this tab and return to the terminal.",
                );
                return Ok(CapturedParams(params));
            }
            Ok(None) => continue,
            Err(e) => {
                return Err(ZohoError::auth_failed(format!(
                    "Callback server error: {e}"
                )));
            }
        }
    }
    Err(
        ZohoError::auth_failed("Timed out waiting for OAuth callback.")
            .with_details(json!({ "timeout_s": timeout.as_secs() })),
    )
}

fn respond(request: tiny_http::Request, status: u16, body: &str) {
    let resp = tiny_http::Response::from_string(body.to_owned())
        .with_status_code(status)
        .with_header(
            tiny_http::Header::from_bytes(&b"Content-Type"[..], &b"text/plain; charset=utf-8"[..])
                .expect("valid header"),
        );
    let _ = request.respond(resp);
}

fn split_url(url: &str) -> (&str, &str) {
    match url.split_once('?') {
        Some((path, query)) => (path, query),
        None => (url, ""),
    }
}

pub(crate) fn parse_query_string(query: &str) -> std::collections::BTreeMap<String, String> {
    let mut out = std::collections::BTreeMap::new();
    for pair in query.split('&').filter(|s| !s.is_empty()) {
        let (k, v) = match pair.split_once('=') {
            Some((k, v)) => (k, v),
            None => (pair, ""),
        };
        out.insert(url_decode(k), url_decode(v));
    }
    out
}

fn url_decode(s: &str) -> String {
    // Minimal URL decode: % escapes + '+' → ' '. Adequate for OAuth callback params.
    let mut out = String::with_capacity(s.len());
    let mut bytes = s.bytes().peekable();
    while let Some(b) = bytes.next() {
        match b {
            b'+' => out.push(' '),
            b'%' => {
                let hi = bytes.next();
                let lo = bytes.next();
                if let (Some(h), Some(l)) = (hi, lo)
                    && let (Some(hv), Some(lv)) = (hex_digit(h), hex_digit(l))
                {
                    out.push((hv * 16 + lv) as char);
                } else {
                    out.push('%');
                    if let Some(h) = hi {
                        out.push(h as char);
                    }
                    if let Some(l) = lo {
                        out.push(l as char);
                    }
                }
            }
            _ => out.push(b as char),
        }
    }
    out
}

fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

pub(crate) fn build_authorize_url(
    region: &Region,
    client_id: &str,
    scope: &str,
    state: &str,
) -> String {
    let params = [
        ("scope", scope),
        ("client_id", client_id),
        ("response_type", "code"),
        ("redirect_uri", REDIRECT_URI),
        ("access_type", "offline"),
        ("prompt", "consent"),
        ("state", state),
    ];
    let encoded = params
        .iter()
        .map(|(k, v)| format!("{}={}", url_encode(k), url_encode(v)))
        .collect::<Vec<_>>()
        .join("&");
    format!("{}/oauth/v2/auth?{}", region.accounts_url, encoded)
}

fn url_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char);
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Exchange an authorization code for tokens. Uses the configured region's
/// accounts URL.
pub fn exchange_code(
    code: &str,
    client_id: &str,
    client_secret: &str,
    region: &Region,
) -> Result<TokenResponse> {
    let url = format!("{}/oauth/v2/token", region.accounts_url);
    let form = [
        ("code", code),
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("redirect_uri", REDIRECT_URI),
        ("grant_type", "authorization_code"),
    ];
    post_token_form(&url, &form, "exchange")
}

/// Refresh an access token. Maps refresh failures to AuthExpired so the
/// operator gets a clear "re-run zb auth login" message.
pub fn refresh_access_token(
    client_id: &str,
    client_secret: &str,
    refresh_token: &str,
    region: &Region,
) -> Result<TokenResponse> {
    let url = format!("{}/oauth/v2/token", region.accounts_url);
    let form = [
        ("refresh_token", refresh_token),
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("grant_type", "refresh_token"),
    ];
    post_token_form(&url, &form, "refresh")
}

fn post_token_form(url: &str, form: &[(&str, &str)], op: &str) -> Result<TokenResponse> {
    let client = reqwest::blocking::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .map_err(|e| ZohoError::network(format!("HTTP client init failed: {e}")))?;
    let resp = client
        .post(url)
        .form(form)
        .send()
        .map_err(|e| ZohoError::network(format!("Network error during token {op}: {e}")))?;
    let status = resp.status();
    let body_text = resp
        .text()
        .map_err(|e| ZohoError::network(format!("Failed to read token {op} response: {e}")))?;
    let body_json: Value =
        serde_json::from_str(&body_text).unwrap_or(Value::String(body_text.clone()));
    if !status.is_success() {
        let kind_err = if op == "refresh" {
            ZohoError::auth_expired("Token refresh failed. Re-run `zb auth login`.")
        } else {
            ZohoError::auth_failed("Token exchange failed.")
        };
        return Err(kind_err.with_details(json!({
            "http_status": status.as_u16(),
            "body": body_json,
        })));
    }
    if let Some(err) = body_json.get("error").and_then(|v| v.as_str()) {
        let kind_err = if op == "refresh" {
            ZohoError::auth_expired(format!("Token refresh rejected: {err}"))
        } else {
            ZohoError::auth_failed(format!("Token exchange rejected: {err}"))
        };
        return Err(kind_err.with_details(json!({ "body": body_json })));
    }
    let token: TokenResponse = serde_json::from_value(body_json.clone()).map_err(|e| {
        ZohoError::auth_failed(format!("Unparseable token {op} response: {e}"))
            .with_details(json!({ "body": body_json }))
    })?;
    Ok(token)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::regions;

    #[test]
    fn authorize_url_has_all_expected_params() {
        let region = regions::resolve("us").unwrap();
        let url = build_authorize_url(
            region,
            "abc-client",
            "ZohoBooks.fullaccess.all",
            "rnd-state",
        );
        assert!(url.starts_with("https://accounts.zoho.com/oauth/v2/auth?"));
        assert!(url.contains("client_id=abc-client"));
        assert!(url.contains("response_type=code"));
        assert!(url.contains("redirect_uri=http%3A%2F%2Flocalhost%3A8976%2Fcallback"));
        assert!(url.contains("access_type=offline"));
        assert!(url.contains("prompt=consent"));
        assert!(url.contains("state=rnd-state"));
        assert!(url.contains("scope=ZohoBooks.fullaccess.all"));
    }

    #[test]
    fn authorize_url_region_eu() {
        let region = regions::resolve("eu").unwrap();
        let url = build_authorize_url(region, "cid", "scope", "s");
        assert!(url.starts_with("https://accounts.zoho.eu/oauth/v2/auth?"));
    }

    #[test]
    fn parse_query_string_basic() {
        let params = parse_query_string("code=ABC&state=xyz");
        assert_eq!(params.get("code"), Some(&"ABC".to_string()));
        assert_eq!(params.get("state"), Some(&"xyz".to_string()));
    }

    #[test]
    fn parse_query_string_decodes_percent_escapes() {
        let params = parse_query_string("error=access%20denied&state=a%2Bb");
        assert_eq!(params.get("error"), Some(&"access denied".to_string()));
        assert_eq!(params.get("state"), Some(&"a+b".to_string()));
    }

    #[test]
    fn parse_query_string_handles_plus() {
        let params = parse_query_string("k=v+w");
        assert_eq!(params.get("k"), Some(&"v w".to_string()));
    }

    #[test]
    fn parse_query_string_handles_empty_value() {
        let params = parse_query_string("k=");
        assert_eq!(params.get("k"), Some(&"".to_string()));
    }

    #[test]
    fn url_encode_round_trips_redirect_uri() {
        let encoded = url_encode("http://localhost:8976/callback");
        assert_eq!(encoded, "http%3A%2F%2Flocalhost%3A8976%2Fcallback");
    }

    #[test]
    fn token_response_deserializes_with_defaults() {
        let body: TokenResponse =
            serde_json::from_str(r#"{"access_token":"AT","refresh_token":"RT","expires_in":3600}"#)
                .unwrap();
        assert_eq!(body.access_token, "AT");
        assert_eq!(body.refresh_token.as_deref(), Some("RT"));
        assert_eq!(body.expires_in, 3600);
    }

    #[test]
    fn token_response_defaults_expires_in_when_missing() {
        let body: TokenResponse =
            serde_json::from_str(r#"{"access_token":"AT","refresh_token":"RT"}"#).unwrap();
        assert_eq!(body.expires_in, 3600);
    }

    #[test]
    fn refresh_succeeds_against_mock() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("POST", "/oauth/v2/token")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"access_token":"new-at","expires_in":3600}"#)
            .match_body(mockito::Matcher::AllOf(vec![
                mockito::Matcher::Regex("refresh_token=rt".into()),
                mockito::Matcher::Regex("grant_type=refresh_token".into()),
                mockito::Matcher::Regex("client_id=cid".into()),
            ]))
            .create();

        let url = format!("{}/oauth/v2/token", server.url());
        let form = [
            ("refresh_token", "rt"),
            ("client_id", "cid"),
            ("client_secret", "csec"),
            ("grant_type", "refresh_token"),
        ];
        let tok = post_token_form(&url, &form, "refresh").unwrap();
        assert_eq!(tok.access_token, "new-at");
        assert_eq!(tok.expires_in, 3600);
    }

    #[test]
    fn refresh_failure_maps_to_auth_expired() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("POST", "/oauth/v2/token")
            .with_status(400)
            .with_header("content-type", "application/json")
            .with_body(r#"{"error":"invalid_grant"}"#)
            .create();

        let url = format!("{}/oauth/v2/token", server.url());
        let form = [
            ("refresh_token", "rt"),
            ("client_id", "cid"),
            ("client_secret", "csec"),
            ("grant_type", "refresh_token"),
        ];
        let err = post_token_form(&url, &form, "refresh").unwrap_err();
        assert_eq!(err.code(), "auth_expired");
    }

    #[test]
    fn exchange_failure_maps_to_auth_failed() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("POST", "/oauth/v2/token")
            .with_status(400)
            .with_header("content-type", "application/json")
            .with_body(r#"{"error":"invalid_code"}"#)
            .create();

        let url = format!("{}/oauth/v2/token", server.url());
        let form = [
            ("code", "abc"),
            ("client_id", "cid"),
            ("client_secret", "csec"),
            ("redirect_uri", REDIRECT_URI),
            ("grant_type", "authorization_code"),
        ];
        let err = post_token_form(&url, &form, "exchange").unwrap_err();
        assert_eq!(err.code(), "auth_failed");
    }

    #[test]
    fn refresh_error_in_200_body_still_maps_to_auth_expired() {
        let mut server = mockito::Server::new();
        let _m = server
            .mock("POST", "/oauth/v2/token")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(r#"{"error":"invalid_grant"}"#)
            .create();

        let url = format!("{}/oauth/v2/token", server.url());
        let form = [("refresh_token", "rt")];
        let err = post_token_form(&url, &form, "refresh").unwrap_err();
        assert_eq!(err.code(), "auth_expired");
    }
}
