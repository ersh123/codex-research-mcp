from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from search_local.adapters.exa import classify_source
from search_local.config import XMLSTOCK_CONFIG, XMLSTOCK_GOOGLE_XML_ENDPOINT, env_or_config
from search_local.models import Source
from search_local.util import domain_from_url

URL_RE = re.compile(r"<url>(.*?)</url>", re.S | re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
PASSAGE_RE = re.compile(r"<passage>(.*?)</passage>", re.S | re.I)
DOC_RE = re.compile(r"<doc(?:\s[^>]*)?>(.*?)</doc>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
ERROR_RE = re.compile(r'<error code="([^"]+)">(.*?)</error>', re.S | re.I)


def clean_xml_text(value: str) -> str:
    value = html.unescape(value)
    value = TAG_RE.sub("", value)
    return html.unescape(value).strip()


def _xml_items(xml: str) -> list[tuple[str, str, str]]:
    docs = DOC_RE.findall(xml)
    if docs:
        items: list[tuple[str, str, str]] = []
        for doc in docs:
            url_match = URL_RE.search(doc)
            if not url_match:
                continue
            title_match = TITLE_RE.search(doc)
            passage_match = PASSAGE_RE.search(doc)
            items.append((
                html.unescape(url_match.group(1).strip()),
                clean_xml_text(title_match.group(1)) if title_match else "",
                clean_xml_text(passage_match.group(1)) if passage_match else "",
            ))
        return items

    urls = [html.unescape(u.strip()) for u in URL_RE.findall(xml)]
    titles = [clean_xml_text(t) for t in TITLE_RE.findall(xml)]
    passages = [clean_xml_text(p) for p in PASSAGE_RE.findall(xml)]
    return [
        (
            url,
            titles[idx] if idx < len(titles) else "",
            passages[idx] if idx < len(passages) else "",
        )
        for idx, url in enumerate(urls)
    ]


def parse_google_xmlstock(xml: str, *, query: str) -> tuple[list[Source], dict[str, Any]]:
    items = _xml_items(xml)
    sources: list[Source] = []
    domains: list[str] = []
    for idx, (url, title, snippet) in enumerate(items, start=1):
        domain = domain_from_url(url)
        domains.append(domain)
        sources.append(Source(
            engine="google-xmlstock",
            query=query,
            rank=idx,
            title=title,
            url=url,
            domain=domain,
            snippet=snippet[:2000],
            source_type=classify_source(url, title),
        ))
    counts = Counter(d for d in domains if d)
    return sources, {
        "source_count": len(sources),
        "engine": "google-xmlstock",
        "top_domains": [{"domain": d, "count": c} for d, c in counts.most_common(15)],
    }


def google_xmlstock_search(
    query: str,
    *,
    num: int = 10,
    page: int | None = None,
    region: str | int | None = None,
    domain: str | None = None,
    device: str | None = None,
    tbm: str | None = None,
    tbs: str | None = None,
    related: bool = False,
) -> tuple[list[Source], dict[str, Any], str, str | None]:
    user = env_or_config("XMLSTOCK_USER", XMLSTOCK_CONFIG)
    key = env_or_config("XMLSTOCK_KEY", XMLSTOCK_CONFIG)
    if not user or not key:
        return [], {"source_count": 0, "engine": "google-xmlstock"}, "", "XMLSTOCK_USER and XMLSTOCK_KEY are required"

    params: dict[str, str | int] = {"user": user, "key": key, "query": query}
    if region is not None:
        params["lr"] = str(region)
    if page is not None:
        params["page"] = int(page)
    if domain:
        params["domain"] = domain
    if device:
        params["device"] = device
    if tbm:
        params["tbm"] = tbm
    if tbs:
        params["tbs"] = tbs
    if related:
        params["related"] = 1
    if num:
        params["groupby"] = f"attr=d.mode=deep.groups-on-page={max(1, min(int(num), 100))}.docs-in-group=1"

    url = f"{XMLSTOCK_GOOGLE_XML_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "codex-research-mcp/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        return [], {"source_count": 0, "engine": "google-xmlstock", "status": exc.code}, body, f"google-xmlstock HTTP {exc.code}: {body}"
    except OSError as exc:
        return [], {"source_count": 0, "engine": "google-xmlstock"}, "", f"google-xmlstock request failed: {exc}"

    if match := ERROR_RE.search(raw):
        code = match.group(1)
        text = clean_xml_text(match.group(2))
        return [], {"source_count": 0, "engine": "google-xmlstock", "error_code": code}, raw, f"google-xmlstock error {code}: {text}"

    sources, summary = parse_google_xmlstock(raw, query=query)
    return sources, summary, raw, None
