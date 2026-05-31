"""
Dedup cache for codex-research profiles.

Stores hash-keyed JSON dumps of profile results below SEARCH_LOCAL_CACHE_ROOT.
Read path: if entry exists AND mtime within TTL → return parsed dict (cache hit).
Write path: serialize result on disk for future hits.

TTLs (seconds) tuned per profile:
  quick / docs / research:   24h   (SERP changes daily, docs links stable for a day)
  google:                    12h   (quota-bound web SERP)
  research-pipeline:         12h   (multi-provider runs are more expensive)
  fetch:                     7d    (URL contents drift slowly)
  doctor:                    0     (always fresh — never cache health check)

Lazy cleanup: on each write, also evicts entries older than MAX_AGE (30 days)
to bound disk growth without a cron.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .config import CACHE_ROOT

DEDUP_ROOT = CACHE_ROOT.parent / "dedup"

TTL_SECONDS = {
    "quick": 24 * 3600,
    "docs": 24 * 3600,
    "research": 24 * 3600,
    "google": 12 * 3600,
    "research-pipeline": 12 * 3600,
    "fetch": 7 * 24 * 3600,
    "doctor": 0,
}

MAX_AGE_SECONDS = 30 * 24 * 3600  # housekeeping ceiling


def _enabled() -> bool:
    return os.environ.get("SEARCH_LOCAL_NO_CACHE", "").strip() not in {"1", "true", "yes"}


def _key(profile: str, query: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"profile": profile, "query": query, "params": params},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _path_for(profile: str, key: str) -> Path:
    return DEDUP_ROOT / f"{profile}-{key}.json"


def lookup(profile: str, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Return cached result if fresh, else None."""
    if not _enabled():
        return None
    ttl = TTL_SECONDS.get(profile, 0)
    if ttl <= 0:
        return None
    path = _path_for(profile, _key(profile, query, params))
    if not path.exists():
        return None
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if age > ttl:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def store(profile: str, query: str, params: dict[str, Any], result: dict[str, Any]) -> None:
    """Persist result. Skip if profile has TTL=0 or result has warnings (don't cache errors)."""
    if not _enabled():
        return
    if TTL_SECONDS.get(profile, 0) <= 0:
        return
    if result.get("warnings"):
        return
    try:
        DEDUP_ROOT.mkdir(parents=True, exist_ok=True)
        path = _path_for(profile, _key(profile, query, params))
        # Atomic write: <name>.tmp then rename — prevents truncated JSON on crash mid-write
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        _evict_old()
    except OSError:
        # cache failures must never break the search call
        pass


def _evict_old() -> None:
    """Drop dedup entries older than MAX_AGE; cheap pass invoked on each write."""
    if not DEDUP_ROOT.exists():
        return
    now = time.time()
    for entry in DEDUP_ROOT.iterdir():
        try:
            if not entry.is_file():
                continue
            if (now - entry.stat().st_mtime) > MAX_AGE_SECONDS:
                entry.unlink()
        except OSError:
            continue


def cleanup_runs(runs_root: Path = CACHE_ROOT, max_age_days: int = 30) -> dict[str, int]:
    """Remove artifact run dirs older than max_age_days. Returns {dropped, kept}.

    Standalone helper for the `search-local doctor` flow or external cron.
    """
    if not runs_root.exists():
        return {"dropped": 0, "kept": 0}
    cutoff = time.time() - max_age_days * 24 * 3600
    dropped = 0
    kept = 0
    for entry in runs_root.iterdir():
        try:
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime < cutoff:
                # shutil.rmtree would also handle subdirs; small artifact dirs are tiny
                import shutil
                shutil.rmtree(entry, ignore_errors=True)
                dropped += 1
            else:
                kept += 1
        except OSError:
            continue
    return {"dropped": dropped, "kept": kept}


def cached_call(
    profile: str,
    query: str,
    params: dict[str, Any],
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Wrap a profile function with read-through cache.

    1. lookup → if fresh, annotate `result['summary']['cache_hit'] = True` and return
    2. invoke fn() (live API call) and store result
    """
    hit = lookup(profile, query, params)
    if hit is not None:
        summary = hit.setdefault("summary", {})
        summary["cache_hit"] = True
        return hit
    result = fn()
    store(profile, query, params, result)
    summary = result.setdefault("summary", {})
    summary["cache_hit"] = False
    return result
