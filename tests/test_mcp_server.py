import json

from search_local import mcp_server


def test_mcp_lists_codex_research_tools():
    response = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}

    assert {"exa_quick", "google_search", "research_pipeline", "search_doctor"} <= names
    assert "yandex_search" not in names


def test_mcp_research_pipeline_call_returns_text_json(monkeypatch):
    def fake_pipeline(query, *, max_sources=80, include_google=True, include_exa=True, google_backend="xmlstock"):
        return {
            "ok": True,
            "profile": "research-pipeline",
            "query": query,
            "sources": [],
            "summary": {
                "engine": "research-pipeline",
                "max_sources": max_sources,
                "include_google": include_google,
                "include_exa": include_exa,
                "google_backend": google_backend,
            },
            "artifacts": {},
            "warnings": [],
        }

    monkeypatch.setattr(mcp_server, "research_pipeline", fake_pipeline)
    monkeypatch.setattr(mcp_server, "write_artifacts", lambda result: {"report_md": "/tmp/report.md"})

    response = mcp_server.handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "research_pipeline",
            "arguments": {"query": "Codex OSS", "max_sources": 12, "include_google": False},
        },
    })

    text = response["result"]["content"][0]["text"]
    payload = json.loads(text)

    assert payload["profile"] == "research-pipeline"
    assert payload["summary"]["max_sources"] == 12
    assert payload["summary"]["include_google"] is False
    assert payload["artifacts"] == {"report_md": "/tmp/report.md"}
