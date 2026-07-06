# -*- coding: utf-8 -*-
"""Tests for ReAct auto-continue guardrails."""

from types import SimpleNamespace

from agentscope.message import Msg, TextBlock

from qwenpaw.agents.react_agent import QwenPawAgent


def _assistant_msg(text: str) -> Msg:
    return Msg(
        name="assistant",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
    )


def _auto_continue_agent(*, hint_count: int = 0) -> QwenPawAgent:
    agent = QwenPawAgent.__new__(QwenPawAgent)
    hints = [
        Msg(
            name="user",
            role="user",
            content=[
                TextBlock(
                    type="text",
                    text="<system-hint>上轮助手仅文字、未调工具。</system-hint>",
                ),
            ],
        )
        for _ in range(hint_count)
    ]
    agent.state = SimpleNamespace(cur_iter=1, context=[*hints])
    agent.react_config = SimpleNamespace(max_iters=100)
    agent._agent_config = SimpleNamespace(
        running=SimpleNamespace(auto_continue_on_text_only=True),
    )
    return agent


def test_looks_like_task_completion_matches_common_phrases():
    assert QwenPawAgent._looks_like_task_completion(
        _assistant_msg("任务已完成，等待你的新任务。"),
    )
    assert QwenPawAgent._looks_like_task_completion(
        _assistant_msg("任务已完结。"),
    )
    assert QwenPawAgent._looks_like_task_completion(
        _assistant_msg("Task is complete. Let me know if you need anything else."),
    )


def test_looks_like_task_completion_ignores_in_progress_updates():
    assert not QwenPawAgent._looks_like_task_completion(
        _assistant_msg("接下来我将读取 README 并开始生成 PPT 大纲。"),
    )
    assert not QwenPawAgent._looks_like_task_completion(
        _assistant_msg(""),
    )


def test_should_not_auto_continue_on_completion_phrase():
    agent = _auto_continue_agent()
    assert agent._should_auto_continue(
        _assistant_msg("任务已完成，等待你的新任务。"),
        "auto",
    ) is False


def test_should_auto_continue_on_planning_text():
    agent = _auto_continue_agent()
    assert agent._should_auto_continue(
        _assistant_msg("接下来我将调用工具生成幻灯片。"),
        "auto",
    ) is True


def test_should_not_auto_continue_on_greeting_reply():
    agent = _auto_continue_agent()
    assert agent._should_auto_continue(
        _assistant_msg("你好！我是 AgentDesk 企伴，有什么可以帮你的？"),
        "auto",
    ) is False


def test_should_not_auto_continue_on_casual_user_turn():
    agent = _auto_continue_agent()
    agent.state.context.append(
        Msg(
            name="user",
            role="user",
            content=[TextBlock(type="text", text="你好")],
        ),
    )
    assert agent._should_auto_continue(
        _assistant_msg("接下来我将调用工具生成幻灯片。"),
        "auto",
    ) is False


def test_should_not_auto_continue_after_max_extra_hints():
    agent = _auto_continue_agent(hint_count=2)
    assert agent._should_auto_continue(
        _assistant_msg("接下来我将调用工具生成幻灯片。"),
        "auto",
    ) is False
