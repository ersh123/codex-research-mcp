from __future__ import annotations

from . import __doc__ as _unused
from pathlib import Path
import re

from search_local.config import EXA_FETCH, EXA_SEARCH
from search_local.models import Source
from search_local.util import domain_from_url, run_cmd


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


def classify_source(url: str, title: str = "") -> str:
    u = url.lower()
    t = title.lower()
    if any(x in u for x in ("/docs", "docs.", "developer.", "/dev/", "api-reference", "reference")) or "docs" in t:
        return "official_docs"
    if "github.com" in u:
        return "github"
    if "reddit.com" in u:
        return "reddit"
    if any(x in u for x in ("stackoverflow.com", "stackexchange.com", "discourse", "forum")):
        return "forum"
    return "web"


def _parse_sections(markdown: str) -> list[tuple[str, list[str]]]:
    lines = markdown.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current_title is not None:
                sections.append((current_title, current))
            current_title = line[3:].strip()
            current = []
        elif current_title is not None:
            current.append(line)
    if current_title is not None:
        sections.append((current_title, current))
    return sections


def parse_exa_markdown(markdown: str, *, query: str, engine: str = "exa") -> list[Source]:
    sources: list[Source] = []
    for idx, (title, lines) in enumerate(_parse_sections(markdown), start=1):
        url = ""
        published = None
        author = None
        summary_parts: list[str] = []
        highlights: list[str] = []
        in_highlights = False
        in_text = False
        text_parts: list[str] = []
        for line in lines:
            if line.startswith("- URL: "):
                url = line.removeprefix("- URL: ").strip()
                in_highlights = False
                in_text = False
            elif line.startswith("- Published: "):
                published = line.removeprefix("- Published: ").strip()
            elif line.startswith("- Author: "):
                author = line.removeprefix("- Author: ").strip()
            elif line.startswith("- Summary: "):
                summary_parts.append(line.removeprefix("- Summary: ").strip())
                in_highlights = False
                in_text = False
            elif line.startswith("- Highlights:"):
                in_highlights = True
                in_text = False
            elif line.startswith("- Text:"):
                in_text = True
                in_highlights = False
            elif in_highlights and line.startswith("  - "):
                highlights.append(line[4:].strip())
            elif in_text:
                if line.strip():
                    text_parts.append(line.strip())
        snippet = " ".join(summary_parts) or " ".join(highlights[:2]) or " ".join(text_parts[:3])
        sources.append(Source(
            engine=engine,
            query=query,
            rank=idx,
            title=title,
            url=url,
            domain=domain_from_url(url),
            snippet=snippet[:2000],
            source_type=classify_source(url, title),
            published=published,
            author=author,
            highlights=highlights,
        ))
    return sources


def exa_search(query: str, *, num: int = 5, domains: list[str] | None = None, category: str | None = None, search_type: str = "auto") -> tuple[list[Source], str, str | None]:
    cmd = [str(EXA_SEARCH), "--num", str(num), "--type", search_type]
    if category:
        cmd += ["--category", category]
    for domain in domains or []:
        cmd += ["--domain", domain]
    cmd.append(query)
    proc = run_cmd(cmd, timeout=90)
    if proc.returncode != 0:
        return [], proc.stdout, proc.stderr or f"exa-search exited {proc.returncode}"
    return parse_exa_markdown(proc.stdout, query=query, engine="exa"), proc.stdout, None


def exa_fetch(urls: list[str]) -> tuple[list[Source], str, str | None]:
    proc = run_cmd([str(EXA_FETCH), *urls], timeout=120)
    query = " ".join(urls)
    if proc.returncode != 0:
        return [], proc.stdout, proc.stderr or f"exa-fetch exited {proc.returncode}"
    sources = parse_exa_markdown(proc.stdout, query=query, engine="exa-fetch")
    for source in sources:
        source.source_type = "fetched_page"
    return sources, proc.stdout, None
