"""
Zerochan Crawler Module - Alternative to Pinterest
Zerochan is an anime/manga image board with accessible search
"""

import asyncio
import re
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    MIN_WIDTH, MIN_HEIGHT, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, MAX_RETRIES,
    CHARACTERS, SEARCH_KEYWORDS
)

ZEROCHAN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}


@dataclass
class ZerochanImage:
    """Represents a Zerochan image"""
    id: str
    url: str
    original_url: str
    width: int
    height: int
    description: str = ''
    tags: list = field(default_factory=list)
    source: str = 'zerochan'
    # Computed scores
    quality_score: float = 0.0
    character_score: float = 0.0
    style_score: float = 0.0
    total_score: float = 0.0
    detected_character: str = ''


class ZerochanCrawler:
    """Crawls Zerochan for xianxia/cultivation images"""

    BASE_URL = 'https://www.zerochan.net'

    def __init__(self):
        self.session = None
        self.images: list[ZerochanImage] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=ZEROCHAN_HEADERS)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch HTML from URL"""
        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        await asyncio.sleep(30 * (attempt + 1))
                    else:
                        print(f'Error {response.status} for {url}')
                        return None
            except Exception as e:
                print(f'Attempt {attempt + 1} failed: {e}')
                await asyncio.sleep(5)
        return None

    def _extract_images_from_search(self, html: str) -> list[dict]:
        """Extract image data from search results page"""
        soup = BeautifulSoup(html, 'lxml')
        images = []

        # Find all image items
        items = soup.select('ul#thumbs2 li')

        for item in items:
            try:
                link = item.select_one('a')
                img = item.select_one('img')

                if not link or not img:
                    continue

                # Get image ID from link
                href = link.get('href', '')
                img_id = href.split('/')[-1] if href else ''

                # Get thumbnail URL and convert to full size
                thumb_url = img.get('src', '')
                if not thumb_url:
                    continue

                # Parse dimensions from title or estimate
                title = img.get('title', '') or img.get('alt', '')

                images.append({
                    'id': img_id,
                    'thumb_url': thumb_url,
                    'title': title,
                    'page_url': f'{self.BASE_URL}{href}',
                })
            except Exception as e:
                continue

        return images

    async def _get_full_image_details(self, page_url: str) -> Optional[dict]:
        """Get full image details from detail page"""
        html = await self._fetch_page(page_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')

        try:
            # Get full-size image URL
            img = soup.select_one('#large img') or soup.select_one('.preview img')
            if not img:
                return None

            url = img.get('src', '')
            if not url:
                return None

            # Parse dimensions
            width = 0
            height = 0

            # Try to get from meta or image dimensions
            size_text = soup.select_one('.resolution')
            if size_text:
                match = re.search(r'(\d+)\s*x\s*(\d+)', size_text.text)
                if match:
                    width = int(match.group(1))
                    height = int(match.group(2))

            # Get tags
            tags = []
            tag_links = soup.select('#tags li a')
            for tag in tag_links:
                tags.append(tag.text.strip())

            # Get description
            description = ' '.join(tags[:10])

            return {
                'url': url,
                'width': width,
                'height': height,
                'tags': tags,
                'description': description,
            }
        except Exception as e:
            print(f'Error parsing details: {e}')
            return None

    async def search(self, query: str, max_results: int = 50) -> list[ZerochanImage]:
        """Search Zerochan for images"""
        print(f'Searching Zerochan: "{query}"')
        images = []
        page = 1

        search_url = f'{self.BASE_URL}/search?q={quote_plus(query)}'

        with tqdm(total=max_results, desc=f'Crawling "{query[:20]}..."') as pbar:
            while len(images) < max_results:
                url = f'{search_url}&p={page}' if page > 1 else search_url
                html = await self._fetch_page(url)

                if not html:
                    break

                items = self._extract_images_from_search(html)
                if not items:
                    break

                for item in items:
                    if len(images) >= max_results:
                        break

                    # Get full details
                    details = await self._get_full_image_details(item['page_url'])

                    if details and details['width'] >= MIN_WIDTH and details['height'] >= MIN_HEIGHT:
                        img = ZerochanImage(
                            id=item['id'],
                            url=details['url'],
                            original_url=item['page_url'],
                            width=details['width'],
                            height=details['height'],
                            description=details['description'],
                            tags=details['tags'],
                        )
                        images.append(img)
                        pbar.update(1)

                    await asyncio.sleep(REQUEST_DELAY_MIN)

                page += 1
                if page > 10:  # Max 10 pages
                    break

        print(f'Found {len(images)} images for "{query}"')
        return images

    async def crawl_xianxia_keywords(self, max_per_keyword: int = 30) -> list[ZerochanImage]:
        """Crawl xianxia-related keywords"""
        # Zerochan-specific xianxia/donghua keywords
        keywords = [
            'Xianxia',
            'Chinese Animation',
            'Douluo Dalu',
            'Battle Through the Heavens',
            'Doupo Cangqiong',
            'Soul Land',
            'Perfect World',
            'Swallowed Star',
            'Martial Universe',
            'The Great Ruler',
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
            await asyncio.sleep(5)  # Longer delay between keywords

        self.images = all_images
        return all_images


# Alternative: Web search-based crawler
class WebSearchCrawler:
    """Crawls images using web search results (Google/Bing)"""

    BING_URL = 'https://www.bing.com/images/search'

    def __init__(self):
        self.session = None
        self.images = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=ZEROCHAN_HEADERS)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def search_bing(self, query: str, max_results: int = 50) -> list[dict]:
        """Search Bing Images"""
        images = []
        params = {
            'q': f'{query} wallpaper 4k',
            'first': 1,
            'count': 35,
            'qft': '+filterui:imagesize-large',  # Large images only
        }

        try:
            async with self.session.get(self.BING_URL, params=params) as response:
                if response.status != 200:
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'lxml')

                # Find image links
                for item in soup.select('a.iusc'):
                    try:
                        import json
                        data = json.loads(item.get('m', '{}'))

                        if data.get('murl'):
                            images.append({
                                'id': str(len(images)),
                                'url': data['murl'],
                                'width': data.get('pwidth', 0) or 1920,
                                'height': data.get('pheight', 0) or 1080,
                                'description': data.get('t', ''),
                                'source': data.get('purl', ''),
                            })

                        if len(images) >= max_results:
                            break
                    except:
                        continue

        except Exception as e:
            print(f'Bing search error: {e}')

        return images


async def main():
    """Test Zerochan crawler"""
    async with ZerochanCrawler() as crawler:
        images = await crawler.search('xianxia', max_results=10)
        print(f'\nFound {len(images)} images')

        for img in images[:5]:
            print(f'  - {img.width}x{img.height}: {img.description[:50]}...')
            print(f'    URL: {img.url[:80]}...')


if __name__ == '__main__':
    asyncio.run(main())
