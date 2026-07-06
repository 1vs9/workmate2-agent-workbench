# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk.team_worker_events import (
    discard_worker_stream_state,
    finalized_worker_trace_events,
    leftover_worker_bubbles,
    resolve_worker_display_name,
    tag_worker_event,
    worker_final_text,
    worker_source_ids_for_actor,
)


class _Translator:
    def __init__(
        self,
        text: str,
        *,
        tool_events: list[dict[str, object]] | None = None,
        thinking_events: list[dict[str, object]] | None = None,
    ) -> None:
        self._text = text
        self._tool_events = tool_events or []
        self._thinking_events = thinking_events or []

    def final_text(self) -> str:
        return self._text

    def finalize_pending_tools(self) -> list[dict[str, object]]:
        return self._tool_events

    def finalize_pending_thinking(self) -> list[dict[str, object]]:
        return self._thinking_events


def test_resolve_worker_display_name_uses_config_name_and_cache() -> None:
    calls: list[str] = []

    def _load(agent_id: str) -> SimpleNamespace:
        calls.append(agent_id)
        return SimpleNamespace(name="Researcher")

    cache: dict[str, str] = {}

    assert resolve_worker_display_name(
        "agent-1",
        cache=cache,
        load_agent_config=_load,
    ) == "Researcher"
    assert resolve_worker_display_name(
        "agent-1",
        cache=cache,
        load_agent_config=_load,
    ) == "Researcher"
    assert calls == ["agent-1"]


def test_resolve_worker_display_name_falls_back_to_agent_id() -> None:
    def _load(agent_id: str) -> SimpleNamespace:
        raise RuntimeError("missing")

    assert resolve_worker_display_name(
        "agent-1",
        cache={},
        load_agent_config=_load,
    ) == "agent-1"


def test_tag_worker_event_sets_actor_session_and_message_id() -> None:
    tagged = tag_worker_event(
        {"type": "text_delta", "content": "hi"},
        actor="Writer",
        task_id="task-1",
        worker_message_ids={"Writer": "msg-1"},
    )

    assert tagged["sender"] == "Writer"
    assert tagged["actor_id"] == "Writer"
    assert tagged["source_member"] == "Writer"
    assert tagged["sessionId"] == "task-1:team:member:Writer"
    assert tagged["message_id"] == "msg-1"


def test_tag_worker_event_keeps_existing_message_id() -> None:
    tagged = tag_worker_event(
        {"type": "text_delta", "message_id": "existing"},
        actor="Writer",
        task_id="task-1",
        worker_message_ids={"Writer": "msg-1"},
    )

    assert tagged["message_id"] == "existing"


def test_worker_final_text_picks_longest_matching_actor_text() -> None:
    translators = {
        "agent-short": _Translator("short"),
        "agent-long": _Translator("much longer"),
        "agent-other": _Translator("ignored even if longer"),
    }
    display_names = {
        "agent-short": "Writer",
        "agent-long": "Writer",
        "agent-other": "Reviewer",
    }

    assert worker_final_text(
        "Writer",
        translators=translators,
        display_name_for=lambda agent_id: display_names[agent_id],
    ) == "much longer"


def test_worker_final_text_uses_resolve_actor_mapping() -> None:
    translators = {"agent-1": _Translator("mapped reply")}

    assert worker_final_text(
        "Writer",
        translators=translators,
        display_name_for=lambda agent_id: "raw-name",
        resolve_actor=lambda value: "Writer" if value == "agent-1" else None,
    ) == "mapped reply"


def test_worker_source_ids_for_actor_matches_display_name_and_actor_mapping() -> None:
    translators = {
        "agent-display": _Translator("display"),
        "agent-mapped": _Translator("mapped"),
        "agent-other": _Translator("other"),
    }

    assert worker_source_ids_for_actor(
        "Writer",
        translators=translators,
        display_name_for=lambda agent_id: "Writer" if agent_id == "agent-display" else "Raw",
        resolve_actor=lambda value: "Writer" if value == "agent-mapped" else None,
    ) == ["agent-display", "agent-mapped"]


def test_discard_worker_stream_state_removes_matching_translators_and_flags() -> None:
    translators = {
        "agent-display": _Translator("display"),
        "agent-mapped": _Translator("mapped"),
        "agent-other": _Translator("other"),
    }
    had_content = {"Writer", "Reviewer"}
    streamed_text = {"Writer", "Reviewer"}

    discard_worker_stream_state(
        "Writer",
        translators=translators,
        had_content=had_content,
        streamed_text=streamed_text,
        display_name_for=lambda agent_id: "Writer" if agent_id == "agent-display" else "Raw",
        resolve_actor=lambda value: "Writer" if value == "agent-mapped" else None,
    )

    assert translators == {"agent-other": translators["agent-other"]}
    assert had_content == {"Reviewer"}
    assert streamed_text == {"Reviewer"}


def test_finalized_worker_trace_events_tags_pending_translator_events() -> None:
    translators = {
        "agent-1": _Translator(
            "",
            tool_events=[{"type": "tool_call_end"}],
            thinking_events=[{"type": "thinking_end"}],
        ),
        "agent-2": _Translator("", tool_events=[{"type": "ignored"}]),
    }

    events = finalized_worker_trace_events(
        translators=translators,
        display_name_for=lambda agent_id: "Writer" if agent_id == "agent-1" else "",
        tag_event=lambda evt, actor: {**evt, "sender": actor},
    )

    assert events == [
        {"type": "tool_call_end", "sender": "Writer"},
        {"type": "thinking_end", "sender": "Writer"},
    ]


def test_leftover_worker_bubbles_selects_only_bubbles_with_content() -> None:
    bubbles = leftover_worker_bubbles(
        worker_message_ids={"Writer": "msg-1", "Empty": "msg-2", "Missing": ""},
        had_content={"Writer", "Missing"},
        final_text_for=lambda actor: f"final:{actor}",
    )

    assert bubbles == [("Writer", "msg-1", "final:Writer")]
