from __future__ import annotations

import calendar
import html
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import requests
import trafilatura

from .config import Settings
from .models import Article

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "ref",
    "ref_src",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def strip_html(raw_text: str) -> str:
    text = TAG_RE.sub(" ", raw_text or "")
    text = html.unescape(text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    normalized_path = parsed.path.rstrip("/") or "/"
    normalized_query = urlencode(query_items, doseq=True)
    return urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower(),
            normalized_path,
            "",
            normalized_query,
            "",
        )
    )


def parse_published_at(entry: feedparser.FeedParserDict) -> str:
    for attr_name in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed_time = getattr(entry, attr_name, None)
        if parsed_time:
            timestamp = calendar.timegm(parsed_time)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    return ""


def fetch_new_articles(
    sources: Iterable[dict[str, str]],
    settings: Settings,
    seen_urls: set[str],
) -> list[Article]:
    articles: list[Article] = []
    queued_urls: set[str] = set()

    for source in sources:
        if len(articles) >= settings.max_articles_per_run:
            break

        try:
            entries = _download_feed_entries(source["url"], settings)
        except requests.RequestException as exc:
            print(f"Failed to load feed: {source['name']} | {exc}")
            continue

        accepted_from_feed = 0

        for entry in entries:
            if len(articles) >= settings.max_articles_per_run:
                break
            if accepted_from_feed >= settings.max_articles_per_feed:
                break

            link = strip_html(getattr(entry, "link", "")).strip()
            if not link:
                continue

            canonical_link = normalize_url(link)
            if canonical_link in seen_urls or canonical_link in queued_urls:
                continue

            title = strip_html(getattr(entry, "title", "Untitled"))
            summary_hint = strip_html(
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            )
            extracted_text = ""
            if settings.enable_content_fetch:
                extracted_text = _extract_article_text(link, settings)

            content = extracted_text or summary_hint or title
            article = Article(
                source=source["name"],
                title=title,
                link=link,
                canonical_link=canonical_link,
                published_at=parse_published_at(entry),
                summary_hint=summary_hint,
                content=content,
            )
            articles.append(article)
            queued_urls.add(canonical_link)
            accepted_from_feed += 1

    return articles


def _download_feed_entries(
    feed_url: str,
    settings: Settings,
) -> list[feedparser.FeedParserDict]:
    response = requests.get(
        feed_url,
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    parsed_feed = feedparser.parse(response.content)
    return list(parsed_feed.entries)


def _extract_article_text(link: str, settings: Settings) -> str:
    try:
        response = requests.get(
            link,
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if not extracted:
            return ""
        return SPACE_RE.sub(" ", extracted).strip()
    except Exception:
        return ""
