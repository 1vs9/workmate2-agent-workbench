# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.team_turn_events import (
    reply_end_event,
    tag_leader_trace_event,
    team_done_label,
    team_done_phase_event,
    timed_out_members_label,
)


def test_tag_leader_trace_event_sets_missing_leader_fields() -> None:
    tagged = tag_leader_trace_event({"type": "tool_call_start"}, sender="Leader")

    assert tagged == {
        "type": "tool_call_start",
        "sender": "Leader",
        "actor_id": "Leader",
        "source_member": "Leader",
    }


def test_tag_leader_trace_event_keeps_existing_sender() -> None:
    tagged = tag_leader_trace_event(
        {"type": "tool_call_start", "sender": "Custom"},
        sender="Leader",
    )

    assert tagged["sender"] == "Custom"
    assert tagged["actor_id"] == "Leader"
    assert tagged["source_member"] == "Leader"


def test_timed_out_members_label_joins_members() -> None:
    assert timed_out_members_label(["Writer", "Reviewer"]) == (
        "Timed out members: Writer, Reviewer"
    )


def test_team_done_phase_event_contains_team_source_member() -> None:
    event = team_done_phase_event(
        team_name="Alpha",
        leader_sender="Leader",
        timed_out=False,
    )

    assert event["type"] == "team_phase"
    assert event["phase"] == "done"
    assert event["label"] == team_done_label("Alpha", timed_out=False)
    assert event["source_member"] == "Leader"


def test_team_done_label_changes_when_timed_out() -> None:
    normal = team_done_label("Alpha", timed_out=False)
    timeout = team_done_label("Alpha", timed_out=True)

    assert normal != timeout
    assert "Alpha" in normal
    assert "Alpha" in timeout


def test_reply_end_event_stringifies_missing_message_id() -> None:
    assert reply_end_event(leader_sender="Leader", leader_message_id=None) == {
        "type": "reply_end",
        "label": "鏈疆鍥炲缁撴潫",
        "sender": "Leader",
        "message_id": "",
    }
