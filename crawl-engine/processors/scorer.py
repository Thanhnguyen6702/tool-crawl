"""
Scorer Processor — Configurable scoring system.
Reads weights and keyword patterns from project config.
"""

import json
import logging
import re

from processors.base import Processor

log = logging.getLogger(__name__)


class ScorerProcessor(Processor):
    """Score items based on configurable criteria."""

    @property
    def name(self) -> str:
        return "scorer"

    async def process(self, items: list[dict]) -> list[dict]:
        weights = self.config.get("weights", {})
        w_quality = weights.get("quality", 1.0)
        w_popularity = weights.get("popularity", 1.0)
        w_keyword = weights.get("keyword", 1.0)

        keyword_patterns = self.config.get("keyword_patterns", [])
        compiled = [(re.compile(p["pattern"], re.IGNORECASE), p.get("score", 5.0))
                     for p in keyword_patterns if "pattern" in p]

        for item in items:
            meta = item.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            # Quality score (resolution-based)
            w = item.get("width", 0)
            h = item.get("height", 0)
            min_dim = min(w, h)
            if min_dim >= 2160:
                q_score = 5.0
            elif min_dim >= 1440:
                q_score = 3.0
            elif min_dim >= 1080:
                q_score = 2.0
            elif min_dim >= 720:
                q_score = 0.5
            else:
                q_score = 0.0

            # Popularity score
            likes = meta.get("likes", 0) or 0
            favorites = meta.get("favorites", 0) or 0
            views = meta.get("views", 0) or 0
            repins = meta.get("repins", 0) or 0

            pop_score = (likes * 2 + favorites * 3 + repins * 3 + views * 0.01)
            # Normalize: cap at 100 for very popular items
            pop_score = min(pop_score, 100.0)

            # Keyword match score
            text = " ".join([
                meta.get("description", ""),
                meta.get("title", ""),
                " ".join(meta.get("tags", [])),
            ])
            kw_score = 0.0
            for pattern, bonus in compiled:
                if pattern.search(text):
                    kw_score += bonus

            # Total
            total = (q_score * w_quality) + (pop_score * w_popularity) + (kw_score * w_keyword)
            item["score"] = round(total, 2)

        # Sort descending
        items.sort(key=lambda x: x.get("score", 0), reverse=True)
        log.info(f"Scored {len(items)} items, top score: {items[0]['score'] if items else 0}")
        return items
