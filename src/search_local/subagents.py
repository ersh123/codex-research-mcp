from __future__ import annotations

import json
import re
from typing import Any

from .llm import chat_completion

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

EXTRA_SUBAGENT_TEMPLATES = [
    {
        "name": "numbers_checker",
        "objective": "Find numeric benchmarks, budgets, CPC/CVR metrics, and measurement caveats.",
        "queries": [
            "{query} benchmarks metrics statistics report",
            "{query} cost conversion rate measurement study",
        ],
    },
    {
        "name": "strategy_builder",
        "objective": "Collect strategy patterns, prioritization frameworks, and decision checklists.",
        "queries": [
            "{query} strategy framework playbook",
            "{query} tactics checklist optimization",
        ],
    },
    {
        "name": "tooling_mapper",
        "objective": "Find tools, automation surfaces, APIs, integrations, and workflow examples.",
        "queries": [
            "{query} tools automation API integration",
            "{query} workflow template setup",
        ],
    },
    {
        "name": "edge_case_hunter",
        "objective": "Search for edge cases, policy limits, account risks, and false-positive advice.",
        "queries": [
            "{query} edge cases policy limits risk",
            "{query} mistakes myths outdated advice",
        ],
    },
]


def _template_plan(query: str, count: int) -> list[dict[str, Any]]:
    templates = [*SUBAGENT_TEMPLATES, *EXTRA_SUBAGENT_TEMPLATES]
    plan: list[dict[str, Any]] = []
    for index in range(max(1, count)):
        if index < len(templates):
            template = templates[index]
            name = template["name"]
        else:
            template = {
                "objective": "Collect additional independent evidence for uncovered angles.",
                "queries": [
                    "{query} evidence examples",
                    "{query} analysis report",
                ],
            }
            name = f"research_lane_{index + 1}"
        plan.append(
            {
                "name": name,
                "objective": template["objective"],
                "queries": [q.format(query=query) for q in template["queries"]],
            }
        )
    return plan


def build_subagent_plan(query: str, *, count: int = 6) -> list[dict[str, Any]]:
    return _template_plan(query, count)


def _slug_name(value: str, fallback: str, seen: set[str]) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")[:48]
    if not slug:
        slug = fallback
    base = slug
    suffix = 2
    while slug in seen:
        slug = f"{base}_{suffix}"
        suffix += 1
    seen.add(slug)
    return slug


def _clean_query(topic: str, query: str) -> str:
    cleaned = " ".join(str(query).split())[:180]
    if not cleaned:
        return topic
    topic_head = topic.split()[0].lower() if topic.split() else ""
    if topic_head and topic_head not in cleaned.lower():
        return f"{topic} {cleaned}"[:220]
    return cleaned


def sanitize_subagent_plan(topic: str, items: list[Any], *, count: int) -> list[dict[str, Any]]:
    fallback = build_subagent_plan(topic, count=count)
    seen: set[str] = set()
    plan: list[dict[str, Any]] = []

    for index, item in enumerate(items[: max(1, count)]):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback[min(index, len(fallback) - 1)]
        name = _slug_name(str(item.get("name") or fallback_item["name"]), f"agent_{index + 1}", seen)
        objective = " ".join(str(item.get("objective") or fallback_item["objective"]).split())[:280]
        raw_queries = item.get("queries")
        if not isinstance(raw_queries, list):
            raw_queries = fallback_item["queries"]
        queries = [_clean_query(topic, q) for q in raw_queries if str(q).strip()]
        if not queries:
            queries = fallback_item["queries"]
        plan.append({"name": name, "objective": objective, "queries": queries[:3]})

    while len(plan) < max(1, count):
        item = fallback[len(plan)]
        name = _slug_name(item["name"], f"agent_{len(plan) + 1}", seen)
        plan.append({"name": name, "objective": item["objective"], "queries": item["queries"]})
    return plan[: max(1, count)]


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start_candidates = [idx for idx in (cleaned.find("["), cleaned.find("{")) if idx >= 0]
    if start_candidates:
        cleaned = cleaned[min(start_candidates):]
    return json.loads(cleaned)


def _parse_llm_plan(topic: str, content: str, *, count: int) -> list[dict[str, Any]]:
    payload = _extract_json(content)
    if isinstance(payload, dict):
        payload = payload.get("subagents") or payload.get("agents") or payload.get("lanes")
    if not isinstance(payload, list):
        raise ValueError("subagent planner must return a JSON list")
    return sanitize_subagent_plan(topic, payload, count=count)


def build_provider_subagent_plan(
    query: str,
    *,
    provider: str = "deterministic",
    count: int = 6,
    model: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    normalized = provider.strip().lower()
    if normalized in {"", "deterministic", "static"}:
        plan = build_subagent_plan(query, count=count)
        return plan, {"provider": "deterministic", "planner_ok": True, "count": len(plan)}, []

    messages = [
        {
            "role": "system",
            "content": (
                "You create independent web-research lane plans. Return JSON only. "
                "Each lane must have name, objective, and 1-3 search queries. "
                "Do not include secrets, hidden reasoning, markdown, or prose."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "topic": query,
                    "subagent_count": max(1, count),
                    "schema": {"subagents": [{"name": "snake_case", "objective": "string", "queries": ["string"]}]},
                    "requirements": [
                        "Make lanes independent and non-overlapping.",
                        "Include primary sources, freshness, skepticism, quantitative evidence, practitioner evidence, and synthesis.",
                        "Queries must be directly usable in a web search engine.",
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]
    planner_kwargs = {
        "model": model,
        "max_tokens": max(1800, max(1, count) * 220),
        "response_format": {"type": "json_object"},
    }
    content, meta, err = chat_completion(normalized, messages, **planner_kwargs)
    if err and "timed out" in err.lower():
        content, meta, err = chat_completion(normalized, messages, **planner_kwargs)
    if err or content is None:
        plan = build_subagent_plan(query, count=count)
        return plan, {"provider": normalized, "planner_ok": False, "count": len(plan), **meta}, [f"subagent planner {normalized}: {err}"]
    try:
        plan = _parse_llm_plan(query, content, count=count)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        fallback = build_subagent_plan(query, count=count)
        return fallback, {"provider": normalized, "planner_ok": False, "count": len(fallback), **meta}, [f"subagent planner {normalized}: invalid plan: {exc}"]
    return plan, {"provider": normalized, "planner_ok": True, "count": len(plan), **meta}, []
