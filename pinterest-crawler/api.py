"""
FastAPI endpoints for Wallpaper API
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import OUTPUT_FILE, CHARACTERS, TOP_RESULTS_COUNT

app = FastAPI(
    title='Xianxia Wallpaper API',
    description='API for high-quality xianxia/cultivation anime wallpapers',
    version='1.0.0',
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class WallpaperImage(BaseModel):
    id: str
    url: str
    width: int
    height: int
    description: str = ''
    total_score: float = 0
    detected_character: str = ''
    quality_score: float = 0
    style_score: float = 0


class WallpaperResponse(BaseModel):
    total: int
    images: list[WallpaperImage]


def load_wallpapers() -> list[dict]:
    """Load wallpapers from JSON file"""
    if not os.path.exists(OUTPUT_FILE):
        return []

    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('images', [])


@app.get('/')
async def root():
    """API info"""
    return {
        'name': 'Xianxia Wallpaper API',
        'version': '1.0.0',
        'endpoints': {
            '/top-wallpapers': 'Get top ranked wallpapers',
            '/character/{name}': 'Get wallpapers by character',
            '/search': 'Search wallpapers',
            '/stats': 'Get statistics',
        },
        'characters': list(CHARACTERS.keys()),
    }


@app.get('/top-wallpapers', response_model=WallpaperResponse)
async def get_top_wallpapers(
    limit: int = Query(default=100, ge=1, le=500),
    min_score: float = Query(default=0, ge=0),
    min_width: int = Query(default=0, ge=0),
    min_height: int = Query(default=0, ge=0),
):
    """Get top ranked wallpapers"""
    wallpapers = load_wallpapers()

    # Apply filters
    filtered = [
        w for w in wallpapers
        if w.get('total_score', 0) >= min_score
        and w.get('width', 0) >= min_width
        and w.get('height', 0) >= min_height
    ]

    # Sort by score
    filtered.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    # Limit
    result = filtered[:limit]

    return WallpaperResponse(
        total=len(result),
        images=[WallpaperImage(**w) for w in result]
    )


@app.get('/character/{name}', response_model=WallpaperResponse)
async def get_by_character(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get wallpapers by character name"""
    # Validate character
    name_lower = name.lower().replace(' ', '_')
    if name_lower not in CHARACTERS and name not in CHARACTERS:
        raise HTTPException(
            status_code=404,
            detail=f'Character not found. Available: {list(CHARACTERS.keys())}'
        )

    wallpapers = load_wallpapers()

    # Filter by character
    filtered = [
        w for w in wallpapers
        if (w.get('detected_character', '').lower() == name_lower or
            w.get('ai_detected_character', '').lower() == name_lower or
            name.lower() in w.get('description', '').lower())
    ]

    # Sort by score
    filtered.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    return WallpaperResponse(
        total=len(filtered[:limit]),
        images=[WallpaperImage(**w) for w in filtered[:limit]]
    )


@app.get('/search', response_model=WallpaperResponse)
async def search_wallpapers(
    q: str = Query(..., min_length=1, description='Search query'),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Search wallpapers by description"""
    wallpapers = load_wallpapers()

    query_lower = q.lower()

    # Search in description
    filtered = [
        w for w in wallpapers
        if query_lower in w.get('description', '').lower()
    ]

    # Sort by score
    filtered.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    return WallpaperResponse(
        total=len(filtered[:limit]),
        images=[WallpaperImage(**w) for w in filtered[:limit]]
    )


@app.get('/stats')
async def get_stats():
    """Get wallpaper statistics"""
    wallpapers = load_wallpapers()

    if not wallpapers:
        return {'total': 0, 'message': 'No wallpapers loaded'}

    # Character counts
    char_counts = {}
    for w in wallpapers:
        char = w.get('detected_character') or w.get('ai_detected_character') or 'unknown'
        char_counts[char] = char_counts.get(char, 0) + 1

    # Resolution stats
    resolutions = {
        '4k': 0,
        '2k': 0,
        '1080p': 0,
        '720p': 0,
        'other': 0,
    }
    for w in wallpapers:
        min_dim = min(w.get('width', 0), w.get('height', 0))
        if min_dim >= 2160:
            resolutions['4k'] += 1
        elif min_dim >= 1440:
            resolutions['2k'] += 1
        elif min_dim >= 1080:
            resolutions['1080p'] += 1
        elif min_dim >= 720:
            resolutions['720p'] += 1
        else:
            resolutions['other'] += 1

    # Score stats
    scores = [w.get('total_score', 0) for w in wallpapers]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0

    return {
        'total': len(wallpapers),
        'by_character': char_counts,
        'by_resolution': resolutions,
        'score_stats': {
            'average': round(avg_score, 2),
            'max': round(max_score, 2),
        }
    }


@app.get('/random')
async def get_random(count: int = Query(default=10, ge=1, le=50)):
    """Get random wallpapers"""
    import random

    wallpapers = load_wallpapers()
    if not wallpapers:
        return {'total': 0, 'images': []}

    # Random sample
    sample = random.sample(wallpapers, min(count, len(wallpapers)))

    return {
        'total': len(sample),
        'images': sample
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
