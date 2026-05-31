import json
from pathlib import Path

from search_local.artifacts import write_artifacts
from search_local.redaction import redact_text


def test_artifacts_created_and_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "secret-value-123")
    result = {
        "ok": True,
        "profile": "quick",
        "query": "q",
        "sources": [{"engine": "test", "query": "q", "rank": 1, "title": "t", "url": "https://e.test/?key=secret-value-123", "snippet": "secret-value-123"}],
        "summary": {"note": "secret-value-123"},
        "artifacts": {},
        "warnings": [],
    }
    paths = write_artifacts(result, str(tmp_path))
    for key in ("report_md", "sources_jsonl", "summary_json"):
        p = Path(paths[key])
        assert p.exists()
        assert "secret-value-123" not in p.read_text()
    assert "EXA_API_KEY=[REDACTED]" == redact_text("EXA_API_KEY=secret-value-123")
    json.loads(Path(paths["summary_json"]).read_text())
