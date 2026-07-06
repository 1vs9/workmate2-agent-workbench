# -*- coding: utf-8 -*-
"""User-visible chat message text (strip composer skill injection)."""

from __future__ import annotations

_SKILL_DISPLAY_MARKER = "the user's task:"
_CHINESE_SKILL_DISPLAY_MARKER = "完成用户任务："
_LOCALE_HINT_OPEN = "<agentdesk-locale-hint>"
_LOCALE_HINT_CLOSE = "</agentdesk-locale-hint>"


def _strip_locale_hint(raw: str) -> str:
    start = raw.find(_LOCALE_HINT_OPEN)
    if start < 0:
        return raw
    end = raw.find(_LOCALE_HINT_CLOSE, start)
    if end < 0:
        return raw
    return (raw[:start] + raw[end + len(_LOCALE_HINT_CLOSE) :]).lstrip()


def display_user_message_content(content: str) -> str:
    """Strip composer skill injection from stored user turns (UI display)."""
    raw = _strip_locale_hint((content or "").strip())
    if not raw:
        return ""
    zh_marker_idx = raw.find(_CHINESE_SKILL_DISPLAY_MARKER)
    if zh_marker_idx >= 0:
        rest = raw[zh_marker_idx + len(_CHINESE_SKILL_DISPLAY_MARKER) :].lstrip()
        body_split = rest.find("\n\n")
        if body_split >= 0:
            rest = rest[:body_split].strip()
        if rest:
            return rest
    marker_idx = raw.find(_SKILL_DISPLAY_MARKER)
    if marker_idx >= 0:
        rest = raw[marker_idx + len(_SKILL_DISPLAY_MARKER) :].lstrip()
        body_split = rest.find("\n\n")
        if body_split >= 0:
            rest = rest[:body_split].strip()
        if rest:
            return rest
    user_msg_marker = "\n\n---\n\nUser message:\n"
    if user_msg_marker in raw:
        return raw.rsplit(user_msg_marker, 1)[-1].strip()
    return raw
