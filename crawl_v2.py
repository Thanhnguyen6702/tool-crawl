#!/usr/bin/env python3
"""
Wallpaper Crawler v2 - Focused on:
  - Tu tiên / Donghua characters (Tiêu Viêm, Thạch Hạo, Vương Lâm, Diệp Phàm...)
  - Gaming (Liên Minh, Liên Quân, PUBG, Genshin...)
  
Sources:
  - Images: Wallhaven (anime wallpapers, best quality)
  - Videos: MoeWalls (live wallpapers)

Saves to /home/thanh/wallpaper/{category}/
"""

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import quote_plus

import aiohttp
from tqdm import tqdm

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════
WALLPAPER_DIR = Path('/home/thanh/wallpaper')
MIN_WIDTH = 1080
MIN_HEIGHT = 720

# Categories with search keywords
# Wallhaven categories: 010=anime, 100=general, 001=people, 110=general+anime
CATEGORIES = {
    # ── Tu Tiên / Donghua ──
    'tieu-viem': {
        'name': 'Tiêu Viêm - Đấu Phá Thương Khung',
        'wallhaven': [
            ('xiao yan', '010'),
            ('battle through the heavens', '010'),
            ('doupo cangqiong', '010'),
            ('斗破苍穹', '010'),
            ('萧炎', '010'),
        ],
        'target_images': 25,
    },
    'thach-hao': {
        'name': 'Thạch Hạo - Hoàn Mỹ Thế Giới',
        'wallhaven': [
            ('shi hao perfect world', '010'),
            ('perfect world anime', '010'),
            ('完美世界', '010'),
            ('wanmei shijie', '010'),
        ],
        'target_images': 25,
    },
    'vuong-lam': {
        'name': 'Vương Lâm - Tiên Nghịch',
        'wallhaven': [
            ('wang lin renegade immortal', '010'),
            ('renegade immortal', '010'),
            ('仙逆', '010'),
            ('xian ni anime', '010'),
        ],
        'target_images': 25,
    },
    'diep-pham': {
        'name': 'Diệp Phàm - Già Thiên',
        'wallhaven': [
            ('ye fan shrouding heavens', '010'),
            ('shrouding the heavens', '010'),
            ('遮天', '010'),
        ],
        'target_images': 25,
    },
    'donghua': {
        'name': 'Donghua - Phim Tu Tiên Trung Quốc',
        'wallhaven': [
            ('donghua wallpaper', '010'),
            ('chinese anime', '010'),
            ('xianxia anime', '010'),
            ('cultivation anime', '010'),
            ('soul land douluo dalu', '010'),
            ('martial universe', '010'),
            ('swallowed star', '010'),
            ('stellar transformations', '010'),
            ('against the gods', '010'),
            ('immortal cultivation', '010'),
        ],
        'target_images': 30,
    },
    # ── Gaming ──
    'lien-minh': {
        'name': 'Liên Minh Huyền Thoại',
        'wallhaven': [
            ('league of legends', '010'),
            ('league of legends 4k', '110'),
            ('lol champion', '010'),
            ('arcane', '010'),
            ('yasuo', '010'),
            ('jinx league', '010'),
        ],
        'target_images': 30,
    },
    'lien-quan': {
        'name': 'Liên Quân Mobile',
        'wallhaven': [
            ('arena of valor', '010'),
            ('honor of kings', '010'),
            ('王者荣耀', '010'),
            ('honor of kings 4k', '110'),
        ],
        'target_images': 25,
    },
    'pubg': {
        'name': 'PUBG',
        'wallhaven': [
            ('pubg wallpaper', '110'),
            ('pubg 4k', '110'),
            ('pubg mobile', '110'),
            ('battlegrounds', '110'),
        ],
        'target_images': 25,
    },
    'genshin': {
        'name': 'Genshin Impact',
        'wallhaven': [
            ('genshin impact', '010'),
            ('genshin impact 4k', '010'),
            ('原神', '010'),
        ],
        'target_images': 25,
    },
}

# Video categories
VIDEO_CATEGORIES = {
    'donghua-video': {
        'name': 'Donghua Live Wallpapers',
        'moewalls_tags': ['chinese', 'donghua', 'xianxia'],
        'target': 15,
    },
    'lol-video': {
        'name': 'LOL Live Wallpapers', 
        'moewalls_tags': ['league-of-legends'],
        'target': 10,
    },
    'genshin-video': {
        'name': 'Genshin Impact Live Wallpapers',
        'moewalls_tags': ['genshin-impact'],
        'target': 10,
    },
    'gaming-video': {
        'name': 'Gaming Live Wallpapers',
        'moewalls_tags': ['gaming', 'game'],
        'target': 15,
    },
}


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
    media_type: str = 'image'
    favorites: int = 0
    views: int = 0
    score: float = 0.0
    local_path: str = ''


# ═══════════════════════════════════════════════════════════
# Wallhaven Crawler (Images) - Best anime wallpaper source
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

    async def search(self, query: str, categories: str = '010', max_results: int = 30) -> list[WallpaperItem]:
        """Search sorted by favorites (= top quality & popular)"""
        images = []
        page = 1

        while len(images) < max_results and page <= 4:
            params = {
                'q': query,
                'categories': categories,
                'purity': '100',       # SFW
                'sorting': 'favorites', # Top first
                'order': 'desc',
                'atleast': f'{MIN_WIDTH}x{MIN_HEIGHT}',
                'page': page,
            }

            try:
                async with self.session.get(f'{self.API_BASE}/search', params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 429:
                        print('    ⏳ Rate limited, waiting 45s...')
                        await asyncio.sleep(45)
                        continue
                    if r.status != 200:
                        break
                    data = await r.json()
            except Exception as e:
                print(f'    ❌ {e}')
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
                    width=w, height=h,
                    description=', '.join(tags[:8]),
                    tags=tags,
                    source='wallhaven',
                    media_type='image',
                    favorites=favs,
                    views=wp.get('views', 0),
                    score=favs,
                ))

            meta = data.get('meta', {})
            if page >= meta.get('last_page', 1):
                break
            page += 1
            await asyncio.sleep(2)

        return images


# ═══════════════════════════════════════════════════════════
# MoeWalls Crawler (Videos) - Best live wallpaper source
# ═══════════════════════════════════════════════════════════
class MoeWallsCrawler:
    BASE_URL = 'https://moewalls.com'

    def __init__(self):
        self.session = None
        self.seen_urls = set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        })
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def crawl_tag(self, tag: str, max_results: int = 15) -> list[WallpaperItem]:
        """Crawl MoeWalls tag page for video wallpapers"""
        videos = []
        page = 1

        while len(videos) < max_results and page <= 3:
            url = f'{self.BASE_URL}/tag/{tag}/page/{page}/' if page > 1 else f'{self.BASE_URL}/tag/{tag}/'

            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status != 200:
                        break
                    html = await r.text()
            except Exception as e:
                print(f'    ❌ MoeWalls error: {e}')
                break

            # Parse post links
            post_links = re.findall(r'href="(https://moewalls\.com/[^"]+/)"', html)
            post_links = [l for l in post_links if '/tag/' not in l and '/page/' not in l 
                         and '/category/' not in l and '/author/' not in l
                         and l not in self.seen_urls]

            if not post_links:
                break

            for link in post_links[:max_results - len(videos)]:
                self.seen_urls.add(link)
                video = await self._parse_post(link)
                if video:
                    videos.append(video)
                await asyncio.sleep(1.5)

            page += 1
            await asyncio.sleep(2)

        return videos

    async def _parse_post(self, url: str) -> WallpaperItem | None:
        """Parse a single MoeWalls post to get video URL"""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return None
                html = await r.text()
        except:
            return None

        # Find video download link
        # Look for .mp4 links
        mp4_links = re.findall(r'href="([^"]*\.mp4[^"]*)"', html)
        if not mp4_links:
            # Try video source
            mp4_links = re.findall(r'src="([^"]*\.mp4[^"]*)"', html)
        if not mp4_links:
            return None

        video_url = mp4_links[0]
        if video_url.startswith('//'):
            video_url = 'https:' + video_url

        # Get title
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else url.split('/')[-2]

        # Get resolution from page
        res_match = re.search(r'(\d{3,4})\s*[x×]\s*(\d{3,4})', html)
        w = int(res_match.group(1)) if res_match else 1920
        h = int(res_match.group(2)) if res_match else 1080

        post_id = hashlib.md5(url.encode()).hexdigest()[:10]

        return WallpaperItem(
            id=post_id,
            url=video_url,
            thumbnail='',
            width=w, height=h,
            description=title,
            tags=[],
            source='moewalls',
            media_type='video',
            score=0,
        )


# ═══════════════════════════════════════════════════════════
# Downloader
# ═══════════════════════════════════════════════════════════
async def download_item(session: aiohttp.ClientSession, item: WallpaperItem, cat_name: str, progress: tqdm) -> bool:
    cat_dir = WALLPAPER_DIR / cat_name
    cat_dir.mkdir(parents=True, exist_ok=True)

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
        timeout = aiohttp.ClientTimeout(total=180)
        async with session.get(item.url, timeout=timeout) as r:
            if r.status != 200:
                return False
            data = await r.read()

        # Skip tiny files
        if item.media_type == 'image' and len(data) < 50_000:
            return False
        if item.media_type == 'video' and len(data) < 500_000:
            return False

        filepath.write_bytes(data)
        item.local_path = str(filepath)
        size_mb = len(data) / 1024 / 1024
        progress.set_postfix_str(f'{filename} ({size_mb:.1f}MB)')
        progress.update(1)
        return True

    except Exception as e:
        progress.set_postfix_str(f'❌ {str(e)[:40]}')
        return False


# ═══════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════
async def main():
    print('═' * 60)
    print('🐉 Wallpaper Crawler v2 - Tu Tiên & Gaming')
    print('═' * 60)
    print(f'Output: {WALLPAPER_DIR}')
    print()

    all_items = []  # (category_dir_name, item)

    # ── Step 1: Crawl Images from Wallhaven ───────────────
    print('\n[Step 1] 🖼️  Crawling images from Wallhaven...')
    async with WallhavenCrawler() as wh:
        for cat_key, cat_config in CATEGORIES.items():
            print(f'\n  📁 {cat_key} — {cat_config["name"]}')
            cat_images = []

            for query, cat_code in cat_config.get('wallhaven', []):
                imgs = await wh.search(query, categories=cat_code, max_results=15)
                cat_images.extend(imgs)
                count = len(imgs)
                if count > 0:
                    print(f'    ✓ "{query}": +{count}')
                else:
                    print(f'    · "{query}": 0')
                await asyncio.sleep(2)

            # Sort by favorites, keep top
            target = cat_config.get('target_images', 25)
            cat_images.sort(key=lambda x: x.score, reverse=True)
            cat_images = cat_images[:target]

            for img in cat_images:
                img.category = cat_key
            all_items.extend([(cat_key, img) for img in cat_images])
            print(f'    ✅ Kept top {len(cat_images)} images')

    # ── Step 2: Crawl Videos from MoeWalls ────────────────
    print('\n[Step 2] 🎬 Crawling videos from MoeWalls...')
    async with MoeWallsCrawler() as mw:
        for cat_key, cat_config in VIDEO_CATEGORIES.items():
            print(f'\n  📁 {cat_key} — {cat_config["name"]}')
            cat_videos = []
            target = cat_config.get('target', 10)

            for tag in cat_config.get('moewalls_tags', []):
                vids = await mw.crawl_tag(tag, max_results=target)
                cat_videos.extend(vids)
                print(f'    ✓ tag "{tag}": +{len(vids)} videos')

            cat_videos = cat_videos[:target]
            for vid in cat_videos:
                vid.category = cat_key
            all_items.extend([(cat_key, vid) for vid in cat_videos])
            print(f'    ✅ Kept {len(cat_videos)} videos')

    # ── Step 3: Download everything ───────────────────────
    total_imgs = sum(1 for _, i in all_items if i.media_type == 'image')
    total_vids = sum(1 for _, i in all_items if i.media_type == 'video')
    print(f'\n[Step 3] ⬇️  Downloading {total_imgs} images + {total_vids} videos...')

    WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failed = 0

    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Referer': 'https://moewalls.com/',
    }) as session:
        with tqdm(total=len(all_items), desc='Downloading') as pbar:
            for i in range(0, len(all_items), 3):
                batch = all_items[i:i+3]
                results = await asyncio.gather(*[
                    download_item(session, item, cat, pbar) for cat, item in batch
                ], return_exceptions=True)

                for ok in results:
                    if ok is True:
                        downloaded += 1
                    else:
                        failed += 1

                await asyncio.sleep(0.3)

    # ── Step 4: Save metadata ─────────────────────────────
    print(f'\n[Step 4] 💾 Saving metadata...')

    by_cat = {}
    for cat, item in all_items:
        if item.local_path:
            by_cat.setdefault(cat, []).append(asdict(item))

    for cat, items in by_cat.items():
        cat_meta = WALLPAPER_DIR / cat / 'metadata.json'
        with open(cat_meta, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    # Global metadata
    global_items = []
    for cat, item in all_items:
        if item.local_path:
            d = asdict(item)
            d['category'] = cat
            global_items.append(d)

    with open(WALLPAPER_DIR / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(global_items, f, ensure_ascii=False, indent=2)

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
        total_mb = sum(os.path.getsize(i['local_path']) for i in items if os.path.exists(i['local_path'])) / 1024 / 1024
        print(f'  📁 {cat}: {imgs} imgs, {vids} vids ({total_mb:.0f}MB)')

    total_size = sum(
        os.path.getsize(i['local_path'])
        for _, i in all_items if i.local_path and os.path.exists(i.local_path)
    ) / 1024 / 1024
    print(f'\nTotal: {total_size:.0f} MB')
    print(f'Preview: http://localhost:3000/wallpaper')


if __name__ == '__main__':
    asyncio.run(main())
