from __future__ import annotations

import re
from collections import Counter, OrderedDict
from datetime import UTC, datetime
from typing import Any

from .models import Source

RISK_TERMS = {
    "deprecated",
    "no longer supported",
    "security advisory",
    "cve-",
    "exploit",
    "breaking change",
    "outdated",
    "unmaintained",
}
HYPE_TERMS = {"ultimate", "revolutionary", "game changer", "guaranteed", "magic", "10x"}


def build_subqueries(query: str) -> list[str]:
    return list(OrderedDict.fromkeys([
        query,
        f"{query} official documentation",
        f"{query} github issue discussion",
        f"{query} changelog release notes",
        f"{query} security advisory CVE",
        f"{query} best practices pitfalls",
    ]))


def quality_score(source: Source) -> float:
    score = 0.35
    if source.source_type == "official_docs":
        score += 0.35
    elif source.source_type == "github":
        score += 0.22
    elif source.source_type == "forum":
        score += 0.08
    if source.url.startswith("https://"):
        score += 0.08
    if source.snippet:
        score += min(len(source.snippet) / 2000, 0.12)
    if source.published:
        score += 0.08
    return round(min(score, 1.0), 3)


def freshness_bucket(source: Source, *, now: datetime | None = None) -> str:
    if not source.published:
        return "unknown"
    now = now or datetime.now(UTC)
    match = re.search(r"(20\d{2}|19\d{2})", source.published)
    if not match:
        return "unknown"
    age = now.year - int(match.group(1))
    if age <= 1:
        return "fresh"
    if age <= 3:
        return "aging"
    return "stale"


def detect_source_flags(source: Source) -> list[str]:
    haystack = f"{source.title} {source.snippet}".lower()
    flags: list[str] = []
    if any(term in haystack for term in RISK_TERMS):
        flags.append("risk_term")
    if any(term in haystack for term in HYPE_TERMS):
        flags.append("hype_language")
    if not source.url:
        flags.append("missing_url")
    if len(source.snippet) < 40:
        flags.append("thin_snippet")
    return flags


def summarize_validation(sources: list[Source]) -> dict[str, Any]:
    domain_counts = Counter(s.domain for s in sources if s.domain)
    type_counts = Counter(s.source_type for s in sources)
    freshness_counts = Counter(freshness_bucket(s) for s in sources)
    flagged = [
        {"rank": s.rank, "url": s.url, "flags": flags}
        for s in sources
        if (flags := detect_source_flags(s))
    ]
    cross_reference = {
        "domains_with_multiple_sources": [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common()
            if count > 1
        ][:15],
        "source_types": dict(type_counts),
    }
    return {
        "source_count": len(sources),
        "unique_domains": len(domain_counts),
        "freshness": dict(freshness_counts),
        "cross_reference": cross_reference,
        "flags": flagged[:25],
        "average_quality_score": round(sum(quality_score(s) for s in sources) / len(sources), 3) if sources else 0,
    }


def annotate_sources(sources: list[Source]) -> list[Source]:
    for source in sources:
        source.extra["quality_score"] = quality_score(source)
        source.extra["freshness"] = freshness_bucket(source)
        flags = detect_source_flags(source)
        if flags:
            source.extra["flags"] = flags
    return sources
