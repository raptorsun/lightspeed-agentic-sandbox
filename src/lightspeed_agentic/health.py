"""Liveness probe handler — process responsive, no external calls."""

from __future__ import annotations

from fastapi import FastAPI


def health_payload() -> dict[str, str]:
    return {"status": "ok"}


def register_health_routes(app: FastAPI) -> None:
    """Register GET /health (liveness)."""

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()
