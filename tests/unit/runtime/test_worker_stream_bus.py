# -*- coding: utf-8 -*-
"""Tests for the worker stream bus used to surface live worker progress."""

import asyncio

import pytest

from qwenpaw.runtime.worker_stream_bus import WorkerStreamBus


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber():
    bus = WorkerStreamBus()
    queue = bus.subscribe("leader:session")

    assert bus.has_subscribers("leader:session") is True

    bus.publish("leader:session", "data: {\"a\": 1}")
    # Allow the cross-thread-safe callback to run on this loop.
    await asyncio.sleep(0)

    assert queue.get_nowait() == "data: {\"a\": 1}"


@pytest.mark.asyncio
async def test_publish_without_subscriber_is_noop():
    bus = WorkerStreamBus()
    assert bus.has_subscribers("missing") is False
    # Should not raise even when nobody is listening.
    bus.publish("missing", "data: {}")


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = WorkerStreamBus()
    queue = bus.subscribe("k")
    bus.unsubscribe("k", queue)

    assert bus.has_subscribers("k") is False
    bus.publish("k", "data: {}")
    await asyncio.sleep(0)
    assert queue.empty()


@pytest.mark.asyncio
async def test_blank_key_or_line_ignored():
    bus = WorkerStreamBus()
    queue = bus.subscribe("k")
    bus.publish("k", "")
    bus.publish("", "data: {}")
    await asyncio.sleep(0)
    assert queue.empty()
