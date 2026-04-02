"""
Image Scoring and Filtering Module
Scores images based on quality, popularity, and character relevance
"""

import re
from dataclasses import dataclass
from typing import Optional

from config import (
    CHARACTERS, SCORE_WEIGHTS, QUALITY_SCORES, CHARACTER_SCORES,
    MIN_WIDTH, MIN_HEIGHT, PREFERRED_MIN_WIDTH, PREFERRED_MIN_HEIGHT
)


class ImageScorer:
    """Scores images based on multiple criteria"""

    def __init__(self):
        self._build_patterns()

    def _build_patterns(self):
        """Build regex patterns for character/series matching"""
        self.character_patterns = {}
        self.series_patterns = {}

        for char_id, char_data in CHARACTERS.items():
            # Character name patterns
            names = char_data['names']
            name_pattern = '|'.join(re.escape(n) for n in names)
            self.character_patterns[char_id] = re.compile(name_pattern, re.IGNORECASE)

            # Series patterns
            series = char_data['series']
            series_pattern = '|'.join(re.escape(s) for s in series)
            self.series_patterns[char_id] = re.compile(series_pattern, re.IGNORECASE)

        # General xianxia/cultivation pattern
        xianxia_keywords = [
            'xianxia', 'xiuxian', 'tu tiên', 'tu tien', 'cultivation',
            'immortal', 'cultivator', 'martial', 'wuxia', 'xuanhuan',
            '修仙', '仙侠', '玄幻', '武侠', '仙人'
        ]
        self.xianxia_pattern = re.compile(
            '|'.join(re.escape(k) for k in xianxia_keywords),
            re.IGNORECASE
        )

    def calculate_quality_score(self, width: int, height: int) -> float:
        """Calculate quality score based on resolution"""
        # Check minimum size
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            return -100  # Disqualify

        # Calculate megapixels
        megapixels = (width * height) / 1_000_000

        # Score based on resolution
        min_dim = min(width, height)

        if min_dim >= 2160:  # 4K
            return QUALITY_SCORES['4k']
        elif min_dim >= 1440:  # 2K
            return QUALITY_SCORES['2k']
        elif min_dim >= 1080:  # 1080p
            return QUALITY_SCORES['1080p']
        elif min_dim >= 720:  # 720p
            return QUALITY_SCORES['720p']
        else:
            return -1  # Below minimum

    def calculate_character_score(self, description: str) -> tuple[float, str]:
        """Calculate character relevance score"""
        if not description:
            return 0.0, ''

        score = 0.0
        detected_character = ''

        # Check for character names
        for char_id, pattern in self.character_patterns.items():
            if pattern.search(description):
                char_weight = CHARACTERS[char_id].get('weight', 1.0)
                score += CHARACTER_SCORES['name_match'] * char_weight
                detected_character = char_id
                break  # Take first match

        # Check for series names
        for char_id, pattern in self.series_patterns.items():
            if pattern.search(description):
                score += CHARACTER_SCORES['series_match']
                if not detected_character:
                    detected_character = char_id
                break

        # Check for general xianxia/cultivation keywords
        if self.xianxia_pattern.search(description):
            score += CHARACTER_SCORES['style_match']

        return score, detected_character

    def calculate_popularity_score(
        self,
        repin_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0
    ) -> float:
        """Calculate popularity score from engagement metrics"""
        return (
            repin_count * SCORE_WEIGHTS['repin'] +
            like_count * SCORE_WEIGHTS['like'] +
            comment_count * SCORE_WEIGHTS['comment']
        )

    def calculate_total_score(
        self,
        width: int,
        height: int,
        description: str = '',
        repin_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        style_score: float = 0.0,  # From CLIP
        ai_character_score: float = 0.0,  # From AI detection
    ) -> dict:
        """Calculate total score and return detailed breakdown"""
        quality = self.calculate_quality_score(width, height)
        character, detected = self.calculate_character_score(description)
        popularity = self.calculate_popularity_score(repin_count, like_count, comment_count)

        # Add AI scores if provided
        if ai_character_score > 0:
            character += CHARACTER_SCORES['ai_detect'] * ai_character_score

        total = (
            popularity +
            quality * SCORE_WEIGHTS['quality'] +
            character * SCORE_WEIGHTS['character'] +
            style_score * 10  # Scale CLIP score
        )

        return {
            'quality_score': quality,
            'character_score': character,
            'popularity_score': popularity,
            'style_score': style_score,
            'total_score': total,
            'detected_character': detected,
        }


class ImageFilter:
    """Filters images based on quality and relevance"""

    def __init__(self):
        self.scorer = ImageScorer()

    def filter_by_resolution(self, images: list, min_width: int = MIN_WIDTH, min_height: int = MIN_HEIGHT) -> list:
        """Filter images by minimum resolution"""
        return [
            img for img in images
            if img.get('width', 0) >= min_width and img.get('height', 0) >= min_height
        ]

    def filter_by_aspect_ratio(self, images: list, min_ratio: float = 0.5, max_ratio: float = 2.0) -> list:
        """Filter images by aspect ratio (for wallpapers)"""
        filtered = []
        for img in images:
            w, h = img.get('width', 1), img.get('height', 1)
            ratio = w / h if h > 0 else 0
            if min_ratio <= ratio <= max_ratio:
                filtered.append(img)
        return filtered

    def filter_watermark_keywords(self, images: list) -> list:
        """Filter out images likely to have watermarks"""
        watermark_keywords = [
            'watermark', 'shutterstock', 'getty', 'alamy',
            'dreamstime', 'depositphotos', 'stock photo'
        ]
        pattern = re.compile('|'.join(watermark_keywords), re.IGNORECASE)

        return [
            img for img in images
            if not pattern.search(img.get('description', '') + img.get('source', ''))
        ]

    def apply_all_filters(self, images: list) -> list:
        """Apply all filters to image list"""
        print(f'Starting with {len(images)} images')

        # Resolution filter
        images = self.filter_by_resolution(images)
        print(f'After resolution filter: {len(images)}')

        # Aspect ratio filter
        images = self.filter_by_aspect_ratio(images)
        print(f'After aspect ratio filter: {len(images)}')

        # Watermark filter
        images = self.filter_watermark_keywords(images)
        print(f'After watermark filter: {len(images)}')

        return images


def score_images(images: list) -> list:
    """Score a list of images and return sorted by score"""
    scorer = ImageScorer()

    for img in images:
        scores = scorer.calculate_total_score(
            width=img.get('width', 0),
            height=img.get('height', 0),
            description=img.get('description', ''),
            repin_count=img.get('repin_count', 0),
            like_count=img.get('like_count', 0),
            comment_count=img.get('comment_count', 0),
            style_score=img.get('style_score', 0.0),
        )

        # Update image with scores
        img.update(scores)

    # Sort by total score descending
    images.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    return images


if __name__ == '__main__':
    # Test scorer
    scorer = ImageScorer()

    test_cases = [
        {
            'width': 1920, 'height': 1080,
            'description': 'Xiao Yan from Battle Through The Heavens',
            'repin_count': 100, 'like_count': 50
        },
        {
            'width': 3840, 'height': 2160,
            'description': '王林 仙逆 xianxia art',
            'repin_count': 500, 'like_count': 200
        },
        {
            'width': 800, 'height': 600,
            'description': 'random image',
            'repin_count': 10, 'like_count': 5
        },
    ]

    for i, test in enumerate(test_cases):
        scores = scorer.calculate_total_score(**test)
        print(f'\nTest {i + 1}:')
        print(f'  Description: {test["description"][:50]}...')
        print(f'  Resolution: {test["width"]}x{test["height"]}')
        print(f'  Scores: {scores}')
