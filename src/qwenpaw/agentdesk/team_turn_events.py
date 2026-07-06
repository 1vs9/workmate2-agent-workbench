# -*- coding: utf-8 -*-
"""Team-turn AgentDesk event builders."""

from __future__ import annotations

from typing import Any


def tag_leader_trace_event(mapped_evt: dict[str, Any], *, sender: str) -> dict[str, Any]:
    """Keep leader-stream trace steps on the leader bubble."""
    tagged = dict(mapped_evt)
    tagged["sender"] = str(tagged.get("sender") or sender)
    tagged.setdefault("actor_id", sender)
    tagged.setdefault("source_member", sender)
    return tagged


def timed_out_members_label(members: list[str]) -> str:
    return "Timed out members: " + ", ".join(members)


def team_done_label(team_name: str, *, timed_out: bool) -> str:
    if timed_out:
        return f"{team_name} 路 鍥㈤槦鍝嶅簲瀹屾垚锛堥儴鍒嗘垚鍛樿秴鏃讹級"
    return f"{team_name} 路 鍥㈤槦鍝嶅簲瀹屾垚"


def team_done_phase_event(
    *,
    team_name: str,
    leader_sender: str,
    timed_out: bool,
) -> dict[str, Any]:
    return {
        "type": "team_phase",
        "phase": "done",
        "label": team_done_label(team_name, timed_out=timed_out),
        "source_member": leader_sender,
    }


def reply_end_event(
    *,
    leader_sender: str,
    leader_message_id: str | None,
) -> dict[str, Any]:
    return {
        "type": "reply_end",
        "label": "鏈疆鍥炲缁撴潫",
        "sender": leader_sender,
        "message_id": str(leader_message_id or ""),
    }
