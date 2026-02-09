import pytest


pytestmark = pytest.mark.gui


def test_gui_import():
    import luxera.gui.app  # noqa: F401
