# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily Security News — a Python script that fetches cybersecurity RSS feeds, filters articles by focus keywords, generates Chinese summaries via LLM, and outputs daily reports to `data/`.

## Commands

### Local Development

```bash
# Activate venv
.venv/Scripts/Activate.ps1  # Windows PowerShell
source .venv/bin/activate   # Linux/macOS

# Run collector
python -m src.main
```

### Environment Setup

```bash
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env  # Edit with your LLM credentials
```

## Architecture

### Data Flow

```
RSS/HTML feeds → fetcher (dedup + filter) → summarizer (LLM batch/single) → writer (JSON + Markdown)
                      ↓                              ↓
                seen_urls.json                  data/YYYY-MM/
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `config.py` | Settings from env vars, defaults for all tunables |
| `feeds.py` | RSS + HTML source definitions with link patterns |
| `fetcher.py` | RSS parsing, HTML scraping, content extraction, blacklist filtering |
| `summarizer.py` | LLM batch/single summarization, fallback logic, risk inference |
| `categorizer.py` | Category assignment based on keyword matching |
| `writer.py` | JSON + Markdown report generation with category index |
| `storage.py` | Seen URLs dedup, atomic JSON writes |
| `main.py` | Orchestration entry point |

### Key Design Patterns

- **Batch LLM first, single retry fallback**: Sends articles in batches to reduce token costs, falls back to single-article retries on failure
- **Focus keyword ranking**: Articles matching `FOCUS_KEYWORDS` are prioritized; `BLACKLIST_KEYWORDS` suppress unwanted topics
- **Two-pass title translation**: `title_zh` can be backfilled post-hoc for existing JSON items via `backfill_title_fields()`
- **Atomic writes**: JSON files use temp file + replace to prevent corruption

### Output Structure

```
data/
├── YYYY-MM/
│   ├── YYYY-MM-DD.json   # Full structured data
│   └── YYYY-MM-DD.md     # Human-readable report
├── latest.json           # Symlink to latest daily JSON
└── latest.md             # Symlink to latest daily Markdown
```

### Category System

16 categories defined in `categorizer.py` with bilingual labels. Assignment uses keyword matching across title, summary, keywords, and focus keywords. Default: `综合资讯` (General Security News).

### LLM Integration

Uses OpenAI-compatible API via `openai` package. Supports:
- Batch processing (configurable via `LLM_BATCH_SIZE`)
- Automatic retry (`LLM_RETRY_COUNT`)
- Fallback summaries when LLM unavailable (`ALLOW_FALLBACK_SUMMARY=true`)
- Chinese rewrite pass if output is mostly English

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | (required for LLM) | API key for LLM provider |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | API endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Model identifier |
| `FOCUS_KEYWORDS` | Built-in list | Comma-separated; prioritizes matching articles |
| `BLACKLIST_KEYWORDS` | `密码学,cryptography,cve,cve-` | Suppresses articles matching visible text |
| `MAX_ARTICLES_PER_RUN` | `50` | Max articles per execution |
| `MAX_ARTICLES_PER_FEED` | `8` | Max candidates per feed before ranking |
| `ENABLE_CONTENT_FETCH` | `true` | Fetch full article content vs. RSS summary only |
| `RUN_DATE` | Today | Override output date (for backfill runs) |

### Default Focus Keywords

Includes: 安全智能体，security agent, ai agent, agentic, soc, crowdstrike, microsoft, cisco, palo alto, edr, xdr, 运营商，apt, 威胁研判

## GitHub Actions

Daily at 08:15 Asia/Shanghai via `.github/workflows/daily.yml`. Artifacts (`data/`, `state/`) auto-commit back to repo.

### Required Secrets

- `LLM_API_KEY`
- `LLM_BASE_URL` (optional)
- `LLM_MODEL` (optional)

## Conventions

- Blacklist matching targets **visible text only** (title + summary_hint), not full body — prevents false positives from incidental CVE mentions
- `canonical_link` = dedup key (URL normalized, tracking params stripped)
- All timestamps in UTC; display uses `TZ_NAME` timezone
- `title_zh` may be empty initially if LLM unavailable; backfilled on subsequent runs
