"""Provider factory — maps to lightspeed-agent/src/providers/factory.ts."""

from __future__ import annotations

from lightspeed_agentic.types import AgentProvider


def create_provider(name: str) -> AgentProvider:
    match name:
        case "deepagents":
            from lightspeed_agentic.providers.deepagents import DeepAgentsProvider

            return DeepAgentsProvider()
        case "gemini":
            from lightspeed_agentic.providers.gemini import GeminiProvider

            return GeminiProvider()
        case "openai":
            from lightspeed_agentic.providers.openai import OpenAIProvider

            return OpenAIProvider()
        case _:
            raise ValueError(f"Unknown provider: {name}. Supported: deepagents, gemini, openai")
