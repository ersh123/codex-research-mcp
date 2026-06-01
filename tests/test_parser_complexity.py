from urllib.parse import parse_qs, urlparse

from search_local.adapters import google_xmlstock
from search_local.adapters.exa import classify_source, parse_exa_markdown
from search_local.adapters.google_cse import parse_google_cse
from search_local.adapters.google_xmlstock import clean_xml_text, parse_google_xmlstock


def test_exa_parser_classifies_docs_github_reddit_forum_and_web_for_complex_query():
    query = 'OpenAI Responses API "response.completed" retry -timeout site:github.com'
    markdown = """# Exa Search Results
requestId: abc
## Official streaming docs
- URL: https://docs.example.com/api-reference/responses/streaming
- Published: 2026-05-01
- Author: Docs Team
- Highlights:
  - response.completed closes the stream.
  - retry after transient disconnects.
## GitHub workaround
- URL: https://github.com/org/repo/issues/42
- Summary: Maintainers discuss stream disconnected before completion.
## Reddit field report
- URL: https://www.reddit.com/r/LocalLLaMA/comments/abc/stream_closed/
- Text:
  User report line one.
  User report line two.
## Forum thread
- URL: https://community.example.com/forum/t/retry-after/77
- Summary: Forum workaround.
## General article
- URL: https://example.com/blog/search-local
- Summary: Plain article.
"""

    sources = parse_exa_markdown(markdown, query=query)

    assert [s.rank for s in sources] == [1, 2, 3, 4, 5]
    assert [s.source_type for s in sources] == ["official_docs", "github", "reddit", "forum", "web"]
    assert sources[0].published == "2026-05-01"
    assert sources[0].author == "Docs Team"
    assert "response.completed" in sources[0].snippet
    assert sources[2].snippet == "User report line one. User report line two."
    assert all(s.query == query for s in sources)


def test_classify_source_uses_title_docs_hint_when_url_is_plain():
    assert classify_source("https://example.com/reference", "API Reference") == "official_docs"
    assert classify_source("https://example.com/product", "Official Docs") == "official_docs"
    assert classify_source("https://stackoverflow.com/questions/1", "Bug") == "forum"


def test_google_cse_parser_handles_docs_metadata_and_result_counts():
    query = "OpenAI Codex MCP research pipeline"
    payload = {
        "searchInformation": {"totalResults": "123", "searchTime": 0.23},
        "items": [
            {
                "title": "Official API reference",
                "link": "https://developers.example.com/api/reference",
                "snippet": "Official docs for the API.",
                "cacheId": "abc",
                "pagemap": {"metatags": [{"article:published_time": "2026-05-20T00:00:00Z"}]},
            },
            {
                "title": "GitHub issue",
                "link": "https://github.com/org/repo/issues/42",
                "snippet": "Maintainers discuss a breaking change.",
            },
        ],
    }

    sources, summary = parse_google_cse(payload, query=query)

    assert summary["engine"] == "google-cse"
    assert summary["source_count"] == 2
    assert summary["total_results"] == "123"
    assert [s.rank for s in sources] == [1, 2]
    assert [s.source_type for s in sources] == ["official_docs", "github"]
    assert sources[0].published == "2026-05-20T00:00:00Z"
    assert sources[0].extra == {"cache_id": "abc"}
    assert all(s.query == query for s in sources)


def test_google_xmlstock_parser_handles_docs_entities_and_domains():
    query = 'codex research mcp "google xml"'
    xml = """
<doc><title>Official &amp; API</title><url>https://developers.example.com/docs/search</url><passage>Docs &lt;b&gt;reference&lt;/b&gt;</passage></doc>
<doc><title>GitHub issue</title><url>https://github.com/org/repo/issues/1</url><passage>Maintainer note</passage></doc>
<doc><title>Plain</title><url>https://example.com/blog</url></doc>
"""

    sources, summary = parse_google_xmlstock(xml, query=query)

    assert summary["engine"] == "google-xmlstock"
    assert summary["source_count"] == 3
    assert summary["top_domains"][0] == {"domain": "developers.example.com", "count": 1}
    assert [s.source_type for s in sources] == ["official_docs", "github", "web"]
    assert sources[0].title == "Official & API"
    assert sources[0].snippet == "Docs reference"
    assert all(s.query == query for s in sources)


def test_clean_xml_text_strips_nested_markup_and_unescapes():
    assert clean_xml_text("Цена &lt;b&gt;<hlword>быстро</hlword>&lt;/b&gt; &amp; честно") == "Цена быстро & честно"


def test_google_xmlstock_search_reads_legacy_xmlstock_config(monkeypatch, tmp_path):
    primary_config = tmp_path / "xmlstock.env"
    legacy_config = tmp_path / "yandex-xmlstock.env"
    legacy_config.write_text(
        "XMLSTOCK_YANDEX_XML_USER=legacy-user\nXMLSTOCK_YANDEX_XML_KEY=legacy-key\n",
        encoding="utf-8",
    )

    for name in ("XMLSTOCK_USER", "XMLSTOCK_KEY", "XMLSTOCK_YANDEX_XML_USER", "XMLSTOCK_YANDEX_XML_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(google_xmlstock, "XMLSTOCK_CONFIG", primary_config)
    monkeypatch.setattr(google_xmlstock, "XMLSTOCK_LEGACY_CONFIG", legacy_config)

    captured: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"<doc><title>Result</title><url>https://example.com/a</url><passage>Snippet</passage></doc>"

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(google_xmlstock.urllib.request, "urlopen", fake_urlopen)

    sources, summary, _raw, err = google_xmlstock.google_xmlstock_search("test query", num=3)

    params = parse_qs(urlparse(captured["url"]).query)
    assert err is None
    assert summary["engine"] == "google-xmlstock"
    assert len(sources) == 1
    assert params["user"] == ["legacy-user"]
    assert params["key"] == ["legacy-key"]
