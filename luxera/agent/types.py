from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class AgentPlan:
    steps: List[str]
    status: str = "ok"


@dataclass(frozen=True)
class ProjectDiff:
    preview: Dict[str, Any]


@dataclass(frozen=True)
class RunManifest:
    payload: Dict[str, Any]


@dataclass(frozen=True)
class AgentSessionLog:
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
