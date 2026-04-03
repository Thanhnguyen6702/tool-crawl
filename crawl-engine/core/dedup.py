"""
Deduplication Module — Multi-method dedup with cross-session persistence.
Methods: URL hash, perceptual hash (pHash + dHash), content hash.
"""

import hashlib
import io
import logging
from typing import Optional

import aiohttp
import imagehash
from PIL import Image

from core.db import CrawlDB

log = logging.getLogger(__name__)


def url_hash(url: str) -> str:
    """SHA-256 hash of URL for exact-match dedup."""
    return hashlib.sha256(url.encode()).hexdigest()


def content_hash(data: bytes) -> str:
    """SHA-256 hash of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_phash(image: Image.Image, hash_size: int = 8) -> str:
    """Compute perceptual hash."""
    return str(imagehash.phash(image, hash_size=hash_size))


def compute_dhash(image: Image.Image, hash_size: int = 8) -> str:
    """Compute difference hash."""
    return str(imagehash.dhash(image, hash_size=hash_size))


def hash_distance(h1: str, h2: str) -> int:
    """Hamming distance between two hex-encoded hashes."""
    try:
        ih1 = imagehash.hex_to_hash(h1)
        ih2 = imagehash.hex_to_hash(h2)
        return ih1 - ih2
    except Exception:
        return 999


class Deduplicator:
    """Cross-session deduplication engine backed by SQLite."""

    def __init__(
        self,
        db: CrawlDB,
        project: str,
        threshold: float = 0.90,
        hash_size: int = 8,
    ):
        self.db = db
        self.project = project
        self.threshold = threshold
        self.hash_size = hash_size
        self.max_distance = int((1 - threshold) * (hash_size ** 2))
        self._hash_cache: list[dict] | None = None

    async def load_hash_cache(self):
        """Load existing hashes from DB for comparison."""
        self._hash_cache = await self.db.get_all_hashes(self.project)
        log.info(f"Loaded {len(self._hash_cache)} hashes for dedup")

    async def is_url_duplicate(self, url: str) -> bool:
        """Check if URL already exists (exact match)."""
        h = url_hash(url)
        return await self.db.url_exists(self.project, h)

    async def is_perceptual_duplicate(self, phash_str: str, dhash_str: str) -> Optional[int]:
        """
        Check if image is perceptually similar to any existing item.
        Returns the ID of the existing duplicate, or None.
        """
        if self._hash_cache is None:
            await self.load_hash_cache()

        for existing in self._hash_cache:
            ep = existing.get("phash")
            ed = existing.get("dhash")
            if not ep or not ed:
                continue

            p_dist = hash_distance(phash_str, ep)
            d_dist = hash_distance(dhash_str, ed)

            if p_dist <= self.max_distance and d_dist <= self.max_distance:
                return existing["id"]

        return None

    async def compute_image_hashes(
        self, image_data: bytes
    ) -> tuple[str | None, str | None, str]:
        """Compute pHash, dHash, and content hash from raw image bytes."""
        c_hash = content_hash(image_data)
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            p = compute_phash(img, self.hash_size)
            d = compute_dhash(img, self.hash_size)
            return p, d, c_hash
        except Exception as e:
            log.warning(f"Failed to compute image hashes: {e}")
            return None, None, c_hash

    async def check_and_register(
        self,
        url: str,
        source: str,
        source_id: str,
        image_data: bytes | None = None,
        width: int = 0,
        height: int = 0,
        metadata: dict | None = None,
        score: float = 0.0,
    ) -> tuple[bool, int]:
        """
        Check if item is duplicate. If not, register it in DB.
        Returns (is_new, item_id).
        """
        u_hash = url_hash(url)

        # 1. URL dedup
        if await self.db.url_exists(self.project, u_hash):
            return False, 0

        # 2. Source ID dedup
        if await self.db.source_id_exists(self.project, source, source_id):
            return False, 0

        # 3. Perceptual hash dedup (if image data provided)
        phash_str = dhash_str = c_hash = None
        if image_data:
            phash_str, dhash_str, c_hash = await self.compute_image_hashes(image_data)
            if phash_str and dhash_str:
                dup_id = await self.is_perceptual_duplicate(phash_str, dhash_str)
                if dup_id:
                    log.debug(f"Perceptual duplicate of item {dup_id}: {url[:60]}")
                    return False, dup_id

        # Not a duplicate — register
        item_id = await self.db.insert_item(
            project=self.project,
            source=source,
            source_id=source_id,
            url=url,
            url_hash=u_hash,
            width=width,
            height=height,
            metadata=metadata,
            phash=phash_str,
            dhash=dhash_str,
            content_hash=c_hash,
            score=score,
        )

        # Update cache
        if phash_str and self._hash_cache is not None:
            self._hash_cache.append({
                "id": item_id,
                "phash": phash_str,
                "dhash": dhash_str,
                "score": score,
            })

        return True, item_id


async def download_image(
    session: aiohttp.ClientSession, url: str, timeout: int = 30
) -> bytes | None:
    """Download image data from URL."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        log.warning(f"Download failed: {url[:60]} — {e}")
    return None
