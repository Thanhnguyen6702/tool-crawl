"""
Image Validator — Check image URLs/paths, remove broken/error ones.
Handles both remote URLs and local file paths.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

import aiohttp
import aiosqlite

from core.db import CrawlDB

log = logging.getLogger(__name__)

WALLPAPER_DIR = Path("/home/thanh/wallpaper")


def _check_local_file(url: str, metadata: dict) -> bool:
    """Check if a local file exists and is readable."""
    # Try local_path from metadata first
    local_path = None
    if isinstance(metadata, dict):
        local_path = metadata.get("local_path")

    if local_path and Path(local_path).exists():
        return Path(local_path).stat().st_size > 0

    # Try to resolve from URL pattern /wallpaper/images/category/file
    if url.startswith("/wallpaper/images/"):
        rel = url.replace("/wallpaper/images/", "")
        full = WALLPAPER_DIR / rel
        if full.exists():
            return full.stat().st_size > 0

    return False


async def validate_images(
    db: CrawlDB,
    project: str,
    batch_size: int = 20,
    timeout: int = 15,
) -> dict:
    """
    Check all image URLs in a project.
    - Local files: check existence
    - Remote URLs: HEAD request
    Delete broken ones from DB.
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

    # Separate local and remote items
    local_items = []
    remote_items = []

    for item in items:
        url = item.get("url", "")
        if url.startswith("/") or url.startswith("file://"):
            local_items.append(item)
        else:
            remote_items.append(item)

    # Validate local files
    for item in local_items:
        url = item.get("url", "")
        meta = item.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        if _check_local_file(url, meta):
            valid += 1
        else:
            broken += 1
            deleted_ids.append(item.get("id"))
            log.debug(f"Broken local: {url}")

    log.info(f"Local files: {len(local_items)} checked, {len(local_items) - len([i for i in deleted_ids])} valid")

    # Validate remote URLs
    if remote_items:
        async with aiohttp.ClientSession(headers=headers) as session:
            for i in range(0, len(remote_items), batch_size):
                batch = remote_items[i:i + batch_size]

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
                                ct = resp.headers.get("Content-Type", "")
                                if "image" in ct or "video" in ct or "octet-stream" in ct:
                                    return item_id, True
                                log.debug(f"Not media ({ct}): {url[:60]}")
                                return item_id, False
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

                await asyncio.sleep(0.5)

    # Delete broken images from DB
    if deleted_ids:
        actual_ids = [i for i in deleted_ids if i is not None]
        log.info(f"Deleting {len(actual_ids)} broken images...")
        for item_id in actual_ids:
            await db._db.execute("DELETE FROM items WHERE id=?", (item_id,))
        await db._db.commit()
        log.info(f"Deleted {len(actual_ids)} broken images")

    summary = {
        "total_checked": total,
        "valid": valid,
        "broken": broken,
        "deleted": len([i for i in deleted_ids if i is not None]),
    }

    log.info(f"Validation complete: {summary}")
    return summary
