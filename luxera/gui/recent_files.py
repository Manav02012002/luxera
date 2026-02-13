from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


def coerce_recent_paths(raw: object) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, Iterable):
        out: List[str] = []
        for item in raw:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.append(s)
        return out
    return []


def add_recent_path(paths: List[str], path: str, *, max_items: int = 10) -> List[str]:
    resolved = str(Path(path).expanduser().resolve())
    deduped = [resolved]
    for p in paths:
        if p != resolved:
            deduped.append(p)
    return deduped[: max(1, int(max_items))]
