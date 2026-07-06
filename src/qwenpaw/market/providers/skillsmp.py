# -*- coding: utf-8 -*-
"""SkillsMP market provider.

Public REST API:

    GET https://skillsmp.com/api/v1/skills/search
        ?q=&page=&limit=&sortBy=

Optional Bearer auth via ``SKILLSMP_API_KEY`` or ``QWENPAW_SKILLSMP_API_KEY``
raises the daily quota (see skillsmp.com/docs/api).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ...agents.skill_system.hub import http_json_get
from ..schema import MarketResult
from .base import MARKET_SEARCH_TIMEOUT_S


_BASE_URL = "https://skillsmp.com"
_SEARCH_PATH = "/api/v1/skills/search"
_MAX_PAGE_SIZE = 100
_DEFAULT_BROWSE_QUERY = "skill"
_API_KEY_ENV_KEYS = ("SKILLSMP_API_KEY", "QWENPAW_SKILLSMP_API_KEY")


def _api_key() -> str | None:
    for key in _API_KEY_ENV_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


def _search_headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


class SkillsMPProvider:
    key = "skillsmp"
    label = "SkillsMP"

    def available(self) -> tuple[bool, str | None]:
        return True, None

    async def search(
        self,
        query: str,
        limit: int,
        page: int,
    ) -> tuple[list[MarketResult], bool, int | None]:
        url = f"{_BASE_URL}{_SEARCH_PATH}"
        page_size = max(1, min(int(limit), _MAX_PAGE_SIZE))
        needle = query.strip() or _DEFAULT_BROWSE_QUERY
        params: dict[str, str | int] = {
            "q": needle,
            "page": max(1, int(page)),
            "limit": page_size,
            "sortBy": "stars",
        }
        headers = _search_headers()
        try:
            if headers:
                body = await _http_json_get_with_headers(
                    url,
                    params=params,
                    headers=headers,
                    timeout=MARKET_SEARCH_TIMEOUT_S,
                )
            else:
                body = await http_json_get(
                    url,
                    params=params,
                    timeout=MARKET_SEARCH_TIMEOUT_S,
                )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"SkillsMP search returned HTTP {e.response.status_code}",
            ) from e

        if not isinstance(body, dict) or not body.get("success", True):
            message = _extract_error_message(body)
            raise RuntimeError(f"SkillsMP search failed: {message}")

        data = body.get("data") if isinstance(body, dict) else None
        items: list[dict[str, object]] = []
        has_more = False
        upstream_total: int | None = None

        if isinstance(data, dict):
            raw_skills = data.get("skills")
            if isinstance(raw_skills, list):
                items = [s for s in raw_skills if isinstance(s, dict)]
            pagination = data.get("pagination")
            if isinstance(pagination, dict):
                has_more = bool(pagination.get("hasNext"))
                raw_total = pagination.get("total")
                if isinstance(raw_total, int) and raw_total >= 0:
                    upstream_total = raw_total

        results: list[MarketResult] = []
        for item in items:
            converted = _to_market_result(item)
            if converted is not None:
                results.append(converted)

        total = upstream_total if upstream_total is not None else len(results)
        if not isinstance(data, dict) or not isinstance(data.get("pagination"), dict):
            has_more = page * page_size < total
        return results, has_more, total


async def _http_json_get_with_headers(
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    timeout_val = timeout or MARKET_SEARCH_TIMEOUT_S
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_val),
        follow_redirects=True,
        headers={
            "User-Agent": "qwenpaw-skills-hub/1.0",
            **(headers or {}),
        },
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _extract_error_message(body: Any) -> str:
    if not isinstance(body, dict):
        return "non-JSON response"
    err = body.get("error")
    if isinstance(err, dict):
        message = _opt_str(err.get("message"))
        if message:
            return message
    return _opt_str(body.get("message")) or "unknown error"


def _to_market_result(item: dict[str, object]) -> MarketResult | None:
    slug = _str(item.get("id"))
    if not slug:
        return None
    name = _str(item.get("name")) or slug
    source_url = _opt_str(item.get("skillUrl")) or f"{_BASE_URL}/skills/{slug}"
    stats: dict[str, str | int] = {}
    stars = _opt_int(item.get("stars"))
    if stars is not None:
        stats["stars"] = stars
    updated = _opt_str(item.get("updatedAt"))
    if updated:
        stats["updated_at"] = updated
    github = _opt_str(item.get("githubUrl"))
    if github:
        stats["github"] = github
    return MarketResult(
        source="skillsmp",
        slug=slug,
        name=name,
        description=_opt_str(item.get("description")),
        source_url=source_url,
        version=None,
        author=_opt_str(item.get("author")),
        icon_url=None,
        stats=stats or None,
    )


def _str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _opt_str(value: object) -> str | None:
    s = _str(value)
    return s or None


def _opt_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


provider = SkillsMPProvider()
