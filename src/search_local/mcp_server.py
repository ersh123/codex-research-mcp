#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .artifacts import write_artifacts
from .profiles import docs, doctor, fetch, google, quick, research, research_pipeline, research_subagents
from .redaction import redact_text


def _with_artifacts(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("profile") != "doctor":
        result["artifacts"] = write_artifacts(result)
    return result


def exa_quick(query: str, num: int = 5) -> dict[str, Any]:
    return _with_artifacts(quick(query, num=int(num)))


def exa_research(query: str, num: int = 5) -> dict[str, Any]:
    return _with_artifacts(research(query, num=int(num)))


def exa_docs(query: str, num: int = 6) -> dict[str, Any]:
    return _with_artifacts(docs(query, num=int(num)))


def exa_fetch(url: str) -> dict[str, Any]:
    return _with_artifacts(fetch([url]))


def google_search(
    query: str,
    num: int = 10,
    start: int = 1,
    backend: str = "xmlstock",
    region: str | int | None = None,
    country: str | None = None,
    language: str | None = None,
    safe: str | None = None,
) -> dict[str, Any]:
    return _with_artifacts(google(query, num=int(num), start=int(start), backend=backend, region=region, country=country, language=language, safe=safe))


def run_research_pipeline(query: str, max_sources: int = 80, include_google: bool = True, include_exa: bool = True, google_backend: str = "xmlstock") -> dict[str, Any]:
    return _with_artifacts(research_pipeline(query, max_sources=int(max_sources), include_google=bool(include_google), include_exa=bool(include_exa), google_backend=google_backend))


def deep_research(query: str, max_sources: int = 140, include_google: bool = True, include_exa: bool = True, google_backend: str = "xmlstock") -> dict[str, Any]:
    return _with_artifacts(research_subagents(query, max_sources=int(max_sources), include_google=bool(include_google), include_exa=bool(include_exa), google_backend=google_backend))


def search_doctor(live: bool = False) -> dict[str, Any]:
    return doctor(live=bool(live))


TOOLS = [
    {
        "name": "exa_quick",
        "description": "Fast Exa search for quick fact lookup and general web discovery.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "num": {"type": "integer", "default": 5}}, "required": ["query"]},
    },
    {
        "name": "exa_research",
        "description": "Multi-query Exa research with dedupe and source classification.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "num": {"type": "integer", "default": 5}}, "required": ["query"]},
    },
    {
        "name": "exa_docs",
        "description": "Docs-first Exa search for official documentation, API references, and SDK guidance.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "num": {"type": "integer", "default": 6}}, "required": ["query"]},
    },
    {
        "name": "exa_fetch",
        "description": "Fetch extracted page content for a known URL through Exa.",
        "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "google_search",
        "description": "Google search via XMLstock Google XML by default, or Google CSE JSON fallback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num": {"type": "integer", "default": 10},
                "start": {"type": "integer", "default": 1},
                "backend": {"type": "string", "enum": ["xmlstock", "cse"], "default": "xmlstock"},
                "region": {"type": "string"},
                "country": {"type": "string"},
                "language": {"type": "string"},
                "safe": {"type": "string", "enum": ["active", "off"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "research_pipeline",
        "description": "Codex-oriented research pipeline: query expansion, multi-provider collection, dedupe, freshness checks, cross-reference, quality audit, and weak-source flags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_sources": {"type": "integer", "default": 80},
                "include_google": {"type": "boolean", "default": True},
                "include_exa": {"type": "boolean", "default": True},
                "google_backend": {"type": "string", "enum": ["xmlstock", "cse"], "default": "xmlstock"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "deep_research",
        "description": "Multi-lane research with deterministic subagents: scope mapping, primary sources, freshness, skepticism, practitioner evidence, synthesis, and quality audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_sources": {"type": "integer", "default": 140},
                "include_google": {"type": "boolean", "default": True},
                "include_exa": {"type": "boolean", "default": True},
                "google_backend": {"type": "string", "enum": ["xmlstock", "cse"], "default": "xmlstock"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_doctor",
        "description": "Health check for Exa, Google CSE credentials, and optional live probes.",
        "inputSchema": {"type": "object", "properties": {"live": {"type": "boolean", "default": False}}},
    },
]


def _text_result(result: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": redact_text(json.dumps(result, ensure_ascii=False, indent=2))}]}


def handle(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-research-mcp", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "exa_quick": exa_quick,
            "exa_research": exa_research,
            "exa_docs": exa_docs,
            "exa_fetch": exa_fetch,
            "google_search": google_search,
            "research_pipeline": run_research_pipeline,
            "deep_research": deep_research,
            "search_doctor": search_doctor,
        }
        if name not in handlers:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown tool {name}"}}
        try:
            return {"jsonrpc": "2.0", "id": rid, "result": _text_result(handlers[name](**args))}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}

    if method == "notifications/initialized":
        return None
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}}


def write(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            write(resp)


if __name__ == "__main__":
    main()
