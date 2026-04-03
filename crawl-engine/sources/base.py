"""
Base Source — Abstract interface for all crawl sources.
Every source plugin must subclass CrawlSource and implement crawl().
"""

import abc
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

log = logging.getLogger(__name__)


@dataclass
class CrawlItem:
    """Universal item returned by any source."""
    source_id: str
    url: str
    width: int = 0
    height: int = 0
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # Engagement
    views: int = 0
    likes: int = 0
    favorites: int = 0
    repins: int = 0
    comments: int = 0


class CrawlSource(abc.ABC):
    """
    Abstract base class for crawl sources.

    Subclass and implement:
      - crawl(keywords, max_per_keyword) -> AsyncIterator[CrawlItem]
      - name property

    Optional overrides:
      - setup() / teardown() for session lifecycle
      - default_headers() for HTTP headers
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique source identifier, e.g. 'wallhaven', 'pinterest'."""
        ...

    @abc.abstractmethod
    async def crawl(
        self, keywords: list[str], max_per_keyword: int = 50
    ) -> AsyncIterator[CrawlItem]:
        """
        Yield CrawlItems from this source.
        Must handle rate limiting and retries internally.
        """
        ...

    async def setup(self):
        """Called before crawling starts. Override to init sessions."""
        pass

    async def teardown(self):
        """Called after crawling ends. Override to cleanup."""
        pass

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, *args):
        await self.teardown()

    def default_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
