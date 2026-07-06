# -*- coding: utf-8 -*-
"""Concurrent store access regression tests (Windows file-lock path)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from qwenpaw.agentdesk.store import AgentDeskStore


def test_concurrent_get_by_key_and_upsert(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key("plaza", "name", "seed", {"name": "seed", "desc": "x"})

    def reader(index: int) -> int:
        for _ in range(20):
            item = store.get_by_key("plaza", "name", "seed")
            if item is None or item.get("name") != "seed":
                raise AssertionError(f"missing seed on read {index}")
        return index

    def writer(index: int) -> int:
        for offset in range(20):
            store.upsert_by_key(
                "employees",
                "name",
                f"emp-{index}-{offset}",
                {"name": f"emp-{index}-{offset}", "desc": "worker"},
            )
        return index

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [
            * [pool.submit(reader, i) for i in range(6)],
            * [pool.submit(writer, i) for i in range(6)],
        ]
        for future in as_completed(futures):
            future.result()

    assert len(store.list_items("employees")) == 120
