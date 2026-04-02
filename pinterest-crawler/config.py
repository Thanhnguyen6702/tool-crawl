"""
Configuration for Pinterest Wallpaper Crawler
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Pinterest configuration
PINTEREST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.pinterest.com/',
    'X-Requested-With': 'XMLHttpRequest',
}

# Target characters for xianxia wallpapers
CHARACTERS = {
    'wang_lin': {
        'names': ['王林', 'Wang Lin', 'Vương Lâm'],
        'series': ['仙逆', 'Renegade Immortal', 'Tiên Nghịch', 'Xian Ni'],
        'weight': 1.0,
    },
    'xiao_yan': {
        'names': ['萧炎', 'Xiao Yan', 'Tiêu Viêm'],
        'series': ['斗破苍穹', 'Battle Through The Heavens', 'Đấu Phá Thương Khung', 'BTTH'],
        'weight': 1.0,
    },
    'ye_fan': {
        'names': ['叶凡', 'Ye Fan', 'Diệp Phàm'],
        'series': ['遮天', 'Shrouding the Heavens', 'Già Thiên', 'Zhe Tian'],
        'weight': 1.0,
    },
    'shi_hao': {
        'names': ['石昊', 'Shi Hao', 'Thạch Hạo'],
        'series': ['完美世界', 'Perfect World', 'Thế Giới Hoàn Mỹ'],
        'weight': 1.0,
    },
}

# Search keywords
SEARCH_KEYWORDS = [
    # English
    'xianxia wallpaper 4k',
    'cultivation anime wallpaper',
    'chinese fantasy art',
    'donghua wallpaper hd',
    'immortal cultivation art',

    # Chinese
    '仙侠壁纸',
    '修仙动漫',
    '玄幻壁纸',

    # Character specific
    'Wang Lin xianxia',
    'Xiao Yan battle through the heavens',
    'Ye Fan shrouding heavens',
    'Shi Hao perfect world',

    # Series
    '仙逆壁纸',
    '斗破苍穹壁纸',
    '遮天壁纸',
    '完美世界壁纸',
]

# Quality thresholds
MIN_WIDTH = 720
MIN_HEIGHT = 720
PREFERRED_MIN_WIDTH = 1920
PREFERRED_MIN_HEIGHT = 1080

# Scoring weights
SCORE_WEIGHTS = {
    'repin': 3,
    'like': 2,
    'comment': 1,
    'quality': 1,  # Multiplied by quality_score
    'character': 1,  # Multiplied by character_score
}

# Quality score bonuses
QUALITY_SCORES = {
    '720p': 0,   # 1280x720
    '1080p': 2,  # 1920x1080
    '2k': 3,     # 2560x1440
    '4k': 5,     # 3840x2160
}

# Character match bonuses
CHARACTER_SCORES = {
    'name_match': 10,      # Character name in description
    'ai_detect': 15,       # AI detected character
    'style_match': 5,      # Xianxia style detected
    'series_match': 8,     # Series name in description
}

# CLIP model for style matching
CLIP_MODEL = 'ViT-B-32'
CLIP_PRETRAINED = 'openai'

# Style prompts for CLIP
STYLE_PROMPTS = [
    'xianxia chinese fantasy character, cultivation, ancient chinese style',
    'chinese immortal cultivator, martial arts fantasy art',
    'donghua anime character, chinese animation style',
]

# Deduplication threshold (0-1, higher = more strict)
DUPLICATE_THRESHOLD = 0.90

# Rate limiting
REQUEST_DELAY_MIN = 2  # seconds
REQUEST_DELAY_MAX = 5  # seconds
MAX_RETRIES = 3

# Storage
CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.getenv('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL')
OUTPUT_FOLDER = 'wallpaper/xianxia'

# Output
TOP_RESULTS_COUNT = 100
OUTPUT_FILE = 'top_wallpapers.json'
