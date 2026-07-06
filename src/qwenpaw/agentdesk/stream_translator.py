# -*- coding: utf-8 -*-
"""Translate QwenPaw console SSE JSON into AgentDesk stream events."""

from __future__ import annotations

import json
from typing import Any, Iterator


def parse_sse_data_line(line: str) -> dict[str, Any] | None:
    """Parse one SSE chunk (``data: {...}\\n\\n``) into a dict."""
    text = (line or "").strip()
    if not text:
        return None
    if text.startswith("data:"):
        text = text[5:].strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
    return None


def _message_text(
    payload: dict[str, Any],
    *,
    include_reasoning: bool = False,
) -> str:
    parts: list[str] = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        block_type = item.get("type")
        if block_type == "text" and item.get("text"):
            parts.append(str(item["text"]))
        elif (
            include_reasoning
            and block_type in ("reasoning", "thinking")
            and item.get("text")
        ):
            parts.append(str(item["text"]))
    return "".join(parts)


def _content_text(payload: dict[str, Any]) -> str:
    if payload.get("type") == "text" and payload.get("text"):
        return str(payload["text"])
    if payload.get("type") in ("reasoning", "thinking") and payload.get("text"):
        return str(payload["text"])
    return ""


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _status_str(payload: dict[str, Any]) -> str:
    return _enum_value(payload.get("status")).lower()


def _message_type(payload: dict[str, Any]) -> str:
    return _enum_value(payload.get("type")).lower()


def _plugin_data(payload: dict[str, Any]) -> dict[str, Any]:
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "data":
            data = item.get("data")
            if isinstance(data, dict):
                return data
    return {}


def _format_detail(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def friendly_stream_error(raw_error: str) -> str:
    """Map low-level runner errors to actionable AgentDesk messages."""
    text = (raw_error or "").strip()
    if not text:
        return "对话失败，请稍后重试。"

    lowered = text.lower()
    if "no active model configured" in lowered or "pick one in the ui" in lowered:
        return (
            "未配置可用模型。AgentDesk 已尝试自动选择，但未成功。"
            "请在 QwenPaw 设置中配置 API Key 并选择模型，或在控制台激活任意可用模型后重试。"
        )
    if "model 'unknown' execution failed" in lowered:
        if "[dump:" in text:
            dump_part = text[text.index("[dump:") :].strip()
            return (
                "对话启动失败（Agent 初始化错误，通常与模型 API 无关）。"
                f"请查看错误转储排查。 {dump_part}"
            )
        return "对话启动失败（Agent 初始化错误，通常与模型 API 无关）。"
    if "pydanticusererror" in lowered or "_structuredoutputdynamicclass" in lowered:
        return (
            "Agent 工具注册失败（内部 schema 错误）。"
            "请升级 WorkBuddy 或暂时在 Agent 配置中禁用相关工具后重试。"
        )
    if "未配置可用模型" in text or "无法激活模型" in text:
        return text
    return text


_TOOL_CALL_TYPES = frozenset(
    {"plugin_call", "function_call", "mcp_tool_call"},
)
_TOOL_OUTPUT_TYPES = frozenset(
    {"plugin_call_output", "function_call_output", "mcp_tool_call_output"},
)


class QwenPawStreamTranslator:
    """Stateful translator for one assistant turn."""

    def __init__(self, *, sender: str) -> None:
        self.sender = sender
        self.accumulated = ""
        self._prior_segments: list[str] = []
        # True once a tool call is announced after the current answer segment
        # began. It distinguishes a real multi-step continuation (text → tool →
        # more text, e.g. the team leader narrating around delegations) from a
        # false-start the model rethinks and replaces (text → reason → text).
        self._tool_since_segment = False
        self._reply_started = False
        self._reasoning_msg_ids: set[str] = set()
        self._answer_msg_ids: set[str] = set()
        self._provisional_reasoning_msg_ids: set[str] = set()
        self._tool_calls_announced: set[str] = set()
        self._tool_results_started: set[str] = set()
        self._tool_results_completed: set[str] = set()
        self._tool_names: dict[str, str] = {}
        self._tool_arguments: dict[str, dict[str, Any]] = {}
        self._tool_output_acc: dict[str, str] = {}
        self._last_announced_tool_call_id: str = ""
        self._thinking_pass = 0
        self._thinking_open = False
        self._thinking_acc = ""
        self._last_completed_thinking = ""
        self._had_turn_output = False

    def _mark_turn_output(self) -> None:
        self._had_turn_output = True

    def _auto_continue_info_events(self) -> list[dict[str, Any]]:
        if not self._had_turn_output:
            return []
        segment = self.accumulated.strip()
        had_visible_text = bool(segment)
        if segment and self._tool_since_segment:
            # A tool call separated this answer segment from the next reasoning
            # pass, so it is a real multi-step continuation (e.g. the leader's
            # narration around each delegation). Preserve it so the full reply
            # survives in final_text() / on reload instead of collapsing to the
            # last segment.
            if not self._prior_segments or self._prior_segments[-1] != segment:
                self._prior_segments.append(segment)
        # Otherwise the partial answer was a false-start the model is replacing;
        # drop it so it doesn't double up with the replacement reply.
        self.accumulated = ""
        self._tool_since_segment = False
        self._last_completed_thinking = ""
        events: list[dict[str, Any]] = []
        # Only surface the info row when draft answer text is being replaced.
        # Tool-polling loops (e.g. repeated check_agent_task) auto-continue with
        # empty accumulated text — skip info there to avoid observability spam.
        if had_visible_text:
            events.append(
                {
                    "type": "info",
                    "label": "继续执行…",
                    "detail": "模型正在下一轮推理",
                },
            )
        events.append({"type": "content_reset"})
        return events

    def _tool_call_start_event(
        self,
        name: str,
        call_id: str,
        tool_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "type": "tool_call_start",
            "label": f"调用 {name}" if name else "工具调用",
            "tool_name": name,
            "tool_call_id": call_id,
        }
        if isinstance(tool_arguments, dict):
            event["tool_arguments"] = tool_arguments
        return event

    def _resolve_tool_call_id(
        self,
        data: dict[str, Any],
        *,
        allow_last_open: bool = False,
    ) -> str:
        """Resolve tool call id from plugin data only (never message envelope id)."""
        call_id = str(data.get("call_id") or "").strip()
        if call_id:
            return call_id
        if allow_last_open and self._last_announced_tool_call_id:
            pending = self._last_announced_tool_call_id
            if pending not in self._tool_results_completed:
                return pending
        return ""

    def _announce_tool_call(
        self,
        events: list[dict[str, Any]],
        name: str,
        call_id: str,
        tool_arguments: dict[str, Any] | None = None,
    ) -> None:
        if not call_id or call_id in self._tool_calls_announced:
            return
        self._tool_calls_announced.add(call_id)
        self._tool_since_segment = True
        if name:
            self._tool_names[call_id] = name
        if isinstance(tool_arguments, dict):
            self._tool_arguments[call_id] = tool_arguments
        self._last_announced_tool_call_id = call_id
        events.append(self._tool_call_start_event(name, call_id, tool_arguments))

    def _artifact_events_for_tool(
        self,
        *,
        name: str,
        call_id: str,
        state: str,
    ) -> list[dict[str, Any]]:
        if state not in ("success", "completed", ""):
            return []
        tool = str(name or "").strip().lower()
        if tool == "materialize_skill":
            args = self._tool_arguments.get(call_id) or {}
            skill_name = str(args.get("name") or "").strip()
            if not skill_name:
                return []
            path = f"skills/{skill_name}/SKILL.md"
            return [
                {
                    "type": "artifact",
                    "kind": "file",
                    "role": "product",
                    "path": path,
                    "name": f"{skill_name}/SKILL.md",
                    "summary": path,
                    "op": "write",
                    "tool": tool,
                },
            ]
        if tool not in {"write_file", "edit_file"}:
            return []
        args = self._tool_arguments.get(call_id) or {}
        raw_path = str(
            args.get("file_path")
            or args.get("path")
            or args.get("target_file")
            or "",
        ).strip()
        if not raw_path:
            return []
        normalized = raw_path.replace("\\", "/")
        file_name = normalized.split("/")[-1] or normalized
        return [
            {
                "type": "artifact",
                "kind": "file",
                "role": "product" if file_name.lower().endswith(".md") else "change",
                "path": normalized,
                "name": file_name,
                "summary": file_name,
                "op": "write" if tool == "write_file" else "edit",
                "tool": tool,
            },
        ]

    def _emit_tool_result_end(
        self,
        *,
        name: str,
        call_id: str,
        output: Any,
        state: str,
    ) -> dict[str, Any]:
        if call_id:
            self._tool_results_completed.add(call_id)
            self._tool_output_acc.pop(call_id, None)
        return {
            "type": "tool_result_end",
            "label": f"完成 {name}" if name else "工具完成",
            "tool_name": name,
            "tool_call_id": call_id,
            "detail": _format_detail(output),
            "state": state,
        }

    def finalize_pending_tools(self) -> list[dict[str, Any]]:
        """Emit synthetic tool_result_end for tools that started but never completed."""
        events: list[dict[str, Any]] = []
        for call_id in self._tool_calls_announced:
            if call_id in self._tool_results_completed:
                continue
            name = self._tool_names.get(call_id, "")
            output = self._tool_output_acc.get(call_id, "")
            events.append(
                self._emit_tool_result_end(
                    name=name,
                    call_id=call_id,
                    output=output or "(completed)",
                    state="success" if output else "unknown",
                ),
            )
        return events

    def _append_thinking_delta(self, piece: str) -> list[dict[str, Any]]:
        if not piece:
            return []
        self._thinking_acc += piece
        events = self._reply_start_events()
        if not self._thinking_open:
            if self._thinking_pass > 0:
                events.extend(self._auto_continue_info_events())
            self._thinking_pass += 1
            self._thinking_open = True
            events.append(
                {
                    "type": "thinking_start",
                    "label": "深度思考",
                },
            )
        events.append(
            {
                "type": "thinking_delta",
                "detail": piece,
            },
        )
        return events

    def _emit_thinking_end(self, full: str) -> list[dict[str, Any]]:
        text = (full or "").strip()
        if not text:
            return []
        self._thinking_open = False
        self._thinking_acc = ""
        self._last_completed_thinking = text
        self._mark_turn_output()
        return [
            {
                "type": "thinking_end",
                "label": "深度思考完成",
                "detail": text,
            },
        ]

    def _pending_thinking_text(self) -> str:
        if self._thinking_acc.strip():
            return self._thinking_acc.strip()
        return self._last_completed_thinking.strip()

    def _answer_message_event(self, text: str) -> dict[str, Any]:
        return {
            "type": "message",
            "role": "assistant",
            "sender": self.sender,
            "content": text,
            "done": False,
        }

    def _text_delta_event(self, piece: str) -> dict[str, Any]:
        return {
            "type": "text_delta",
            "role": "assistant",
            "sender": self.sender,
            "content": piece,
            "done": False,
        }

    def _promote_reasoning_only_answer(self) -> list[dict[str, Any]]:
        """Emit ``text_delta`` when QwenPaw ended with reasoning but no text block.

        QwenPaw upstream keeps thinking in a separate envelope (``type=reasoning``)
        from the visible answer (``type=text``). When a model replies only via
        thinking blocks, ``response.completed`` arrives with no text deltas — promote
        the reasoning text into the main bubble via ``text_delta``, keeping
        ``thinking_*`` trace events in the process panel (no ``thinking_retract``).
        """
        if self.accumulated.strip():
            return []
        text = self._pending_thinking_text()
        if not text:
            return []
        self.accumulated = text
        self._mark_turn_output()
        events = self._reply_start_events()
        events.append(self._text_delta_event(text))
        return events

    def finalize_answer_fallback(self) -> list[dict[str, Any]]:
        """Stream-end safety net when ``response.completed`` was not observed."""
        return self._promote_reasoning_only_answer()

    def finalize_pending_thinking(self) -> list[dict[str, Any]]:
        """Emit thinking_end when deltas arrived but reasoning completion was empty."""
        if not self._thinking_open and not self._thinking_acc.strip():
            return []
        return self._emit_thinking_end(self._thinking_acc)

    def _reply_start_events(self) -> list[dict[str, Any]]:
        if self._reply_started:
            return []
        self._reply_started = True
        return [
            {
                "type": "trace",
                "step": "reply_start",
                "label": "开始处理",
            },
        ]

    def _promote_provisional_answer_content(
        self,
        msg_id: str,
    ) -> list[dict[str, Any]]:
        """Re-route answer text that arrived before the assistant envelope."""
        if not msg_id or msg_id not in self._provisional_reasoning_msg_ids:
            return []
        if msg_id in self._reasoning_msg_ids:
            return []

        events: list[dict[str, Any]] = []
        self._provisional_reasoning_msg_ids.discard(msg_id)

        if not (self._thinking_open or self._thinking_acc.strip()):
            return events

        events.append({"type": "thinking_retract"})
        self._thinking_open = False
        migrated = self._thinking_acc
        self._thinking_acc = ""
        if not migrated:
            return events

        self.accumulated += migrated
        self._mark_turn_output()
        events.extend(self._reply_start_events())
        events.append(self._text_delta_event(migrated))
        return events

    def _register_answer_msg_id(self, msg_id: str) -> None:
        if not msg_id:
            return
        self._answer_msg_ids.add(msg_id)
        self._provisional_reasoning_msg_ids.discard(msg_id)

    def _register_reasoning_msg_id(self, msg_id: str) -> None:
        if not msg_id:
            return
        self._reasoning_msg_ids.add(msg_id)
        self._provisional_reasoning_msg_ids.discard(msg_id)

    def _content_is_thinking(self, qwen_event: dict[str, Any]) -> bool:
        content_type = _enum_value(qwen_event.get("type")).lower()
        if content_type in ("reasoning", "thinking"):
            return True
        msg_id = str(qwen_event.get("msg_id") or "")
        if not msg_id:
            return False
        if msg_id in self._answer_msg_ids:
            return False
        if msg_id in self._reasoning_msg_ids:
            return True
        # Reasoning content chunks can arrive before the reasoning envelope;
        # treat unknown msg_id as provisional thinking until an answer envelope
        # registers the id.
        self._provisional_reasoning_msg_ids.add(msg_id)
        return True

    def _handle_reasoning_message(
        self,
        qwen_event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        msg_id = str(qwen_event.get("id") or "")
        status = _status_str(qwen_event)
        if status in ("in_progress", "created"):
            if msg_id and msg_id in self._reasoning_msg_ids:
                return []
            if msg_id:
                self._register_reasoning_msg_id(msg_id)
            events = self._reply_start_events()
            if self._thinking_open:
                self._thinking_open = False
                self._thinking_acc = ""
            if self._thinking_pass > 0:
                events.extend(self._auto_continue_info_events())
            self._thinking_pass += 1
            self._thinking_open = True
            events.append(
                {
                    "type": "thinking_start",
                    "label": "深度思考",
                },
            )
            return events
        if status == "completed":
            if msg_id:
                self._reasoning_msg_ids.discard(msg_id)
            full = _message_text(qwen_event) or self._thinking_acc
            return self._emit_thinking_end(full)
        return []

    def translate(self, qwen_event: dict[str, Any]) -> list[dict[str, Any]]:
        if not qwen_event:
            return []

        if qwen_event.get("error"):
            return [
                {
                    "type": "error",
                    "content": friendly_stream_error(str(qwen_event.get("error"))),
                    "fatal": True,
                },
            ]

        obj = _enum_value(qwen_event.get("object")).lower()
        if obj == "response":
            status = _status_str(qwen_event)
            if status in ("completed", "failed", "cancelled", "incomplete"):
                err = qwen_event.get("error")
                if err:
                    if isinstance(err, dict):
                        message = str(err.get("message") or err.get("code") or err)
                    else:
                        message = str(
                            getattr(err, "message", None) or err,
                        )
                    return [
                        {
                            "type": "error",
                            "content": friendly_stream_error(message),
                            "fatal": True,
                        },
                    ]
                if status == "completed":
                    return self._promote_reasoning_only_answer()
            return []

        if obj == "content":
            is_thinking = self._content_is_thinking(qwen_event)
            if is_thinking:
                piece = _content_text(qwen_event)
                if not piece:
                    return []
                if qwen_event.get("delta") is True:
                    return self._append_thinking_delta(piece)
                if len(piece) >= len(self._thinking_acc):
                    self._thinking_acc = piece
                else:
                    self._thinking_acc += piece
                return []
            content_type = _enum_value(qwen_event.get("type")).lower()
            if content_type == "text" and qwen_event.get("delta") is True:
                piece = _content_text(qwen_event)
                if not piece:
                    return []
                self.accumulated += piece
                self._mark_turn_output()
                events = self._reply_start_events()
                events.append(self._text_delta_event(piece))
                return events
            return []

        if obj == "message":
            msg_type = _message_type(qwen_event)
            status = _status_str(qwen_event)
            role = _enum_value(qwen_event.get("role")).lower()
            envelope_id = str(qwen_event.get("id") or "")

            if (
                msg_type in ("message", "")
                and role == "assistant"
                and status in ("in_progress", "created")
                and envelope_id
            ):
                promoted = self._promote_provisional_answer_content(envelope_id)
                self._register_answer_msg_id(envelope_id)
                if promoted and msg_type in ("message", ""):
                    return promoted

            if msg_type in _TOOL_CALL_TYPES:
                if status not in ("completed", "in_progress", "created"):
                    return []
                data = _plugin_data(qwen_event)
                name = str(data.get("name") or "")
                call_id = self._resolve_tool_call_id(data)
                call_args = data.get("arguments")
                tool_arguments = call_args if isinstance(call_args, dict) else None
                events = self._reply_start_events()
                self._announce_tool_call(events, name, call_id, tool_arguments)
                if status == "completed":
                    detail = _format_detail(data.get("arguments"))
                    self._mark_turn_output()
                    events.append(
                        {
                            "type": "tool_call_end",
                            "label": f"调用 {name}" if name else "工具调用",
                            "tool_name": name,
                            "tool_call_id": call_id,
                            "detail": detail,
                            "tool_arguments": tool_arguments or {},
                        },
                    )
                return events

            if msg_type in _TOOL_OUTPUT_TYPES:
                data = _plugin_data(qwen_event)
                name = str(data.get("name") or "")
                call_id = self._resolve_tool_call_id(data, allow_last_open=True)
                if status in ("in_progress", "created"):
                    events = self._reply_start_events()
                    self._announce_tool_call(events, name, call_id)
                    if call_id not in self._tool_results_started:
                        self._tool_results_started.add(call_id)
                        events.append(
                            {
                                "type": "tool_result_start",
                                "tool_name": name,
                                "tool_call_id": call_id,
                            },
                        )
                    output_piece = _format_detail(data.get("output"))
                    if output_piece:
                        prev = self._tool_output_acc.get(call_id, "")
                        delta = (
                            output_piece[len(prev) :]
                            if output_piece.startswith(prev)
                            else output_piece
                        )
                        if delta:
                            self._tool_output_acc[call_id] = output_piece
                            events.append(
                                {
                                    "type": "tool_result_delta",
                                    "tool_name": name,
                                    "tool_call_id": call_id,
                                    "detail": delta,
                                },
                            )
                    return events
                if status == "completed":
                    output = data.get("output")
                    state = str(data.get("state") or "success")
                    self._mark_turn_output()
                    detail = _format_detail(output)
                    prev = self._tool_output_acc.get(call_id, "")
                    trailing = ""
                    if detail and prev:
                        if detail.startswith(prev) and len(detail) > len(prev):
                            trailing = detail[len(prev) :]
                        elif detail != prev:
                            trailing = detail
                    events = self._reply_start_events()
                    self._announce_tool_call(events, name, call_id)
                    if trailing:
                        events.append(
                            {
                                "type": "tool_result_delta",
                                "tool_name": name,
                                "tool_call_id": call_id,
                                "detail": trailing,
                            },
                        )
                    events.append(
                        self._emit_tool_result_end(
                            name=name,
                            call_id=call_id,
                            output=output,
                            state=state,
                        ),
                    )
                    events.extend(
                        self._artifact_events_for_tool(
                            name=name,
                            call_id=call_id,
                            state=state,
                        ),
                    )
                    return events
                return []

            if msg_type == "reasoning":
                return self._handle_reasoning_message(qwen_event)

            role = _enum_value(qwen_event.get("role")).lower()
            if (
                msg_type in ("message", "")
                and status == "completed"
                and role == "assistant"
            ):
                full = _message_text(qwen_event)
                if not full.strip():
                    full = _message_text(qwen_event, include_reasoning=True)
                if not full.strip():
                    return []
                if not self.accumulated.strip():
                    self.accumulated = full
                    self._mark_turn_output()
                    events = self._reply_start_events()
                    events.append(self._text_delta_event(full))
                    return events
                if full.startswith(self.accumulated):
                    self.accumulated = full
                elif not self.accumulated.startswith(full):
                    self.accumulated = full
                events = self._reply_start_events()
                events.append(self._answer_message_event(full))
                return events
            return []

        msg_type = _enum_value(qwen_event.get("type")).lower()
        if msg_type == "reasoning":
            return self._handle_reasoning_message(qwen_event)

        if msg_type in _TOOL_CALL_TYPES:
            data = _plugin_data(qwen_event)
            name = str(data.get("name") or "")
            call_id = self._resolve_tool_call_id(data)
            events: list[dict[str, Any]] = []
            self._announce_tool_call(events, name, call_id)
            self._mark_turn_output()
            events.append(
                {
                    "type": "tool_call_end",
                    "label": f"调用 {name}" if name else "工具调用",
                    "tool_name": name,
                    "tool_call_id": call_id,
                    "detail": _format_detail(data.get("arguments")),
                },
            )
            return events

        return []

    def final_text(self) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        for segment in [*self._prior_segments, self.accumulated.strip()]:
            normalized = segment.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            parts.append(normalized)
        return "\n\n".join(parts)

    def current_segment_text(self) -> str:
        """Return only the active answer segment (post-``content_reset``)."""
        return self.accumulated.strip()


def translate_sse_chunk(
    translator: QwenPawStreamTranslator,
    sse_chunk: str,
) -> Iterator[dict[str, Any]]:
    """Yield AgentDesk events parsed from one QwenPaw SSE string."""
    payload = parse_sse_data_line(sse_chunk)
    if payload is None:
        return
    for evt in translator.translate(payload):
        yield evt
