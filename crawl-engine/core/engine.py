"""
Crawl Engine — Main pipeline orchestrator.
Loads project config, runs sources, dedup, processors, storage.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import aiohttp
import yaml

from core.db import CrawlDB
from core.dedup import Deduplicator, url_hash, download_image
from core.storage import create_storage
from sources.base import CrawlSource
from processors.base import Processor

log = logging.getLogger(__name__)

# ── Source & Processor Registry ──────────────────────────────

SOURCE_REGISTRY: dict[str, type[CrawlSource]] = {}
PROCESSOR_REGISTRY: dict[str, type[Processor]] = {}


def register_source(cls: type[CrawlSource]):
    SOURCE_REGISTRY[cls.__name__.lower().replace("source", "")] = cls
    return cls


def register_processor(cls: type[Processor]):
    PROCESSOR_REGISTRY[cls.__name__.lower().replace("processor", "")] = cls
    return cls


def _load_plugins():
    """Auto-register built-in sources and processors."""
    from sources.wallhaven import WallhavenSource
    from sources.pinterest import PinterestSource
    from processors.image_filter import ImageFilterProcessor
    from processors.scorer import ScorerProcessor

    SOURCE_REGISTRY["wallhaven"] = WallhavenSource
    SOURCE_REGISTRY["pinterest"] = PinterestSource
    PROCESSOR_REGISTRY["image_filter"] = ImageFilterProcessor
    PROCESSOR_REGISTRY["scorer"] = ScorerProcessor


# ── Project Config ───────────────────────────────────────────

class ProjectConfig:
    """Parsed project YAML configuration."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with open(self.path, "r") as f:
            self._raw = yaml.safe_load(f)

        self.name: str = self._raw["name"]
        self.sources: list[dict] = self._raw.get("sources", [])
        self.processors: list[dict] = self._raw.get("processors", [])
        self.dedup: dict = self._raw.get("dedup", {})
        self.storage: list[dict] = self._raw.get("storage", [])
        self.output: dict = self._raw.get("output", {})
        self.schedule: str | None = self._raw.get("schedule")

    def __repr__(self):
        return f"<ProjectConfig {self.name}>"


# ── Engine ───────────────────────────────────────────────────

class CrawlEngine:
    """Main crawl engine. Orchestrates the full pipeline."""

    def __init__(self, project_path: str | Path, db_path: str | Path | None = None):
        _load_plugins()
        self.project = ProjectConfig(project_path)
        self.db = CrawlDB(db_path or Path(__file__).parent.parent / "data" / "crawl.db")
        self.dedup: Optional[Deduplicator] = None

    async def __aenter__(self):
        await self.db.connect()
        self.dedup = Deduplicator(
            db=self.db,
            project=self.project.name,
            threshold=self.project.dedup.get("threshold", 0.90),
        )
        await self.dedup.load_hash_cache()
        return self

    async def __aexit__(self, *args):
        await self.db.close()

    async def run(
        self,
        skip_download: bool = False,
        max_per_keyword: int | None = None,
        limit_output: int | None = None,
    ) -> dict:
        """
        Run the full crawl pipeline:
        1. Crawl all sources
        2. Dedup (URL + source_id, optionally perceptual)
        3. Run processors (filter, score, etc.)
        4. Download & store
        5. Return summary
        """
        start = time.time()
        project = self.project
        summary = {
            "project": project.name,
            "sources": {},
            "total_found": 0,
            "total_new": 0,
            "total_dup": 0,
            "processed": 0,
            "downloaded": 0,
            "duration": 0,
        }

        log.info(f"{'='*60}")
        log.info(f"Crawl Engine — Project: {project.name}")
        log.info(f"{'='*60}")

        # ── Step 1: Crawl Sources ────────────────────────────
        for src_cfg in project.sources:
            src_type = src_cfg["type"]
            keywords = src_cfg.get("keywords", [])
            mpk = max_per_keyword or src_cfg.get("max_per_keyword", 50)
            src_config = src_cfg.get("config", {})

            source_cls = SOURCE_REGISTRY.get(src_type)
            if not source_cls:
                log.error(f"Unknown source: {src_type}")
                continue

            run_id = await self.db.start_run(project.name, src_type)
            found = new = dup = 0

            try:
                async with source_cls(src_config) as source:
                    log.info(f"\n[Source: {src_type}] Crawling {len(keywords)} keywords...")

                    async for item in source.crawl(keywords, mpk):
                        found += 1

                        # Quick dedup: URL + source_id
                        is_new, item_id = await self.dedup.check_and_register(
                            url=item.url,
                            source=src_type,
                            source_id=item.source_id,
                            width=item.width,
                            height=item.height,
                            metadata={
                                "title": item.title,
                                "description": item.description,
                                "tags": item.tags,
                                "views": item.views,
                                "likes": item.likes,
                                "favorites": item.favorites,
                                "repins": item.repins,
                                "comments": item.comments,
                                **item.metadata,
                            },
                        )

                        if is_new:
                            new += 1
                        else:
                            dup += 1

                await self.db.finish_run(run_id, found, new, dup)
            except Exception as e:
                log.error(f"Source {src_type} failed: {e}")
                await self.db.finish_run(run_id, found, new, dup, status="error", error=str(e))

            summary["sources"][src_type] = {"found": found, "new": new, "dup": dup}
            summary["total_found"] += found
            summary["total_new"] += new
            summary["total_dup"] += dup

            log.info(f"[{src_type}] Found: {found}, New: {new}, Dup: {dup}")

        # ── Step 2: Process ──────────────────────────────────
        items = await self.db.get_items(project.name, status="new", limit=10000)
        log.info(f"\n[Processing] {len(items)} new items")

        for proc_cfg in project.processors:
            proc_type = proc_cfg["type"]
            proc_config = {k: v for k, v in proc_cfg.items() if k != "type"}

            proc_cls = PROCESSOR_REGISTRY.get(proc_type)
            if not proc_cls:
                log.warning(f"Unknown processor: {proc_type}")
                continue

            processor = proc_cls(proc_config)
            items = await processor.process(items)

        # Update scores in DB
        for item in items:
            if item.get("id") and item.get("score"):
                await self.db.update_score(item["id"], item["score"])
                await self.db.update_status(item["id"], "processed")

        summary["processed"] = len(items)

        # ── Step 3: Download & Store ─────────────────────────
        if not skip_download and project.storage:
            limit = limit_output or project.output.get("limit", 100)
            top_items = items[:limit]

            storages = [create_storage(s) for s in project.storage]

            log.info(f"\n[Storage] Downloading top {len(top_items)} items...")
            downloaded = 0

            async with aiohttp.ClientSession() as session:
                for item in top_items:
                    url = item.get("url", "")
                    if not url:
                        continue

                    data = await download_image(session, url)
                    if not data:
                        continue

                    # Compute hashes if missing
                    if not item.get("phash") and self.dedup:
                        p, d, c = await self.dedup.compute_image_hashes(data)
                        if item.get("id"):
                            await self.db.update_hashes(item["id"], p, d, c)

                    # Generate storage key
                    ext = url.rsplit(".", 1)[-1].split("?")[0][:4]
                    if ext not in ("jpg", "jpeg", "png", "webp"):
                        ext = "jpg"
                    key = f"{item.get('source', 'unknown')}/{item.get('source_id', 'x')}.{ext}"

                    for storage in storages:
                        try:
                            await storage.save(key, data)
                        except Exception as e:
                            log.error(f"Storage save failed: {e}")

                    if item.get("id"):
                        await self.db.update_status(item["id"], "downloaded")
                    downloaded += 1

                    # Rate limit downloads
                    await asyncio.sleep(0.5)

            summary["downloaded"] = downloaded

        summary["duration"] = round(time.time() - start, 1)

        # ── Summary ──────────────────────────────────────────
        log.info(f"\n{'='*60}")
        log.info(f"Pipeline Complete — {summary['duration']}s")
        log.info(f"{'='*60}")
        log.info(f"  Found:      {summary['total_found']}")
        log.info(f"  New:        {summary['total_new']}")
        log.info(f"  Duplicate:  {summary['total_dup']}")
        log.info(f"  Processed:  {summary['processed']}")
        log.info(f"  Downloaded: {summary['downloaded']}")

        return summary
