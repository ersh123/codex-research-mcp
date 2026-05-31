from __future__ import annotations

import os
import re
from pathlib import Path

from .config import secret_config_paths

SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer|google_cse_api_key|exa_api_key|xmlstock_key)\s*[:=]\s*([^\s\"',}]+)")
CREDENTIAL_URL_RE = re.compile(r"(?i)([?&](?:key|token|password|user)=)[^&\s\"'<>]+")


def _read_env_values(path: Path) -> list[str]:
    values: list[str] = []
    if not path.exists():
        return values
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if re.search(r"(?i)(key|token|secret|password)", key):
                value = value.strip().strip('"').strip("'")
                if len(value) >= 6:
                    values.append(value)
    except OSError:
        pass
    return values


def secret_values() -> list[str]:
    vals: list[str] = []
    for key, value in os.environ.items():
        if re.search(r"(?i)(key|token|secret|password)", key) and len(value) >= 6:
            vals.append(value)
    for path in secret_config_paths():
        vals.extend(_read_env_values(path))
    return sorted(set(vals), key=len, reverse=True)


def redact_text(text: str) -> str:
    redacted = text
    for value in secret_values():
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
    redacted = CREDENTIAL_URL_RE.sub(lambda m: f"{m.group(1)}[REDACTED]", redacted)
    return redacted
