#!/usr/bin/env python3
"""
Xianxia Wallpaper Crawler - Main Pipeline
Crawl → Filter → AI classify → Rank → Deduplicate → Output

Usage:
    python main.py                    # Run full pipeline
    python main.py --skip-ai          # Skip AI filtering (faster)
    python main.py --source wallhaven # Use Wallhaven (default)
    python main.py --source pinterest # Use Pinterest
    python main.py --limit 50         # Limit results per keyword
    python main.py --preview          # Generate preview HTML
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from config import (
    SEARCH_KEYWORDS, TOP_RESULTS_COUNT, OUTPUT_FILE, OUTPUT_FOLDER,
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, LOCAL_DOWNLOAD_DIR
)
from scorer import ImageScorer, ImageFilter, score_images
from deduplicator import deduplicate_images


async def run_pipeline(
    skip_ai: bool = False,
    skip_dedup: bool = False,
    max_per_keyword: int = 50,
    output_count: int = TOP_RESULTS_COUNT,
    source: str = 'wallhaven',
):
    """Run the complete crawling pipeline"""
    print('=' * 60)
    print('Xianxia Wallpaper Crawler Pipeline')
    print('=' * 60)
    print(f'Started: {datetime.now().isoformat()}')
    print(f'Source: {source}')
    print(f'Max per keyword: {max_per_keyword}')
    print(f'Target output: {output_count} images')
    print()

    # Step 1: Crawl
    print(f'\n[Step 1/5] Crawling {source}...')

    if source == 'wallhaven':
        from wallhaven_crawler import WallhavenCrawler
        async with WallhavenCrawler() as crawler:
            all_images = await crawler.crawl_xianxia_keywords(max_per_keyword=max_per_keyword)
            print(f'Crawled {len(all_images)} total images')
            images = [asdict(img) for img in all_images]
    else:
        from crawler import PinterestCrawler
        async with PinterestCrawler() as crawler:
            all_images = await crawler.crawl_all_keywords(max_per_keyword=max_per_keyword)
            print(f'Crawled {len(all_images)} total images')
            images = [asdict(img) for img in all_images]

    # Save raw results
    with open('raw_crawled.json', 'w', encoding='utf-8') as f:
        json.dump(images, f, ensure_ascii=False, indent=2)
    print(f'Saved raw results to raw_crawled.json')

    # Step 2: Filter
    print('\n[Step 2/5] Filtering images...')
    img_filter = ImageFilter()
    images = img_filter.apply_all_filters(images)
    print(f'{len(images)} images after filtering')

    # Step 3: AI Classification (optional)
    if not skip_ai:
        print('\n[Step 3/5] AI Classification...')
        try:
            from ai_filter import apply_ai_filters
            images = await apply_ai_filters(images)
            print(f'AI classification complete')
        except ImportError as e:
            print(f'AI filtering skipped (missing dependencies): {e}')
    else:
        print('\n[Step 3/5] AI Classification... SKIPPED')

    # Step 4: Score and Rank
    print('\n[Step 4/5] Scoring and ranking...')
    images = score_images(images)
    print(f'Scoring complete')

    # Step 5: Deduplicate (optional)
    if not skip_dedup:
        print('\n[Step 5/5] Deduplicating...')
        try:
            images = await deduplicate_images(images)
            print(f'{len(images)} images after deduplication')
        except Exception as e:
            print(f'Deduplication skipped: {e}')
    else:
        print('\n[Step 5/5] Deduplication... SKIPPED')

    # Get top results
    top_images = images[:output_count]

    # Generate output
    output = {
        'generated': datetime.now().isoformat(),
        'total': len(top_images),
        'pipeline': {
            'crawled': len(all_images) if 'all_images' in dir() else 0,
            'filtered': len(images),
            'ai_enabled': not skip_ai,
            'dedup_enabled': not skip_dedup,
        },
        'images': top_images,
    }

    # Save output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nSaved top {len(top_images)} images to {OUTPUT_FILE}')

    # Print summary
    print('\n' + '=' * 60)
    print('Pipeline Complete!')
    print('=' * 60)
    print(f'Total images: {len(top_images)}')

    # Character breakdown
    char_counts = {}
    for img in top_images:
        char = img.get('detected_character') or img.get('ai_detected_character') or 'unknown'
        char_counts[char] = char_counts.get(char, 0) + 1

    print('\nCharacter breakdown:')
    for char, count in sorted(char_counts.items(), key=lambda x: -x[1]):
        print(f'  {char}: {count}')

    # Top 5 images
    print('\nTop 5 images:')
    for i, img in enumerate(top_images[:5]):
        print(f'  {i+1}. Score: {img.get("total_score", 0):.1f}')
        print(f'     {img.get("width", 0)}x{img.get("height", 0)} - {img.get("description", "")[:50]}...')

    return top_images


async def download_to_local(images: list):
    """Download images to local wallpaper folder"""
    import aiohttp
    import hashlib
    from config import PINTEREST_HEADERS

    base_dir = Path(LOCAL_DOWNLOAD_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f'\nDownloading to {LOCAL_DOWNLOAD_DIR}...')

    downloaded = 0
    async with aiohttp.ClientSession(headers=PINTEREST_HEADERS) as session:
        for img in images:
            try:
                url = img.get('url', '')
                if not url:
                    continue

                # Create character folder
                char = img.get('detected_character') or img.get('ai_detected_character') or 'general'
                char_dir = base_dir / char
                char_dir.mkdir(exist_ok=True)

                # Generate filename from URL hash
                img_id = img.get('id') or hashlib.md5(url.encode()).hexdigest()[:12]
                ext = url.split('.')[-1].split('?')[0][:4]
                if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                    ext = 'jpg'
                filepath = char_dir / f'{img_id}.{ext}'

                if filepath.exists():
                    print(f'  Skip (exists): {filepath.name}')
                    continue

                # Download
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    data = await response.read()

                # Save
                filepath.write_bytes(data)
                downloaded += 1
                print(f'  [{downloaded}] {filepath.name} ({len(data)//1024}KB)')

            except Exception as e:
                print(f'  Error: {e}')

    # Save metadata JSON
    metadata_file = base_dir / 'metadata.json'
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(images, f, ensure_ascii=False, indent=2)

    print(f'\nDownloaded {downloaded} images to {LOCAL_DOWNLOAD_DIR}')
    print(f'Metadata saved to {metadata_file}')
    return downloaded


async def upload_to_r2(images: list):
    """Upload top images to Cloudflare R2"""
    if not all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]):
        print('R2 not configured, skipping upload')
        return

    print('\nUploading to R2...')

    import boto3
    import aiohttp
    from config import PINTEREST_HEADERS

    s3 = boto3.client(
        's3',
        endpoint_url=f'https://{os.getenv("CLOUDFLARE_ACCOUNT_ID")}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )

    uploaded = 0
    async with aiohttp.ClientSession(headers=PINTEREST_HEADERS) as session:
        for img in images:
            try:
                url = img.get('url', '')
                if not url:
                    continue

                # Download image
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    data = await response.read()

                # Generate key
                char = img.get('detected_character') or 'unknown'
                img_id = img.get('id', str(hash(url)))[:10]
                key = f'{OUTPUT_FOLDER}/{char}/{img_id}.jpg'

                # Upload
                s3.put_object(
                    Bucket=R2_BUCKET_NAME,
                    Key=key,
                    Body=data,
                    ContentType='image/jpeg',
                    Metadata={
                        'source': 'pinterest',
                        'score': str(img.get('total_score', 0)),
                        'character': char,
                    }
                )
                uploaded += 1

            except Exception as e:
                print(f'Upload error: {e}')

    print(f'Uploaded {uploaded} images to R2')


def generate_preview_html(images: list, output_path: str = 'preview.html'):
    """Generate HTML preview of images"""
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xianxia Wallpapers Preview</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #fff;
            padding: 20px;
        }
        h1 { text-align: center; margin-bottom: 20px; color: #fff; }
        .stats {
            text-align: center;
            margin-bottom: 30px;
            color: #888;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            max-width: 1800px;
            margin: 0 auto;
        }
        .card {
            background: #1a1a1a;
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.2s;
        }
        .card:hover { transform: scale(1.02); }
        .card img {
            width: 100%;
            height: 200px;
            object-fit: cover;
            cursor: pointer;
        }
        .card-info {
            padding: 15px;
        }
        .card-title {
            font-size: 14px;
            color: #fff;
            margin-bottom: 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .card-meta {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #888;
        }
        .score {
            background: #2d5a27;
            color: #7fff00;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: bold;
        }
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal.active { display: flex; }
        .modal img {
            max-width: 95vw;
            max-height: 95vh;
            object-fit: contain;
        }
        .modal-close {
            position: absolute;
            top: 20px; right: 30px;
            font-size: 40px;
            color: #fff;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <h1>🐉 Xianxia Wallpapers Preview</h1>
    <div class="stats">
        Total: ''' + str(len(images)) + ''' images | Generated: ''' + datetime.now().strftime('%Y-%m-%d %H:%M') + '''
    </div>
    <div class="grid">
'''

    for img in images:
        score = img.get('total_score', 0)
        width = img.get('width', 0)
        height = img.get('height', 0)
        desc = (img.get('description', '') or 'No description')[:50]
        url = img.get('url', '')

        html += f'''
        <div class="card">
            <img src="{url}" alt="{desc}" loading="lazy" onclick="showModal('{url}')">
            <div class="card-info">
                <div class="card-title">{desc}</div>
                <div class="card-meta">
                    <span>{width}x{height}</span>
                    <span class="score">{score:.1f}</span>
                </div>
            </div>
        </div>
'''

    html += '''
    </div>
    <div class="modal" id="modal" onclick="hideModal()">
        <span class="modal-close">&times;</span>
        <img id="modal-img" src="">
    </div>
    <script>
        function showModal(url) {
            document.getElementById('modal-img').src = url;
            document.getElementById('modal').classList.add('active');
        }
        function hideModal() {
            document.getElementById('modal').classList.remove('active');
        }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') hideModal();
        });
    </script>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'Preview saved to {output_path}')
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Xianxia Wallpaper Crawler')
    parser.add_argument('--skip-ai', action='store_true', help='Skip AI filtering')
    parser.add_argument('--skip-dedup', action='store_true', help='Skip deduplication')
    parser.add_argument('--limit', type=int, default=50, help='Max images per keyword')
    parser.add_argument('--output', type=int, default=TOP_RESULTS_COUNT, help='Number of output images')
    parser.add_argument('--source', choices=['wallhaven', 'pinterest'], default='wallhaven', help='Image source')
    parser.add_argument('--preview', action='store_true', help='Generate preview HTML')
    parser.add_argument('--upload', action='store_true', help='Upload to R2 after processing')
    parser.add_argument('--download', action='store_true', help='Download to local wallpaper folder')

    args = parser.parse_args()

    # Run pipeline
    images = asyncio.run(run_pipeline(
        skip_ai=args.skip_ai,
        skip_dedup=args.skip_dedup,
        max_per_keyword=args.limit,
        output_count=args.output,
        source=args.source,
    ))

    # Generate preview
    if args.preview and images:
        generate_preview_html(images)
        print('Open preview.html in browser to view results')

    # Optional: Download to local
    if args.download and images:
        asyncio.run(download_to_local(images))

    # Optional: Upload to R2
    if args.upload and images:
        asyncio.run(upload_to_r2(images))


if __name__ == '__main__':
    main()
