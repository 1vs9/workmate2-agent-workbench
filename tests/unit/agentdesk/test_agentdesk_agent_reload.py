# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk import agent_reload


class _Manager:
    def __init__(self, *, loaded: bool = True, fail: bool = False) -> None:
        self.loaded = loaded
        self.fail = fail
        self.reloaded: list[str] = []

    def is_agent_loaded(self, agent_id: str) -> bool:
        return self.loaded and agent_id == "agent-1"

    async def reload_agent(self, agent_id: str) -> bool:
        if self.fail:
            raise RuntimeError("boom")
        self.reloaded.append(agent_id)
        return True


def _request(manager: _Manager | None):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(multi_agent_manager=manager)),
    )


async def test_reload_agent_after_skill_mount_reloads_loaded_agent() -> None:
    manager = _Manager()

    reloaded = await agent_reload.reload_agent_after_skill_mount(
        _request(manager),
        "agent-1",
    )

    assert reloaded is True
    assert manager.reloaded == ["agent-1"]


async def test_reload_agent_after_skill_mount_skips_missing_request_or_agent() -> None:
    manager = _Manager(loaded=False)

    assert await agent_reload.reload_agent_after_skill_mount(None, "agent-1") is False
    assert (
        await agent_reload.reload_agent_after_skill_mount(_request(manager), "agent-1")
        is False
    )
    assert manager.reloaded == []


async def test_reload_agent_after_skill_mount_swallows_reload_failure() -> None:
    manager = _Manager(fail=True)

    assert (
        await agent_reload.reload_agent_after_skill_mount(_request(manager), "agent-1")
        is False
    )
