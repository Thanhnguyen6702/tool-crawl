#!/usr/bin/env python3
"""
Import existing local wallpaper collection into the crawl engine DB.
Reads metadata.json + per-image JSON files from /home/thanh/wallpaper/
"""

import asyncio
import json
import hashlib
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import CrawlDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

WALLPAPER_DIR = Path("/home/thanh/wallpaper")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}


async def import_from_metadata_json(db: CrawlDB, project: str):
    """Import from the main metadata.json file."""
    meta_file = WALLPAPER_DIR / "metadata.json"
    if not meta_file.exists():
        log.warning("metadata.json not found")
        return 0

    with open(meta_file) as f:
        items = json.load(f)

    log.info(f"Found {len(items)} items in metadata.json")
    imported = 0
    skipped = 0

    for item in items:
        local_path = item.get("local_path", "")
        category = item.get("category", "general")
        filename = item.get("filename", "")
        media_type = item.get("media_type", "image")
        title = item.get("title", "")
        description = item.get("description", "")

        if not local_path or not Path(local_path).exists():
            skipped += 1
            continue

        # Use local path as URL for preview (we'll serve it)
        url = f"/wallpaper/images/{category}/{filename}"
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        source_id = Path(filename).stem

        # Get image dimensions
        width = height = 0
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_EXTS:
            try:
                from PIL import Image
                img = Image.open(local_path)
                width, height = img.size
                img.close()
            except Exception:
                pass

        metadata = {
            "title": title,
            "description": description,
            "category": category,
            "media_type": media_type,
            "local_path": local_path,
            "size": item.get("size", 0),
        }

        await db.insert_item(
            project=project,
            source=f"local-{category}",
            source_id=source_id,
            url=url,
            url_hash=url_hash,
            width=width,
            height=height,
            metadata=metadata,
            status="downloaded",
        )
        imported += 1

    log.info(f"Imported {imported}, skipped {skipped}")
    return imported


async def import_from_directories(db: CrawlDB, project: str):
    """Scan category directories for any files not in metadata.json."""
    imported = 0

    for category_dir in sorted(WALLPAPER_DIR.iterdir()):
        if not category_dir.is_dir():
            continue

        category = category_dir.name
        files = [f for f in category_dir.iterdir()
                 if f.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS]

        for filepath in files:
            source_id = filepath.stem
            filename = filepath.name
            ext = filepath.suffix.lower()
            media_type = "video" if ext in VIDEO_EXTS else "image"

            url = f"/wallpaper/images/{category}/{filename}"
            url_hash = hashlib.sha256(url.encode()).hexdigest()

            # Skip if already exists
            if await db.url_exists(project, url_hash):
                continue

            width = height = 0
            if media_type == "image":
                try:
                    from PIL import Image
                    img = Image.open(filepath)
                    width, height = img.size
                    img.close()
                except Exception:
                    pass

            # Try to load per-image JSON
            json_path = filepath.with_suffix(filepath.suffix + ".json")
            title = description = ""
            if json_path.exists():
                try:
                    with open(json_path) as f:
                        jdata = json.load(f)
                    title = jdata.get("title", "") or jdata.get("description", "")[:100]
                    description = jdata.get("description", "")
                except Exception:
                    pass

            metadata = {
                "title": title,
                "description": description,
                "category": category,
                "media_type": media_type,
                "local_path": str(filepath),
                "size": filepath.stat().st_size,
            }

            await db.insert_item(
                project=project,
                source=f"local-{category}",
                source_id=source_id,
                url=url,
                url_hash=url_hash,
                width=width,
                height=height,
                metadata=metadata,
                status="downloaded",
            )
            imported += 1

        if imported > 0:
            log.info(f"  {category}: scanned")

    log.info(f"Directory scan imported {imported} additional files")
    return imported


async def main():
    project = "xianxia-wallpaper"

    async with CrawlDB() as db:
        log.info("=== Importing from metadata.json ===")
        n1 = await import_from_metadata_json(db, project)

        log.info("\n=== Scanning directories for additional files ===")
        n2 = await import_from_directories(db, project)

        log.info(f"\n=== Done: {n1 + n2} total imported ===")

        stats = await db.get_stats(project)
        log.info(f"Project stats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
