import json

from search_local import config, llm, subagents


def test_resolve_deepseek_provider_reads_private_config(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.env"
    cfg.write_text(
        "DEEPSEEK_API_KEY=test-secret-value\n"
        "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "DEEPSEEK_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(llm, "LLM_CONFIG", cfg)
    monkeypatch.setattr(llm, "DEEPSEEK_CONFIG", tmp_path / "missing.env")
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "SEARCH_LOCAL_LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    provider, error = llm.resolve_chat_provider("deepseek")

    assert error is None
    assert provider.name == "deepseek"
    assert provider.api_key == "test-secret-value"
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.model == "deepseek-chat"


def test_chat_completion_calls_openai_compatible_endpoint(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.env"
    cfg.write_text("DEEPSEEK_API_KEY=test-secret-value\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")
    monkeypatch.setattr(llm, "LLM_CONFIG", cfg)
    monkeypatch.setattr(llm, "DEEPSEEK_CONFIG", tmp_path / "missing.env")
    for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{\"subagents\": []}"}}], "usage": {"total_tokens": 12}}).encode()

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["payload"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    content, meta, error = llm.chat_completion("deepseek", [{"role": "user", "content": "plan"}], timeout=12)

    assert error is None
    assert content == "{\"subagents\": []}"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["auth"] == "Bearer test-secret-value"
    assert captured["payload"]["model"] == "deepseek-chat"
    assert captured["timeout"] == 12
    assert meta["usage"]["total_tokens"] == 12


def test_build_provider_subagent_plan_parses_llm_json(monkeypatch):
    topic = "Yandex Direct 2026 optimization research"
    payload = {
        "subagents": [
            {"name": f"Lane {index}", "objective": f"Objective {index}", "queries": [f"{topic} angle {index}"]}
            for index in range(10)
        ]
    }

    def fake_chat(provider, messages, *, model=None, **_kwargs):
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert "subagent_count" in messages[1]["content"]
        return json.dumps(payload), {"provider": provider, "model": model, "usage": {"total_tokens": 100}}, None

    monkeypatch.setattr(subagents, "chat_completion", fake_chat)

    plan, meta, warnings = subagents.build_provider_subagent_plan(topic, provider="deepseek", count=10, model="deepseek-chat")

    assert warnings == []
    assert meta["planner_ok"] is True
    assert len(plan) == 10
    assert plan[0]["name"] == "lane_0"
    assert plan[-1]["queries"] == [f"{topic} angle 9"]


def test_build_provider_subagent_plan_falls_back_on_bad_llm_json(monkeypatch):
    monkeypatch.setattr(subagents, "chat_completion", lambda *_args, **_kwargs: ("not-json", {"provider": "deepseek"}, None))

    plan, meta, warnings = subagents.build_provider_subagent_plan("Codex research", provider="deepseek", count=10)

    assert len(plan) == 10
    assert meta["planner_ok"] is False
    assert warnings
    assert plan[0]["name"] == "scope_mapper"


def test_build_provider_subagent_plan_retries_timeout(monkeypatch):
    topic = "Yandex Direct 2026"
    calls = []
    payload = {"subagents": [{"name": f"lane_{index}", "objective": "Objective", "queries": [f"{topic} {index}"]} for index in range(10)]}

    def fake_chat(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return None, {"provider": "deepseek"}, "<urlopen error timed out>"
        return json.dumps(payload), {"provider": "deepseek", "usage": {"total_tokens": 50}}, None

    monkeypatch.setattr(subagents, "chat_completion", fake_chat)

    plan, meta, warnings = subagents.build_provider_subagent_plan(topic, provider="deepseek", count=10)

    assert len(calls) == 2
    assert warnings == []
    assert meta["planner_ok"] is True
    assert len(plan) == 10


def test_redaction_includes_private_llm_config(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.env"
    cfg.write_text("DEEPSEEK_API_KEY=test-secret-value\n", encoding="utf-8")
    monkeypatch.setattr(config, "LLM_CONFIG", cfg)
    monkeypatch.setattr(config, "DEEPSEEK_CONFIG", tmp_path / "missing.env")

    from search_local.redaction import redact_text

    assert "test-secret-value" not in redact_text("leaked test-secret-value")
