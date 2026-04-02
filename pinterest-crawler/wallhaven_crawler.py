"""
Wallhaven Crawler Module
Wallhaven has a public API for high-quality wallpapers
API Docs: https://wallhaven.cc/help/api
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from tqdm import tqdm

from config import MIN_WIDTH, MIN_HEIGHT, REQUEST_DELAY_MIN


@dataclass
class WallhavenImage:
    """Represents a Wallhaven wallpaper"""
    id: str
    url: str
    original_url: str
    width: int
    height: int
    description: str = ''
    tags: list = field(default_factory=list)
    source: str = 'wallhaven'
    category: str = ''
    purity: str = 'sfw'
    views: int = 0
    favorites: int = 0
    colors: list = field(default_factory=list)
    # Computed scores
    quality_score: float = 0.0
    character_score: float = 0.0
    style_score: float = 0.0
    total_score: float = 0.0
    detected_character: str = ''
    repin_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class WallhavenCrawler:
    """Crawls Wallhaven for xianxia/anime wallpapers"""

    API_BASE = 'https://wallhaven.cc/api/v1'

    def __init__(self, api_key: str = None):
        self.api_key = api_key  # Optional for NSFW
        self.session = None
        self.images: list[WallhavenImage] = []

    async def __aenter__(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        self.session = aiohttp.ClientSession(headers=headers)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _fetch_api(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Fetch from Wallhaven API"""
        url = f'{self.API_BASE}/{endpoint}'
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    print('Rate limited, waiting 60s...')
                    await asyncio.sleep(60)
                    return await self._fetch_api(endpoint, params)
                else:
                    print(f'API Error {response.status}: {await response.text()}')
                    return None
        except Exception as e:
            print(f'Fetch error: {e}')
            return None

    def _parse_wallpaper(self, data: dict) -> Optional[WallhavenImage]:
        """Parse wallpaper data from API response"""
        try:
            # Skip low resolution
            width = data.get('dimension_x', 0)
            height = data.get('dimension_y', 0)

            if width < MIN_WIDTH or height < MIN_HEIGHT:
                return None

            # Extract tags
            tags = [t.get('name', '') for t in data.get('tags', [])]
            description = ', '.join(tags[:10])

            # Get highest resolution URL
            url = data.get('path', '')

            return WallhavenImage(
                id=data.get('id', ''),
                url=url,
                original_url=data.get('url', ''),
                width=width,
                height=height,
                description=description,
                tags=tags,
                category=data.get('category', ''),
                purity=data.get('purity', 'sfw'),
                views=data.get('views', 0),
                favorites=data.get('favorites', 0),
                colors=data.get('colors', []),
                # Map favorites to likes for scoring
                like_count=data.get('favorites', 0),
                repin_count=data.get('views', 0) // 100,
            )
        except Exception as e:
            print(f'Parse error: {e}')
            return None

    async def search(self, query: str, max_results: int = 50) -> list[WallhavenImage]:
        """
        Search Wallhaven for wallpapers

        Categories: general, anime, people
        Purity: sfw, sketchy
        Sorting: date_added, relevance, random, views, favorites, toplist
        """
        print(f'Searching Wallhaven: "{query}"')
        images = []
        page = 1

        with tqdm(total=max_results, desc=f'Crawling "{query[:20]}..."') as pbar:
            while len(images) < max_results:
                params = {
                    'q': query,
                    'categories': '010',  # anime only
                    'purity': '100',  # SFW only
                    'sorting': 'favorites',  # Best first
                    'order': 'desc',
                    'atleast': f'{MIN_WIDTH}x{MIN_HEIGHT}',
                    'page': page,
                }

                data = await self._fetch_api('search', params)

                if not data or 'data' not in data:
                    break

                wallpapers = data.get('data', [])
                if not wallpapers:
                    break

                for wp in wallpapers:
                    if len(images) >= max_results:
                        break

                    img = self._parse_wallpaper(wp)
                    if img:
                        images.append(img)
                        pbar.update(1)

                # Check if more pages available
                meta = data.get('meta', {})
                if page >= meta.get('last_page', 1):
                    break

                page += 1
                await asyncio.sleep(REQUEST_DELAY_MIN)

        print(f'Found {len(images)} images for "{query}"')
        return images

    async def get_tag_wallpapers(self, tag_id: int, max_results: int = 50) -> list[WallhavenImage]:
        """Get wallpapers by tag ID"""
        images = []
        page = 1

        while len(images) < max_results:
            params = {
                'q': f'id:{tag_id}',
                'categories': '010',
                'purity': '100',
                'sorting': 'favorites',
                'atleast': f'{MIN_WIDTH}x{MIN_HEIGHT}',
                'page': page,
            }

            data = await self._fetch_api('search', params)
            if not data or 'data' not in data:
                break

            for wp in data.get('data', []):
                img = self._parse_wallpaper(wp)
                if img:
                    images.append(img)
                if len(images) >= max_results:
                    break

            page += 1
            await asyncio.sleep(REQUEST_DELAY_MIN)

        return images

    async def crawl_xianxia_keywords(self, max_per_keyword: int = 30) -> list[WallhavenImage]:
        """Crawl xianxia/cultivation related keywords"""
        keywords = [
            # Direct donghua/xianxia
            'xianxia',
            'donghua',
            'chinese anime',
            'cultivation',

            # Popular series
            'soul land',
            'douluo dalu',
            'battle through the heavens',
            'doupo cangqiong',
            'perfect world anime',
            'martial universe',
            'swallowed star',
            'stellar transformations',
            'against the gods',
            'immortal',

            # Art style
            'chinese fantasy',
            'wuxia',
            'martial arts anime',
        ]

        all_images = []
        seen_ids = set()

        for keyword in keywords:
            images = await self.search(keyword, max_per_keyword)

            for img in images:
                if img.id not in seen_ids:
                    seen_ids.add(img.id)
                    all_images.append(img)

            print(f'Total unique: {len(all_images)}')
            await asyncio.sleep(3)

        self.images = all_images
        return all_images

    def save_results(self, filepath: str = 'wallhaven_results.json'):
        """Save results to JSON"""
        data = [asdict(img) for img in self.images]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'Saved {len(self.images)} images to {filepath}')


async def main():
    """Test Wallhaven crawler"""
    async with WallhavenCrawler() as crawler:
        images = await crawler.search('xianxia', max_results=10)
        print(f'\nFound {len(images)} images')

        for img in images[:5]:
            print(f'  - {img.width}x{img.height}: {img.description[:50]}...')
            print(f'    URL: {img.url[:80]}...')
            print(f'    Favorites: {img.favorites}')


if __name__ == '__main__':
    asyncio.run(main())
