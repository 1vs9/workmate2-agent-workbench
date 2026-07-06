# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.team_timeline import (
    TeamTimelineWriter,
    classify_leader_narration,
    filter_leader_persist_text,
    merge_stream_text_delta,
)


def test_classify_leader_narration_detects_worker_status() -> None:
    kind, target = classify_leader_narration("研究员正在搜索中...")
    assert kind == "phase"
    assert target == "研究员"


def test_classify_leader_narration_keeps_real_answer_as_leader_text() -> None:
    kind, target = classify_leader_narration(
        "以下是将上述功能整合而成的一段描述：系统支持技能、单智能体与多智能体协作。",
    )
    assert kind == "leader_text"
    assert target is None


def test_timeline_writer_emits_delegation_from_tool_call_end() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    evt = {
        "type": "tool_call_end",
        "tool_name": "submit_to_agent",
        "tool_call_id": "call-1",
        "detail": {
            "arguments": {
                "to_agent": "研究员",
                "text": "请分析今日新闻",
            },
        },
    }
    entry = writer.entry_from_mapped_event(evt)
    assert entry is not None
    assert entry["kind"] == "delegation"
    assert entry["target"] == "研究员"
    assert entry["text"] == "请分析今日新闻"
    assert entry["delegation_id"] == "call-1"


def test_timeline_writer_dedupes_identical_delegation() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    evt = {
        "type": "tool_call_end",
        "tool_name": "chat_with_agent",
        "tool_call_id": "call-1",
        "detail": {"arguments": {"to_agent": "研究员", "text": "同上"}},
    }
    first = writer.entry_from_mapped_event(evt)
    second = writer.entry_from_mapped_event(evt)
    assert first is not None
    assert second is None


def test_timeline_writer_maps_worker_status_as_phase() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    entry = writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "研究员正在地毯式搜索中...",
        },
        leader_message_id="msg-leader",
    )
    assert entry is not None
    assert entry["kind"] == "phase"
    assert entry["phase"] == "worker_status"
    assert entry["target"] == "研究员"


def test_timeline_writer_maps_worker_text_delta() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    entry = writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "研究员",
            "content": "检索完成",
        },
        worker_message_ids={"研究员": "msg-worker-1"},
    )
    assert entry is not None
    assert entry["kind"] == "worker_text"
    assert entry["actor"] == "研究员"
    assert entry["text"] == "检索完成"
    assert entry["message_id"] == "msg-worker-1"
    assert entry.get("delta") is True


def test_timeline_writer_tracks_leader_answer_excluding_phase() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "已安排研究员与审查官并行调研。",
        },
    )
    writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "研究员正在搜索中...",
        },
    )
    assert writer.leader_answer_text() == "已安排研究员与审查官并行调研。"


def test_filter_leader_persist_text_strips_status_narration() -> None:
    raw = (
        "已安排研究员调研。\n\n"
        "研究员正在地毯式搜索中...\n\n"
        "研究员还在分析数据..."
    )
    assert filter_leader_persist_text(raw) == "已安排研究员调研。"


def test_classify_leader_narration_detects_round_progress_block() -> None:
    progress = (
        "📋 本轮进度：✅ @规划者已收到任务，正在拆解为 3-4 个子问题；"
        "随后将派给 @研究员 地毯式检索，@审查官 把关，@主笔 成稿。已派工"
    )
    kind, target = classify_leader_narration(progress)
    assert kind == "phase"
    assert target is None


def test_classify_leader_narration_keeps_substantive_report() -> None:
    report = (
        "## 未来一周大事件综览\n\n"
        "规划者拆题完成，研究员收集了多条线索，审查官把关后主笔成稿如下：\n"
        "1. 世界经济论坛相关活动\n"
        "2. 夏季达沃斯论坛筹备进展\n"
        "3. 科技行业重要发布会"
    )
    kind, target = classify_leader_narration(report)
    assert kind == "leader_text"
    assert target is None


def test_classify_leader_narration_keeps_completion_recap() -> None:
    recap = (
        "没有断！流程已经完整走完了\n\n全流程回顾：\n"
        "- 规划者：拆解完成\n- 研究员：检索完成\n"
        "- 审查官：质量把关\n- 主笔：排版结构化长文"
    )
    kind, target = classify_leader_narration(recap)
    assert kind == "leader_text"
    assert target is None


def test_merge_stream_text_delta_appends_incremental_pieces() -> None:
    assert merge_stream_text_delta("你好", "世界") == "你好世界"


def test_merge_stream_text_delta_replaces_cumulative_rewrite() -> None:
    a = "📋 本轮进度：✅ @规划者已收到任务。已派工"
    b = "📋 本轮进度：✅ @规划者已收到任务。@主笔已派工"
    assert merge_stream_text_delta(a, b) == b
    assert merge_stream_text_delta(b, b) == b


def test_timeline_writer_emits_round_progress_for_coordination_block() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    entry = writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "📋 本轮进度：✅ @规划者已派工。@主笔成稿。",
        },
    )
    assert entry is not None
    assert entry["kind"] == "phase"
    assert entry["phase"] == "round_progress"


def test_timeline_writer_preserves_newlines_in_text_delta() -> None:
    writer = TeamTimelineWriter(round_id="round-1", leader_sender="团队·leader")
    first = writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "---\n\n",
        },
    )
    second = writer.entry_from_mapped_event(
        {
            "type": "text_delta",
            "sender": "团队·leader",
            "content": "## Title",
        },
    )
    assert first is not None
    assert second is not None
    assert first["text"] == "---\n\n"
    assert second["text"] == "## Title"
