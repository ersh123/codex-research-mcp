from search_local.models import Source
from search_local.quality import build_quality_audit, claim_inventory, evidence_type, trust_tier


def _source(
    rank: int,
    *,
    url: str,
    title: str,
    snippet: str,
    source_type: str = "web",
    published: str | None = "2026-01-01",
) -> Source:
    domain = url.split("/")[2] if "://" in url else ""
    return Source(
        engine="test",
        query="q",
        rank=rank,
        title=title,
        url=url,
        domain=domain,
        snippet=snippet,
        source_type=source_type,
        published=published,
    )


def test_quality_audit_scores_primary_sources_and_claim_coverage():
    sources = [
        _source(
            1,
            url="https://docs.example.com/api/release",
            title="Official API release notes",
            snippet="The 2026 API release requires explicit retry handling and supports idempotency keys for safer writes.",
            source_type="official_docs",
        ),
        _source(
            2,
            url="https://github.com/org/repo/issues/42",
            title="Maintainer issue discussion",
            snippet="Maintainers confirmed in 2026 that retry handling should use idempotency keys after transient failures.",
            source_type="github",
        ),
        _source(
            3,
            url="https://example.com/blog",
            title="Implementation guide",
            snippet="A field guide says retry handling can reduce duplicate writes when idempotency keys are configured.",
            source_type="web",
        ),
    ]

    audit = build_quality_audit(sources)

    assert audit["verdict"] in {"usable", "strong"}
    assert audit["overall_score"] > 0.6
    assert audit["coverage"]["claims_found"] >= 2
    assert audit["source_mix"]["trust_tiers"]["primary"] >= 1
    assert audit["recommendations"] == [] or all(isinstance(item, str) for item in audit["recommendations"])


def test_quality_audit_flags_thin_weak_sources():
    sources = [
        _source(1, url="", title="Ultimate magic fix", snippet="", source_type="web", published=None),
        _source(2, url="http://thin.example.com", title="Guaranteed 10x", snippet="Short", source_type="web", published=None),
    ]

    audit = build_quality_audit(sources)

    assert audit["verdict"] in {"weak", "thin"}
    assert audit["source_mix"]["flags"]["thin_snippet"] == 2
    assert audit["source_mix"]["flags"]["hype_language"] >= 1
    assert audit["recommendations"]


def test_evidence_type_and_claim_inventory_are_deterministic():
    source = _source(
        1,
        url="https://github.com/org/repo/issues/1",
        title="Issue: removed option",
        snippet="The 2026 release removed the legacy option and requires the new configuration flag.",
        source_type="github",
    )

    claims = claim_inventory([source])

    assert evidence_type(source) == "maintainer_discussion"
    assert trust_tier(source) == "secondary"
    assert claims[0]["polarity"] in {"negative", "mixed"}
    assert claims[0]["sources"][0]["rank"] == 1


def test_research_word_does_not_make_generic_source_primary():
    source = _source(
        1,
        url="https://example.com/deep-research",
        title="Open-source deep research assistant",
        snippet="This article compares research assistants and lists practical workflow ideas.",
        source_type="web",
        published=None,
    )

    assert evidence_type(source) == "generic_web"
    assert trust_tier(source) == "weak"
