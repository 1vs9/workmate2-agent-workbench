# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import http_boundary


def test_body_dict_returns_mutable_copy() -> None:
    source = {"name": "Analyst"}

    copied = http_boundary.body_dict(source)
    copied["name"] = "Planner"

    assert source == {"name": "Analyst"}
    assert copied == {"name": "Planner"}
    assert http_boundary.body_dict(None) == {}


@pytest.mark.parametrize(
    ("raiser", "status_code"),
    [
        (http_boundary.raise_bad_request, 400),
        (http_boundary.raise_conflict, 409),
        (http_boundary.raise_bad_gateway, 502),
    ],
)
def test_raise_http_exception_from_error(raiser, status_code) -> None:
    original = ValueError("bad input")

    with pytest.raises(HTTPException) as exc:
        raiser(original)

    assert exc.value.status_code == status_code
    assert exc.value.detail == "bad input"
    assert exc.value.__cause__ is original


def test_raise_not_found_allows_stable_public_detail() -> None:
    original = LookupError("internal missing id")

    with pytest.raises(HTTPException) as exc:
        http_boundary.raise_not_found(original, detail="Not found")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Not found"
    assert exc.value.__cause__ is original
