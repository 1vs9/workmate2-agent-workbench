# -*- coding: utf-8 -*-
"""Tests for CloudPaw ACP permission auto-approve helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLE_ROOT = _REPO_ROOT / "plugins" / "bundle"
if str(_BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BUNDLE_ROOT))

from cloudpaw import hooks  # noqa: E402  pylint: disable=wrong-import-position


@pytest.mark.parametrize(
    ("options", "expected_id"),
    [
        (
            [
                {"optionId": "allow_always", "kind": "allow_always"},
                {"optionId": "allow_once", "kind": "allow_once"},
            ],
            "allow_once",
        ),
        (
            [
                {"optionId": "proceed_always", "kind": "proceed_always"},
                {"optionId": "proceed_once", "kind": "proceed_once"},
            ],
            "proceed_once",
        ),
        (
            [{"optionId": "allow_always", "kind": "allow_always"}],
            "allow_always",
        ),
    ],
)
def test_pick_allow_option_prefers_one_shot_grants(
    options: list[dict[str, str]],
    expected_id: str,
) -> None:
    selected = hooks._pick_allow_option(options)
    assert selected is not None
    assert selected["optionId"] == expected_id


def test_acp_auto_approve_enabled_from_environ() -> None:
    env_key = hooks._ACP_AUTO_APPROVE_ENV
    with patch.dict(os.environ, {env_key: "true"}, clear=False):
        assert hooks._acp_auto_approve_enabled() is True
    with patch.dict(os.environ, {env_key: "0"}, clear=False):
        assert hooks._acp_auto_approve_enabled() is False


def test_acp_auto_approve_enabled_from_envs_json() -> None:
    env_key = hooks._ACP_AUTO_APPROVE_ENV
    env = {k: v for k, v in os.environ.items() if k != env_key}
    with patch.dict(os.environ, env, clear=True):
        with patch(
            "qwenpaw.envs.load_envs",
            return_value={env_key: "yes"},
        ):
            assert hooks._acp_auto_approve_enabled() is True


def test_acp_auto_approve_disabled_by_default() -> None:
    env_key = hooks._ACP_AUTO_APPROVE_ENV
    env = {k: v for k, v in os.environ.items() if k != env_key}
    with patch.dict(os.environ, env, clear=True):
        with patch("qwenpaw.envs.load_envs", return_value={}):
            assert hooks._acp_auto_approve_enabled() is False
