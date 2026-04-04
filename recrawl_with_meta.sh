#!/bin/bash
# Re-crawl Pinterest with metadata for better categorization
export PATH="$HOME/.local/bin:$PATH"

WALLPAPER_DIR="/home/thanh/wallpaper"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

# Clean old data
rm -rf "$WALLPAPER_DIR"/*

pin() {
    local category="$1"
    local query="$2"
    local limit="${3:-30}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    echo -e "${CYAN}▶${NC} [$category] $query"

    gallery-dl \
        "https://www.pinterest.com/search/pins/?q=${query}&rs=typed" \
        --range "1-$limit" \
        -D "$out_dir" \
        --filename "{id}.{extension}" \
        --write-metadata \
        --no-part \
        --sleep-request 2.5 \
        --retries 3 \
        -q 2>/dev/null

    echo -e "${GREEN}✅${NC} $(find "$out_dir" -maxdepth 1 \( -name "*.jpg" -o -name "*.png" -o -name "*.webp" \) | wc -l) images"
}

ytdl() {
    local category="$1"
    local query="$2"
    local limit="${3:-5}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    echo -e "${CYAN}▶${NC} YT [$category] $query"

    yt-dlp \
        "ytsearch${limit}:${query}" \
        -o "$out_dir/%(title).60s.%(ext)s" \
        -f "bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1080]/best[height>=720]" \
        --merge-output-format mp4 \
        --no-playlist \
        --max-filesize 300M \
        -q --no-warnings 2>/dev/null

    echo -e "${GREEN}✅${NC} $(find "$out_dir" -maxdepth 1 -name "*.mp4" | wc -l) videos"
}

echo "════════════════════════════════════"
echo "🐉 Re-crawl with Metadata"
echo "════════════════════════════════════"

# ── Tu Tiên ──
pin "tieu-viem" "xiao+yan+battle+through+the+heavens+wallpaper+4k" 30
pin "tieu-viem" "doupo+cangqiong+xiao+yan+wallpaper" 25
pin "tieu-viem" "battle+through+the+heavens+anime+wallpaper" 20

pin "thach-hao" "shi+hao+perfect+world+anime+wallpaper+4k" 30
pin "thach-hao" "perfect+world+wanmei+shijie+wallpaper" 25
pin "thach-hao" "stone+ape+perfect+world+wallpaper" 15

pin "vuong-lam" "wang+lin+xian+ni+renegade+immortal+wallpaper" 30
pin "vuong-lam" "renegade+immortal+anime+wallpaper+4k" 25

pin "diep-pham" "ye+fan+shrouding+heavens+anime+wallpaper" 30
pin "diep-pham" "zhe+tian+donghua+wallpaper+4k" 25

pin "donghua"   "xianxia+chinese+anime+wallpaper+4k" 30
pin "donghua"   "donghua+anime+wallpaper+hd" 25
pin "donghua"   "soul+land+douluo+dalu+wallpaper+4k" 20
pin "donghua"   "swallowed+star+tunshi+xingkong+wallpaper" 15
pin "donghua"   "against+the+gods+wallpaper+4k" 15

# ── Gaming ──
pin "lien-minh" "league+of+legends+4k+wallpaper" 30
pin "lien-minh" "league+of+legends+champion+wallpaper" 25
pin "lien-minh" "arcane+league+of+legends+wallpaper+4k" 20
pin "lien-minh" "yasuo+lol+wallpaper" 15

pin "lien-quan" "arena+of+valor+wallpaper+4k" 25
pin "lien-quan" "honor+of+kings+wallpaper+4k" 25

pin "pubg"      "pubg+mobile+wallpaper+4k" 25
pin "pubg"      "pubg+battlegrounds+4k+wallpaper" 25

pin "genshin"   "genshin+impact+wallpaper+4k" 30
pin "genshin"   "genshin+impact+character+wallpaper" 25

# ── Videos ──
ytdl "tieu-viem" "Xiao Yan Battle Through Heavens live wallpaper 4K" 6
ytdl "thach-hao" "Shi Hao Perfect World live wallpaper 4K" 6
ytdl "vuong-lam" "Renegade Immortal Wang Lin live wallpaper 4K" 5
ytdl "donghua"   "xianxia donghua live wallpaper engine 4K" 8
ytdl "donghua"   "Soul Land Douluo Dalu live wallpaper" 5
ytdl "lien-minh" "League of Legends live wallpaper 4K" 8
ytdl "lien-minh" "League of Legends cinematic 2024 4K" 4
ytdl "lien-quan" "Arena of Valor live wallpaper 4K" 6
ytdl "pubg"      "PUBG Mobile live wallpaper 4K engine" 6
ytdl "genshin"   "Genshin Impact live wallpaper 4K" 8

echo ""
echo "✅ Crawl done. Building smart metadata..."

# ── Build metadata with title/description ──
python3 - <<'PYEOF'
import json, os, re
from pathlib import Path

WALLPAPER_DIR = Path('/home/thanh/wallpaper')

# Character keywords for re-classification
CHAR_MAP = {
    'tieu-viem': ['xiao yan', 'tiêu viêm', '萧炎', 'battle through', 'doupo', '斗破苍穹', 'đấu phá'],
    'thach-hao': ['shi hao', 'thạch hạo', '石昊', 'perfect world', 'wanmei', '完美世界', 'hoàn mỹ'],
    'vuong-lam': ['wang lin', 'vương lâm', '王林', 'renegade immortal', 'xian ni', '仙逆', 'tiên nghịch'],
    'diep-pham': ['ye fan', 'diệp phàm', '叶凡', 'shrouding', 'zhe tian', '遮天', 'già thiên'],
    'donghua': ['donghua', 'xianxia', 'cultivation', 'soul land', 'douluo', 'tu tiên', 'martial', 'swallowed star', 'immortal'],
    'lien-minh': ['league of legends', 'lol', 'arcane', 'yasuo', 'jinx', 'riot', 'liên minh'],
    'lien-quan': ['arena of valor', 'honor of kings', '王者荣耀', 'liên quân', 'aov'],
    'pubg': ['pubg', 'battlegrounds', 'playerunknown'],
    'genshin': ['genshin', '原神', 'genshin impact', 'teyvat', 'paimon'],
}

all_items = []
reclassified = 0

for cat_dir in sorted(WALLPAPER_DIR.iterdir()):
    if not cat_dir.is_dir():
        continue
    orig_cat = cat_dir.name

    for f in sorted(cat_dir.iterdir()):
        if f.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.mp4']:
            continue
        if f.name == 'metadata.json':
            continue

        media_type = 'video' if f.suffix.lower() == '.mp4' else 'image'

        # Read Pinterest metadata if exists
        meta_file = f.with_suffix(f.suffix + '.json')
        title = ''
        description = ''
        board = ''
        seo = ''

        if meta_file.exists():
            try:
                with open(meta_file) as mf:
                    md = json.load(mf)
                title = md.get('title', '') or md.get('grid_title', '') or ''
                description = md.get('description', '') or ''
                board = md.get('board', {}).get('name', '') if isinstance(md.get('board'), dict) else ''
                seo = md.get('seo_alt_text', '') or ''
            except:
                pass

        # Combine all text for matching
        all_text = f'{title} {description} {board} {seo}'.lower()

        # Try to find best category match
        best_cat = orig_cat
        best_score = 0

        for cat, keywords in CHAR_MAP.items():
            score = sum(1 for kw in keywords if kw.lower() in all_text)
            if score > best_score:
                best_score = score
                best_cat = cat

        if best_cat != orig_cat and best_score >= 2:
            reclassified += 1

        # Use original category if no strong match (keep folder structure)
        display_title = title or description or f.stem
        if len(display_title) > 60:
            display_title = display_title[:60] + '...'

        all_items.append({
            'url': f'/wallpaper/images/{orig_cat}/{f.name}',
            'filename': f.name,
            'category': orig_cat,
            'best_category': best_cat,
            'media_type': media_type,
            'title': title,
            'description': description[:200],
            'board': board,
            'size': f.stat().st_size,
            'local_path': str(f),
        })

with open(WALLPAPER_DIR / 'metadata.json', 'w') as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)

imgs = sum(1 for i in all_items if i['media_type'] == 'image')
vids = sum(1 for i in all_items if i['media_type'] == 'video')
titled = sum(1 for i in all_items if i['title'])
print(f'Total: {imgs} images + {vids} videos')
print(f'With title: {titled}/{len(all_items)}')
print(f'Would reclassify: {reclassified}')

# Show some mismatches
mismatches = [i for i in all_items if i['category'] != i['best_category'] and i['title']]
for m in mismatches[:10]:
    print(f'  {m["category"]} → {m["best_category"]}: {m["title"][:60]}')
PYEOF
