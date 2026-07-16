"""Claude provider — wraps claude-agent-sdk.

Maps to lightspeed-agent/src/providers/claude.ts.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from lightspeed_agentic.types import (
    AgentProvider,
    ContentBlockStopEvent,
    ProviderEvent,
    ProviderQueryOptions,
    ResultEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    stringify,
)

_skills_link_cache: dict[str, str] = {}


class ClaudeProvider(AgentProvider):
    @property
    def name(self) -> str:
        return "claude"

    @staticmethod
    def _ensure_skills_link(cwd: str) -> str:
        """Set up .claude/skills/ with symlinks to each skill dir in cwd.

        Claude Code discovers skills from .claude/skills/ under its cwd.
        Creates the structure in cwd if writable (evals), otherwise falls
        back to /tmp (cluster with read-only volume mounts).
        """
        if cwd in _skills_link_cache:
            return _skills_link_cache[cwd]

        cwd_path = Path(cwd)
        if (cwd_path / ".claude" / "skills").exists():
            _skills_link_cache[cwd] = cwd
            return cwd

        fallback = Path(tempfile.gettempdir()) / "claude-workspace"
        for base in [cwd_path, fallback]:
            skills_dir = base / ".claude" / "skills"
            try:
                skills_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue
            for entry in cwd_path.iterdir():
                if entry.name.startswith(".") or not entry.is_dir():
                    continue
                with contextlib.suppress(FileExistsError):
                    (skills_dir / entry.name).symlink_to(entry)
            result = str(base)
            _skills_link_cache[cwd] = result
            return result

        _skills_link_cache[cwd] = cwd
        return cwd

    async def query(self, options: ProviderQueryOptions) -> AsyncIterator[ProviderEvent]:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            StreamEvent,
            UserMessage,
            query,
        )

        effective_cwd = self._ensure_skills_link(options.cwd)

        output_format: dict[str, object] | None = None
        if options.output_schema:
            output_format = {
                "type": "json_schema",
                "schema": options.output_schema,
            }

        mcp_servers: dict[str, Any] = {}
        allowed_tools = list(options.allowed_tools)
        if options.mcp_servers:
            from lightspeed_agentic.mcp import to_claude_mcp_config

            mcp_servers = to_claude_mcp_config(options.mcp_servers)
            for server_name in mcp_servers:
                allowed_tools.append(f"mcp__{server_name}__*")

        reasoning_kwargs: dict[str, Any] = {}
        if options.reasoning_config:
            for key in ("thinking", "effort", "max_thinking_tokens"):
                if key in options.reasoning_config:
                    reasoning_kwargs[key] = options.reasoning_config[key]

        sdk_options = ClaudeAgentOptions(
            model=options.model,
            max_turns=options.max_turns,
            max_budget_usd=options.max_budget_usd,
            system_prompt=options.system_prompt,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            cwd=effective_cwd,
            skills="all",
            include_partial_messages=True,
            output_format=output_format,
            mcp_servers=mcp_servers,
            **reasoning_kwargs,
        )

        _tool_name = ""
        _tool_call_id = ""
        _tool_input_parts: list[str] = []
        _tool_input_len = 0
        _response_model = ""
        _emitted_tool_ids: set[str] = set()

        async for msg in query(prompt=options.prompt, options=sdk_options):
            if isinstance(msg, StreamEvent):
                event = msg.event
                etype = event.get("type")
                if etype == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        _tool_name = block.get("name", "")
                        _tool_call_id = block.get("id", "")
                        _tool_input_parts.clear()
                        _tool_input_len = 0
                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    dtype = delta.get("type")
                    if dtype == "text_delta" and delta.get("text"):
                        yield TextDeltaEvent(text=delta["text"])
                    elif dtype == "thinking_delta" and delta.get("thinking"):
                        yield ThinkingDeltaEvent(thinking=delta["thinking"])
                    elif (
                        dtype == "input_json_delta"
                        and delta.get("partial_json")
                        and _tool_input_len < 100_000
                    ):
                        _tool_input_parts.append(delta["partial_json"])
                        _tool_input_len += len(delta["partial_json"])
                elif etype == "content_block_stop":
                    if _tool_name:
                        yield ToolCallEvent(
                            name=_tool_name,
                            input="".join(_tool_input_parts),
                            call_id=_tool_call_id,
                        )
                        if _tool_call_id:
                            _emitted_tool_ids.add(_tool_call_id)
                        _tool_name = ""
                        _tool_call_id = ""
                        _tool_input_parts.clear()
                        _tool_input_len = 0
                    yield ContentBlockStopEvent()
                continue

            if isinstance(msg, AssistantMessage):
                _response_model = getattr(msg, "model", "") or _response_model
                for block in msg.content:
                    if getattr(block, "type", None) == "tool_use":
                        bid = getattr(block, "id", "")
                        if bid and bid in _emitted_tool_ids:
                            continue
                        yield ToolCallEvent(
                            name=getattr(block, "name", ""),
                            input=json.dumps(getattr(block, "input", {})),
                            call_id=bid,
                        )

            if isinstance(msg, UserMessage):
                for block in getattr(msg, "content", []):
                    if getattr(block, "type", None) == "tool_result":
                        yield ToolResultEvent(
                            output=stringify(getattr(block, "content", "")),
                            call_id=getattr(block, "tool_use_id", ""),
                        )

            if isinstance(msg, ResultMessage):
                structured = getattr(msg, "structured_output", None)
                text = (
                    stringify(structured)
                    if structured is not None
                    else (getattr(msg, "result", None) or "")
                )

                usage = getattr(msg, "usage", None) or {}
                if isinstance(usage, dict):
                    in_tok = usage.get("input_tokens", 0)
                    out_tok = usage.get("output_tokens", 0)
                    details = usage.get("output_tokens_details", {}) or {}
                    reason_tok = (
                        details.get("thinking_tokens", 0)
                        if isinstance(details, dict)
                        else getattr(details, "thinking_tokens", 0)
                    )
                else:
                    in_tok = getattr(usage, "input_tokens", 0)
                    out_tok = getattr(usage, "output_tokens", 0)
                    details = getattr(usage, "output_tokens_details", None)
                    reason_tok = getattr(details, "thinking_tokens", 0) if details else 0
                yield ResultEvent(
                    text=text,
                    cost_usd=getattr(msg, "total_cost_usd", 0) or 0,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    reasoning_tokens=reason_tok,
                    response_model=_response_model,
                )
