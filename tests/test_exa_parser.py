from search_local.adapters.exa import parse_exa_markdown


def test_parse_exa_wrapper_output():
    text = """# Exa Search Results
requestId: abc
## Official API Docs
- URL: https://docs.example.com/api/reference
- Published: 2026-01-01
- Summary: Useful summary.
- Highlights:
  - Important highlight.
## GitHub issue
- URL: https://github.com/org/repo/issues/1
- Summary: Workaround found.
"""
    sources = parse_exa_markdown(text, query="api docs")
    assert len(sources) == 2
    assert sources[0].title == "Official API Docs"
    assert sources[0].domain == "docs.example.com"
    assert sources[0].source_type == "official_docs"
    assert sources[1].source_type == "github"
