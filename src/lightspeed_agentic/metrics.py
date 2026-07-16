"""Prometheus metrics for OTel GenAI semantic conventions."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest

TOKEN_BUCKETS = (
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
)

token_usage = Histogram(
    "gen_ai_client_token_usage",
    "Token usage distribution",
    ["gen_ai_token_type", "gen_ai_request_model", "gen_ai_provider_name", "gen_ai_operation_name"],
    buckets=TOKEN_BUCKETS,
)

operation_duration = Histogram(
    "gen_ai_client_operation_duration_seconds",
    "LLM operation duration",
    ["gen_ai_request_model", "gen_ai_provider_name", "gen_ai_operation_name"],
)

tool_duration = Histogram(
    "gen_ai_execute_tool_duration_seconds",
    "Tool execution duration",
    ["gen_ai_tool_name"],
)


def register_metrics_route(app: FastAPI) -> None:
    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
