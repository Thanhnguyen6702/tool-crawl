#!/usr/bin/env python3
"""
Optimize wallpapers & upload to Cloudflare R2 — V2
- Higher quality: thumb q=85, preview q=92, full q=95
- Sizes: thumb 480px, preview 1080px, full = original (max 2160)
- Filter low-quality images (< 600px wide, landscape)
- Proper pagination API (no 404)
- Parallel processing per category
"""

import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import boto3
from PIL import Image
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

# ── Config ──────────────────────────────────────────────────────
WALLPAPER_DIR  = Path('/home/thanh/wallpaper')
OPTIMIZED_DIR  = Path('/home/thanh/wallpaper-optimized-v2')
FFMPEG         = os.path.expanduser('~/.local/bin/ffmpeg')

R2_ENDPOINT    = f"https://{os.getenv('CLOUDFLARE_ACCOUNT_ID')}.r2.cloudflarestorage.com"
R2_ACCESS_KEY  = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_KEY  = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET      = os.getenv('R2_BUCKET_NAME', 'funnycolor')
R2_PUBLIC_URL  = os.getenv('R2_PUBLIC_URL', '').rstrip('/')

THUMB_WIDTH    = 480;  THUMB_Q    = 85
PREVIEW_WIDTH  = 1080; PREVIEW_Q  = 92
FULL_MAX_WIDTH = 2160; FULL_Q     = 95

MIN_WIDTH  = 600
MIN_HEIGHT = 800

VIDEO_HEIGHT  = 1080
VIDEO_BITRATE = '4M'
PAGE_SIZE     = 20
WORKERS       = 6   # parallel image workers per category

CATEGORY_NAMES = {
    'tieu-viem':     'Tiêu Viêm',
    'thach-hao':     'Thạch Hạo',
    'vuong-lam':     'Vương Lâm',
    'diep-pham':     'Diệp Phàm',
    'donghua':       'Donghua',
    'lien-minh':     'Liên Minh',
    'lien-quan':     'Liên Quân',
    'pubg':          'PUBG',
    'genshin':       'Genshin Impact',
    'trending-anime':'Trending Anime',
}
CATEGORY_ORDER = list(CATEGORY_NAMES.keys())


# ── S3/R2 ────────────────────────────────────────────────────────
def get_s3():
    return boto3.client('s3', endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY, aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto')

def delete_r2_prefix(s3, prefix='wallpaper/'):
    print(f'🗑️  Deleting R2: {prefix}...')
    paginator = s3.get_paginator('list_objects_v2')
    total = 0
    for page in paginator.paginate(Bucket=R2_BUCKET, Prefix=prefix):
        objs = page.get('Contents', [])
        if not objs: break
        keys = [{'Key': o['Key']} for o in objs]
        s3.delete_objects(Bucket=R2_BUCKET, Delete={'Objects': keys})
        total += len(keys)
        print(f'  deleted {total}...', end='\r')
    print(f'\n✅ Deleted {total} objects')

def upload_file(s3, local, key, ct=None):
    if not ct:
        ext = str(local).rsplit('.', 1)[-1].lower()
        ct = {'webp':'image/webp','jpg':'image/jpeg','jpeg':'image/jpeg',
              'png':'image/png','mp4':'video/mp4','json':'application/json'
             }.get(ext, 'application/octet-stream')
    s3.upload_file(str(local), R2_BUCKET, key, ExtraArgs={
        'ContentType': ct, 'CacheControl': 'public, max-age=31536000'})


# ── Image optimization ───────────────────────────────────────────
def optimize_one_image(args):
    src, cat, item_id, cat_dir = args
    try:
        img = Image.open(src)
        w, h = img.size

        if w < MIN_WIDTH or h < MIN_HEIGHT:
            return None
        if w > h * 1.3:
            return None  # landscape

        result = {'id': item_id, 'category': cat, 'type': 'IMAGE', 'width': w, 'height': h}

        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (0, 0, 0))
            bg.paste(img, mask=img.split()[3]); img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # thumb
        td = cat_dir / 'thumb'; td.mkdir(parents=True, exist_ok=True)
        tp = td / f'{item_id}.webp'
        if not tp.exists():
            t = img.resize((THUMB_WIDTH, int(h * THUMB_WIDTH / w)), Image.LANCZOS)
            t.save(tp, 'WEBP', quality=THUMB_Q)
        result['thumb'] = f'wallpaper/{cat}/thumb/{item_id}.webp'

        # preview
        pd2 = cat_dir / 'preview'; pd2.mkdir(parents=True, exist_ok=True)
        pp = pd2 / f'{item_id}.webp'
        if not pp.exists():
            if w > PREVIEW_WIDTH:
                pv = img.resize((PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)), Image.LANCZOS)
            else:
                pv = img
            pv.save(pp, 'WEBP', quality=PREVIEW_Q)
        result['preview'] = f'wallpaper/{cat}/preview/{item_id}.webp'

        # full
        fd = cat_dir / 'full'; fd.mkdir(parents=True, exist_ok=True)
        fp = fd / f'{item_id}.webp'
        if not fp.exists():
            if w > FULL_MAX_WIDTH:
                fi = img.resize((FULL_MAX_WIDTH, int(h * FULL_MAX_WIDTH / w)), Image.LANCZOS)
            else:
                fi = img
            fi.save(fp, 'WEBP', quality=FULL_Q)
        result['full'] = f'wallpaper/{cat}/full/{item_id}.webp'

        img.close()
        return result
    except Exception as e:
        return None

def optimize_video(src, cat, item_id, cat_dir):
    try:
        vd = cat_dir / 'video'; vd.mkdir(parents=True, exist_ok=True)
        out = vd / f'{item_id}.mp4'
        if not out.exists():
            subprocess.run([FFMPEG,'-y','-i',str(src),
                '-vf',f'scale=-2:{VIDEO_HEIGHT}','-c:v','libx264','-preset','fast',
                '-b:v',VIDEO_BITRATE,'-c:a','aac','-b:a','128k',
                '-movflags','+faststart',str(out)],
                capture_output=True, timeout=300)
        if not out.exists() or out.stat().st_size == 0:
            return None
        # thumb from video
        td = cat_dir / 'thumb'; td.mkdir(parents=True, exist_ok=True)
        tp = td / f'{item_id}.webp'
        if not tp.exists():
            subprocess.run([FFMPEG,'-y','-i',str(src),'-vframes','1','-ss','1',
                f'-vf','scale={THUMB_WIDTH}:-2',str(tp)], capture_output=True, timeout=60)
        return {'id': item_id, 'category': cat, 'type': 'VIDEO',
                'width': 0, 'height': 0,
                'thumb': f'wallpaper/{cat}/thumb/{item_id}.webp',
                'url':   f'wallpaper/{cat}/video/{item_id}.mp4'}
    except: return None


# ── API JSON ─────────────────────────────────────────────────────
def to_api_item(item, base_url):
    p = f'{base_url}/wallpaper/{item["category"]}'
    if item['type'] == 'VIDEO':
        return {'id': item['id'], 'url': f'{p}/video/{item["id"]}.mp4',
                'thumbnailUrl': f'{p}/thumb/{item["id"]}.webp',
                'previewUrl':   f'{p}/thumb/{item["id"]}.webp',
                'type': 'VIDEO', 'category': item['category'],
                'width': item.get('width',0), 'height': item.get('height',0)}
    return {'id': item['id'],
            'url':          f'{p}/full/{item["id"]}.webp',
            'thumbnailUrl': f'{p}/thumb/{item["id"]}.webp',
            'previewUrl':   f'{p}/preview/{item["id"]}.webp',
            'type': 'IMAGE', 'category': item['category'],
            'width': item.get('width',0), 'height': item.get('height',0)}

def generate_api(all_items, api_dir, base_url):
    api_dir.mkdir(parents=True, exist_ok=True)
    by_cat = {}
    for it in all_items:
        by_cat.setdefault(it['category'], []).append(it)

    cats_list, all_wp = [], []
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat, [])
        if not items: continue
        wps = [to_api_item(it, base_url) for it in items]
        all_wp.extend(wps)
        cat_thumb = next((w['thumbnailUrl'] for w in wps if w['type']=='IMAGE'), wps[0]['thumbnailUrl'] if wps else '')
        cats_list.append({'id': cat, 'name': CATEGORY_NAMES[cat],
                          'thumbnailUrl': cat_thumb, 'wallpaperCount': len(wps)})

        # paginated files
        total_pages = max(1, (len(wps) + PAGE_SIZE - 1) // PAGE_SIZE)
        for pg in range(1, total_pages + 1):
            chunk = wps[(pg-1)*PAGE_SIZE : pg*PAGE_SIZE]
            fname = f'{cat}.json' if pg == 1 else f'{cat}_{pg}.json'
            with open(api_dir / fname, 'w') as f:
                json.dump({'category': cat, 'page': pg, 'totalPages': total_pages,
                           'totalItems': len(wps), 'hasMore': pg < total_pages, 'data': chunk},
                          f, ensure_ascii=False)
        print(f'  📄 {cat}: {len(wps)} items → {total_pages} pages')

    # categories.json
    with open(api_dir / 'categories.json', 'w') as f:
        json.dump(cats_list, f, ensure_ascii=False, indent=2)

    # home.json
    featured = []
    for cat in CATEGORY_ORDER:
        imgs = [w for w in all_wp if w['category']==cat and w['type']=='IMAGE'][:6]
        featured.extend(imgs)
    with open(api_dir / 'home.json', 'w') as f:
        json.dump({'featured': featured[:30], 'categories': cats_list,
                   'totalWallpapers': len(all_wp)}, f, ensure_ascii=False, indent=2)

    # config.json
    with open(api_dir / 'config.json', 'w') as f:
        json.dump({'api_source':'R2', 'r2_base_url': f'{base_url}/wallpaper/api/',
                   'version': 2, 'updated_at': datetime.now().isoformat()}, f)

    print(f'\n✅ API: {len(cats_list)} categories, {len(all_wp)} wallpapers')


# ── Main ─────────────────────────────────────────────────────────
def process_category(cat):
    src_dir = WALLPAPER_DIR / cat
    if not src_dir.is_dir(): return []
    cat_dir  = OPTIMIZED_DIR / cat
    # STRICT extension filter — no .json .m4a etc.
    IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
    VID_EXTS = {'.mp4'}

    # Only pick real image/video files
    img_files = sorted(f for f in src_dir.iterdir()
                       if f.is_file() and f.suffix.lower() in IMG_EXTS)
    vid_files = sorted(f for f in src_dir.iterdir()
                       if f.is_file() and f.suffix.lower() in VID_EXTS
                       and '.f' not in f.stem)  # skip yt-dlp fragment files like .f299.mp4

    results = []
    # Sequential images (avoid PIL multithread issues)
    for idx, f in enumerate(img_files, 1):
        item_id = f'{cat}_{idx:04d}'
        r = optimize_one_image((f, cat, item_id, cat_dir))
        if r:
            results.append(r)
            print(f'  [{idx}/{len(img_files)}] {item_id}', end='\r')

    # Sequential videos
    for idx, f in enumerate(vid_files, 1):
        item_id = f'{cat}_v{idx:04d}'
        r = optimize_video(f, cat, item_id, cat_dir)
        if r: results.append(r)

    img_ok = sum(1 for r in results if r['type']=='IMAGE')
    vid_ok = sum(1 for r in results if r['type']=='VIDEO')
    print(f'  ✅ {cat}: {img_ok}/{len(img_files)} images + {vid_ok}/{len(vid_files)} videos')
    return results


def main():
    print('🎨 Wallpaper Optimizer V2')
    print(f'   Quality: thumb={THUMB_Q} preview={PREVIEW_Q} full={FULL_Q}')
    print(f'   Sizes  : thumb={THUMB_WIDTH}px preview={PREVIEW_WIDTH}px full≤{FULL_MAX_WIDTH}px')
    print()
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)

    all_items = []
    for cat in CATEGORY_ORDER:
        print(f'📁 {cat} ({CATEGORY_NAMES[cat]})')
        all_items.extend(process_category(cat))

    print('\n📝 Generating API JSON...')
    generate_api(all_items, OPTIMIZED_DIR / 'api', R2_PUBLIC_URL)

    with open(OPTIMIZED_DIR / 'metadata.json', 'w') as f:
        json.dump({'generated_at': datetime.now().isoformat(),
                   'total': len(all_items), 'items': all_items}, f, ensure_ascii=False)

    total_mb = sum(f.stat().st_size for f in OPTIMIZED_DIR.rglob('*') if f.is_file()) / 1024**2
    print(f'\n📊 Total: {len(all_items)} items | {total_mb:.1f} MB')

    if '--upload' not in sys.argv:
        print('\n💡 Run with --upload to push to R2'); return

    s3 = get_s3()
    delete_r2_prefix(s3, 'wallpaper/')

    print('\n🚀 Uploading...')
    count = errs = 0
    for root, _, files in os.walk(OPTIMIZED_DIR):
        for fname in files:
            local = Path(root) / fname
            key   = f'wallpaper/{local.relative_to(OPTIMIZED_DIR)}'
            try:
                upload_file(s3, local, key)
                count += 1
                if count % 100 == 0: print(f'  {count} uploaded...', end='\r')
            except Exception as e:
                errs += 1
                print(f'  ❌ {key}: {e}')
    print(f'\n✅ Uploaded {count} files, {errs} errors')


if __name__ == '__main__':
    main()
