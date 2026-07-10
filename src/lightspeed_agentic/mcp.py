"""MCP server configuration parsing and header resolution.

Reads LIGHTSPEED_MCP_SERVERS env var (JSON array) and resolves header values
from Kubernetes-mounted secrets and projected service account tokens.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("lightspeed_agentic")

SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # noqa: S105
MCP_SECRET_MOUNT_ROOT = "/var/secrets/mcp"  # noqa: S105


@dataclass(frozen=True)
class ResolvedMCPHeader:
    name: str
    value: str


@dataclass(frozen=True)
class ResolvedMCPServer:
    name: str
    url: str
    timeout: int = 60
    headers: list[ResolvedMCPHeader] = field(default_factory=list)


def _resolve_header(header: dict) -> ResolvedMCPHeader | None:
    """Resolve a single header entry based on its source type."""
    name = header["name"]
    source = header["source"]

    if source == "ServiceAccountToken":
        try:
            token = Path(SA_TOKEN_PATH).read_text().strip()
        except OSError:
            logger.warning("SA token not found at %s for header %s", SA_TOKEN_PATH, name)
            return None
        return ResolvedMCPHeader(name=name, value=f"Bearer {token}")

    if source == "Secret":
        secret_name = header.get("secretName", "")
        root = Path(MCP_SECRET_MOUNT_ROOT).resolve()
        secret_dir = (root / secret_name).resolve()
        if not secret_name or not secret_dir.is_relative_to(root):
            logger.warning("Invalid secret path: %s for header %s", secret_dir, name)
            return None
        if not secret_dir.is_dir():
            logger.warning("Secret dir not found: %s for header %s", secret_dir, name)
            return None
        try:
            files = sorted(
                (f for f in secret_dir.iterdir() if f.is_file()), key=lambda f: f.name
            )
        except OSError:
            logger.warning("Cannot list secret dir %s for header %s", secret_dir, name)
            return None
        if not files:
            logger.warning("No files in secret dir %s for header %s", secret_dir, name)
            return None
        try:
            value = files[0].read_text().strip()
        except OSError:
            logger.warning("Cannot read secret file %s for header %s", files[0], name)
            return None
        return ResolvedMCPHeader(name=name, value=value)

    if source == "Client":
        return None

    logger.warning("Unknown header source %r for header %s, skipping", source, name)
    return None


def parse_mcp_servers() -> list[ResolvedMCPServer]:
    """Parse LIGHTSPEED_MCP_SERVERS env var and resolve all header values."""
    raw = os.environ.get("LIGHTSPEED_MCP_SERVERS", "").strip()
    if not raw:
        return []

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in LIGHTSPEED_MCP_SERVERS")
        return []

    if not isinstance(entries, list):
        logger.error("LIGHTSPEED_MCP_SERVERS must be a JSON array")
        return []

    servers: list[ResolvedMCPServer] = []
    for entry in entries:
        if not isinstance(entry, dict) or "name" not in entry or "url" not in entry:
            logger.warning("Skipping invalid MCP server entry: %r", entry)
            continue
        resolved_headers: list[ResolvedMCPHeader] = []
        for h in entry.get("headers", []):
            if not isinstance(h, dict) or "name" not in h or "source" not in h:
                logger.warning("Skipping invalid header in server %r: %r", entry.get("name"), h)
                continue
            resolved = _resolve_header(h)
            if resolved is not None:
                resolved_headers.append(resolved)

        servers.append(
            ResolvedMCPServer(
                name=entry["name"],
                url=entry["url"],
                timeout=entry.get("timeout", 60),
                headers=resolved_headers,
            )
        )

    if servers:
        logger.info("Resolved %d MCP server(s): %s", len(servers), [s.name for s in servers])
    return servers


def _headers_dict(server: ResolvedMCPServer) -> dict[str, str]:
    return {h.name: h.value for h in server.headers}


def to_claude_mcp_config(servers: list[ResolvedMCPServer]) -> dict[str, dict]:
    """Convert to claude-agent-sdk McpServerConfig format (dict keyed by name)."""
    result: dict[str, dict] = {}
    for s in servers:
        result[s.name] = {
            "type": "http",
            "url": s.url,
            **( {"headers": _headers_dict(s)} if s.headers else {}),
        }
    return result


def to_gemini_mcp_toolsets(servers: list[ResolvedMCPServer]) -> list:
    """Convert to google-adk McpToolset instances."""
    from google.adk.tools.mcp_tool.mcp_toolset import (
        McpToolset,
        StreamableHTTPConnectionParams,
    )

    toolsets = []
    for s in servers:
        params = StreamableHTTPConnectionParams(
            url=s.url,
            headers=_headers_dict(s) if s.headers else None,
            timeout=float(s.timeout),
        )
        toolsets.append(McpToolset(connection_params=params))
    return toolsets


def to_openai_mcp_servers(servers: list[ResolvedMCPServer]) -> list:
    """Convert to openai-agents MCPServerStreamableHttp instances."""
    from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams

    result = []
    for s in servers:
        params = MCPServerStreamableHttpParams(
            url=s.url,
            **( {"headers": _headers_dict(s)} if s.headers else {}),
        )
        result.append(MCPServerStreamableHttp(params=params, name=s.name))
    return result
