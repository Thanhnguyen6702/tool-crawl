#!/bin/bash
# ══════════════════════════════════════════════════════════
# Wallpaper Trending Crawler - Nguồn xịn, top quality
# ══════════════════════════════════════════════════════════
#
# IMAGES:
#   1. Wallhaven API - Top favorited anime/gaming (public API, best quality)
#   2. Pinterest - Character-specific searches
#   3. Zerochan - Anime character art
#
# VIDEOS:
#   1. YouTube - Live wallpaper 4K channels
#   2. Bilibili - Donghua/Chinese anime clips
#
# OUTPUT: /home/thanh/wallpaper/trending-{category}/
# ══════════════════════════════════════════════════════════

export PATH="$HOME/.local/bin:$PATH"
WALLPAPER_DIR="/home/thanh/wallpaper"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

# ── Wallhaven API (best anime/gaming wallpapers) ──────────
wallhaven() {
    local category="$1"
    local query="$2"
    local cat_code="${3:-010}"   # 010=anime, 110=general+anime, 100=general
    local sorting="${4:-toplist}" # toplist, favorites, views
    local limit="${5:-25}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"

    echo -e "${CYAN}▶ Wallhaven${NC} [$category] q=\"$query\" sort=$sorting"

    python3 - "$out_dir" "$query" "$cat_code" "$sorting" "$limit" <<'PYEOF'
import sys, json, os, asyncio, aiohttp, time
from pathlib import Path

out_dir, query, cat_code, sorting, limit = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
API = 'https://wallhaven.cc/api/v1/search'
seen = set(f.stem.split('_')[-1] for f in Path(out_dir).glob('wallhaven_*'))

async def run():
    downloaded = 0
    async with aiohttp.ClientSession() as s:
        for page in range(1, 6):
            if downloaded >= limit: break
            params = {
                'q': query, 'categories': cat_code, 'purity': '100',
                'sorting': sorting, 'order': 'desc',
                'atleast': '1080x720', 'page': page,
            }
            if sorting == 'toplist':
                params['topRange'] = '1M'
            try:
                async with s.get(API, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429:
                        time.sleep(45); continue
                    if r.status != 200: break
                    data = await r.json()
            except: break

            for wp in data.get('data', []):
                if downloaded >= limit: break
                wid = wp['id']
                if wid in seen: continue
                seen.add(wid)
                url = wp.get('path', '')
                ext = url.rsplit('.', 1)[-1] if '.' in url else 'jpg'
                fpath = Path(out_dir) / f'wallhaven_{wid}.{ext}'
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as r2:
                        if r2.status == 200:
                            fpath.write_bytes(await r2.read())
                            downloaded += 1
                except: pass

            if page >= data.get('meta', {}).get('last_page', 1): break
            await asyncio.sleep(2)
    print(f'  → {downloaded} images')

asyncio.run(run())
PYEOF
    echo -e "${GREEN}✅${NC} $(find "$out_dir" -maxdepth 1 \( -name '*.jpg' -o -name '*.png' \) | wc -l) total images"
}

# ── Pinterest via gallery-dl ──────────────────────────────
pin() {
    local category="$1"
    local query="$2"
    local limit="${3:-25}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    echo -e "${CYAN}▶ Pinterest${NC} [$category] $query"

    gallery-dl \
        "https://www.pinterest.com/search/pins/?q=${query}&rs=typed" \
        --range "1-$limit" \
        -D "$out_dir" \
        --filename "pin_{id}.{extension}" \
        --write-metadata \
        --no-part \
        --sleep-request 2.5 \
        --retries 3 \
        -q 2>/dev/null

    echo -e "${GREEN}✅${NC} $(find "$out_dir" -maxdepth 1 \( -name '*.jpg' -o -name '*.png' -o -name '*.webp' \) | wc -l) total images"
}

# ── YouTube video ─────────────────────────────────────────
ytdl() {
    local category="$1"
    local query="$2"
    local limit="${3:-5}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    echo -e "${CYAN}▶ YouTube${NC} [$category] $query"

    yt-dlp \
        "ytsearch${limit}:${query}" \
        -o "$out_dir/%(title).60s.%(ext)s" \
        -f "bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1080]/best[height>=720]" \
        --merge-output-format mp4 \
        --no-playlist --max-filesize 300M \
        -q --no-warnings 2>/dev/null

    echo -e "${GREEN}✅${NC} $(find "$out_dir" -maxdepth 1 -name '*.mp4' | wc -l) total videos"
}

echo "═══════════════════════════════════════════════════"
echo "🔥 Trending Wallpaper Crawler - Multi-Source"
echo "═══════════════════════════════════════════════════"
echo ""

# ╔═════════════════════════════════════════════════════════╗
# ║  1. TRENDING ANIME - Wallhaven Top Monthly              ║
# ╚═════════════════════════════════════════════════════════╝
echo -e "\n${YELLOW}━━━ 🔥 TRENDING ANIME (Wallhaven Top Monthly) ━━━${NC}"
wallhaven "trending-anime" "" "010" "toplist" 40

# ╔═════════════════════════════════════════════════════════╗
# ║  2. TU TIÊN - Multiple sources                         ║
# ╚═════════════════════════════════════════════════════════╝
echo -e "\n${YELLOW}━━━ ⚔️ TU TIÊN / DONGHUA ━━━${NC}"

# Tiêu Viêm
wallhaven "tieu-viem" "battle through the heavens" "010" "favorites" 15
pin       "tieu-viem" "xiao+yan+battle+through+heavens+4k+wallpaper" 25
pin       "tieu-viem" "萧炎+斗破苍穹+wallpaper+高清" 15

# Thạch Hạo
wallhaven "thach-hao" "perfect world anime" "010" "favorites" 15
pin       "thach-hao" "shi+hao+perfect+world+anime+wallpaper+4k" 25
pin       "thach-hao" "石昊+完美世界+壁纸" 15

# Vương Lâm
pin       "vuong-lam" "wang+lin+renegade+immortal+xian+ni+wallpaper+4k" 25
pin       "vuong-lam" "仙逆+王林+wallpaper" 15

# Diệp Phàm  
pin       "diep-pham" "ye+fan+shrouding+heavens+zhe+tian+wallpaper+4k" 25
pin       "diep-pham" "遮天+叶凡+wallpaper" 15

# Donghua chung - nhiều bộ
wallhaven "donghua" "donghua" "010" "favorites" 15
wallhaven "donghua" "chinese anime" "010" "favorites" 15
pin       "donghua" "soul+land+douluo+dalu+wallpaper+4k" 20
pin       "donghua" "斗罗大陆+唐三+wallpaper" 15
pin       "donghua" "xianxia+donghua+anime+wallpaper+4k" 25
pin       "donghua" "martial+peak+wu+dong+qian+kun+wallpaper" 20
pin       "donghua" "stellar+transformations+swallowed+star+wallpaper" 15

# ╔═════════════════════════════════════════════════════════╗
# ║  3. GAMING - Wallhaven + Pinterest                      ║
# ╚═════════════════════════════════════════════════════════╝
echo -e "\n${YELLOW}━━━ 🎮 GAMING ━━━${NC}"

# LOL
wallhaven "lien-minh" "league of legends" "010" "favorites" 20
wallhaven "lien-minh" "arcane" "010" "favorites" 15
pin       "lien-minh" "league+of+legends+champion+splash+art+4k" 25
pin       "lien-minh" "arcane+jinx+vi+wallpaper+4k" 15

# Liên Quân / Honor of Kings
wallhaven "lien-quan" "honor of kings" "010" "favorites" 15
pin       "lien-quan" "honor+of+kings+王者荣耀+wallpaper+4k" 25
pin       "lien-quan" "arena+of+valor+splash+art+wallpaper" 20

# PUBG
wallhaven "pubg" "pubg" "110" "favorites" 15
pin       "pubg" "pubg+mobile+wallpaper+4k+hd" 25

# Genshin
wallhaven "genshin" "genshin impact" "010" "favorites" 20
pin       "genshin" "genshin+impact+character+wallpaper+4k" 25
pin       "genshin" "原神+wallpaper+4k+角色" 15

# ╔═════════════════════════════════════════════════════════╗
# ║  4. VIDEOS - YouTube 4K Live Wallpapers                 ║
# ╚═════════════════════════════════════════════════════════╝
echo -e "\n${YELLOW}━━━ 🎬 VIDEOS ━━━${NC}"

# Tu Tiên
ytdl "tieu-viem" "Xiao Yan Battle Through the Heavens live wallpaper 4K loop" 6
ytdl "thach-hao" "Perfect World Shi Hao anime live wallpaper 4K" 5
ytdl "vuong-lam" "Renegade Immortal Wang Lin live wallpaper" 4
ytdl "donghua"   "donghua xianxia live wallpaper 4K engine loop" 8
ytdl "donghua"   "Soul Land Tang San live wallpaper 4K" 5

# Gaming
ytdl "lien-minh" "League of Legends live wallpaper 4K engine loop" 8
ytdl "lien-minh" "Arcane LOL live wallpaper 4K" 4
ytdl "lien-quan" "Honor of Kings arena of valor live wallpaper 4K" 5
ytdl "pubg"      "PUBG mobile live wallpaper 4K loop" 5
ytdl "genshin"   "Genshin Impact live wallpaper 4K engine loop" 8

# Trending
ytdl "trending-anime" "anime live wallpaper 4K trending 2024" 8
ytdl "trending-anime" "best anime live wallpaper engine 4K" 5

# ═══════════════════════════════════════════════════════════
echo -e "\n═══════════════════════════════════════════════════"
echo "✅ DONE!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "📊 Summary:"
for dir in "$WALLPAPER_DIR"/*/; do
    cat=$(basename "$dir")
    imgs=$(find "$dir" -maxdepth 1 \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.webp" \) 2>/dev/null | wc -l)
    vids=$(find "$dir" -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l)
    size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    printf "  %-20s %3d imgs  %2d vids  %s\n" "$cat" "$imgs" "$vids" "$size"
done
echo ""
total_imgs=$(find "$WALLPAPER_DIR" \( -name "*.jpg" -o -name "*.png" -o -name "*.webp" \) | wc -l)
total_vids=$(find "$WALLPAPER_DIR" -name "*.mp4" | wc -l)
echo "Total: $total_imgs images + $total_vids videos ($(du -sh "$WALLPAPER_DIR" | cut -f1))"

# ── Rebuild metadata ──────────────────────────────────────
python3 - <<'PYEOF'
import json, os
from pathlib import Path

WALLPAPER_DIR = Path('/home/thanh/wallpaper')

# Character keywords for smart categorization
CHAR_MAP = {
    'tieu-viem': ['xiao yan', 'tiêu viêm', '萧炎', 'battle through', 'doupo', '斗破苍穹'],
    'thach-hao': ['shi hao', 'thạch hạo', '石昊', 'perfect world', 'wanmei', '完美世界'],
    'vuong-lam': ['wang lin', 'vương lâm', '王林', 'renegade immortal', 'xian ni', '仙逆'],
    'diep-pham': ['ye fan', 'diệp phàm', '叶凡', 'shrouding', 'zhe tian', '遮天'],
    'donghua': ['donghua', 'xianxia', 'cultivation', 'soul land', 'douluo', 'tang san', '唐三', 'martial', 'swallowed star'],
    'lien-minh': ['league of legends', 'lol', 'arcane', 'yasuo', 'jinx', 'riot'],
    'lien-quan': ['arena of valor', 'honor of kings', '王者荣耀', 'aov'],
    'pubg': ['pubg', 'battlegrounds'],
    'genshin': ['genshin', '原神'],
    'trending-anime': ['anime', 'trending'],
}

all_items = []
for cat_dir in sorted(WALLPAPER_DIR.iterdir()):
    if not cat_dir.is_dir(): continue
    cat = cat_dir.name
    for f in sorted(cat_dir.iterdir()):
        if f.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.mp4']: continue
        media_type = 'video' if f.suffix.lower() == '.mp4' else 'image'

        # Read Pinterest metadata
        title, description, board, seo = '', '', '', ''
        meta_file = f.with_suffix(f.suffix + '.json')
        if meta_file.exists():
            try:
                md = json.loads(meta_file.read_text())
                title = md.get('title', '') or md.get('grid_title', '') or ''
                description = md.get('description', '') or ''
                board = md.get('board', {}).get('name', '') if isinstance(md.get('board'), dict) else ''
                seo = md.get('seo_alt_text', '') or ''
            except: pass

        all_text = f'{title} {description} {board} {seo} {f.stem}'.lower()
        best_cat = cat
        best_score = 0
        for c, kws in CHAR_MAP.items():
            score = sum(1 for kw in kws if kw.lower() in all_text)
            if score > best_score:
                best_score = score
                best_cat = c

        if best_score < 2:
            best_cat = cat

        all_items.append({
            'url': f'/wallpaper/images/{cat}/{f.name}',
            'filename': f.name,
            'category': cat,
            'best_category': best_cat,
            'media_type': media_type,
            'title': title or f.stem.replace('_', ' ').replace('-', ' '),
            'description': description[:200],
            'size': f.stat().st_size,
            'local_path': str(f),
        })

with open(WALLPAPER_DIR / 'metadata.json', 'w') as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)

imgs = sum(1 for i in all_items if i['media_type']=='image')
vids = sum(1 for i in all_items if i['media_type']=='video')
print(f'Metadata: {imgs} images + {vids} videos')
PYEOF

echo "Preview: http://localhost:3000/wallpaper"
