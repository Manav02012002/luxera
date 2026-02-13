from __future__ import annotations

import inspect

from luxera.agent.tools.api import AgentTools
from luxera.agent.tools.registry import build_default_registry


def test_registry_exposes_gui_command_surface() -> None:
    tools = AgentTools()
    registry = build_default_registry(tools)
    surface = registry.describe()
    expected = {
        "geom.import",
        "geom.clean",
        "project.grid.add",
        "job.run",
        "report.pdf",
        "bundle.audit",
    }
    for name in expected:
        assert name in surface


def test_agent_tools_use_command_layer_for_stateful_ops() -> None:
    methods = [
        AgentTools.import_geometry,
        AgentTools.clean_geometry,
        AgentTools.add_grid,
        AgentTools.run_job,
        AgentTools.build_pdf,
    ]
    for method in methods:
        src = inspect.getsource(method)
        assert "cmd_" in src


def test_agent_tools_avoid_raw_file_writes_in_runtime_surface() -> None:
    src = inspect.getsource(AgentTools)
    assert "write_text(" not in src
    assert "write_bytes(" not in src
