"""Tests for GET /health liveness endpoint."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lightspeed_agentic.health import health_payload, register_health_routes


def test_health_payload() -> None:
    assert health_payload() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_route() -> None:
    app = FastAPI()
    register_health_routes(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
