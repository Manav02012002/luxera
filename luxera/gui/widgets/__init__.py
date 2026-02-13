from typing import Any

__all__ = [
    "CopilotPanel",
    "AssistantPanel",
    "ProjectTreeWidget",
    "PropertiesInspector",
    "Viewport2D",
    "ResultsView",
    "VariantsPanel",
    "JobManagerWidget",
    "LogPanel",
]


def __getattr__(name: str) -> Any:
    # Keep GUI package import-safe in non-GUI environments.
    if name == "CopilotPanel":
        from luxera.gui.widgets.copilot_panel import CopilotPanel

        return CopilotPanel
    if name == "AssistantPanel":
        from luxera.gui.widgets.assistant_panel import AssistantPanel

        return AssistantPanel
    if name == "ProjectTreeWidget":
        from luxera.gui.widgets.project_tree import ProjectTreeWidget

        return ProjectTreeWidget
    if name == "PropertiesInspector":
        from luxera.gui.widgets.inspector import PropertiesInspector

        return PropertiesInspector
    if name == "Viewport2D":
        from luxera.gui.widgets.viewport2d import Viewport2D

        return Viewport2D
    if name == "ResultsView":
        from luxera.gui.widgets.results_view import ResultsView

        return ResultsView
    if name == "VariantsPanel":
        from luxera.gui.widgets.variants_panel import VariantsPanel

        return VariantsPanel
    if name == "JobManagerWidget":
        from luxera.gui.widgets.job_manager import JobManagerWidget

        return JobManagerWidget
    if name == "LogPanel":
        from luxera.gui.widgets.log_panel import LogPanel

        return LogPanel
    raise AttributeError(name)
