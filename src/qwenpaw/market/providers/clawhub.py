# -*- coding: utf-8 -*-
"""ClawHub market provider.

Flat /search endpoint via hub's shared async client:

    GET https://clawhub.ai/api/v1/search?q=&limit=    (no paging)

"""

from __future__ import annotations

from ...agents.skill_system.hub import search_hub_skills
from ..schema import MarketResult
from .base import MARKET_SEARCH_TIMEOUT_S


_HOMEPAGE = "https://clawhub.ai"

# ClawHub returns no rows for an empty `q`; browse with a neutral default.
_DEFAULT_BROWSE_QUERY = "skill"

# Cap upstream fetch size (ClawHub has no paging; we slice locally).
_MAX_FETCH = 200


class ClawHubProvider:
    key = "clawhub"
    label = "ClawHub"

    def available(self) -> tuple[bool, str | None]:
        return True, None

    async def search(
        self,
        query: str,
        limit: int,
        page: int,
    ) -> tuple[list[MarketResult], bool, int | None]:
        needle = query.strip() or _DEFAULT_BROWSE_QUERY
        page_size = max(1, min(int(limit), 100))
        fetch_limit = min(page_size * max(1, int(page)), _MAX_FETCH)
        raw = await search_hub_skills(
            needle,
            limit=fetch_limit,
            timeout=MARKET_SEARCH_TIMEOUT_S,
        )
        all_results: list[MarketResult] = []
        for item in raw:
            slug = (item.slug or "").strip()
            if not slug:
                continue
            source_url = item.source_url or f"{_HOMEPAGE}/{slug}"
            all_results.append(
                MarketResult(
                    source=self.key,
                    slug=slug,
                    name=item.name or slug,
                    description=item.description or None,
                    source_url=source_url,
                    version=item.version or None,
                    author=item.author or None,
                    icon_url=item.icon_url or None,
                ),
            )
        start = (page - 1) * limit
        end = start + limit
        total = len(all_results)
        return all_results[start:end], end < total, total


provider = ClawHubProvider()
