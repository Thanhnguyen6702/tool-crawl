#!/bin/bash
# Scout live wallpaper sources - evaluate quality before crawling
# Only list URLs + metadata, NO download

BASE="https://wallpaperwaifu.com"
OUTPUT="/home/thanh/tool-crawl/scout_results.txt"
> "$OUTPUT"

SEARCHES=(
    "genshin+impact"
    "league+of+legends"  
    "naruto"
    "demon+slayer"
    "one+piece"
    "dragon+ball"
    "jujutsu+kaisen"
    "solo+leveling"
    "cyberpunk"
    "anime+girl"
)

echo "🔍 Scouting wallpaperwaifu.com for high-quality live wallpapers..."
echo ""

for query in "${SEARCHES[@]}"; do
    echo "=== $query ===" | tee -a "$OUTPUT"
    
    # Get wallpaper pages
    pages=$(curl -s "${BASE}/?s=${query}" | grep -oP 'href="https://wallpaperwaifu\.com/[^"]*live-wallpaper[^"]*"' | sort -u | sed 's/href="//;s/"$//')
    
    for url in $pages; do
        # Get file size from download page
        info=$(curl -s "$url" | grep -oP 'data-url="[^"]*"|File Size:[^<]*')
        file_url=$(echo "$info" | grep -oP 'data-url="[^"]*"' | sed 's/data-url="//;s/"//')
        file_size=$(echo "$info" | grep -oP 'File Size:[^<]*' | sed 's/File Size:\s*//')
        name=$(basename "$url" | sed 's/-live-wallpaper\///')
        
        if [ -n "$file_url" ]; then
            echo "  📹 $name | ${file_size:-unknown} | ${BASE}${file_url}" | tee -a "$OUTPUT"
        fi
    done
    echo "" | tee -a "$OUTPUT"
    sleep 1  # rate limit
done

echo ""
echo "✅ Results saved to $OUTPUT"
total=$(grep "📹" "$OUTPUT" | wc -l)
echo "📊 Found: $total live wallpapers"
