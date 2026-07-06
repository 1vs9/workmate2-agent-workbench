# -*- coding: utf-8 -*-
"""Lightweight locale hints for AgentDesk user-facing generation."""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_BUILTIN_SKILL_LANGUAGES = frozenset({"en", "zh"})


def detect_user_language(text: str, *, default: str = "zh") -> str:
    """Infer response language from user text (zh vs en)."""
    sample = (text or "").strip()
    if not sample:
        normalized_default = str(default or "zh").strip().lower()
        return normalized_default if normalized_default in _BUILTIN_SKILL_LANGUAGES else "zh"

    cjk_chars = len(_CJK_RE.findall(sample))
    latin_chars = len(re.findall(r"[A-Za-z]", sample))
    if cjk_chars >= 2 or (cjk_chars > 0 and cjk_chars >= latin_chars):
        return "zh"
    if latin_chars >= 8 and cjk_chars == 0:
        return "en"
    normalized_default = str(default or "zh").strip().lower()
    return normalized_default if normalized_default in _BUILTIN_SKILL_LANGUAGES else "zh"


def is_chinese_language(language: str | None) -> bool:
    return str(language or "").strip().lower().startswith("zh")


_CHAT_LOCALE_HINT_TAG = "agentdesk-locale-hint"


def build_chat_response_language_hint(user_text: str) -> str:
    """Short per-turn hint prepended to the agent message (not shown in UI)."""
    language = detect_user_language(user_text)
    if is_chinese_language(language):
        return (
            f"<{_CHAT_LOCALE_HINT_TAG}>"
            "本轮请使用中文回复；不要默认套用英文 FAQ/Q&A 模板、英文小节标题或英文问答结构，"
            "除非用户明确要求英文。"
            f"</{_CHAT_LOCALE_HINT_TAG}>\n\n"
        )
    return (
        f"<{_CHAT_LOCALE_HINT_TAG}>"
        "Reply in the same language as the user's message. "
        "Do not default to a different language or FAQ/Q&A template unless asked."
        f"</{_CHAT_LOCALE_HINT_TAG}>\n\n"
    )
