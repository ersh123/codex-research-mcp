from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CACHE_ROOT
from .redaction import redact_text
from .util import timestamp_slug


def make_run_dir(profile: str, query: str, out: str | None = None) -> Path:
    if out:
        path = Path(out).expanduser().resolve()
    else:
        path = CACHE_ROOT / f"{profile}-{timestamp_slug(query)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_safe(data: Any) -> Any:
    if isinstance(data, Path):
        return str(data)
    if isinstance(data, dict):
        return {k: _json_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_json_safe(v) for v in data]
    return data


def render_report(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) or {}
    sources = result.get("sources", []) or []
    warnings = result.get("warnings", []) or []
    lines = [
        f"# search-local report: {result.get('profile', '')}",
        "",
        f"Query: `{result.get('query', '')}`",
        f"OK: `{result.get('ok')}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- **{key}**: `{value}`")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {w}" for w in warnings)
    lines.extend(["", "## Sources", ""])
    for src in sources[:50]:
        title = src.get("title") or src.get("url") or "Untitled"
        url = src.get("url", "")
        rank = src.get("rank", "")
        engine = src.get("engine", "")
        domain = src.get("domain", "")
        snippet = src.get("snippet", "")
        lines.append(f"{rank}. **{title}** ({engine}, {domain})")
        if url:
            lines.append(f"   - {url}")
        if snippet:
            lines.append(f"   - {snippet[:500]}")
    return redact_text("\n".join(lines).rstrip() + "\n")


def write_artifacts(result: dict[str, Any], out: str | None = None) -> dict[str, str]:
    run_dir = make_run_dir(result.get("profile", "run"), result.get("query", "run"), out)
    sources_path = run_dir / "sources.jsonl"
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "report.md"

    sources = result.get("sources", []) or []
    with sources_path.open("w", encoding="utf-8") as fh:
        for src in sources:
            fh.write(redact_text(json.dumps(_json_safe(src), ensure_ascii=False)) + "\n")

    summary_payload = {k: v for k, v in result.items() if k != "artifacts"}
    summary_path.write_text(redact_text(json.dumps(_json_safe(summary_payload), ensure_ascii=False, indent=2)) + "\n", encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    return {"run_dir": str(run_dir), "sources_jsonl": str(sources_path), "summary_json": str(summary_path), "report_md": str(report_path)}
