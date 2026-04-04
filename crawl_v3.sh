#!/bin/bash
# Wallpaper Crawler v3
# Images: Pinterest via gallery-dl
# Videos: YouTube via yt-dlp

export PATH="$HOME/.local/bin:$PATH"

WALLPAPER_DIR="/home/thanh/wallpaper"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log() { echo -e "${CYAN}▶${NC} $1"; }
ok()  { echo -e "${GREEN}✅${NC} $1"; }

# ── Pinterest image crawl ──────────────────────────────────
pin() {
    local category="$1"
    local query="$2"       # already URL-encoded English
    local limit="${3:-25}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    log "Pinterest [$category]: $query (max $limit)"

    gallery-dl \
        "https://www.pinterest.com/search/pins/?q=${query}&rs=typed" \
        --range "1-$limit" \
        -D "$out_dir" \
        --filename "{id}.{extension}" \
        --no-part \
        --sleep-request 2.5 \
        --retries 3 \
        -q 2>/dev/null

    local n=$(find "$out_dir" -maxdepth 1 \( -name "*.jpg" -o -name "*.png" -o -name "*.webp" \) | wc -l)
    ok "$category → $n images"
}

# ── YouTube video download ─────────────────────────────────
ytdl() {
    local category="$1"
    local query="$2"
    local limit="${3:-5}"
    local out_dir="$WALLPAPER_DIR/$category"
    mkdir -p "$out_dir"
    log "YouTube [$category]: $query (${limit} videos)"

    yt-dlp \
        "ytsearch${limit}:${query}" \
        -o "$out_dir/%(title).60s.%(ext)s" \
        -f "bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height>=1080]/best[height>=720]" \
        --merge-output-format mp4 \
        --no-playlist \
        --max-filesize 300M \
        -q --no-warnings 2>/dev/null

    local n=$(find "$out_dir" -maxdepth 1 -name "*.mp4" | wc -l)
    ok "$category → $n videos"
}

echo "════════════════════════════════════════"
echo "🐉 Wallpaper Crawler v3"
echo "════════════════════════════════════════"
mkdir -p "$WALLPAPER_DIR"

# ╔══════════════════════════════╗
# ║  IMAGES - Pinterest          ║
# ╚══════════════════════════════╝
echo -e "\n${YELLOW}━━━ 🖼️  IMAGES ━━━${NC}"

# Tu Tiên - Tiêu Viêm
pin "tieu-viem" "xiao+yan+battle+through+the+heavens+wallpaper+4k" 30
pin "tieu-viem" "doupo+cangqiong+xiao+yan+wallpaper" 25
pin "tieu-viem" "battle+through+the+heavens+anime+wallpaper" 20

# Tu Tiên - Thạch Hạo
pin "thach-hao" "shi+hao+perfect+world+anime+wallpaper+4k" 30
pin "thach-hao" "perfect+world+wanmei+shijie+wallpaper" 25
pin "thach-hao" "stone+ape+perfect+world+wallpaper" 15

# Tu Tiên - Vương Lâm
pin "vuong-lam"  "wang+lin+xian+ni+renegade+immortal+wallpaper" 30
pin "vuong-lam"  "renegade+immortal+anime+wallpaper+4k" 25

# Tu Tiên - Diệp Phàm
pin "diep-pham"  "ye+fan+shrouding+heavens+anime+wallpaper" 30
pin "diep-pham"  "zhe+tian+donghua+wallpaper+4k" 25

# Donghua chung
pin "donghua"    "xianxia+chinese+anime+wallpaper+4k" 30
pin "donghua"    "donghua+anime+wallpaper+hd" 25
pin "donghua"    "soul+land+douluo+dalu+wallpaper+4k" 20
pin "donghua"    "swallowed+star+tunshi+xingkong+wallpaper" 15
pin "donghua"    "against+the+gods+wallpaper+4k" 15

# Gaming - Liên Minh
pin "lien-minh"  "league+of+legends+4k+wallpaper" 30
pin "lien-minh"  "league+of+legends+champion+wallpaper" 25
pin "lien-minh"  "arcane+league+of+legends+wallpaper+4k" 20
pin "lien-minh"  "yasuo+lol+wallpaper" 15

# Gaming - Liên Quân
pin "lien-quan"  "arena+of+valor+wallpaper+4k" 25
pin "lien-quan"  "honor+of+kings+wallpaper+4k" 25

# Gaming - PUBG
pin "pubg"       "pubg+mobile+wallpaper+4k" 25
pin "pubg"       "pubg+battlegrounds+4k+wallpaper" 25

# Gaming - Genshin
pin "genshin"    "genshin+impact+wallpaper+4k" 30
pin "genshin"    "genshin+impact+character+wallpaper" 25

# ╔══════════════════════════════╗
# ║  VIDEOS - YouTube            ║
# ╚══════════════════════════════╝
echo -e "\n${YELLOW}━━━ 🎬 VIDEOS ━━━${NC}"

ytdl "tieu-viem"  "Xiao Yan Battle Through Heavens live wallpaper 4K" 6
ytdl "thach-hao"  "Shi Hao Perfect World live wallpaper 4K" 6
ytdl "vuong-lam"  "Renegade Immortal Wang Lin live wallpaper 4K" 5
ytdl "donghua"    "xianxia donghua live wallpaper engine 4K" 8
ytdl "donghua"    "Soul Land Douluo Dalu live wallpaper" 5
ytdl "lien-minh"  "League of Legends live wallpaper 4K" 8
ytdl "lien-minh"  "League of Legends cinematic 2024 4K" 4
ytdl "lien-quan"  "Arena of Valor live wallpaper 4K" 6
ytdl "pubg"       "PUBG Mobile live wallpaper 4K engine" 6
ytdl "genshin"    "Genshin Impact live wallpaper 4K" 8

# ── Summary & Metadata ────────────────────────────────────
echo -e "\n════════════════════════════════════════"
echo "✅ DONE!"
echo "════════════════════════════════════════"
echo "📊 Summary:"
for dir in "$WALLPAPER_DIR"/*/; do
    cat=$(basename "$dir")
    imgs=$(find "$dir" -maxdepth 1 \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.webp" \) 2>/dev/null | wc -l)
    vids=$(find "$dir" -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l)
    size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    printf "  %-15s %3d imgs  %2d vids  %s\n" "$cat" "$imgs" "$vids" "$size"
done
echo ""
echo "Total: $(du -sh "$WALLPAPER_DIR" 2>/dev/null | cut -f1)"

# Save metadata
python3 - <<'PYEOF'
import json, os
from pathlib import Path
WALLPAPER_DIR = Path('/home/thanh/wallpaper')
all_items = []
for cat_dir in sorted(WALLPAPER_DIR.iterdir()):
    if not cat_dir.is_dir(): continue
    cat = cat_dir.name
    for f in sorted(cat_dir.iterdir()):
        if f.name == 'metadata.json': continue
        if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            all_items.append({'url': f'/wallpaper/images/{cat}/{f.name}', 'filename': f.name, 'category': cat, 'media_type': 'image', 'local_path': str(f), 'size': f.stat().st_size})
        elif f.suffix.lower() == '.mp4':
            all_items.append({'url': f'/wallpaper/images/{cat}/{f.name}', 'filename': f.name, 'category': cat, 'media_type': 'video', 'local_path': str(f), 'size': f.stat().st_size})
with open(WALLPAPER_DIR / 'metadata.json', 'w') as f:
    json.dump(all_items, f, ensure_ascii=False, indent=2)
imgs = sum(1 for i in all_items if i['media_type']=='image')
vids = sum(1 for i in all_items if i['media_type']=='video')
print(f'Metadata saved: {imgs} images + {vids} videos')
PYEOF
