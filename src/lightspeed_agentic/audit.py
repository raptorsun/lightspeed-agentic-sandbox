"""Structured audit event emission for compliance logging."""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

from opentelemetry.context import Context
from opentelemetry.trace import StatusCode

from lightspeed_agentic.metrics import tool_duration
from lightspeed_agentic.tracing import get_tracer
from lightspeed_agentic.types import TOOL_INPUT_MAX_CHARS, TOOL_OUTPUT_MAX_CHARS, ProviderEvent


def derive_phase(context: dict[str, Any] | None) -> str:
    if not context:
        return "analysis"
    if "phase" in context:
        return str(context["phase"])
    if "executionResult" in context:
        return "verification"
    if "approvedOption" in context:
        return "execution"
    return "analysis"


class AuditLogger:
    def __init__(
        self, trace_id: str, phase: str, model: str, provider: str, *, log_enabled: bool = True
    ) -> None:
        self._trace_id = trace_id
        self._phase = phase
        self._model = model
        self._provider = provider
        self._log_enabled = log_enabled
        self._text_buffer: list[str] = []
        self._thinking_buffer: list[str] = []
        self._last_tool_name = "unknown"
        self._tool_span: Any = None
        self._tool_start: float = 0.0
        self._tracer = get_tracer()
        self._parent_context: Context | None = None
        self._emit("audit.agent.started", model=model, provider=provider)

    def set_parent_context(self, ctx: Context) -> None:
        """Set the parent span context for tool spans.

        Must be called from within the agent.run span block so that
        tool spans are correctly parented under agent.run.
        """
        self._parent_context = ctx

    def process_event(self, event: ProviderEvent) -> None:
        match event.type:
            case "text_delta":
                self._text_buffer.append(event.text)
            case "thinking_delta":
                self._thinking_buffer.append(event.thinking)
            case "content_block_stop":
                self._flush_buffers()
            case "tool_call":
                self._flush_buffers()
                if self._tool_span is not None:
                    tool_duration.labels(gen_ai_tool_name=self._last_tool_name).observe(
                        time.monotonic() - self._tool_start
                    )
                    self._tool_span.end()
                self._last_tool_name = event.name or "unknown"
                self._tool_start = time.monotonic()
                self._tool_span = self._tracer.start_span(
                    f"tool.{self._last_tool_name}",
                    context=self._parent_context,
                    attributes={
                        "tool.name": self._last_tool_name,
                        "tool.input": (event.input or "")[:TOOL_INPUT_MAX_CHARS],
                    },
                )
                self._emit(
                    "audit.agent.tool.call", tool_name=self._last_tool_name, tool_input=event.input
                )
            case "tool_result":
                self._emit(
                    "audit.agent.tool.result",
                    tool_name=self._last_tool_name,
                    tool_output=event.output,
                    success=True,
                )
                if self._tool_span is not None:
                    tool_duration.labels(gen_ai_tool_name=self._last_tool_name).observe(
                        time.monotonic() - self._tool_start
                    )
                    self._tool_span.set_attribute(
                        "tool.output", event.output[:TOOL_OUTPUT_MAX_CHARS]
                    )
                    self._tool_span.set_status(StatusCode.OK)
                    self._tool_span.end()
                    self._tool_span = None
            case "result":
                self._flush_buffers()

    def complete(
        self, *, success: bool, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> None:
        self._flush_buffers()
        if self._tool_span is not None:
            tool_duration.labels(gen_ai_tool_name=self._last_tool_name).observe(
                time.monotonic() - self._tool_start
            )
            self._tool_span.set_status(StatusCode.ERROR)
            self._tool_span.end()
            self._tool_span = None
        self._emit(
            "audit.agent.completed",
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    def _flush_buffers(self) -> None:
        if self._text_buffer:
            text = "".join(self._text_buffer)
            self._text_buffer.clear()
            if text:
                self._emit("audit.agent.text", text=text)
        if self._thinking_buffer:
            thinking = "".join(self._thinking_buffer)
            self._thinking_buffer.clear()
            if thinking:
                self._emit("audit.agent.thinking", thinking=thinking)

    def _emit(self, event: str, **fields: Any) -> None:
        if not self._log_enabled:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "audit",
            "event": event,
            "trace_id": self._trace_id,
            "phase": self._phase,
            **fields,
        }
        print(json.dumps(record, default=str), flush=True, file=sys.stdout)
