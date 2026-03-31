from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from .config import load_settings
from .feeds import FEEDS
from .fetcher import fetch_new_articles
from .storage import load_seen_urls, save_seen_urls
from .summarizer import summarize_articles
from .writer import write_reports


def _configure_runtime_logging() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass


def main() -> int:
    _configure_runtime_logging()
    print("Collector started.")
    project_root = Path(__file__).resolve().parents[1]
    settings = load_settings(project_root)

    print("Loading seen URL state...")
    seen_urls = load_seen_urls(settings.state_file)
    print(f"Loaded {len(seen_urls)} seen URLs.")

    print("Collecting candidate articles...")
    articles = fetch_new_articles(FEEDS, settings, seen_urls)
    print(f"Found {len(articles)} new articles to process.")
    if not articles:
        return 0

    print("Summarizing selected articles...")
    summaries = summarize_articles(articles, settings)
    if not summaries:
        print("No article summaries were generated.")
        return 1

    successful_urls = {summary.canonical_link for summary in summaries}
    llm_count = sum(1 for summary in summaries if not summary.used_fallback)
    fallback_count = len(summaries) - llm_count
    print(f"LLM summaries: {llm_count} | Fallback summaries: {fallback_count}")

    run_timestamp = datetime.now(settings.timezone).isoformat(timespec="seconds")
    print("Writing report files...")
    write_reports(
        report_date=settings.run_date,
        generated_at=run_timestamp,
        report_title=settings.report_title,
        output_dir=settings.output_dir,
        summaries=summaries,
        settings=settings,
    )
    print("Saving updated seen URL state...")
    save_seen_urls(settings.state_file, seen_urls | successful_urls)
    print(f"Wrote {len(summaries)} article summaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
