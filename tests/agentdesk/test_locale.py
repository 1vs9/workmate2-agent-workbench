# -*- coding: utf-8 -*-
"""Tests for AgentDesk locale detection."""

from qwenpaw.agentdesk.locale import (
    build_chat_response_language_hint,
    detect_user_language,
    is_chinese_language,
)


def test_detect_user_language_defaults_to_chinese():
    assert detect_user_language("") == "zh"
    assert detect_user_language("   ") == "zh"


def test_detect_user_language_recognizes_mixed_chinese_input():
    assert detect_user_language("请帮我创建一个 skill") == "zh"
    assert detect_user_language("整理会议纪要") == "zh"


def test_detect_user_language_recognizes_english_input():
    assert detect_user_language("Create a weekly report skill") == "en"


def test_is_chinese_language():
    assert is_chinese_language("zh")
    assert is_chinese_language("zh-CN")
    assert not is_chinese_language("en")


def test_build_chat_response_language_hint_prefers_chinese():
    hint = build_chat_response_language_hint("请帮我整理会议纪要")
    assert "中文" in hint
    assert "FAQ" in hint or "Q&A" in hint


def test_build_chat_response_language_hint_english_for_english_input():
    hint = build_chat_response_language_hint("Summarize this document")
    assert "same language" in hint
