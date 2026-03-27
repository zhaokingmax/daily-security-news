from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import load_settings
from .feeds import FEEDS
from .fetcher import fetch_new_articles
from .storage import load_seen_urls, save_seen_urls
from .summarizer import summarize_article
from .writer import write_reports


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    settings = load_settings(project_root)

    seen_urls = load_seen_urls(settings.state_file)
    print(f"Loaded {len(seen_urls)} seen URLs.")

    articles = fetch_new_articles(FEEDS, settings, seen_urls)
    print(f"Found {len(articles)} new articles to process.")
    if not articles:
        return 0

    summaries = []
    successful_urls: set[str] = set()

    for article in articles:
        try:
            summary = summarize_article(article, settings)
            summaries.append(summary)
            successful_urls.add(article.canonical_link)
            print(f"Summarized: {article.title}")
        except Exception as exc:
            print(f"Failed to summarize article: {article.link} | {exc}")

    if not summaries:
        print("No article summaries were generated.")
        return 1

    run_timestamp = datetime.now(settings.timezone).isoformat(timespec="seconds")
    write_reports(
        report_date=settings.run_date,
        generated_at=run_timestamp,
        report_title=settings.report_title,
        output_dir=settings.output_dir,
        summaries=summaries,
    )
    save_seen_urls(settings.state_file, seen_urls | successful_urls)
    print(f"Wrote {len(summaries)} article summaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

