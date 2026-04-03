"""
Pinterest Source — Crawls Pinterest search via internal API.
"""

import asyncio
import json
import logging
import random
from typing import AsyncIterator, Optional
from urllib.parse import quote_plus

import aiohttp

from sources.base import CrawlSource, CrawlItem

log = logging.getLogger(__name__)


class PinterestSource(CrawlSource):
    """Pinterest image source."""

    SEARCH_URL = "https://www.pinterest.com/resource/BaseSearchResource/get/"

    @property
    def name(self) -> str:
        return "pinterest"

    async def setup(self):
        headers = {
            **self.default_headers(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pinterest.com/",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._session = aiohttp.ClientSession(headers=headers)
        self._delay_min = self.config.get("delay_min", 2)
        self._delay_max = self.config.get("delay_max", 5)
        self._min_width = self.config.get("min_width", 720)
        self._min_height = self.config.get("min_height", 720)

    async def teardown(self):
        if hasattr(self, "_session") and self._session:
            await self._session.close()

    def _build_params(self, query: str, bookmark: str = "") -> dict:
        options = {
            "query": query,
            "scope": "pins",
            "rs": "typed",
            "source_url": f"/search/pins/?q={quote_plus(query)}&rs=typed",
        }
        if bookmark:
            options["bookmarks"] = [bookmark]

        return {
            "source_url": f"/search/pins/?q={quote_plus(query)}",
            "data": json.dumps({"options": options, "context": {}}),
        }

    async def _fetch_page(self, query: str, bookmark: str = "") -> tuple[list, str]:
        params = self._build_params(query, bookmark)
        for attempt in range(3):
            try:
                async with self._session.get(
                    self.SEARCH_URL, params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        resource = data.get("resource_response", {})
                        results = resource.get("data", {}).get("results", [])
                        next_bm = resource.get("bookmark", "")
                        return results, next_bm
                    if resp.status == 429:
                        wait = 30 * (attempt + 1)
                        log.warning(f"Pinterest rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                    else:
                        log.error(f"Pinterest {resp.status}")
                        return [], ""
            except Exception as e:
                log.error(f"Pinterest attempt {attempt+1} failed: {e}")
                await asyncio.sleep(5)
        return [], ""

    def _parse_pin(self, pin: dict) -> Optional[CrawlItem]:
        images = pin.get("images", {})
        orig = images.get("orig", {}) or images.get("736x", {}) or {}

        url = orig.get("url", "")
        width = orig.get("width", 0)
        height = orig.get("height", 0)

        if width < self._min_width or height < self._min_height or not url:
            return None

        return CrawlItem(
            source_id=str(pin.get("id", "")),
            url=url,
            width=width,
            height=height,
            title=pin.get("title", ""),
            description=pin.get("description", "") or pin.get("title", ""),
            repins=pin.get("repin_count", 0) or 0,
            likes=pin.get("like_count", 0) or 0,
            comments=pin.get("comment_count", 0) or 0,
            metadata={
                "source_domain": pin.get("domain", ""),
                "board": pin.get("board", {}).get("name", ""),
                "pinner": pin.get("pinner", {}).get("username", ""),
            },
        )

    async def crawl(
        self, keywords: list[str], max_per_keyword: int = 50
    ) -> AsyncIterator[CrawlItem]:
        for keyword in keywords:
            log.info(f'Pinterest: searching "{keyword}"')
            count = 0
            bookmark = ""
            max_pages = (max_per_keyword // 25) + 2

            for _ in range(max_pages):
                if count >= max_per_keyword:
                    break

                results, bookmark = await self._fetch_page(keyword, bookmark)
                if not results:
                    break

                for pin in results:
                    if count >= max_per_keyword:
                        break
                    item = self._parse_pin(pin)
                    if item:
                        yield item
                        count += 1

                if not bookmark:
                    break

                delay = random.uniform(self._delay_min, self._delay_max)
                await asyncio.sleep(delay)

            log.info(f'Pinterest: found {count} for "{keyword}"')
