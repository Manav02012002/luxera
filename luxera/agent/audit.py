from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List

from luxera.project.schema import Project


@dataclass(frozen=True)
class AgentAuditEvent:
    id: str
    created_at: float
    action: str
    plan: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    diffs: List[Dict[str, Any]] = field(default_factory=list)
    job_hashes: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def append_audit_event(project: Project, action: str, plan: str, **kwargs: Any) -> AgentAuditEvent:
    event = AgentAuditEvent(
        id=str(uuid.uuid4()),
        created_at=time.time(),
        action=action,
        plan=plan,
        tool_calls=list(kwargs.get("tool_calls", [])),
        diffs=list(kwargs.get("diffs", [])),
        job_hashes=list(kwargs.get("job_hashes", [])),
        artifacts=list(kwargs.get("artifacts", [])),
        warnings=list(kwargs.get("warnings", [])),
        metadata=dict(kwargs.get("metadata", {})),
    )
    project.agent_history.append(event.to_dict())
    return event
