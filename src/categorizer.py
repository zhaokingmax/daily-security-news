from __future__ import annotations

import re

from .models import ArticleSummary

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "AI安全与安全智能体",
        [
            "ai",
            "llm",
            "genai",
            "大模型",
            "安全智能体",
            "security agent",
            "agentic",
            "prompt injection",
            "guardrail",
        ],
    ),
    (
        "身份与访问控制",
        [
            "identity",
            "iam",
            "access management",
            "access control",
            "sso",
            "mfa",
            "authentication",
            "authorization",
            "零信任",
        ],
    ),
    (
        "终端安全与EDR/XDR",
        [
            "edr",
            "xdr",
            "endpoint",
            "defender",
            "crowdstrike",
            "sentinelone",
            "终端安全",
        ],
    ),
    (
        "APT与国家级威胁",
        [
            "apt",
            "nation-state",
            "state-sponsored",
            "国家级",
            "威胁溯源",
            "attribution",
            "threat actor",
        ],
    ),
    (
        "运营商与关键基础设施",
        [
            "telecom",
            "telecommunications",
            "运营商",
            "critical infrastructure",
            "电信",
            "grid",
            "pipeline",
        ],
    ),
    (
        "漏洞与补丁",
        [
            "zero-day",
            "0day",
            "vulnerability",
            "漏洞",
            "patch",
            "exploit",
            "rce",
        ],
    ),
    (
        "恶意软件与勒索软件",
        [
            "malware",
            "ransomware",
            "botnet",
            "trojan",
            "wiper",
            "木马",
            "勒索",
        ],
    ),
    (
        "钓鱼与社工诈骗",
        [
            "phishing",
            "scam",
            "social engineering",
            "business email compromise",
            "bec",
            "钓鱼",
            "诈骗",
        ],
    ),
    (
        "数据泄露与隐私",
        [
            "breach",
            "data leak",
            "data exposure",
            "privacy",
            "泄露",
            "数据外泄",
        ],
    ),
    (
        "云安全与容器",
        [
            "cloud",
            "aws",
            "azure",
            "gcp",
            "kubernetes",
            "container",
            "docker",
            "云安全",
        ],
    ),
    (
        "网络与边界安全",
        [
            "firewall",
            "vpn",
            "router",
            "switch",
            "network",
            "cisco",
            "palo alto",
            "fortinet",
            "netscaler",
            "边界安全",
        ],
    ),
    (
        "应用安全与供应链",
        [
            "application security",
            "appsec",
            "supply chain",
            "dependency",
            "ci/cd",
            "软件供应链",
            "应用安全",
        ],
    ),
    (
        "威胁情报与研判",
        [
            "threat intelligence",
            "threat hunting",
            "threat analysis",
            "威胁情报",
            "威胁研判",
            "ioc",
        ],
    ),
    (
        "安全运营与SOC",
        [
            "soc",
            "security operations center",
            "siem",
            "soar",
            "mdr",
            "安全运营",
        ],
    ),
    (
        "工控与物联网安全",
        [
            "ot",
            "ics",
            "scada",
            "iot",
            "industrial",
            "工控",
            "物联网",
        ],
    ),
    (
        "政策合规与治理",
        [
            "policy",
            "regulation",
            "compliance",
            "governance",
            "cisa",
            "cncert",
            "政策",
            "合规",
        ],
    ),
]
DEFAULT_CATEGORY = "综合资讯"


def categorize_summary(summary: ArticleSummary) -> str:
    normalized_summary = summary.summary.replace("未调用大模型，以下为原文关键信息摘录：", "")
    search_text = "\n".join(
        [
            summary.title,
            summary.source,
            normalized_summary,
            " ".join(summary.keywords),
            " ".join(summary.important_points),
            " ".join(summary.matched_focus_keywords),
        ]
    )

    for category, keywords in CATEGORY_RULES:
        if any(_contains_keyword(search_text, keyword) for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


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
