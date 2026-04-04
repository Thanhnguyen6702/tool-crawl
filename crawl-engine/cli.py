#!/usr/bin/env python3
"""
Crawl Engine CLI
Usage:
    python cli.py run <project>              # Run a crawl project
    python cli.py run <project> --skip-download  # Crawl only, no download
    python cli.py run <project> --limit 50   # Limit output items
    python cli.py status <project>           # Show project stats
    python cli.py history <project>          # Show crawl history
    python cli.py list                       # List available projects
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECTS_DIR = Path(__file__).parent / "projects"


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def find_project(name: str) -> Path:
    """Find project YAML file by name."""
    # Try exact path first
    p = Path(name)
    if p.exists():
        return p

    # Try in projects directory
    for ext in ("", ".yaml", ".yml"):
        candidate = PROJECTS_DIR / f"{name}{ext}"
        if candidate.exists():
            return candidate

    print(f"Error: Project '{name}' not found")
    print(f"Available projects:")
    for f in PROJECTS_DIR.glob("*.yaml"):
        print(f"  - {f.stem}")
    sys.exit(1)


async def cmd_run(args):
    from core.engine import CrawlEngine

    project_path = find_project(args.project)
    print(f"Loading project: {project_path}")

    async with CrawlEngine(project_path) as engine:
        summary = await engine.run(
            skip_download=args.skip_download,
            max_per_keyword=args.max_per_keyword,
            limit_output=args.limit,
        )

    print(f"\n📊 Summary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


async def cmd_status(args):
    from core.db import CrawlDB

    async with CrawlDB() as db:
        stats = await db.get_stats(args.project)
        print(f"\n📊 Project: {stats['project']}")
        print(f"  Total items:  {stats['total_items']}")
        print(f"  New:          {stats['new']}")
        print(f"  Processed:    {stats['processed']}")
        print(f"  Downloaded:   {stats['downloaded']}")
        print(f"  Duplicate:    {stats['duplicate']}")
        print(f"  Total runs:   {stats['total_runs']}")


async def cmd_history(args):
    from core.db import CrawlDB
    from datetime import datetime

    async with CrawlDB() as db:
        runs = await db.get_runs(args.project, limit=args.limit)
        if not runs:
            print(f"No crawl history for '{args.project}'")
            return

        print(f"\n📜 Crawl History: {args.project}")
        print(f"{'ID':>4} {'Source':<12} {'Status':<8} {'Found':>6} {'New':>5} {'Dup':>5} {'Date'}")
        print("-" * 70)

        for run in runs:
            dt = datetime.fromtimestamp(run["started_at"]).strftime("%Y-%m-%d %H:%M")
            print(
                f"{run['id']:>4} {run['source']:<12} {run['status']:<8} "
                f"{run['items_found']:>6} {run['items_new']:>5} {run['items_dup']:>5} {dt}"
            )


async def cmd_validate(args):
    from core.db import CrawlDB
    from core.validator import validate_images

    async with CrawlDB() as db:
        result = await validate_images(db, args.project)
        print(f"\n🔍 Validation Result:")
        print(f"  Checked:  {result['total_checked']}")
        print(f"  Valid:    {result['valid']}")
        print(f"  Broken:   {result['broken']}")
        print(f"  Deleted:  {result['deleted']}")


def cmd_list(args):
    print("\n📂 Available Projects:")
    for f in sorted(PROJECTS_DIR.glob("*.yaml")):
        print(f"  - {f.stem}")
    if not list(PROJECTS_DIR.glob("*.yaml")):
        print("  (none found)")


def main():
    parser = argparse.ArgumentParser(description="Crawl Engine CLI")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Run a crawl project")
    p_run.add_argument("project", help="Project name or YAML path")
    p_run.add_argument("--skip-download", action="store_true", help="Skip downloading files")
    p_run.add_argument("--max-per-keyword", type=int, help="Override max items per keyword")
    p_run.add_argument("--limit", type=int, help="Limit output items")

    # status
    p_status = sub.add_parser("status", help="Show project stats")
    p_status.add_argument("project", help="Project name")

    # history
    p_hist = sub.add_parser("history", help="Show crawl history")
    p_hist.add_argument("project", help="Project name")
    p_hist.add_argument("--limit", type=int, default=20)

    # validate
    p_val = sub.add_parser("validate", help="Check & remove broken images")
    p_val.add_argument("project", help="Project name")

    # list
    sub.add_parser("list", help="List available projects")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "history":
        asyncio.run(cmd_history(args))
    elif args.command == "validate":
        asyncio.run(cmd_validate(args))
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
