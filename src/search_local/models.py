from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Source:
    engine: str
    query: str
    rank: int
    title: str = ""
    url: str = ""
    domain: str = ""
    snippet: str = ""
    source_type: str = "web"
    published: str | None = None
    author: str | None = None
    highlights: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v not in (None, "", [], {})}
