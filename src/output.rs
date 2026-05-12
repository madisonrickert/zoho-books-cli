#![allow(dead_code)] // Plumbing module; consumers are commands + shared.rs.

use std::io::{self, Write};

use serde_json::{Value, json};

use crate::cli::OutputFormat;

pub fn emit_success<W: Write>(data: &Value, format: OutputFormat, out: &mut W) -> io::Result<()> {
    let payload = json!({ "ok": true, "data": data });
    emit(&payload, format, out)
}

pub fn emit_error<W: Write>(payload: &Value, format: OutputFormat, err: &mut W) -> io::Result<()> {
    emit(payload, format, err)
}

pub fn emit<W: Write>(payload: &Value, format: OutputFormat, out: &mut W) -> io::Result<()> {
    match format {
        OutputFormat::Json => write_json(payload, out),
        OutputFormat::Yaml => write_yaml(payload, out),
        OutputFormat::Table => write_table(payload, out),
        OutputFormat::Csv => write_csv(payload, out),
    }?;
    out.flush()
}

fn write_json<W: Write>(payload: &Value, out: &mut W) -> io::Result<()> {
    serde_json::to_writer(&mut *out, payload).map_err(io::Error::other)?;
    out.write_all(b"\n")
}

/// NDJSON: one JSON object per line, `\n` terminated, flushed after each line.
/// Used by emit_list_paginated under `--page-all`.
pub fn write_ndjson_line<W: Write>(value: &Value, out: &mut W) -> io::Result<()> {
    serde_json::to_writer(&mut *out, value).map_err(io::Error::other)?;
    out.write_all(b"\n")?;
    out.flush()
}

fn write_yaml<W: Write>(payload: &Value, out: &mut W) -> io::Result<()> {
    let yaml = serde_yml::to_string(payload).map_err(io::Error::other)?;
    out.write_all(yaml.as_bytes())
}

/// Python's table format depends on `rich`; when absent it falls back to
/// pretty-printed indented JSON. The Rust port uses the fallback unconditionally
/// (matches documented Python behavior with no extra dep).
fn write_table<W: Write>(payload: &Value, out: &mut W) -> io::Result<()> {
    serde_json::to_writer_pretty(&mut *out, payload).map_err(io::Error::other)?;
    out.write_all(b"\n")
}

fn write_csv<W: Write>(payload: &Value, out: &mut W) -> io::Result<()> {
    let Some(items) = extract_csv_items(payload) else {
        eprintln!(
            "zb: --format csv only applies to list responses (data.items[]); falling back to json."
        );
        return write_json(payload, out);
    };

    if items.is_empty() {
        return Ok(());
    }

    // Build the column key order from first-seen positions across all items.
    let mut keys: Vec<String> = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for item in items {
        if let Some(obj) = item.as_object() {
            for k in obj.keys() {
                if seen.insert(k.clone()) {
                    keys.push(k.clone());
                }
            }
        }
    }

    let mut wtr = csv::Writer::from_writer(vec![]);
    wtr.write_record(&keys).map_err(io::Error::other)?;
    for item in items {
        if let Some(obj) = item.as_object() {
            let row: Vec<String> = keys
                .iter()
                .map(|k| csv_cell(obj.get(k).unwrap_or(&Value::Null)))
                .collect();
            wtr.write_record(&row).map_err(io::Error::other)?;
        }
    }
    let data = wtr.into_inner().map_err(io::Error::other)?;
    out.write_all(&data)
}

fn extract_csv_items(payload: &Value) -> Option<&Vec<Value>> {
    if !payload.get("ok")?.as_bool()? {
        return None;
    }
    payload.get("data")?.get("items")?.as_array()
}

fn csv_cell(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(s) => s.clone(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::Object(_) | Value::Array(_) => value.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn capture<F: FnOnce(&mut Vec<u8>) -> io::Result<()>>(f: F) -> String {
        let mut buf = Vec::new();
        f(&mut buf).unwrap();
        String::from_utf8(buf).unwrap()
    }

    #[test]
    fn json_success_envelope_shape() {
        let s = capture(|w| emit_success(&json!({"id": "123"}), OutputFormat::Json, w));
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["ok"], true);
        assert_eq!(parsed["data"]["id"], "123");
        assert!(
            s.ends_with('\n'),
            "must be newline-terminated for NDJSON-compat"
        );
    }

    #[test]
    fn json_error_envelope_shape() {
        let payload = json!({"ok": false, "error": {"code": "validation", "message": "bad"}});
        let s = capture(|w| emit_error(&payload, OutputFormat::Json, w));
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["ok"], false);
        assert_eq!(parsed["error"]["code"], "validation");
    }

    #[test]
    fn yaml_format_produces_yaml() {
        let s = capture(|w| emit_success(&json!({"k": "v"}), OutputFormat::Yaml, w));
        assert!(s.contains("ok: true"));
        assert!(s.contains("data:"));
        assert!(s.contains("k: v"));
    }

    #[test]
    fn table_format_is_pretty_json() {
        let s = capture(|w| emit_success(&json!({"k": "v"}), OutputFormat::Table, w));
        // Pretty JSON has 2-space indent
        assert!(s.contains("\n  \"ok\""));
        assert!(s.contains("\n  \"data\""));
    }

    #[test]
    fn csv_format_emits_rows_from_data_items() {
        let payload = json!({
            "ok": true,
            "data": {
                "items": [
                    {"id": "1", "name": "Alpha"},
                    {"id": "2", "name": "Beta"}
                ]
            }
        });
        let s = capture(|w| emit(&payload, OutputFormat::Csv, w));
        assert!(s.starts_with("id,name\n"));
        assert!(s.contains("1,Alpha"));
        assert!(s.contains("2,Beta"));
    }

    #[test]
    fn csv_format_falls_back_to_json_for_non_list_payload() {
        let payload = json!({"ok": true, "data": {"id": "1"}});
        let s = capture(|w| emit(&payload, OutputFormat::Csv, w));
        let parsed: Value = serde_json::from_str(s.trim_end()).unwrap();
        assert_eq!(parsed["ok"], true);
        assert_eq!(parsed["data"]["id"], "1");
    }

    #[test]
    fn csv_format_empty_list_produces_no_output() {
        let payload = json!({"ok": true, "data": {"items": []}});
        let s = capture(|w| emit(&payload, OutputFormat::Csv, w));
        assert_eq!(s, "");
    }

    #[test]
    fn csv_format_unions_keys_across_items() {
        let payload = json!({
            "ok": true,
            "data": {
                "items": [
                    {"id": "1", "name": "Alpha"},
                    {"id": "2", "extra": "x"}
                ]
            }
        });
        let s = capture(|w| emit(&payload, OutputFormat::Csv, w));
        let first_line = s.lines().next().unwrap();
        assert!(first_line.contains("id"));
        assert!(first_line.contains("name"));
        assert!(first_line.contains("extra"));
    }

    #[test]
    fn ndjson_streams_one_object_per_line() {
        let mut buf = Vec::new();
        write_ndjson_line(&json!({"page": 1}), &mut buf).unwrap();
        write_ndjson_line(&json!({"page": 2}), &mut buf).unwrap();
        write_ndjson_line(&json!({"page": 3}), &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        let lines: Vec<&str> = s.lines().collect();
        assert_eq!(lines.len(), 3);
        for (i, line) in lines.iter().enumerate() {
            let parsed: Value = serde_json::from_str(line).unwrap();
            assert_eq!(parsed["page"], (i + 1) as i64);
        }
    }

    #[test]
    fn ndjson_each_line_ends_in_newline() {
        let mut buf = Vec::new();
        write_ndjson_line(&json!({"x": 1}), &mut buf).unwrap();
        assert_eq!(buf.last(), Some(&b'\n'));
    }

    #[test]
    fn ndjson_no_trailing_whitespace_within_object() {
        let mut buf = Vec::new();
        write_ndjson_line(&json!({"x": 1}), &mut buf).unwrap();
        let s = String::from_utf8(buf).unwrap();
        // serde_json compact output: no spaces between commas/colons
        assert_eq!(s.trim_end(), r#"{"x":1}"#);
    }

    #[test]
    fn nineteen_digit_id_round_trip_via_emit() {
        // Public-contract invariant 11: 19-digit IDs preserved bit-perfect.
        // serde_json with arbitrary_precision OFF would corrupt this number.
        // arbitrary_precision is enabled in Cargo.toml; verify the assumption.
        let raw = r#"{"contact_id":9820000005670010000}"#;
        let parsed: Value = serde_json::from_str(raw).unwrap();
        let s = capture(|w| emit_success(&parsed, OutputFormat::Json, w));
        assert!(
            s.contains("9820000005670010000"),
            "expected exact 19-digit ID in output, got: {s}"
        );
    }
}
