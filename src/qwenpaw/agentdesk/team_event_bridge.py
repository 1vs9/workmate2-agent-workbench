# -*- coding: utf-8 -*-
"""Map native QwenPaw team delegation events into AgentDesk SSE shape."""

from __future__ import annotations

import json
from typing import Any

from .agents import resolve_agent_id

NATIVE_DELEGATION_TOOLS = frozenset({"chat_with_agent"})


def json_or_empty(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class NativeTeamEventBridge:
    """Map sync ``chat_with_agent`` delegation into AgentDesk team UI events."""

    def __init__(self, *, members: list[str], leader_sender: str) -> None:
        self._leader_sender = leader_sender
        self._member_lookup: dict[str, str] = {}
        for name in members:
            normalized = str(name or "").strip()
            if not normalized:
                continue
            self._member_lookup[normalized.lower()] = normalized
            try:
                agent_id = resolve_agent_id(normalized)
                self._member_lookup[agent_id.lower()] = normalized
                from ..config.config import load_agent_config

                cfg = load_agent_config(agent_id)
                display = str(cfg.name or "").strip()
                if display:
                    self._member_lookup[display.lower()] = normalized
            except Exception:
                continue
        self._call_actor: dict[str, str] = {}
        self._started_calls: set[str] = set()
        self._call_id_by_actor: dict[str, str] = {}
        self._worker_result_seen = False
        self._synthesizing_emitted = False
        self._timed_out_workers: list[str] = []

    def _resolve_actor(self, target: str) -> str:
        normalized = str(target or "").strip()
        if not normalized:
            return ""
        return self._member_lookup.get(normalized.lower(), normalized)

    def _arguments_from_event(self, evt: dict[str, Any]) -> dict[str, Any]:
        args = evt.get("tool_arguments")
        if isinstance(args, dict):
            return args
        detail_dict = json_or_empty(evt.get("detail"))
        if isinstance(detail_dict.get("arguments"), dict):
            return detail_dict["arguments"]
        return detail_dict

    def _worker_start_event(self, actor: str, call_id: str) -> dict[str, Any]:
        return {
            "type": "worker_start",
            "worker": actor,
            "actor_id": actor,
            "delegation_id": call_id,
            "source_member": actor,
        }

    def _worker_done_event(self, actor: str, call_id: str) -> dict[str, Any]:
        return {
            "type": "worker_done",
            "worker": actor,
            "actor_id": actor,
            "delegation_id": call_id,
            "source_member": actor,
        }

    def _synthesizing_event(self) -> dict[str, Any]:
        return {
            "type": "team_phase",
            "phase": "synthesizing",
            "label": f"{self._leader_sender} 正在汇总…",
            "source_member": self._leader_sender,
        }

    def _emit_worker_start_if_possible(
        self,
        extras: list[dict[str, Any]],
        *,
        call_id: str,
        evt: dict[str, Any],
    ) -> None:
        if not call_id or call_id in self._started_calls:
            return
        args = self._arguments_from_event(evt)
        actor = self._resolve_actor(str(args.get("to_agent") or args.get("agent_id") or ""))
        if not actor:
            return
        self._call_actor[call_id] = actor
        self._started_calls.add(call_id)
        extras.append(self._worker_start_event(actor, call_id))

    def map_event(self, evt: dict[str, Any]) -> list[dict[str, Any]]:
        evt_type = str(evt.get("type") or "")
        mapped: list[dict[str, Any]] = []

        if (
            self._worker_result_seen
            and not self._synthesizing_emitted
            and evt_type in {"text_delta", "message", "thinking_start", "thinking_delta"}
        ):
            self._synthesizing_emitted = True
            mapped.append(self._synthesizing_event())

        mapped.append(evt)
        tool_name = str(evt.get("tool_name") or "").strip()
        call_id = str(evt.get("tool_call_id") or "").strip()

        if tool_name in NATIVE_DELEGATION_TOOLS and evt_type in {"tool_call_start", "tool_call_end"}:
            self._emit_worker_start_if_possible(mapped, call_id=call_id, evt=evt)
            if evt_type == "tool_call_end":
                args = self._arguments_from_event(evt)
                actor = self._resolve_actor(
                    str(args.get("to_agent") or args.get("agent_id") or ""),
                )
                if actor:
                    evt["member_name"] = actor

        if tool_name in NATIVE_DELEGATION_TOOLS and evt_type == "tool_result_end" and call_id:
            actor = self._call_actor.get(call_id, "")
            if not actor:
                args = self._arguments_from_event(evt)
                actor = self._resolve_actor(str(args.get("to_agent") or args.get("agent_id") or ""))
                if actor:
                    self._call_actor[call_id] = actor
            if actor and call_id not in self._started_calls:
                self._started_calls.add(call_id)
                mapped.append(self._worker_start_event(actor, call_id))
            if actor:
                mapped.append(self._worker_done_event(actor, call_id))
                self._worker_result_seen = True
                self._call_id_by_actor[actor] = call_id
                self._call_actor.pop(call_id, None)
        return mapped

    def worker_results_seen(self) -> bool:
        return self._worker_result_seen

    def emit_worker_done_from_bus(self, actor: str) -> list[dict[str, Any]]:
        """Bus DONE sentinel: emit worker_done when worker stream ends."""
        normalized = self._resolve_actor(actor) or str(actor or "").strip()
        if not normalized:
            return []
        call_id = self._call_id_by_actor.get(normalized, "")
        if not call_id:
            for cid, act in list(self._call_actor.items()):
                resolved = self._resolve_actor(act) or act
                if resolved == normalized or act == normalized:
                    call_id = cid
                    self._call_actor.pop(cid, None)
                    break
        if not call_id:
            return []
        self._call_id_by_actor.pop(normalized, None)
        self._worker_result_seen = True
        return [self._worker_done_event(normalized, call_id)]

    def reset_round_activity_flags(self) -> None:
        self._worker_result_seen = False
        self._synthesizing_emitted = False

    def timed_out_workers(self) -> list[str]:
        return list(self._timed_out_workers)


# Back-compat alias for tests and internal imports.
_NativeTeamEventBridge = NativeTeamEventBridge
