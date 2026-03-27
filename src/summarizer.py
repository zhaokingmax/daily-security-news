from __future__ import annotations

import json
import re
from functools import lru_cache

from openai import OpenAI

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


def summarize_article(article: Article, settings: Settings) -> ArticleSummary:
    if settings.llm_enabled:
        try:
            return _summarize_with_llm(article, settings)
        except Exception as exc:
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


def _summarize_with_llm(article: Article, settings: Settings) -> ArticleSummary:
    client = _get_client(settings.llm_api_key or "", settings.llm_base_url)
    response = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a cybersecurity analyst. "
                    "Return one JSON object only. "
                    'Schema: {"summary": string, "risk_level": "高|中|低", '
                    '"keywords": string[], "important_points": string[]}. '
                    "Use Simplified Chinese. Do not wrap JSON in markdown."
                ),
            },
            {
                "role": "user",
                "content": _build_prompt(article),
            },
        ],
    )
    message = response.choices[0].message.content or ""
    payload = _parse_json_payload(message)

    return ArticleSummary(
        source=article.source,
        title=article.title,
        link=article.link,
        canonical_link=article.canonical_link,
        published_at=article.published_at,
        risk_level=_normalize_risk_level(payload.get("risk_level")),
        keywords=_normalize_keywords(payload.get("keywords")),
        summary=_normalize_summary(payload.get("summary")),
        important_points=_normalize_points(payload.get("important_points")),
        used_fallback=False,
    )


def _build_prompt(article: Article) -> str:
    content = article.content[:8000]
    return f"""
请为下面这篇网络安全资讯生成中文摘要，输出严格 JSON，不要输出其他说明。

要求：
1. summary 为 3-5 句中文摘要，突出事件、影响和处置建议。
2. risk_level 只能是 高 / 中 / 低。
3. keywords 输出 3-5 个关键词。
4. important_points 输出 2-4 条要点，每条一句话。
5. 不要编造文章中没有出现的事实；信息不足时明确说明信息有限。

文章元数据：
标题: {article.title}
来源: {article.source}
发布时间: {article.published_at or "Unknown"}
链接: {article.link}

文章内容：
{content}
""".strip()


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


def _normalize_risk_level(value: object) -> str:
    text = str(value or "").strip()
    if text in {"高", "中", "低"}:
        return text
    return "中"


def _normalize_keywords(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    keywords = [str(item).strip() for item in value if str(item).strip()]
    return keywords[:5]


def _normalize_summary(value: object) -> str:
    summary = str(value or "").strip()
    if not summary:
        return "摘要生成失败。"
    return summary


def _normalize_points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    points = [str(item).strip() for item in value if str(item).strip()]
    return points[:4]


def _build_fallback_summary(article: Article) -> ArticleSummary:
    text = article.content or article.summary_hint or article.title
    points = _extract_points(text)
    summary = "；".join(points[:3]) or "未能从原文中提取足够内容，请检查源站是否可访问。"

    return ArticleSummary(
        source=article.source,
        title=article.title,
        link=article.link,
        canonical_link=article.canonical_link,
        published_at=article.published_at,
        risk_level=_infer_risk_level(text),
        keywords=_guess_keywords(article),
        summary=summary,
        important_points=points[:3] or [article.title],
        used_fallback=True,
    )


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
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{2,}", article.title)
    keywords = candidates[:4]
    if article.source not in keywords:
        keywords.append(article.source)
    return keywords[:5]

