# -*- coding: utf-8 -*-
"""AgentDesk / WorkBuddy compatibility layer on top of QwenPaw."""

from .settings import get_bundled_frontend_dir, get_frontend_dir, is_agentdesk_enabled

__all__ = [
    "get_bundled_frontend_dir",
    "get_frontend_dir",
    "is_agentdesk_enabled",
]
