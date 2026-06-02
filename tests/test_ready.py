"""Tests for GET /ready readiness endpoint."""

from __future__ import annotations

import urllib.error
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lightspeed_agentic.config import ResolvedSDK
from lightspeed_agentic.health import (
    check_provider_endpoint,
    check_provider_env,
    probe_provider_endpoint,
    register_ready_route,
    run_readiness_checks,
)

_CLAUDE_SDK = ResolvedSDK(
    "claude",
    ("ANTHROPIC_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"),
    "https://api.anthropic.com/",
)

_GEMINI_SDK = ResolvedSDK(
    "gemini",
    ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"),
    "https://generativelanguage.googleapis.com/",
)

_OPENAI_SDK = ResolvedSDK(
    "openai",
    ("OPENAI_API_KEY",),
    "https://api.openai.com/",
)


def test_check_provider_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert "error: missing" in check_provider_env(_CLAUDE_SDK.expected_envs)


def test_check_provider_env_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert check_provider_env(_CLAUDE_SDK.expected_envs) == "ok"


def test_check_provider_env_claude_vertex_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/secrets/google/credentials.json")
    assert check_provider_env(_CLAUDE_SDK.expected_envs) == "ok"


def test_check_provider_env_gemini_vertex_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/secrets/google/credentials.json")
    assert check_provider_env(_GEMINI_SDK.expected_envs) == "ok"


def test_check_provider_env_gemini_either_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert "error: missing" in check_provider_env(_GEMINI_SDK.expected_envs)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert check_provider_env(_GEMINI_SDK.expected_envs) == "ok"


def test_probe_provider_endpoint_http_error_is_ok() -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("", 403, "", {}, None)):
        assert probe_provider_endpoint("https://api.anthropic.com/") == "ok"


def test_probe_provider_endpoint_connection_error() -> None:
    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("connection refused")):
        result = probe_provider_endpoint("https://api.anthropic.com/")
    assert result.startswith("error: ")


def test_check_provider_endpoint_uses_probe_url() -> None:
    custom = ResolvedSDK("openai", ("OPENAI_API_KEY",), "https://custom.example/v1")
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint(custom.probe_url) == "ok"
    mock_probe.assert_called_once_with("https://custom.example/v1")


def test_check_provider_endpoint_vertex_url() -> None:
    vertex = ResolvedSDK(
        "claude",
        ("GOOGLE_APPLICATION_CREDENTIALS",),
        "https://europe-west4-aiplatform.googleapis.com/",
    )
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint(vertex.probe_url) == "ok"
    mock_probe.assert_called_once_with("https://europe-west4-aiplatform.googleapis.com/")


def test_check_provider_endpoint_empty_url() -> None:
    empty = ResolvedSDK("openai", ("OPENAI_API_KEY",), "")
    assert check_provider_endpoint(empty.probe_url) == "error: empty probe URL"


@pytest.mark.asyncio
async def test_ready_route_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    app = FastAPI()
    register_ready_route(app, sdk=_CLAUDE_SDK)
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_route_provider_env_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    app = FastAPI()
    register_ready_route(app, sdk=_CLAUDE_SDK)
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert body["checks"]["provider_env"].startswith("error: ")
    assert body["checks"]["provider_endpoint"] == "ok"


def test_run_readiness_checks_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with patch("lightspeed_agentic.health.probe_provider_endpoint", return_value="ok"):
        ok, checks = run_readiness_checks(_OPENAI_SDK)
    assert ok is True
    assert checks == {"provider_env": "ok", "provider_endpoint": "ok"}
