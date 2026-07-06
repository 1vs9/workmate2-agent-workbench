# -*- coding: utf-8 -*-
"""Deterministic tool-style icon keys for skills (no emoji)."""

from __future__ import annotations

import re

SKILL_ICON_KEYS: frozenset[str] = frozenset(
    {
        "fileText",
        "table",
        "presentation",
        "filePdf",
        "global",
        "read",
        "folder",
        "bulb",
        "team",
        "idcard",
        "calendar",
        "lineChart",
        "message",
        "mail",
        "code",
        "search",
        "cloud",
        "shop",
        "link",
        "api",
        "security",
        "tool",
    }
)

_FALLBACK_KEYS: tuple[str, ...] = (
    "tool",
    "api",
    "code",
    "search",
    "folder",
    "fileText",
    "read",
    "bulb",
)

_NAME_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^docx$|^word", re.I), "fileText"),
    (re.compile(r"^xlsx$|^excel", re.I), "table"),
    (re.compile(r"^pptx$|^ppt", re.I), "presentation"),
    (re.compile(r"^pdf$", re.I), "filePdf"),
    (re.compile(r"browser|web|crawl", re.I), "global"),
    (re.compile(r"^news$|资讯|舆情", re.I), "read"),
    (re.compile(r"make[_-]?plan|计划|规划", re.I), "calendar"),
    (re.compile(r"file[_-]?reader|文件阅读", re.I), "read"),
    (re.compile(r"make[_-]?skill|skill[_-]?creator|技能创作", re.I), "bulb"),
    (re.compile(r"multi[_-]?agent|协作", re.I), "team"),
    (re.compile(r"employee[_-]?creator|员工创建", re.I), "idcard"),
    (re.compile(r"stock|finance|chart|分析|数据", re.I), "lineChart"),
    (re.compile(r"channel[_-]?message|消息|飞书|slack|dingtalk", re.I), "message"),
    (re.compile(r"himalaya|mail|email|邮件", re.I), "mail"),
    (re.compile(r"cron|schedule|定时", re.I), "calendar"),
    (re.compile(r"guidance|qa|index", re.I), "search"),
    (re.compile(r"chat[_-]?with", re.I), "message"),
    (re.compile(r"cdp|browser_cdp", re.I), "api"),
    (re.compile(r"security|auth|encrypt|合规", re.I), "security"),
    (re.compile(r"code|git|dev|script|编程", re.I), "code"),
)


def is_skill_icon_key(value: str | None) -> bool:
    return bool(value and value in SKILL_ICON_KEYS)


def derive_skill_icon_key(name: str, description: str = "") -> str:
    """Return a stable tool icon key from skill name/description."""
    text = f"{(name or '').strip().lower()} {description or ''}".strip()
    for pattern, icon_key in _NAME_RULES:
        if pattern.search(text):
            return icon_key
    seed = (name or "skill").strip().lower()
    digest = 0
    for char in seed:
        digest = (digest * 31 + ord(char)) & 0xFFFFFFFF
    return _FALLBACK_KEYS[digest % len(_FALLBACK_KEYS)]
