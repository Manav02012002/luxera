from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional

from luxera.project.schema import Project
from luxera.project.diff import ProjectDiff
from luxera.ai.assistant import propose_luminaire_layout


@dataclass(frozen=True)
class AgentProposal:
    id: str
    created_at: float
    kind: str
    rationale: str
    diff: ProjectDiff
    metrics: Dict[str, Any]


def propose_layout(
    project: Project,
    target_lux: float,
    constraints: Optional[Dict[str, Any]] = None,
) -> AgentProposal:
    diff = propose_luminaire_layout(project, target_lux, constraints=constraints)
    rationale = f"Proposed layout targeting {target_lux} lux with constraints {constraints or {}}"
    return AgentProposal(
        id=str(uuid.uuid4()),
        created_at=time.time(),
        kind="layout",
        rationale=rationale,
        diff=diff,
        metrics={},
    )


def apply_proposal(project: Project, proposal: AgentProposal) -> Project:
    proposal.diff.apply(project)
    project.agent_history.append(
        {
            "id": proposal.id,
            "created_at": proposal.created_at,
            "kind": proposal.kind,
            "rationale": proposal.rationale,
            "metrics": proposal.metrics,
        }
    )
    return project
