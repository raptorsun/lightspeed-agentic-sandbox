"""Provider factory — maps to lightspeed-agent/src/providers/factory.ts."""

from __future__ import annotations

from lightspeed_agentic.types import AgentProvider


def create_provider(name: str) -> AgentProvider:
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
