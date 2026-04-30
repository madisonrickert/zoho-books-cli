# Synthetic Zoho-shaped fixtures

These fixtures mirror the *shape* of Zoho Books v3 API responses (per the [public API docs](https://www.zoho.com/books/api/v3/)) using **fully fake data**:

- Org name: "Acme Industries"
- Contact / customer / vendor names: "Acme Corp", "Northwind Foods", etc.
- IDs: 19-digit, prefixed with `9999` (real Zoho IDs do not start with `9999` for any production org we've seen — this is a deliberate marker).
- Emails / domains: `example.com` / `example.org`
- Amounts and dates: arbitrary

**Used by:** `bench/measure_static.py` to measure response-payload token cost (component #3) without leaking any real customer data.

**Updating:** if Zoho changes a response shape, update the fixture's *structure* but keep the data fake. Do **not** paste output from a live `zb` or MCP call here.
