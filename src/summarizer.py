from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from itertools import islice

from openai import OpenAI

from .categorizer import categorize_summary
from .config import Settings
from .models import Article, ArticleSummary

HIGH_RISK_MARKERS = {
    "zero-day",
    "0day",
    "ransomware",
    "breach",
    "data leak",
    "exploit",
    "remote code execution",
    "botnet",
}
MEDIUM_RISK_MARKERS = {
    "malware",
    "phishing",
    "patch",
    "vulnerability",
    "cve-",
    "backdoor",
    "supply chain",
}


def summarize_articles(
    articles: list[Article],
    settings: Settings,
) -> list[ArticleSummary]:
    if not articles:
        return []

    if not settings.llm_enabled:
        return [_build_fallback_summary(article) for article in articles]

    summaries: list[ArticleSummary] = []
    batch_size = max(1, settings.llm_batch_size)
    total_batches = (len(articles) + batch_size - 1) // batch_size

    for batch_index, batch in enumerate(_chunked(articles, batch_size), start=1):
        print(
            f"Running LLM batch {batch_index}/{total_batches} "
            f"for {len(batch)} articles..."
        )
        summaries.extend(_summarize_batch_with_resilience(batch, settings))

    return summaries


def summarize_article(article: Article, settings: Settings) -> ArticleSummary:
    summaries = summarize_articles([article], settings)
    if not summaries:
        raise RuntimeError(f"Failed to summarize article: {article.link}")
    return summaries[0]


def _summarize_batch_with_resilience(
    articles: list[Article],
    settings: Settings,
) -> list[ArticleSummary]:
    llm_results: dict[str, ArticleSummary] = {}

    try:
        llm_results = _summarize_batch_with_llm(articles, settings)
    except Exception as exc:
        print(f"Batch LLM summary failed for {len(articles)} articles | {exc}")

    summaries: list[ArticleSummary] = []
    for article in articles:
        summary = llm_results.get(article.canonical_link)
        if summary is None:
            summary = _summarize_single_with_resilience(article, settings)
        summaries.append(summary)

    batch_llm_count = sum(1 for summary in summaries if not summary.used_fallback)
    print(
        f"Completed batch: {batch_llm_count}/{len(summaries)} via LLM, "
        f"{len(summaries) - batch_llm_count} via fallback."
    )

    return summaries


def _summarize_single_with_resilience(
    article: Article,
    settings: Settings,
) -> ArticleSummary:
    if settings.llm_enabled:
        try:
            return _summarize_with_llm(article, settings)
        except Exception as exc:
            print(f"Single article LLM summary failed: {article.link} | {exc}")
            if not settings.allow_fallback_summary:
                raise RuntimeError(
                    f"LLM summary failed for {article.link}: {exc}"
                ) from exc

    if not settings.allow_fallback_summary:
        raise RuntimeError("LLM credentials are missing and fallback summary is disabled.")
    return _build_fallback_summary(article)


@lru_cache(maxsize=1)
def _get_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url)


def _summarize_batch_with_llm(
    articles: list[Article],
    settings: Settings,
) -> dict[str, ArticleSummary]:
    client = _get_client(settings.llm_api_key or "", settings.llm_base_url)
    article_lookup = {
        str(index): article
        for index, article in enumerate(articles, start=1)
    }

    response = _chat_complete(
        client,
        settings,
        [
            {
                "role": "system",
                "content": (
                    "You are a cybersecurity analyst. "
                    "Return one JSON object only. "
                    'Schema: {"items": [{"id": string, "summary": string, '
                    '"risk_level": "高|中|低", "keywords": string[], '
                    '"important_points": string[]}]}. '
                    "Use Simplified Chinese for all explanatory text. "
                    "If the source article is in English, translate key facts first and then summarize in Chinese. "
                    "Return exactly one item for each input article id. "
                    "Do not wrap JSON in markdown."
                ),
            },
            {
                "role": "user",
                "content": _build_batch_prompt(article_lookup, settings),
            },
        ],
        temperature=0.2,
    )
    payload = _parse_json_payload(response.choices[0].message.content or "")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Batch LLM payload missing items array.")

    results: dict[str, ArticleSummary] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue

        article_id = str(raw_item.get("id") or "").strip()
        article = article_lookup.get(article_id)
        if article is None:
            continue

        normalized_payload = _normalize_payload(raw_item)
        normalized_payload = _ensure_chinese_payload(client, settings, normalized_payload)
        results[article.canonical_link] = _build_article_summary(article, normalized_payload, used_fallback=False)

    return results


def _summarize_with_llm(article: Article, settings: Settings) -> ArticleSummary:
    client = _get_client(settings.llm_api_key or "", settings.llm_base_url)
    response = _chat_complete(
        client,
        settings,
        [
            {
                "role": "system",
                "content": (
                    "You are a cybersecurity analyst. "
                    "Return one JSON object only. "
                    'Schema: {"summary": string, "risk_level": "高|中|低", '
                    '"keywords": string[], "important_points": string[]}. '
                    "Use Simplified Chinese for all explanatory text. "
                    "If the source article is in English, translate the key facts first and then summarize in Chinese. "
                    "Keep vendor, product, malware, and standard names only when necessary. "
                    "Do not wrap JSON in markdown."
                ),
            },
            {
                "role": "user",
                "content": _build_single_prompt(article, settings),
            },
        ],
        temperature=0.2,
    )
    payload = _parse_json_payload(response.choices[0].message.content or "")
    normalized_payload = _normalize_payload(payload)
    normalized_payload = _ensure_chinese_payload(client, settings, normalized_payload)
    return _build_article_summary(article, normalized_payload, used_fallback=False)


def _build_batch_prompt(
    article_lookup: dict[str, Article],
    settings: Settings,
) -> str:
    items = []
    for article_id, article in article_lookup.items():
        items.append(
            {
                "id": article_id,
                "title": article.title,
                "source": article.source,
                "published_at": article.published_at or "Unknown",
                "focus_keywords": article.matched_focus_keywords,
                "content_excerpt": _compact_article_text(article, settings),
            }
        )

    return (
        "请批量处理下面这些网络安全资讯，输出严格 JSON，不要输出其他说明。\n\n"
        "要求：\n"
        "1. items 中每个对象必须对应一个输入 id，不能遗漏。\n"
        "2. summary 为 2-4 句中文摘要，优先保留事件、影响、建议。\n"
        "3. 如果原文是英文，先翻译关键信息，再输出简体中文。\n"
        "4. keywords 输出 3-5 个关键词，尽量中文化。\n"
        "5. important_points 输出 2-3 条中文要点。\n"
        "6. 不要编造信息，不确定就写信息有限。\n\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )


def _build_single_prompt(article: Article, settings: Settings) -> str:
    return f"""
请为下面这篇网络安全资讯生成中文摘要，输出严格 JSON，不要输出其他说明。

要求：
1. summary 为 3-5 句中文摘要，突出事件、影响和处置建议。
2. risk_level 只能是 高 / 中 / 低。
3. 如果原文是英文，先理解并翻译关键信息，再输出中文摘要。
4. keywords 输出 3-5 个关键词，尽量使用中文；厂商、产品、组织名称可以保留英文。
5. important_points 输出 2-4 条要点，每条一句话，尽量使用中文。
6. 如出现英文句子或英文要点，需要先转成简体中文再输出。
7. 不要编造文章中没有出现的事实；信息不足时明确说明信息有限。

文章元数据：
标题: {article.title}
来源: {article.source}
发布时间: {article.published_at or "Unknown"}
命中关注词: {", ".join(article.matched_focus_keywords) or "无"}
链接: {article.link}

文章内容：
{_compact_article_text(article, settings)}
""".strip()


def _compact_article_text(article: Article, settings: Settings) -> str:
    text = article.content or article.summary_hint or article.title
    text = re.sub(r"\s+", " ", text).strip()
    return text[: settings.max_llm_input_chars_per_article]


def _parse_json_payload(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced_match:
        cleaned = fenced_match.group(1)

    object_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if object_match:
        cleaned = object_match.group(0)

    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("LLM payload is not a JSON object.")
    return payload


def _normalize_payload(payload: dict) -> dict:
    return {
        "summary": _normalize_summary(payload.get("summary")),
        "risk_level": _normalize_risk_level(payload.get("risk_level")),
        "keywords": _normalize_keywords(payload.get("keywords")),
        "important_points": _normalize_points(payload.get("important_points")),
    }


def _normalize_risk_level(value: object) -> str:
    text = str(value or "").strip()
    if text in {"高", "中", "低"}:
        return text
    return "中"


def _normalize_keywords(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    keywords: list[str] = []
    for item in value:
        keyword = str(item).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords[:5]


def _normalize_summary(value: object) -> str:
    summary = str(value or "").strip()
    if not summary:
        return "摘要生成失败。"
    return summary


def _normalize_points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    points: list[str] = []
    for item in value:
        point = str(item).strip()
        if point and point not in points:
            points.append(point)
    return points[:4]


def _build_article_summary(
    article: Article,
    payload: dict,
    used_fallback: bool,
) -> ArticleSummary:
    summary = ArticleSummary(
        source=article.source,
        title=article.title,
        link=article.link,
        canonical_link=article.canonical_link,
        published_at=article.published_at,
        category="",
        risk_level=_normalize_risk_level(payload.get("risk_level")),
        keywords=_normalize_keywords(payload.get("keywords")),
        summary=_normalize_summary(payload.get("summary")),
        important_points=_normalize_points(payload.get("important_points")),
        used_fallback=used_fallback,
        matched_focus_keywords=article.matched_focus_keywords,
    )
    summary.category = categorize_summary(summary)
    return summary


def _build_fallback_summary(article: Article) -> ArticleSummary:
    text = article.content or article.summary_hint or article.title
    points = _extract_points(text)
    summary = (
        "未调用大模型，以下为原文关键信息摘录："
        + ("；".join(points[:3]) or "未能从原文中提取足够内容，请检查源站是否可访问。")
    )

    return _build_article_summary(
        article,
        {
            "risk_level": _infer_risk_level(text),
            "keywords": _guess_keywords(article),
            "summary": summary,
            "important_points": points[:3] or [article.title],
        },
        used_fallback=True,
    )


def _ensure_chinese_payload(
    client: OpenAI,
    settings: Settings,
    payload: dict,
) -> dict:
    if _payload_is_mostly_chinese(payload):
        return payload

    rewrite_response = _chat_complete(
        client,
        settings,
        [
            {
                "role": "system",
                "content": (
                    "You rewrite cybersecurity summaries into Simplified Chinese. "
                    "Return one JSON object only and keep the same schema."
                ),
            },
            {
                "role": "user",
                "content": (
                    "把下面 JSON 中所有说明性文本改写为简体中文。"
                    "厂商、产品、组织、恶意软件名称可以保留英文。"
                    "keywords 和 important_points 也要尽量中文化。\n\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ],
        temperature=0.1,
    )
    rewrite_message = rewrite_response.choices[0].message.content or ""
    rewritten_payload = _normalize_payload(_parse_json_payload(rewrite_message))
    if _payload_is_mostly_chinese(rewritten_payload):
        return rewritten_payload
    return payload


def _payload_is_mostly_chinese(payload: dict) -> bool:
    parts = [
        str(payload.get("summary") or ""),
        *[str(item) for item in payload.get("important_points") or []],
        *[str(item) for item in payload.get("keywords") or []],
    ]
    combined = " ".join(part for part in parts if part.strip())
    if not combined:
        return False

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", combined))
    english_chars = len(re.findall(r"[A-Za-z]", combined))
    return chinese_chars > 0 and chinese_chars >= max(12, english_chars // 2)


def _extract_points(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    chunks = re.split(r"(?<=[。！？.!?])\s+", normalized)
    points = [chunk.strip(" -") for chunk in chunks if chunk.strip()]
    return points[:4]


def _infer_risk_level(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in HIGH_RISK_MARKERS):
        return "高"
    if any(marker in lowered for marker in MEDIUM_RISK_MARKERS):
        return "中"
    return "低"


def _guess_keywords(article: Article) -> list[str]:
    keywords = list(article.matched_focus_keywords)
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{2,}", article.title)
    for candidate in candidates:
        if candidate not in keywords:
            keywords.append(candidate)
    if article.source not in keywords:
        keywords.append(article.source)
    return keywords[:5]


def _chunked(items: list[Article], size: int) -> list[list[Article]]:
    iterator = iter(items)
    chunks: list[list[Article]] = []
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            break
        chunks.append(chunk)
    return chunks


def _chat_complete(
    client: OpenAI,
    settings: Settings,
    messages: list[dict[str, str]],
    temperature: float,
):
    attempts = max(1, settings.llm_retry_count + 1)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return client.chat.completions.create(
                model=settings.llm_model,
                temperature=temperature,
                messages=messages,
                timeout=max(60, settings.request_timeout_seconds * 3),
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(min(2 * attempt, 6))

    raise RuntimeError(f"LLM request failed after {attempts} attempts: {last_error}")
