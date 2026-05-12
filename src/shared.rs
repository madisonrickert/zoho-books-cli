//! Body/query parsing + emit helpers used by every domain command.
//!
//! `parse_body` returns `Box<RawValue>` so `--body` bytes (or
//! `@file.json` contents) reach the wire byte-perfect — critical for
//! 19-digit Zoho IDs that exceed `Number.MAX_SAFE_INTEGER`.
//! `parse_query_pairs` merges `--query k=v` flags with an optional
//! `--params <JSON>` object (params wins; null removes; numerics
//! coerce to strings under `arbitrary_precision`).
//!
//! `emit_list` / `emit_object` / `emit_action` strip Zoho's
//! `code`/`message` envelope and emit the CLI's `{ok, data}` shape.
//! `emit_list_paginated` is the pagination driver — single-page by
//! default, NDJSON-streaming under `--page-all` until
//! `page_context.has_more_page` is false or the page-limit is reached.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Write};
use std::path::Path;
use std::thread;
use std::time::Duration;

use serde_json::Value;
use serde_json::value::RawValue;

use crate::cli::OutputFormat;
use crate::errors::{Result, ZohoError};
use crate::output;

pub type Query = BTreeMap<String, String>;

/// Parse the `--body` flag. Returns the raw JSON bytes (validated as JSON) or None.
///
/// Accepts either a literal JSON string or `@path/to/file.json`. Returning a
/// `Box<RawValue>` preserves the original byte sequence — critical for 19-digit
/// Zoho IDs that exceed JavaScript's MAX_SAFE_INTEGER and would corrupt under
/// any code path that round-trips through `serde_json::Value`'s default Number
/// representation.
pub fn parse_body(raw: Option<&str>) -> Result<Option<Box<RawValue>>> {
    let Some(text) = raw.filter(|s| !s.is_empty()) else {
        return Ok(None);
    };
    let json_text = if let Some(path_str) = text.strip_prefix('@') {
        let path = Path::new(path_str);
        if !path.exists() {
            return Err(ZohoError::validation(format!(
                "Body file not found: {}",
                path.display()
            )));
        }
        fs::read_to_string(path).map_err(|e| {
            ZohoError::validation(format!("Failed to read body file {}: {e}", path.display()))
        })?
    } else {
        text.to_owned()
    };
    let parsed: Box<RawValue> = serde_json::from_str(&json_text)
        .map_err(|e| ZohoError::validation(format!("--body is not valid JSON: {e}")))?;
    Ok(Some(parsed))
}

/// Parse repeated `--query key=value` flags plus an optional `--params <JSON>`.
///
/// Merge order: `--query` pairs first, then `--params` JSON on top so an explicit
/// JSON object overrides individual `--query` flags. Values are coerced to
/// strings (Zoho expects query params as strings); booleans become "true"/"false";
/// nulls remove the key.
pub fn parse_query_pairs(pairs: &[String], params_json: Option<&str>) -> Result<Query> {
    let mut result: Query = BTreeMap::new();

    for item in pairs {
        let Some((key, value)) = item.split_once('=') else {
            return Err(ZohoError::validation(format!(
                "--query must be key=value, got: {item}"
            )));
        };
        if key.is_empty() {
            return Err(ZohoError::validation(format!(
                "--query key must be non-empty, got: {item}"
            )));
        }
        result.insert(key.to_string(), value.to_string());
    }

    if let Some(json_text) = params_json {
        let parsed: Value = serde_json::from_str(json_text)
            .map_err(|e| ZohoError::validation(format!("--params is not valid JSON: {e}")))?;
        let Value::Object(map) = parsed else {
            return Err(ZohoError::validation(format!(
                "--params must be a JSON object (got {}).",
                match parsed {
                    Value::Null => "null",
                    Value::Bool(_) => "boolean",
                    Value::Number(_) => "number",
                    Value::String(_) => "string",
                    Value::Array(_) => "array",
                    Value::Object(_) => "object",
                }
            )));
        };
        for (key, value) in map {
            match value {
                Value::Null => {
                    result.remove(&key);
                }
                Value::Bool(b) => {
                    result.insert(key, if b { "true".into() } else { "false".into() });
                }
                Value::String(s) => {
                    result.insert(key, s);
                }
                Value::Number(n) => {
                    result.insert(key, n.to_string());
                }
                Value::Array(_) | Value::Object(_) => {
                    // Serialize compound values; rare but consistent with str().
                    result.insert(key, value.to_string());
                }
            }
        }
    }

    Ok(result)
}

/// Strip Zoho's `code`/`message` envelope from a list response and emit
/// `{items, page_context}`.
pub fn emit_list<W: Write>(
    resp: &Value,
    collection_key: &str,
    format: OutputFormat,
    out: &mut W,
) -> io::Result<()> {
    let (items, page_context) = list_parts(resp, collection_key);
    let data = serde_json::json!({
        "items": items,
        "page_context": page_context,
    });
    output::emit_success(&data, format, out)
}

fn list_parts(resp: &Value, collection_key: &str) -> (Value, Value) {
    let obj = match resp.as_object() {
        Some(obj) => obj,
        None => {
            return (Value::Array(vec![]), Value::Object(serde_json::Map::new()));
        }
    };
    let items = obj
        .get(collection_key)
        .cloned()
        .unwrap_or(Value::Array(vec![]));
    let page_context = obj
        .get("page_context")
        .cloned()
        .unwrap_or(Value::Object(serde_json::Map::new()));
    (items, page_context)
}

/// Strip Zoho's `code`/`message` envelope from a single-object response.
pub fn emit_object<W: Write>(resp: &Value, format: OutputFormat, out: &mut W) -> io::Result<()> {
    let stripped = strip_envelope(resp);
    output::emit_success(&stripped, format, out)
}

fn strip_envelope(resp: &Value) -> Value {
    match resp.as_object() {
        None => serde_json::json!({ "response": resp }),
        Some(obj) => {
            let mut out = serde_json::Map::with_capacity(obj.len());
            for (k, v) in obj {
                if k != "code" && k != "message" {
                    out.insert(k.clone(), v.clone());
                }
            }
            Value::Object(out)
        }
    }
}

/// Emit an action response (no meaningful body) as `{<id_field>, acted, response}`.
pub fn emit_action<W: Write>(
    id_field: &str,
    id_value: &str,
    resp: &Value,
    format: OutputFormat,
    out: &mut W,
) -> io::Result<()> {
    let payload = serde_json::json!({
        id_field: id_value,
        "acted": true,
        "response": resp,
    });
    output::emit_success(&payload, format, out)
}

/// Pagination config bundled to keep `emit_list_paginated`'s arg list short
/// (clippy::too_many_arguments territory otherwise). Only the runtime-varying
/// `fetch`, `query`, and `out` stay positional.
#[derive(Debug, Clone, Copy)]
pub struct PageOpts<'a> {
    pub collection_key: &'a str,
    pub page_all: bool,
    pub page_limit: u32,
    pub page_delay_ms: u64,
    pub format: OutputFormat,
}

/// Pagination driver. Generic over a fetch closure so it doesn't depend on a
/// concrete client type.
///
/// Single-page behavior when `opts.page_all` is false. Otherwise loops
/// page=N..N+limit (where N is `query["page"]` or 1), emits NDJSON, sleeps
/// `opts.page_delay_ms` between requests, stops when
/// `page_context.has_more_page` is false.
pub fn emit_list_paginated<F, W>(
    mut fetch: F,
    mut query: Query,
    opts: &PageOpts<'_>,
    out: &mut W,
) -> Result<()>
where
    F: FnMut(&Query) -> Result<Value>,
    W: Write,
{
    if !opts.page_all {
        let resp = fetch(&query)?;
        emit_list(&resp, opts.collection_key, opts.format, out).map_err(ZohoError::from)?;
        return Ok(());
    }

    let start: u32 = query.get("page").and_then(|s| s.parse().ok()).unwrap_or(1);
    let mut current = start;
    let mut fetched: u32 = 0;
    while fetched < opts.page_limit {
        query.insert("page".into(), current.to_string());
        let resp = fetch(&query)?;
        let (items, page_ctx) = list_parts(&resp, opts.collection_key);
        let line = serde_json::json!({
            "ok": true,
            "data": { "items": items, "page_context": page_ctx },
        });
        output::write_ndjson_line(&line, out).map_err(ZohoError::from)?;
        fetched += 1;
        let has_more = page_ctx
            .as_object()
            .and_then(|o| o.get("has_more_page"))
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        if !has_more {
            break;
        }
        if opts.page_delay_ms > 0 {
            thread::sleep(Duration::from_millis(opts.page_delay_ms));
        }
        current += 1;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::NamedTempFile;

    // --- parse_body -------------------------------------------------------

    #[test]
    fn parse_body_none_when_absent_or_empty() {
        assert!(parse_body(None).unwrap().is_none());
        assert!(parse_body(Some("")).unwrap().is_none());
    }

    #[test]
    fn parse_body_accepts_inline_json() {
        let body = parse_body(Some(r#"{"name":"x"}"#)).unwrap().unwrap();
        assert_eq!(body.get(), r#"{"name":"x"}"#);
    }

    #[test]
    fn parse_body_rejects_invalid_json() {
        let err = parse_body(Some("not json")).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("not valid JSON"));
    }

    #[test]
    fn parse_body_reads_at_file_reference() {
        let mut f = NamedTempFile::new().unwrap();
        writeln!(f, r#"{{"from":"file"}}"#).unwrap();
        let arg = format!("@{}", f.path().display());
        let body = parse_body(Some(&arg)).unwrap().unwrap();
        let parsed: Value = serde_json::from_str(body.get()).unwrap();
        assert_eq!(parsed["from"], "file");
    }

    #[test]
    fn parse_body_at_path_must_exist() {
        let err = parse_body(Some("@/nonexistent/file.json")).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("not found"));
    }

    #[test]
    fn parse_body_preserves_19_digit_id() {
        // Public-contract invariant 11.
        let raw = r#"{"contact_id":9820000005670010000}"#;
        let body = parse_body(Some(raw)).unwrap().unwrap();
        assert!(body.get().contains("9820000005670010000"));
    }

    #[test]
    fn parse_body_preserves_20_digit_numeric() {
        // Beyond u64::MAX. RawValue stores the original bytes, so this works
        // independently of serde_json's arbitrary_precision feature — but
        // confirming it explicitly closes the "what if Zoho ever ships a
        // bigger ID field?" hypothetical.
        let raw = r#"{"future_id":99999999999999999999}"#;
        let body = parse_body(Some(raw)).unwrap().unwrap();
        assert_eq!(body.get(), r#"{"future_id":99999999999999999999}"#);
    }

    #[test]
    fn parse_query_params_preserves_20_digit_numeric() {
        // --params '{"id":99999999999999999999}' must url-encode the literal
        // unchanged. Coercion happens via Number::to_string() which preserves
        // the source bytes under arbitrary_precision.
        let q = parse_query_pairs(&[], Some(r#"{"id":99999999999999999999}"#)).unwrap();
        assert_eq!(q.get("id").unwrap(), "99999999999999999999");
    }

    // --- parse_query_pairs ------------------------------------------------

    #[test]
    fn parse_query_empty() {
        let q = parse_query_pairs(&[], None).unwrap();
        assert!(q.is_empty());
    }

    #[test]
    fn parse_query_single_pair() {
        let q = parse_query_pairs(&["status=active".into()], None).unwrap();
        assert_eq!(q.get("status"), Some(&"active".to_string()));
    }

    #[test]
    fn parse_query_value_with_equals_in_it() {
        let q = parse_query_pairs(&["filter=k=v".into()], None).unwrap();
        assert_eq!(q.get("filter"), Some(&"k=v".to_string()));
    }

    #[test]
    fn parse_query_rejects_missing_equals() {
        let err = parse_query_pairs(&["bad".into()], None).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("key=value"));
    }

    #[test]
    fn parse_query_rejects_empty_key() {
        let err = parse_query_pairs(&["=v".into()], None).unwrap_err();
        assert_eq!(err.code(), "validation");
    }

    #[test]
    fn parse_query_params_overrides_pairs() {
        let q = parse_query_pairs(&["a=1".into(), "b=2".into()], Some(r#"{"a":"99","c":"3"}"#))
            .unwrap();
        assert_eq!(q.get("a"), Some(&"99".to_string()));
        assert_eq!(q.get("b"), Some(&"2".to_string()));
        assert_eq!(q.get("c"), Some(&"3".to_string()));
    }

    #[test]
    fn parse_query_params_coerces_types() {
        let q = parse_query_pairs(&[], Some(r#"{"b":true,"n":42,"s":"hi"}"#)).unwrap();
        assert_eq!(q.get("b"), Some(&"true".to_string()));
        assert_eq!(q.get("n"), Some(&"42".to_string()));
        assert_eq!(q.get("s"), Some(&"hi".to_string()));
    }

    #[test]
    fn parse_query_params_null_removes_key() {
        let q = parse_query_pairs(&["a=1".into()], Some(r#"{"a":null}"#)).unwrap();
        assert!(!q.contains_key("a"));
    }

    #[test]
    fn parse_query_params_must_be_object() {
        let err = parse_query_pairs(&[], Some(r#"[1,2,3]"#)).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("JSON object"));
    }

    #[test]
    fn parse_query_params_rejects_invalid_json() {
        let err = parse_query_pairs(&[], Some("nope")).unwrap_err();
        assert_eq!(err.code(), "validation");
        assert!(err.message.contains("not valid JSON"));
    }

    // --- emit_list / emit_object / emit_action ----------------------------

    fn capture<F: FnOnce(&mut Vec<u8>) -> io::Result<()>>(f: F) -> String {
        let mut buf = Vec::new();
        f(&mut buf).unwrap();
        String::from_utf8(buf).unwrap()
    }

    #[test]
    fn emit_list_strips_envelope() {
        let resp = json!({
            "code": 0,
            "message": "success",
            "contacts": [{"id": "1"}, {"id": "2"}],
            "page_context": {"page": 1, "has_more_page": false},
        });
        let s = capture(|w| {
            emit_list(&resp, "contacts", OutputFormat::Json, w).map_err(io::Error::other)
        });
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["ok"], true);
        assert_eq!(parsed["data"]["items"].as_array().unwrap().len(), 2);
        assert_eq!(parsed["data"]["page_context"]["has_more_page"], false);
        assert!(parsed["data"].get("code").is_none());
        assert!(parsed["data"].get("message").is_none());
    }

    #[test]
    fn emit_list_with_missing_collection_returns_empty() {
        let resp = json!({"code": 0, "message": "no records"});
        let s = capture(|w| {
            emit_list(&resp, "contacts", OutputFormat::Json, w).map_err(io::Error::other)
        });
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["data"]["items"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn emit_object_strips_zoho_envelope_fields() {
        let resp = json!({
            "code": 0,
            "message": "success",
            "contact": {"id": "1", "name": "Alpha"},
        });
        let s = capture(|w| emit_object(&resp, OutputFormat::Json, w).map_err(io::Error::other));
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["ok"], true);
        assert!(parsed["data"].get("code").is_none());
        assert!(parsed["data"].get("message").is_none());
        assert_eq!(parsed["data"]["contact"]["name"], "Alpha");
    }

    #[test]
    fn emit_action_includes_id_and_acted_flag() {
        let resp = json!({"code": 0, "message": "voided"});
        let s = capture(|w| {
            emit_action("invoice_id", "12345", &resp, OutputFormat::Json, w)
                .map_err(io::Error::other)
        });
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["data"]["invoice_id"], "12345");
        assert_eq!(parsed["data"]["acted"], true);
        assert_eq!(parsed["data"]["response"]["message"], "voided");
    }

    // --- emit_list_paginated ---------------------------------------------

    fn page_opts(page_all: bool, page_limit: u32) -> PageOpts<'static> {
        PageOpts {
            collection_key: "contacts",
            page_all,
            page_limit,
            page_delay_ms: 0,
            format: OutputFormat::Json,
        }
    }

    #[test]
    fn paginated_single_page_when_page_all_false() {
        let q = Query::new();
        let mut called = 0;
        let fetch = |_q: &Query| -> Result<Value> {
            called += 1;
            Ok(json!({"contacts": [{"id": "1"}], "page_context": {"has_more_page": false}}))
        };
        let s = capture(|w| {
            emit_list_paginated(fetch, q, &page_opts(false, 10), w).map_err(io::Error::other)
        });
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["data"]["items"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn paginated_loops_until_has_more_false_and_emits_ndjson() {
        let mut call = 0;
        let fetch = |q: &Query| -> Result<Value> {
            call += 1;
            let page: u32 = q.get("page").unwrap().parse().unwrap();
            let has_more = page < 3;
            Ok(json!({
                "contacts": [{"page": page}],
                "page_context": {"page": page, "has_more_page": has_more}
            }))
        };
        let s = capture(|w| {
            emit_list_paginated(fetch, Query::new(), &page_opts(true, 10), w)
                .map_err(io::Error::other)
        });
        let lines: Vec<&str> = s.lines().collect();
        assert_eq!(lines.len(), 3);
        for line in &lines {
            let parsed: Value = serde_json::from_str(line).unwrap();
            assert_eq!(parsed["ok"], true);
        }
    }

    #[test]
    fn paginated_respects_page_limit() {
        let fetch = |q: &Query| -> Result<Value> {
            let page: u32 = q.get("page").unwrap().parse().unwrap();
            Ok(json!({
                "contacts": [{"page": page}],
                "page_context": {"page": page, "has_more_page": true}
            }))
        };
        let s = capture(|w| {
            emit_list_paginated(fetch, Query::new(), &page_opts(true, 2), w)
                .map_err(io::Error::other)
        });
        let lines: Vec<&str> = s.lines().collect();
        assert_eq!(
            lines.len(),
            2,
            "must stop at page_limit even if has_more_page is true"
        );
    }

    #[test]
    fn paginated_starts_from_existing_page_query_param() {
        use std::cell::RefCell;
        use std::rc::Rc;

        let mut q = Query::new();
        q.insert("page".into(), "5".into());
        let seen_pages: Rc<RefCell<Vec<u32>>> = Rc::new(RefCell::new(Vec::new()));
        let seen_clone = Rc::clone(&seen_pages);
        let fetch = move |q: &Query| -> Result<Value> {
            let page: u32 = q.get("page").unwrap().parse().unwrap();
            seen_clone.borrow_mut().push(page);
            let has_more = page < 7;
            Ok(json!({
                "contacts": [{"page": page}],
                "page_context": {"page": page, "has_more_page": has_more}
            }))
        };
        let _ = capture(|w| {
            emit_list_paginated(fetch, q, &page_opts(true, 10), w).map_err(io::Error::other)
        });
        // Sweep started at 5 (from the existing query param) and continued until
        // has_more_page=false at page 7.
        assert_eq!(*seen_pages.borrow(), vec![5, 6, 7]);
    }
}
