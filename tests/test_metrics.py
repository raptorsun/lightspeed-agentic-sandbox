"""Tests for gen_ai.* Prometheus metrics."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY

from lightspeed_agentic.metrics import register_metrics_route
from lightspeed_agentic.routes import build_router
from lightspeed_agentic.types import ResultEvent, ToolCallEvent, ToolResultEvent

from .conftest import MockProvider


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _make_app(provider: MockProvider) -> FastAPI:
    app = FastAPI()
    router = build_router(provider, skills_dir="/workspace", model="test-model")
    app.include_router(router, prefix="/v1/agent")
    register_metrics_route(app)
    return app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format():
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "gen_ai_client_token_usage" in resp.text


@pytest.mark.asyncio
async def test_run_records_token_usage():
    provider = MockProvider(
        events=[
            ResultEvent(
                text='{"success": true, "summary": "ok"}',
                cost_usd=0.01,
                input_tokens=100,
                output_tokens=50,
            ),
        ]
    )
    app = _make_app(provider)
    labels_in = {
        "gen_ai_token_type": "input",
        "gen_ai_request_model": "test-model",
        "gen_ai_provider_name": "mock",
        "gen_ai_operation_name": "chat",
    }
    labels_out = {
        "gen_ai_token_type": "output",
        "gen_ai_request_model": "test-model",
        "gen_ai_provider_name": "mock",
        "gen_ai_operation_name": "chat",
    }
    before_in_count = _sample("gen_ai_client_token_usage_count", labels_in)
    before_out_count = _sample("gen_ai_client_token_usage_count", labels_out)
    before_in_sum = _sample("gen_ai_client_token_usage_sum", labels_in)
    before_out_sum = _sample("gen_ai_client_token_usage_sum", labels_out)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200

    assert _sample("gen_ai_client_token_usage_count", labels_in) == before_in_count + 1
    assert _sample("gen_ai_client_token_usage_count", labels_out) == before_out_count + 1
    assert _sample("gen_ai_client_token_usage_sum", labels_in) == before_in_sum + 100
    assert _sample("gen_ai_client_token_usage_sum", labels_out) == before_out_sum + 50


@pytest.mark.asyncio
async def test_run_records_operation_duration():
    app = _make_app(MockProvider())
    labels = {
        "gen_ai_request_model": "test-model",
        "gen_ai_provider_name": "mock",
        "gen_ai_operation_name": "chat",
    }
    before_count = _sample("gen_ai_client_operation_duration_seconds_count", labels)
    before_sum = _sample("gen_ai_client_operation_duration_seconds_sum", labels)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200

    assert _sample("gen_ai_client_operation_duration_seconds_count", labels) == before_count + 1
    delta = _sample("gen_ai_client_operation_duration_seconds_sum", labels) - before_sum
    assert delta > 0, "operation duration must be positive"


@pytest.mark.asyncio
async def test_run_records_tool_duration():
    events = [
        ToolCallEvent(name="bash", input="ls"),
        ToolResultEvent(output="file.txt"),
        ResultEvent(
            text='{"success": true, "summary": "done"}',
            cost_usd=0.01,
            input_tokens=10,
            output_tokens=5,
        ),
    ]
    app = _make_app(MockProvider(events=events))
    labels = {"gen_ai_tool_name": "bash"}
    before_count = _sample("gen_ai_execute_tool_duration_seconds_count", labels)
    before_sum = _sample("gen_ai_execute_tool_duration_seconds_sum", labels)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200

    assert _sample("gen_ai_execute_tool_duration_seconds_count", labels) == before_count + 1
    delta = _sample("gen_ai_execute_tool_duration_seconds_sum", labels) - before_sum
    assert delta > 0, "tool duration must be positive"


@pytest.mark.asyncio
async def test_empty_response_records_metrics():
    provider = MockProvider(events=[ResultEvent(text="")])
    app = _make_app(provider)
    labels = {
        "gen_ai_request_model": "test-model",
        "gen_ai_provider_name": "mock",
        "gen_ai_operation_name": "chat",
    }
    before = _sample("gen_ai_client_operation_duration_seconds_count", labels)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    assert _sample("gen_ai_client_operation_duration_seconds_count", labels) == before + 1


@pytest.mark.asyncio
async def test_zero_tokens_not_recorded():
    provider = MockProvider(events=[ResultEvent(text="")])
    app = _make_app(provider)
    labels_in = {
        "gen_ai_token_type": "input",
        "gen_ai_request_model": "test-model",
        "gen_ai_provider_name": "mock",
        "gen_ai_operation_name": "chat",
    }
    before = _sample("gen_ai_client_token_usage_count", labels_in)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/agent/run", json={"query": "test"})

    assert _sample("gen_ai_client_token_usage_count", labels_in) == before
