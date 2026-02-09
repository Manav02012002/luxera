from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional

from luxera.project.schema import Project
from luxera.project.diff import ProjectDiff
from luxera.ai.assistant import propose_luminaire_layout
from luxera.agent.audit import append_audit_event


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
    append_audit_event(
        project,
        action="agent.propose_layout",
        plan="Generate candidate layout diff from target lux and constraints.",
        diffs=[{"ops": len(diff.ops)}],
        metadata={"target_lux": target_lux, "constraints": constraints or {}},
    )
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
    append_audit_event(
        project,
        action="agent.apply_proposal",
        plan="Apply approved proposal diff to project state.",
        diffs=[{"ops": len(proposal.diff.ops)}],
        metadata={"proposal_id": proposal.id, "kind": proposal.kind},
    )
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
