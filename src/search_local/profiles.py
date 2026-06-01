from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from typing import Any

from .adapters.exa import exa_fetch, exa_search
from .adapters.google_cse import google_cse_search
from .adapters.google_xmlstock import google_xmlstock_search
from .cache import cached_call
from .config import (
    DEEPSEEK_CONFIG,
    EXA_CONFIG,
    EXA_FETCH,
    EXA_SEARCH,
    GOOGLE_CSE_CONFIG,
    LLM_CONFIG,
    XMLSTOCK_CONFIG,
    XMLSTOCK_LEGACY_CONFIG,
    env_or_config,
    env_or_config_any,
)
from .models import Source
from .quality import build_quality_audit
from .research import annotate_sources, build_subqueries, summarize_validation
from .subagents import build_provider_subagent_plan
from .util import run_cmd


def _dedupe_sources(sources: list[Source]) -> list[Source]:
    seen: set[str] = set()
    out: list[Source] = []
    for src in sources:
        key = src.url or f"{src.engine}:{src.title}:{src.rank}"
        if key in seen:
            continue
        seen.add(key)
        src.rank = len(out) + 1
        out.append(src)
    return out


def _result(profile: str, query: str, sources: list[Source], summary: dict[str, Any], warnings: list[str] | None = None, *, allow_partial: bool = False) -> dict[str, Any]:
    warning_list = warnings or []
    return {
        "ok": (not warning_list) or (allow_partial and bool(sources)),
        "profile": profile,
        "query": query,
        "sources": [s.to_dict() for s in sources],
        "summary": summary,
        "artifacts": {},
        "warnings": warning_list,
    }


def quick(query: str, *, num: int = 5) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        sources, _raw, err = exa_search(query, num=num)
        warnings = [err] if err else []
        return _result("quick", query, sources, {"source_count": len(sources), "engine": "exa"}, warnings)
    return cached_call("quick", query, {"num": num}, _live)


def docs(query: str, *, num: int = 6) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        doc_query = f"{query} official documentation API reference docs"
        sources, _raw, err = exa_search(doc_query, num=num)
        warnings = [err] if err else []
        official_count = sum(1 for s in sources if s.source_type == "official_docs")
        return _result("docs", query, sources, {"source_count": len(sources), "official_docs_count": official_count, "engine": "exa"}, warnings)
    return cached_call("docs", query, {"num": num}, _live)


def google(
    query: str,
    *,
    num: int = 10,
    start: int = 1,
    region: str | int | None = None,
    backend: str = "xmlstock",
    country: str | None = None,
    language: str | None = None,
    safe: str | None = None,
) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        if backend == "cse":
            sources, summary, _raw, err = google_cse_search(query, num=num, start=start, country=country, language=language, safe=safe)
        else:
            page = ((max(start, 1) - 1) // max(num, 1)) if start > 1 else None
            sources, summary, _raw, err = google_xmlstock_search(query, num=num, page=page, region=region)
        warnings = [err] if err else []
        return _result("google", query, sources, summary, warnings)
    params = {"num": num, "start": start, "region": region, "backend": backend, "country": country, "language": language, "safe": safe}
    return cached_call("google", query, params, _live)


def research(query: str, *, num: int = 5) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        subqueries = OrderedDict.fromkeys([
            query,
            f"{query} official documentation",
            f"{query} best practices",
            f"{query} issues workaround",
        ])
        all_sources: list[Source] = []
        warnings: list[str] = []
        for subquery in subqueries:
            sources, _raw, err = exa_search(subquery, num=num)
            if err:
                warnings.append(f"{subquery}: {err}")
            for src in sources:
                src.extra["subquery"] = subquery
            all_sources.extend(sources)
        all_sources = _dedupe_sources(all_sources)
        return _result("research", query, all_sources, {"source_count": len(all_sources), "subqueries": list(subqueries), "engine": "exa"}, warnings)
    return cached_call("research", query, {"num": num}, _live)


def research_pipeline(query: str, *, max_sources: int = 80, include_google: bool = True, include_exa: bool = True, google_backend: str = "xmlstock") -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        subqueries = build_subqueries(query)
        provider_count = int(include_exa) + int(include_google)
        per_query_num = max(2, min(100, math.ceil(max_sources / max(len(subqueries) * max(provider_count, 1), 1))))
        all_sources: list[Source] = []
        warnings: list[str] = []

        for subquery in subqueries:
            if include_exa:
                sources, _raw, err = exa_search(subquery, num=per_query_num)
                if err:
                    warnings.append(f"exa {subquery}: {err}")
                for src in sources:
                    src.extra["subquery"] = subquery
                all_sources.extend(sources)
            if include_google:
                if google_backend == "cse":
                    sources, _summary, _raw, err = google_cse_search(subquery, num=per_query_num)
                    provider_name = "google-cse"
                else:
                    sources, _summary, _raw, err = google_xmlstock_search(subquery, num=per_query_num)
                    provider_name = "google-xmlstock"
                if err:
                    warnings.append(f"google {subquery}: {err}")
                for src in sources:
                    src.extra["subquery"] = subquery
                all_sources.extend(sources)

        all_sources = annotate_sources(_dedupe_sources(all_sources))[:max_sources]
        summary = {
            "engine": "research-pipeline",
            "subqueries": subqueries,
            "providers": [name for name, enabled in [("exa", include_exa), (provider_name if include_google else "google-xmlstock", include_google)] if enabled],
            **summarize_validation(all_sources),
            "quality_audit": build_quality_audit(all_sources),
        }
        return _result("research-pipeline", query, all_sources, summary, warnings)

    params = {"max_sources": max_sources, "include_google": include_google, "include_exa": include_exa, "google_backend": google_backend}
    return cached_call("research-pipeline", query, params, _live)


def research_subagents(
    query: str,
    *,
    max_sources: int = 140,
    include_google: bool = True,
    include_exa: bool = True,
    google_backend: str = "xmlstock",
    subagent_provider: str = "deterministic",
    subagent_count: int = 6,
    subagent_model: str | None = None,
    parallelism: int = 8,
) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        plan, planner, plan_warnings = build_provider_subagent_plan(query, provider=subagent_provider, count=subagent_count, model=subagent_model)
        provider_count = int(include_exa) + int(include_google)
        query_count = sum(len(lane["queries"]) for lane in plan)
        per_query_num = max(2, min(25, math.ceil(max_sources / max(query_count * max(provider_count, 1), 1))))
        all_sources: list[Source] = []
        warnings: list[str] = [*plan_warnings]
        providers: list[str] = []
        if include_exa:
            providers.append("exa")
        if include_google:
            providers.append("google-cse" if google_backend == "cse" else "google-xmlstock")

        tasks: list[dict[str, Any]] = []
        for lane in plan:
            for subquery in lane["queries"]:
                if include_exa:
                    tasks.append({"provider": "exa", "lane": lane, "subquery": subquery})
                if include_google:
                    tasks.append({"provider": "google", "lane": lane, "subquery": subquery})

        def run_task(index: int, task: dict[str, Any]) -> tuple[int, str | None, list[Source]]:
            lane = task["lane"]
            subquery = task["subquery"]
            provider = task["provider"]
            if provider == "exa":
                sources, _raw, err = exa_search(subquery, num=per_query_num)
            elif google_backend == "cse":
                sources, _summary, _raw, err = google_cse_search(subquery, num=per_query_num)
            else:
                sources, _summary, _raw, err = google_xmlstock_search(subquery, num=per_query_num)
            for src in sources:
                src.extra["subagent"] = lane["name"]
                src.extra["lane_objective"] = lane["objective"]
                src.extra["subquery"] = subquery
            warning = f"{provider} {lane['name']} {subquery}: {err}" if err else None
            return index, warning, sources

        task_results: list[tuple[int, str | None, list[Source]]] = []
        worker_count = max(1, min(max(1, parallelism), len(tasks))) if tasks else 0
        if tasks:
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                futures = [pool.submit(run_task, index, task) for index, task in enumerate(tasks)]
                for future in as_completed(futures):
                    task_results.append(future.result())

        for _index, warning, sources in sorted(task_results, key=lambda item: item[0]):
            if warning:
                warnings.append(warning)
            all_sources.extend(sources)

        all_sources = annotate_sources(_dedupe_sources(all_sources))[:max_sources]
        validation = summarize_validation(all_sources)
        audit = build_quality_audit(all_sources)
        summary = {
            "engine": "research-subagents",
            "subagents": plan,
            "subagent_provider": subagent_provider,
            "subagent_count": len(plan),
            "subagent_planner": planner,
            "providers": providers,
            "per_query_num": per_query_num,
            "parallelism": worker_count,
            "partial_failures": len(warnings),
            **validation,
            "quality_audit": audit,
        }
        return _result("research-subagents", query, all_sources, summary, warnings, allow_partial=True)

    params = {
        "max_sources": max_sources,
        "include_google": include_google,
        "include_exa": include_exa,
        "google_backend": google_backend,
        "subagent_provider": subagent_provider,
        "subagent_count": subagent_count,
        "subagent_model": subagent_model,
        "parallelism": parallelism,
    }
    return cached_call("research-subagents", query, params, _live)


def fetch(urls: list[str]) -> dict[str, Any]:
    def _live() -> dict[str, Any]:
        sources, _raw, err = exa_fetch(urls)
        warnings = [err] if err else []
        return _result("fetch", " ".join(urls), sources, {"source_count": len(sources), "engine": "exa-fetch"}, warnings)
    key = " ".join(sorted(urls))
    return cached_call("fetch", key, {"urls": sorted(urls)}, _live)


def doctor(*, live: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            warnings.append(f"{name}: {detail}")

    def add_optional(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "optional": True, "detail": detail})

    for name, path in [("exa-search", EXA_SEARCH), ("exa-fetch", EXA_FETCH)]:
        add(name, path.exists() and path.is_file(), str(path))
    add("exa-config", EXA_CONFIG.exists(), f"{EXA_CONFIG} exists; content not printed" if EXA_CONFIG.exists() else f"{EXA_CONFIG} missing")
    add(
        "google-xmlstock-config",
        bool(
            env_or_config_any(("XMLSTOCK_USER", "XMLSTOCK_YANDEX_XML_USER"), XMLSTOCK_CONFIG, XMLSTOCK_LEGACY_CONFIG)
            and env_or_config_any(("XMLSTOCK_KEY", "XMLSTOCK_YANDEX_XML_KEY"), XMLSTOCK_CONFIG, XMLSTOCK_LEGACY_CONFIG)
        ),
        f"{XMLSTOCK_CONFIG} or {XMLSTOCK_LEGACY_CONFIG} or env XMLSTOCK_USER/XMLSTOCK_KEY",
    )
    add_optional(
        "google-cse-config",
        bool(env_or_config("GOOGLE_CSE_API_KEY", GOOGLE_CSE_CONFIG) and env_or_config("GOOGLE_CSE_CX", GOOGLE_CSE_CONFIG)),
        f"optional fallback: {GOOGLE_CSE_CONFIG} or env GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX",
    )
    add_optional(
        "deepseek-config",
        bool(env_or_config("DEEPSEEK_API_KEY", LLM_CONFIG, DEEPSEEK_CONFIG)),
        f"optional subagent planner: {LLM_CONFIG} or {DEEPSEEK_CONFIG} or env DEEPSEEK_API_KEY",
    )

    for name, path in [("exa-search-help", EXA_SEARCH), ("exa-fetch-help", EXA_FETCH)]:
        if path.exists():
            proc = run_cmd([str(path), "--help"], timeout=20)
            add(name, proc.returncode == 0, "help ok" if proc.returncode == 0 else proc.stderr)

    live_summary: dict[str, Any] = {}
    if live:
        q = quick("OpenAI Codex MCP documentation", num=1)
        add("exa-live", bool(q["sources"]), f"sources={len(q['sources'])}")
        g = google("OpenAI Codex MCP documentation", num=1)
        add("google-live", bool(g["sources"]), f"sources={len(g['sources'])}")
        live_summary = {"exa_sources": len(q["sources"]), "google_sources": len(g["sources"])}

    return {
        "ok": not warnings,
        "profile": "doctor",
        "query": "doctor",
        "sources": [],
        "summary": {"checks": checks, "live": live, **live_summary},
        "artifacts": {},
        "warnings": warnings,
    }
