from __future__ import annotations

import os
import shutil
from pathlib import Path


def _path_from_env(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name, fallback)).expanduser()


def _which_or_path(binary_name: str, env_name: str, fallback: str) -> Path:
    explicit = os.environ.get(env_name)
    if explicit:
        return Path(explicit).expanduser()
    found = shutil.which(binary_name)
    if found:
        return Path(found)
    return Path(fallback).expanduser()


EXA_SEARCH = _which_or_path("exa-search", "EXA_SEARCH_BIN", "~/.local/bin/exa-search")
EXA_FETCH = _which_or_path("exa-fetch", "EXA_FETCH_BIN", "~/.local/bin/exa-fetch")

EXA_CONFIG = _path_from_env("EXA_CONFIG", "~/.config/exa/.env")
GOOGLE_CSE_CONFIG = _path_from_env("GOOGLE_CSE_CONFIG", "~/.config/google-cse/.env")
XMLSTOCK_CONFIG = _path_from_env("XMLSTOCK_CONFIG", "~/.config/xmlstock/.env")
XMLSTOCK_LEGACY_CONFIG = _path_from_env("XMLSTOCK_LEGACY_CONFIG", "~/.config/yandex-xmlstock/.env")
LLM_CONFIG = _path_from_env("SEARCH_LOCAL_LLM_CONFIG", "~/.config/codex-research-mcp/llm.env")
DEEPSEEK_CONFIG = _path_from_env("DEEPSEEK_CONFIG", "~/.config/deepseek/.env")

CACHE_ROOT = _path_from_env(
    "SEARCH_LOCAL_CACHE_ROOT",
    str(Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "codex-research-mcp" / "runs"),
)

GOOGLE_CSE_ENDPOINT = os.environ.get("GOOGLE_CSE_ENDPOINT", "https://www.googleapis.com/customsearch/v1")
XMLSTOCK_GOOGLE_XML_ENDPOINT = os.environ.get("XMLSTOCK_GOOGLE_XML_ENDPOINT", "https://xmlstock.com/google/xml/")


def config_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def secret_config_paths() -> list[Path]:
    return [EXA_CONFIG, GOOGLE_CSE_CONFIG, XMLSTOCK_CONFIG, XMLSTOCK_LEGACY_CONFIG, LLM_CONFIG, DEEPSEEK_CONFIG]


def env_or_config(name: str, *paths: Path) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    for path in paths:
        value = config_values(path).get(name)
        if value:
            return value
    return None


def env_or_config_any(names: tuple[str, ...], *paths: Path) -> str | None:
    for name in names:
        if value := env_or_config(name, *paths):
            return value
    return None
