from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.request
from typing import Any

from .config import DEEPSEEK_CONFIG, LLM_CONFIG, env_or_config_any
from .redaction import redact_text


@dataclass(frozen=True)
class ChatProvider:
    name: str
    api_key: str
    base_url: str
    model: str


def _provider_prefix(provider: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", provider.upper()).strip("_")


def _provider_defaults(provider: str) -> tuple[str | None, str | None]:
    if provider == "deepseek":
        return "https://api.deepseek.com", "deepseek-chat"
    return None, None


def resolve_chat_provider(provider: str, *, model: str | None = None) -> tuple[ChatProvider | None, str | None]:
    normalized = provider.strip().lower()
    if not normalized or normalized == "deterministic":
        return None, "LLM provider is not enabled"

    prefix = _provider_prefix(normalized)
    default_base_url, default_model = _provider_defaults(normalized)
    paths = (LLM_CONFIG, DEEPSEEK_CONFIG)

    api_key = env_or_config_any(
        (
            f"{prefix}_API_KEY",
            "SEARCH_LOCAL_LLM_API_KEY",
            "LLM_API_KEY",
        ),
        *paths,
    )
    base_url = env_or_config_any(
        (
            f"{prefix}_BASE_URL",
            "SEARCH_LOCAL_LLM_BASE_URL",
            "LLM_BASE_URL",
        ),
        *paths,
    ) or default_base_url
    resolved_model = model or env_or_config_any(
        (
            f"{prefix}_MODEL",
            "SEARCH_LOCAL_LLM_MODEL",
            "LLM_MODEL",
        ),
        *paths,
    ) or default_model

    if not api_key:
        return None, f"{prefix}_API_KEY or SEARCH_LOCAL_LLM_API_KEY is required"
    if not base_url:
        return None, f"{prefix}_BASE_URL or SEARCH_LOCAL_LLM_BASE_URL is required"
    if not resolved_model:
        return None, f"{prefix}_MODEL or SEARCH_LOCAL_LLM_MODEL is required"

    return ChatProvider(normalized, api_key, base_url, resolved_model), None


def _chat_completions_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    return f"{root}/chat/completions"


def chat_completion(
    provider: str,
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int = 900,
    temperature: float = 0.2,
    timeout: float = 90.0,
    response_format: dict[str, str] | None = None,
) -> tuple[str | None, dict[str, Any], str | None]:
    config, error = resolve_chat_provider(provider, model=model)
    if error or config is None:
        return None, {}, error

    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    request = urllib.request.Request(
        _chat_completions_url(config.base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, {"provider": config.name, "model": config.model, "status": exc.code}, redact_text(f"HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        return None, {"provider": config.name, "model": config.model}, redact_text(str(exc))
    except OSError as exc:
        return None, {"provider": config.name, "model": config.model}, redact_text(str(exc))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, {"provider": config.name, "model": config.model}, f"invalid JSON response: {exc}"

    choices = data.get("choices") or []
    if not choices:
        return None, {"provider": config.name, "model": config.model}, "empty chat completion choices"
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return None, {"provider": config.name, "model": config.model}, "empty chat completion content"

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    meta = {"provider": config.name, "model": config.model, "usage": usage}
    return content, meta, None
