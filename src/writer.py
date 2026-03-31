from __future__ import annotations

import shutil
from pathlib import Path

from .categorizer import format_category_label
from .models import ArticleSummary
from .storage import read_json_file, write_json_file


def write_reports(
    report_date: str,
    generated_at: str,
    report_title: str,
    output_dir: Path,
    summaries: list[ArticleSummary],
    settings=None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    monthly_dir = output_dir / report_date[:7]
    monthly_dir.mkdir(parents=True, exist_ok=True)

    report_json_path = monthly_dir / f"{report_date}.json"
    report_markdown_path = monthly_dir / f"{report_date}.md"
    latest_json_path = output_dir / "latest.json"
    latest_markdown_path = output_dir / "latest.md"

    existing_payload = read_json_file(report_json_path, default={})
    existing_items = existing_payload.get("items", []) if isinstance(existing_payload, dict) else []
    merged_items = _merge_items(existing_items, [summary.to_dict() for summary in summaries])
    if settings is not None:
        from .summarizer import backfill_title_fields

        merged_items = backfill_title_fields(merged_items, settings)

    payload = {
        "date": report_date,
        "generated_at": generated_at,
        "count": len(merged_items),
        "items": merged_items,
    }
    write_json_file(report_json_path, payload)
    report_markdown_path.write_text(
        _build_markdown_report(report_title, report_date, generated_at, merged_items),
        encoding="utf-8",
    )

    shutil.copyfile(report_json_path, latest_json_path)
    shutil.copyfile(report_markdown_path, latest_markdown_path)


def _merge_items(existing_items: list[dict], new_items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in existing_items + new_items:
        canonical_link = item.get("canonical_link") or item.get("link")
        if canonical_link:
            merged[canonical_link] = item

    return sorted(
        merged.values(),
        key=lambda item: (
            item.get("published_at", ""),
            item.get("title_zh") or item.get("title", ""),
        ),
        reverse=True,
    )


def _build_markdown_report(
    report_title: str,
    report_date: str,
    generated_at: str,
    items: list[dict],
) -> str:
    llm_count = sum(1 for item in items if not item.get("used_fallback"))
    fallback_count = len(items) - llm_count
    lines = [
        f"# {report_title} | {report_date}",
        "",
        f"- 生成时间: {generated_at}",
        f"- 文章数量: {len(items)}",
        f"- 大模型摘要: {llm_count}",
        f"- 回退摘要: {fallback_count}",
        "",
        "## 分类清单",
        "",
    ]
    lines.extend(_build_category_index(items))
    lines.extend(["", "## 详细内容", ""])

    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index}. {_display_title(item)}",
                f"- 分类: {format_category_label(item.get('category') or '综合资讯')}",
                f"- 来源: {item['source']}",
                f"- 发布时间: {item.get('published_at') or 'Unknown'}",
                f"- 风险等级: {item['risk_level']}",
                f"- 关键词: {', '.join(item.get('keywords') or []) or 'N/A'}",
                f"- 命中关注词: {', '.join(item.get('matched_focus_keywords') or []) or '无'}",
                f"- 原文链接: {item['link']}",
                f"- 摘要来源: {'回退逻辑' if item.get('used_fallback') else '大模型'}",
                "",
                *(_original_title_lines(item)),
                "### 摘要",
                item["summary"],
                "",
                "### 要点",
            ]
        )
        for point in item.get("important_points", []):
            lines.append(f"- {point}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _build_category_index(items: list[dict]) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        category = item.get("category") or "综合资讯"
        grouped.setdefault(category, []).append(item)

    ordered_categories = sorted(
        grouped.items(),
        key=lambda pair: (-len(pair[1]), pair[0]),
    )

    lines: list[str] = []
    for category, category_items in ordered_categories:
        lines.append(f"### {format_category_label(category)}（{len(category_items)}）")
        for item in category_items:
            lines.append(f"- {_bilingual_title(item)}")
        lines.append("")

    if not lines:
        lines.append("- 暂无分类结果")

    return lines


def _display_title(item: dict) -> str:
    return (item.get("title_zh") or item.get("title") or "").strip()


def _bilingual_title(item: dict) -> str:
    display_title = _display_title(item)
    original_title = str(item.get("title") or "").strip()
    if not original_title or display_title == original_title:
        return display_title
    return f"{display_title} / {original_title}"


def _original_title_lines(item: dict) -> list[str]:
    display_title = _display_title(item)
    original_title = str(item.get("title") or "").strip()
    if not original_title or display_title == original_title:
        return []
    return [f"- 原标题: {original_title}", ""]
