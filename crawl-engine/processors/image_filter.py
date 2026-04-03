"""
Image Filter Processor — Filter by resolution, aspect ratio, watermarks.
"""

import json
import logging
import re

from processors.base import Processor

log = logging.getLogger(__name__)


class ImageFilterProcessor(Processor):
    """Filter images based on quality criteria."""

    @property
    def name(self) -> str:
        return "image_filter"

    async def process(self, items: list[dict]) -> list[dict]:
        min_w = self.config.get("min_width", 720)
        min_h = self.config.get("min_height", 720)
        min_ratio = self.config.get("min_aspect_ratio", 0.3)
        max_ratio = self.config.get("max_aspect_ratio", 3.0)
        filter_watermarks = self.config.get("filter_watermarks", True)

        before = len(items)
        result = []

        watermark_re = re.compile(
            r"watermark|shutterstock|getty|alamy|dreamstime|depositphotos|stock photo",
            re.IGNORECASE,
        )

        for item in items:
            meta = item.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            w = item.get("width", 0)
            h = item.get("height", 0)

            # Resolution check
            if w < min_w or h < min_h:
                continue

            # Aspect ratio check
            if h > 0:
                ratio = w / h
                if ratio < min_ratio or ratio > max_ratio:
                    continue

            # Watermark keyword check
            if filter_watermarks:
                desc = meta.get("description", "") + " " + meta.get("source_domain", "")
                if watermark_re.search(desc):
                    continue

            result.append(item)

        log.info(f"ImageFilter: {before} → {len(result)} items")
        return result
