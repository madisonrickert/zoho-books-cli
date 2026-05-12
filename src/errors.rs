#![allow(dead_code)] // Plumbing module; full consumer set lands with auth.rs + client.rs.

use serde_json::{Value, json};
use thiserror::Error;

pub const EXIT_SUCCESS: i32 = 0;
pub const EXIT_UNKNOWN: i32 = 1;
pub const EXIT_AUTH: i32 = 2;
pub const EXIT_VALIDATION: i32 = 3;
pub const EXIT_API: i32 = 4;
pub const EXIT_RATE_LIMIT: i32 = 5;
pub const EXIT_NETWORK: i32 = 6;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    AuthRequired,
    AuthExpired,
    AuthFailed,
    Validation,
    NotFound,
    Api,
    RateLimited,
    Network,
    Unknown,
    /// Sentinel: a `--dry-run` preview has been emitted on stdout. The dispatch
    /// layer in `main` treats this as success (exit 0) and suppresses error
    /// envelope emission.
    DryRunOk,
}

impl ErrorKind {
    pub fn code(self) -> &'static str {
        match self {
            Self::AuthRequired => "auth_required",
            Self::AuthExpired => "auth_expired",
            Self::AuthFailed => "auth_failed",
            Self::Validation => "validation",
            Self::NotFound => "not_found",
            Self::Api => "api_error",
            Self::RateLimited => "rate_limited",
            Self::Network => "network",
            Self::Unknown => "unknown",
            Self::DryRunOk => "dry_run_ok",
        }
    }

    pub fn exit_code(self) -> i32 {
        match self {
            Self::AuthRequired | Self::AuthExpired | Self::AuthFailed => EXIT_AUTH,
            Self::Validation => EXIT_VALIDATION,
            Self::NotFound | Self::Api => EXIT_API,
            Self::RateLimited => EXIT_RATE_LIMIT,
            Self::Network => EXIT_NETWORK,
            Self::Unknown => EXIT_UNKNOWN,
            Self::DryRunOk => EXIT_SUCCESS,
        }
    }
}

#[derive(Debug, Error)]
#[error("{message}")]
pub struct ZohoError {
    pub kind: ErrorKind,
    pub message: String,
    pub details: Option<Value>,
}

impl ZohoError {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            details: None,
        }
    }

    pub fn with_details(mut self, details: Value) -> Self {
        self.details = Some(details);
        self
    }

    pub fn code(&self) -> &'static str {
        self.kind.code()
    }

    pub fn exit_code(&self) -> i32 {
        self.kind.exit_code()
    }

    pub fn to_envelope(&self) -> Value {
        json!({
            "ok": false,
            "error": {
                "code": self.code(),
                "message": self.message,
                "details": self.details.clone().unwrap_or_else(|| json!({})),
            }
        })
    }

    pub fn auth_required(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::AuthRequired, msg)
    }
    pub fn auth_expired(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::AuthExpired, msg)
    }
    pub fn auth_failed(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::AuthFailed, msg)
    }
    pub fn validation(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Validation, msg)
    }
    pub fn not_found(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::NotFound, msg)
    }
    pub fn api(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Api, msg)
    }
    pub fn rate_limited(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::RateLimited, msg)
    }
    pub fn network(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Network, msg)
    }
}

pub type Result<T> = std::result::Result<T, ZohoError>;

impl From<std::io::Error> for ZohoError {
    fn from(e: std::io::Error) -> Self {
        Self::validation(format!("io error: {e}"))
    }
}

impl From<serde_json::Error> for ZohoError {
    fn from(e: serde_json::Error) -> Self {
        Self::validation(format!("invalid JSON: {e}"))
    }
}

impl From<reqwest::Error> for ZohoError {
    fn from(e: reqwest::Error) -> Self {
        let msg = e.to_string();
        if e.is_timeout() || e.is_connect() {
            Self::network(msg)
        } else if e.is_decode() {
            Self::api(format!("invalid response: {msg}"))
        } else {
            Self::network(msg)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_codes_match_python_table() {
        assert_eq!(ErrorKind::AuthRequired.exit_code(), 2);
        assert_eq!(ErrorKind::AuthExpired.exit_code(), 2);
        assert_eq!(ErrorKind::AuthFailed.exit_code(), 2);
        assert_eq!(ErrorKind::Validation.exit_code(), 3);
        assert_eq!(ErrorKind::NotFound.exit_code(), 4);
        assert_eq!(ErrorKind::Api.exit_code(), 4);
        assert_eq!(ErrorKind::RateLimited.exit_code(), 5);
        assert_eq!(ErrorKind::Network.exit_code(), 6);
        assert_eq!(ErrorKind::Unknown.exit_code(), 1);
    }

    #[test]
    fn codes_match_python_strings() {
        assert_eq!(ErrorKind::AuthRequired.code(), "auth_required");
        assert_eq!(ErrorKind::AuthExpired.code(), "auth_expired");
        assert_eq!(ErrorKind::AuthFailed.code(), "auth_failed");
        assert_eq!(ErrorKind::Validation.code(), "validation");
        assert_eq!(ErrorKind::NotFound.code(), "not_found");
        assert_eq!(ErrorKind::Api.code(), "api_error");
        assert_eq!(ErrorKind::RateLimited.code(), "rate_limited");
        assert_eq!(ErrorKind::Network.code(), "network");
    }

    #[test]
    fn envelope_shape_matches_contract() {
        let err = ZohoError::validation("bad input").with_details(json!({"field": "name"}));
        let envelope = err.to_envelope();
        assert_eq!(envelope["ok"], false);
        assert_eq!(envelope["error"]["code"], "validation");
        assert_eq!(envelope["error"]["message"], "bad input");
        assert_eq!(envelope["error"]["details"]["field"], "name");
    }

    #[test]
    fn envelope_defaults_details_to_empty_object() {
        let err = ZohoError::auth_required("no creds");
        let envelope = err.to_envelope();
        assert!(envelope["error"]["details"].is_object());
        assert_eq!(envelope["error"]["details"].as_object().unwrap().len(), 0);
    }
}
