# 🕷️ Universal Crawl Engine

A plugin-based, extensible crawl engine with cross-session deduplication.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# List projects
python cli.py list

# Run a project
python cli.py run xianxia_wallpaper

# Crawl only (no download)
python cli.py run xianxia_wallpaper --skip-download

# Check stats
python cli.py status xianxia-wallpaper

# View history
python cli.py history xianxia-wallpaper
```

## Architecture

```
crawl-engine/
├── core/           # Engine core
│   ├── engine.py   # Pipeline orchestrator
│   ├── db.py       # SQLite persistence
│   ├── dedup.py    # Multi-method deduplication
│   └── storage.py  # Local/R2 storage backends
├── sources/        # Pluggable crawl sources
│   ├── base.py     # Abstract interface
│   ├── wallhaven.py
│   └── pinterest.py
├── processors/     # Pluggable processing steps
│   ├── base.py     # Abstract interface
│   ├── image_filter.py
│   └── scorer.py
├── projects/       # YAML project configs
│   └── xianxia_wallpaper.yaml
└── cli.py          # CLI interface
```

## Adding a New Source

1. Create `sources/my_source.py`
2. Subclass `CrawlSource`, implement `crawl()` method
3. Register in `core/engine.py`
4. Add to project YAML

```python
from sources.base import CrawlSource, CrawlItem

class MySource(CrawlSource):
    @property
    def name(self) -> str:
        return "my_source"

    async def crawl(self, keywords, max_per_keyword=50):
        for keyword in keywords:
            # Your crawl logic here
            yield CrawlItem(
                source_id="unique-id",
                url="https://...",
                width=1920,
                height=1080,
            )
```

## Adding a New Processor

```python
from processors.base import Processor

class MyProcessor(Processor):
    @property
    def name(self) -> str:
        return "my_processor"

    async def process(self, items):
        # Filter/modify/score items
        return items
```

## Project Config (YAML)

```yaml
name: my-project

sources:
  - type: wallhaven
    keywords: [keyword1, keyword2]
    max_per_keyword: 50
    config:
      delay: 2

processors:
  - type: image_filter
    min_width: 1080
  - type: scorer
    weights: { quality: 1, popularity: 0.5 }

dedup:
  threshold: 0.90

storage:
  - type: local
    path: /path/to/output

output:
  limit: 100
```

## Deduplication

Multi-method, cross-session:
- **URL hash** — exact URL match (SHA-256)
- **Source ID** — same item from same source
- **Perceptual hash** — visually similar images (pHash + dHash)
- **Content hash** — identical file bytes

All stored in SQLite, persists across runs. Never downloads the same image twice.

## Extending for Manga/Novel Crawling

The engine is content-agnostic. For manga:

1. Create `sources/nettruyen.py` implementing `CrawlSource`
2. Create `processors/text_processor.py` for chapter processing
3. Create `projects/manga_reader.yaml`

The dedup system works with any content — just provide unique source_ids.
