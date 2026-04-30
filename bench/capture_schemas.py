"""Snapshot the Zoho Books MCP server's tool schemas to a fixture file.

Connects to the Zoho MCP HTTP endpoint, calls ``list_tools``, and writes the
resulting schemas to ``bench/fixtures/zoho_mcp_schemas.json``. **Schemas only
— no per-user URL, no auth token, no live response data.** The fixture is
safe to commit.

Usage:

    # The URL is per-user (contains an OAuth token), so we read it from env.
    # If you have it configured in Claude Code, you can lift it via
    # `claude mcp get '<your Zoho MCP server name>'`.
    export ZOHO_MCP_URL='https://<host>.zohomcp.com/mcp/<token>/message'
    uv run bench/capture_schemas.py

The output is consumed by ``bench/measure_static.py`` to count tool-catalog
tokens against ``count_tokens``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

OUT = Path(__file__).parent / "fixtures" / "zoho_mcp_schemas.json"


async def _list_via(client_ctx) -> dict:
    """Run list_tools() against a connected client context."""
    async with client_ctx as conn:
        # Both streamable_http and sse return (read, write[, ...]); accept any.
        read, write, *_ = conn
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return {
                "captured_at": datetime.now(UTC).isoformat(),
                "captured_unix": int(time.time()),
                "tool_count": len(tools.tools),
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema,
                    }
                    for t in tools.tools
                ],
            }


def _looks_like_wrong_transport(exc: BaseException) -> bool:
    """Check `exc` (and any nested ExceptionGroup leaves) for HTTP 401/404/405."""
    needles = ("401", "404", "405")
    stack: list[BaseException] = [exc]
    while stack:
        e = stack.pop()
        if any(code in str(e) for code in needles):
            return True
        sub = getattr(e, "exceptions", None)
        if sub:
            stack.extend(sub)
    return False


async def _capture(url: str) -> dict:
    """Try streamable HTTP first; fall back to SSE on 401 / 404 / 405."""
    try:
        return await _list_via(streamablehttp_client(url))
    except BaseException as e:
        # Zoho's MCP URL path ends in `/message`, which is an SSE
        # convention. Streamable HTTP rejects an SSE endpoint with
        # 401/404/405. Anything else is a real error and bubbles up.
        if not _looks_like_wrong_transport(e):
            raise
        print(
            "streamable HTTP rejected (looks like SSE endpoint); retrying via SSE…",
            file=sys.stderr,
        )
        return await _list_via(sse_client(url))


def main() -> int:
    url = os.environ.get("ZOHO_MCP_URL")
    if not url:
        print(
            "error: set ZOHO_MCP_URL to the Zoho MCP server URL.\n"
            "  Find it via: claude mcp get 'claude.ai Zoho MCP'",
            file=sys.stderr,
        )
        return 2

    payload = asyncio.run(_capture(url))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {payload['tool_count']} tool schemas to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
