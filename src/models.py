from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class Article:
    source: str
    title: str
    link: str
    canonical_link: str
    published_at: str
    summary_hint: str
    content: str
    matched_focus_keywords: list[str]


@dataclass(slots=True)
class ArticleSummary:
    source: str
    title: str
    title_zh: str
    link: str
    canonical_link: str
    published_at: str
    category: str
    risk_level: str
    keywords: list[str]
    summary: str
    important_points: list[str]
    used_fallback: bool
    matched_focus_keywords: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
