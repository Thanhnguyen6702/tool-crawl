"""
Pinterest Crawler Module
Crawls images from Pinterest search and boards
"""

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    PINTEREST_HEADERS, SEARCH_KEYWORDS, CHARACTERS,
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, MAX_RETRIES,
    MIN_WIDTH, MIN_HEIGHT
)


@dataclass
class PinterestImage:
    """Represents a Pinterest image with metadata"""
    id: str
    url: str
    original_url: str
    width: int
    height: int
    description: str = ''
    repin_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    source: str = ''
    board_name: str = ''
    pinner: str = ''
    created_at: str = ''
    # Computed scores
    quality_score: float = 0.0
    character_score: float = 0.0
    style_score: float = 0.0
    total_score: float = 0.0
    detected_character: str = ''
    tags: list = field(default_factory=list)


class PinterestCrawler:
    """Crawls Pinterest for xianxia wallpapers"""

    BASE_URL = 'https://www.pinterest.com'
    SEARCH_URL = 'https://www.pinterest.com/resource/BaseSearchResource/get/'
    BOARD_URL = 'https://www.pinterest.com/resource/BoardFeedResource/get/'

    def __init__(self):
        self.session = None
        self.images: list[PinterestImage] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=PINTEREST_HEADERS)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _random_delay(self):
        """Random delay to avoid rate limiting"""
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def _build_search_params(self, query: str, bookmark: str = '') -> dict:
        """Build Pinterest search API parameters"""
        options = {
            'query': query,
            'scope': 'pins',
            'rs': 'typed',
            'source_url': f'/search/pins/?q={quote_plus(query)}&rs=typed',
        }

        if bookmark:
            options['bookmarks'] = [bookmark]

        return {
            'source_url': f'/search/pins/?q={quote_plus(query)}',
            'data': json.dumps({
                'options': options,
                'context': {}
            })
        }

    async def _fetch_search_page(self, query: str, bookmark: str = '') -> tuple[list, str]:
        """Fetch a single page of search results"""
        params = self._build_search_params(query, bookmark)

        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.get(self.SEARCH_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        resource = data.get('resource_response', {})
                        results = resource.get('data', {}).get('results', [])
                        next_bookmark = resource.get('bookmark', '')
                        return results, next_bookmark
                    elif response.status == 429:
                        print(f'Rate limited, waiting {30 * (attempt + 1)}s...')
                        await asyncio.sleep(30 * (attempt + 1))
                    else:
                        print(f'Error {response.status} fetching search page')
                        return [], ''
            except Exception as e:
                print(f'Attempt {attempt + 1} failed: {e}')
                await asyncio.sleep(5)

        return [], ''

    def _extract_image_data(self, pin: dict) -> Optional[PinterestImage]:
        """Extract image data from a Pinterest pin object"""
        try:
            # Get image info
            images = pin.get('images', {})
            orig = images.get('orig', {}) or images.get('736x', {}) or {}

            url = orig.get('url', '')
            width = orig.get('width', 0)
            height = orig.get('height', 0)

            # Skip low quality images
            if width < MIN_WIDTH or height < MIN_HEIGHT:
                return None

            if not url:
                return None

            # Extract other metadata
            return PinterestImage(
                id=str(pin.get('id', '')),
                url=url,
                original_url=pin.get('link', url),
                width=width,
                height=height,
                description=pin.get('description', '') or pin.get('title', ''),
                repin_count=pin.get('repin_count', 0) or 0,
                like_count=pin.get('like_count', 0) or 0,
                comment_count=pin.get('comment_count', 0) or 0,
                source=pin.get('domain', ''),
                board_name=pin.get('board', {}).get('name', ''),
                pinner=pin.get('pinner', {}).get('username', ''),
                created_at=pin.get('created_at', ''),
            )
        except Exception as e:
            print(f'Error extracting image data: {e}')
            return None

    async def search(self, query: str, max_results: int = 100) -> list[PinterestImage]:
        """Search Pinterest for images"""
        print(f'Searching: "{query}"')
        images = []
        bookmark = ''
        pages = 0
        max_pages = (max_results // 25) + 2

        with tqdm(total=max_results, desc=f'Crawling "{query[:20]}..."') as pbar:
            while len(images) < max_results and pages < max_pages:
                results, bookmark = await self._fetch_search_page(query, bookmark)

                if not results:
                    break

                for pin in results:
                    img = self._extract_image_data(pin)
                    if img:
                        images.append(img)
                        pbar.update(1)
                        if len(images) >= max_results:
                            break

                pages += 1
                self._random_delay()

                if not bookmark:
                    break

        print(f'Found {len(images)} images for "{query}"')
        return images

    async def crawl_all_keywords(self, max_per_keyword: int = 50) -> list[PinterestImage]:
        """Crawl all configured search keywords"""
        all_images = []
        seen_ids = set()

        for keyword in SEARCH_KEYWORDS:
            images = await self.search(keyword, max_per_keyword)

            # Deduplicate by ID
            for img in images:
                if img.id not in seen_ids:
                    seen_ids.add(img.id)
                    all_images.append(img)

            print(f'Total unique images: {len(all_images)}')

        self.images = all_images
        return all_images

    def save_raw_results(self, filepath: str = 'raw_results.json'):
        """Save raw crawled results to JSON"""
        data = [asdict(img) for img in self.images]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'Saved {len(self.images)} images to {filepath}')


# Alternative: Use Playwright for JavaScript rendering
class PlaywrightCrawler:
    """Fallback crawler using Playwright for JS-rendered content"""

    def __init__(self):
        self.browser = None
        self.page = None

    async def setup(self):
        """Initialize Playwright browser"""
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        await self.page.set_extra_http_headers(PINTEREST_HEADERS)

    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def search(self, query: str, max_results: int = 100) -> list[dict]:
        """Search Pinterest using browser automation"""
        if not self.page:
            await self.setup()

        url = f'https://www.pinterest.com/search/pins/?q={quote_plus(query)}'
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')

        images = []
        scroll_count = 0
        max_scrolls = max_results // 20 + 5

        while len(images) < max_results and scroll_count < max_scrolls:
            # Extract images from page
            pins = await self.page.query_selector_all('[data-test-id="pin"]')

            for pin in pins:
                try:
                    img = await pin.query_selector('img')
                    if img:
                        src = await img.get_attribute('src')
                        alt = await img.get_attribute('alt') or ''

                        if src and 'pinimg.com' in src:
                            # Convert to original size
                            orig_url = re.sub(r'/\d+x/', '/originals/', src)
                            images.append({
                                'url': orig_url,
                                'description': alt,
                            })
                except:
                    pass

            # Scroll down
            await self.page.evaluate('window.scrollBy(0, 1000)')
            await asyncio.sleep(1)
            scroll_count += 1

        return images[:max_results]


async def main():
    """Test crawler"""
    async with PinterestCrawler() as crawler:
        # Test with one keyword
        images = await crawler.search('xianxia wallpaper 4k', max_results=20)
        print(f'\nFound {len(images)} images')

        for img in images[:5]:
            print(f'  - {img.width}x{img.height}: {img.description[:50]}...')

        crawler.images = images
        crawler.save_raw_results('test_results.json')


if __name__ == '__main__':
    asyncio.run(main())
