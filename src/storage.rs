//! Credential storage: a `Storage` trait with two impls.
//!
//! `RealStorage` is the production backend. It tries the OS keyring first
//! (service `zoho-books-cli`, account `credentials`) and falls back to a
//! JSON file at `<config_dir>/zoho-books-cli/credentials.json` —
//! `~/Library/Application Support/...` on macOS, `~/.config/...` on Linux,
//! `%APPDATA%\...` on Windows. On unix the file is chmod'd `0600`; on
//! Windows it inherits user-private NTFS ACLs from `%APPDATA%`. File
//! writes use `tempfile::NamedTempFile` for atomic temp-then-rename.
//!
//! `MemoryStorage` (gated `#[cfg(test)]`) is the in-process test fixture.
//!
//! The `Credentials` struct mirrors the Python implementation's 7-field
//! JSON schema; all fields are `Option` so partial credentials still
//! deserialize cleanly.

use std::fs;
use std::io::Write;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
#[cfg(test)]
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tempfile::NamedTempFile;

use crate::errors::{Result, ZohoError};

pub const SERVICE: &str = "zoho-books-cli";
pub const ACCOUNT: &str = "credentials";

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Credentials {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub client_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub client_secret: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub refresh_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub access_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub region: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
}

pub trait Storage: Send + Sync {
    fn load(&self) -> Result<Option<Credentials>>;
    fn save(&self, creds: &Credentials) -> Result<()>;
    fn clear(&self) -> Result<()>;
}

pub struct RealStorage {
    file_path: PathBuf,
    keyring_enabled: bool,
}

impl RealStorage {
    pub fn new() -> Self {
        Self {
            file_path: default_file_path(),
            keyring_enabled: true,
        }
    }

    #[cfg(test)]
    pub fn with_file_path(file_path: PathBuf) -> Self {
        Self {
            file_path,
            keyring_enabled: false,
        }
    }
}

impl Default for RealStorage {
    fn default() -> Self {
        Self::new()
    }
}

pub fn default_file_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("zoho-books-cli")
        .join("credentials.json")
}

/// `keyring-core` requires a default credential store be activated before any
/// `Entry` is used. We do this once per process via `std::sync::Once`,
/// selecting the platform-appropriate store at compile time:
///
/// - macOS: `apple-native-keyring-store`'s `keychain` module — stores via the
///   Security framework, the same shape Python's `keyring` library used. This
///   is what makes the drop-in canary work (Rust reads a Python-written entry).
/// - Linux: `zbus-secret-service-keyring-store` — D-Bus Secret Service via
///   pure-Rust zbus (no `libdbus-1` system dep). Same wire protocol Python's
///   `keyring` defaults to on Linux, so credentials cross over without re-auth.
/// - Windows: `windows-native-keyring-store` — Wincred (Credential Manager),
///   the same backend Python's `keyring` defaults to.
/// - Other targets: the keyring path becomes a no-op and the file fallback
///   handles all storage.
fn ensure_keyring_init() {
    use std::sync::Once;
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        #[cfg(target_os = "macos")]
        {
            if let Ok(store) = apple_native_keyring_store::keychain::Store::new() {
                keyring_core::set_default_store(store);
            }
        }
        #[cfg(target_os = "linux")]
        {
            if let Ok(store) = zbus_secret_service_keyring_store::Store::new() {
                keyring_core::set_default_store(store);
            }
        }
        #[cfg(target_os = "windows")]
        {
            if let Ok(store) = windows_native_keyring_store::Store::new() {
                keyring_core::set_default_store(store);
            }
        }
    });
}

fn try_keyring_load() -> Option<String> {
    ensure_keyring_init();
    let entry = keyring_core::Entry::new(SERVICE, ACCOUNT).ok()?;
    entry.get_password().ok()
}

fn try_keyring_save(raw: &str) -> bool {
    ensure_keyring_init();
    let Ok(entry) = keyring_core::Entry::new(SERVICE, ACCOUNT) else {
        return false;
    };
    entry.set_password(raw).is_ok()
}

fn try_keyring_clear() {
    ensure_keyring_init();
    if let Ok(entry) = keyring_core::Entry::new(SERVICE, ACCOUNT) {
        let _ = entry.delete_credential();
    }
}

fn read_file(path: &Path) -> Result<Option<Credentials>> {
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path)?;
    let parsed: Credentials = serde_json::from_str(&raw)?;
    Ok(Some(parsed))
}

fn write_file(path: &Path, creds: &Credentials) -> Result<()> {
    let raw = serde_json::to_string(creds)?;
    let parent = path.parent().ok_or_else(|| {
        ZohoError::validation(format!("credentials path has no parent: {path:?}"))
    })?;
    fs::create_dir_all(parent)?;
    let mut tmp = NamedTempFile::new_in(parent)?;
    tmp.write_all(raw.as_bytes())?;
    tmp.as_file_mut().sync_all()?;
    // Unix: explicit 0600 chmod. Windows: %APPDATA% inherits a user-private
    // NTFS ACL by default, so no extra step needed for an analogous guarantee.
    #[cfg(unix)]
    {
        let perms = fs::Permissions::from_mode(0o600);
        fs::set_permissions(tmp.path(), perms)?;
    }
    tmp.persist(path)
        .map_err(|e| ZohoError::validation(format!("failed to persist credentials file: {e}")))?;
    Ok(())
}

impl Storage for RealStorage {
    fn load(&self) -> Result<Option<Credentials>> {
        if self.keyring_enabled
            && let Some(raw) = try_keyring_load()
            && let Ok(creds) = serde_json::from_str::<Credentials>(&raw)
        {
            return Ok(Some(creds));
        }
        read_file(&self.file_path)
    }

    fn save(&self, creds: &Credentials) -> Result<()> {
        let raw = serde_json::to_string(creds)?;
        if self.keyring_enabled && try_keyring_save(&raw) {
            return Ok(());
        }
        write_file(&self.file_path, creds)
    }

    fn clear(&self) -> Result<()> {
        if self.keyring_enabled {
            try_keyring_clear();
        }
        if self.file_path.exists() {
            fs::remove_file(&self.file_path)?;
        }
        Ok(())
    }
}

#[cfg(test)]
#[derive(Default)]
pub struct MemoryStorage {
    inner: Mutex<Option<Credentials>>,
}

#[cfg(test)]
impl MemoryStorage {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with(creds: Credentials) -> Self {
        Self {
            inner: Mutex::new(Some(creds)),
        }
    }
}

#[cfg(test)]
impl Storage for MemoryStorage {
    fn load(&self) -> Result<Option<Credentials>> {
        Ok(self.inner.lock().unwrap().clone())
    }

    fn save(&self, creds: &Credentials) -> Result<()> {
        *self.inner.lock().unwrap() = Some(creds.clone());
        Ok(())
    }

    fn clear(&self) -> Result<()> {
        *self.inner.lock().unwrap() = None;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn sample_creds() -> Credentials {
        Credentials {
            client_id: Some("cid".into()),
            client_secret: Some("csecret".into()),
            refresh_token: Some("rtoken".into()),
            access_token: Some("atoken".into()),
            expires_at: Some(1_712_345_678.0),
            region: Some("us".into()),
            org_id: Some("123456".into()),
        }
    }

    #[test]
    fn memory_storage_round_trip() {
        let store = MemoryStorage::new();
        assert!(store.load().unwrap().is_none());
        store.save(&sample_creds()).unwrap();
        assert_eq!(store.load().unwrap().unwrap(), sample_creds());
        store.clear().unwrap();
        assert!(store.load().unwrap().is_none());
    }

    #[test]
    fn file_storage_round_trip_and_perms() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("credentials.json");
        let store = RealStorage::with_file_path(path.clone());

        assert!(store.load().unwrap().is_none());
        store.save(&sample_creds()).unwrap();
        assert_eq!(store.load().unwrap().unwrap(), sample_creds());

        // 0600 perms (unix only — Windows inherits a user-private ACL from %APPDATA%).
        #[cfg(unix)]
        {
            let meta = fs::metadata(&path).unwrap();
            let mode = meta.permissions().mode() & 0o777;
            assert_eq!(mode, 0o600, "expected 0600, got {mode:o}");
        }

        store.clear().unwrap();
        assert!(!path.exists());
    }

    #[test]
    fn file_storage_reads_python_written_blob() {
        // Drop-in compatibility canary: the Rust binary must read a file
        // that was written by the Python implementation.
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("credentials.json");
        let python_blob = serde_json::json!({
            "client_id": "cid",
            "client_secret": "csecret",
            "refresh_token": "rtoken",
            "access_token": "atoken",
            "expires_at": 1712345678.0,
            "region": "us",
            "org_id": "999000111000"
        });
        fs::write(&path, serde_json::to_string(&python_blob).unwrap()).unwrap();

        let store = RealStorage::with_file_path(path);
        let loaded = store.load().unwrap().unwrap();
        assert_eq!(loaded.client_id.as_deref(), Some("cid"));
        assert_eq!(loaded.org_id.as_deref(), Some("999000111000"));
        assert_eq!(loaded.region.as_deref(), Some("us"));
    }

    #[test]
    fn missing_optional_fields_load_as_none() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("credentials.json");
        fs::write(&path, r#"{"client_id": "cid", "refresh_token": "rtoken"}"#).unwrap();
        let store = RealStorage::with_file_path(path);
        let loaded = store.load().unwrap().unwrap();
        assert_eq!(loaded.client_id.as_deref(), Some("cid"));
        assert_eq!(loaded.refresh_token.as_deref(), Some("rtoken"));
        assert!(loaded.access_token.is_none());
        assert!(loaded.expires_at.is_none());
        assert!(loaded.org_id.is_none());
    }

    #[test]
    fn empty_credentials_round_trip() {
        let store = MemoryStorage::new();
        let empty = Credentials::default();
        store.save(&empty).unwrap();
        assert_eq!(store.load().unwrap().unwrap(), empty);
    }
}
