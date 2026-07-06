# -*- coding: utf-8 -*-
"""Unit tests for AgentDesk stream translation."""

from qwenpaw.agentdesk.stream_translator import (
    QwenPawStreamTranslator,
    parse_sse_data_line,
    translate_sse_chunk,
)


def test_parse_sse_data_line():
    raw = 'data: {"object":"content","type":"text","text":"hi","delta":true}\n\n'
    payload = parse_sse_data_line(raw)
    assert payload is not None
    assert payload["text"] == "hi"


def test_text_delta_translation():
    translator = QwenPawStreamTranslator(sender="default")
    chunk = (
        'data: {"object":"content","type":"text","text":"Hello","delta":true}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert len(events) == 2
    assert events[0]["step"] == "reply_start"
    assert events[1]["type"] == "text_delta"
    assert events[1]["content"] == "Hello"
    assert translator.final_text() == "Hello"


def test_runtime_ordering_streams_each_delta_incrementally():
    """Envelope-first ordering (as produced by stream_query) must yield one
    ``text_delta`` per content chunk — never buffer the whole answer."""
    translator = QwenPawStreamTranslator(sender="leader")
    msg_id = "m-1"

    envelope = (
        'data: {"object":"message","id":"%s","type":"message",'
        '"role":"assistant","status":"in_progress","content":[]}\n\n' % msg_id
    )
    list(translate_sse_chunk(translator, envelope))

    text_deltas: list[str] = []
    for piece in ["你", "好", "，", "世界"]:
        chunk = (
            'data: {"object":"content","msg_id":"%s","type":"text",'
            '"text":"%s","delta":true}\n\n' % (msg_id, piece)
        )
        for evt in translate_sse_chunk(translator, chunk):
            if evt["type"] == "text_delta":
                text_deltas.append(evt["content"])

    # Each chunk surfaced its own incremental delta (no batching).
    assert text_deltas == ["你", "好", "，", "世界"]
    assert translator.final_text() == "你好，世界"


def test_text_content_before_envelope_does_not_swallow_answer():
    """Even if a text chunk arrives before the assistant envelope, the answer
    must still be delivered (promoted), not lost in provisional thinking."""
    translator = QwenPawStreamTranslator(sender="leader")
    msg_id = "m-2"

    early = (
        'data: {"object":"content","msg_id":"%s","type":"text",'
        '"text":"早","delta":true}\n\n' % msg_id
    )
    list(translate_sse_chunk(translator, early))

    envelope = (
        'data: {"object":"message","id":"%s","type":"message",'
        '"role":"assistant","status":"in_progress","content":[]}\n\n' % msg_id
    )
    promoted = [
        evt
        for evt in translate_sse_chunk(translator, envelope)
        if evt["type"] == "text_delta"
    ]
    # The provisionally-buffered text is promoted to a real text_delta.
    assert any("早" in evt["content"] for evt in promoted)

    later = (
        'data: {"object":"content","msg_id":"%s","type":"text",'
        '"text":"安","delta":true}\n\n' % msg_id
    )
    deltas = [
        evt["content"]
        for evt in translate_sse_chunk(translator, later)
        if evt["type"] == "text_delta"
    ]
    assert deltas == ["安"]


def test_assistant_message_completion():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"message","role":"assistant","status":"completed",'
        '"content":[{"type":"text","text":"Full reply"}]}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert len(events) == 2
    assert events[0]["type"] == "trace"
    assert events[0]["step"] == "reply_start"
    assert events[1]["type"] == "text_delta"
    assert events[1]["content"] == "Full reply"


def test_plugin_call_translation():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"read_file","call_id":"c1",'
        '"arguments":{"path":"README.md"}}}]}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert len(events) == 3
    assert events[0]["step"] == "reply_start"
    assert events[1]["type"] == "tool_call_start"
    assert events[1]["tool_name"] == "read_file"
    tool_evt = events[2]
    assert tool_evt["type"] == "tool_call_end"
    assert tool_evt["tool_name"] == "read_file"
    assert tool_evt["tool_call_id"] == "c1"
    assert "README.md" in tool_evt["detail"]


def test_plugin_call_in_progress_emits_start_only():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"message","type":"plugin_call","status":"in_progress",'
        '"content":[{"type":"data","data":{"name":"execute_shell_command",'
        '"call_id":"c2","arguments":{}}}]}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert [e.get("type") or e.get("step") for e in events] == ["trace", "tool_call_start"]
    assert events[1]["tool_name"] == "execute_shell_command"


def test_auto_continue_skips_info_for_tool_polling_without_text():
    """Repeated tool→reason cycles with no answer text must not spam info rows."""
    translator = QwenPawStreamTranslator(sender="bot")
    tool_start = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"check_agent_task","call_id":"c1",'
        '"arguments":{}}}]}\n\n'
    )
    tool_end = (
        'data: {"object":"message","type":"plugin_call_output","status":"completed",'
        '"content":[{"type":"data","data":{"name":"check_agent_task","call_id":"c1",'
        '"output":"pending","state":"success"}}]}\n\n'
    )
    think = (
        'data: {"object":"message","type":"reasoning","id":"r%s",'
        '"status":"in_progress","content":[]}\n\n'
    )
    events: list[dict] = []
    for i in range(3):
        events.extend(translate_sse_chunk(translator, tool_start))
        events.extend(translate_sse_chunk(translator, tool_end))
        events.extend(translate_sse_chunk(translator, think % (i + 1)))
        if i == 0:
            events.extend(
                translate_sse_chunk(
                    translator,
                    think % (i + 2),
                ),
            )
    info_events = [e for e in events if e.get("type") == "info"]
    reset_events = [e for e in events if e.get("type") == "content_reset"]
    assert info_events == []
    assert len(reset_events) >= 1


def test_auto_continue_info_on_second_thinking_start():
    translator = QwenPawStreamTranslator(sender="bot")
    text = (
        'data: {"object":"content","type":"text","text":"plan","delta":true}\n\n'
    )
    think1 = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    think2 = (
        'data: {"object":"message","type":"reasoning","id":"r2",'
        '"status":"in_progress","content":[]}\n\n'
    )
    events = []
    for chunk in [text, think1, think2]:
        events.extend(translate_sse_chunk(translator, chunk))
    info_events = [e for e in events if e.get("type") == "info"]
    reset_events = [e for e in events if e.get("type") == "content_reset"]
    assert len(info_events) == 1
    assert info_events[0]["label"] == "继续执行…"
    assert len(reset_events) == 1
    assert translator.accumulated == ""
    assert translator.final_text() == ""


def test_auto_continue_resets_accumulated_text():
    translator = QwenPawStreamTranslator(sender="bot")
    first = (
        'data: {"object":"content","type":"text","text":"draft","delta":true}\n\n'
    )
    think1 = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    think2 = (
        'data: {"object":"message","type":"reasoning","id":"r2",'
        '"status":"in_progress","content":[]}\n\n'
    )
    second = (
        'data: {"object":"content","type":"text","text":"final","delta":true}\n\n'
    )
    for chunk in [first, think1, think2, second]:
        list(translate_sse_chunk(translator, chunk))
    assert translator.accumulated == "final"
    assert translator.final_text() == "final"


def test_auto_continue_preserves_segment_after_tool_call():
    """Multi-step narration (text -> tool -> reason -> text), e.g. the team
    leader narrating around each delegation, must keep ALL segments instead of
    collapsing to the last one (which made the reloaded leader bubble lose its
    summary)."""
    translator = QwenPawStreamTranslator(sender="bot")
    seg1 = (
        'data: {"object":"content","type":"text","text":"seg1","delta":true}\n\n'
    )
    tool = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"in_progress","content":[{"type":"data","data":'
        '{"name":"submit_to_agent","call_id":"c1","output":""}}]}\n\n'
    )
    think1 = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    think2 = (
        'data: {"object":"message","type":"reasoning","id":"r2",'
        '"status":"in_progress","content":[]}\n\n'
    )
    seg2 = (
        'data: {"object":"content","type":"text","text":"seg2","delta":true}\n\n'
    )
    for chunk in [seg1, tool, think1, think2, seg2]:
        list(translate_sse_chunk(translator, chunk))
    assert translator.final_text() == "seg1\n\nseg2"


def test_plugin_call_output_streaming_translation():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"in_progress","content":[{"type":"data","data":'
        '{"name":"execute_shell_command","call_id":"c1","output":"line1\\n"}}]}\n\n'
    )
    more = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"in_progress","content":[{"type":"data","data":'
        '{"name":"execute_shell_command","call_id":"c1","output":"line1\\nline2\\n"}}]}\n\n'
    )
    end = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"completed","content":[{"type":"data","data":'
        '{"name":"execute_shell_command","call_id":"c1","output":"line1\\nline2\\n",'
        '"state":"success"}}]}\n\n'
    )
    start_events = list(translate_sse_chunk(translator, start))
    more_events = list(translate_sse_chunk(translator, more))
    end_events = list(translate_sse_chunk(translator, end))
    assert start_events[0]["step"] == "reply_start"
    assert start_events[1]["type"] == "tool_call_start"
    assert start_events[2]["type"] == "tool_result_start"
    assert start_events[3]["type"] == "tool_result_delta"
    assert start_events[3]["detail"] == "line1\n"
    assert more_events[0]["type"] == "tool_result_delta"
    assert more_events[0]["detail"] == "line2\n"
    assert end_events[-1]["type"] == "tool_result_end"
    assert end_events[-1]["detail"] == "line1\nline2\n"


def test_plugin_call_output_translation():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"in_progress","content":[{"type":"data","data":'
        '{"name":"read_file","call_id":"c1","output":""}}]}\n\n'
    )
    end = (
        'data: {"object":"message","type":"plugin_call_output",'
        '"status":"completed","content":[{"type":"data","data":'
        '{"name":"read_file","call_id":"c1","output":"file body",'
        '"state":"success"}}]}\n\n'
    )
    start_events = list(translate_sse_chunk(translator, start))
    end_events = list(translate_sse_chunk(translator, end))
    assert start_events[0]["step"] == "reply_start"
    assert start_events[1]["type"] == "tool_call_start"
    assert start_events[2]["type"] == "tool_result_start"
    assert end_events[0]["type"] == "tool_result_end"
    assert end_events[0]["detail"] == "file body"
    assert end_events[0]["state"] == "success"


def test_reasoning_content_delta():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"content","type":"reasoning","text":"think",'
        '"delta":true}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert events[0]["step"] == "reply_start"
    assert events[1]["type"] == "thinking_start"
    assert events[2]["type"] == "thinking_delta"
    assert events[2]["detail"] == "think"


def test_reasoning_text_delta_via_msg_id():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    delta = (
        'data: {"object":"content","type":"text","msg_id":"r1",'
        '"text":"deep","delta":true}\n\n'
    )
    end = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"completed","content":[{"type":"text","text":"deep thought"}]}\n\n'
    )
    start_events = list(translate_sse_chunk(translator, start))
    delta_events = list(translate_sse_chunk(translator, delta))
    end_events = list(translate_sse_chunk(translator, end))
    assert start_events[0]["step"] == "reply_start"
    assert start_events[1]["type"] == "thinking_start"
    assert delta_events[0]["type"] == "thinking_delta"
    assert delta_events[0]["detail"] == "deep"
    assert end_events[0]["type"] == "thinking_end"
    assert end_events[0]["detail"] == "deep thought"
    assert translator.final_text() == ""


def test_response_error_translation():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"response","status":"completed",'
        '"error":{"message":"model execution failed"}}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["fatal"] is True
    assert "model execution failed" in events[0]["content"]


def test_finalize_pending_tools_after_call_without_result():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"chat_with_agent","call_id":"c1",'
        '"arguments":{"to_agent":"emp_1"}}}]}\n\n'
    )
    list(translate_sse_chunk(translator, start))
    finalized = translator.finalize_pending_tools()
    assert len(finalized) == 1
    assert finalized[0]["type"] == "tool_result_end"
    assert finalized[0]["tool_call_id"] == "c1"
    assert finalized[0]["tool_name"] == "chat_with_agent"


def test_tool_result_end_matches_last_open_tool_without_call_id():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"chat_with_agent","call_id":"c1",'
        '"arguments":{}}}]}\n\n'
    )
    end = (
        'data: {"object":"message","type":"plugin_call_output","status":"completed",'
        '"content":[{"type":"data","data":{"name":"chat_with_agent","output":"done",'
        '"state":"success"}}]}\n\n'
    )
    list(translate_sse_chunk(translator, start))
    end_events = list(translate_sse_chunk(translator, end))
    assert end_events[-1]["type"] == "tool_result_end"
    assert end_events[-1]["tool_call_id"] == "c1"
    assert end_events[-1]["detail"] == "done"
    assert translator.finalize_pending_tools() == []


def test_reasoning_text_delta_not_mixed_with_answer():
    translator = QwenPawStreamTranslator(sender="bot")
    chunks = [
        (
            'data: {"object":"message","type":"reasoning","id":"r1",'
            '"status":"in_progress","content":[]}\n\n'
        ),
        (
            'data: {"object":"content","type":"text","msg_id":"r1",'
            '"text":"hmm","delta":true}\n\n'
        ),
        (
            'data: {"object":"message","id":"a1","role":"assistant",'
            '"status":"in_progress","content":[]}\n\n'
        ),
        (
            'data: {"object":"content","type":"text","msg_id":"a1",'
            '"text":"Hi","delta":true}\n\n'
        ),
    ]
    all_events = []
    for chunk in chunks:
        all_events.extend(translate_sse_chunk(translator, chunk))
    thinking = [e for e in all_events if e.get("type") == "thinking_delta"]
    text = [e for e in all_events if e.get("type") == "text_delta"]
    assert len(thinking) == 1
    assert thinking[0]["detail"] == "hmm"
    assert len(text) == 1
    assert text[0]["content"] == "Hi"
    assert translator.final_text() == "Hi"


def test_reasoning_completed_empty_message_uses_accumulated_deltas():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    delta = (
        'data: {"object":"content","type":"text","msg_id":"r1",'
        '"text":"deep thought","delta":true}\n\n'
    )
    end = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"completed","content":[]}\n\n'
    )
    list(translate_sse_chunk(translator, start))
    list(translate_sse_chunk(translator, delta))
    end_events = list(translate_sse_chunk(translator, end))
    assert len(end_events) == 1
    assert end_events[0]["type"] == "thinking_end"
    assert end_events[0]["detail"] == "deep thought"


def test_finalize_pending_thinking_after_deltas_without_completion():
    translator = QwenPawStreamTranslator(sender="bot")
    delta = (
        'data: {"object":"content","type":"reasoning","text":"solo",'
        '"delta":true}\n\n'
    )
    list(translate_sse_chunk(translator, delta))
    finalized = translator.finalize_pending_thinking()
    assert len(finalized) == 1
    assert finalized[0]["type"] == "thinking_end"
    assert finalized[0]["detail"] == "solo"
    assert translator.finalize_pending_thinking() == []


def test_reasoning_non_delta_content_accumulates_for_end():
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    mirror = (
        'data: {"object":"content","type":"text","msg_id":"r1",'
        '"text":"full mirror","delta":false}\n\n'
    )
    end = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"completed","content":[]}\n\n'
    )
    list(translate_sse_chunk(translator, start))
    list(translate_sse_chunk(translator, mirror))
    end_events = list(translate_sse_chunk(translator, end))
    assert len(end_events) == 1
    assert end_events[0]["type"] == "thinking_end"
    assert end_events[0]["detail"] == "full mirror"


def test_reasoning_text_delta_before_envelope_not_in_answer():
    """Content with reasoning msg_id must not leak into text_delta/final_text."""
    translator = QwenPawStreamTranslator(sender="bot")
    delta = (
        'data: {"object":"content","type":"text","msg_id":"r1",'
        '"text":"plan","delta":true}\n\n'
    )
    start = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"in_progress","content":[]}\n\n'
    )
    end = (
        'data: {"object":"message","type":"reasoning","id":"r1",'
        '"status":"completed","content":[{"type":"text","text":"plan"}]}\n\n'
    )
    answer_env = (
        'data: {"object":"message","id":"a1","role":"assistant",'
        '"status":"in_progress","content":[]}\n\n'
    )
    answer_delta = (
        'data: {"object":"content","type":"text","msg_id":"a1",'
        '"text":"Hi","delta":true}\n\n'
    )

    delta_events = list(translate_sse_chunk(translator, delta))
    assert not any(e.get("type") == "text_delta" for e in delta_events)
    assert any(e.get("type") == "thinking_delta" for e in delta_events)
    assert translator.accumulated == ""

    list(translate_sse_chunk(translator, start))
    list(translate_sse_chunk(translator, end))
    list(translate_sse_chunk(translator, answer_env))
    answer_events = list(translate_sse_chunk(translator, answer_delta))

    assert len(answer_events) == 1
    assert answer_events[0]["type"] == "text_delta"
    assert answer_events[0]["content"] == "Hi"
    assert translator.final_text() == "Hi"


def test_provisional_answer_promote_retracts_thinking():
    """Answer text before envelope is promoted; thinking must not duplicate bubble."""
    translator = QwenPawStreamTranslator(sender="bot")
    early = (
        'data: {"object":"content","type":"text","msg_id":"a1",'
        '"text":"阶段1：数据采集","delta":true}\n\n'
    )
    envelope = (
        'data: {"object":"message","id":"a1","role":"assistant",'
        '"status":"in_progress","content":[]}\n\n'
    )
    more = (
        'data: {"object":"content","type":"text","msg_id":"a1",'
        '"text":"继续","delta":true}\n\n'
    )

    early_events = list(translate_sse_chunk(translator, early))
    assert any(e.get("type") == "thinking_delta" for e in early_events)
    assert not any(e.get("type") == "text_delta" for e in early_events)

    promote_events = list(translate_sse_chunk(translator, envelope))
    assert any(e.get("type") == "thinking_retract" for e in promote_events)
    promoted_text = [
        e.get("content")
        for e in promote_events
        if e.get("type") == "text_delta"
    ]
    assert promoted_text == ["阶段1：数据采集"]

    more_events = list(translate_sse_chunk(translator, more))
    assert more_events[-1]["type"] == "text_delta"
    assert more_events[-1]["content"] == "继续"
    assert translator.final_text() == "阶段1：数据采集继续"


def test_reasoning_envelope_without_object_field():
    """Reasoning envelopes missing object=message still route to thinking."""
    translator = QwenPawStreamTranslator(sender="bot")
    start = (
        'data: {"type":"reasoning","id":"r9","status":"in_progress",'
        '"content":[]}\n\n'
    )
    delta = (
        'data: {"object":"content","type":"text","msg_id":"r9",'
        '"text":"solo","delta":true}\n\n'
    )
    end = (
        'data: {"type":"reasoning","id":"r9","status":"completed",'
        '"content":[{"type":"text","text":"solo"}]}\n\n'
    )

    start_events = list(translate_sse_chunk(translator, start))
    assert any(e.get("type") == "thinking_start" for e in start_events)
    delta_events = list(translate_sse_chunk(translator, delta))
    assert any(e.get("type") == "thinking_delta" for e in delta_events)
    assert not any(e.get("type") == "text_delta" for e in delta_events)
    end_events = list(translate_sse_chunk(translator, end))
    assert end_events[0]["type"] == "thinking_end"
    assert translator.final_text() == ""

    response = 'data: {"object":"response","status":"completed"}\n\n'
    promote_events = list(translate_sse_chunk(translator, response))
    assert not any(e.get("type") == "thinking_retract" for e in promote_events)
    text_deltas = [e for e in promote_events if e.get("type") == "text_delta"]
    assert text_deltas[-1]["content"] == "solo"
    assert translator.final_text() == "solo"

    assert translator.finalize_answer_fallback() == []


def test_response_completed_promotes_reasoning_only_during_stream():
    """Reasoning-only turns promote at response.completed, not via end fallback."""
    translator = QwenPawStreamTranslator(sender="AgentDesk企伴")
    greeting = "你好！我是 AgentDesk企伴，你的企业智能工作助手。"
    delta = (
        'data: {"object":"content","type":"reasoning","text":"%s",'
        '"delta":true}\n\n' % greeting
    )
    response = 'data: {"object":"response","status":"completed"}\n\n'
    list(translate_sse_chunk(translator, delta))
    list(translate_sse_chunk(translator, response))
    assert translator.final_text() == greeting
    assert translator.finalize_answer_fallback() == []


def test_finalize_answer_fallback_after_reasoning_only_reply():
    """Stream-end safety net when response.completed never arrives."""
    translator = QwenPawStreamTranslator(sender="AgentDesk企伴")
    greeting = "你好！我是 AgentDesk企伴，你的企业智能工作助手。"
    delta = (
        'data: {"object":"content","type":"reasoning","text":"%s",'
        '"delta":true}\n\n' % greeting
    )
    list(translate_sse_chunk(translator, delta))
    finalized = translator.finalize_pending_thinking()
    assert finalized[0]["type"] == "thinking_end"
    assert finalized[0]["detail"] == greeting
    assert translator.final_text() == ""

    fallback = translator.finalize_answer_fallback()
    assert not any(e.get("type") == "thinking_retract" for e in fallback)
    assert fallback[-1]["type"] == "text_delta"
    assert fallback[-1]["content"] == greeting
    assert translator.final_text() == greeting


def test_response_completed_does_not_promote_when_answer_text_arrived():
    translator = QwenPawStreamTranslator(sender="bot")
    chunks = [
        (
            'data: {"object":"message","type":"reasoning","id":"r1",'
            '"status":"in_progress","content":[]}\n\n'
        ),
        (
            'data: {"object":"content","type":"text","msg_id":"r1",'
            '"text":"hmm","delta":true}\n\n'
        ),
        (
            'data: {"object":"message","type":"reasoning","id":"r1",'
            '"status":"completed","content":[{"type":"text","text":"hmm"}]}\n\n'
        ),
        (
            'data: {"object":"message","id":"a1","role":"assistant",'
            '"status":"in_progress","content":[]}\n\n'
        ),
        (
            'data: {"object":"content","type":"text","msg_id":"a1",'
            '"text":"Hi","delta":true}\n\n'
        ),
        'data: {"object":"response","status":"completed"}\n\n',
    ]
    all_events = []
    for chunk in chunks:
        all_events.extend(translate_sse_chunk(translator, chunk))
    text = [e for e in all_events if e.get("type") == "text_delta"]
    assert len(text) == 1
    assert text[0]["content"] == "Hi"
    assert translator.final_text() == "Hi"


def test_assistant_completed_message_with_reasoning_block():
    translator = QwenPawStreamTranslator(sender="bot")
    chunk = (
        'data: {"object":"message","role":"assistant","status":"completed",'
        '"content":[{"type":"reasoning","text":"Hi from reasoning"}]}\n\n'
    )
    events = list(translate_sse_chunk(translator, chunk))
    assert events[-1]["type"] == "text_delta"
    assert events[-1]["content"] == "Hi from reasoning"
    assert translator.final_text() == "Hi from reasoning"


def test_write_file_tool_emits_artifact_event():
    translator = QwenPawStreamTranslator(sender="researcher")
    call = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"write_file","call_id":"call-1",'
        '"arguments":{"file_path":"AI_Trend_Report_2026H1.md","content":"# Trends"}}}]}'
        "\n\n"
    )
    result = (
        'data: {"object":"message","type":"plugin_call_output","status":"completed",'
        '"content":[{"type":"data","data":{"name":"write_file","call_id":"call-1",'
        '"output":"Wrote AI_Trend_Report_2026H1.md","state":"success"}}]}'
        "\n\n"
    )
    list(translate_sse_chunk(translator, call))
    events = list(translate_sse_chunk(translator, result))
    artifact_events = [evt for evt in events if evt.get("type") == "artifact"]
    assert len(artifact_events) == 1
    assert artifact_events[0]["path"] == "AI_Trend_Report_2026H1.md"
    assert artifact_events[0]["name"] == "AI_Trend_Report_2026H1.md"


def test_materialize_skill_tool_emits_artifact_event():
    translator = QwenPawStreamTranslator(sender="skill-creator")
    call = (
        'data: {"object":"message","type":"plugin_call","status":"completed",'
        '"content":[{"type":"data","data":{"name":"materialize_skill","call_id":"call-2",'
        '"arguments":{"name":"team-strength-analyzer","description":"Analyze teams",'
        '"body":"# Overview"}}}]}'
        "\n\n"
    )
    result = (
        'data: {"object":"message","type":"plugin_call_output","status":"completed",'
        '"content":[{"type":"data","data":{"name":"materialize_skill","call_id":"call-2",'
        '"output":"**Skill created and enabled**: `team-strength-analyzer`",'
        '"state":"success"}}]}'
        "\n\n"
    )
    list(translate_sse_chunk(translator, call))
    events = list(translate_sse_chunk(translator, result))
    artifact_events = [evt for evt in events if evt.get("type") == "artifact"]
    assert len(artifact_events) == 1
    assert artifact_events[0]["path"] == "skills/team-strength-analyzer/SKILL.md"
    assert artifact_events[0]["name"] == "team-strength-analyzer/SKILL.md"
    assert artifact_events[0]["role"] == "product"


def test_final_text_dedupes_identical_prior_segments():
    """Repeated auto-continue segments must not concatenate verbatim duplicates."""
    translator = QwenPawStreamTranslator(sender="leader")
    translator._prior_segments = ["status", "status", "other"]
    translator.accumulated = "status"
    assert translator.final_text() == "status\n\nother"

