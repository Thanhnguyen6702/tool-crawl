"""
Image Validator — Check image URLs, remove broken/error ones.
"""

import asyncio
import logging
import time

import aiohttp
import aiosqlite

from core.db import CrawlDB

log = logging.getLogger(__name__)


async def validate_images(
    db: CrawlDB,
    project: str,
    batch_size: int = 20,
    timeout: int = 15,
) -> dict:
    """
    Check all image URLs in a project. Mark broken ones as 'error' and delete them.
    Returns summary of results.
    """
    items = await db.get_items(project, limit=100000)
    total = len(items)
    valid = 0
    broken = 0
    deleted_ids = []

    log.info(f"Validating {total} images for project '{project}'...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            tasks = []

            async def check_url(item):
                url = item.get("url", "")
                item_id = item.get("id")
                if not url or not item_id:
                    return item_id, False

                try:
                    async with session.head(
                        url,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        allow_redirects=True,
                    ) as resp:
                        if resp.status == 200:
                            # Check content-type is image
                            ct = resp.headers.get("Content-Type", "")
                            if "image" in ct or "octet-stream" in ct:
                                return item_id, True
                            else:
                                log.debug(f"Not image ({ct}): {url[:60]}")
                                return item_id, False
                        else:
                            log.debug(f"HTTP {resp.status}: {url[:60]}")
                            return item_id, False
                except Exception as e:
                    log.debug(f"Error checking {url[:60]}: {e}")
                    return item_id, False

            results = await asyncio.gather(*[check_url(item) for item in batch])

            for item_id, is_valid in results:
                if is_valid:
                    valid += 1
                else:
                    broken += 1
                    deleted_ids.append(item_id)

            # Rate limit
            await asyncio.sleep(0.5)

            checked = min(i + batch_size, total)
            if checked % 50 == 0 or checked == total:
                log.info(f"  Checked {checked}/{total} — Valid: {valid}, Broken: {broken}")

    # Delete broken images from DB
    if deleted_ids:
        log.info(f"Deleting {len(deleted_ids)} broken images...")
        for item_id in deleted_ids:
            await db._db.execute("DELETE FROM items WHERE id=?", (item_id,))
        await db._db.commit()
        log.info(f"Deleted {len(deleted_ids)} broken images")

    summary = {
        "total_checked": total,
        "valid": valid,
        "broken": broken,
        "deleted": len(deleted_ids),
    }

    log.info(f"Validation complete: {summary}")
    return summary
