"""Tests for reasoning config parsing and provider adapter wiring."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lightspeed_agentic.types import ProviderQueryOptions


def _base_options(**overrides) -> ProviderQueryOptions:
    defaults = {
        "prompt": "test prompt",
        "system_prompt": "test system",
        "model": "test-model",
        "max_turns": 10,
        "max_budget_usd": 1.0,
        "allowed_tools": ["Bash"],
        "cwd": "/tmp/test",  # noqa: S108
    }
    defaults.update(overrides)
    return ProviderQueryOptions(**defaults)


# --- Claude adapter reasoning wiring ---


class TestClaudeReasoningConfig:
    @pytest.mark.asyncio
    async def test_no_reasoning_config(self) -> None:
        """When reasoning_config is None, no reasoning kwargs are passed."""
        sdk_options = await self._run_claude(reasoning_config=None)
        assert not hasattr(sdk_options, "thinking") or sdk_options.thinking is None
        assert not hasattr(sdk_options, "effort") or sdk_options.effort is None

    @pytest.mark.asyncio
    async def test_thinking_and_effort(self) -> None:
        """Recognized keys are forwarded to ClaudeAgentOptions."""
        reasoning = {"thinking": {"type": "enabled", "budget_tokens": 5000}, "effort": "high"}
        sdk_options = await self._run_claude(reasoning_config=reasoning)
        assert sdk_options.thinking == {"type": "enabled", "budget_tokens": 5000}
        assert sdk_options.effort == "high"

    @pytest.mark.asyncio
    async def test_all_keys_passed_through(self) -> None:
        """All reasoning_config keys are forwarded to ClaudeAgentOptions."""
        reasoning = {"unknown_key": "value", "effort": "low"}
        sdk_options = await self._run_claude(reasoning_config=reasoning)
        assert sdk_options.effort == "low"
        assert sdk_options.unknown_key == "value"

    @staticmethod
    async def _run_claude(reasoning_config=None):
        """Run ClaudeProvider.query() with a mock claude_agent_sdk."""
        captured_options = {}

        class FakeClaudeAgentOptions:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                captured_options["instance"] = self

        async def fake_query(*, prompt, options):  # noqa: ARG001
            return
            yield

        mock_sdk = ModuleType("claude_agent_sdk")
        mock_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
        mock_sdk.ResultMessage = type("ResultMessage", (), {})
        mock_sdk.AssistantMessage = type("AssistantMessage", (), {})
        mock_sdk.UserMessage = type("UserMessage", (), {})
        mock_sdk.StreamEvent = type("StreamEvent", (), {})
        mock_sdk.query = fake_query

        with patch.dict(sys.modules, {"claude_agent_sdk": mock_sdk}):
            # Force re-import to pick up mock
            if "lightspeed_agentic.providers.claude" in sys.modules:
                del sys.modules["lightspeed_agentic.providers.claude"]
            from lightspeed_agentic.providers.claude import ClaudeProvider

            provider = ClaudeProvider()
            options = _base_options(reasoning_config=reasoning_config)
            async for _ in provider.query(options):
                pass

        return captured_options["instance"]


class TestGeminiReasoningConfig:
    @pytest.mark.asyncio
    async def test_no_reasoning_config(self) -> None:
        """When reasoning_config is None, no ThinkingConfig is set."""
        gen_config = await self._run_gemini(reasoning_config=None)
        assert not hasattr(gen_config, "thinking_config") or gen_config.thinking_config is None

    @pytest.mark.asyncio
    async def test_thinking_config_keys(self) -> None:
        """Recognized keys are mapped to ThinkingConfig."""
        reasoning = {"thinking_budget": 2048, "include_thoughts": True}
        gen_config = await self._run_gemini(reasoning_config=reasoning)
        tc = gen_config.thinking_config
        assert tc is not None
        assert tc.thinking_budget == 2048
        assert tc.include_thoughts is True

    @pytest.mark.asyncio
    async def test_all_keys_passed_through(self) -> None:
        """All reasoning_config keys are forwarded to ThinkingConfig."""
        reasoning = {"unknown_param": "x", "thinking_budget": 1024}
        gen_config = await self._run_gemini(reasoning_config=reasoning)
        tc = gen_config.thinking_config
        assert tc.thinking_budget == 1024
        assert tc.unknown_param == "x"

    @staticmethod
    async def _run_gemini(reasoning_config=None):
        """Run GeminiProvider.query() and capture the GenerateContentConfig."""
        captured = {}

        class FakeThinkingConfig:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class FakeGenerateContentConfig:
            def __init__(self, **kwargs):
                self.thinking_config = kwargs.get("thinking_config")
                self.tool_config = kwargs.get("tool_config")
                captured["gen_config"] = self

        class FakeToolConfig:
            def __init__(self, **kwargs):
                pass

        class FakeContent:
            def __init__(self, **kwargs):
                pass

        class FakePart:
            def __init__(self, **kwargs):
                pass

        mock_types = MagicMock()
        mock_types.ThinkingConfig = FakeThinkingConfig
        mock_types.GenerateContentConfig = FakeGenerateContentConfig
        mock_types.ToolConfig = FakeToolConfig
        mock_types.Content = FakeContent
        mock_types.Part = FakePart

        mock_agent_cls = MagicMock()
        mock_runner = MagicMock()

        async def _empty_run(**_kwargs):
            return
            yield

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_async = _empty_run
        mock_runner.return_value = mock_runner_instance

        mock_session = MagicMock()
        mock_session.id = "sess-1"
        mock_session_service_cls = MagicMock()
        mock_session_service_cls.return_value.create_session = AsyncMock(return_value=mock_session)

        # Build the mock google.adk module tree
        google_mod = ModuleType("google")
        google_mod.__path__ = []  # type: ignore[attr-defined]
        genai_mod = ModuleType("google.genai")
        genai_mod.types = mock_types  # type: ignore[attr-defined]
        adk_mod = ModuleType("google.adk")
        adk_mod.__path__ = []  # type: ignore[attr-defined]
        agents_mod = ModuleType("google.adk.agents")
        agents_mod.Agent = mock_agent_cls  # type: ignore[attr-defined]
        agents_mod.RunConfig = MagicMock()  # type: ignore[attr-defined]
        run_config_mod = ModuleType("google.adk.agents.run_config")
        run_config_mod.StreamingMode = MagicMock(SSE="sse", NONE="none")  # type: ignore[attr-defined]
        runners_mod = ModuleType("google.adk.runners")
        runners_mod.Runner = mock_runner  # type: ignore[attr-defined]
        sessions_mod = ModuleType("google.adk.sessions")
        sessions_mod.InMemorySessionService = mock_session_service_cls  # type: ignore[attr-defined]
        tools_mod = ModuleType("google.adk.tools")
        tools_mod.exit_loop = MagicMock()  # type: ignore[attr-defined]
        tools_mod.google_search = MagicMock()  # type: ignore[attr-defined]
        tools_mod.url_context = MagicMock()  # type: ignore[attr-defined]
        bash_tool_mod = ModuleType("google.adk.tools.bash_tool")
        bash_tool_mod.ExecuteBashTool = MagicMock()  # type: ignore[attr-defined]
        tool_confirm_mod = ModuleType("google.adk.tools.tool_confirmation")
        tool_confirm_mod.ToolConfirmation = MagicMock()  # type: ignore[attr-defined]

        modules = {
            "google": google_mod,
            "google.genai": genai_mod,
            "google.adk": adk_mod,
            "google.adk.agents": agents_mod,
            "google.adk.agents.run_config": run_config_mod,
            "google.adk.runners": runners_mod,
            "google.adk.sessions": sessions_mod,
            "google.adk.tools": tools_mod,
            "google.adk.tools.bash_tool": bash_tool_mod,
            "google.adk.tools.tool_confirmation": tool_confirm_mod,
        }

        with patch.dict(sys.modules, modules):
            if "lightspeed_agentic.providers.gemini" in sys.modules:
                del sys.modules["lightspeed_agentic.providers.gemini"]
            from lightspeed_agentic.providers.gemini import GeminiProvider

            provider = GeminiProvider()
            options = _base_options(reasoning_config=reasoning_config)
            async for _ in provider.query(options):
                pass

        return captured["gen_config"]


class TestOpenAIReasoningConfig:
    @pytest.mark.asyncio
    async def test_no_reasoning_config(self) -> None:
        """When reasoning_config is None, no model_settings is passed."""
        agent_kwargs = await self._run_openai(reasoning_config=None)
        assert "model_settings" not in agent_kwargs

    @pytest.mark.asyncio
    async def test_reasoning_keys(self) -> None:
        """Recognized keys build ModelSettings with Reasoning."""
        reasoning = {"effort": "high", "mode": "chain_of_thought", "verbosity": "high"}
        agent_kwargs = await self._run_openai(reasoning_config=reasoning)
        ms = agent_kwargs["model_settings"]
        assert ms.reasoning.effort == "high"
        assert ms.reasoning.mode == "chain_of_thought"
        assert ms.verbosity == "high"

    @pytest.mark.asyncio
    async def test_all_keys_passed_through(self) -> None:
        """All non-verbosity keys are forwarded to Reasoning."""
        reasoning = {"effort": "low", "unknown_stuff": True}
        agent_kwargs = await self._run_openai(reasoning_config=reasoning)
        ms = agent_kwargs["model_settings"]
        assert ms.reasoning.effort == "low"
        assert ms.reasoning.unknown_stuff is True

    @staticmethod
    async def _run_openai(reasoning_config=None):
        """Run OpenAIProvider.query() with mocks and return the SandboxAgent kwargs."""
        from lightspeed_agentic.providers.openai import OpenAIProvider

        class FakeReasoning:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class FakeModelSettings:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        captured_kwargs = {}

        mock_result = MagicMock()

        async def _empty_events():
            return
            yield

        mock_result.stream_events = _empty_events
        mock_result.final_output = "done"
        mock_result.context_wrapper.usage.input_tokens = 10
        mock_result.context_wrapper.usage.output_tokens = 5

        def _capture_sandbox_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        mock_sandbox_agent_cls = MagicMock(side_effect=_capture_sandbox_agent)

        with (
            patch("agents.sandbox.SandboxAgent", mock_sandbox_agent_cls),
            patch("agents.Runner.run_streamed", return_value=mock_result),
            patch("agents.models.openai_responses.OpenAIResponsesModel", MagicMock()),
            patch("openai.AsyncOpenAI", MagicMock()),
            patch("agents.model_settings.ModelSettings", FakeModelSettings),
            patch("openai.types.shared.Reasoning", FakeReasoning),
        ):
            provider = OpenAIProvider()
            provider._client = MagicMock()
            options = _base_options(reasoning_config=reasoning_config)
            async for _ in provider.query(options):
                pass

        return captured_kwargs
