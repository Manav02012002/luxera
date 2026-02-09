from pathlib import Path

from luxera.agent.audit import append_audit_event
from luxera.project.schema import Project


def test_append_audit_event():
    project = Project(name="Audit")
    ev = append_audit_event(
        project,
        action="test.action",
        plan="Do test action",
        artifacts=["a.txt"],
        job_hashes=["h1"],
    )
    assert ev.action == "test.action"
    assert project.agent_history
    assert project.agent_history[-1]["action"] == "test.action"
