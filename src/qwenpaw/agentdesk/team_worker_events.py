# -*- coding: utf-8 -*-
"""Worker stream event helpers for AgentDesk team mode."""

from __future__ import annotations

from typing import Any, Callable

from .team_sessions import team_member_session_id


def resolve_worker_display_name(
    agent_id: str,
    *,
    cache: dict[str, str],
    load_agent_config: Callable[[str], Any] | None = None,
) -> str:
    """Resolve a worker display name from agent config, with caller-owned cache."""
    aid = str(agent_id or "").strip()
    if not aid:
        return ""
    cached = cache.get(aid)
    if cached is not None:
        return cached
    name = aid
    try:
        if load_agent_config is None:
            from ..config.config import load_agent_config as _load_agent_config

            load_agent_config = _load_agent_config
        cfg = load_agent_config(aid)
        if (cfg.name or "").strip():
            name = cfg.name.strip()
    except Exception:  # noqa: BLE001 - fall back to the raw id
        name = aid
    cache[aid] = name
    return name


def tag_worker_event(
    evt: dict[str, Any],
    *,
    actor: str,
    task_id: str,
    worker_message_ids: dict[str, str],
) -> dict[str, Any]:
    """Attach stable AgentDesk team-worker routing fields to an event."""
    tagged = dict(evt)
    tagged["sender"] = actor
    tagged["actor_id"] = actor
    tagged["source_member"] = actor
    tagged["sessionId"] = team_member_session_id(task_id, actor)
    worker_msg_id = worker_message_ids.get(actor)
    if worker_msg_id and not str(tagged.get("message_id") or "").strip():
        tagged["message_id"] = worker_msg_id
    return tagged


def worker_final_text(
    actor: str,
    *,
    translators: dict[str, Any],
    display_name_for: Callable[[str], str],
    resolve_actor: Callable[[str], str | None] | None = None,
) -> str:
    """Best accumulated clean reply text for *actor* across worker streams."""
    best = ""
    for src_agent_id, translator in translators.items():
        resolved = display_name_for(src_agent_id)
        if resolve_actor is not None:
            resolved = (
                resolve_actor(str(src_agent_id))
                or resolve_actor(resolved)
                or resolved
            )
        if resolved != actor:
            continue
        text = translator.final_text()
        if text and len(text) > len(best):
            best = text
    return best


def worker_source_ids_for_actor(
    actor: str,
    *,
    translators: dict[str, Any],
    display_name_for: Callable[[str], str],
    resolve_actor: Callable[[str], str | None] | None = None,
) -> list[str]:
    """Return translator source ids currently associated with *actor*."""
    matched: list[str] = []
    for src_agent_id in translators:
        if display_name_for(src_agent_id) == actor:
            matched.append(src_agent_id)
            continue
        if resolve_actor is not None and resolve_actor(src_agent_id) == actor:
            matched.append(src_agent_id)
    return matched


def discard_worker_stream_state(
    actor: str,
    *,
    translators: dict[str, Any],
    had_content: set[str],
    streamed_text: set[str],
    display_name_for: Callable[[str], str],
    resolve_actor: Callable[[str], str | None] | None = None,
) -> None:
    """Forget per-worker streaming state after that worker has finished."""
    for src_agent_id in worker_source_ids_for_actor(
        actor,
        translators=translators,
        display_name_for=display_name_for,
        resolve_actor=resolve_actor,
    ):
        translators.pop(src_agent_id, None)
    had_content.discard(actor)
    streamed_text.discard(actor)


def finalized_worker_trace_events(
    *,
    translators: dict[str, Any],
    display_name_for: Callable[[str], str],
    tag_event: Callable[[dict[str, Any], str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Finalize pending tool/thinking trace events for active worker translators."""
    events: list[dict[str, Any]] = []
    for src_agent_id, translator in translators.items():
        actor = display_name_for(src_agent_id)
        if not actor:
            continue
        for tail_evt in [
            *translator.finalize_pending_tools(),
            *translator.finalize_pending_thinking(),
        ]:
            events.append(tag_event(tail_evt, actor))
    return events


def leftover_worker_bubbles(
    *,
    worker_message_ids: dict[str, str],
    had_content: set[str],
    final_text_for: Callable[[str], str],
) -> list[tuple[str, str, str]]:
    """Return worker bubbles that should be finalized at stream shutdown."""
    bubbles: list[tuple[str, str, str]] = []
    for actor, message_id in list(worker_message_ids.items()):
        if not message_id:
            continue
        if actor not in had_content:
            continue
        bubbles.append((actor, message_id, final_text_for(actor)))
    return bubbles
