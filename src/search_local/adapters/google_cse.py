from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from search_local.adapters.exa import classify_source
from search_local.config import GOOGLE_CSE_CONFIG, GOOGLE_CSE_ENDPOINT, env_or_config
from search_local.models import Source
from search_local.util import domain_from_url


def parse_google_cse(payload: dict[str, Any], *, query: str) -> tuple[list[Source], dict[str, Any]]:
    items = payload.get("items") or []
    sources: list[Source] = []
    for idx, item in enumerate(items, start=1):
        url = str(item.get("link") or "")
        title = str(item.get("title") or url or "Untitled")
        snippet = str(item.get("snippet") or item.get("htmlSnippet") or "")
        pagemap = item.get("pagemap") if isinstance(item.get("pagemap"), dict) else {}
        metatags = pagemap.get("metatags") or []
        published = None
        if metatags and isinstance(metatags[0], dict):
            published = (
                metatags[0].get("article:published_time")
                or metatags[0].get("date")
                or metatags[0].get("pubdate")
            )
        sources.append(Source(
            engine="google-cse",
            query=query,
            rank=idx,
            title=title,
            url=url,
            domain=domain_from_url(url),
            snippet=snippet[:2000],
            source_type=classify_source(url, title),
            published=published,
            extra={"cache_id": item.get("cacheId")} if item.get("cacheId") else {},
        ))
    search_info = payload.get("searchInformation") or {}
    summary = {
        "source_count": len(sources),
        "engine": "google-cse",
        "total_results": search_info.get("totalResults"),
        "search_time": search_info.get("searchTime"),
    }
    return sources, summary


def google_cse_search(
    query: str,
    *,
    num: int = 10,
    start: int = 1,
    country: str | None = None,
    language: str | None = None,
    safe: str | None = None,
) -> tuple[list[Source], dict[str, Any], str, str | None]:
    api_key = env_or_config("GOOGLE_CSE_API_KEY", GOOGLE_CSE_CONFIG)
    cx = env_or_config("GOOGLE_CSE_CX", GOOGLE_CSE_CONFIG)
    if not api_key or not cx:
        return [], {"source_count": 0, "engine": "google-cse"}, "", "GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX are required"

    params: dict[str, str | int] = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max(1, min(int(num), 10)),
        "start": max(1, int(start)),
    }
    if country:
        params["cr"] = country
    if language:
        params["lr"] = language
    if safe:
        params["safe"] = safe

    url = f"{GOOGLE_CSE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "codex-research-mcp/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        return [], {"source_count": 0, "engine": "google-cse", "status": exc.code}, body, f"google-cse HTTP {exc.code}: {body}"
    except OSError as exc:
        return [], {"source_count": 0, "engine": "google-cse"}, "", f"google-cse request failed: {exc}"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], {"source_count": 0, "engine": "google-cse"}, raw, f"google-cse JSON parse failed: {exc}"
    sources, summary = parse_google_cse(payload, query=query)
    return sources, summary, raw, None
