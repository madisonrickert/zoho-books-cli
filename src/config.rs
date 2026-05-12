//! `RuntimeConfig` and the precedence resolution that builds it:
//! CLI flag > env var (`ZOHO_REGION`, `ZOHO_ORG_ID`, `ZOHO_CLIENT_ID`,
//! `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`) > stored credentials >
//! default. Also the helpers commands use to persist tokens
//! (`save_tokens`, `update_access_token`, `save_org`) and the assertion
//! helpers (`require_auth`, `require_org`) that map missing state to the
//! right typed error.

use std::env;

use crate::errors::{Result, ZohoError};
use crate::regions::{self, Region};
use crate::storage::{Credentials, Storage};

#[derive(Debug, Clone)]
pub struct RuntimeConfig {
    pub region: &'static Region,
    pub org_id: Option<String>,
    pub client_id: Option<String>,
    pub client_secret: Option<String>,
    pub refresh_token: Option<String>,
    pub access_token: Option<String>,
    pub expires_at: Option<f64>,
}

#[derive(Debug, Default, Clone)]
pub struct Overrides {
    pub region: Option<String>,
    pub org_id: Option<String>,
}

pub fn load<S: Storage + ?Sized>(storage: &S, overrides: &Overrides) -> Result<RuntimeConfig> {
    let stored = storage.load()?.unwrap_or_default();
    let env = EnvVars::read();
    load_with(&stored, &env, overrides)
}

#[derive(Debug, Default)]
struct EnvVars {
    region: Option<String>,
    org_id: Option<String>,
    client_id: Option<String>,
    client_secret: Option<String>,
    refresh_token: Option<String>,
}

impl EnvVars {
    fn read() -> Self {
        Self {
            region: env::var("ZOHO_REGION").ok(),
            org_id: env::var("ZOHO_ORG_ID").ok(),
            client_id: env::var("ZOHO_CLIENT_ID").ok(),
            client_secret: env::var("ZOHO_CLIENT_SECRET").ok(),
            refresh_token: env::var("ZOHO_REFRESH_TOKEN").ok(),
        }
    }
}

fn load_with(stored: &Credentials, env: &EnvVars, overrides: &Overrides) -> Result<RuntimeConfig> {
    let region_code = first_some([
        overrides.region.clone(),
        env.region.clone(),
        stored.region.clone(),
    ])
    .unwrap_or_else(|| "us".into());

    let region = regions::resolve(&region_code)?;

    Ok(RuntimeConfig {
        region,
        org_id: first_some([
            overrides.org_id.clone(),
            env.org_id.clone(),
            stored.org_id.clone(),
        ]),
        client_id: first_some([env.client_id.clone(), stored.client_id.clone()]),
        client_secret: first_some([env.client_secret.clone(), stored.client_secret.clone()]),
        refresh_token: first_some([env.refresh_token.clone(), stored.refresh_token.clone()]),
        access_token: stored.access_token.clone(),
        expires_at: stored.expires_at,
    })
}

fn first_some<I: IntoIterator<Item = Option<String>>>(items: I) -> Option<String> {
    items.into_iter().flatten().find(|s| !s.is_empty())
}

pub fn require_auth(cfg: &RuntimeConfig) -> Result<()> {
    if cfg.client_id.is_none() || cfg.client_secret.is_none() || cfg.refresh_token.is_none() {
        return Err(ZohoError::auth_required(
            "No credentials found. Run `zb auth login` or set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN.",
        ));
    }
    Ok(())
}

pub fn require_org(cfg: &RuntimeConfig) -> Result<&str> {
    cfg.org_id
        .as_deref()
        .ok_or_else(|| ZohoError::validation(
            "No organization selected. Run `zb org list` then `zb org use <id>`, or set ZOHO_ORG_ID.",
        ))
}

pub fn save_org<S: Storage + ?Sized>(storage: &S, org_id: &str) -> Result<()> {
    let mut creds = storage.load()?.unwrap_or_default();
    creds.org_id = Some(org_id.to_string());
    storage.save(&creds)
}

pub struct SaveTokens<'a> {
    pub client_id: &'a str,
    pub client_secret: &'a str,
    pub access_token: &'a str,
    pub refresh_token: &'a str,
    pub expires_at: f64,
    pub region: &'a str,
}

pub fn save_tokens<S: Storage + ?Sized>(storage: &S, t: SaveTokens<'_>) -> Result<()> {
    let mut creds = storage.load()?.unwrap_or_default();
    creds.client_id = Some(t.client_id.to_string());
    creds.client_secret = Some(t.client_secret.to_string());
    creds.access_token = Some(t.access_token.to_string());
    creds.refresh_token = Some(t.refresh_token.to_string());
    creds.expires_at = Some(t.expires_at);
    creds.region = Some(t.region.to_string());
    storage.save(&creds)
}

pub fn update_access_token<S: Storage + ?Sized>(
    storage: &S,
    access_token: &str,
    expires_at: f64,
) -> Result<()> {
    let mut creds = storage.load()?.unwrap_or_default();
    creds.access_token = Some(access_token.to_string());
    creds.expires_at = Some(expires_at);
    storage.save(&creds)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::MemoryStorage;

    fn stored(region: Option<&str>, org_id: Option<&str>) -> Credentials {
        Credentials {
            region: region.map(str::to_string),
            org_id: org_id.map(str::to_string),
            client_id: Some("stored-cid".into()),
            client_secret: Some("stored-csec".into()),
            refresh_token: Some("stored-rt".into()),
            access_token: Some("stored-at".into()),
            expires_at: Some(123.0),
        }
    }

    fn env(region: Option<&str>, org_id: Option<&str>) -> EnvVars {
        EnvVars {
            region: region.map(str::to_string),
            org_id: org_id.map(str::to_string),
            ..Default::default()
        }
    }

    #[test]
    fn precedence_override_wins() {
        let cfg = load_with(
            &stored(Some("eu"), Some("stored-org")),
            &env(Some("in"), Some("env-org")),
            &Overrides {
                region: Some("au".into()),
                org_id: Some("flag-org".into()),
            },
        )
        .unwrap();
        assert_eq!(cfg.region.code, "au");
        assert_eq!(cfg.org_id.as_deref(), Some("flag-org"));
    }

    #[test]
    fn precedence_env_over_stored() {
        let cfg = load_with(
            &stored(Some("eu"), Some("stored-org")),
            &env(Some("in"), Some("env-org")),
            &Overrides::default(),
        )
        .unwrap();
        assert_eq!(cfg.region.code, "in");
        assert_eq!(cfg.org_id.as_deref(), Some("env-org"));
    }

    #[test]
    fn precedence_stored_when_no_env_or_override() {
        let cfg = load_with(
            &stored(Some("eu"), Some("stored-org")),
            &EnvVars::default(),
            &Overrides::default(),
        )
        .unwrap();
        assert_eq!(cfg.region.code, "eu");
        assert_eq!(cfg.org_id.as_deref(), Some("stored-org"));
    }

    #[test]
    fn default_region_is_us_when_nothing_set() {
        let cfg = load_with(
            &Credentials::default(),
            &EnvVars::default(),
            &Overrides::default(),
        )
        .unwrap();
        assert_eq!(cfg.region.code, "us");
        assert!(cfg.org_id.is_none());
    }

    #[test]
    fn unknown_region_returns_validation_error() {
        let bad = Credentials {
            region: Some("xx".into()),
            ..Credentials::default()
        };
        let err = load_with(&bad, &EnvVars::default(), &Overrides::default()).unwrap_err();
        assert_eq!(err.code(), "validation");
    }

    #[test]
    fn require_auth_passes_when_all_three_present() {
        let cfg = load_with(
            &stored(Some("us"), Some("org")),
            &EnvVars::default(),
            &Overrides::default(),
        )
        .unwrap();
        require_auth(&cfg).unwrap();
    }

    #[test]
    fn require_auth_fails_when_refresh_token_missing() {
        let mut creds = stored(Some("us"), Some("org"));
        creds.refresh_token = None;
        let cfg = load_with(&creds, &EnvVars::default(), &Overrides::default()).unwrap();
        let err = require_auth(&cfg).unwrap_err();
        assert_eq!(err.code(), "auth_required");
    }

    #[test]
    fn require_org_fails_when_org_missing() {
        let cfg = load_with(
            &stored(Some("us"), None),
            &EnvVars::default(),
            &Overrides::default(),
        )
        .unwrap();
        let err = require_org(&cfg).unwrap_err();
        assert_eq!(err.code(), "validation");
    }

    #[test]
    fn save_org_writes_into_storage_preserving_other_fields() {
        let storage = MemoryStorage::with(stored(Some("us"), None));
        save_org(&storage, "new-org-123").unwrap();
        let loaded = storage.load().unwrap().unwrap();
        assert_eq!(loaded.org_id.as_deref(), Some("new-org-123"));
        assert_eq!(loaded.region.as_deref(), Some("us"));
        assert_eq!(loaded.client_id.as_deref(), Some("stored-cid"));
    }

    #[test]
    fn save_tokens_writes_all_seven_fields() {
        let storage = MemoryStorage::new();
        save_tokens(
            &storage,
            SaveTokens {
                client_id: "cid",
                client_secret: "csec",
                access_token: "at",
                refresh_token: "rt",
                expires_at: 999.0,
                region: "us",
            },
        )
        .unwrap();
        let loaded = storage.load().unwrap().unwrap();
        assert_eq!(loaded.client_id.as_deref(), Some("cid"));
        assert_eq!(loaded.client_secret.as_deref(), Some("csec"));
        assert_eq!(loaded.access_token.as_deref(), Some("at"));
        assert_eq!(loaded.refresh_token.as_deref(), Some("rt"));
        assert_eq!(loaded.expires_at, Some(999.0));
        assert_eq!(loaded.region.as_deref(), Some("us"));
    }

    #[test]
    fn update_access_token_preserves_long_lived_creds() {
        let storage = MemoryStorage::with(stored(Some("us"), Some("org")));
        update_access_token(&storage, "new-at", 1000.0).unwrap();
        let loaded = storage.load().unwrap().unwrap();
        assert_eq!(loaded.access_token.as_deref(), Some("new-at"));
        assert_eq!(loaded.expires_at, Some(1000.0));
        assert_eq!(loaded.refresh_token.as_deref(), Some("stored-rt"));
        assert_eq!(loaded.client_id.as_deref(), Some("stored-cid"));
    }
}
