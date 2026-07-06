# -*- coding: utf-8 -*-
"""Append-only team conversation timeline — canonical ordering for team UI."""

from __future__ import annotations

import json
import re
import time
from typing import Any

DELEGATION_TOOLS = frozenset({"chat_with_agent", "submit_to_agent"})

TIMELINE_KINDS = frozenset(
    {
        "user_message",
        "leader_text",
        "delegation",
        "worker_text",
        "worker_trace",
        "phase",
        "round_boundary",
    },
)

_TRACE_KINDS = frozenset(
    {
        "reply_start",
        "reply_end",
        "skills_active",
        "info",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "thinking_retract",
        "tool_call_start",
        "tool_call_end",
        "tool_result_start",
        "tool_result_delta",
        "tool_result_end",
    },
)


def _now_ts() -> float:
    return time.time()


def build_timeline_entry(
    kind: str,
    actor: str,
    *,
    round_id: str,
    seq: int,
    target: str | None = None,
    text: str = "",
    phase: str | None = None,
    label: str | None = None,
    message_id: str | None = None,
    delegation_id: str | None = None,
    trace: dict[str, Any] | None = None,
    delta: bool = False,
) -> dict[str, Any]:
    """Build a timeline entry payload (not yet persisted)."""
    entry: dict[str, Any] = {
        "kind": kind,
        "actor": actor.strip(),
        "seq": seq,
        "ts": _now_ts(),
        "round_id": round_id,
    }
    if target:
        entry["target"] = target.strip()
    if text:
        entry["text"] = text
    if phase:
        entry["phase"] = phase
    if label:
        entry["label"] = label
    if message_id:
        entry["message_id"] = message_id
    if delegation_id:
        entry["delegation_id"] = delegation_id
    if trace:
        entry["trace"] = dict(trace)
    if delta:
        entry["delta"] = True
    return entry


def _parse_detail(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _arguments_from_event(evt: dict[str, Any]) -> dict[str, Any]:
    detail = _parse_detail(evt.get("detail"))
    args = detail.get("arguments")
    if isinstance(args, dict):
        return args
    tool_args = evt.get("tool_arguments")
    if isinstance(tool_args, dict):
        return tool_args
    if isinstance(tool_args, str) and tool_args.strip():
        try:
            parsed = json.loads(tool_args)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return detail


_WORKER_STATUS_RE = re.compile(
    r"^(?P<worker>[\u4e00-\u9fffA-Za-z0-9·_-]+?)(正在|已经|还在|终于|已)(?P<rest>.+)$",
)

_STATUS_HINTS = ("正在", "还在", "进行中", "搜索", "分析", "汇总", "等待")
_KNOWN_ROSTER_TOKENS = ("研究员", "写手", "规划者", "审查官", "主笔", "分析师")
_PROGRESS_HEADER_RE = re.compile(
    r"(本轮进度|当前进度|团队进度|协调进度|进度[：:])",
)
_AT_MENTION_RE = re.compile(r"@[\u4e00-\u9fffA-Za-z0-9·_-]+")
_PROGRESS_MARKERS = ("已派工", "收到任务", "开始检索", "地毯式", "成稿")
_SUBSTANTIVE_MIN_LEN = 220
_SUBSTANTIVE_MARKERS = (
    "综览",
    "总结",
    "报告",
    "全文",
    "全流程回顾",
    "最终成果",
    "事件清单",
    "一周大事件",
    "结构化长文",
)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,3}\s", re.MULTILINE)


def _is_substantive_leader_answer(text: str) -> bool:
    """Long-form leader synthesis must not be misclassified as orchestration phase."""
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) >= 400:
        return True
    if _MARKDOWN_HEADING_RE.search(stripped):
        return True
    if len(stripped) >= _SUBSTANTIVE_MIN_LEN and any(
        marker in stripped for marker in _SUBSTANTIVE_MARKERS
    ):
        return True
    if "全流程回顾" in stripped and len(stripped) >= 100:
        return True
    return False


def merge_stream_text_delta(existing: str, incoming: str) -> str:
    """Merge streamed text chunks; treat cumulative rewrites as replace, not append."""
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming.startswith(existing) and len(incoming) > len(existing):
        return incoming
    if existing.startswith(incoming) and len(existing) > len(incoming):
        suffix = existing[len(incoming):]
        if suffix == incoming or (incoming and suffix.startswith(incoming)):
            return f"{existing}{incoming}"
        return existing
    if _PROGRESS_HEADER_RE.search(existing) and _PROGRESS_HEADER_RE.search(incoming):
        return incoming if len(incoming) >= len(existing) else existing
    if incoming == existing and len(incoming) > 1:
        return existing
    return f"{existing}{incoming}"


def _first_roster_token(text: str) -> str | None:
    for match in _AT_MENTION_RE.finditer(text):
        mention = match.group(0)[1:].strip()
        for token in _KNOWN_ROSTER_TOKENS:
            if mention == token or token in mention:
                return token
    for token in _KNOWN_ROSTER_TOKENS:
        if token in text:
            return token
    return None


def classify_leader_narration(text: str) -> tuple[str, str | None]:
    """Return ``(timeline_kind, worker_target)`` for leader-side narration."""
    stripped = text.strip()
    if not stripped:
        return "leader_text", None
    if _is_substantive_leader_answer(stripped):
        return "leader_text", None
    match = _WORKER_STATUS_RE.match(stripped)
    if match:
        return "phase", match.group("worker")
    if _PROGRESS_HEADER_RE.search(stripped):
        roster_hits = sum(1 for token in _KNOWN_ROSTER_TOKENS if token in stripped)
        if roster_hits >= 2 or len(_AT_MENTION_RE.findall(stripped)) >= 2:
            return "phase", None
        return "phase", _first_roster_token(stripped)
    at_count = len(_AT_MENTION_RE.findall(stripped))
    roster_hits = sum(1 for token in _KNOWN_ROSTER_TOKENS if token in stripped)
    if at_count >= 1 and roster_hits >= 2:
        return "phase", None
    if roster_hits >= 2 and any(marker in stripped for marker in _PROGRESS_MARKERS):
        return "phase", None
    if len(stripped) <= 160 and any(h in stripped for h in _STATUS_HINTS):
        for token in _KNOWN_ROSTER_TOKENS:
            if token in stripped:
                return "phase", token
    return "leader_text", None


def filter_leader_persist_text(text: str) -> str:
    """Drop orchestration status narration from text persisted on the leader bubble."""
    stripped = text.strip()
    if not stripped:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]
    if not paragraphs:
        kind, _ = classify_leader_narration(stripped)
        return "" if kind == "phase" else stripped
    kept = [
        paragraph
        for paragraph in paragraphs
        if classify_leader_narration(paragraph)[0] != "phase"
    ]
    return "\n\n".join(kept).strip()


class TeamTimelineWriter:
    """Builds monotonic timeline entries for one team chat round."""

    def __init__(self, *, round_id: str, leader_sender: str) -> None:
        self._round_id = round_id
        self._leader_sender = leader_sender
        self._next_seq = 0
        self._seen_delegations: set[str] = set()
        self._active_workers: set[str] = set()
        self._leader_answer_parts: list[str] = []

    def user_message_entry(self, text: str) -> dict[str, Any]:
        return self._next_entry("user_message", "user", text=text.strip())

    def leader_answer_text(self) -> str:
        """Concatenated leader reply text excluding orchestration status narration."""
        return "".join(self._leader_answer_parts).strip()

    def _record_leader_answer(self, content: str, *, delta: bool) -> None:
        if not content:
            return
        prev = self.leader_answer_text()
        merged = merge_stream_text_delta(prev, content) if delta else content
        self._leader_answer_parts = [merged] if merged else []

    def _leader_text_entry(
        self,
        content: str,
        *,
        leader_message_id: str | None,
        delta: bool,
    ) -> dict[str, Any]:
        kind, target = classify_leader_narration(content)
        if kind == "phase":
            return self._next_entry(
                "phase",
                self._leader_sender,
                target=target,
                phase="worker_status" if target else "round_progress",
                label=content,
                message_id=leader_message_id,
            )
        self._record_leader_answer(content, delta=delta)
        return self._next_entry(
            "leader_text",
            self._leader_sender,
            text=content,
            message_id=leader_message_id,
            delta=delta,
        )

    def _next_entry(
        self,
        kind: str,
        actor: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entry = build_timeline_entry(
            kind,
            actor,
            round_id=self._round_id,
            seq=self._next_seq,
            **kwargs,
        )
        self._next_seq += 1
        return entry

    def entry_from_mapped_event(
        self,
        evt: dict[str, Any],
        *,
        leader_message_id: str | None = None,
        worker_message_ids: dict[str, str] | None = None,
        resolve_actor: Any = None,
    ) -> dict[str, Any] | None:
        """Map a team SSE payload to a timeline entry, if applicable."""
        evt_type = str(evt.get("type") or "")
        sender = str(evt.get("sender") or evt.get("actor_id") or "").strip()
        worker_message_ids = worker_message_ids or {}

        if evt_type == "team_phase":
            phase = str(evt.get("phase") or "").strip()
            label = str(evt.get("label") or "").strip()
            return self._next_entry(
                "phase",
                self._leader_sender,
                phase=phase or "unknown",
                label=label or None,
            )

        if evt_type == "worker_start":
            worker = str(evt.get("worker") or evt.get("sender") or "").strip()
            delegation_id = str(evt.get("delegation_id") or "").strip() or None
            if worker:
                self._active_workers.add(worker)
            return self._next_entry(
                "phase",
                self._leader_sender,
                target=worker or None,
                phase="worker_started",
                delegation_id=delegation_id,
                label=f"{worker} 开始执行" if worker else None,
            )

        if evt_type == "worker_done":
            worker = str(evt.get("worker") or evt.get("sender") or "").strip()
            if worker:
                self._active_workers.discard(worker)
            return self._next_entry(
                "phase",
                self._leader_sender,
                target=worker or None,
                phase="worker_done",
                label=f"{worker} 已完成" if worker else None,
            )

        if evt_type == "content_reset":
            self._leader_answer_parts.clear()
            return self._next_entry(
                "round_boundary",
                self._leader_sender,
                message_id=leader_message_id,
            )

        if evt_type == "text_delta":
            content = str(evt.get("content") or "")
            if not content.strip():
                return None
            if sender == self._leader_sender or not sender:
                return self._leader_text_entry(
                    content,
                    leader_message_id=leader_message_id,
                    delta=True,
                )
            return self._next_entry(
                "worker_text",
                sender,
                text=content,
                message_id=worker_message_ids.get(sender),
                delta=True,
            )

        if evt_type == "message":
            content = str(evt.get("content") or "")
            if not content.strip():
                return None
            if sender == self._leader_sender or not sender:
                return self._leader_text_entry(
                    content,
                    leader_message_id=leader_message_id,
                    delta=False,
                )
            return self._next_entry(
                "worker_text",
                sender,
                text=content,
                message_id=worker_message_ids.get(sender),
            )

        tool_name = str(evt.get("tool_name") or "").strip()
        if tool_name in DELEGATION_TOOLS and evt_type == "tool_call_end":
            args = _arguments_from_event(evt)
            to_agent = str(args.get("to_agent") or args.get("agent_id") or "").strip()
            brief = str(args.get("text") or "").strip()
            if resolve_actor is not None and to_agent:
                resolved = resolve_actor(to_agent)
                if resolved:
                    to_agent = resolved
            if not to_agent or not brief:
                return None
            delegation_id = str(evt.get("tool_call_id") or "").strip()
            dedupe_key = delegation_id or f"{to_agent}:{brief[:120]}"
            if dedupe_key in self._seen_delegations:
                return None
            self._seen_delegations.add(dedupe_key)
            return self._next_entry(
                "delegation",
                self._leader_sender,
                target=to_agent,
                text=brief,
                delegation_id=delegation_id or None,
                message_id=leader_message_id,
            )

        if evt_type in _TRACE_KINDS:
            actor = sender or self._leader_sender
            if actor == self._leader_sender:
                return None
            if evt_type in {
                "thinking_delta",
                "thinking_retract",
                "tool_result_delta",
            }:
                return None
            return self._next_entry(
                "worker_trace",
                actor,
                trace=dict(evt),
                message_id=worker_message_ids.get(actor),
            )

        return None
