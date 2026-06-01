import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from search_local import cli, profiles
from search_local.models import Source


QUERY_CASES = [
    "exa pricing",
    "OpenAI Responses API Retry-After",
    'грузовое такси красноярск "цена" site:avito.ru -грузчики',
    "OpenAI Responses API stream disconnected before completion stream closed before response.completed retry backoff idempotency",
]


def _source(query: str, rank: int = 1, *, url: str | None = None, source_type: str = "web") -> Source:
    url = url or f"https://example.com/{rank}"
    return Source(
        engine="fake",
        query=query,
        rank=rank,
        title=f"Result {rank}",
        url=url,
        domain=(urlparse(url).netloc or "example.com").removeprefix("www."),
        snippet=f"snippet for {query}",
        source_type=source_type,
    )


@pytest.mark.parametrize("query", QUERY_CASES)
def test_quick_preserves_varied_queries(monkeypatch, query):
    calls = []

    def fake_exa_search(q, *, num=5, **_kwargs):
        calls.append((q, num))
        return [_source(q)], "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)

    result = profiles.quick(query, num=3)

    assert result["ok"] is True
    assert result["profile"] == "quick"
    assert result["query"] == query
    assert result["summary"]["source_count"] == 1
    assert result["summary"]["engine"] == "exa"
    assert result["summary"]["cache_hit"] is False
    assert result["sources"][0]["query"] == query
    assert calls == [(query, 3)]


@pytest.mark.parametrize("query", QUERY_CASES)
def test_docs_expands_query_but_reports_original(monkeypatch, query):
    calls = []

    def fake_exa_search(q, *, num=6, **_kwargs):
        calls.append((q, num))
        return [_source(q, source_type="official_docs")], "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)

    result = profiles.docs(query, num=2)

    assert result["ok"] is True
    assert result["profile"] == "docs"
    assert result["query"] == query
    assert result["summary"]["official_docs_count"] == 1
    assert calls == [(f"{query} official documentation API reference docs", 2)]


def test_research_builds_multi_query_plan_and_dedupes(monkeypatch):
    query = "OpenAI Responses API Retry-After backoff strategy"
    calls = []

    def fake_exa_search(q, *, num=5, **_kwargs):
        calls.append(q)
        duplicate = _source(q, 1, url="https://docs.example.com/reports")
        unique = _source(q, 2, url=f"https://example.com/{len(calls)}")
        return [duplicate, unique], "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)

    result = profiles.research(query, num=4)

    assert result["ok"] is True
    assert result["profile"] == "research"
    assert result["query"] == query
    assert result["summary"]["subqueries"] == [
        query,
        f"{query} official documentation",
        f"{query} best practices",
        f"{query} issues workaround",
    ]
    assert calls == result["summary"]["subqueries"]
    assert result["summary"]["source_count"] == 5
    assert [src["rank"] for src in result["sources"]] == [1, 2, 3, 4, 5]
    assert all(src["extra"]["subquery"] in calls for src in result["sources"])


def test_fetch_handles_multiple_complex_urls(monkeypatch):
    urls = [
        "https://docs.example.com/api/reports?section=retry-after",
        "https://github.com/org/repo/issues/123#issuecomment-456",
    ]
    calls = []

    def fake_exa_fetch(given_urls):
        calls.append(given_urls)
        return [
            _source(" ".join(given_urls), 1, url=given_urls[0], source_type="fetched_page"),
            _source(" ".join(given_urls), 2, url=given_urls[1], source_type="fetched_page"),
        ], "raw", None

    monkeypatch.setattr(profiles, "exa_fetch", fake_exa_fetch)

    result = profiles.fetch(urls)

    assert result["ok"] is True
    assert result["profile"] == "fetch"
    assert result["query"] == " ".join(urls)
    assert result["summary"]["source_count"] == 2
    assert result["summary"]["engine"] == "exa-fetch"
    assert result["summary"]["cache_hit"] is False
    assert calls == [urls]


def test_google_search_defaults_to_xmlstock(monkeypatch):
    query = "OpenAI Codex for OSS research MCP"
    calls = []

    def fake_google_xmlstock_search(q, *, num=10, page=None, region=None, **_kwargs):
        calls.append((q, num, page, region))
        return [_source(q, url="https://developers.google.com/custom-search/v1/overview", source_type="official_docs")], {
            "source_count": 1,
            "engine": "google-xmlstock",
            "total_results": "10",
        }, "raw", None

    monkeypatch.setattr(profiles, "google_xmlstock_search", fake_google_xmlstock_search)

    result = profiles.google(query, num=7, start=11, region="us")

    assert result["ok"] is True
    assert result["profile"] == "google"
    assert result["query"] == query
    assert result["summary"]["engine"] == "google-xmlstock"
    assert result["summary"]["source_count"] == 1
    assert calls == [(query, 7, 1, "us")]


def test_google_search_can_use_cse_fallback(monkeypatch):
    query = "OpenAI Codex for OSS research MCP"
    calls = []

    def fake_google_cse_search(q, *, num=10, start=1, country=None, language=None, safe=None):
        calls.append((q, num, start, country, language, safe))
        return [_source(q, url="https://developers.google.com/custom-search/v1/overview", source_type="official_docs")], {
            "source_count": 1,
            "engine": "google-cse",
            "total_results": "10",
        }, "raw", None

    monkeypatch.setattr(profiles, "google_cse_search", fake_google_cse_search)

    result = profiles.google(query, num=7, start=11, backend="cse", country="countryUS", language="lang_en", safe="off")

    assert result["ok"] is True
    assert result["summary"]["engine"] == "google-cse"
    assert calls == [(query, 7, 11, "countryUS", "lang_en", "off")]


def test_research_pipeline_dedupes_and_adds_validation(monkeypatch):
    query = "Codex MCP deep research"
    exa_calls = []
    google_calls = []

    def fake_exa_search(q, *, num=5, **_kwargs):
        exa_calls.append((q, num))
        return [
            _source(q, 1, url="https://docs.example.com/api", source_type="official_docs"),
            _source(q, 2, url=f"https://github.com/org/repo/{len(exa_calls)}", source_type="github"),
        ], "raw", None

    def fake_google_xmlstock_search(q, *, num=10, **_kwargs):
        google_calls.append((q, num))
        return [
            _source(q, 1, url="https://docs.example.com/api", source_type="official_docs"),
            _source(q, 2, url=f"https://example.com/article/{len(google_calls)}", source_type="web"),
        ], {"source_count": 2, "engine": "google-xmlstock"}, "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)
    monkeypatch.setattr(profiles, "google_xmlstock_search", fake_google_xmlstock_search)

    result = profiles.research_pipeline(query, max_sources=20)

    assert result["ok"] is True
    assert result["profile"] == "research-pipeline"
    assert result["summary"]["engine"] == "research-pipeline"
    assert result["summary"]["providers"] == ["exa", "google-xmlstock"]
    assert result["summary"]["source_count"] == len(result["sources"])
    assert result["summary"]["unique_domains"] >= 3
    assert len(exa_calls) == 6
    assert len(google_calls) == 6
    assert all("quality_score" in src["extra"] for src in result["sources"])


def test_research_pipeline_scales_per_query_collection_for_200_plus_sources(monkeypatch):
    query = "Codex MCP 200 source research"
    exa_nums = []
    google_nums = []

    def fake_exa_search(q, *, num=5, **_kwargs):
        exa_nums.append(num)
        return [_source(q, rank=i, url=f"https://exa.example.com/{len(exa_nums)}/{i}") for i in range(1, num + 1)], "raw", None

    def fake_google_xmlstock_search(q, *, num=10, **_kwargs):
        google_nums.append(num)
        return [_source(q, rank=i, url=f"https://google.example.com/{len(google_nums)}/{i}") for i in range(1, num + 1)], {"source_count": num, "engine": "google-xmlstock"}, "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)
    monkeypatch.setattr(profiles, "google_xmlstock_search", fake_google_xmlstock_search)

    result = profiles.research_pipeline(query, max_sources=220)

    assert result["ok"] is True
    assert len(result["sources"]) == 220
    assert min(exa_nums) >= 19
    assert min(google_nums) >= 19


def test_research_subagents_runs_lanes_and_quality_audit(monkeypatch):
    query = "deep research agent architecture"
    exa_calls = []
    google_calls = []

    def fake_exa_search(q, *, num=5, **_kwargs):
        exa_calls.append((q, num))
        return [
            _source(q, 1, url=f"https://docs.example.com/{len(exa_calls)}", source_type="official_docs"),
            _source(q, 2, url=f"https://github.com/org/repo/issues/{len(exa_calls)}", source_type="github"),
        ], "raw", None

    def fake_google_xmlstock_search(q, *, num=10, **_kwargs):
        google_calls.append((q, num))
        return [
            _source(q, 1, url=f"https://example.com/report/{len(google_calls)}"),
        ], {"source_count": 1, "engine": "google-xmlstock"}, "raw", None

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)
    monkeypatch.setattr(profiles, "google_xmlstock_search", fake_google_xmlstock_search)

    result = profiles.research_subagents(query, max_sources=36)

    assert result["ok"] is True
    assert result["profile"] == "research-subagents"
    assert result["summary"]["engine"] == "research-subagents"
    assert result["summary"]["providers"] == ["exa", "google-xmlstock"]
    assert len(result["summary"]["subagents"]) == 6
    assert len(exa_calls) == 12
    assert len(google_calls) == 12
    assert result["summary"]["quality_audit"]["overall_score"] > 0
    assert result["summary"]["quality_audit"]["coverage"]["claims_found"] >= 1
    assert all("subagent" in src["extra"] for src in result["sources"])


def test_research_subagents_treats_single_provider_failure_as_partial(monkeypatch):
    def fake_exa_search(q, *, num=5, **_kwargs):
        return [_source(q, 1, url="https://docs.example.com/ok", source_type="official_docs")], "raw", None

    def fake_google_xmlstock_search(q, *, num=10, **_kwargs):
        return [], {"source_count": 0, "engine": "google-xmlstock"}, "", "timeout"

    monkeypatch.setattr(profiles, "exa_search", fake_exa_search)
    monkeypatch.setattr(profiles, "google_xmlstock_search", fake_google_xmlstock_search)

    result = profiles.research_subagents("partial failure", max_sources=12)

    assert result["ok"] is True
    assert result["warnings"]
    assert result["summary"]["partial_failures"] == 12
    assert result["sources"]


def test_doctor_treats_missing_google_cse_as_optional(monkeypatch, tmp_path):
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    exa_config = tmp_path / "exa.env"
    xmlstock_config = tmp_path / "xmlstock.env"
    missing_cse_config = tmp_path / "missing-google-cse.env"
    missing_legacy_config = tmp_path / "missing-legacy.env"
    exa_config.write_text("EXA_API_KEY=test\n", encoding="utf-8")
    xmlstock_config.write_text("XMLSTOCK_USER=user\nXMLSTOCK_KEY=key\n", encoding="utf-8")

    for name in ("GOOGLE_CSE_API_KEY", "GOOGLE_CSE_CX"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(profiles, "EXA_SEARCH", tool)
    monkeypatch.setattr(profiles, "EXA_FETCH", tool)
    monkeypatch.setattr(profiles, "EXA_CONFIG", exa_config)
    monkeypatch.setattr(profiles, "XMLSTOCK_CONFIG", xmlstock_config)
    monkeypatch.setattr(profiles, "XMLSTOCK_LEGACY_CONFIG", missing_legacy_config)
    monkeypatch.setattr(profiles, "GOOGLE_CSE_CONFIG", missing_cse_config)

    result = profiles.doctor(live=False)
    cse_check = next(check for check in result["summary"]["checks"] if check["name"] == "google-cse-config")

    assert result["ok"] is True
    assert result["warnings"] == []
    assert cse_check["ok"] is False
    assert cse_check["optional"] is True


@pytest.mark.parametrize(
    ("argv", "runner_name", "expected"),
    [
        (["quick", "simple query", "--num", "2"], "run_quick", {"query": "simple query", "num": 2}),
        (["docs", "OpenAI Responses API Retry-After", "--num", "3"], "run_docs", {"query": "OpenAI Responses API Retry-After", "num": 3}),
        (["research", 'сложный запрос "кавычки" -минус', "--num", "4"], "run_research", {"query": 'сложный запрос "кавычки" -минус', "num": 4}),
        (["pipeline", "Codex MCP research", "--max-sources", "30", "--no-google"], "run_research_pipeline", {"query": "Codex MCP research", "max_sources": 30, "include_google": False, "include_exa": True, "google_backend": "xmlstock"}),
        (["pipeline", "Codex MCP research", "--google-backend", "cse"], "run_research_pipeline", {"query": "Codex MCP research", "max_sources": 80, "include_google": True, "include_exa": True, "google_backend": "cse"}),
        (["deep", "Codex MCP research", "--max-sources", "40", "--no-exa"], "run_research_subagents", {"query": "Codex MCP research", "max_sources": 40, "include_google": True, "include_exa": False, "google_backend": "xmlstock"}),
        (["google", "OpenAI Codex OSS", "--num", "7", "--start", "11", "--backend", "cse", "--country", "countryUS", "--language", "lang_en", "--safe", "off"], "run_google", {"query": "OpenAI Codex OSS", "num": 7, "start": 11, "region": None, "backend": "cse", "country": "countryUS", "language": "lang_en", "safe": "off"}),
        (["fetch", "https://example.com/a?x=1", "https://example.com/b#frag"], "run_fetch", {"urls": ["https://example.com/a?x=1", "https://example.com/b#frag"]}),
    ],
)
def test_cli_dispatch_contract_for_varied_commands(monkeypatch, tmp_path, capsys, argv, runner_name, expected):
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        query = expected.get("query") or " ".join(expected.get("urls", []))
        return {
            "ok": True,
            "profile": argv[0],
            "query": query,
            "sources": [_source(query).to_dict()],
            "summary": {"source_count": 1, "engine": "fake"},
            "artifacts": {},
            "warnings": [],
        }

    monkeypatch.setattr(cli, runner_name, fake_runner)

    code = cli.main([*argv, "--out", str(tmp_path), "--json"])
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 0
    assert payload["ok"] is True
    assert set(payload) == {"ok", "profile", "query", "sources", "summary", "artifacts", "warnings"}
    assert Path(payload["artifacts"]["report_md"]).exists()
    assert Path(payload["artifacts"]["sources_jsonl"]).exists()
    assert Path(payload["artifacts"]["summary_json"]).exists()

    args, kwargs = calls[0]
    if runner_name == "run_fetch":
        assert args == (expected["urls"],)
        assert kwargs == {}
    elif runner_name == "run_research_pipeline":
        assert args == (expected["query"],)
        assert kwargs == {"max_sources": expected["max_sources"], "include_google": expected["include_google"], "include_exa": expected["include_exa"], "google_backend": expected["google_backend"]}
    elif runner_name == "run_research_subagents":
        assert args == (expected["query"],)
        assert kwargs == {"max_sources": expected["max_sources"], "include_google": expected["include_google"], "include_exa": expected["include_exa"], "google_backend": expected["google_backend"]}
    elif runner_name == "run_google":
        assert args == (expected["query"],)
        assert kwargs == {"num": expected["num"], "start": expected["start"], "region": expected["region"], "backend": expected["backend"], "country": expected["country"], "language": expected["language"], "safe": expected["safe"]}
    else:
        assert args == (expected["query"],)
        assert kwargs == {"num": expected["num"]}


def test_cli_json_and_artifacts_redact_complex_secret_leaks(monkeypatch, tmp_path, capsys):
    secret = "exa-secret-value-456"
    monkeypatch.setenv("EXA_API_KEY", secret)

    def fake_quick(query, *, num=5):
        return {
            "ok": True,
            "profile": "quick",
            "query": query,
            "sources": [_source(query, url=f"https://example.com/page?key={secret}").to_dict()],
            "summary": {"source_count": 1, "note": f"EXA_API_KEY={secret}"},
            "artifacts": {},
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_quick", fake_quick)

    code = cli.main(["quick", "secret handling query", "--out", str(tmp_path), "--json"])
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 0
    assert secret not in stdout
    for key, artifact_path in payload["artifacts"].items():
        if key == "run_dir":
            continue
        assert secret not in Path(artifact_path).read_text(encoding="utf-8")
