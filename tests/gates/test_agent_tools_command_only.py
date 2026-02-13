from __future__ import annotations

import inspect

import luxera.agent.tools.api as api_mod
from luxera.agent.tools.api import AgentTools
from luxera.agent.tools.registry import build_default_registry


def test_registry_surface_maps_to_gui_command_layer() -> None:
    reg = build_default_registry(AgentTools())
    surface = reg.describe()
    for name in ("project.open", "project.diff.apply", "job.run", "results.heatmap", "report.pdf", "bundle.audit"):
        assert name in surface


def test_agent_tools_do_not_import_engine_or_runner_exec_paths() -> None:
    src = inspect.getsource(api_mod)
    assert "from luxera.engine." not in src
    assert "from luxera.project.runner import" not in src
    assert "from luxera.ai.assistant import" not in src
    assert "from luxera.geometry.scene_prep import" not in src
    assert "run_job_in_memory(" not in src


def test_stateful_tool_methods_route_via_cmd_functions() -> None:
    required = {
        AgentTools.apply_diff: "cmd_apply_diff",
        AgentTools.run_job: "cmd_run_job",
        AgentTools.import_geometry: "cmd_import_geometry",
        AgentTools.clean_geometry: "cmd_clean_geometry",
        AgentTools.propose_layout_diff: "cmd_propose_layout",
        AgentTools.render_heatmap: "cmd_render_heatmap",
        AgentTools.build_pdf: "cmd_export_report",
    }
    for method, token in required.items():
        src = inspect.getsource(method)
        assert token in src
