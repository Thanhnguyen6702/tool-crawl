#!/usr/bin/env python3
"""
Wallpaper Pipeline V3 — Redesigned Architecture

Changes from V2:
1. JSON uses RELATIVE paths (no base URL) → app resolves with baseUrl
2. 4 tiers: thumb (480), preview (1080), full (2160), original (raw)
3. Better manifest: manifest.json at root with version, config
4. Category manifest with metadata
5. Original images preserved for download

Directory structure:
  /wallpaper/
    manifest.json                    ← app config, version, categories
    categories/
      {cat-id}/
        meta.json                    ← category info
        page_1.json ... page_N.json  ← wallpaper list (paged)
    images/
      {cat-id}/
        thumb/{id}.webp              ← 480px, q=85  (grid)
        preview/{id}.webp            ← 1080px, q=92 (preview screen)
        full/{id}.webp               ← 2160px, q=95 (set wallpaper)
        original/{id}.{ext}          ← raw file     (download/save)
    videos/
      {cat-id}/
        thumb/{id}.webp              ← video thumbnail
        {id}.mp4                     ← video file

JSON format (NO absolute URLs):
  wallpaper.thumbnailUrl = "images/tieu-viem/thumb/tieu-viem_0002.webp"
  → App resolves: baseUrl + "/" + thumbnailUrl
"""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone

from PIL import Image

# ── Config ──────────────────────────────────────────────────────
WALLPAPER_DIR  = Path('/home/thanh/wallpaper')
OUTPUT_DIR     = Path('/home/thanh/wallpaper-v3')

THUMB_WIDTH    = 480;  THUMB_Q    = 85
PREVIEW_WIDTH  = 1080; PREVIEW_Q  = 92
FULL_MAX_WIDTH = 2160; FULL_Q     = 95

MIN_WIDTH  = 600
MIN_HEIGHT = 800

PAGE_SIZE  = 20
WORKERS    = 6

CATEGORY_NAMES = {
    'tieu-viem':      'Tiêu Viêm',
    'thach-hao':      'Thạch Hạo',
    'vuong-lam':      'Vương Lâm',
    'diep-pham':      'Diệp Phàm',
    'donghua':        'Donghua',
    'lien-minh':      'Liên Minh',
    'lien-quan':      'Liên Quân',
    'pubg':           'PUBG',
    'genshin':        'Genshin Impact',
    'trending-anime': 'Trending Anime',
}

CATEGORY_ICONS = {
    'tieu-viem':      '🔥',
    'thach-hao':      '⚡',
    'vuong-lam':      '👑',
    'diep-pham':      '🍃',
    'donghua':        '🎬',
    'lien-minh':      '⚔️',
    'lien-quan':      '🏟️',
    'pubg':           '🔫',
    'genshin':        '✨',
    'trending-anime': '📈',
}

# ── Helpers ─────────────────────────────────────────────────────

def is_portrait(path: Path) -> bool:
    """Check if image is portrait (height > width)."""
    try:
        with Image.open(path) as img:
            w, h = img.size
            return h > w and w >= MIN_WIDTH and h >= MIN_HEIGHT
    except Exception:
        return False


def get_image_size(path: Path) -> tuple:
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def resize_webp(src: Path, dst: Path, max_width: int, quality: int):
    """Resize image to WebP, maintaining aspect ratio."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as img:
            w, h = img.size
            if w > max_width:
                ratio = max_width / w
                new_size = (max_width, int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(dst, 'WEBP', quality=quality, method=4)
            return True
    except Exception as e:
        print(f"  ⚠️  Skip {src.name}: {e}")
        return False


def copy_original(src: Path, dst: Path):
    """Copy original file as-is for download."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def get_file_ext(path: Path) -> str:
    return path.suffix.lower()


# ── Process Category ────────────────────────────────────────────

def process_category(cat_id: str):
    cat_dir = WALLPAPER_DIR / cat_id
    if not cat_dir.is_dir():
        print(f"⚠️  {cat_id}: not found, skipping")
        return None

    cat_name = CATEGORY_NAMES.get(cat_id, cat_id.replace('-', ' ').title())
    cat_icon = CATEGORY_ICONS.get(cat_id, '🖼️')

    # Collect valid images
    image_files = sorted([
        f for f in cat_dir.iterdir()
        if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.heic')
        and not f.name.endswith('.json')
    ])

    # Collect videos
    video_files = sorted([
        f for f in cat_dir.iterdir()
        if f.suffix.lower() in ('.mp4', '.webm')
    ])

    print(f"\n📂 {cat_name} ({cat_id}): {len(image_files)} images, {len(video_files)} videos")

    wallpapers = []
    idx = 0

    # ── Process images ──
    def process_single_image(src: Path) -> dict | None:
        nonlocal idx
        if not is_portrait(src):
            return None

        idx += 1
        wid = f"{cat_id}_{idx:04d}"
        ext = get_file_ext(src)
        w, h = get_image_size(src)

        # Paths relative to output root
        thumb_rel   = f"images/{cat_id}/thumb/{wid}.webp"
        preview_rel = f"images/{cat_id}/preview/{wid}.webp"
        full_rel    = f"images/{cat_id}/full/{wid}.webp"
        orig_rel    = f"images/{cat_id}/original/{wid}{ext}"

        thumb_out   = OUTPUT_DIR / thumb_rel
        preview_out = OUTPUT_DIR / preview_rel
        full_out    = OUTPUT_DIR / full_rel
        orig_out    = OUTPUT_DIR / orig_rel

        # Generate tiers
        ok_thumb   = resize_webp(src, thumb_out, THUMB_WIDTH, THUMB_Q)
        ok_preview = resize_webp(src, preview_out, PREVIEW_WIDTH, PREVIEW_Q)
        ok_full    = resize_webp(src, full_out, FULL_MAX_WIDTH, FULL_Q)

        if not (ok_thumb and ok_preview and ok_full):
            return None

        # Copy original
        copy_original(src, orig_out)

        orig_size = orig_out.stat().st_size

        return {
            "id": wid,
            "type": "IMAGE",
            "category": cat_id,
            "width": w,
            "height": h,
            "thumbnail": thumb_rel,
            "preview": preview_rel,
            "full": full_rel,
            "original": orig_rel,
            "originalSize": orig_size,
            "originalFormat": ext.lstrip('.').upper(),
        }

    # Process images in parallel
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_single_image, f): f for f in image_files}
        for future in as_completed(futures):
            result = future.result()
            if result:
                wallpapers.append(result)

    # Sort by ID
    wallpapers.sort(key=lambda x: x['id'])

    # Re-index
    for i, wp in enumerate(wallpapers):
        new_id = f"{cat_id}_{i+1:04d}"
        wp['id'] = new_id

    # ── Process videos ──
    for vf in video_files:
        idx += 1
        wid = f"{cat_id}_v{idx:04d}"
        vid_rel = f"videos/{cat_id}/{wid}.mp4"

        # Copy video
        vid_out = OUTPUT_DIR / vid_rel
        vid_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vf, vid_out)

        # Generate thumbnail from video
        thumb_rel = f"videos/{cat_id}/thumb/{wid}.webp"
        thumb_out = OUTPUT_DIR / thumb_rel
        thumb_out.parent.mkdir(parents=True, exist_ok=True)

        # Try ffmpeg for video thumbnail
        try:
            subprocess.run([
                'ffmpeg', '-y', '-i', str(vf),
                '-vframes', '1', '-q:v', '2',
                str(thumb_out.with_suffix('.jpg'))
            ], capture_output=True, timeout=10)

            jpg_tmp = thumb_out.with_suffix('.jpg')
            if jpg_tmp.exists():
                resize_webp(jpg_tmp, thumb_out, THUMB_WIDTH, THUMB_Q)
                jpg_tmp.unlink()
        except Exception:
            pass

        vid_size = vid_out.stat().st_size

        wallpapers.append({
            "id": wid,
            "type": "VIDEO",
            "category": cat_id,
            "width": 0,
            "height": 0,
            "thumbnail": thumb_rel if (OUTPUT_DIR / thumb_rel).exists() else "",
            "preview": thumb_rel if (OUTPUT_DIR / thumb_rel).exists() else "",
            "full": vid_rel,
            "original": vid_rel,
            "originalSize": vid_size,
            "originalFormat": "MP4",
        })

    print(f"   ✅ {len(wallpapers)} wallpapers processed")

    # ── Write paginated JSON ──
    cat_api_dir = OUTPUT_DIR / "categories" / cat_id
    cat_api_dir.mkdir(parents=True, exist_ok=True)

    total_pages = max(1, (len(wallpapers) + PAGE_SIZE - 1) // PAGE_SIZE)

    for page in range(1, total_pages + 1):
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_data = {
            "page": page,
            "totalPages": total_pages,
            "totalItems": len(wallpapers),
            "pageSize": PAGE_SIZE,
            "items": wallpapers[start:end],
        }
        page_file = cat_api_dir / f"page_{page}.json"
        with open(page_file, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, ensure_ascii=False, indent=2)

    # ── Write category meta ──
    images_count = sum(1 for w in wallpapers if w['type'] == 'IMAGE')
    videos_count = sum(1 for w in wallpapers if w['type'] == 'VIDEO')

    # Pick first image as category thumbnail
    first_img = next((w for w in wallpapers if w['type'] == 'IMAGE'), None)

    meta = {
        "id": cat_id,
        "name": cat_name,
        "icon": cat_icon,
        "thumbnail": first_img['thumbnail'] if first_img else "",
        "totalItems": len(wallpapers),
        "imageCount": images_count,
        "videoCount": videos_count,
        "totalPages": total_pages,
    }

    with open(cat_api_dir / "meta.json", 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


# ── Main ────────────────────────────────────────────────────────

def main():
    print("🚀 Wallpaper Pipeline V3")
    print(f"   Input:  {WALLPAPER_DIR}")
    print(f"   Output: {OUTPUT_DIR}")
    print()

    # Clean output
    if OUTPUT_DIR.exists():
        print("🗑️  Cleaning previous output...")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Process each category
    all_categories = []
    total_wallpapers = 0

    for cat_id in sorted(CATEGORY_NAMES.keys()):
        meta = process_category(cat_id)
        if meta:
            all_categories.append(meta)
            total_wallpapers += meta['totalItems']

    # ── Write manifest.json ──
    manifest = {
        "version": 3,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "apiVersion": "v3",
        "config": {
            "pageSize": PAGE_SIZE,
            "imageTiers": {
                "thumbnail": {"maxWidth": THUMB_WIDTH, "quality": THUMB_Q, "format": "webp"},
                "preview":   {"maxWidth": PREVIEW_WIDTH, "quality": PREVIEW_Q, "format": "webp"},
                "full":      {"maxWidth": FULL_MAX_WIDTH, "quality": FULL_Q, "format": "webp"},
                "original":  {"description": "Raw file, original format and resolution"},
            },
        },
        "stats": {
            "totalCategories": len(all_categories),
            "totalWallpapers": total_wallpapers,
            "totalImages": sum(c['imageCount'] for c in all_categories),
            "totalVideos": sum(c['videoCount'] for c in all_categories),
        },
        "categories": all_categories,
    }

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"✅ Pipeline V3 complete!")
    print(f"   Categories:  {len(all_categories)}")
    print(f"   Wallpapers:  {total_wallpapers}")
    print(f"   Output:      {OUTPUT_DIR}")
    print(f"   Manifest:    {manifest_path}")

    # Size report
    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.rglob('*') if f.is_file())
    print(f"   Total size:  {total_size / (1024**3):.2f} GB")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
