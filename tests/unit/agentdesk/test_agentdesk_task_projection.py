# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.task_projection import task_for_client, task_sort_key


def test_task_sort_key_prefers_created_at_then_updated_at() -> None:
    assert task_sort_key({"created_at": 10, "updated_at": 20}) == 10.0
    assert task_sort_key({"updated_at": 20}) == 20.0
    assert task_sort_key({"created_at": "bad"}) == 0.0


def test_task_for_client_projects_messages_and_created_at() -> None:
    projected = task_for_client(
        {
            "id": "task-1",
            "created_at": 123,
            "messages": [
                {"role": "assistant", "content": "hello"},
                "bad",
            ],
        },
    )

    assert projected["createdAt"] == 123
    assert projected["messages"] == [{"role": "assistant", "content": "hello"}]
