"""
Image Deduplication Module
Uses perceptual hashing to find and remove duplicate images
"""

import asyncio
import io
from typing import Optional

import aiohttp
import imagehash
from PIL import Image
from tqdm import tqdm

from config import DUPLICATE_THRESHOLD, PINTEREST_HEADERS


class ImageDeduplicator:
    """Deduplicates images using perceptual hashing"""

    def __init__(self, threshold: float = DUPLICATE_THRESHOLD):
        self.threshold = threshold
        self.hashes: dict[str, str] = {}  # image_id -> hash

    async def _download_image(self, session: aiohttp.ClientSession, url: str) -> Optional[Image.Image]:
        """Download image and return PIL Image"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.read()
                    return Image.open(io.BytesIO(data))
        except Exception as e:
            pass
        return None

    def _compute_hash(self, image: Image.Image) -> str:
        """Compute perceptual hash for an image"""
        # Use multiple hash types for better accuracy
        phash = imagehash.phash(image)
        dhash = imagehash.dhash(image)
        # Combine hashes
        return f'{phash}_{dhash}'

    def _hash_similarity(self, hash1: str, hash2: str) -> float:
        """Calculate similarity between two hashes (0-1)"""
        try:
            p1, d1 = hash1.split('_')
            p2, d2 = hash2.split('_')

            ph1 = imagehash.hex_to_hash(p1)
            ph2 = imagehash.hex_to_hash(p2)
            dh1 = imagehash.hex_to_hash(d1)
            dh2 = imagehash.hex_to_hash(d2)

            # Calculate Hamming distance (lower = more similar)
            p_dist = ph1 - ph2  # Returns Hamming distance
            d_dist = dh1 - dh2

            # Convert to similarity (0-1)
            # Max Hamming distance for 64-bit hash is 64
            p_sim = 1 - (p_dist / 64)
            d_sim = 1 - (d_dist / 64)

            # Average similarity
            return (p_sim + d_sim) / 2
        except:
            return 0.0

    async def compute_hashes(self, images: list) -> dict[str, str]:
        """Compute hashes for all images"""
        hashes = {}

        async with aiohttp.ClientSession(headers=PINTEREST_HEADERS) as session:
            tasks = []

            async def process_image(img: dict):
                img_id = img.get('id', img.get('url', ''))
                url = img.get('url', '')

                if not url:
                    return

                pil_image = await self._download_image(session, url)
                if pil_image:
                    try:
                        h = self._compute_hash(pil_image)
                        hashes[img_id] = h
                    except Exception as e:
                        pass

            # Process in batches to avoid overwhelming
            batch_size = 10
            for i in tqdm(range(0, len(images), batch_size), desc='Computing hashes'):
                batch = images[i:i + batch_size]
                tasks = [process_image(img) for img in batch]
                await asyncio.gather(*tasks)
                await asyncio.sleep(0.5)  # Rate limit

        self.hashes = hashes
        return hashes

    def find_duplicates(self, images: list) -> list[tuple[str, str, float]]:
        """Find duplicate pairs among images"""
        duplicates = []
        ids = list(self.hashes.keys())

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                id1, id2 = ids[i], ids[j]
                hash1, hash2 = self.hashes[id1], self.hashes[id2]

                similarity = self._hash_similarity(hash1, hash2)
                if similarity >= self.threshold:
                    duplicates.append((id1, id2, similarity))

        return duplicates

    def deduplicate(self, images: list) -> list:
        """Remove duplicates, keeping highest quality version"""
        if not self.hashes:
            print('No hashes computed. Run compute_hashes first.')
            return images

        # Find duplicates
        duplicates = self.find_duplicates(images)
        print(f'Found {len(duplicates)} duplicate pairs')

        # Build map of image_id -> image
        img_map = {img.get('id', img.get('url', '')): img for img in images}

        # Track which images to remove
        to_remove = set()

        for id1, id2, similarity in duplicates:
            # Skip if already marked for removal
            if id1 in to_remove or id2 in to_remove:
                continue

            img1 = img_map.get(id1, {})
            img2 = img_map.get(id2, {})

            # Keep the higher quality one (larger resolution or higher score)
            score1 = img1.get('total_score', 0) or (img1.get('width', 0) * img1.get('height', 0))
            score2 = img2.get('total_score', 0) or (img2.get('width', 0) * img2.get('height', 0))

            if score1 >= score2:
                to_remove.add(id2)
            else:
                to_remove.add(id1)

        # Filter out duplicates
        deduped = [
            img for img in images
            if img.get('id', img.get('url', '')) not in to_remove
        ]

        print(f'Removed {len(to_remove)} duplicates, {len(deduped)} images remaining')
        return deduped


async def deduplicate_images(images: list, threshold: float = DUPLICATE_THRESHOLD) -> list:
    """Convenience function to deduplicate images"""
    deduplicator = ImageDeduplicator(threshold)
    await deduplicator.compute_hashes(images)
    return deduplicator.deduplicate(images)


if __name__ == '__main__':
    # Test with sample images
    test_images = [
        {'id': '1', 'url': 'https://example.com/img1.jpg', 'width': 1920, 'height': 1080},
        {'id': '2', 'url': 'https://example.com/img2.jpg', 'width': 1920, 'height': 1080},
    ]

    async def test():
        deduplicator = ImageDeduplicator()
        # Note: Would need real URLs to test properly
        print('Deduplicator initialized')

    asyncio.run(test())
