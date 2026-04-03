"""
Database Module — SQLite persistence for crawl history, dedup hashes, metadata.
Async via aiosqlite. Lightweight enough for 2GB RAM servers.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import aiosqlite

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "crawl.db"


class CrawlDB:
    """Async SQLite database for crawl engine persistence."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._init_tables()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _init_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT NOT NULL,
                source      TEXT NOT NULL,
                source_id   TEXT NOT NULL,
                url         TEXT NOT NULL,
                url_hash    TEXT NOT NULL,
                phash       TEXT,
                dhash       TEXT,
                content_hash TEXT,
                width       INTEGER DEFAULT 0,
                height      INTEGER DEFAULT 0,
                metadata    TEXT DEFAULT '{}',
                score       REAL DEFAULT 0.0,
                status      TEXT DEFAULT 'new',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                UNIQUE(project, source, source_id)
            );

            CREATE INDEX IF NOT EXISTS idx_items_url_hash
                ON items(url_hash);
            CREATE INDEX IF NOT EXISTS idx_items_phash
                ON items(phash) WHERE phash IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_items_dhash
                ON items(dhash) WHERE dhash IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_items_content_hash
                ON items(content_hash) WHERE content_hash IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_items_project_status
                ON items(project, status);

            CREATE TABLE IF NOT EXISTS crawl_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT NOT NULL,
                source      TEXT NOT NULL,
                started_at  REAL NOT NULL,
                finished_at REAL,
                items_found INTEGER DEFAULT 0,
                items_new   INTEGER DEFAULT 0,
                items_dup   INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'running',
                error       TEXT
            );

            CREATE TABLE IF NOT EXISTS job_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT NOT NULL,
                source      TEXT NOT NULL,
                keyword     TEXT,
                priority    INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'pending',
                created_at  REAL NOT NULL,
                started_at  REAL,
                finished_at REAL,
                error       TEXT
            );
        """)
        await self._db.commit()

    # ── Item Operations ──────────────────────────────────────

    async def url_exists(self, project: str, url_hash: str) -> bool:
        cur = await self._db.execute(
            "SELECT 1 FROM items WHERE project=? AND url_hash=?",
            (project, url_hash),
        )
        return (await cur.fetchone()) is not None

    async def source_id_exists(self, project: str, source: str, source_id: str) -> bool:
        cur = await self._db.execute(
            "SELECT 1 FROM items WHERE project=? AND source=? AND source_id=?",
            (project, source, source_id),
        )
        return (await cur.fetchone()) is not None

    async def insert_item(
        self,
        project: str,
        source: str,
        source_id: str,
        url: str,
        url_hash: str,
        width: int = 0,
        height: int = 0,
        metadata: dict | None = None,
        phash: str | None = None,
        dhash: str | None = None,
        content_hash: str | None = None,
        score: float = 0.0,
        status: str = "new",
    ) -> int:
        now = time.time()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        cur = await self._db.execute(
            """INSERT OR IGNORE INTO items
               (project, source, source_id, url, url_hash, phash, dhash,
                content_hash, width, height, metadata, score, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project, source, source_id, url, url_hash, phash, dhash,
             content_hash, width, height, meta_json, score, status, now, now),
        )
        await self._db.commit()
        return cur.lastrowid

    async def update_hashes(
        self, item_id: int, phash: str | None, dhash: str | None, content_hash: str | None
    ):
        await self._db.execute(
            "UPDATE items SET phash=?, dhash=?, content_hash=?, updated_at=? WHERE id=?",
            (phash, dhash, content_hash, time.time(), item_id),
        )
        await self._db.commit()

    async def update_score(self, item_id: int, score: float):
        await self._db.execute(
            "UPDATE items SET score=?, updated_at=? WHERE id=?",
            (score, time.time(), item_id),
        )
        await self._db.commit()

    async def update_status(self, item_id: int, status: str):
        await self._db.execute(
            "UPDATE items SET status=?, updated_at=? WHERE id=?",
            (status, time.time(), item_id),
        )
        await self._db.commit()

    async def get_items(
        self, project: str, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        q = "SELECT * FROM items WHERE project=?"
        params: list = [project]
        if status:
            q += " AND status=?"
            params.append(status)
        q += " ORDER BY score DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur = await self._db.execute(q, params)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_all_hashes(self, project: str) -> list[dict]:
        """Get all perceptual hashes for dedup comparison."""
        cur = await self._db.execute(
            "SELECT id, phash, dhash, score FROM items WHERE project=? AND phash IS NOT NULL",
            (project,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def count_items(self, project: str, status: str | None = None) -> int:
        q = "SELECT COUNT(*) FROM items WHERE project=?"
        params: list = [project]
        if status:
            q += " AND status=?"
            params.append(status)
        cur = await self._db.execute(q, params)
        row = await cur.fetchone()
        return row[0]

    # ── Crawl Run Operations ─────────────────────────────────

    async def start_run(self, project: str, source: str) -> int:
        cur = await self._db.execute(
            "INSERT INTO crawl_runs (project, source, started_at) VALUES (?,?,?)",
            (project, source, time.time()),
        )
        await self._db.commit()
        return cur.lastrowid

    async def finish_run(
        self, run_id: int, items_found: int, items_new: int, items_dup: int,
        status: str = "done", error: str | None = None,
    ):
        await self._db.execute(
            """UPDATE crawl_runs
               SET finished_at=?, items_found=?, items_new=?, items_dup=?,
                   status=?, error=?
               WHERE id=?""",
            (time.time(), items_found, items_new, items_dup, status, error, run_id),
        )
        await self._db.commit()

    async def get_runs(self, project: str, limit: int = 20) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM crawl_runs WHERE project=? ORDER BY started_at DESC LIMIT ?",
            (project, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── Stats ────────────────────────────────────────────────

    async def get_stats(self, project: str) -> dict:
        total = await self.count_items(project)
        new = await self.count_items(project, "new")
        processed = await self.count_items(project, "processed")
        downloaded = await self.count_items(project, "downloaded")
        duplicate = await self.count_items(project, "duplicate")

        cur = await self._db.execute(
            "SELECT COUNT(*) FROM crawl_runs WHERE project=?", (project,)
        )
        runs = (await cur.fetchone())[0]

        return {
            "project": project,
            "total_items": total,
            "new": new,
            "processed": processed,
            "downloaded": downloaded,
            "duplicate": duplicate,
            "total_runs": runs,
        }
