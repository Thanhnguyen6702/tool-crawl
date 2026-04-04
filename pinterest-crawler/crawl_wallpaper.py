#!/usr/bin/env python3
"""
Wallpaper Crawler - Download high quality images & videos
Sources: Wallhaven (images), Pixabay (videos), Pexels (videos)
Saves to /home/thanh/wallpaper/{category}/

Usage:
    python3 crawl_wallpaper.py                # Crawl all
    python3 crawl_wallpaper.py --images-only  # Images only
    python3 crawl_wallpaper.py --videos-only  # Videos only
"""

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════
WALLPAPER_DIR = Path('/home/thanh/wallpaper')
PIXABAY_API_KEY = os.getenv('VITE_PIXABAY_API_KEY', '')

# Min quality
MIN_WIDTH = 1920
MIN_HEIGHT = 1080

# Categories with search keywords
CATEGORIES = {
    'xianxia': {
        'wallhaven': ['xianxia', 'cultivation anime', 'chinese fantasy anime', 'donghua'],
        'pixabay': ['chinese fantasy', 'ancient chinese', 'mystic warrior'],
        'desc': 'Tu tiên / Xianxia'
    },
    'wuxia': {
        'wallhaven': ['wuxia', 'martial arts anime', 'sword fighting anime', 'chinese martial'],
        'pixabay': ['martial arts', 'kung fu', 'samurai warrior'],
        'desc': 'Kiếm hiệp / Wuxia'
    },
    'anime-landscape': {
        'wallhaven': ['anime landscape 4k', 'anime scenery', 'anime nature wallpaper', 'anime sky'],
        'pixabay': ['anime landscape', 'fantasy landscape'],
        'desc': 'Phong cảnh anime'
    },
    'anime-character': {
        'wallhaven': ['anime character', 'anime girl wallpaper', 'anime boy wallpaper', 'anime portrait'],
        'pixabay': ['anime character'],
        'desc': 'Nhân vật anime'
    },
    'fantasy': {
        'wallhaven': ['fantasy art', 'dark fantasy', 'epic fantasy wallpaper', 'dragon fantasy'],
        'pixabay': ['fantasy world', 'magical forest', 'dragon'],
        'desc': 'Fantasy / Huyền ảo'
    },
    'nature-4k': {
        'wallhaven': ['nature 4k', 'mountain landscape 4k', 'ocean wallpaper', 'forest 4k'],
        'pixabay': ['nature 4k', 'mountain 4k', 'ocean waves', 'forest'],
        'desc': 'Thiên nhiên 4K'
    },
    'abstract': {
        'wallhaven': ['abstract 4k', 'abstract art wallpaper', 'geometric abstract', 'colorful abstract'],
        'pixabay': ['abstract background', 'colorful abstract'],
        'desc': 'Abstract / Trừu tượng'
    },
    'dark-aesthetic': {
        'wallhaven': ['dark aesthetic', 'dark anime', 'dark wallpaper 4k', 'amoled wallpaper'],
        'pixabay': ['dark background', 'dark aesthetic', 'night sky'],
        'desc': 'Dark / AMOLED'
    },
}

# Target per category
TARGET_IMAGES_PER_CAT = 25  # ~200 total across 8 categories
TARGET_VIDEOS_PER_CAT = 7   # ~50 total across ~7 categories


@dataclass
class WallpaperItem:
    id: str
    url: str
    thumbnail: str = ''
    width: int = 0
    height: int = 0
    description: str = ''
    tags: list = field(default_factory=list)
    source: str = ''
    category: str = ''
    media_type: str = 'image'  # image or video
    favorites: int = 0
    views: int = 0
    score: float = 0.0
    local_path: str = ''


# ═══════════════════════════════════════════════════════════
# Wallhaven Crawler (Images)
# ═══════════════════════════════════════════════════════════
class WallhavenCrawler:
    API_BASE = 'https://wallhaven.cc/api/v1'

    def __init__(self):
        self.session = None
        self.seen_ids = set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def search(self, query: str, category_name: str, max_results: int = 30) -> list[WallpaperItem]:
        """Search Wallhaven - sorted by favorites (top quality)"""
        images = []
        page = 1

        while len(images) < max_results and page <= 5:
            params = {
                'q': query,
                'categories': '010',  # anime only
                'purity': '100',      # SFW
                'sorting': 'favorites',
                'order': 'desc',
                'atleast': f'{MIN_WIDTH}x{MIN_HEIGHT}',
                'page': page,
            }

            try:
                async with self.session.get(f'{self.API_BASE}/search', params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 429:
                        print('  ⏳ Rate limited, waiting 45s...')
                        await asyncio.sleep(45)
                        continue
                    if r.status != 200:
                        break
                    data = await r.json()
            except Exception as e:
                print(f'  ❌ Error: {e}')
                break

            wallpapers = data.get('data', [])
            if not wallpapers:
                break

            for wp in wallpapers:
                if len(images) >= max_results:
                    break

                wid = wp.get('id', '')
                if wid in self.seen_ids:
                    continue
                self.seen_ids.add(wid)

                w = wp.get('dimension_x', 0)
                h = wp.get('dimension_y', 0)
                if w < MIN_WIDTH or h < MIN_HEIGHT:
                    continue

                tags = [t.get('name', '') for t in wp.get('tags', [])]
                favs = wp.get('favorites', 0)

                images.append(WallpaperItem(
                    id=wid,
                    url=wp.get('path', ''),
                    thumbnail=wp.get('thumbs', {}).get('large', ''),
                    width=w,
                    height=h,
                    description=', '.join(tags[:5]),
                    tags=tags,
                    source='wallhaven',
                    category=category_name,
                    media_type='image',
                    favorites=favs,
                    views=wp.get('views', 0),
                    score=favs,
                ))

            meta = data.get('meta', {})
            if page >= meta.get('last_page', 1):
                break

            page += 1
            await asyncio.sleep(2.5)

        return images


# ═══════════════════════════════════════════════════════════
# Pixabay Crawler (Videos)
# ═══════════════════════════════════════════════════════════
class PixabayCrawler:
    API_BASE = 'https://pixabay.com/api'

    def __init__(self):
        self.session = None
        self.api_key = PIXABAY_API_KEY
        self.seen_ids = set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def search_videos(self, query: str, category_name: str, max_results: int = 10) -> list[WallpaperItem]:
        """Search Pixabay for videos"""
        if not self.api_key:
            print('  ⚠️ No Pixabay API key, skipping videos')
            return []

        videos = []
        page = 1

        while len(videos) < max_results and page <= 3:
            params = {
                'key': self.api_key,
                'q': query,
                'video_type': 'film',  # film = high quality
                'min_width': 1920,
                'min_height': 1080,
                'order': 'popular',
                'per_page': 20,
                'page': page,
                'safesearch': 'true',
            }

            try:
                async with self.session.get(f'{self.API_BASE}/videos/', params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 429:
                        print('  ⏳ Rate limited, waiting 30s...')
                        await asyncio.sleep(30)
                        continue
                    if r.status != 200:
                        break
                    data = await r.json()
            except Exception as e:
                print(f'  ❌ Error: {e}')
                break

            hits = data.get('hits', [])
            if not hits:
                break

            for hit in hits:
                if len(videos) >= max_results:
                    break

                vid = str(hit.get('id', ''))
                if vid in self.seen_ids:
                    continue
                self.seen_ids.add(vid)

                # Get best quality video URL
                video_data = hit.get('videos', {})
                # Try large → medium → small
                best = video_data.get('large', video_data.get('medium', video_data.get('small', {})))
                video_url = best.get('url', '')
                vw = best.get('width', 0)
                vh = best.get('height', 0)

                if not video_url or vw < 1280:
                    continue

                videos.append(WallpaperItem(
                    id=vid,
                    url=video_url,
                    thumbnail=hit.get('picture_id', ''),
                    width=vw,
                    height=vh,
                    description=hit.get('tags', ''),
                    tags=hit.get('tags', '').split(', '),
                    source='pixabay',
                    category=category_name,
                    media_type='video',
                    favorites=hit.get('likes', 0),
                    views=hit.get('views', 0),
                    score=hit.get('likes', 0) + hit.get('downloads', 0) * 0.5,
                ))

            total = data.get('totalHits', 0)
            if page * 20 >= total:
                break

            page += 1
            await asyncio.sleep(1.5)

        return videos

    async def search_images(self, query: str, category_name: str, max_results: int = 15) -> list[WallpaperItem]:
        """Search Pixabay for images (supplement Wallhaven)"""
        if not self.api_key:
            return []

        images = []
        page = 1

        while len(images) < max_results and page <= 3:
            params = {
                'key': self.api_key,
                'q': query,
                'image_type': 'illustration',
                'min_width': 1920,
                'min_height': 1080,
                'order': 'popular',
                'per_page': 20,
                'page': page,
                'safesearch': 'true',
            }

            try:
                async with self.session.get(f'{self.API_BASE}/', params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status != 200:
                        break
                    data = await r.json()
            except Exception as e:
                print(f'  ❌ Error: {e}')
                break

            hits = data.get('hits', [])
            if not hits:
                break

            for hit in hits:
                if len(images) >= max_results:
                    break

                iid = str(hit.get('id', ''))
                if iid in self.seen_ids:
                    continue
                self.seen_ids.add(iid)

                images.append(WallpaperItem(
                    id=iid,
                    url=hit.get('largeImageURL', ''),
                    thumbnail=hit.get('webformatURL', ''),
                    width=hit.get('imageWidth', 0),
                    height=hit.get('imageHeight', 0),
                    description=hit.get('tags', ''),
                    tags=hit.get('tags', '').split(', '),
                    source='pixabay',
                    category=category_name,
                    media_type='image',
                    favorites=hit.get('likes', 0),
                    views=hit.get('views', 0),
                    score=hit.get('likes', 0) + hit.get('downloads', 0) * 0.3,
                ))

            page += 1
            await asyncio.sleep(1)

        return images


# ═══════════════════════════════════════════════════════════
# Downloader
# ═══════════════════════════════════════════════════════════
async def download_item(session: aiohttp.ClientSession, item: WallpaperItem, progress: tqdm) -> bool:
    """Download a single wallpaper item to local disk"""
    cat_dir = WALLPAPER_DIR / item.category
    cat_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension
    if item.media_type == 'video':
        ext = 'mp4'
    else:
        url_path = item.url.split('?')[0]
        ext = url_path.split('.')[-1].lower()
        if ext not in ['jpg', 'jpeg', 'png', 'webp']:
            ext = 'jpg'

    filename = f'{item.source}_{item.id}.{ext}'
    filepath = cat_dir / filename

    if filepath.exists():
        item.local_path = str(filepath)
        progress.update(1)
        return True

    try:
        async with session.get(item.url, timeout=aiohttp.ClientTimeout(total=120)) as r:
            if r.status != 200:
                return False
            data = await r.read()

        filepath.write_bytes(data)
        item.local_path = str(filepath)
        size_mb = len(data) / 1024 / 1024
        progress.set_postfix_str(f'{filename} ({size_mb:.1f}MB)')
        progress.update(1)
        return True

    except Exception as e:
        progress.set_postfix_str(f'❌ {e}')
        return False


# ═══════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════
async def main(images_only=False, videos_only=False):
    print('═' * 60)
    print('🐉 Wallpaper Crawler - High Quality Images & Videos')
    print('═' * 60)
    print(f'Output: {WALLPAPER_DIR}')
    print(f'Categories: {len(CATEGORIES)}')
    print(f'Target: ~{TARGET_IMAGES_PER_CAT * len(CATEGORIES)} images + ~{TARGET_VIDEOS_PER_CAT * len(CATEGORIES)} videos')
    print()

    all_items = []

    # ── Step 1: Crawl Images ──────────────────────────────
    if not videos_only:
        print('\n[Step 1] 🖼️  Crawling images from Wallhaven + Pixabay...')
        async with WallhavenCrawler() as wh, PixabayCrawler() as px:
            for cat_name, cat_config in CATEGORIES.items():
                print(f'\n  📁 {cat_name} ({cat_config["desc"]})')

                cat_images = []

                # Wallhaven (primary source for anime/fantasy)
                for kw in cat_config.get('wallhaven', []):
                    imgs = await wh.search(kw, cat_name, max_results=10)
                    cat_images.extend(imgs)
                    print(f'    Wallhaven "{kw}": +{len(imgs)}')
                    await asyncio.sleep(2)

                # Pixabay (supplement)
                for kw in cat_config.get('pixabay', [])[:2]:
                    imgs = await px.search_images(kw, cat_name, max_results=8)
                    cat_images.extend(imgs)
                    print(f'    Pixabay "{kw}": +{len(imgs)}')

                # Sort by score, keep top
                cat_images.sort(key=lambda x: x.score, reverse=True)
                cat_images = cat_images[:TARGET_IMAGES_PER_CAT]
                all_items.extend(cat_images)
                print(f'    ✅ Kept top {len(cat_images)} images')

    # ── Step 2: Crawl Videos ──────────────────────────────
    if not images_only:
        print('\n[Step 2] 🎬 Crawling videos from Pixabay...')
        async with PixabayCrawler() as px:
            for cat_name, cat_config in CATEGORIES.items():
                print(f'\n  📁 {cat_name} ({cat_config["desc"]})')

                cat_videos = []
                for kw in cat_config.get('pixabay', []):
                    vids = await px.search_videos(kw, cat_name, max_results=5)
                    cat_videos.extend(vids)
                    print(f'    Pixabay video "{kw}": +{len(vids)}')

                cat_videos.sort(key=lambda x: x.score, reverse=True)
                cat_videos = cat_videos[:TARGET_VIDEOS_PER_CAT]
                all_items.extend(cat_videos)
                print(f'    ✅ Kept top {len(cat_videos)} videos')

    # ── Step 3: Download ──────────────────────────────────
    images_count = sum(1 for i in all_items if i.media_type == 'image')
    videos_count = sum(1 for i in all_items if i.media_type == 'video')
    print(f'\n[Step 3] ⬇️  Downloading {images_count} images + {videos_count} videos...')

    WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0

    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    }) as session:
        with tqdm(total=len(all_items), desc='Downloading') as pbar:
            # Download in batches of 5
            for i in range(0, len(all_items), 5):
                batch = all_items[i:i+5]
                results = await asyncio.gather(*[
                    download_item(session, item, pbar) for item in batch
                ], return_exceptions=True)

                for ok in results:
                    if ok is True:
                        downloaded += 1
                    else:
                        failed += 1

                await asyncio.sleep(0.5)

    # ── Step 4: Save metadata ─────────────────────────────
    print(f'\n[Step 4] 💾 Saving metadata...')

    # Save per-category metadata
    by_cat = {}
    for item in all_items:
        if item.local_path:
            by_cat.setdefault(item.category, []).append(asdict(item))

    for cat, items in by_cat.items():
        cat_meta = WALLPAPER_DIR / cat / 'metadata.json'
        with open(cat_meta, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    # Save global metadata
    global_meta = [asdict(i) for i in all_items if i.local_path]
    with open(WALLPAPER_DIR / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(global_meta, f, ensure_ascii=False, indent=2)

    # ── Summary ───────────────────────────────────────────
    print('\n' + '═' * 60)
    print('✅ DONE!')
    print('═' * 60)
    print(f'Downloaded: {downloaded} | Failed: {failed}')
    print(f'\nBy category:')
    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        imgs = sum(1 for i in items if i['media_type'] == 'image')
        vids = sum(1 for i in items if i['media_type'] == 'video')
        print(f'  📁 {cat}: {imgs} images, {vids} videos')

    # Disk usage
    total_size = sum(
        os.path.getsize(str(WALLPAPER_DIR / i.category / os.path.basename(i.local_path)))
        for i in all_items if i.local_path
    )
    print(f'\nTotal size: {total_size / 1024 / 1024:.1f} MB')
    print(f'Preview: http://localhost:3000/wallpaper')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--images-only', action='store_true')
    parser.add_argument('--videos-only', action='store_true')
    args = parser.parse_args()

    asyncio.run(main(images_only=args.images_only, videos_only=args.videos_only))
