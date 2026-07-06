# -*- coding: utf-8 -*-
"""Tests for QwenPawAgent.compress_context.

These lock in the contract that automatic context compaction is routed
through QwenPaw's own (thinking-safe) ``LightContextManager.compact_context``
rather than agentscope's native ``generate_structured_output`` path, which
forces a ``tool_choice`` and is rejected by reasoning models in thinking mode.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from agentscope.agent import ContextConfig
from agentscope.message import Msg, TextBlock

from qwenpaw.agents.react_agent import QwenPawAgent


def _msg(text: str) -> Msg:
    return Msg(
        name="assistant",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
    )


class _FakeModel:
    """Minimal model stub exposing the bits compress_context touches."""

    context_size = 1000

    def __init__(self, tokens: int) -> None:
        self._tokens = tokens
        # If the override ever falls back to the native structured-output
        # path, this would be invoked — the tests assert it never is.
        self.generate_structured_output = AsyncMock()

    async def count_tokens(self, **_kwargs) -> int:
        return self._tokens


class _FakeContextManager:
    def __init__(self, result: dict) -> None:
        self._result = result
        self.calls: list[tuple[list[Msg], str]] = []

    async def compact_context(
        self,
        messages,
        previous_summary: str = "",
        extra_instruction: str = "",
    ) -> dict:
        self.calls.append((list(messages), previous_summary))
        return self._result

    def get_dialog_path(self):
        return None


def _agent(
    *,
    tokens: int,
    cm_result: dict,
    context: list[Msg],
    summary: str = "",
    split: tuple[list[Msg], list[Msg]] | None = None,
) -> tuple[QwenPawAgent, _FakeContextManager, _FakeModel]:
    agent = QwenPawAgent.__new__(QwenPawAgent)
    model = _FakeModel(tokens)
    cm = _FakeContextManager(cm_result)
    agent.model = model
    agent.context_manager = cm
    agent.context_config = ContextConfig()  # trigger 0.8, reserve 0.1
    agent.name = "TestAgent"
    agent.state = SimpleNamespace(context=list(context), summary=summary)
    agent._prepare_model_input = AsyncMock(return_value={"tools": []})
    agent._split_context_for_compression = AsyncMock(
        return_value=split if split is not None else ([], list(context)),
    )
    return agent, cm, model


async def test_skips_when_below_threshold():
    ctx = [_msg("a"), _msg("b")]
    # 100 < 0.8 * 1000 → no compaction at all.
    agent, cm, model = _agent(tokens=100, cm_result={}, context=ctx)

    await agent.compress_context()

    assert cm.calls == []
    agent._split_context_for_compression.assert_not_awaited()
    model.generate_structured_output.assert_not_awaited()
    assert [m.get_text_content() for m in agent.state.context] == ["a", "b"]


async def test_compacts_via_qwenpaw_compactor_on_success():
    m1, m2, m3 = _msg("old1"), _msg("old2"), _msg("recent")
    agent, cm, model = _agent(
        tokens=900,  # >= 800 threshold
        cm_result={"success": True, "history_compact": "## Summary\nrolled up"},
        context=[m1, m2, m3],
        summary="prev",
        split=([m1, m2], [m3]),
    )

    await agent.compress_context()

    # Routed through QwenPaw compactor, never the structured-output path.
    assert len(cm.calls) == 1
    compacted_msgs, prev_summary = cm.calls[0]
    assert [m.get_text_content() for m in compacted_msgs] == ["old1", "old2"]
    assert prev_summary == "prev"
    model.generate_structured_output.assert_not_awaited()

    # Summary replaced, context trimmed to the reserved tail.
    assert agent.state.summary == "## Summary\nrolled up"
    assert [m.get_text_content() for m in agent.state.context] == ["recent"]


async def test_trims_but_keeps_summary_when_compaction_returns_failure():
    m1, m2, m3 = _msg("old1"), _msg("old2"), _msg("recent")
    agent, cm, _model = _agent(
        tokens=900,
        cm_result={"success": False, "reason": "empty summary",
                   "history_compact": ""},
        context=[m1, m2, m3],
        summary="prev",
        split=([m1, m2], [m3]),
    )

    await agent.compress_context()

    # Context still trimmed to relieve pressure; previous summary preserved.
    assert [m.get_text_content() for m in agent.state.context] == ["recent"]
    assert agent.state.summary == "prev"


async def test_does_not_crash_when_compactor_raises():
    m1, m2, m3 = _msg("old1"), _msg("old2"), _msg("recent")
    agent, cm, _model = _agent(
        tokens=900,
        cm_result={},
        context=[m1, m2, m3],
        summary="prev",
        split=([m1, m2], [m3]),
    )
    cm.compact_context = AsyncMock(side_effect=RuntimeError("llm boom"))

    # Must swallow the error rather than aborting the reply stream.
    await agent.compress_context()

    # Failure happened before trimming → context left intact.
    assert len(agent.state.context) == 3
    assert agent.state.summary == "prev"
