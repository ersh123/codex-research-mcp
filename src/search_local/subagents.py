from __future__ import annotations

from typing import Any

SUBAGENT_TEMPLATES = [
    {
        "name": "scope_mapper",
        "objective": "Map the topic, terms, and likely answer shape before collecting evidence.",
        "queries": [
            "{query} overview key concepts",
            "{query} comparison alternatives",
        ],
    },
    {
        "name": "primary_source_hunter",
        "objective": "Prefer primary evidence: official docs, changelogs, papers, repositories, and standards.",
        "queries": [
            "{query} official documentation changelog release notes",
            "{query} github repository issue pull request specification paper",
        ],
    },
    {
        "name": "freshness_guard",
        "objective": "Find current behavior, recent changes, deprecations, and version-sensitive details.",
        "queries": [
            "{query} latest update 2026 deprecation migration",
            "{query} breaking change current version known issue",
        ],
    },
    {
        "name": "skeptic",
        "objective": "Look for counter-evidence, failure reports, limitations, and overclaimed claims.",
        "queries": [
            "{query} limitations pitfalls failure case",
            "{query} criticism contradiction does not work",
        ],
    },
    {
        "name": "practitioner",
        "objective": "Collect practical examples, implementation reports, and field-tested patterns.",
        "queries": [
            "{query} best practices implementation example",
            "{query} case study lessons learned",
        ],
    },
    {
        "name": "synthesis_editor",
        "objective": "Find structured summaries and check whether the final answer has enough coverage.",
        "queries": [
            "{query} guide checklist",
            "{query} benchmark evaluation",
        ],
    },
]


def build_subagent_plan(query: str) -> list[dict[str, Any]]:
    return [
        {
            "name": template["name"],
            "objective": template["objective"],
            "queries": [q.format(query=query) for q in template["queries"]],
        }
        for template in SUBAGENT_TEMPLATES
    ]
