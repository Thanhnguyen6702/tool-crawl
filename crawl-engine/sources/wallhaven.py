"""
Wallhaven Source — Crawls wallhaven.cc via public API.
API docs: https://wallhaven.cc/help/api
"""

import asyncio
import logging
from typing import AsyncIterator, Optional

import aiohttp

from sources.base import CrawlSource, CrawlItem

log = logging.getLogger(__name__)


class WallhavenSource(CrawlSource):
    """Wallhaven wallpaper source."""

    API_BASE = "https://wallhaven.cc/api/v1"

    @property
    def name(self) -> str:
        return "wallhaven"

    async def setup(self):
        headers = self.default_headers()
        api_key = self.config.get("api_key")
        if api_key:
            headers["X-API-Key"] = api_key
        self._session = aiohttp.ClientSession(headers=headers)
        self._delay = self.config.get("delay", 2)
        self._categories = self.config.get("categories", "010")  # anime
        self._purity = self.config.get("purity", "100")  # sfw
        self._sorting = self.config.get("sorting", "favorites")
        self._min_res = self.config.get("min_resolution", "720x720")

    async def teardown(self):
        if hasattr(self, "_session") and self._session:
            await self._session.close()

    async def _fetch(self, endpoint: str, params: dict | None = None) -> Optional[dict]:
        url = f"{self.API_BASE}/{endpoint}"
        try:
            async with self._session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 429:
                    log.warning("Wallhaven rate limited, waiting 60s")
                    await asyncio.sleep(60)
                    return await self._fetch(endpoint, params)
                log.error(f"Wallhaven API {resp.status}: {await resp.text()}")
        except Exception as e:
            log.error(f"Wallhaven fetch error: {e}")
        return None

    def _parse_item(self, data: dict) -> Optional[CrawlItem]:
        width = data.get("dimension_x", 0)
        height = data.get("dimension_y", 0)
        tags = [t.get("name", "") for t in data.get("tags", [])]

        return CrawlItem(
            source_id=str(data.get("id", "")),
            url=data.get("path", ""),
            width=width,
            height=height,
            title="",
            description=", ".join(tags[:15]),
            tags=tags,
            views=data.get("views", 0),
            favorites=data.get("favorites", 0),
            likes=data.get("favorites", 0),
            metadata={
                "category": data.get("category", ""),
                "purity": data.get("purity", ""),
                "colors": data.get("colors", []),
                "wallhaven_url": data.get("url", ""),
            },
        )

    async def crawl(
        self, keywords: list[str], max_per_keyword: int = 50
    ) -> AsyncIterator[CrawlItem]:
        for keyword in keywords:
            log.info(f'Wallhaven: searching "{keyword}"')
            count = 0
            page = 1

            while count < max_per_keyword:
                params = {
                    "q": keyword,
                    "categories": self._categories,
                    "purity": self._purity,
                    "sorting": self._sorting,
                    "order": "desc",
                    "atleast": self._min_res,
                    "page": page,
                }

                data = await self._fetch("search", params)
                if not data or "data" not in data:
                    break

                wallpapers = data["data"]
                if not wallpapers:
                    break

                for wp in wallpapers:
                    if count >= max_per_keyword:
                        break
                    item = self._parse_item(wp)
                    if item and item.url:
                        yield item
                        count += 1

                meta = data.get("meta", {})
                if page >= meta.get("last_page", 1):
                    break

                page += 1
                await asyncio.sleep(self._delay)

            log.info(f'Wallhaven: found {count} for "{keyword}"')
