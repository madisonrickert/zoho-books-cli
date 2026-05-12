use std::path::Path;

use serde_json::json;

use crate::errors::{Result, ZohoError};

pub const ALLOWED_EXTENSIONS: &[&str] = &["pdf", "jpg", "jpeg", "png", "gif"];
pub const MAX_BYTES: u64 = 10 * 1024 * 1024;

pub fn validate(file: &Path) -> Result<()> {
    let path_str = file.display().to_string();
    let meta = file.metadata().map_err(|_| {
        ZohoError::validation(format!("File not found: {path_str}"))
            .with_details(json!({ "path": path_str }))
    })?;
    if !meta.is_file() {
        return Err(
            ZohoError::validation(format!("Not a regular file: {path_str}"))
                .with_details(json!({ "path": path_str })),
        );
    }
    let ext = file
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    if !ALLOWED_EXTENSIONS.contains(&ext.as_str()) {
        let allowed: Vec<&str> = {
            let mut v: Vec<&str> = ALLOWED_EXTENSIONS.to_vec();
            v.sort_unstable();
            v
        };
        return Err(ZohoError::validation(format!(
            "Unsupported file type '.{ext}'. Allowed: {}",
            allowed
                .iter()
                .map(|e| format!(".{e}"))
                .collect::<Vec<_>>()
                .join(", ")
        ))
        .with_details(json!({ "path": path_str, "extension": format!(".{ext}") })));
    }
    let size = meta.len();
    if size > MAX_BYTES {
        return Err(ZohoError::validation(format!(
            "File too large ({size} bytes). Max: {MAX_BYTES} bytes (10 MB)."
        ))
        .with_details(json!({
            "path": path_str,
            "size_bytes": size,
            "max_bytes": MAX_BYTES,
        })));
    }
    Ok(())
}

pub fn guess_mime(file: &Path) -> &'static str {
    let ext = file
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .unwrap_or_default();
    match ext.as_str() {
        "pdf" => "application/pdf",
        "jpg" | "jpeg" => "image/jpeg",
        "png" => "image/png",
        "gif" => "image/gif",
        _ => "application/octet-stream",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Write;
    use tempfile::TempDir;

    fn write_file(dir: &Path, name: &str, bytes: &[u8]) -> std::path::PathBuf {
        let p = dir.join(name);
        let mut f = fs::File::create(&p).unwrap();
        f.write_all(bytes).unwrap();
        p
    }

    #[test]
    fn accepts_allowed_extensions() {
        let tmp = TempDir::new().unwrap();
        for ext in ALLOWED_EXTENSIONS {
            let p = write_file(tmp.path(), &format!("test.{ext}"), b"x");
            validate(&p).unwrap_or_else(|e| panic!("rejected .{ext}: {}", e.message));
        }
    }

    #[test]
    fn case_insensitive_extension() {
        let tmp = TempDir::new().unwrap();
        let p = write_file(tmp.path(), "test.PDF", b"x");
        validate(&p).unwrap();
        let p = write_file(tmp.path(), "test.JPG", b"x");
        validate(&p).unwrap();
    }

    #[test]
    fn rejects_unknown_extension() {
        let tmp = TempDir::new().unwrap();
        let p = write_file(tmp.path(), "evil.exe", b"x");
        let err = validate(&p).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains(".exe"));
    }

    #[test]
    fn rejects_missing_file() {
        let p = std::path::PathBuf::from("/nonexistent/path/to.pdf");
        let err = validate(&p).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("File not found"));
    }

    #[test]
    fn rejects_oversize_file() {
        let tmp = TempDir::new().unwrap();
        let p = tmp.path().join("big.pdf");
        let f = fs::File::create(&p).unwrap();
        f.set_len(MAX_BYTES + 1).unwrap();
        let err = validate(&p).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("too large"));
    }

    #[test]
    fn rejects_directory() {
        let tmp = TempDir::new().unwrap();
        // Pass the directory itself
        let err = validate(tmp.path()).unwrap_err();
        assert_eq!(err.code(), "validation");
    }

    #[test]
    fn guess_mime_known_types() {
        assert_eq!(guess_mime(Path::new("x.pdf")), "application/pdf");
        assert_eq!(guess_mime(Path::new("x.PNG")), "image/png");
        assert_eq!(guess_mime(Path::new("x.JPEG")), "image/jpeg");
        assert_eq!(guess_mime(Path::new("x.gif")), "image/gif");
    }

    #[test]
    fn guess_mime_unknown_falls_back() {
        assert_eq!(guess_mime(Path::new("x.bin")), "application/octet-stream");
        assert_eq!(guess_mime(Path::new("noext")), "application/octet-stream");
    }
}
