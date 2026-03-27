from __future__ import annotations

import calendar
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
import trafilatura

from .config import Settings
from .models import Article

try:
    import brotli
except ImportError:  # pragma: no cover - dependency is installed in production
    brotli = None

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
ANCHOR_RE = re.compile(
    r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_CONTENT_TEMPLATE = (
    r"<meta[^>]+(?:property|name)=[\"']{name}[\"'][^>]+content=[\"']([^\"']+)[\"']"
)
TIME_TAG_RE = re.compile(
    r"<time[^>]+datetime=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
GENERIC_TITLES = {
    "",
    "发表评论",
    "首页",
}
SOURCE_SCAN_MULTIPLIER = 6


@dataclass(slots=True)
class ArticleCandidate:
    source: str
    link: str
    canonical_link: str
    title: str
    summary_hint: str
    published_at: str
    matched_focus_keywords: list[str]


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
    sources: Iterable[dict[str, object]],
    settings: Settings,
    seen_urls: set[str],
) -> list[Article]:
    articles: list[Article] = []
    queued_urls: set[str] = set()

    for source in sources:
        try:
            candidates = _load_source_candidates(source, settings, seen_urls, queued_urls)
        except requests.RequestException as exc:
            print(f"Failed to load source: {source['name']} | {exc}")
            continue
        except Exception as exc:
            print(f"Failed to parse source: {source['name']} | {exc}")
            continue

        accepted_from_source = 0
        scan_limit = max(settings.max_articles_per_feed * SOURCE_SCAN_MULTIPLIER, 6)

        for candidate in candidates[:scan_limit]:
            if accepted_from_source >= settings.max_articles_per_feed:
                break

            article = _materialize_article(candidate, settings)
            if article is None:
                continue

            article_blacklist_hits = _find_blacklist_hits(article.title, article.summary_hint, settings.blacklist_keywords)
            if article_blacklist_hits:
                print(
                    f"Skipped blacklisted article: {article.title} | "
                    f"matched: {', '.join(article_blacklist_hits)}"
                )
                continue

            if article.canonical_link in seen_urls or article.canonical_link in queued_urls:
                continue

            articles.append(article)
            queued_urls.add(article.canonical_link)
            accepted_from_source += 1

    ranked_articles = sorted(
        articles,
        key=lambda item: (
            len(item.matched_focus_keywords),
            item.published_at,
            item.title.lower(),
        ),
        reverse=True,
    )
    return ranked_articles[: settings.max_articles_per_run]


def _load_source_candidates(
    source: dict[str, object],
    settings: Settings,
    seen_urls: set[str],
    queued_urls: set[str],
) -> list[ArticleCandidate]:
    kind = str(source.get("kind", "rss"))
    if kind == "html":
        candidates = _download_html_candidates(source, settings)
    else:
        candidates = _download_rss_candidates(source, settings)

    filtered: list[ArticleCandidate] = []
    for candidate in candidates:
        if candidate.canonical_link in seen_urls or candidate.canonical_link in queued_urls:
            continue
        candidate_blacklist_hits = _find_blacklist_hits(
            candidate.title,
            candidate.summary_hint,
            settings.blacklist_keywords,
        )
        if candidate_blacklist_hits:
            print(
                f"Skipped blacklisted candidate: {candidate.title} | "
                f"matched: {', '.join(candidate_blacklist_hits)}"
            )
            continue
        filtered.append(candidate)

    return sorted(
        filtered,
        key=lambda item: (
            len(item.matched_focus_keywords),
            item.published_at,
            item.title.lower(),
        ),
        reverse=True,
    )


def _download_rss_candidates(
    source: dict[str, object],
    settings: Settings,
) -> list[ArticleCandidate]:
    response = requests.get(
        str(source["url"]),
        headers=_build_headers(settings),
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    parsed_feed = feedparser.parse(_response_bytes(response))

    candidates: list[ArticleCandidate] = []
    for entry in parsed_feed.entries:
        link = strip_html(getattr(entry, "link", "")).strip()
        if not link:
            continue

        title = strip_html(getattr(entry, "title", "Untitled"))
        summary_hint = strip_html(
            getattr(entry, "summary", "") or getattr(entry, "description", "")
        )
        candidate = ArticleCandidate(
            source=str(source["name"]),
            title=title,
            link=link,
            canonical_link=normalize_url(link),
            published_at=parse_published_at(entry),
            summary_hint=summary_hint,
            matched_focus_keywords=_find_matching_keywords(
                f"{title}\n{summary_hint}",
                settings.focus_keywords,
            ),
        )
        candidates.append(candidate)

    return candidates


def _download_html_candidates(
    source: dict[str, object],
    settings: Settings,
) -> list[ArticleCandidate]:
    source_url = str(source["url"])
    response = requests.get(
        source_url,
        headers=_build_headers(settings),
        timeout=settings.request_timeout_seconds,
        verify=False if "cnetsec.com" in source_url else True,
    )
    response.raise_for_status()
    page_html = _response_text(response)

    patterns = [
        re.compile(str(pattern), re.IGNORECASE)
        for pattern in source.get("link_patterns", [])
    ]

    candidates: list[ArticleCandidate] = []
    seen_links: set[str] = set()

    for href, inner_html in ANCHOR_RE.findall(page_html):
        full_link = urljoin(source_url, html.unescape(href))
        if not any(pattern.fullmatch(full_link) for pattern in patterns):
            continue

        canonical_link = normalize_url(full_link)
        if canonical_link in seen_links:
            continue

        title = strip_html(inner_html)
        if not title or len(title) < 6:
            continue

        seen_links.add(canonical_link)
        candidates.append(
            ArticleCandidate(
                source=str(source["name"]),
                title=title,
                link=full_link,
                canonical_link=canonical_link,
                published_at="",
                summary_hint="",
                matched_focus_keywords=_find_matching_keywords(title, settings.focus_keywords),
            )
        )

    return candidates


def _materialize_article(
    candidate: ArticleCandidate,
    settings: Settings,
) -> Article | None:
    title = candidate.title
    summary_hint = candidate.summary_hint
    published_at = candidate.published_at
    content = summary_hint or title

    if settings.enable_content_fetch:
        article_payload = _extract_article_payload(candidate.link, settings)
        title = _choose_title(candidate.title, article_payload["title"], candidate.source)
        summary_hint = article_payload["summary_hint"] or summary_hint
        published_at = article_payload["published_at"] or published_at
        content = article_payload["content"] or summary_hint or title

    if not title or not content:
        return None

    matched_focus_keywords = _merge_keywords(
        candidate.matched_focus_keywords,
        _find_matching_keywords(
            "\n".join([title, summary_hint, content]),
            settings.focus_keywords,
        ),
    )

    return Article(
        source=candidate.source,
        title=title,
        link=candidate.link,
        canonical_link=candidate.canonical_link,
        published_at=published_at,
        summary_hint=summary_hint,
        content=content,
        matched_focus_keywords=matched_focus_keywords,
    )


def _extract_article_payload(link: str, settings: Settings) -> dict[str, str]:
    try:
        response = requests.get(
            link,
            headers=_build_headers(settings),
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        page_html = _response_text(response)
        metadata = trafilatura.extract_metadata(page_html, default_url=link)
        extracted = trafilatura.extract(
            page_html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )

        title = (
            _extract_meta_content(page_html, "og:title")
            or _extract_meta_content(page_html, "twitter:title")
            or _extract_title_tag(page_html)
        )
        if metadata and getattr(metadata, "title", None) and not _is_generic_title(metadata.title):
            title = title or metadata.title

        summary_hint = (
            _extract_meta_content(page_html, "description")
            or _extract_meta_content(page_html, "og:description")
            or (getattr(metadata, "description", "") if metadata else "")
        )

        published_at = (
            _extract_meta_content(page_html, "article:published_time")
            or _extract_meta_content(page_html, "pubdate")
            or _extract_time_datetime(page_html)
            or (getattr(metadata, "date", "") if metadata else "")
        )

        return {
            "title": strip_html(title),
            "summary_hint": strip_html(summary_hint),
            "published_at": strip_html(published_at),
            "content": SPACE_RE.sub(" ", extracted or "").strip(),
        }
    except Exception:
        return {
            "title": "",
            "summary_hint": "",
            "published_at": "",
            "content": "",
        }


def _build_headers(settings: Settings) -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "*/*",
    }


def _response_bytes(response: requests.Response) -> bytes:
    if response.headers.get("Content-Encoding", "").lower() == "br" and brotli is not None:
        try:
            return brotli.decompress(response.content)
        except brotli.error:
            pass
    return response.content


def _response_text(response: requests.Response) -> str:
    if response.headers.get("Content-Encoding", "").lower() == "br" and brotli is not None:
        try:
            return brotli.decompress(response.content).decode(
                response.encoding or "utf-8",
                errors="ignore",
            )
        except brotli.error:
            pass
    return response.text


def _extract_meta_content(page_html: str, name: str) -> str:
    pattern = re.compile(
        META_CONTENT_TEMPLATE.format(name=re.escape(name)),
        re.IGNORECASE,
    )
    match = pattern.search(page_html)
    if not match:
        return ""
    return html.unescape(match.group(1))


def _extract_title_tag(page_html: str) -> str:
    match = TITLE_TAG_RE.search(page_html)
    if not match:
        return ""
    return html.unescape(strip_html(match.group(1)))


def _extract_time_datetime(page_html: str) -> str:
    match = TIME_TAG_RE.search(page_html)
    if not match:
        return ""
    return html.unescape(match.group(1)).strip()


def _is_generic_title(title: str) -> bool:
    normalized = strip_html(title)
    if normalized in GENERIC_TITLES:
        return True
    return len(normalized) <= 2


def _choose_title(candidate_title: str, extracted_title: str, source_name: str) -> str:
    cleaned_candidate = strip_html(candidate_title)
    cleaned_extracted = strip_html(extracted_title)
    if cleaned_extracted and not _is_generic_title(cleaned_extracted):
        if cleaned_extracted != source_name:
            return cleaned_extracted
    return cleaned_candidate or cleaned_extracted or "Untitled"


def _candidate_search_text(candidate: ArticleCandidate) -> str:
    return "\n".join([candidate.title, candidate.summary_hint])


def _article_search_text(article: Article) -> str:
    return "\n".join(
        [
            article.title,
            article.summary_hint,
            article.content,
        ]
    )


def _find_blacklist_hits(
    title: str,
    summary_hint: str,
    blacklist_keywords: list[str],
) -> list[str]:
    # Blacklist should only suppress articles whose visible headline/summary
    # clearly centers on the unwanted topic. Matching the full body caused
    # too many false positives when articles mentioned CVEs in passing.
    visible_text = "\n".join([title, summary_hint]).strip()
    return _find_matching_keywords(visible_text, blacklist_keywords)


def _merge_keywords(first: list[str], second: list[str]) -> list[str]:
    merged: list[str] = []
    for keyword in first + second:
        if keyword not in merged:
            merged.append(keyword)
    return merged


def _find_matching_keywords(text: str, keywords: list[str]) -> list[str]:
    if not text.strip():
        return []

    matches: list[str] = []
    for keyword in keywords:
        if _contains_keyword(text, keyword) and keyword not in matches:
            matches.append(keyword)
    return matches


def _contains_keyword(text: str, keyword: str) -> bool:
    cleaned_keyword = keyword.strip()
    if not cleaned_keyword:
        return False

    if re.search(r"[\u4e00-\u9fff]", cleaned_keyword):
        return cleaned_keyword in text

    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(cleaned_keyword)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))
