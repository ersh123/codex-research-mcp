from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifacts import write_artifacts
from .cache import cleanup_runs
from .profiles import docs as run_docs
from .profiles import doctor as run_doctor
from .profiles import fetch as run_fetch
from .profiles import google as run_google
from .profiles import quick as run_quick
from .profiles import research as run_research
from .profiles import research_pipeline as run_research_pipeline
from .redaction import redact_text


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="print machine JSON result")
    p.add_argument("--out", help="artifact output directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-research", description="Local research CLI for Exa, Google XMLstock, Google CSE, and Codex MCP workflows")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("quick", help="fast Exa search")
    p.add_argument("query")
    p.add_argument("--num", type=int, default=5)
    _add_common(p)

    p = sub.add_parser("research", help="multi-query Exa research")
    p.add_argument("query")
    p.add_argument("--num", type=int, default=5)
    _add_common(p)

    p = sub.add_parser("pipeline", help="Codex-oriented research pipeline with validation signals")
    p.add_argument("query")
    p.add_argument("--max-sources", type=int, default=80)
    p.add_argument("--no-google", action="store_true")
    p.add_argument("--no-exa", action="store_true")
    p.add_argument("--google-backend", choices=["xmlstock", "cse"], default="xmlstock")
    _add_common(p)

    p = sub.add_parser("docs", help="official/docs-first Exa search")
    p.add_argument("query")
    p.add_argument("--num", type=int, default=6)
    _add_common(p)

    p = sub.add_parser("google", help="Google search via XMLstock Google XML by default, or CSE JSON fallback")
    p.add_argument("query")
    p.add_argument("--num", type=int, default=10)
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--backend", choices=["xmlstock", "cse"], default="xmlstock")
    p.add_argument("--region", help="optional XMLstock Google region/lr parameter")
    p.add_argument("--country", help="optional cr parameter, e.g. countryUS")
    p.add_argument("--language", help="optional lr parameter, e.g. lang_en")
    p.add_argument("--safe", choices=["active", "off"], help="optional safe search mode")
    _add_common(p)

    p = sub.add_parser("fetch", help="fetch URL contents through Exa")
    p.add_argument("urls", nargs="+")
    _add_common(p)

    p = sub.add_parser("doctor", help="check local search dependencies")
    p.add_argument("--live", action="store_true")
    _add_common(p)

    p = sub.add_parser("cleanup", help="evict old artifact run dirs from cache")
    p.add_argument("--max-age-days", type=int, default=30, help="drop runs older than N days (default 30)")
    p.add_argument("--json", action="store_true", help="print machine JSON result")

    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "quick":
        return run_quick(args.query, num=args.num)
    if args.command == "research":
        return run_research(args.query, num=args.num)
    if args.command == "pipeline":
        return run_research_pipeline(args.query, max_sources=args.max_sources, include_google=not args.no_google, include_exa=not args.no_exa, google_backend=args.google_backend)
    if args.command == "docs":
        return run_docs(args.query, num=args.num)
    if args.command == "google":
        return run_google(args.query, num=args.num, start=args.start, region=args.region, backend=args.backend, country=args.country, language=args.language, safe=args.safe)
    if args.command == "fetch":
        return run_fetch(args.urls)
    if args.command == "doctor":
        return run_doctor(live=args.live)
    if args.command == "cleanup":
        stats = cleanup_runs(max_age_days=args.max_age_days)
        return {
            "ok": True,
            "profile": "cleanup",
            "query": f"max_age_days={args.max_age_days}",
            "sources": [],
            "summary": stats,
            "artifacts": {},
            "warnings": [],
        }
    raise ValueError(f"unknown command: {args.command}")


def emit(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(redact_text(json.dumps(result, ensure_ascii=False, indent=2)))
        return
    report_path = result.get("artifacts", {}).get("report_md")
    if report_path and Path(report_path).exists():
        print(Path(report_path).read_text(encoding="utf-8"))
    else:
        print(redact_text(json.dumps(result, ensure_ascii=False, indent=2)))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = dispatch(args)
    if args.command != "cleanup":
        artifacts = write_artifacts(result, getattr(args, "out", None))
        result["artifacts"] = artifacts
    emit(result, as_json=getattr(args, "json", False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
