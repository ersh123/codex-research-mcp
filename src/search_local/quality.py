from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .models import Source
from .research import detect_source_flags, freshness_bucket, quality_score

PRIMARY_DOMAINS = (
    "docs.",
    "developer.",
    "developers.",
    "github.com",
    "arxiv.org",
)

STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "not",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
    "without",
}

CLAIM_SIGNAL_RE = re.compile(
    r"(\b20\d{2}\b|\b\d+(?:\.\d+)?%?\b|\bmust\b|\bshould\b|\brequires?\b|\bsupports?\b|"
    r"\bdeprecated\b|\bremoved\b|\breleased\b|\bchanged\b|\badded\b|\bsecurity\b|\bCVE-\d+)",
    re.I,
)
NEGATIVE_RE = re.compile(r"\b(no longer|not|cannot|can't|without|deprecated|removed|unsupported|fails?|broken|risk)\b", re.I)
POSITIVE_RE = re.compile(r"\b(supports?|available|works?|can|released|added|improves?|increases?)\b", re.I)


def evidence_type(source: Source) -> str:
    url = source.url.lower()
    title = source.title.lower()
    domain = source.domain.lower()
    if source.source_type == "official_docs":
        return "primary_docs"
    if domain.startswith(("docs.", "developer.", "developers.")):
        return "primary_docs"
    if source.source_type == "github":
        if "/issues/" in url or "/discussions/" in url:
            return "maintainer_discussion"
        if "/pull/" in url or "/commit/" in url or "/blob/" in url:
            return "source_repository"
        return "source_repository"
    if source.source_type in {"forum", "reddit"}:
        return "field_report"
    if "arxiv.org" in url or "paper" in title or "technical report" in title:
        return "paper"
    if source.published:
        return "dated_web"
    return "generic_web"


def trust_tier(source: Source) -> str:
    etype = evidence_type(source)
    if etype in {"primary_docs", "source_repository", "paper"}:
        return "primary"
    if etype in {"maintainer_discussion", "dated_web"}:
        return "secondary"
    if etype == "field_report":
        return "field"
    return "weak"


def trust_score(source: Source) -> float:
    tier = trust_tier(source)
    base = {"primary": 0.88, "secondary": 0.68, "field": 0.52, "weak": 0.36}[tier]
    if source.url.startswith("https://"):
        base += 0.04
    if source.published:
        base += 0.04
    if len(source.snippet) >= 180:
        base += 0.04
    if any(source.domain.startswith(prefix) for prefix in PRIMARY_DOMAINS):
        base += 0.04
    flags = detect_source_flags(source)
    if "hype_language" in flags:
        base -= 0.12
    if "thin_snippet" in flags:
        base -= 0.12
    if "missing_url" in flags:
        base -= 0.25
    return round(max(0.0, min(1.0, base)), 3)


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s+", compact)
    return [part.strip(" .") for part in parts if 40 <= len(part.strip()) <= 280]


def extract_claims(source: Source, *, per_source: int = 3) -> list[str]:
    text = " ".join([source.title, source.snippet, " ".join(source.highlights)])
    candidates = [s for s in _sentences(text) if CLAIM_SIGNAL_RE.search(s)]
    if not candidates and source.snippet:
        candidates = _sentences(source.snippet)[:1]
    return candidates[:per_source]


def claim_fingerprint(text: str) -> str:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
    useful = [word for word in words if word not in STOPWORDS]
    return " ".join(useful[:10]) or text.lower()[:80]


def claim_polarity(text: str) -> str:
    has_negative = bool(NEGATIVE_RE.search(text))
    has_positive = bool(POSITIVE_RE.search(text))
    if has_negative and not has_positive:
        return "negative"
    if has_positive and not has_negative:
        return "positive"
    if has_negative and has_positive:
        return "mixed"
    return "neutral"


def claim_inventory(sources: list[Source], *, max_claims: int = 30) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[str, Source]]] = defaultdict(list)
    for source in sources:
        for claim in extract_claims(source):
            grouped[claim_fingerprint(claim)].append((claim, source))

    claims: list[dict[str, Any]] = []
    for key, items in grouped.items():
        domains = sorted({source.domain for _claim, source in items if source.domain})
        primary_sources = [source for _claim, source in items if trust_tier(source) == "primary"]
        avg_trust = sum(trust_score(source) for _claim, source in items) / max(len(items), 1)
        confidence = avg_trust
        if len(domains) >= 2:
            confidence += 0.12
        if primary_sources:
            confidence += 0.10
        polarities = Counter(claim_polarity(claim) for claim, _source in items)
        claims.append({
            "claim": items[0][0],
            "fingerprint": key,
            "support_count": len(items),
            "domains": domains[:8],
            "primary_support": len(primary_sources),
            "polarity": polarities.most_common(1)[0][0],
            "confidence": round(min(1.0, confidence), 3),
            "sources": [
                {
                    "rank": source.rank,
                    "title": source.title,
                    "url": source.url,
                    "domain": source.domain,
                    "trust_tier": trust_tier(source),
                }
                for _claim, source in items[:5]
            ],
        })

    return sorted(claims, key=lambda c: (c["confidence"], c["support_count"], c["primary_support"]), reverse=True)[:max_claims]


def contradiction_inventory(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_fingerprint[claim["fingerprint"]].append(claim)

    contradictions: list[dict[str, Any]] = []
    for key, items in by_fingerprint.items():
        polarities = {item["polarity"] for item in items}
        if len(items) > 1 and {"positive", "negative"} <= polarities:
            contradictions.append({
                "fingerprint": key,
                "risk": "polarity_conflict",
                "claims": [item["claim"] for item in items[:4]],
            })
    return contradictions[:10]


def source_scorecard(sources: list[Source], *, limit: int = 80) -> list[dict[str, Any]]:
    rows = []
    for source in sources[:limit]:
        rows.append({
            "rank": source.rank,
            "title": source.title,
            "url": source.url,
            "domain": source.domain,
            "source_type": source.source_type,
            "evidence_type": evidence_type(source),
            "trust_tier": trust_tier(source),
            "trust_score": trust_score(source),
            "freshness": freshness_bucket(source),
            "quality_score": quality_score(source),
            "flags": detect_source_flags(source),
        })
    return rows


def build_quality_audit(sources: list[Source]) -> dict[str, Any]:
    if not sources:
        return {
            "overall_score": 0,
            "verdict": "no_sources",
            "recommendations": ["Collect sources before synthesis."],
            "claims": [],
            "contradictions": [],
            "source_scorecard": [],
        }

    scorecard = source_scorecard(sources)
    claims = claim_inventory(sources)
    contradictions = contradiction_inventory(claims)
    tiers = Counter(row["trust_tier"] for row in scorecard)
    evidence = Counter(row["evidence_type"] for row in scorecard)
    freshness = Counter(row["freshness"] for row in scorecard)
    flags = Counter(flag for row in scorecard for flag in row["flags"])

    trust_avg = sum(row["trust_score"] for row in scorecard) / len(scorecard)
    primary_ratio = tiers["primary"] / len(scorecard)
    multi_source_claims = sum(1 for claim in claims if claim["support_count"] >= 2 or claim["primary_support"])
    citation_coverage = min(1.0, multi_source_claims / max(min(len(claims), 12), 1))
    freshness_score = (freshness["fresh"] + 0.65 * freshness["unknown"] + 0.35 * freshness["aging"]) / len(scorecard)
    diversity_score = min(1.0, len({row["domain"] for row in scorecard if row["domain"]}) / 12)
    contradiction_score = max(0.0, 1.0 - len(contradictions) * 0.18)
    overall = round(
        trust_avg * 0.34
        + citation_coverage * 0.24
        + freshness_score * 0.16
        + diversity_score * 0.14
        + contradiction_score * 0.08
        + primary_ratio * 0.04,
        3,
    )

    if overall >= 0.78:
        verdict = "strong"
    elif overall >= 0.62:
        verdict = "usable"
    elif overall >= 0.45:
        verdict = "thin"
    else:
        verdict = "weak"

    recommendations: list[str] = []
    if primary_ratio < 0.2:
        recommendations.append("Add more primary sources: official docs, source repositories, papers, or changelogs.")
    if citation_coverage < 0.5:
        recommendations.append("Cross-check key claims with at least two independent sources before synthesis.")
    if flags["thin_snippet"] > len(scorecard) * 0.25:
        recommendations.append("Fetch full pages for thin snippets; SERP text is not enough for a final answer.")
    if contradictions:
        recommendations.append("Resolve contradiction candidates before writing the final report.")
    if freshness["stale"]:
        recommendations.append("Replace stale sources for fast-moving topics.")

    return {
        "overall_score": overall,
        "verdict": verdict,
        "source_mix": {
            "trust_tiers": dict(tiers),
            "evidence_types": dict(evidence),
            "freshness": dict(freshness),
            "flags": dict(flags),
        },
        "coverage": {
            "claims_found": len(claims),
            "multi_source_or_primary_claims": multi_source_claims,
            "citation_coverage_score": round(citation_coverage, 3),
            "domain_diversity_score": round(diversity_score, 3),
            "average_trust_score": round(trust_avg, 3),
        },
        "claims": claims,
        "contradictions": contradictions,
        "recommendations": recommendations,
        "source_scorecard": scorecard,
    }
