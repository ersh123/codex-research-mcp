from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .redaction import redact_text


def run_cmd(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    proc.stdout = redact_text(proc.stdout or "")
    proc.stderr = redact_text(proc.stderr or "")
    return proc


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        value = domain_from_url(value)
    value = value.split("/")[0].split(":")[0]
    if value.startswith("www."):
        value = value[4:]
    try:
        value = value.encode("idna").decode("ascii")
    except Exception:
        pass
    return value


def domain_matches(domain: str, target: str) -> bool:
    if not domain or not target:
        return False
    d = normalize_domain(domain)
    t = normalize_domain(target)
    return d == t or d.endswith("." + t)


def slugify(text: str, max_len: int = 60) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\-а-яё]+", "-", text, flags=re.I)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text[:max_len].strip("-") or "run")


def timestamp_slug(query: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{slugify(query)}"
