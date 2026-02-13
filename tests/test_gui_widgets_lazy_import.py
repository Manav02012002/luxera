from __future__ import annotations

import inspect

import luxera.gui.widgets as widgets


def test_widgets_package_uses_lazy_getattr_imports() -> None:
    src = inspect.getsource(widgets)
    assert "__getattr__" in src
    assert "from luxera.gui.widgets.copilot_panel import CopilotPanel" in src
