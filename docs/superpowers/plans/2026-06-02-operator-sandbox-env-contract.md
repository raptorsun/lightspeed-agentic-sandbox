# OLS-3200: Operator-Sandbox Env Var Contract — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SDK-specific env vars with generic `LIGHTSPEED_*` vars between operator and sandbox.

**Architecture:** New `config.py` in sandbox reads `LIGHTSPEED_PROVIDER` + related vars, sets SDK-specific env vars in `os.environ`, returns SDK name. Operator's `patchLLMCredentials` rewritten to set only `LIGHTSPEED_*` vars. Coordinated merge, no backward compat.

**Tech Stack:** Python (sandbox), Go/kubebuilder (operator), pytest, Go testing

---

## File Structure

### Sandbox (lightspeed-agentic-sandbox)

| File | Action | Responsibility |
|---|---|---|
| `src/lightspeed_agentic/config.py` | Create | `resolve_sdk()` — reads `LIGHTSPEED_*` vars, sets SDK env vars, returns SDK name |
| `src/lightspeed_agentic/app.py` | Modify | Wire `resolve_sdk()` before provider construction |
| `src/lightspeed_agentic/factory.py` | Modify | `create_provider(name: str)` — required arg, no env fallback |
| `src/lightspeed_agentic/health.py` | Modify | Accept `sdk_name` param instead of reading `LIGHTSPEED_AGENT_PROVIDER` |
| `tests/test_config.py` | Create | Unit tests for all 7 provider mappings |
| `tests/test_factory.py` | Modify | Update for required `name` arg |
| `tests/test_ready.py` | Modify | Update for `sdk_name` param threading |
| `tests/test_health.py` | Modify | No change expected (tests `register_health_routes`, not ready) |
| `.ai/spec/what/configuration.md` | Modify | Mark rules 1-2 implemented, remove planned tag |

### Operator (lightspeed-agentic-operator)

| File | Action | Responsibility |
|---|---|---|
| `controller/proposal/sandbox_templates.go` | Modify | `patchLLMCredentials` → set `LIGHTSPEED_*` vars, unconditional credential mount |
| `controller/proposal/sandbox_templates_test.go` | Modify | Assert `LIGHTSPEED_*` vars, no SDK-specific vars |
| `.ai/spec/what/sandbox-execution.md` | Modify | Mark OLS-3153 implemented |

---

## Task 1: Sandbox — `config.py` with `resolve_sdk()` (tests first)

**Files:**
- Create: `tests/test_config.py`
- Create: `src/lightspeed_agentic/config.py`

- [ ] **Step 1: Write failing tests for all 7 provider mappings**

Create `tests/test_config.py`:

```python
"""Tests for LIGHTSPEED_* → SDK env var mapping."""

from __future__ import annotations

import os

import pytest

from lightspeed_agentic.config import resolve_sdk


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all LIGHTSPEED_* and SDK-specific vars to isolate tests."""
    for var in [
        "LIGHTSPEED_PROVIDER",
        "LIGHTSPEED_MODEL",
        "LIGHTSPEED_MODEL_PROVIDER",
        "LIGHTSPEED_PROVIDER_URL",
        "LIGHTSPEED_PROVIDER_PROJECT",
        "LIGHTSPEED_PROVIDER_REGION",
        "LIGHTSPEED_PROVIDER_API_VERSION",
        "ANTHROPIC_MODEL",
        "GEMINI_MODEL",
        "OPENAI_MODEL",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_BEDROCK",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "CLOUD_ML_REGION",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "AWS_REGION",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "anthropic")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "claude-sonnet-4-20250514")

    sdk = resolve_sdk()

    assert sdk == "claude"
    assert os.environ["ANTHROPIC_MODEL"] == "claude-sonnet-4-20250514"


def test_anthropic_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "anthropic")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "claude-opus-4-6")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_URL", "https://proxy.example.com")

    resolve_sdk()

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://proxy.example.com"


def test_vertex_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "vertex")
    monkeypatch.setenv("LIGHTSPEED_MODEL_PROVIDER", "Anthropic")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "claude-sonnet-4-20250514")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_PROJECT", "my-project")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_REGION", "us-east5")

    sdk = resolve_sdk()

    assert sdk == "claude"
    assert os.environ["ANTHROPIC_MODEL"] == "claude-sonnet-4-20250514"
    assert os.environ["CLAUDE_CODE_USE_VERTEX"] == "1"
    assert os.environ["ANTHROPIC_VERTEX_PROJECT_ID"] == "my-project"
    assert os.environ["CLOUD_ML_REGION"] == "us-east5"
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == (
        "/var/run/secrets/llm-credentials/GOOGLE_APPLICATION_CREDENTIALS"
    )


def test_vertex_google(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "vertex")
    monkeypatch.setenv("LIGHTSPEED_MODEL_PROVIDER", "Google")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_PROJECT", "my-project")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_REGION", "us-central1")

    sdk = resolve_sdk()

    assert sdk == "gemini"
    assert os.environ["GEMINI_MODEL"] == "gemini-2.5-flash"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "my-project"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "us-central1"


def test_vertex_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "vertex")
    monkeypatch.setenv("LIGHTSPEED_MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "gpt-4.1")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_URL", "https://vertex-openai.example.com")

    sdk = resolve_sdk()

    assert sdk == "openai"
    assert os.environ["OPENAI_MODEL"] == "gpt-4.1"
    assert os.environ["OPENAI_BASE_URL"] == "https://vertex-openai.example.com"


def test_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "openai")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "gpt-4.1")

    sdk = resolve_sdk()

    assert sdk == "openai"
    assert os.environ["OPENAI_MODEL"] == "gpt-4.1"


def test_openai_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "openai")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "gpt-4.1")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_URL", "https://custom.openai.com/v1")

    resolve_sdk()

    assert os.environ["OPENAI_BASE_URL"] == "https://custom.openai.com/v1"


def test_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "azure")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "gpt-4.1")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_URL", "https://my-resource.openai.azure.com")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_API_VERSION", "2024-08-01-preview")

    sdk = resolve_sdk()

    assert sdk == "openai"
    assert os.environ["OPENAI_MODEL"] == "gpt-4.1"
    assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://my-resource.openai.azure.com"
    assert os.environ["AZURE_OPENAI_API_VERSION"] == "2024-08-01-preview"


def test_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "bedrock")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "claude-sonnet-4-20250514")
    monkeypatch.setenv("LIGHTSPEED_PROVIDER_REGION", "us-east-1")

    sdk = resolve_sdk()

    assert sdk == "claude"
    assert os.environ["ANTHROPIC_MODEL"] == "claude-sonnet-4-20250514"
    assert os.environ["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert os.environ["AWS_REGION"] == "us-east-1"


def test_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)

    sdk = resolve_sdk()

    assert sdk == "claude"


def test_default_model_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "anthropic")

    resolve_sdk()

    assert "ANTHROPIC_MODEL" not in os.environ


def test_vertex_missing_model_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "vertex")
    monkeypatch.setenv("LIGHTSPEED_MODEL", "some-model")

    with pytest.raises(ValueError, match="LIGHTSPEED_MODEL_PROVIDER"):
        resolve_sdk()


def test_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("LIGHTSPEED_PROVIDER", "watsonx")

    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_sdk()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_config -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'lightspeed_agentic.config'`

- [ ] **Step 3: Implement `resolve_sdk()` in `config.py`**

Create `src/lightspeed_agentic/config.py`:

```python
"""Configuration mapping: LIGHTSPEED_* generic vars → SDK-specific env vars.

The operator sets generic LIGHTSPEED_* env vars on the sandbox pod.
This module maps them to the SDK-specific env vars that each provider
SDK reads internally. Called once at startup before provider construction.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

LLM_CREDENTIALS_PATH = "/var/run/secrets/llm-credentials"


def _setenv(key: str, value: str) -> None:
    os.environ[key] = value


def _setenv_if(key: str, value: str | None) -> None:
    if value:
        _setenv(key, value)


def _resolve_anthropic(model: str | None, url: str | None) -> str:
    _setenv_if("ANTHROPIC_MODEL", model)
    _setenv_if("ANTHROPIC_BASE_URL", url)
    return "claude"


def _resolve_vertex(
    model_provider: str | None,
    model: str | None,
    url: str | None,
    project: str | None,
    region: str | None,
) -> str:
    if not model_provider:
        raise ValueError(
            "LIGHTSPEED_MODEL_PROVIDER is required when LIGHTSPEED_PROVIDER=vertex"
        )

    match model_provider:
        case "Anthropic":
            _setenv_if("ANTHROPIC_MODEL", model)
            _setenv("CLAUDE_CODE_USE_VERTEX", "1")
            _setenv_if("ANTHROPIC_VERTEX_PROJECT_ID", project)
            _setenv_if("CLOUD_ML_REGION", region)
            _setenv(
                "GOOGLE_APPLICATION_CREDENTIALS",
                f"{LLM_CREDENTIALS_PATH}/GOOGLE_APPLICATION_CREDENTIALS",
            )
            _setenv_if("ANTHROPIC_BASE_URL", url)
            return "claude"
        case "Google":
            _setenv_if("GEMINI_MODEL", model)
            _setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
            _setenv_if("GOOGLE_CLOUD_PROJECT", project)
            _setenv_if("GOOGLE_CLOUD_LOCATION", region)
            return "gemini"
        case "OpenAI":
            _setenv_if("OPENAI_MODEL", model)
            _setenv_if("OPENAI_BASE_URL", url)
            return "openai"
        case _:
            raise ValueError(
                f"Unknown LIGHTSPEED_MODEL_PROVIDER: {model_provider!r}. "
                "Supported: Anthropic, Google, OpenAI"
            )


def _resolve_openai(model: str | None, url: str | None) -> str:
    _setenv_if("OPENAI_MODEL", model)
    _setenv_if("OPENAI_BASE_URL", url)
    return "openai"


def _resolve_azure(
    model: str | None,
    url: str | None,
    api_version: str | None,
) -> str:
    _setenv_if("OPENAI_MODEL", model)
    _setenv_if("AZURE_OPENAI_ENDPOINT", url)
    _setenv_if("AZURE_OPENAI_API_VERSION", api_version)
    return "openai"


def _resolve_bedrock(
    model: str | None,
    url: str | None,
    region: str | None,
) -> str:
    _setenv_if("ANTHROPIC_MODEL", model)
    _setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    _setenv_if("AWS_REGION", region)
    _setenv_if("ANTHROPIC_BASE_URL", url)
    return "claude"


def resolve_sdk() -> str:
    """Read LIGHTSPEED_* env vars, set SDK-specific env vars, return SDK name.

    Returns one of: "claude", "gemini", "openai".
    """
    provider = os.environ.get("LIGHTSPEED_PROVIDER", "").strip().lower() or "anthropic"
    model = os.environ.get("LIGHTSPEED_MODEL", "").strip() or None
    model_provider = os.environ.get("LIGHTSPEED_MODEL_PROVIDER", "").strip() or None
    url = os.environ.get("LIGHTSPEED_PROVIDER_URL", "").strip() or None
    project = os.environ.get("LIGHTSPEED_PROVIDER_PROJECT", "").strip() or None
    region = os.environ.get("LIGHTSPEED_PROVIDER_REGION", "").strip() or None
    api_version = os.environ.get("LIGHTSPEED_PROVIDER_API_VERSION", "").strip() or None

    match provider:
        case "anthropic":
            sdk = _resolve_anthropic(model, url)
        case "vertex":
            sdk = _resolve_vertex(model_provider, model, url, project, region)
        case "openai":
            sdk = _resolve_openai(model, url)
        case "azure":
            sdk = _resolve_azure(model, url, api_version)
        case "bedrock":
            sdk = _resolve_bedrock(model, url, region)
        case _:
            raise ValueError(
                f"Unknown provider: {provider!r}. "
                "Supported: anthropic, vertex, openai, azure, bedrock"
            )

    logger.info("Resolved LIGHTSPEED_PROVIDER=%s → SDK=%s", provider, sdk)
    return sdk
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_config -v"`
Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test`
Expected: All PASS (config.py doesn't affect existing code yet)

- [ ] **Step 6: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox
git add src/lightspeed_agentic/config.py tests/test_config.py
git commit -m "feat: add LIGHTSPEED_* → SDK env var mapping (OLS-3200)"
```

---

## Task 2: Sandbox — Update `factory.py` to take required SDK name

**Files:**
- Modify: `src/lightspeed_agentic/factory.py`
- Modify: `tests/test_factory.py`

- [ ] **Step 1: Update `test_factory.py` — remove env fallback tests, require name arg**

Replace `tests/test_factory.py` contents:

```python
"""Tests for provider factory."""

import importlib

import pytest

from lightspeed_agentic.factory import create_provider


def test_create_provider_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("nonexistent")


def test_create_provider_requires_name():
    with pytest.raises(TypeError):
        create_provider()  # type: ignore[call-arg]


def test_create_provider_explicit_name():
    for name in ("claude", "gemini", "openai"):
        try:
            provider = create_provider(name)
            assert provider.name == name
        except ImportError:
            pass


def test_openai_provider_module_imports_without_eager_optional_sdk_imports():
    module = importlib.import_module("lightspeed_agentic.providers.openai")
    assert module.OpenAIProvider().name == "openai"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_factory -v"`
Expected: `test_create_provider_requires_name` FAILS — `create_provider()` still accepts no args

- [ ] **Step 3: Update `factory.py` — required `name` arg, no env fallback**

Replace `src/lightspeed_agentic/factory.py` contents:

```python
"""Provider factory — instantiates the selected SDK provider."""

from __future__ import annotations

from lightspeed_agentic.types import AgentProvider


def create_provider(name: str) -> AgentProvider:
    """Create a provider by SDK name: 'claude', 'gemini', or 'openai'."""
    match name:
        case "claude":
            from lightspeed_agentic.providers.claude import ClaudeProvider

            return ClaudeProvider()
        case "gemini":
            from lightspeed_agentic.providers.gemini import GeminiProvider

            return GeminiProvider()
        case "openai":
            from lightspeed_agentic.providers.openai import OpenAIProvider

            return OpenAIProvider()
        case _:
            raise ValueError(
                f"Unknown provider: {name}. Supported: claude, gemini, openai"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_factory -v"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox
git add src/lightspeed_agentic/factory.py tests/test_factory.py
git commit -m "refactor: require SDK name arg in create_provider (OLS-3200)"
```

---

## Task 3: Sandbox — Update `health.py` to accept `sdk_name` param

**Files:**
- Modify: `src/lightspeed_agentic/health.py`
- Modify: `tests/test_ready.py`

- [ ] **Step 1: Update `test_ready.py` — pass `sdk_name` instead of setting env var**

Replace `tests/test_ready.py` contents:

```python
"""Tests for GET /ready readiness endpoint."""

from __future__ import annotations

import urllib.error
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lightspeed_agentic.health import (
    check_provider_endpoint,
    check_provider_env,
    probe_provider_endpoint,
    register_ready_route,
    run_readiness_checks,
)


def test_check_provider_env_no_provider() -> None:
    assert check_provider_env(None) == "error: provider not configured"


def test_check_provider_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert "error: missing" in check_provider_env("claude")


def test_check_provider_env_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert check_provider_env("claude") == "ok"


def test_check_provider_env_claude_vertex_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/run/secrets/llm-credentials/GOOGLE_APPLICATION_CREDENTIALS")
    assert check_provider_env("claude") == "ok"


def test_check_provider_env_gemini_vertex_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/run/secrets/llm-credentials/GOOGLE_APPLICATION_CREDENTIALS")
    assert check_provider_env("gemini") == "ok"


def test_check_provider_env_gemini_either_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert "error: missing" in check_provider_env("gemini")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert check_provider_env("gemini") == "ok"


def test_check_provider_env_unknown_provider() -> None:
    assert "unknown provider" in check_provider_env("watsonx")


def test_probe_provider_endpoint_http_error_is_ok() -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("", 403, "", {}, None)):
        assert probe_provider_endpoint("https://api.anthropic.com/") == "ok"


def test_probe_provider_endpoint_connection_error() -> None:
    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("connection refused")):
        result = probe_provider_endpoint("https://api.anthropic.com/")
    assert result.startswith("error: ")


def test_check_provider_endpoint_openai_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.example/v1")
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint("openai") == "ok"
    mock_probe.assert_called_once_with("https://custom.example/v1")


def test_check_provider_endpoint_claude_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    monkeypatch.setenv("CLOUD_ML_REGION", "europe-west4")
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint("claude") == "ok"
    mock_probe.assert_called_once_with("https://europe-west4-aiplatform.googleapis.com/")


def test_check_provider_endpoint_claude_vertex_default_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    monkeypatch.delenv("CLOUD_ML_REGION", raising=False)
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint("claude") == "ok"
    mock_probe.assert_called_once_with("https://us-east5-aiplatform.googleapis.com/")


def test_check_provider_endpoint_gemini_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("CLOUD_ML_REGION", "us-central1")
    with patch(
        "lightspeed_agentic.health.probe_provider_endpoint",
        return_value="ok",
    ) as mock_probe:
        assert check_provider_endpoint("gemini") == "ok"
    mock_probe.assert_called_once_with("https://us-central1-aiplatform.googleapis.com/")


@pytest.mark.asyncio
async def test_ready_route_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    app = FastAPI()
    register_ready_route(app, sdk_name="claude")
    with patch(
        "lightspeed_agentic.health.check_provider_endpoint",
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
    register_ready_route(app, sdk_name="claude")
    with patch(
        "lightspeed_agentic.health.check_provider_endpoint",
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
    with (
        patch("lightspeed_agentic.health.check_provider_env", return_value="ok"),
        patch("lightspeed_agentic.health.check_provider_endpoint", return_value="ok"),
    ):
        ok, checks = run_readiness_checks("openai")
    assert ok is True
    assert checks == {"provider_env": "ok", "provider_endpoint": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_ready -v"`
Expected: FAIL — `register_ready_route` doesn't accept `sdk_name`, `check_provider_env(None)` returns wrong message, etc.

- [ ] **Step 3: Update `health.py` — thread `sdk_name` through all functions**

Replace `src/lightspeed_agentic/health.py` contents:

```python
"""Health and readiness probe handlers."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import JSONResponse

PROBE_TIMEOUT_SEC = 3.0

_PROVIDER_CREDENTIAL_VARS: dict[str, list[str]] = {
    "claude": ["ANTHROPIC_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
    "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
    "openai": ["OPENAI_API_KEY"],
}


def _vertex_endpoint_url() -> str:
    region = os.environ.get("CLOUD_ML_REGION", "us-east5")
    return f"https://{region}-aiplatform.googleapis.com/"


def _claude_probe_url() -> str:
    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        return _vertex_endpoint_url()
    return "https://api.anthropic.com/"


def _gemini_probe_url() -> str:
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"):
        return _vertex_endpoint_url()
    return "https://generativelanguage.googleapis.com/"


_PROVIDER_PROBE_URL: dict[str, Callable[[], str]] = {
    "claude": _claude_probe_url,
    "gemini": _gemini_probe_url,
    "openai": lambda: os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/",
}


def health_payload() -> dict[str, str]:
    return {"status": "ok"}


def register_health_routes(app: FastAPI) -> None:
    """Register GET /health (liveness)."""

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()


def check_provider_env(provider: str | None) -> str:
    """R1: required credential env var(s) present and non-empty."""
    if provider is None:
        return "error: provider not configured"
    env_vars = _PROVIDER_CREDENTIAL_VARS.get(provider)
    if env_vars is None:
        return f"error: unknown provider {provider!r}"
    if any(os.environ.get(var, "").strip() for var in env_vars):
        return "ok"
    if len(env_vars) == 1:
        return f"error: missing {env_vars[0]}"
    return f"error: missing {' or '.join(env_vars)}"


def probe_provider_endpoint(url: str, timeout: float = PROBE_TIMEOUT_SEC) -> str:
    """R2: HTTP GET; any HTTP response (including 4xx) means reachable."""
    scheme = urlparse(url).scheme
    if scheme not in ("https", "http"):
        return f"error: unsupported URL scheme {scheme!r}"
    try:
        request = urllib.request.Request(url, method="GET")  # noqa: S310
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
            return "ok"
    except urllib.error.HTTPError:
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def check_provider_endpoint(provider: str | None) -> str:
    if provider is None:
        return "error: provider not configured"
    url_fn = _PROVIDER_PROBE_URL.get(provider)
    if url_fn is None:
        return f"error: unknown provider {provider!r}"
    url = url_fn().strip()
    if not url:
        return "error: empty probe URL"
    return probe_provider_endpoint(url)


def run_readiness_checks(provider: str | None) -> tuple[bool, dict[str, str]]:
    checks = {
        "provider_env": check_provider_env(provider),
        "provider_endpoint": check_provider_endpoint(provider),
    }
    return all(status == "ok" for status in checks.values()), checks


def ready_response(provider: str | None) -> tuple[int, dict[str, object]]:
    ok, checks = run_readiness_checks(provider)
    if ok:
        return 200, {"status": "ok"}
    return 503, {"status": "error", "checks": checks}


def register_ready_route(app: FastAPI, *, sdk_name: str | None = None) -> None:
    """Register GET /ready (readiness)."""

    @app.get("/ready")
    def ready() -> JSONResponse:
        status_code, body = ready_response(sdk_name)
        return JSONResponse(status_code=status_code, content=body)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_ready -v"`
Expected: All PASS

- [ ] **Step 5: Run `test_health.py` to confirm no regression**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test PYTEST_ARGS="-k test_health -v"`
Expected: All PASS (health tests don't touch ready logic)

- [ ] **Step 6: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox
git add src/lightspeed_agentic/health.py tests/test_ready.py
git commit -m "refactor: thread sdk_name through readiness checks (OLS-3200)"
```

---

## Task 4: Sandbox — Wire `app.py` and run full suite

**Files:**
- Modify: `src/lightspeed_agentic/app.py`

- [ ] **Step 1: Update `app.py` to call `resolve_sdk()` and thread SDK name**

Replace `src/lightspeed_agentic/app.py` contents:

```python
"""FastAPI application — production entry point.

Usage: uvicorn lightspeed_agentic.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from lightspeed_agentic.config import resolve_sdk
from lightspeed_agentic.factory import create_provider
from lightspeed_agentic.health import register_health_routes, register_ready_route
from lightspeed_agentic.routes import build_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

sdk_name = resolve_sdk()

app = FastAPI(title="lightspeed-agentic-sandbox")

provider = create_provider(sdk_name)
router = build_router(
    provider,
    skills_dir=os.environ.get("LIGHTSPEED_SKILLS_DIR", "/app/skills"),
)
app.include_router(router, prefix="/v1/agent")

register_health_routes(app)
register_ready_route(app, sdk_name=sdk_name)
```

- [ ] **Step 2: Run full test suite**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test`
Expected: All PASS

- [ ] **Step 3: Run lint**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox
git add src/lightspeed_agentic/app.py
git commit -m "feat: wire resolve_sdk() into app startup (OLS-3200)"
```

---

## Task 5: Sandbox — Update behavioral specs

**Files:**
- Modify: `.ai/spec/what/configuration.md`

- [ ] **Step 1: Update `configuration.md` — mark OLS-3153 as implemented**

In `.ai/spec/what/configuration.md`, in the "Planned Changes" section, change:

```
- [OLS-3153] **Operator-sandbox env var contract**: generic `LIGHTSPEED_*` env vars replace SDK-specific env vars set by operator. Sandbox handles all SDK-specific mapping via configuration mapping (rule 2).
```

to:

```
- [OLS-3153] ~~IMPLEMENTED~~ Operator-sandbox env var contract: generic `LIGHTSPEED_*` env vars replace SDK-specific env vars. Sandbox handles all SDK-specific mapping via `config.py:resolve_sdk()` (rule 2).
```

- [ ] **Step 2: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox
git add .ai/spec/what/configuration.md
git commit -m "docs: mark OLS-3153 env var contract as implemented (OLS-3200)"
```

---

## Task 6: Operator — Rewrite `patchLLMCredentials` (tests first)

**Files:**
- Modify: `controller/proposal/sandbox_templates_test.go`
- Modify: `controller/proposal/sandbox_templates.go`

- [ ] **Step 1: Update test helpers and constants for new contract**

In `controller/proposal/sandbox_templates_test.go`, update the `testLLMProvider` helper for Vertex to include `ModelProvider`:

At the `LLMProviderGoogleCloudVertex` case (line 18), change:

```go
	case agenticv1alpha1.LLMProviderGoogleCloudVertex:
		spec.GoogleCloudVertex = agenticv1alpha1.GoogleCloudVertexConfig{CredentialsSecret: creds, ProjectID: "test-project", Region: "us-central1"}
```

to:

```go
	case agenticv1alpha1.LLMProviderGoogleCloudVertex:
		spec.GoogleCloudVertex = agenticv1alpha1.GoogleCloudVertexConfig{CredentialsSecret: creds, ProjectID: "test-project", Region: "us-central1", ModelProvider: agenticv1alpha1.GoogleCloudVertexModelProviderAnthropic}
```

- [ ] **Step 2: Rewrite `TestPatchLLMCredentials_Anthropic` for generic vars**

Replace `TestPatchLLMCredentials_Anthropic` (lines 236-260):

```go
func TestPatchLLMCredentials_Anthropic(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProviderWithURL(agenticv1alpha1.LLMProviderAnthropic, "https://custom.api")

	if err := patchLLMCredentials(tmpl, llm, "claude-opus-4-6"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	if !hasSecretEnvFrom(tmpl, "my-llm-secret") {
		t.Error("missing envFrom secretRef for my-llm-secret")
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER")
	} else if e["value"] != "anthropic" {
		t.Errorf("LIGHTSPEED_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_MODEL"); !ok {
		t.Error("missing LIGHTSPEED_MODEL")
	} else if e["value"] != "claude-opus-4-6" {
		t.Errorf("LIGHTSPEED_MODEL = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_URL"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_URL")
	} else if e["value"] != "https://custom.api" {
		t.Errorf("LIGHTSPEED_PROVIDER_URL = %q", e["value"])
	}

	// Must NOT have SDK-specific vars
	if _, ok := findEnv(envs, "ANTHROPIC_MODEL"); ok {
		t.Error("should not set ANTHROPIC_MODEL")
	}
	if _, ok := findEnv(envs, "ANTHROPIC_BASE_URL"); ok {
		t.Error("should not set ANTHROPIC_BASE_URL")
	}

	// Must have unconditional credential volume mount
	assertCredentialVolumeMount(t, tmpl)
}
```

- [ ] **Step 3: Rewrite `TestPatchLLMCredentials_Vertex` for generic vars**

Replace `TestPatchLLMCredentials_Vertex` (lines 262-297):

```go
func TestPatchLLMCredentials_Vertex(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProvider(agenticv1alpha1.LLMProviderGoogleCloudVertex)

	if err := patchLLMCredentials(tmpl, llm, "claude-opus-4-6"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	if !hasSecretEnvFrom(tmpl, "my-llm-secret") {
		t.Error("missing envFrom secretRef for my-llm-secret")
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER")
	} else if e["value"] != "vertex" {
		t.Errorf("LIGHTSPEED_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_MODEL"); !ok {
		t.Error("missing LIGHTSPEED_MODEL")
	} else if e["value"] != "claude-opus-4-6" {
		t.Errorf("LIGHTSPEED_MODEL = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_MODEL_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_MODEL_PROVIDER")
	} else if e["value"] != "Anthropic" {
		t.Errorf("LIGHTSPEED_MODEL_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_PROJECT"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_PROJECT")
	} else if e["value"] != "test-project" {
		t.Errorf("LIGHTSPEED_PROVIDER_PROJECT = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_REGION"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_REGION")
	} else if e["value"] != "us-central1" {
		t.Errorf("LIGHTSPEED_PROVIDER_REGION = %q", e["value"])
	}

	// Must NOT have SDK-specific vars
	if _, ok := findEnv(envs, "CLAUDE_CODE_USE_VERTEX"); ok {
		t.Error("should not set CLAUDE_CODE_USE_VERTEX")
	}
	if _, ok := findEnv(envs, "GOOGLE_APPLICATION_CREDENTIALS"); ok {
		t.Error("should not set GOOGLE_APPLICATION_CREDENTIALS")
	}

	assertCredentialVolumeMount(t, tmpl)
}
```

- [ ] **Step 4: Rewrite `TestPatchLLMCredentials_Bedrock` for generic vars**

Replace `TestPatchLLMCredentials_Bedrock` (lines 299-313):

```go
func TestPatchLLMCredentials_Bedrock(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProvider(agenticv1alpha1.LLMProviderAWSBedrock)

	if err := patchLLMCredentials(tmpl, llm, "claude-opus-4-6"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER")
	} else if e["value"] != "bedrock" {
		t.Errorf("LIGHTSPEED_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_REGION"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_REGION")
	} else if e["value"] != "us-east-1" {
		t.Errorf("LIGHTSPEED_PROVIDER_REGION = %q", e["value"])
	}

	// Must NOT have SDK-specific vars
	if _, ok := findEnv(envs, "CLAUDE_CODE_USE_BEDROCK"); ok {
		t.Error("should not set CLAUDE_CODE_USE_BEDROCK")
	}

	assertCredentialVolumeMount(t, tmpl)
}
```

- [ ] **Step 5: Add `assertCredentialVolumeMount` test helper**

Add this helper function after the `emptyTemplate()` function:

```go
func assertCredentialVolumeMount(t *testing.T, tmpl *unstructured.Unstructured) {
	t.Helper()
	containers, _, _ := unstructured.NestedSlice(tmpl.Object, "spec", "podTemplate", "spec", "containers")
	if len(containers) == 0 {
		t.Fatal("no containers")
	}
	container := containers[0].(map[string]any)
	mounts, _, _ := unstructured.NestedSlice(container, "volumeMounts")
	found := false
	for _, m := range mounts {
		mount := m.(map[string]any)
		if mount["name"] == llmCredsVolumeName && mount["mountPath"] == llmCredsMountPath {
			found = true
			if mount["readOnly"] != true {
				t.Error("credential volume mount should be readOnly")
			}
			break
		}
	}
	if !found {
		t.Errorf("missing credential volume mount at %s", llmCredsMountPath)
	}
}
```

- [ ] **Step 6: Add tests for Azure and OpenAI providers**

Add after `TestPatchLLMCredentials_Bedrock`:

```go
func TestPatchLLMCredentials_OpenAI(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProviderWithURL(agenticv1alpha1.LLMProviderOpenAI, "https://custom.openai.com")

	if err := patchLLMCredentials(tmpl, llm, "gpt-4.1"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER")
	} else if e["value"] != "openai" {
		t.Errorf("LIGHTSPEED_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_MODEL"); !ok {
		t.Error("missing LIGHTSPEED_MODEL")
	} else if e["value"] != "gpt-4.1" {
		t.Errorf("LIGHTSPEED_MODEL = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_URL"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_URL")
	} else if e["value"] != "https://custom.openai.com" {
		t.Errorf("LIGHTSPEED_PROVIDER_URL = %q", e["value"])
	}

	if _, ok := findEnv(envs, "OPENAI_BASE_URL"); ok {
		t.Error("should not set OPENAI_BASE_URL")
	}

	assertCredentialVolumeMount(t, tmpl)
}

func TestPatchLLMCredentials_Azure(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProvider(agenticv1alpha1.LLMProviderAzureOpenAI)
	llm.Spec.AzureOpenAI.APIVersion = "2024-08-01-preview"

	if err := patchLLMCredentials(tmpl, llm, "gpt-4.1"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER")
	} else if e["value"] != "azure" {
		t.Errorf("LIGHTSPEED_PROVIDER = %q", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_URL"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_URL")
	} else if e["value"] != "https://test.openai.azure.com" {
		t.Errorf("LIGHTSPEED_PROVIDER_URL = %q, want endpoint", e["value"])
	}

	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_API_VERSION"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_API_VERSION")
	} else if e["value"] != "2024-08-01-preview" {
		t.Errorf("LIGHTSPEED_PROVIDER_API_VERSION = %q", e["value"])
	}

	if _, ok := findEnv(envs, "AZURE_OPENAI_ENDPOINT"); ok {
		t.Error("should not set AZURE_OPENAI_ENDPOINT")
	}

	assertCredentialVolumeMount(t, tmpl)
}

func TestPatchLLMCredentials_AzureURLOverridesEndpoint(t *testing.T) {
	tmpl := emptyTemplate()
	llm := testLLMProvider(agenticv1alpha1.LLMProviderAzureOpenAI)
	llm.Spec.AzureOpenAI.URL = "https://proxy.example.com"

	if err := patchLLMCredentials(tmpl, llm, "gpt-4.1"); err != nil {
		t.Fatalf("patchLLMCredentials: %v", err)
	}

	envs := getEnvVars(tmpl)
	if e, ok := findEnv(envs, "LIGHTSPEED_PROVIDER_URL"); !ok {
		t.Error("missing LIGHTSPEED_PROVIDER_URL")
	} else if e["value"] != "https://proxy.example.com" {
		t.Errorf("LIGHTSPEED_PROVIDER_URL = %q, want URL override", e["value"])
	}
}
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator && go test ./controller/proposal/ -run TestPatchLLMCredentials -v`
Expected: FAIL — `patchLLMCredentials` still sets old env vars

- [ ] **Step 8: Rewrite `patchLLMCredentials` in `sandbox_templates.go`**

Update the constants at the top of the file. Change:

```go
	vertexCredsMountPath = "/var/secrets/google"
	vertexCredsFileName  = "credentials.json"
	llmCredsVolumeName   = "llm-credentials"
```

to:

```go
	llmCredsMountPath  = "/var/run/secrets/llm-credentials"
	llmCredsVolumeName = "llm-credentials"
```

Then replace the `patchLLMCredentials` function body. The new function:
1. Always sets `LIGHTSPEED_PROVIDER` (mapped from `LLMProviderType`)
2. Always sets `LIGHTSPEED_MODEL` from the `model` argument
3. Always calls `addEnvFromSecret` and `addSecretVolume`/`addVolumeMount` (unconditional)
4. Per-type switch sets only optional `LIGHTSPEED_*` vars

Provider type mapping in Go:

```go
func providerTypeString(t agenticv1alpha1.LLMProviderType) string {
	switch t {
	case agenticv1alpha1.LLMProviderAnthropic:
		return "anthropic"
	case agenticv1alpha1.LLMProviderGoogleCloudVertex:
		return "vertex"
	case agenticv1alpha1.LLMProviderOpenAI:
		return "openai"
	case agenticv1alpha1.LLMProviderAzureOpenAI:
		return "azure"
	case agenticv1alpha1.LLMProviderAWSBedrock:
		return "bedrock"
	default:
		return strings.ToLower(string(t))
	}
}
```

New `patchLLMCredentials`:

```go
func patchLLMCredentials(tmpl *unstructured.Unstructured, llm *agenticv1alpha1.LLMProvider, model string) error {
	secretName := credentialsSecretName(llm)
	if secretName == "" {
		return fmt.Errorf("%s: credentials secret not configured", ErrLLMCredentials)
	}

	// Generic vars — always set
	if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER", providerTypeString(llm.Spec.Type)); err != nil {
		return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
	}
	if err := setEnvVar(tmpl, "LIGHTSPEED_MODEL", model); err != nil {
		return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
	}

	// Credentials — unconditional envFrom + volume mount
	if err := addEnvFromSecret(tmpl, secretName); err != nil {
		return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
	}
	if err := addSecretVolume(tmpl, llmCredsVolumeName, secretName); err != nil {
		return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
	}
	if err := addVolumeMount(tmpl, llmCredsVolumeName, llmCredsMountPath, true); err != nil {
		return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
	}

	// Per-provider optional vars
	switch llm.Spec.Type {
	case agenticv1alpha1.LLMProviderAnthropic:
		if u := llm.Spec.Anthropic.URL; u != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_URL", u); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}

	case agenticv1alpha1.LLMProviderGoogleCloudVertex:
		cfg := llm.Spec.GoogleCloudVertex
		if err := setEnvVar(tmpl, "LIGHTSPEED_MODEL_PROVIDER", string(cfg.ModelProvider)); err != nil {
			return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
		}
		if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_PROJECT", cfg.ProjectID); err != nil {
			return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
		}
		if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_REGION", cfg.Region); err != nil {
			return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
		}
		if u := cfg.URL; u != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_URL", u); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}

	case agenticv1alpha1.LLMProviderOpenAI:
		if u := llm.Spec.OpenAI.URL; u != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_URL", u); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}

	case agenticv1alpha1.LLMProviderAzureOpenAI:
		cfg := llm.Spec.AzureOpenAI
		url := cfg.Endpoint
		if cfg.URL != "" {
			url = cfg.URL
		}
		if url != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_URL", url); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}
		if cfg.APIVersion != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_API_VERSION", cfg.APIVersion); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}

	case agenticv1alpha1.LLMProviderAWSBedrock:
		cfg := llm.Spec.AWSBedrock
		if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_REGION", cfg.Region); err != nil {
			return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
		}
		if u := cfg.URL; u != "" {
			if err := setEnvVar(tmpl, "LIGHTSPEED_PROVIDER_URL", u); err != nil {
				return fmt.Errorf("%s: %w", ErrLLMCredentials, err)
			}
		}
	}

	return nil
}
```

Note: you will need to add `"strings"` to the import block if not already there, for `strings.ToLower` in `providerTypeString`.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator && go test ./controller/proposal/ -run TestPatchLLMCredentials -v`
Expected: All PASS

- [ ] **Step 10: Run full operator test suite**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator && make test`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator
git add controller/proposal/sandbox_templates.go controller/proposal/sandbox_templates_test.go
git commit -m "feat: replace SDK-specific env vars with LIGHTSPEED_* contract (OLS-3200)"
```

---

## Task 7: Operator — Update behavioral spec

**Files:**
- Modify: `.ai/spec/what/sandbox-execution.md`

- [ ] **Step 1: Mark OLS-3153 as implemented in Planned Changes**

In `.ai/spec/what/sandbox-execution.md`, in the "Planned Changes" section, change:

```
- [OLS-3153] **Operator-sandbox env var contract**: SDK-specific env vars removed from operator; replaced by generic `LIGHTSPEED_*` vars (rule 16a). Sandbox handles all SDK-specific mapping internally. Supersedes OLS-3044 and OLS-3051.
```

to:

```
- [OLS-3153] ~~IMPLEMENTED~~ Operator-sandbox env var contract: SDK-specific env vars removed from operator; replaced by generic `LIGHTSPEED_*` vars (rule 16a). Sandbox handles all SDK-specific mapping internally. Supersedes OLS-3044 and OLS-3051.
```

- [ ] **Step 2: Commit**

```bash
cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator
git add .ai/spec/what/sandbox-execution.md
git commit -m "docs: mark OLS-3153 env var contract as implemented (OLS-3200)"
```

---

## Task 8: Final verification — both repos

- [ ] **Step 1: Run sandbox full suite**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && make test && make lint`
Expected: All PASS, no lint errors

- [ ] **Step 2: Run operator full suite**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator && make test`
Expected: All PASS

- [ ] **Step 3: Verify no remaining LIGHTSPEED_AGENT_PROVIDER references in sandbox**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-sandbox && rg "LIGHTSPEED_AGENT_PROVIDER" src/ tests/`
Expected: No matches

- [ ] **Step 4: Verify no SDK-specific env vars in operator template code**

Run: `cd /home/ometelka/projects/ols-agentic/lightspeed-agentic-operator && rg "ANTHROPIC_MODEL|CLAUDE_CODE_USE_VERTEX|OPENAI_BASE_URL|GCP_PROJECT|GCP_REGION" controller/proposal/sandbox_templates.go`
Expected: No matches
