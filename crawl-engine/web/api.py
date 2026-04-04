"""
Crawl Engine Web API — FastAPI backend for preview & management.
"""

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

# Paths
ENGINE_DIR = Path(__file__).parent.parent
DB_PATH = ENGINE_DIR / "data" / "crawl.db"
PROJECTS_DIR = ENGINE_DIR / "projects"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Crawl Engine", version="1.0")

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve local wallpaper images
WALLPAPER_DIR = Path("/home/thanh/wallpaper")
if WALLPAPER_DIR.exists():
    app.mount("/wallpaper/images", StaticFiles(directory=str(WALLPAPER_DIR)), name="wallpaper")


# ── Helpers ──────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def row_to_dict(row) -> dict:
    d = dict(row)
    if "metadata" in d and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass
    return d


# ── API Endpoints ────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/projects")
async def list_projects():
    """List all available projects."""
    projects = []
    for f in sorted(PROJECTS_DIR.glob("*.yaml")):
        projects.append({"name": f.stem, "path": str(f)})
    return {"projects": projects}


@app.get("/api/stats/{project}")
async def project_stats(project: str):
    """Get project statistics."""
    db = get_db()
    try:
        total = db.execute(
            "SELECT COUNT(*) FROM items WHERE project=?", (project,)
        ).fetchone()[0]

        by_status = {}
        for row in db.execute(
            "SELECT status, COUNT(*) as cnt FROM items WHERE project=? GROUP BY status",
            (project,),
        ):
            by_status[row["status"]] = row["cnt"]

        by_source = {}
        for row in db.execute(
            "SELECT source, COUNT(*) as cnt FROM items WHERE project=? GROUP BY source",
            (project,),
        ):
            by_source[row["source"]] = row["cnt"]

        return {
            "project": project,
            "total": total,
            "by_status": by_status,
            "by_source": by_source,
        }
    finally:
        db.close()


@app.get("/api/items/{project}")
async def list_items(
    project: str,
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "score",
    order: str = "desc",
    page: int = 1,
    per_page: int = 40,
):
    """List crawled items with filters, pagination, and search."""
    db = get_db()
    try:
        where = ["project=?"]
        params: list = [project]

        if source:
            where.append("source=?")
            params.append(source)
        if status:
            where.append("status=?")
            params.append(status)
        if search:
            where.append("(metadata LIKE ? OR url LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where)

        # Validate sort column
        valid_sorts = {"score", "created_at", "width", "height", "id"}
        if sort not in valid_sorts:
            sort = "score"
        order_sql = "DESC" if order == "desc" else "ASC"

        # Count
        total = db.execute(
            f"SELECT COUNT(*) FROM items WHERE {where_sql}", params
        ).fetchone()[0]

        # Fetch page
        offset = (page - 1) * per_page
        rows = db.execute(
            f"SELECT * FROM items WHERE {where_sql} ORDER BY {sort} {order_sql} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        items = [row_to_dict(r) for r in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }
    finally:
        db.close()


@app.get("/api/sources/{project}")
async def list_sources(project: str):
    """List unique sources for a project."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT DISTINCT source FROM items WHERE project=?", (project,)
        ).fetchall()
        return {"sources": [r["source"] for r in rows]}
    finally:
        db.close()


@app.get("/api/history/{project}")
async def crawl_history(project: str, limit: int = 20):
    """Get crawl run history."""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM crawl_runs WHERE project=? ORDER BY started_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return {"runs": [dict(r) for r in rows]}
    finally:
        db.close()


# ── Crawl Trigger ────────────────────────────────────────────

class CrawlRequest(BaseModel):
    project: str
    max_per_keyword: int = 50
    skip_download: bool = False
    limit: int | None = None


_running_crawls: dict[str, bool] = {}


async def _run_crawl(req: CrawlRequest):
    """Background crawl task."""
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from core.engine import CrawlEngine

    project_path = PROJECTS_DIR / f"{req.project}.yaml"
    if not project_path.exists():
        log.error(f"Project not found: {req.project}")
        return

    _running_crawls[req.project] = True
    try:
        async with CrawlEngine(project_path, DB_PATH) as engine:
            await engine.run(
                skip_download=req.skip_download,
                max_per_keyword=req.max_per_keyword,
                limit_output=req.limit,
            )
    except Exception as e:
        log.error(f"Crawl failed: {e}")
    finally:
        _running_crawls.pop(req.project, None)


@app.post("/api/crawl")
async def trigger_crawl(req: CrawlRequest, bg: BackgroundTasks):
    """Trigger a crawl job in the background."""
    if req.project in _running_crawls:
        raise HTTPException(409, f"Crawl already running for {req.project}")

    project_path = PROJECTS_DIR / f"{req.project}.yaml"
    if not project_path.exists():
        # Also try the project name as-is (for names with hyphens in YAML)
        found = False
        for f in PROJECTS_DIR.glob("*.yaml"):
            import yaml
            with open(f) as fh:
                cfg = yaml.safe_load(fh)
            if cfg.get("name") == req.project:
                req.project = f.stem
                found = True
                break
        if not found:
            raise HTTPException(404, f"Project not found: {req.project}")

    bg.add_task(_run_crawl, req)
    return {"status": "started", "project": req.project}


@app.get("/api/crawl/status")
async def crawl_status():
    """Check running crawl jobs."""
    return {"running": list(_running_crawls.keys())}


# ── Validate (check & remove broken images) ─────────────────

_running_validates: dict[str, bool] = {}


async def _run_validate(project: str):
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from core.db import CrawlDB
    from core.validator import validate_images

    _running_validates[project] = True
    try:
        async with CrawlDB(DB_PATH) as db:
            result = await validate_images(db, project)
            log.info(f"Validate result: {result}")
    except Exception as e:
        log.error(f"Validate failed: {e}")
    finally:
        _running_validates.pop(project, None)


@app.post("/api/validate/{project}")
async def trigger_validate(project: str, bg: BackgroundTasks):
    """Validate all images: check URLs, remove broken ones."""
    if project in _running_validates:
        raise HTTPException(409, f"Validation already running for {project}")
    bg.add_task(_run_validate, project)
    return {"status": "started", "project": project}


@app.get("/api/validate/status")
async def validate_status():
    return {"running": list(_running_validates.keys())}


# ── Run Server ───────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8686)
