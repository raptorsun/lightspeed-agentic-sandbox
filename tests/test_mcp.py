"""Tests for MCP server configuration parsing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lightspeed_agentic.mcp import (
    MCP_SECRET_MOUNT_ROOT,
    SA_TOKEN_PATH,
    ResolvedMCPHeader,
    ResolvedMCPServer,
    parse_mcp_servers,
)


class TestParseMCPServers:
    def test_empty_env_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert parse_mcp_servers() == []

    def test_empty_string_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": ""}):
            assert parse_mcp_servers() == []

    def test_whitespace_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": "   "}):
            assert parse_mcp_servers() == []

    def test_invalid_json_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": "not-json"}):
            assert parse_mcp_servers() == []

    def test_non_array_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": '{"key": "val"}'}):
            assert parse_mcp_servers() == []

    def test_basic_server_no_headers(self):
        servers_json = json.dumps([{"name": "test", "url": "http://test:8080/mcp"}])
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0] == ResolvedMCPServer(
                name="test", url="http://test:8080/mcp", timeout=60, headers=[]
            )

    def test_custom_timeout(self):
        servers_json = json.dumps(
            [{"name": "test", "url": "http://test:8080/mcp", "timeout": 120}]
        )
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert result[0].timeout == 120

    def test_service_account_token_header(self, tmp_path: Path):
        token_file = tmp_path / "token"
        token_file.write_text("my-sa-token")

        servers_json = json.dumps(
            [
                {
                    "name": "ocp",
                    "url": "http://mcp:8080/mcp",
                    "headers": [{"name": "Authorization", "source": "ServiceAccountToken"}],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", str(token_file)),
        ):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0].headers == [
                ResolvedMCPHeader(name="Authorization", value="Bearer my-sa-token")
            ]

    def test_service_account_token_missing(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ocp",
                    "url": "http://mcp:8080/mcp",
                    "headers": [{"name": "Authorization", "source": "ServiceAccountToken"}],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", "/nonexistent/path"),
        ):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0].headers == []

    def test_secret_header(self, tmp_path: Path):
        secret_dir = tmp_path / "my-secret"
        secret_dir.mkdir()
        (secret_dir / "header").write_text("secret-value-123")

        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [
                        {"name": "X-Api-Key", "source": "Secret", "secretName": "my-secret"}
                    ],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.MCP_SECRET_MOUNT_ROOT", str(tmp_path)),
        ):
            result = parse_mcp_servers()
            assert result[0].headers == [
                ResolvedMCPHeader(name="X-Api-Key", value="secret-value-123")
            ]

    def test_secret_dir_missing(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [
                        {"name": "X-Api-Key", "source": "Secret", "secretName": "no-such-secret"}
                    ],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.MCP_SECRET_MOUNT_ROOT", "/nonexistent"),
        ):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_client_source_skipped(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [{"name": "Authorization", "source": "Client"}],
                }
            ]
        )
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_multiple_servers(self, tmp_path: Path):
        token_file = tmp_path / "token"
        token_file.write_text("tok")

        servers_json = json.dumps(
            [
                {"name": "a", "url": "http://a:8080/mcp"},
                {"name": "b", "url": "http://b:8080/mcp", "timeout": 30},
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", str(token_file)),
        ):
            result = parse_mcp_servers()
            assert len(result) == 2
            assert result[0].name == "a"
            assert result[1].name == "b"
            assert result[1].timeout == 30
