#!/usr/bin/env python3
"""
Optimize wallpapers & upload to Cloudflare R2
- Generates thumbnail (300px), preview (720px), full (WebP compressed)
- Compresses videos to 720p
- Uploads all to R2 with proper structure
- Generates API JSON files for mobile app
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import boto3
from PIL import Image
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════
WALLPAPER_DIR = Path('/home/thanh/wallpaper')
OPTIMIZED_DIR = Path('/home/thanh/wallpaper-optimized')
FFMPEG = os.path.expanduser('~/.local/bin/ffmpeg')

R2_ENDPOINT = f"https://{os.getenv('CLOUDFLARE_ACCOUNT_ID')}.r2.cloudflarestorage.com"
R2_ACCESS_KEY = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.getenv('R2_BUCKET_NAME', 'funnycolor')
R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL', '').rstrip('/')

# Image sizes
THUMB_WIDTH = 300
PREVIEW_WIDTH = 720
FULL_MAX_WIDTH = 1440  # Max for mobile, saves bandwidth vs 4K

# Video
VIDEO_HEIGHT = 720
VIDEO_BITRATE = '2M'

# Category display names
CATEGORY_NAMES = {
    'tieu-viem': 'Tiêu Viêm - Đấu Phá Thương Khung',
    'thach-hao': 'Thạch Hạo - Hoàn Mỹ Thế Giới',
    'vuong-lam': 'Vương Lâm - Tiên Nghịch',
    'diep-pham': 'Diệp Phàm - Già Thiên',
    'donghua': 'Donghua Tổng Hợp',
    'lien-minh': 'Liên Minh Huyền Thoại',
    'lien-quan': 'Liên Quân Mobile',
    'pubg': 'PUBG Mobile',
    'genshin': 'Genshin Impact',
    'trending-anime': 'Anime Trending',
}


def optimize_image(src: Path, cat: str, item_id: str) -> dict | None:
    """Create thumb, preview, full versions of an image"""
    try:
        img = Image.open(src)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        w, h = img.size
        result = {'id': item_id, 'category': cat, 'type': 'image', 'width': w, 'height': h}

        cat_dir = OPTIMIZED_DIR / cat

        # Thumbnail (300px wide, WebP)
        thumb_dir = cat_dir / 'thumb'
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f'{item_id}.webp'
        if not thumb_path.exists():
            ratio = THUMB_WIDTH / w
            thumb = img.resize((THUMB_WIDTH, int(h * ratio)), Image.LANCZOS)
            thumb.save(thumb_path, 'WEBP', quality=75)
        result['thumb'] = f'wallpaper/{cat}/thumb/{item_id}.webp'
        result['thumb_size'] = thumb_path.stat().st_size

        # Preview (720px wide, WebP)
        preview_dir = cat_dir / 'preview'
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / f'{item_id}.webp'
        if not preview_path.exists():
            ratio = PREVIEW_WIDTH / w
            preview = img.resize((PREVIEW_WIDTH, int(h * ratio)), Image.LANCZOS)
            preview.save(preview_path, 'WEBP', quality=82)
        result['preview'] = f'wallpaper/{cat}/preview/{item_id}.webp'
        result['preview_size'] = preview_path.stat().st_size

        # Full (max 1440px, WebP for smaller size)
        full_dir = cat_dir / 'full'
        full_dir.mkdir(parents=True, exist_ok=True)
        full_path = full_dir / f'{item_id}.webp'
        if not full_path.exists():
            if w > FULL_MAX_WIDTH:
                ratio = FULL_MAX_WIDTH / w
                full_img = img.resize((FULL_MAX_WIDTH, int(h * ratio)), Image.LANCZOS)
            else:
                full_img = img
            full_img.save(full_path, 'WEBP', quality=88)
        result['full'] = f'wallpaper/{cat}/full/{item_id}.webp'
        result['full_size'] = full_path.stat().st_size

        img.close()
        return result

    except Exception as e:
        print(f'  ❌ Image error {src.name}: {e}')
        return None


def optimize_video(src: Path, cat: str, item_id: str) -> dict | None:
    """Compress video to 720p MP4"""
    try:
        cat_dir = OPTIMIZED_DIR / cat / 'video'
        cat_dir.mkdir(parents=True, exist_ok=True)
        out_path = cat_dir / f'{item_id}.mp4'

        # Also create thumbnail from first frame
        thumb_dir = OPTIMIZED_DIR / cat / 'thumb'
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f'{item_id}.webp'

        if not thumb_path.exists():
            # Extract first frame as thumbnail
            subprocess.run([
                FFMPEG, '-i', str(src), '-vframes', '1',
                '-vf', f'scale={THUMB_WIDTH}:-1',
                '-f', 'image2', '-y', '/tmp/frame.jpg'
            ], capture_output=True, timeout=30)
            if Path('/tmp/frame.jpg').exists():
                img = Image.open('/tmp/frame.jpg')
                img.save(thumb_path, 'WEBP', quality=75)
                img.close()

        if not out_path.exists():
            # Get source info
            probe = subprocess.run([
                os.path.expanduser('~/.local/bin/ffprobe'),
                '-v', 'quiet', '-print_format', 'json',
                '-show_streams', str(src)
            ], capture_output=True, text=True, timeout=15)
            info = json.loads(probe.stdout)
            src_height = 0
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    src_height = int(stream.get('height', 0))
                    break

            # Compress
            vf = f'scale=-2:{VIDEO_HEIGHT}' if src_height > VIDEO_HEIGHT else ''
            cmd = [
                FFMPEG, '-i', str(src),
                '-c:v', 'libx264', '-preset', 'medium',
                '-b:v', VIDEO_BITRATE, '-maxrate', '3M', '-bufsize', '4M',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',  # Important for streaming
                '-y', str(out_path)
            ]
            if vf:
                cmd.insert(-2, '-vf')
                cmd.insert(-2, vf)

            subprocess.run(cmd, capture_output=True, timeout=300)

        if not out_path.exists():
            return None

        result = {
            'id': item_id,
            'category': cat,
            'type': 'video',
            'video': f'wallpaper/{cat}/video/{item_id}.mp4',
            'video_size': out_path.stat().st_size,
        }
        if thumb_path.exists():
            result['thumb'] = f'wallpaper/{cat}/thumb/{item_id}.webp'
        return result

    except Exception as e:
        print(f'  ❌ Video error {src.name}: {e}')
        return None


def upload_to_r2(local_path: Path, r2_key: str, content_type: str):
    """Upload a file to R2"""
    s3 = boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
    )
    s3.upload_file(
        str(local_path), R2_BUCKET, r2_key,
        ExtraArgs={'ContentType': content_type, 'CacheControl': 'public, max-age=31536000'}
    )


def get_content_type(path: str) -> str:
    if path.endswith('.webp'): return 'image/webp'
    if path.endswith('.jpg') or path.endswith('.jpeg'): return 'image/jpeg'
    if path.endswith('.png'): return 'image/png'
    if path.endswith('.mp4'): return 'video/mp4'
    if path.endswith('.json'): return 'application/json'
    return 'application/octet-stream'


def main():
    print('═' * 55)
    print('🚀 Optimize & Upload to R2')
    print('═' * 55)

    # Read metadata
    meta_path = WALLPAPER_DIR / 'metadata.json'
    if not meta_path.exists():
        print('❌ No metadata.json found')
        return

    items = json.loads(meta_path.read_text())
    print(f'Items: {len(items)}')

    OPTIMIZED_DIR.mkdir(exist_ok=True)

    # ── Step 1: Optimize ──────────────────────────────────
    print('\n[Step 1] 🔧 Optimizing images & videos...')
    api_items = []
    img_count = vid_count = 0

    for i, item in enumerate(items):
        local = Path(item.get('local_path', ''))
        if not local.exists():
            continue

        cat = item.get('best_category') or item.get('category', 'unknown')
        item_id = local.stem.replace(' ', '_')
        media_type = item.get('media_type', 'image')

        if media_type == 'video':
            print(f'  [{i+1}/{len(items)}] 🎬 {cat}/{local.name[:40]}...')
            result = optimize_video(local, cat, item_id)
            if result:
                result['title'] = item.get('title', '')
                result['description'] = item.get('description', '')
                api_items.append(result)
                vid_count += 1
        else:
            if (i + 1) % 20 == 0:
                print(f'  [{i+1}/{len(items)}] 🖼️  Processing images...')
            result = optimize_image(local, cat, item_id)
            if result:
                result['title'] = item.get('title', '')
                result['description'] = item.get('description', '')
                api_items.append(result)
                img_count += 1

    print(f'\n  ✅ Optimized: {img_count} images + {vid_count} videos')

    # Size comparison
    orig_size = sum(Path(i['local_path']).stat().st_size for i in items if Path(i.get('local_path','')).exists())
    opt_size = sum(f.stat().st_size for f in OPTIMIZED_DIR.rglob('*') if f.is_file())
    print(f'  📦 Original: {orig_size/1024/1024/1024:.1f} GB → Optimized: {opt_size/1024/1024/1024:.1f} GB ({100-opt_size/orig_size*100:.0f}% smaller)')

    # ── Step 2: Generate API JSONs ────────────────────────
    print('\n[Step 2] 📋 Generating API JSONs...')

    api_dir = OPTIMIZED_DIR / 'api'
    api_dir.mkdir(exist_ok=True)

    # Categories JSON
    categories = {}
    for item in api_items:
        cat = item['category']
        if cat not in categories:
            categories[cat] = {'id': cat, 'name': CATEGORY_NAMES.get(cat, cat), 'images': 0, 'videos': 0}
        if item['type'] == 'image':
            categories[cat]['images'] += 1
        else:
            categories[cat]['videos'] += 1

    cat_list = sorted(categories.values(), key=lambda x: x['images'] + x['videos'], reverse=True)
    (api_dir / 'categories.json').write_text(json.dumps(cat_list, ensure_ascii=False, indent=2))

    # Per-category JSON (paginated, 20 per page)
    PAGE_SIZE = 20
    for cat_id, cat_info in categories.items():
        cat_items = [i for i in api_items if i['category'] == cat_id]

        # Add public URLs
        for item in cat_items:
            for key in ['thumb', 'preview', 'full', 'video']:
                if key in item:
                    item[f'{key}_url'] = f'{R2_PUBLIC_URL}/{item[key]}'

        total_pages = (len(cat_items) + PAGE_SIZE - 1) // PAGE_SIZE
        for page in range(total_pages):
            start = page * PAGE_SIZE
            end = start + PAGE_SIZE
            page_data = {
                'category': cat_id,
                'name': cat_info['name'],
                'page': page + 1,
                'total_pages': total_pages,
                'total_items': len(cat_items),
                'items': cat_items[start:end],
            }
            fname = f'{cat_id}.json' if page == 0 else f'{cat_id}_{page+1}.json'
            (api_dir / fname).write_text(json.dumps(page_data, ensure_ascii=False, indent=2))

    # All items summary (for home screen)
    featured = sorted(api_items, key=lambda x: x.get('full_size', x.get('video_size', 0)), reverse=True)[:30]
    for item in featured:
        for key in ['thumb', 'preview', 'full', 'video']:
            if key in item:
                item[f'{key}_url'] = f'{R2_PUBLIC_URL}/{item[key]}'

    home_data = {
        'generated': datetime.now().isoformat(),
        'total_images': img_count,
        'total_videos': vid_count,
        'categories': cat_list,
        'featured': featured,
    }
    (api_dir / 'home.json').write_text(json.dumps(home_data, ensure_ascii=False, indent=2))

    print(f'  ✅ Generated {len(categories)} category JSONs + home.json')

    # ── Step 3: Upload to R2 ──────────────────────────────
    print('\n[Step 3] ☁️  Uploading to R2...')

    if not all([R2_ACCESS_KEY, R2_SECRET_KEY]):
        print('  ⚠️ R2 credentials missing, skipping upload')
        print(f'  Files ready at: {OPTIMIZED_DIR}')
        return

    files_to_upload = list(OPTIMIZED_DIR.rglob('*'))
    files_to_upload = [f for f in files_to_upload if f.is_file()]
    print(f'  Files to upload: {len(files_to_upload)}')

    uploaded = 0
    errors = 0

    s3 = boto3.client('s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
    )

    for i, fpath in enumerate(files_to_upload):
        r2_key = str(fpath.relative_to(OPTIMIZED_DIR))
        # Prefix with wallpaper/ for non-api files
        if not r2_key.startswith('api/'):
            r2_key = f'wallpaper/{r2_key}' if not r2_key.startswith('wallpaper/') else r2_key
        else:
            r2_key = f'wallpaper/{r2_key}'

        ct = get_content_type(str(fpath))

        try:
            s3.upload_file(
                str(fpath), R2_BUCKET, r2_key,
                ExtraArgs={'ContentType': ct, 'CacheControl': 'public, max-age=31536000'}
            )
            uploaded += 1
            if (i + 1) % 50 == 0:
                print(f'  [{i+1}/{len(files_to_upload)}] uploaded...')
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f'  ❌ {r2_key}: {e}')

    print(f'\n  ✅ Uploaded: {uploaded} | Errors: {errors}')

    # ── Summary ───────────────────────────────────────────
    print('\n' + '═' * 55)
    print('✅ ALL DONE!')
    print('═' * 55)
    print(f'Images: {img_count} | Videos: {vid_count}')
    print(f'Optimized size: {opt_size/1024/1024/1024:.2f} GB')
    print(f'\nAPI endpoints:')
    print(f'  {R2_PUBLIC_URL}/wallpaper/api/home.json')
    print(f'  {R2_PUBLIC_URL}/wallpaper/api/categories.json')
    print(f'  {R2_PUBLIC_URL}/wallpaper/api/{{category}}.json')
    print(f'\nImage URLs:')
    print(f'  Thumb:   {R2_PUBLIC_URL}/wallpaper/{{cat}}/thumb/{{id}}.webp')
    print(f'  Preview: {R2_PUBLIC_URL}/wallpaper/{{cat}}/preview/{{id}}.webp')
    print(f'  Full:    {R2_PUBLIC_URL}/wallpaper/{{cat}}/full/{{id}}.webp')
    print(f'  Video:   {R2_PUBLIC_URL}/wallpaper/{{cat}}/video/{{id}}.mp4')


if __name__ == '__main__':
    main()
